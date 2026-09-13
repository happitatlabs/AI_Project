import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import ts from 'typescript';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'sql-members-'));
const databases = [];
const originalFetch = globalThis.fetch;
try {
  for (const folder of ['src', 'api']) {
    fs.mkdirSync(path.join(temp, folder));
    for (const file of fs.readdirSync(folder).filter(f => f.endsWith('.ts'))) {
      fs.writeFileSync(path.join(temp, folder, file.replace(/\.ts$/, '.js')), ts.transpileModule(fs.readFileSync(path.join(folder, file), 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2020 },
      }).outputText);
    }
  }
  fs.writeFileSync(path.join(temp, 'package.json'), '{"type":"module"}');
  const { MemberAccount, memberRequest } = await import(pathToFileURL(path.join(temp, 'src/memberAccount.js')));
  const { memberCookie, readMember, digest } = await import(pathToFileURL(path.join(temp, 'src/memberAuth.js')));
  const { explainSql } = await import(pathToFileURL(path.join(temp, 'src/sqlExplainer.js')));
  const { default: worker } = await import(pathToFileURL(path.join(temp, 'src/cloudflareWorker.js')));
  const { resolveCreditOperation, CREDIT_OPERATIONS } = await import(pathToFileURL(path.join(temp, 'src/creditPolicy.js')));
  assert.equal(resolveCreditOperation('/api/ai-explain', { sql: "SELECT ';' AS x; -- ;" }), 'single');
  assert.equal(resolveCreditOperation('/api/ai-explain', { sql: 'SELECT $$a;b$$ AS "a;b"; /* ; */' }), 'single');
  assert.equal(resolveCreditOperation('/api/ai-explain', { sql: 'SELECT 1; SELECT 2;', mode: 'single', cost: 0 }), 'multi');
  assert.equal(resolveCreditOperation('/api/ai-explain', { sql: 'SELECT 1;', mode: 'multi' }), 'multi');
  assert.equal(resolveCreditOperation('/api/ai-document-draft', { sql: 'SELECT 1; SELECT 2;' }), 'multiDocument');
  const records = new Map();
  const namespace = {
    idFromName: name => name,
    get(id) {
      if (!records.has(id)) {
        const db = new DatabaseSync(':memory:'); databases.push(db);
        const storage = {
          sql: { exec(query, ...params) { const statement = db.prepare(query); return { toArray: () => statement.all(...params) }; } },
          transactionSync(callback) { db.exec('BEGIN'); try { const value = callback(); db.exec('COMMIT'); return value; } catch (e) { db.exec('ROLLBACK'); throw e; } },
        };
        // Cloudflare executes on exec(), whereas node:sqlite executes when all() is called.
        storage.sql.exec = (query, ...params) => { const rows = db.prepare(query).all(...params); return { toArray: () => rows }; };
        records.set(id, { storage, object: new MemberAccount({ storage }) });
      }
      return { fetch: request => records.get(id).object.fetch(request) };
    },
  };
  const origin = 'https://demo.example';
  const env = { AI_CREDITS_ENABLED: 'true', PUBLIC_ORIGIN: origin, MEMBER_ACCOUNTS: namespace,
    DEMO_USERNAME: 'plushome58@naver.com', DEMO_PASSWORD: 'synthetic-admin-password', DEMO_SESSION_SECRET: 'synthetic-signing-secret-at-least-32-characters',
    AI_PROVIDER: 'openai', OPENAI_API_KEY: 'synthetic-key', OPENAI_MODEL: 'synthetic-model', ASSETS: { fetch: async () => new Response('public app') } };
  const req = (pathname, body, cookie, extra = {}) => new Request(origin + pathname, { method: body === undefined ? 'GET' : 'POST',
    headers: { Origin: origin, 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}), ...extra }, body: body === undefined ? undefined : JSON.stringify(body) });
  const call = (pathname, body, cookie, extra) => worker.fetch(req(pathname, body, cookie, extra), env);
  const runtime = async cookie => (await call('/api/runtime-config', undefined, cookie)).json();
  assert.equal(await (await call('/')).text(), 'public app');
  assert.equal((await runtime()).loginRequired, false);
  assert.equal((await runtime()).aiEnabled, false);
  assert.deepEqual((await runtime()).providers, []);
  assert.equal((await call('/api/ai-explain', {})).status, 401);
  assert.equal((await call('/api/auth/google/start')).status, 503);
  assert.equal((await worker.fetch(new Request(origin + '/api/auth/register', { method: 'POST', body: '{}' }), env)).status, 403);

  const signup = await call('/api/auth/register', { username: 'member-one', password: 'long-synthetic-password' });
  assert.equal(signup.status, 200);
  const cookie = signup.headers.get('set-cookie').split(';')[0];
  assert.equal((await runtime(cookie)).credits.remaining, 10);
  assert.equal((await call('/api/auth/register', { username: 'member-one', password: 'another-long-password' })).status, 409);
  assert.equal((await call('/api/auth/register', { username: 'plushome58@naver.com', password: 'another-long-password' })).status, 400);
  assert.equal((await call('/api/auth/member-login', { username: 'member-one', password: 'wrong-long-password' })).status, 401);
  assert.equal((await call('/api/auth/member-login', { username: 'member-one', password: 'long-synthetic-password' })).status, 200);
  const identity = await readMember(req('/', undefined, cookie), env);
  assert.equal(identity.unlimited, false);
  const tampered = cookie.slice(0, -4) + 'AAAA';
  assert.equal((await runtime(tampered)).authenticated, false);
  for (const route of ['/api/ai-explain', '/api/ai-data-insights', '/api/ai-sql-rewrite', '/api/ai-document-draft', '/api/ai-multi-document-draft']) {
    assert.notEqual((await call(route, {}, cookie)).status, 200);
    assert.equal((await runtime(cookie)).credits.remaining, 10, 'invalid input must release the full operation cost');
  }
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ output_text: JSON.stringify({ sql: 'SELECT id FROM users;', summary: 'test recommendation', warnings: [] }) }); };
  const id = crypto.randomUUID();
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie, { 'X-Request-Id': id })).status, 200);
  assert.equal((await runtime(cookie)).credits.remaining, 7);
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie, { 'X-Request-Id': id })).status, 409);
  for (let i = 0; i < 2; i++) assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;', cost: 0, unlimited: true }, cookie)).status, 200);
  const insufficient = await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie);
  assert.equal(insufficient.status, 402);
  assert.deepEqual((await insufficient.json()).credits, { remaining: 1, required: 3, unlimited: false });
  assert.equal(calls, 3, 'no provider call when remaining is positive but insufficient');
  const pricedCookie = await memberCookie({ id: 'priced-member', username: 'priced-member', unlimited: false }, env.DEMO_SESSION_SECRET);
  const pricedSql = 'SELECT id FROM users;';
  assert.equal((await call('/api/ai-explain', { sql: pricedSql, analysis: explainSql(pricedSql) }, pricedCookie)).status, 200);
  assert.equal((await runtime(pricedCookie)).credits.remaining, 9);
  assert.equal((await call('/api/ai-explain', { sql: pricedSql, analysis: explainSql(pricedSql), mode: 'multi' }, pricedCookie)).status, 200);
  assert.equal((await runtime(pricedCookie)).credits.remaining, 7);
  assert.equal((await call('/api/ai-explain', { sql: `${pricedSql} SELECT 2;`, analysis: explainSql(pricedSql), mode: 'single', cost: 1 }, pricedCookie)).status, 200);
  assert.equal((await runtime(pricedCookie)).credits.remaining, 5, 'multi SQL cannot obtain the single price by changing a browser field');
  const record = records.get(identity.id); record.object = new MemberAccount({ storage: record.storage });
  assert.equal((await runtime(cookie)).credits.remaining, 1, 'no daily/session/restart trial refill');
  const history = await (await call('/api/credits/history', undefined, cookie)).json();
  assert.equal(history.entries.filter(e => e.kind === 'signup').length, 1);
  assert.equal(history.entries.filter(e => e.kind === 'spent').reduce((sum, e) => sum + e.used, 0), 9);
  assert.equal(history.entries.reduce((sum, e) => sum + e.delta, 0), 1);
  assert.equal(history.entries[0].remaining, 1);
  assert.ok(!JSON.stringify(history).includes('SELECT'), 'credit history contains no SQL');
  assert.equal((await call('/api/credits/history')).status, 401);
  assert.equal((await call('/api/credits/history?before=bad', undefined, cookie)).status, 400);
  const concurrent = await Promise.all(Array.from({ length: 8 }, () => memberRequest(namespace, 'concurrent-member', '/reserve', { id: crypto.randomUUID(), operation: 'rewrite' })));
  assert.equal(concurrent.filter(r => r.status === 200).length, 3);
  assert.equal(concurrent.filter(r => r.status === 402).length, 5);
  assert.equal((await (await memberRequest(namespace, 'concurrent-member', '/balance')).json()).remaining, 1);
  const reservationId = crypto.randomUUID();
  await memberRequest(namespace, 'refund-member', '/reserve', { id: reservationId, operation: 'rewrite' });
  await memberRequest(namespace, 'refund-member', '/release', { id: reservationId });
  await memberRequest(namespace, 'refund-member', '/release', { id: reservationId });
  assert.equal((await (await memberRequest(namespace, 'refund-member', '/balance')).json()).remaining, 10);
  assert.equal((await memberRequest(namespace, 'refund-member', '/complete', { id: reservationId })).status, 409, 'cancelled result cannot be completed/delivered for free');
  const trial = await memberCookie({ id: 'failure-member', username: 'failure-user', unlimited: false }, env.DEMO_SESSION_SECRET);
  globalThis.fetch = async () => { throw new Error('synthetic provider failure'); };
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, trial)).status, 502);
  assert.equal((await runtime(trial)).credits.remaining, 10);

  // Different-cost reservations must refund their actual charges, including after restart/expiry.
  for (const operation of Object.keys(CREDIT_OPERATIONS)) {
    const accountId = `operation-${operation}`;
    const reservation = crypto.randomUUID();
    const held = await (await memberRequest(namespace, accountId, '/reserve', { id: reservation, operation })).json();
    assert.equal(held.remaining, 10 - CREDIT_OPERATIONS[operation].cost);
    await memberRequest(namespace, accountId, '/complete', { id: reservation });
    await memberRequest(namespace, accountId, '/release', { id: reservation });
    assert.equal((await (await memberRequest(namespace, accountId, '/balance')).json()).remaining, held.remaining, 'completed use cannot be refunded');
  }
  await memberRequest(namespace, 'expiry', '/reserve', { id: crypto.randomUUID(), operation: 'multi' });
  await memberRequest(namespace, 'expiry', '/reserve', { id: crypto.randomUUID(), operation: 'insights' });
  records.get('expiry').storage.sql.exec('UPDATE ledger SET expires=0');
  assert.equal((await (await memberRequest(namespace, 'expiry', '/balance')).json()).remaining, 10);
  assert.equal((await (await memberRequest(namespace, 'expiry', '/balance')).json()).remaining, 10, 'expiry cannot refund twice');

  // Reconstruct the production v1 schema in a synthetic in-memory account.
  namespace.get('old-wallet');
  const oldStorage = records.get('old-wallet').storage;
  oldStorage.sql.exec('DROP TABLE ledger');
  oldStorage.sql.exec('DROP TABLE credit_events');
  oldStorage.sql.exec('INSERT INTO wallet VALUES (1, 4)');
  oldStorage.sql.exec('CREATE TABLE ledger (id TEXT PRIMARY KEY, status TEXT NOT NULL, expires INTEGER NOT NULL)');
  oldStorage.sql.exec("INSERT INTO ledger VALUES (?, 'reserved', 0)", crypto.randomUUID());
  records.get('old-wallet').object = new MemberAccount({ storage: oldStorage });
  assert.equal((await (await memberRequest(namespace, 'old-wallet', '/balance')).json()).remaining, 5);
  records.get('old-wallet').object = new MemberAccount({ storage: oldStorage });
  const migratedHistory = await (await memberRequest(namespace, 'old-wallet', '/history')).json();
  assert.equal(migratedHistory.entries.filter(e => e.kind === 'opening').length, 1);
  assert.equal(migratedHistory.entries.filter(e => e.kind === 'signup').length, 0);
  assert.equal((await (await memberRequest(namespace, 'old-wallet', '/balance')).json()).remaining, 5, 'existing members receive no automatic refill');

  for (let i = 0; i < 27; i++) {
    const requestId = crypto.randomUUID();
    await memberRequest(namespace, 'paged', '/reserve', { id: requestId, operation: 'multi' });
    await memberRequest(namespace, 'paged', '/release', { id: requestId });
  }
  const pagedCookie = await memberCookie({ id: 'paged', username: 'paged', unlimited: false }, env.DEMO_SESSION_SECRET);
  const firstPage = await (await call('/api/credits/history', undefined, pagedCookie)).json();
  const secondPage = await (await call(`/api/credits/history?before=${firstPage.nextCursor}`, undefined, pagedCookie)).json();
  assert.equal(firstPage.entries.length, 50);
  assert.equal(secondPage.entries.length, 5);
  assert.equal(new Set([...firstPage.entries, ...secondPage.entries].map(e => e.seq)).size, 55);
  assert.ok(!(await (await call('/api/credits/history', undefined, pagedCookie)).json()).entries.some(e => e.kind === 'spent'), 'history is scoped to the signed-in member');

  const adminLogin = await call('/api/auth/login', { username: env.DEMO_USERNAME, password: env.DEMO_PASSWORD });
  const adminCookie = adminLogin.headers.get('set-cookie').split(';')[0];
  assert.equal((await runtime(adminCookie)).credits.unlimited, true);
  globalThis.fetch = async () => Response.json({ output_text: JSON.stringify({ sql: 'SELECT id FROM users;', summary: 'test', warnings: [] }) });
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, adminCookie)).status, 200);
  const unlimitedHistory = await (await call('/api/credits/history', undefined, adminCookie)).json();
  assert.ok(unlimitedHistory.entries.some(e => e.kind === 'unlimited' && e.used === 0 && e.remaining === null));
  const fakeEmail = await memberCookie({ id: 'local:fake', username: env.DEMO_USERNAME, unlimited: false }, env.DEMO_SESSION_SECRET);
  assert.equal((await runtime(fakeEmail)).credits.unlimited, false, 'display email cannot grant unlimited');
  assert.equal((await call('/api/credits/grant', { amount: 999 }, cookie)).status, 503);
  assert.equal((await call('/api/payments/confirm', { amount: 999 }, cookie)).status, 503);
  const catalog = await (await call('/api/credits/packs')).json();
  assert.deepEqual(catalog.packs.map(p => p.credits), [30, 100, 300]);
  assert.ok(catalog.packs.every(p => p.price === null && p.available === false));
  assert.equal(catalog.paymentsEnabled, false);
  const logout = await call('/api/auth/logout', {}, cookie);
  assert.match(logout.headers.get('set-cookie'), /__Host-sql-member=;/);
  assert.match(logout.headers.get('set-cookie'), /__Host-sql-diagnoser-demo=;/);

  const socialEnv = { ...env, OAUTH_GOOGLE_CLIENT_ID: 'synthetic-client', OAUTH_GOOGLE_CLIENT_SECRET: 'synthetic-secret' };
  const start = await worker.fetch(req('/api/auth/google/start'), socialEnv);
  assert.equal(start.status, 302);
  const authUrl = new URL(start.headers.get('location'));
  assert.ok(authUrl.searchParams.get('code_challenge'));
  const oauthCookie = start.headers.get('set-cookie').split(';')[0];
  const invalid = await worker.fetch(req('/api/auth/google/callback?code=synthetic&state=wrong', undefined, oauthCookie), socialEnv);
  assert.match(await invalid.text(), /ok:false/);
  globalThis.fetch = async url => String(url).includes('/token') ? Response.json({ access_token: 'synthetic-token' }) : Response.json({ sub: 'subject-1', email: env.DEMO_USERNAME, email_verified: false });
  const socialLogin = await worker.fetch(req(`/api/auth/google/callback?code=synthetic&state=${authUrl.searchParams.get('state')}`, undefined, oauthCookie), socialEnv);
  assert.equal(socialLogin.status, 200);
  const socialCookies = socialLogin.headers.getSetCookie().find(c => c.startsWith('__Host-sql-member=')).split(';')[0];
  assert.equal((await runtime(socialCookies)).credits.unlimited, false, 'unverified provider email cannot grant unlimited');
  assert.equal((await runtime(socialCookies)).credits.remaining, 10);
  assert.equal((await readMember(req('/', undefined, socialCookies), env)).id, 'google:' + await digest('subject-1'));
  const kakaoEnv = { ...env, OAUTH_KAKAO_CLIENT_ID: 'synthetic-kakao' };
  const kakaoStart = await worker.fetch(req('/api/auth/kakao/start'), kakaoEnv);
  const kakaoUrl = new URL(kakaoStart.headers.get('location'));
  const kakaoCookie = kakaoStart.headers.get('set-cookie').split(';')[0];
  globalThis.fetch = async (url, options) => {
    if (String(url).includes('/token')) {
      assert.equal(options.body.has('client_secret'), false, 'optional secret must not send the string undefined');
      return Response.json({ access_token: 'synthetic' });
    }
    return Response.json({ id: 123 });
  };
  const kakaoResult = await worker.fetch(req(`/api/auth/kakao/callback?code=test&state=${kakaoUrl.searchParams.get('state')}`, undefined, kakaoCookie), kakaoEnv);
  assert.match(await kakaoResult.text(), /ok:true/);
  console.log('member credits: 10-credit signup, operation costs, positive shortage, concurrency, history, migration, refunds, unlimited access, disabled packs and OAuth tests passed');
} finally { globalThis.fetch = originalFetch; databases.forEach(db => db.close()); fs.rmSync(temp, { recursive: true, force: true }); }
