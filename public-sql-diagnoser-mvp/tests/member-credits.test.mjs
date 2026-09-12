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
  const { default: worker } = await import(pathToFileURL(path.join(temp, 'src/cloudflareWorker.js')));
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
  assert.equal((await runtime(cookie)).credits.remaining, 1);
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
    assert.equal((await runtime(cookie)).credits.remaining, 1, 'invalid input must release reservation');
  }
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ output_text: JSON.stringify({ sql: 'SELECT id FROM users;', summary: 'test recommendation', warnings: [] }) }); };
  const id = crypto.randomUUID();
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie, { 'X-Request-Id': id })).status, 200);
  assert.equal((await runtime(cookie)).credits.remaining, 0);
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie, { 'X-Request-Id': id })).status, 409);
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, cookie)).status, 402);
  assert.equal(calls, 1);
  const record = records.get(identity.id); record.object = new MemberAccount({ storage: record.storage });
  assert.equal((await runtime(cookie)).credits.remaining, 0, 'no daily/session/restart trial refill');
  const concurrent = await Promise.all(Array.from({ length: 8 }, () => memberRequest(namespace, 'concurrent-member', '/reserve', { id: crypto.randomUUID() })));
  assert.equal(concurrent.filter(r => r.status === 200).length, 1);
  assert.equal(concurrent.filter(r => r.status === 402).length, 7);
  const reservationId = crypto.randomUUID();
  await memberRequest(namespace, 'refund-member', '/reserve', { id: reservationId });
  await memberRequest(namespace, 'refund-member', '/release', { id: reservationId });
  await memberRequest(namespace, 'refund-member', '/release', { id: reservationId });
  assert.equal((await (await memberRequest(namespace, 'refund-member', '/balance')).json()).remaining, 1);
  assert.equal((await memberRequest(namespace, 'refund-member', '/complete', { id: reservationId })).status, 409, 'cancelled result cannot be completed/delivered for free');
  const trial = await memberCookie({ id: 'failure-member', username: 'failure-user', unlimited: false }, env.DEMO_SESSION_SECRET);
  globalThis.fetch = async () => { throw new Error('synthetic provider failure'); };
  assert.equal((await call('/api/ai-sql-rewrite', { sql: 'SELECT id FROM users;' }, trial)).status, 502);
  assert.equal((await runtime(trial)).credits.remaining, 1);

  const adminLogin = await call('/api/auth/login', { username: env.DEMO_USERNAME, password: env.DEMO_PASSWORD });
  const adminCookie = adminLogin.headers.get('set-cookie').split(';')[0];
  assert.equal((await runtime(adminCookie)).credits.unlimited, true);
  const fakeEmail = await memberCookie({ id: 'local:fake', username: env.DEMO_USERNAME, unlimited: false }, env.DEMO_SESSION_SECRET);
  assert.equal((await runtime(fakeEmail)).credits.unlimited, false, 'display email cannot grant unlimited');
  assert.equal((await call('/api/credits/grant', { amount: 999 }, cookie)).status, 503);
  assert.equal((await call('/api/payments/confirm', { amount: 999 }, cookie)).status, 503);
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
  assert.equal((await readMember(req('/', undefined, socialCookies), env)).id, 'google:' + await digest('subject-1'));
  console.log('member credits: public access, signup/auth, trial once, concurrent reserve, idempotency, failure refund, unlimited authorization, disabled payments and OAuth state tests passed');
} finally { globalThis.fetch = originalFetch; databases.forEach(db => db.close()); fs.rmSync(temp, { recursive: true, force: true }); }
