// A bounded lexical model for change review, not a dialect AST or equivalence proof.
export type SqlToken = { text: string; kind: "word" | "quoted" | "literal" | "symbol" | "hint"; start: number; end: number; depth: number };
export type SqlSpan = { start: number; end: number; line: number; column: number; text: string };
export type ScopedSource = { table: string; alias: string; ordinal: number; token: number; aliasToken?: number; child?: string; span: SqlSpan };
export type ScopedExpression = { name: string; key: string; span: SqlSpan; block: string; context: string; contextKey: string; kind: string; startToken: number; endToken: number };
export type QueryBlock = { id: string; parent?: string; depth: number; startToken: number; endToken: number; span: SqlSpan; sources: ScopedSource[]; context: string; contextKey: string };
export type ScopedRelation = { kind: "explicit_join" | "same_block_condition" | "correlation" | "in" | "exists" | "unknown"; block: string; targetBlock?: string; left: string; right: string; key: string; span: SqlSpan };
export type ScopedSql = { sql: string; tokens: SqlToken[]; blocks: QueryBlock[]; outputs: ScopedExpression[]; filters: ScopedExpression[]; groups: ScopedExpression[]; aggregates: ScopedExpression[]; order: ScopedExpression[]; relations: ScopedRelation[]; structures: ScopedExpression[]; warnings: string[]; canonical: string; partial: boolean };

const upper = (token?: SqlToken) => token?.kind === "word" ? token.text.toUpperCase() : token?.text;
const id = (token?: SqlToken) => token?.kind === "word" || token?.kind === "quoted";
const norm = (token: SqlToken) => token.kind === "word" ? token.text.toUpperCase() : token.text;
const stop = new Set(["WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "OFFSET", "FETCH", "UNION", "EXCEPT", "INTERSECT", "RETURNING", "QUALIFY", "WINDOW", "FOR"]);
const reserved = new Set([...stop, "JOIN", "LEFT", "RIGHT", "FULL", "INNER", "OUTER", "CROSS", "ON", "USING", "AS", "SET", "FROM", "AND", "OR"]);

export function tokenizeSql(sql: string): { tokens: SqlToken[]; warnings: string[] } {
  const tokens: SqlToken[] = [], warnings: string[] = [];
  let depth = 0;
  for (let i = 0; i < sql.length;) {
    if (/\s/.test(sql[i])) { i++; continue; }
    const start = i;
    if (sql.startsWith("--", i)) {
      const end = sql.indexOf("\n", i); i = end < 0 ? sql.length : end;
      if (sql[start + 2] === "+") tokens.push({ text: sql.slice(start, i), kind: "hint", start, end: i, depth });
      continue;
    }
    if (sql.startsWith("/*", i)) {
      let count = 1; i += 2;
      while (i < sql.length && count) {
        if (sql.startsWith("/*", i)) { count++; i += 2; }
        else if (sql.startsWith("*/", i)) { count--; i += 2; }
        else i++;
      }
      if (count) warnings.push("닫히지 않은 주석");
      if (sql[start + 2] === "+" || sql[start + 2] === "!") tokens.push({ text: sql.slice(start, i), kind: "hint", start, end: i, depth });
      continue;
    }
    const dollar = sql.slice(i).match(/^\$(?:[A-Za-z_]\w*)?\$/)?.[0];
    if (dollar) {
      const end = sql.indexOf(dollar, i + dollar.length);
      i = end < 0 ? sql.length : end + dollar.length;
      if (end < 0) warnings.push("닫히지 않은 dollar 문자열");
      tokens.push({ text: sql.slice(start, i), kind: "literal", start, end: i, depth }); continue;
    }
    if ("'\"`[".includes(sql[i])) {
      const quote = sql[i] === "[" ? "]" : sql[i]; let closed = false; i++;
      while (i < sql.length) {
        if (sql[i] === "\\") { warnings.push("백슬래시 이스케이프의 방언 의존 해석"); i += 2; continue; }
        if (sql[i] === quote) { if (sql[i + 1] === quote) { i += 2; continue; } i++; closed = true; break; } i++;
      }
      if (!closed) warnings.push("닫히지 않은 문자열 또는 인용 식별자");
      tokens.push({ text: sql.slice(start, i), kind: sql[start] === "'" ? "literal" : "quoted", start, end: i, depth }); continue;
    }
    const word = sql.slice(i).match(/^[A-Za-z_][\w$#]*/)?.[0];
    const number = sql.slice(i).match(/^\d+(?:\.\d+)?/)?.[0];
    const text = word ?? number ?? sql.slice(i).match(/^(?:>=|<=|<>|!=|\|\||::)/)?.[0] ?? sql[i];
    if (text === ")") depth--;
    tokens.push({ text, kind: word ? "word" : number ? "literal" : "symbol", start, end: i + text.length, depth });
    if (text === "(") depth++;
    if (depth < 0) warnings.push("괄호 범위 불일치");
    i += text.length;
  }
  if (depth !== 0) warnings.push("괄호 범위 불일치");
  return { tokens, warnings: [...new Set(warnings)] };
}

export function analyzeChangeScopes(sql: string): ScopedSql {
  const { tokens: t, warnings } = tokenizeSql(sql);
  const span = (a: number, b: number): SqlSpan => {
    const start = t[a]?.start ?? 0, end = t[b - 1]?.end ?? start;
    const prefix = sql.slice(0, start);
    return { start, end, line: prefix.split("\n").length, column: start - prefix.lastIndexOf("\n"), text: sql.slice(start, end) };
  };
  const close = new Map<number, number>(), stack: number[] = [];
  t.forEach((token, i) => { if (token.text === "(") stack.push(i); if (token.text === ")") { const open = stack.pop(); if (open !== undefined) close.set(open, i); } });
  const blocks: QueryBlock[] = [];
  t.forEach((token, i) => {
    if (upper(token) !== "SELECT") return;
    let end = i + 1;
    while (end < t.length && t[end].depth >= token.depth && !(t[end].depth === token.depth && ["UNION", "EXCEPT", "INTERSECT", ";"].includes(upper(t[end]) ?? ""))) end++;
    blocks.push({ id: "", depth: token.depth, startToken: i, endToken: end, span: span(i, end), sources: [], context: "", contextKey: "" });
  });
  const mainSelect = blocks.find(b => b.depth === Math.min(...blocks.map(q => q.depth)));
  if (!mainSelect || !["SELECT", "WITH"].includes(upper(t[0]) ?? "")) {
    blocks.unshift({ id: "", depth: 0, startToken: 0, endToken: t.length, span: span(0, t.length), sources: [], context: "", contextKey: "" });
  } else if (blocks[0] !== mainSelect) { blocks.splice(blocks.indexOf(mainSelect), 1); blocks.unshift(mainSelect); }
  blocks.forEach((b, i) => { b.id = `q${i}`; });
  blocks.forEach(b => {
    const parent = blocks.filter(p => p !== b && p.startToken < b.startToken && p.endToken >= b.endToken).sort((a, z) => z.depth - a.depth)[0];
    b.parent = parent?.id;
  });
  const root = blocks[0];
  const owner = (i: number) => blocks.filter(b => b.startToken <= i && b.endToken > i).sort((a, b) => b.depth - a.depth)[0] ?? root;
  const blockById = (name?: string) => blocks.find(b => b.id === name);
  const readSource = (b: QueryBlock, index: number) => {
    let i = index; const start = i;
    let table = "", child: QueryBlock | undefined;
    if (t[i]?.text === "(") {
      const end = close.get(i); if (end === undefined) return;
      child = blocks.find(q => q.startToken > i && q.endToken <= end && q.parent === b.id);
      table = "<inline-view>"; i = end + 1;
      if (!child) warnings.push(`${b.id}: FROM 괄호 구문을 인라인 뷰로 확정하지 못함`);
    } else if (id(t[i])) {
      table = t[i++].text;
      while (t[i]?.text === "." && id(t[i + 1])) { table += "." + t[i + 1].text; i += 2; }
      if (t[i]?.text === "(") warnings.push(`${b.id}: 테이블 함수/특수 FROM 구문은 부분 분석`);
    } else return;
    if (upper(t[i]) === "AS") i++;
    const aliasToken = id(t[i]) && !reserved.has(upper(t[i]) ?? "") ? i : undefined;
    const alias = aliasToken === undefined ? table : t[aliasToken].text;
    if (b.sources.some(s => s.alias.toUpperCase() === alias.toUpperCase())) warnings.push(`${b.id}: 중복 별칭 ${alias}`);
    b.sources.push({ table, alias, aliasToken, token: start, child: child?.id, ordinal: b.sources.length, span: span(start, aliasToken === undefined ? i : i + 1) });
  };
  for (const b of blocks) {
    let inFrom = false;
    for (let i = b.startToken; i < b.endToken; i++) {
      if (t[i].depth !== b.depth) continue;
      const word = upper(t[i]);
      if (stop.has(word ?? "")) inFrom = false;
      if (word === "SET") inFrom = false;
      if (["FROM", "JOIN", "UPDATE", "INTO"].includes(word ?? "") || (inFrom && t[i].text === ",")) { readSource(b, i + 1); inFrom = word !== "UPDATE"; }
    }
  }
  const resolve = (b: QueryBlock, qualifier: string): { block: QueryBlock; source: ScopedSource } | undefined => {
    let current: QueryBlock | undefined = b;
    while (current) {
      const source = current.sources.find(s => s.alias.toUpperCase() === qualifier.toUpperCase() || s.table.toUpperCase() === qualifier.toUpperCase());
      if (source) return { block: current, source };
      current = blockById(current.parent);
    }
    return undefined;
  };
  const sourceKey = (source: ScopedSource) => `${source.table.toUpperCase()}#${source.ordinal}`;
  const canonical = (a: number, z: number) => {
    const result: string[] = [];
    for (let i = a; i < z; i++) {
      const token = t[i], b = owner(i);
      if (token.text === ";" && i === z - 1) continue;
      const declared = b.sources.find(s => s.aliasToken === i);
      if (declared && token.kind === "word") { result.push(`@${sourceKey(declared)}`); continue; }
      if (token.kind === "word" && t[i + 1]?.text === ".") {
        const ref = resolve(b, token.text);
        if (ref) { result.push(`@${sourceKey(ref.source)}${ref.block === b ? "" : `^${b.depth - ref.block.depth}`}`); continue; }
      }
      if (upper(token) === "AS" && b.sources.some(s => s.aliasToken === i + 1)) continue;
      result.push(norm(token));
    }
    return result.join(" ");
  };
  const clauseRange = (b: QueryBlock, word: string): [number, number] | undefined => {
    const start = t.findIndex((token, i) => i >= b.startToken && i < b.endToken && token.depth === b.depth && upper(token) === word);
    if (start < 0) return;
    let end = start + 1;
    while (end < b.endToken && !(t[end].depth === b.depth && (stop.has(upper(t[end]) ?? "") || t[end].text === ";"))) end++;
    return [start + (["GROUP", "ORDER"].includes(word) && upper(t[start + 1]) === "BY" ? 2 : 1), end];
  };
  const split = (a: number, z: number, delimiter: string, depth: number): [number, number][] => {
    const ranges: [number, number][] = []; let start = a, cases = 0, between = false;
    for (let i = a; i < z; i++) {
      if (t[i].depth !== depth) continue;
      if (upper(t[i]) === "CASE") cases++;
      if (upper(t[i]) === "END") cases--;
      if (upper(t[i]) === "BETWEEN") between = true;
      if (upper(t[i]) === delimiter && !cases) { if (between && delimiter === "AND") { between = false; continue; } ranges.push([start, i]); start = i + 1; }
    }
    if (start < z) ranges.push([start, z]); return ranges;
  };
  const projections: ScopedExpression[] = [], filters: ScopedExpression[] = [], groups: ScopedExpression[] = [], order: ScopedExpression[] = [];
  const expr = (b: QueryBlock, a: number, z: number, kind: string, name = ""): ScopedExpression => ({ name, key: canonical(a, z), span: span(a, z), block: b.id, context: "", contextKey: "", kind, startToken: a, endToken: z });
  for (const b of blocks) {
    if (upper(t[b.startToken]) === "SELECT") {
      let end = b.startToken + 1;
      while (end < b.endToken && !(t[end].depth === b.depth && ["FROM", ...stop, ";"].includes(upper(t[end]) ?? ""))) end++;
      for (const [a, z] of split(b.startToken + 1, end, ",", b.depth)) {
        let aliasIndex = -1;
        for (let i = a; i < z; i++) if (t[i].depth === b.depth && upper(t[i]) === "AS") aliasIndex = i + 1;
        let expressionEnd = aliasIndex < 0 ? z : aliasIndex - 1;
        if (aliasIndex < 0 && z - a > 1 && id(t[z - 1]) && t[z - 2]?.text !== "." && [")", "END"].includes(upper(t[z - 2]) ?? "")) { aliasIndex = z - 1; expressionEnd = z - 1; }
        const name = aliasIndex >= 0 ? t[aliasIndex]?.text : (id(t[z - 1]) ? t[z - 1].text : `column_${projections.filter(p => p.block === b.id).length + 1}`);
        projections.push(expr(b, a, expressionEnd, "projection", name));
      }
    }
    for (const clause of ["WHERE", "HAVING", "GROUP", "ORDER"]) {
      const range = clauseRange(b, clause); if (!range) continue;
      const collection = clause === "GROUP" ? groups : clause === "ORDER" ? order : filters;
      const hasOr = t.slice(...range).some(token => token.depth === b.depth && upper(token) === "OR");
      const ranges = hasOr && clause === "WHERE" ? [range] : split(...range, ["GROUP", "ORDER"].includes(clause) ? "," : "AND", b.depth);
      ranges.forEach(([a, z], i) => collection.push(expr(b, a, z, clause, `${clause}[${i + 1}]`)));
    }
  }
  const outputs = projections.filter(p => p.block === root.id);
  const rootFilters = filters.filter(p => p.block === root.id);
  const rootOrders = order.filter(p => p.block === root.id);
  for (const b of blocks) {
    const output = outputs.find(p => p.startToken < b.startToken && p.endToken >= b.endToken);
    const filter = rootFilters.find(p => p.startToken <= b.startToken && p.endToken >= b.endToken);
    const sort = rootOrders.find(p => p.startToken <= b.startToken && p.endToken >= b.endToken);
    if (b === root) { b.context = "최상위"; b.contextKey = "root"; }
    else if (output) { b.context = `출력 ${output.name}`; b.contextKey = `output:${output.name}`; }
    else if (filter) {
      const tables = [...new Set(blocks.filter(q => q.startToken >= filter.startToken && q.endToken <= filter.endToken).flatMap(q => q.sources.map(s => s.table.toUpperCase())).filter(n => n !== "<INLINE-VIEW>"))].sort().join(",");
      b.context = `최상위 ${filter.name} (${tables})`; b.contextKey = `filter:${tables}`;
    } else if (sort) { b.context = `최상위 ${sort.name}`; b.contextKey = `sort:${sort.name}`; }
    else { b.context = "FROM/기타 내부 블록"; b.contextKey = "source"; }
  }
  for (const e of [...projections, ...filters, ...groups, ...order]) {
    const b = blockById(e.block)!; e.context = b.context;
    e.contextKey = b.contextKey;
    // Scope identity is kept separately from expression text; never merge aliases across blocks.
    e.key = `${b.contextKey}/${b === root ? "root" : b.sources.map(sourceKey).join(",")}/${e.kind}/${e.key}`;
  }
  const aggregates: ScopedExpression[] = [], structures: ScopedExpression[] = [], relations: ScopedRelation[] = [];
  for (let i = 0; i < t.length; i++) {
    const b = owner(i), word = upper(t[i]);
    if (["SUM", "COUNT", "AVG", "MIN", "MAX"].includes(word ?? "") && t[i + 1]?.text === "(") {
      const end = close.get(i + 1);
      if (end !== undefined) { const e = expr(b, i, end + 1, "aggregate", word); e.context = b.context; e.contextKey = b.contextKey; e.key = `${b.contextKey}/${b.sources.map(sourceKey).join(",")}/${e.key}`; aggregates.push(e); }
    }
    if ((word === "IN" || word === "EXISTS") && t[i + 1]?.text === "(") {
      const child = blocks.find(q => q.startToken === i + 2);
      if (child) relations.push({ kind: word.toLowerCase() as "in" | "exists", block: b.id, targetBlock: child.id, left: `${b.id}`, right: child.id, key: `${b.contextKey}/${word}/${canonical(i, child.endToken + 1)}`, span: span(i, child.endToken + 1) });
    }
    if (word === "JOIN") {
      const right = b.sources.find(s => s.token === i + 1);
      const left = right && b.sources[right.ordinal - 1];
      if (left && right) { const type = ["LEFT", "RIGHT", "FULL", "INNER", "CROSS"].includes(upper(t[i - 1]) ?? "") ? upper(t[i - 1]) : upper(t[i - 1]) === "OUTER" ? upper(t[i - 2]) : "INNER";
        relations.push({ kind: "explicit_join", block: b.id, left: `${left.table} ${left.alias}@${b.id}`, right: `${right.table} ${right.alias}@${b.id}`, key: `${b.contextKey}/${sourceKey(left)}:${type}:${sourceKey(right)}`, span: span(Math.max(b.startToken, i - 1), right.aliasToken === undefined ? i + 2 : right.aliasToken + 1) }); }
    }
    if (id(t[i]) && t[i + 1]?.text === "." && id(t[i + 2]) && t[i + 3]?.text === "=" && id(t[i + 4]) && t[i + 5]?.text === "." && id(t[i + 6])) {
      const left = resolve(b, t[i].text), right = resolve(b, t[i + 4].text);
      const kind = !left || !right ? "unknown" : left.block !== right.block ? "correlation" : left.source !== right.source ? "same_block_condition" : undefined;
      if (kind) relations.push({ kind, block: b.id, targetBlock: right?.block.id, left: `${t[i].text}.${t[i + 2].text} [${left?.source.table ?? "?"}@${left?.block.id ?? "?"}]`, right: `${t[i + 4].text}.${t[i + 6].text} [${right?.source.table ?? "?"}@${right?.block.id ?? "?"}]`, key: `${b.contextKey}/${kind}/${canonical(i, i + 7)}`, span: span(i, i + 7) });
    }
  }
  for (const b of blocks) for (const source of b.sources.filter(s => s.child)) {
    const e = expr(b, source.token, (source.aliasToken ?? source.token) + 1, "derived_table", source.alias);
    e.context = b === root ? "최상위 FROM" : b.context;
    e.contextKey = b.contextKey;
    e.key = `${b.contextKey}/derived/${canonical(source.token, (source.aliasToken ?? source.token) + 1)}`; structures.push(e);
  }
  for (const b of blocks) {
    const peers = blocks.filter(q => q.contextKey === b.contextKey && q.sources.map(sourceKey).join() === b.sources.map(sourceKey).join());
    if (peers.length > 1) warnings.push(`${b.context}: 동일 소스의 여러 블록은 위치 순서로 구분하며 이동 후 대응은 보류`);
    const identity = b === root ? "root" : `${b.contextKey}/${b.sources.map(sourceKey).join()}/instance:${peers.indexOf(b)}`;
    for (const e of [...filters, ...groups, ...aggregates, ...order, ...structures].filter(e => e.block === b.id)) e.key = `${identity}/${e.key}`;
    for (const r of relations.filter(r => r.block === b.id)) r.key = `${identity}/${r.key}`;
  }
  if (t.some(token => token.kind === "hint")) warnings.push("힌트는 보존하며 방언별 효과를 판단하지 않음");
  if (t.some(token => ["WITH", "UNION", "INTERSECT", "EXCEPT", "PIVOT", "UNPIVOT", "LATERAL", "APPLY", "QUALIFY", "CONNECT", "MODEL", "OVER", "JSON_TABLE"].includes(upper(token) ?? ""))) warnings.push("CTE/집합/윈도우/방언 특수 구문은 부분 분석이며 동등성 판단 보류");
  if (t.some(token => token.text === ";" && token !== t[t.length - 1])) warnings.push("여러 문장의 범위 비교는 지원하지 않음");
  if (Math.max(...blocks.map(b => b.depth)) > 4) warnings.push("깊은 중첩: 블록 대응과 결과 동등성은 판단 보류");
  if (relations.some(r => r.kind === "unknown")) warnings.push("일부 관계의 참조 대상을 해석하지 못함");
  if (blocks.some(b => b !== root && !b.parent)) warnings.push("최상위와 연결되지 않은 쿼리 블록은 부분 분석");
  if (!t.some(token => ["SELECT", "UPDATE", "DELETE", "INSERT", "MERGE"].includes(upper(token) ?? ""))) warnings.push("미지원 명령: 쿼리 범위를 확정하지 못함");
  return { sql, tokens: t, blocks, outputs, filters, groups, aggregates, order, relations, structures, warnings: [...new Set(warnings)], canonical: canonical(0, t.length), partial: warnings.length > 0 };
}

export const spanLabel = (span: SqlSpan) => `L${span.line}:${span.column} [${span.start},${span.end})`;
export const briefSql = (sql: string, max = 160) => { const value = sql.replace(/\s+/g, " ").trim(); return value.length > max ? value.slice(0, max) + "… (상세 원문 참조)" : value; };
