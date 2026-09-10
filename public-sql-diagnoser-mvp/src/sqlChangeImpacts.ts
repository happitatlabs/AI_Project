import { type ScopedSql, type ScopedExpression, type SqlSpan, spanLabel, briefSql } from "./sqlChangeScope.js";

export type ChangeImpact = { id: string; kind: string; label: string; statement: string; condition: string; evidence: string[]; assessment: "observed-risk" | "unresolved"; facts?: Record<string, string | number | boolean> };
const inside = (outer: SqlSpan, inner: SqlSpan) => inner.start >= outer.start && inner.end <= outer.end;
const evidence = (side: string, item?: { span: SqlSpan; block?: string }) => item ? `${side} ${item.block ?? ""} ${spanLabel(item.span)}: ${item.span.text}` : `${side}: 대응 항목 없음`;
const hasWord = (sql: ScopedSql, item: ScopedExpression, word: string) => sql.tokens.slice(item.startToken, item.endToken).some(t => t.kind === "word" && t.text.toUpperCase() === word);
const members = (sql: ScopedSql, item: ScopedExpression) => sql.relations.filter(r => ["in", "exists"].includes(r.kind) && inside(item.span, r.span)
  && sql.blocks.some(b => inside(r.span, b.span) && b.sources.some(s => !s.child && s.table !== "<inline-view>")));

export function buildChangeImpacts(before: ScopedSql, after: ScopedSql): ChangeImpact[] {
  if (before.canonical === after.canonical) return [];
  const changes: ChangeImpact[] = [];
  const add = (kind: string, label: string, statement: string, condition: string, items: string[], assessment: ChangeImpact["assessment"] = "observed-risk") => changes.push({ id: `${kind}-${changes.length}`, kind, label, statement, condition, evidence: items, assessment });
  for (const old of before.outputs) {
    const current = after.outputs.find(p => p.name === old.name);
    if (!current) { add("output-removed", "출력 컬럼 제거", `${old.name} 출력 컬럼이 제거되었습니다.`, "이 컬럼을 사용하는 화면·내보내기·후속 SQL의 입력 스키마가 달라집니다.", [evidence("변경 전", old)]); continue; }
    if (current.key === old.key) continue;
    const oldAggregates = before.aggregates.filter(a => inside(old.span, a.span));
    const newAggregates = after.aggregates.filter(a => inside(current.span, a.span));
    const oldMax = oldAggregates.find(a => a.name === "MAX"), newMax = newAggregates.find(a => a.name === "MAX");
    if ((oldMax || newMax) && Boolean(oldMax) !== Boolean(newMax) && (hasWord(before, old, "SUM") || hasWord(after, current, "SUM"))
      && (before.tokens.slice(old.startToken, old.endToken).some(t => t.text === "*") || after.tokens.slice(current.startToken, current.endToken).some(t => t.text === "*"))) {
      const direct = (oldMax ? newAggregates : oldAggregates).filter(a => a.name === "SUM").sort((a, b) => a.span.text.length - b.span.text.length)[0];
      const beforeFormula = oldMax?.span.text ?? direct?.span.text ?? old.span.text;
      const afterFormula = newMax?.span.text ?? direct?.span.text ?? current.span.text;
      add("calculation", `${old.name}: 계산식 변경`, `변경 전 ${briefSql(beforeFormula, 110)} → 변경 후 ${briefSql(afterFormula, 110)}. 곱셈을 포함하는 집계식의 MAX 사용 여부가 달라졌습니다.`, "MAX가 곱셈 입력을 대체하는 구조라면, 그 그룹 안에 서로 다른 값이 있고 곱하는 수량이 0이 아닐 때 합계가 달라질 수 있습니다. 실제 피연산자·그룹 키와 데이터 확인이 필요합니다.", [evidence("변경 전", oldMax ?? old), evidence("변경 후", newMax ?? current)]);
    } else if (oldAggregates.length || newAggregates.length) {
      add("calculation", `${old.name}: 집계 표현식 변경`, "출력 계산의 집계/중첩 표현식이 변경되었습니다. 집계 단위가 바뀌었다고 단정하지 않습니다.", "일부는 표현 정리일 수 있습니다. 필터·NULL 처리·집계 입력을 함께 확인해야 결과 차이를 판단할 수 있습니다.", [evidence("변경 전", old), evidence("변경 후", current)], "unresolved");
    } else {
      add("expression", `${old.name}: 출력 표현식 변경`, "출력에 사용하는 표현식 또는 참조 경로가 변경되었습니다.", "인라인 뷰의 투영·필터를 포함한 참조 대응이 필요하며 결과 동등성은 보류합니다.", [evidence("변경 전", old), evidence("변경 후", current)], "unresolved");
    }
    if (hasWord(before, old, "COALESCE") !== hasWord(after, current, "COALESCE")) {
      add("null-handling", `${old.name}: NULL 대체 처리`, `COALESCE가 ${hasWord(before, old, "COALESCE") ? "제거" : "추가"}되었습니다.`, "집계 입력이 없거나 전부 NULL이면 SUM은 NULL이 될 수 있습니다. 대체값이 0인 쪽과 NULL인 쪽을 구분해야 합니다.", [evidence("변경 전", old), evidence("변경 후", current)]);
    }
    const oldMembership = members(before, old), newMembership = members(after, current);
    if (oldMembership.length !== newMembership.length) {
      const describe = (sql: ScopedSql, relations: typeof oldMembership) => relations.map(r => {
        const block = sql.blocks.find(b => b.id === r.targetBlock);
        return `${r.kind.toUpperCase()} (${block?.sources.map(s => s.table).join(", ") || "하위 쿼리"})`;
      }).join(", ") || "해당 포함·존재 조건 없음";
      add("aggregate-filter", `${old.name}: 집계 대상 필터`, `변경 전 ${describe(before, oldMembership)} → 변경 후 ${describe(after, newMembership)}.`, "해당 하위 쿼리에 일치하는 행이 없는 대상이 새로 포함되거나 제외될 수 있습니다. 날짜 집계는 선택 날짜가, 금액·건수 집계는 입력 대상이 달라질 수 있습니다. 다른 조건이 같은 제한을 보장하는지는 별도 확인해야 합니다.", [...oldMembership.map(r => evidence("변경 전", r)), ...newMembership.map(r => evidence("변경 후", r))]);
    }
    const oldMin = oldAggregates.find(a => a.name === "MIN"), newMin = newAggregates.find(a => a.name === "MIN");
    if (oldMin && newMin) {
      const oldBlock = before.blocks.find(b => b.id === oldMin.block)!, newBlock = after.blocks.find(b => b.id === newMin.block)!;
      const oldConditions = before.filters.filter(f => f.block === oldBlock.id), newConditions = after.filters.filter(f => f.block === newBlock.id);
      if (oldConditions.map(f => f.key).join("\n") !== newConditions.map(f => f.key).join("\n")) {
        add("aggregate-period", `${old.name}: 집계 시작 경계`, "기간 경계를 구하는 MIN 하위 쿼리의 대상 조건이 변경되었습니다. NULL 대체 처리와 별도 변경입니다.", "조건에서 제외됐던 더 이른 날짜의 행이 포함되면 MIN이 앞당겨지고, 그 사이에 발생한 금액 등이 집계에 포함될 수 있습니다.", [evidence("변경 전", oldBlock), evidence("변경 후", newBlock)]);
      }
    }
  }
  for (const current of after.outputs.filter(p => !before.outputs.some(o => o.name === p.name))) add("output-added", "출력 컬럼 추가", `${current.name} 출력 컬럼이 추가되었습니다.`, "결과 스키마가 바뀝니다. 기존 위치 기반 소비자와 내보내기를 확인하세요.", [evidence("변경 후", current)]);

  // Literal predicates are compared only inside the same root predicate context and base table.
  const literalConditions = (sql: ScopedSql) => sql.filters.flatMap(f => {
    const b = sql.blocks.find(b => b.id === f.block)!;
    const tokens = sql.tokens.slice(f.startToken, f.endToken);
    if (tokens.length !== 5 || tokens[1].text !== "." || tokens[3].text !== "=" || tokens[4].kind !== "literal") return [];
    const source = b.sources.find(s => s.alias.toUpperCase() === tokens[0].text.toUpperCase());
    if (!source) return [];
    return [{ f, key: `${b.contextKey}/${source.table.toUpperCase()}/${tokens[2].text.toUpperCase()}/${tokens[4].text}`, column: tokens[2].text, table: source.table }];
  });
  const oldLiterals = literalConditions(before), newLiterals = literalConditions(after);
  for (const [side, added, own, other] of [["변경 후", true, newLiterals, oldLiterals], ["변경 전", false, oldLiterals, newLiterals]] as const) {
    for (const item of own.filter(v => !other.some(o => o.key === v.key))) {
      if (!item.f.contextKey.startsWith("filter:")) continue;
      const otherSql = added ? before : after;
      const counterparts = otherSql.blocks.filter(b => b.contextKey === item.f.contextKey && b.sources.some(s => s.table.toUpperCase() === item.table.toUpperCase()));
      add("local-filter", `${item.table}.${item.column}: 블록 내부 조건`, `${item.f.context}의 ${item.f.block}에 ${briefSql(item.f.span.text, 90)} 조건이 ${added ? "추가" : "제거"}된 것으로 관찰됩니다.`, "다른 쿼리 블록에 같은 컬럼 조건이 있어도 이 블록에 적용된 것으로 간주하지 않습니다. 해당 조건을 만족하지 않는 행에서만 관련 구매·포함 판정이 성립한다면 결과가 달라질 수 있습니다. 우회 조건의 동등성은 보류합니다.", [evidence(side, item.f)]);
      changes[changes.length - 1].facts = { table: item.table, column: item.column, added, block: item.f.block, counterpartCount: counterparts.length };
      if (counterparts.length === 1) changes[changes.length - 1].evidence.push(evidence(added ? "변경 전 대응 후보" : "변경 후 대응 후보", counterparts[0]));
    }
  }
  const rootBefore = before.filters.filter(f => f.block === before.blocks[0].id), rootAfter = after.filters.filter(f => f.block === after.blocks[0].id);
  for (const [side, own, other] of [["제거", rootBefore, rootAfter], ["추가", rootAfter, rootBefore]] as const) {
    for (const f of own.filter(f => !other.some(o => o.key === f.key))) {
      const sourceSql = side === "제거" ? before : after;
      if (hasWord(sourceSql, f, "OR") && hasWord(sourceSql, f, "EXISTS")) add("row-filter", "외부 행 선택 조건", `IN/EXISTS와 OR가 포함된 최상위 행 선택 조건이 ${side}되었습니다.`, "OR의 양쪽 조건을 모두 만족하지 않는 고객이 다른 모든 조건은 통과한다면, 이 필터 제거 시 포함될 수 있습니다. 출력 컬럼 변화와 별개입니다.", [evidence(side === "제거" ? "변경 전" : "변경 후", f)]);
    }
  }
  const notIn = (sql: ScopedSql) => sql.relations.filter(r => r.kind === "in" && sql.tokens.findIndex(t => t.start === r.span.start) > 0 && sql.tokens[sql.tokens.findIndex(t => t.start === r.span.start) - 1].text.toUpperCase() === "NOT");
  const oldNotIn = notIn(before), newNotIn = notIn(after);
  if ((oldNotIn.length || newNotIn.length) && oldNotIn.map(r => r.key).join() !== newNotIn.map(r => r.key).join()) {
    add("not-in-null", "NOT IN 내부 조건과 NULL", "NOT IN 하위 쿼리의 조건/표현식이 변경되었습니다. 내부 포함 조건이 제거되면 NULL 배제 여부도 달라질 수 있습니다.", "하위 쿼리의 반환 컬럼이 NULL 가능하고 나머지 필터를 통과한 NULL이 유입되면, 비일치 값의 NOT IN이 UNKNOWN이 되어 행이 제외될 수 있습니다. NOT EXISTS와 동등하다고 판단하지 않습니다.", [...oldNotIn.map(r => evidence("변경 전", r)), ...newNotIn.map(r => evidence("변경 후", r))]);
    const nullRejecting = (sql: ScopedSql, relations: typeof oldNotIn) => relations.some(r => {
      const b = sql.blocks.find(b => b.id === r.targetBlock); if (!b) return false;
      const p = sql.tokens.slice(b.startToken + 1, b.startToken + 4);
      if (p.length !== 3 || p[1].text !== ".") return false;
      return sql.filters.filter(f => f.block === b.id).some(f => {
        const ft = sql.tokens.slice(f.startToken, f.endToken);
        return ft.slice(0, 3).map(t => t.text.toUpperCase()).join() === p.map(t => t.text.toUpperCase()).join()
          && (ft[3]?.text.toUpperCase() === "IN" || ft.slice(3, 6).map(t => t.text.toUpperCase()).join(" ") === "IS NOT NULL");
      });
    });
    changes[changes.length - 1].facts = { beforeExplicitNullRejection: nullRejecting(before, oldNotIn), afterExplicitNullRejection: nullRejecting(after, newNotIn) };
  }
  const oldOrder = before.order.filter(o => o.block === before.blocks[0].id), newOrder = after.order.filter(o => o.block === after.blocks[0].id);
  for (let i = 0; i < Math.max(oldOrder.length, newOrder.length); i++) {
    if (oldOrder[i]?.key === newOrder[i]?.key) continue;
    add("order", i === 0 ? "주 정렬 표현식" : "보조 정렬", `${i + 1}번째 정렬 기준이 ${!newOrder[i] ? "제거" : !oldOrder[i] ? "추가" : "변경"}되었습니다.`, i === 0 ? "표현식 차이는 확인되지만 정렬 결과 차이는 계산된 키 값·NULL 정렬 정책·DBMS에 따라 달라집니다." : "주 정렬 키가 같은 행이 있으면 보조 키 제거/추가가 동률 순서에 영향을 줄 수 있습니다.", [evidence("변경 전", oldOrder[i]), evidence("변경 후", newOrder[i])] );
  }
  return changes;
}
