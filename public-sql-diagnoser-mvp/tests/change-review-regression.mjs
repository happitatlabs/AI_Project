import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sql-change-regression-'));
try {
  for (const name of fs.readdirSync('src').filter(name => name.endsWith('.ts'))) {
    const compiled = ts.transpileModule(fs.readFileSync(path.join('src', name), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2022 },
    });
    fs.writeFileSync(path.join(dir, name.replace(/\.ts$/, '.js')), compiled.outputText);
  }
  fs.writeFileSync(path.join(dir, 'package.json'), '{"type":"module"}');
  const { buildSqlChangeReview, buildSqlChangeReviewMarkdown, buildSqlChangeReviewTechnicalMarkdown, buildSqlChangeReportItems } = await import(pathToFileURL(path.join(dir, 'sqlChangeReview.js')));
  const a = fs.readFileSync('tests/fixtures/change-review/original.sql', 'utf8');
  const b = fs.readFileSync('tests/fixtures/change-review/dirty.sql', 'utf8');
  const review = buildSqlChangeReview(b, a);
  const { analyzeChangeScopes } = await import(pathToFileURL(path.join(dir, 'sqlChangeScope.js')));
  const group = (r, name) => r.changeGroups.find(g => g.id === name);
  const changed = (r, name) => group(r, name).added.length + group(r, name).removed.length;
  const unchangedPairs = [
    ["SELECT c.id FROM customers c WHERE c.status='A';", "SELECT u.id\nFROM customers AS u /* ordinary */ WHERE u.status = 'A';"],
    ["SELECT c.id FROM customers c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id=c.id);", "SELECT x.id FROM customers x WHERE EXISTS (SELECT 1 FROM orders z WHERE z.customer_id=x.id);"],
    ["SELECT '/*text*/ -- string' AS v FROM t;", "SELECT  '/*text*/ -- string' AS v FROM t; -- comment"],
  ];
  for (const [old, next] of unchangedPairs) assert.equal(buildSqlChangeReview(old, next).changeCount, 0, old);
  for (const [old, next] of [
    ["SELECT 'a b' AS v FROM t;", "SELECT 'a  b' AS v FROM t;"],
    ['SELECT "Case" FROM t;', 'SELECT "case" FROM t;'],
    ["SELECT /*+ INDEX(t ix1) */ id FROM t;", "SELECT /*+ INDEX(t ix2) */ id FROM t;"],
  ]) assert.ok(buildSqlChangeReview(old, next).changeCount > 0);
  const scoped = analyzeChangeScopes("SELECT x.id FROM customers x WHERE EXISTS (SELECT 1 FROM orders x WHERE x.customer_id=1) AND x.id=2;");
  assert.ok(scoped.filters.find(f => f.span.text === 'x.customer_id=1').key.includes('ORDERS'));
  assert.ok(scoped.filters.find(f => f.span.text === 'x.id=2').key.includes('CUSTOMERS'));
  const selfJoin = analyzeChangeScopes('SELECT a.id FROM customers a JOIN customers b ON a.parent_id=b.id;');
  assert.ok(selfJoin.relations.some(r => r.kind === 'explicit_join' && r.left.includes('a@') && r.right.includes('b@')));
  const correlation = analyzeChangeScopes('SELECT p.id FROM products p WHERE EXISTS (SELECT 1 FROM products q WHERE q.id=p.id);');
  assert.ok(correlation.relations.some(r => r.kind === 'correlation' && r.left.includes('q.id') && r.right.includes('p.id')));
  assert.ok(!correlation.relations.some(r => r.kind === 'explicit_join' || r.kind === 'same_block_condition'));
  assert.ok(correlation.relations.some(r => r.kind === 'exists'));
  const aggregateOnly = buildSqlChangeReview('SELECT SUM(o.amount) AS total FROM orders o;', 'SELECT SUM(o.amount * 2) AS total FROM orders o;');
  assert.equal(changed(aggregateOnly, 'group-by'), 0);
  assert.ok(changed(aggregateOnly, 'aggregations') > 0);
  assert.ok(aggregateOnly.keyChanges.some(f => f.label === '집계 계산식 변경'));
  assert.equal(analyzeChangeScopes('SELECT CASE WHEN 1=1 THEN SUM(o.amount) ELSE 0 END AS total FROM orders o;').aggregates[0].span.text, 'SUM(o.amount)');
  assert.equal(changed(review, 'joins'), 0);
  assert.ok(!review.nextQuestions.some(q => q.id === 'verify-join-cardinality'));
  assert.ok(review.scopes.after.structures.some(s => s.name === 'order_stats'));
  assert.ok(review.scopes.after.structures.some(s => s.name === 'region_stats'));
  assert.ok(review.scopes.before.structures.some(s => s.name === 'x' && s.context === '최상위 FROM'));
  assert.equal(review.scopes.after.groups.filter(g => g.block === 'q0').length, 0);
  assert.ok(group(review, 'group-by').removed.every(s => s.includes('customer_type')));
  assert.ok(group(review, 'outputs').removed.includes('customer_type'));
  for (const kind of ['calculation', 'aggregate-filter', 'null-handling', 'aggregate-period', 'local-filter', 'row-filter', 'output-removed', 'order', 'not-in-null']) assert.ok(review.impacts.some(i => i.kind === kind), kind);
  const localStatus = review.impacts.find(i => i.kind === 'local-filter' && i.facts.table === 'orders' && i.facts.column === 'status');
  assert.equal(localStatus.facts.added, true);
  assert.equal(localStatus.facts.counterpartCount, 1);
  assert.ok(localStatus.evidence.some(e => e.includes('orders d2')));
  assert.ok(localStatus.evidence.some(e => e.includes("o7.status = 'COMPLETED'")));
  assert.deepEqual(review.impacts.find(i => i.kind === 'not-in-null').facts, { beforeExplicitNullRejection: true, afterExplicitNullRejection: false });
  const reverse = buildSqlChangeReview(a, b);
  for (const g of review.changeGroups) {
    assert.deepEqual([...g.removed].sort(), [...group(reverse, g.id).added].sort(), g.id);
    assert.deepEqual([...g.added].sort(), [...group(reverse, g.id).removed].sort(), g.id);
  }
  assert.equal(review.analysisStatus, 'partial');
  const report = buildSqlChangeReviewMarkdown(review);
  const items = buildSqlChangeReportItems(review);
  assert.ok(report.length < 16000, 'user report must not be a raw SQL inventory');
  assert.ok(!report.includes('```sql'));
  assert.ok(!report.includes('상세 추가·제거 근거'));
  assert.match(report, /부분 분석/);
  assert.match(report, /MAX\(oi2.unit_price\)/);
  assert.match(report, /SUM\(oi.quantity \* oi.unit_price\)/);
  for (const item of items) {
    assert.ok(report.includes(item.observation));
    assert.ok(report.includes(item.consequence));
  }
  for (const kind of ['calculation', 'null-handling', 'aggregate-period', 'aggregate-filter', 'local-filter', 'row-filter', 'output-removed', 'order', 'not-in-null']) {
    assert.ok(items.some(i => i.id.startsWith(kind + '-')), `user report must include ${kind}`);
  }
  assert.ok(buildSqlChangeReviewTechnicalMarkdown(review).includes(b));
  assert.ok(buildSqlChangeReviewTechnicalMarkdown(review).includes(a));
  assert.ok(buildSqlChangeReviewMarkdown(review, [review.checklist[0].id]).includes(`- [x] ${review.checklist[0].label}`));
  assert.ok(buildSqlChangeReviewMarkdown(review).includes(`- [ ] ${review.checklist[0].label}`));
  assert.ok(review.keyChanges.some(k => k.id === 'partial-analysis'));
  assert.ok(review.keyChanges.every(k => k.evidence.every(e => e.length <= 180)));
  assert.match(review.direction, /인라인 뷰 x → customers c/);
  assert.equal(review.counts.evidenceEntries, review.changeGroups.reduce((n, g) => n + g.added.length + g.removed.length, 0));
  assert.equal(buildSqlChangeReview('EXEC dynamic_sql;', 'EXEC dynamic_sql;').analysisStatus, 'partial');
  const deep = 'SELECT ' + '(SELECT '.repeat(10) + '1' + ')'.repeat(10) + ' AS nested;';
  assert.equal(buildSqlChangeReview(deep, deep).analysisStatus, 'partial');

  // Isolate each output or outer predicate without changing its internal expression.
  const isolated = {};
  for (const name of ['total_sales', 'last_order_date', 'successful_payment_amount']) {
    const old = review.scopes.before.outputs.find(p => p.name === name), next = review.scopes.after.outputs.find(p => p.name === name);
    const beforeQuery = `SELECT ${old.span.text} AS ${name} FROM customers x;`;
    const afterQuery = `SELECT ${next.span.text} AS ${name} FROM customers c;`;
    const isolatedReview = buildSqlChangeReview(beforeQuery, afterQuery);
    assert.ok(isolatedReview.impacts.some(i => i.label.startsWith(name)));
    isolated[name] = { before: beforeQuery, after: afterQuery };
  }
  for (const [name, test] of [
    ['expensive_purchase', f => f.span.text.includes('products') && f.span.text.trim().startsWith('EXISTS')],
    ['refund_null', f => f.span.text.includes('NOT IN')],
    ['additional_filter', f => f.span.text.includes('payments') && f.span.text.includes('OR')],
  ]) {
    const old = review.scopes.before.filters.find(f => f.block === 'q0' && test(f));
    const next = review.scopes.after.filters.find(f => f.block === 'q0' && test(f));
    assert.ok(old, name);
    isolated[name] = { before: `SELECT x.customer_id FROM customers x WHERE ${old.span.text};`, after: `SELECT c.customer_id FROM customers c${next ? ' WHERE ' + next.span.text : ''};` };
    const isolatedReview = buildSqlChangeReview(isolated[name].before, isolated[name].after);
    assert.ok(changed(isolatedReview, 'filters') > 0, name);
  }
  assert.ok(changed(buildSqlChangeReview('SELECT id, status AS customer_type FROM customers;', 'SELECT id FROM customers;'), 'outputs') > 0);
  const addedJoin = buildSqlChangeReview('SELECT o.id, SUM(o.amount) FROM orders o GROUP BY o.id;', 'SELECT o.id, SUM(o.amount) FROM orders o JOIN payments p ON p.order_id=o.id GROUP BY o.id;');
  assert.equal(changed(addedJoin, 'group-by'), 0, 'adding a source must not change unchanged root GROUP BY');
  const orderOnly = buildSqlChangeReview('SELECT id, amount FROM orders ORDER BY amount * 2 DESC, id;', 'SELECT id, amount FROM orders ORDER BY amount DESC;');
  assert.equal(orderOnly.impacts.filter(i => i.kind === 'order').length, 2);
  if (process.argv.includes('--report')) {
    fs.mkdirSync('reports/change-review', { recursive: true });
    fs.writeFileSync('reports/change-review/corrected-b-to-a.md', buildSqlChangeReviewMarkdown(review));
    fs.writeFileSync('reports/change-review/technical-b-to-a.md', buildSqlChangeReviewTechnicalMarkdown(review));
    const uiReview = buildSqlChangeReview(b.replace(/\r\n/g, '\n'), a.replace(/\r\n/g, '\n'));
    assert.deepEqual(uiReview.counts, review.counts);
    fs.writeFileSync('reports/change-review/corrected-ui-b-to-a.md', buildSqlChangeReviewMarkdown(uiReview));
    fs.writeFileSync('reports/change-review/corrected-b-to-a.json', JSON.stringify(review, null, 2));
    fs.writeFileSync('reports/change-review/isolated-sql.json', JSON.stringify(isolated, null, 2));
    console.log(JSON.stringify({ counts: review.counts, impacts: review.impacts.map(i => [i.kind, i.label]), joins: review.scopes.before.relations.filter(r => r.kind === 'explicit_join' || r.kind === 'same_block_condition'), groupBy: review.changeGroups.find(g => g.id === 'group-by'), direction: review.direction }, null, 2));
  }
  assert.equal(buildSqlChangeReview(a, a).changeCount, 0);
  if (process.argv.includes('--capture-baseline')) {
    fs.mkdirSync('reports/change-review', { recursive: true });
    fs.writeFileSync('reports/change-review/baseline-b-to-a.md', buildSqlChangeReviewMarkdown(review));
    fs.writeFileSync('reports/change-review/baseline-b-to-a.json', JSON.stringify({
      changeCount: review.changeCount, groups: review.changeGroups,
      keyChanges: review.keyChanges, beforeJoins: review.beforeAnalysis.joins,
    }, null, 2));
    console.log(JSON.stringify({ count: review.changeCount, groups: review.changeGroups.map(g => [g.id, g.removed.length, g.added.length]) }));
  }
  console.log('change review reproduction passed');
} finally { fs.rmSync(dir, { recursive: true, force: true }); }
