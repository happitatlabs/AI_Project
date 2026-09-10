import { analyzeMultipleSql } from "./multiSqlAnalysis.js";
import { analyzeSqlRisks, type SqlRiskFinding } from "./riskDetector.js";
import { analyzeSql, inspectCommandScope, type SqlAnalysisResult } from "./sqlExplainer.js";
import { analyzeChangeScopes, briefSql, spanLabel, tokenizeSql, type ScopedSql, type SqlSpan } from "./sqlChangeScope.js";
import { buildChangeImpacts, type ChangeImpact } from "./sqlChangeImpacts.js";

export type SqlChangeSeverity = "critical" | "warning" | "notice" | "info";

export type SqlChangeFinding = {
  evidence: string[];
  id: string;
  label: string;
  severity: SqlChangeSeverity;
  statement: string;
  whyItMatters: string;
};

export type SqlChangeQuestion = {
  id: string;
  question: string;
  reason: string;
};

export type SqlChangeChecklistItem = {
  id: string;
  label: string;
  reason: string;
};

export type SqlChangeGroup = {
  added: string[];
  id: string;
  label: string;
  removed: string[];
};

export type SqlChangeReviewResult = {
  scopes: { before: ScopedSql; after: ScopedSql };
  impacts: ChangeImpact[];
  counts: { evidenceEntries: number; changedCategories: number; newRiskCategories: number | null };
  analysisStatus: "partial" | "lexical";
  direction: string;
  afterAnalysis: SqlAnalysisResult;
  beforeAnalysis: SqlAnalysisResult;
  checklist: SqlChangeChecklistItem[];
  changeCount: number;
  changeGroups: SqlChangeGroup[];
  keyChanges: SqlChangeFinding[];
  nextQuestions: SqlChangeQuestion[];
  operation: {
    after: string;
    afterTarget?: string;
    before: string;
    beforeTarget?: string;
  };
  severity: SqlChangeSeverity;
  soWhat: string;
  summary: string;
  warnings: string[];
};

const MAX_KEY_CHANGES = 3;
const MAX_QUESTIONS = 4;

const severityRank: Record<SqlChangeSeverity, number> = {
  critical: 0,
  warning: 1,
  notice: 2,
  info: 3,
};

const unique = (values: string[]) => Array.from(new Set(values.filter(Boolean)));

const compact = (value: string) => value.replace(/\s+/g, " ").trim();

const normalizeComparable = (value: string) => tokenizeSql(value).tokens.map(t => t.kind === "word" ? t.text.toUpperCase() : t.text).join(" ");


const detectWriteTarget = (sql: string, operation: string) => {
  const patterns: Record<string, RegExp> = {
    DELETE: /\bDELETE\s+FROM\s+([^\s;(]+)/i,
    INSERT: /\bINSERT\s+INTO\s+([^\s;(]+)/i,
    MERGE: /\bMERGE\s+INTO\s+([^\s;(]+)/i,
    UPDATE: /^\s*UPDATE\s+([^\s;(]+)/i,
  };
  const pattern = patterns[operation];

  return pattern?.exec(sql)?.[1];
};

const collectionDiff = (
  id: string,
  label: string,
  beforeValues: string[],
  afterValues: string[],
): SqlChangeGroup => {
  const beforeMap = new Map(beforeValues.map((value) => [normalizeComparable(value), value]));
  const afterMap = new Map(afterValues.map((value) => [normalizeComparable(value), value]));

  return {
    added: [...afterMap.entries()]
      .filter(([key]) => !beforeMap.has(key))
      .map(([, value]) => value),
    id,
    label,
    removed: [...beforeMap.entries()]
      .filter(([key]) => !afterMap.has(key))
      .map(([, value]) => value),
  };
};


const risksFor = (sql: string) => analyzeSqlRisks(analyzeMultipleSql(sql)).findings;

const riskKey = (finding: SqlRiskFinding) => finding.category;

const newRisks = (beforeRisks: SqlRiskFinding[], afterRisks: SqlRiskFinding[]) => {
  const beforeCategories = new Set(beforeRisks.map(riskKey));

  return afterRisks.filter((finding) => !beforeCategories.has(riskKey(finding)));
};

const riskSeverity = (finding: SqlRiskFinding): SqlChangeSeverity => {
  if (finding.severity === "critical") {
    return "critical";
  }

  if (finding.severity === "high") {
    return "warning";
  }

  return "notice";
};

const addFinding = (findings: SqlChangeFinding[], finding: SqlChangeFinding) => {
  if (!findings.some((item) => item.id === finding.id)) {
    findings.push(finding);
  }
};

const addQuestion = (questions: SqlChangeQuestion[], question: SqlChangeQuestion) => {
  if (questions.length < MAX_QUESTIONS && !questions.some((item) => item.id === question.id)) {
    questions.push(question);
  }
};

const isWriteOperation = (operation: string) => ["DELETE", "INSERT", "MERGE", "UPDATE"].includes(operation);

const scopeDiff = (id: string, label: string, before: Array<{ key: string; span: SqlSpan; block?: string; context?: string; kind?: string; name?: string }>, after: Array<{ key: string; span: SqlSpan; block?: string; context?: string; kind?: string; name?: string }>): SqlChangeGroup => {
  const old = new Map(before.map(e => [e.key, e])), next = new Map(after.map(e => [e.key, e]));
  const display = (e: typeof before[number]) => `${e.context ?? ""} ${e.block ?? ""} ${e.kind ?? ""} ${e.name ?? ""} ${spanLabel(e.span)}: ${e.span.text}`;
  return { id, label, removed: [...old].filter(([key]) => !next.has(key)).map(([, e]) => display(e)), added: [...next].filter(([key]) => !old.has(key)).map(([, e]) => display(e)) };
};

export const buildSqlChangeReview = (
  beforeSql: string,
  afterSql: string,
): SqlChangeReviewResult => {
  if (!beforeSql.trim() || !afterSql.trim()) {
    throw new Error("변경 전 SQL과 변경 후 SQL을 모두 입력해 주세요.");
  }

  const beforeAnalysis = analyzeSql(beforeSql);
  const afterAnalysis = analyzeSql(afterSql);
  const beforeScope = analyzeChangeScopes(beforeSql), afterScope = analyzeChangeScopes(afterSql);
  const sameTokens = beforeScope.canonical === afterScope.canonical;
  const impacts = buildChangeImpacts(beforeScope, afterScope);
  const partial = beforeScope.partial || afterScope.partial;
  const beforeOperation = inspectCommandScope(beforeSql).command ?? "UNKNOWN";
  const afterOperation = inspectCommandScope(afterSql).command ?? "UNKNOWN";
  const beforeTarget = detectWriteTarget(beforeSql, beforeOperation);
  const afterTarget = detectWriteTarget(afterSql, afterOperation);
  const beforeRisks = risksFor(beforeSql);
  const afterRisks = risksFor(afterSql);
  // Legacy risk inference is not used as evidence for partially resolved scopes.
  const introducedRisks = sameTokens || partial ? [] : newRisks(beforeRisks, afterRisks);
  const joinKinds = ["explicit_join", "same_block_condition"];
  const changeGroups = [
    collectionDiff("tables", "참조 테이블", beforeScope.blocks.flatMap(b => b.sources.filter(s => !s.child).map(s => s.table)), afterScope.blocks.flatMap(b => b.sources.filter(s => !s.child).map(s => s.table))),
    scopeDiff("joins", "명시적 JOIN / 동일 블록 관계", beforeScope.relations.filter(r => joinKinds.includes(r.kind)), afterScope.relations.filter(r => joinKinds.includes(r.kind))),
    scopeDiff("correlations", "상관 참조 (JOIN 아님)", beforeScope.relations.filter(r => r.kind === "correlation"), afterScope.relations.filter(r => r.kind === "correlation")),
    scopeDiff("membership", "IN / EXISTS 포함·존재 조건", beforeScope.relations.filter(r => ["in", "exists"].includes(r.kind)), afterScope.relations.filter(r => ["in", "exists"].includes(r.kind))),
    scopeDiff("unknown-relations", "분류 보류 관계", beforeScope.relations.filter(r => r.kind === "unknown"), afterScope.relations.filter(r => r.kind === "unknown")),
    scopeDiff("filters", "WHERE / HAVING 조건 표현", beforeScope.filters, afterScope.filters),
    scopeDiff("group-by", "GROUP BY 기준", beforeScope.groups, afterScope.groups),
    scopeDiff("aggregations", "집계 함수·계산식 (GROUP BY와 별개)", beforeScope.aggregates, afterScope.aggregates),
    scopeDiff("staged-structure", "인라인 뷰 위치별 변경", beforeScope.structures, afterScope.structures),
    collectionDiff("outputs", "최상위 출력 컬럼", beforeScope.outputs.map(o => o.name), afterScope.outputs.map(o => o.name)),
    scopeDiff("output-expressions", "최상위 출력 표현식", beforeScope.outputs, afterScope.outputs),
    scopeDiff("order-by", "정렬 표현식 / 순서", beforeScope.order.filter(o => o.block === beforeScope.blocks[0].id).map((o, i) => ({ ...o, key: `${i}/${o.key}` })), afterScope.order.filter(o => o.block === afterScope.blocks[0].id).map((o, i) => ({ ...o, key: `${i}/${o.key}` }))),
  ];
  if (sameTokens) changeGroups.forEach(g => { g.added = []; g.removed = []; });
  if (!sameTokens && !changeGroups.some(g => g.added.length || g.removed.length)) changeGroups.push({ id: "unclassified", label: "미분류 토큰 차이", removed: [beforeSql], added: [afterSql] });
  const changedGroups = changeGroups.filter((group) => group.added.length > 0 || group.removed.length > 0);
  const findings: SqlChangeFinding[] = [];
  const questions: SqlChangeQuestion[] = [];
  const operationChanged = beforeOperation !== afterOperation;
  const targetChanged = normalizeComparable(beforeTarget ?? "") !== normalizeComparable(afterTarget ?? "");
  const removedAllFilters =
    isWriteOperation(afterOperation) &&
    inspectCommandScope(beforeSql).hasWhere && !inspectCommandScope(afterSql).hasWhere;
  const filterChanges = changedGroups.find((group) => group.id === "filters");
  const joinChanges = changedGroups.find((group) => group.id === "joins");
  const tableChanges = changedGroups.find((group) => group.id === "tables");
  const aggregationChanges = changedGroups.filter((group) => ["aggregations", "group-by"].includes(group.id));
  const groupByChanged = changedGroups.some(g => g.id === "group-by");
  const rootGroupByChanged = beforeScope.groups.filter(g => g.block === beforeScope.blocks[0].id).map(g => g.key).join() !== afterScope.groups.filter(g => g.block === afterScope.blocks[0].id).map(g => g.key).join();
  if (partial) addFinding(findings, { id: "partial-analysis", label: "부분 분석 · 결과 동등성 판단 보류", severity: "warning", statement: "블록·원문 근거는 추출했지만 깊은 중첩 또는 미지원 구문의 대응을 완전히 검증하지 못했습니다.", whyItMatters: "아래 구문 차이는 업무 변경이나 성능 저하의 확정 건수가 아닙니다.", evidence: [...beforeScope.warnings, ...afterScope.warnings] });
  for (const impact of impacts.filter(i => (i.kind === "calculation" && i.assessment === "observed-risk") || i.kind === "null-handling")) {
    addFinding(findings, { id: impact.id, label: impact.label, severity: "warning", statement: impact.statement, whyItMatters: impact.condition, evidence: ["블록·행 위치와 원문은 상세 근거에 보존됩니다."] });
  }

  if (operationChanged || (targetChanged && (beforeTarget || afterTarget))) {
    const changesToWrite = !isWriteOperation(beforeOperation) && isWriteOperation(afterOperation);
    addFinding(findings, {
      evidence: [
        `작업 유형: ${beforeOperation} → ${afterOperation}`,
        ...(beforeTarget || afterTarget ? [`쓰기 대상: ${beforeTarget ?? "없음"} → ${afterTarget ?? "없음"}`] : []),
      ],
      id: "operation-change",
      label: "작업 및 대상 변경",
      severity: changesToWrite || targetChanged ? "critical" : "warning",
      statement: `작업 유형이 ${beforeOperation}에서 ${afterOperation}로 바뀌었습니다.${beforeTarget || afterTarget ? ` 쓰기 대상은 ${beforeTarget ?? "없음"}에서 ${afterTarget ?? "없음"}로 분석됩니다.` : ""}`,
      whyItMatters: "읽기·쓰기 유형이나 대상 테이블의 변화는 검증 범위와 복구 계획을 직접 바꿉니다.",
    });
  }

  for (const impact of impacts.filter(i => (i.kind === "calculation" && i.assessment === "observed-risk") || ["null-handling", "aggregate-period", "local-filter"].includes(i.kind))) {
    addQuestion(questions, { id: `verify-${impact.id}`, question: `${impact.label}에 대해 결과가 달라지는 경계 데이터를 확인했나요?`, reason: impact.condition });
  }
  if (removedAllFilters) {
    addFinding(findings, {
      evidence: filterChanges?.removed ?? ["변경 후 WHERE/HAVING 조건 없음"],
      id: "write-filter-removed",
      label: "쓰기 범위 조건 제거",
      severity: "critical",
      statement: `변경 후 ${afterOperation} SQL에서 파서가 인식한 범위 조건이 사라졌습니다.`,
      whyItMatters: "의도하지 않은 전체 행 변경 가능성이 있으므로 실행 전에 대상 행 수 확인이 필요합니다.",
    });
  } else if (filterChanges) {
    addFinding(findings, {
      evidence: [
        ...filterChanges.removed.map((item) => `제거: ${item}`),
        ...filterChanges.added.map((item) => `추가: ${item}`),
      ],
      id: "filter-change",
      label: "결과 범위 변경",
      severity: "warning",
      statement: `대응이 일치하지 않는 조건 표현이 변경 전 ${filterChanges.removed.length}개, 변경 후 ${filterChanges.added.length}개입니다. 논리 조건 전체의 삭제·신설로 단정하지 않습니다.`,
      whyItMatters: "조건 변화는 반환되거나 변경되는 데이터 범위를 바꿀 수 있지만 실제 행 수는 SQL만으로 알 수 없습니다.",
    });
  }

  if (joinChanges) {
    addFinding(findings, {
      evidence: [
        ...joinChanges.removed.map((item) => `제거: ${item}`),
        ...joinChanges.added.map((item) => `추가: ${item}`),
      ],
      id: "join-change",
      label: "JOIN 경로 변경",
      severity: "warning",
      statement: "명시적 JOIN 또는 같은 쿼리 블록의 연결 조건이 달라졌습니다. JOIN 절과 연결 조건은 중복된 근거일 수 있어 독립 변경 건수로 합산하지 않습니다.",
      whyItMatters: "새 조인 키의 유일성과 관계 수에 따라 결과 행이 늘거나 누락될 가능성이 있습니다.",
    });
  }

  for (const risk of introducedRisks) {
    addFinding(findings, {
      evidence: [risk.evidence],
      id: `new-risk-${risk.category}`,
      label: `새 리스크 · ${risk.title}`,
      severity: riskSeverity(risk),
      statement: risk.message,
      whyItMatters: risk.recommendation,
    });
  }

  if (tableChanges) {
    addFinding(findings, {
      evidence: [
        ...tableChanges.removed.map((item) => `제거: ${item}`),
        ...tableChanges.added.map((item) => `추가: ${item}`),
      ],
      id: "table-change",
      label: "의존 테이블 변경",
      severity: "notice",
      statement: `참조 테이블이 ${tableChanges.removed.length}개 제거되고 ${tableChanges.added.length}개 추가되었습니다.`,
      whyItMatters: "새 테이블의 스키마, 권한, 데이터 보존 기준이 변경 영향 범위에 포함됩니다.",
    });
  }

  if (aggregationChanges.length > 0) {
    addFinding(findings, {
      evidence: aggregationChanges.flatMap((group) => [
        ...group.removed.map((item) => `제거: ${item}`),
        ...group.added.map((item) => `추가: ${item}`),
      ]),
      id: "aggregation-change",
      label: groupByChanged ? rootGroupByChanged ? "최상위 GROUP BY 기준 변경" : "내부 GROUP BY 구문 변경" : "집계 계산식 변경",
      severity: "notice",
      statement: groupByChanged ? rootGroupByChanged ? "최상위 GROUP BY 표현식의 차이가 확인됐습니다. 실제 한 행의 단위는 별도 검증이 필요합니다." : "최상위 GROUP BY는 변경되지 않았습니다. 제거/추가된 출력이나 내부 블록의 GROUP BY 구문 차이가 있습니다." : "집계 함수 또는 입력 계산식이 변경됐습니다. GROUP BY 변경은 확인되지 않았습니다.",
      whyItMatters: "계산식·대상 필터·NULL 처리는 집계 단위가 같아도 숫자를 바꿀 수 있습니다.",
    });
  }

  if (removedAllFilters) {
    addQuestion(questions, {
      id: "verify-write-scope",
      question: "변경 후 조건으로 영향을 받는 행 수를 실행 전에 SELECT로 확인했나요?",
      reason: "쓰기 SQL의 범위 조건 제거가 감지되었습니다.",
    });
  }

  if (operationChanged || targetChanged || isWriteOperation(afterOperation)) {
    addQuestion(questions, {
      id: "verify-rollback",
      question: "대상 테이블, 실행 순서, 트랜잭션과 롤백 방법이 문서화되어 있나요?",
      reason: `${afterOperation} 작업은 실제 데이터를 변경할 수 있습니다.`,
    });
  }

  if (filterChanges && !removedAllFilters) {
    addQuestion(questions, {
      id: "verify-filter-scope",
      question: "추가·제거된 조건이 의도한 업무 범위와 경계값을 정확히 표현하나요?",
      reason: "WHERE 또는 HAVING 조건 변화가 감지되었습니다.",
    });
  }

  if (joinChanges) {
    addQuestion(questions, {
      id: "verify-join-cardinality",
      question: "새 조인 키의 1:1·1:N 관계와 조인 전후 행 수 변화를 확인했나요?",
      reason: "JOIN 경로가 변경되어 결과 중복 또는 누락 가능성을 확인해야 합니다.",
    });
  }

  if (tableChanges || targetChanged) {
    addQuestion(questions, {
      id: "verify-table-impact",
      question: "추가·제거된 테이블을 사용하는 화면, 배치, View의 영향 범위를 확인했나요?",
      reason: targetChanged ? "쓰기 대상 테이블이 변경되었습니다." : "테이블 의존성이 변경되었습니다.",
    });
  }

  if (aggregationChanges.length > 0) {
    addQuestion(questions, {
      id: "verify-aggregation-grain",
      question: rootGroupByChanged ? "변경된 최상위 GROUP BY가 기대하는 한 행의 업무 단위와 일치하나요?" : groupByChanged ? "내부 GROUP BY 변경이 출력 컬럼·하위 블록 제거에 따른 것인지 확인했나요?" : "변경된 계산식과 집계 대상 필터의 결과를 따로 검증했나요?",
      reason: groupByChanged ? "GROUP BY 표현식 차이가 감지되었습니다." : "GROUP BY 변경 없이 집계식 차이가 감지되었습니다.",
    });
  }

  if (questions.length === 0) {
    addQuestion(questions, {
      id: "verify-unparsed-difference",
      question: "출력 컬럼, 정렬, 별칭, 리터럴 등 구조 요약 밖의 차이도 의도한 변경인지 확인했나요?",
      reason: "현재 파서가 인식한 주요 구조 변화는 없거나 제한적입니다.",
    });
  }

  const sortedFindings = findings.sort(
    (left, right) => severityRank[left.severity] - severityRank[right.severity],
  );
  const changeCount =
    changedGroups.reduce((total, group) => total + group.added.length + group.removed.length, 0) +
    (operationChanged ? 1 : 0) +
    (targetChanged && (beforeTarget || afterTarget) ? 1 : 0);
  const keyChanges = sortedFindings.length > 0
    ? sortedFindings.slice(0, MAX_KEY_CHANGES)
    : [{
        evidence: ["파서가 인식한 테이블, JOIN, 조건, 집계, 단계 구조 차이 없음"],
        id: "no-structural-change",
        label: "주요 구조 변화 없음",
        severity: "info" as const,
        statement: "현재 파서가 인식한 범위에서 주요 구조 차이를 찾지 못했습니다.",
        whyItMatters: "표현식, 출력 순서, 주석처럼 요약되지 않은 차이는 원문 비교가 필요합니다.",
      }];
  const severity = keyChanges[0]?.severity ?? "info";
  const summary = (partial ? "부분 분석입니다. " : "") + (changeCount > 0
    ? `${changedGroups.length}개 구문 분류에서 차이를 확인했습니다. 계산식·필터·출력 스키마를 구분해 검토해야 하며, 분류 수는 업무 변경·위험 건수가 아닙니다.`
    : "현재 토큰 분석 범위에서 차이가 없습니다. 결과 동등성의 증명은 아닙니다.");
  const soWhat = severity === "critical"
    ? "이 변경은 데이터 변경 범위나 쓰기 대상에 직접 영향을 줄 수 있습니다. 배포 전에 대상 행 수와 복구 방법을 먼저 확인해야 합니다."
    : severity === "warning"
      ? "계산식, NULL 처리, 집계 대상과 행 선택 조건을 분리해 검증해야 합니다. 상관 참조나 EXISTS 자체는 JOIN 행 증식의 근거가 아닙니다."
      : changeCount > 0
        ? "구조 변화가 확인되었지만 실제 결과·성능 영향은 실행 데이터와 스키마를 함께 확인해야 판단할 수 있습니다."
        : "주요 구조가 같더라도 출력 컬럼, 리터럴, 정렬처럼 파서 요약 밖의 변경은 별도 확인이 필요합니다.";
  const limitedQuestions = questions.slice(0, MAX_QUESTIONS);
  const checklist: SqlChangeChecklistItem[] = [
    {
      id: "confirm-change-purpose",
      label: "변경 목적과 기대 결과를 관계자 기준으로 확인했습니다.",
      reason: "구조 비교는 업무 요구사항의 정답 여부를 판단하지 않습니다.",
    },
    ...limitedQuestions.map((question) => ({
      id: `check-${question.id}`,
      label: question.question,
      reason: question.reason,
    })),
  ];
  const warnings = unique([
    ...beforeScope.warnings.map(w => `변경 전: ${w}`), ...afterScope.warnings.map(w => `변경 후: ${w}`),
    "변경 비교는 범위 보존 토큰 분석, 기존 단건 설명·위험 엔진은 정규식과 괄호/문자 스캔을 사용합니다. 완전한 AST 파서는 아닙니다.",
    "동일 구문이 필터·집계·포함 조건 등의 여러 상세 분류에 나타날 수 있습니다. 상세 항목 수를 업무 변경 수로 합산하지 않습니다.",
    "블록 대응은 출력 이름과 최상위 조건의 참조 테이블 문맥을 사용합니다. 복잡한 이동·우회 표현의 의미 동등성은 판단하지 않습니다.",
    ...beforeAnalysis.warnings.map((warning) => `변경 전: ${warning}`),
    ...afterAnalysis.warnings.map((warning) => `변경 후: ${warning}`),
    "구조 비교는 SQL을 실행하지 않으며 실제 행 수, 실행 계획, 제약조건을 확인하지 않습니다.",
  ]);

  return {
    scopes: { before: beforeScope, after: afterScope }, impacts,
    analysisStatus: partial ? "partial" : "lexical",
    counts: { evidenceEntries: changeCount, changedCategories: changedGroups.length, newRiskCategories: partial ? null : introducedRisks.length },
    direction: `변경 전 → 변경 후. 최상위 FROM: ${beforeScope.blocks[0].sources.map(s => s.child ? `인라인 뷰 ${s.alias}` : `${s.table} ${s.alias}`).join(", ")} → ${afterScope.blocks[0].sources.map(s => s.child ? `인라인 뷰 ${s.alias}` : `${s.table} ${s.alias}`).join(", ")}`,
    afterAnalysis,
    beforeAnalysis,
    checklist,
    changeCount,
    changeGroups,
    keyChanges: keyChanges.map(f => ({ ...f, evidence: f.evidence.map(e => briefSql(e)) })),
    nextQuestions: limitedQuestions,
    operation: {
      after: afterOperation,
      afterTarget,
      before: beforeOperation,
      beforeTarget,
    },
    severity,
    soWhat,
    summary,
    warnings,
  };
};

export type SqlChangeReportItem = {
  id: string;
  title: string;
  observation: string;
  consequence: string;
  status: "조건부 영향" | "판단 보류";
  evidence: string[];
};

// The UI and exported report share these conclusions; raw parser inventories remain an appendix.
export const buildSqlChangeReportItems = (review: SqlChangeReviewResult): SqlChangeReportItem[] => {
  const actionable = review.impacts.filter(i => i.assessment === "observed-risk");
  const items: SqlChangeReportItem[] = actionable.map(i => ({
    id: i.id, title: i.label, observation: i.statement, consequence: i.condition,
    status: "조건부 영향", evidence: i.evidence,
  }));
  const unresolved = review.impacts.filter(i => i.assessment === "unresolved"
    && !actionable.some(a => a.label.split(":")[0] === i.label.split(":")[0]));
  if (unresolved.length) items.push({
    id: "unresolved-expressions", title: "표현식과 참조 경로 · 대응 확인 필요",
    observation: `${unique(unresolved.map(i => i.label.split(":")[0])).join(", ")}의 표현식 또는 참조 경로가 다릅니다.`,
    consequence: "표현 정리인지 실제 계산 변경인지 아직 구분하지 못했습니다. 인라인 뷰의 출력과 내부 조건을 대조해야 하며, 영향 없음으로 승인하지 않습니다.",
    status: "판단 보류", evidence: unresolved.flatMap(i => i.evidence),
  });
  const rootViews = (scope: ScopedSql) => scope.structures.filter(s => s.block === scope.blocks[0].id);
  const oldViews = rootViews(review.scopes.before), newViews = rootViews(review.scopes.after);
  if (oldViews.length !== newViews.length) items.push({
    id: "root-source-report", title: "최상위 조회 구조",
    observation: review.direction,
    consequence: `최상위 인라인 뷰 구성이 달라졌습니다. 변경 후 내부 인라인 뷰 ${review.scopes.after.structures.filter(s => s.block !== review.scopes.after.blocks[0].id).map(s => s.name).join(", ") || "없음"}. 내부 뷰까지 모두 제거되었다는 뜻은 아니며 결과 동등성은 별도 확인이 필요합니다.`,
    status: "판단 보류", evidence: [...oldViews, ...newViews].map(s => `${s.context} ${spanLabel(s.span)}`),
  });
  // Keep changes with no impact adapter visible, rather than silently presenting an empty report.
  if (!items.length) for (const f of review.keyChanges.filter(f => f.id !== "partial-analysis")) items.push({
    id: f.id, title: f.label, observation: f.statement, consequence: f.whyItMatters,
    status: "판단 보류", evidence: f.evidence,
  });
  return items;
};

export const buildSqlChangeReviewMarkdown = (review: SqlChangeReviewResult, checkedIds: string[] = []) => [
  "# SQL 변경 검토 보고서", "", review.direction,
  `검증 범위: ${review.analysisStatus === "partial" ? "부분 분석 · 미해석 구간 있음" : "지원 범위 내 구문 비교"}. SQL을 실행하지 않았으며 결과 동등성·성능을 보증하지 않습니다.`,
  "", "## 핵심 결과",
  ...review.keyChanges.map(f => `- ${f.label}: ${f.statement}`),
  "", "## 그래서 무엇이 중요한가", review.soWhat,
  "", "## 다음으로 확인할 질문",
  ...review.nextQuestions.map((q, i) => `${i + 1}. ${q.question}`),
  "", "## 변경별 결과 영향",
  ...buildSqlChangeReportItems(review).flatMap((item, i) => [
    `### ${i + 1}. ${item.title}`, `- 확인된 변경: ${item.observation}`,
    `- 결과 영향·확인 조건: ${item.consequence}`, `- 판단 상태: ${item.status}`,
    ...unique(item.evidence.map(e => e.match(/^(.*?)L\d+:\d+ \[\d+,\d+\)/)?.[0] ?? "").filter(Boolean)).slice(0, 4).map(e => `- 원문 위치: ${e}`), "",
  ]),
  "## 변경 검토 체크리스트",
  ...review.checklist.map(item => `- [${checkedIds.includes(item.id) ? "x" : " "}] ${item.label}`),
  "", "## 결론",
  review.changeCount === 0 ? "정규화 범위 내 구문 차이가 없습니다. 이것이 미지원 구문까지 포함한 의미 동등성 증명은 아닙니다."
    : "확인된 변경의 발생 조건에 해당하는 데이터를 검증한 뒤 변경 의도와 일치하는지 판단해야 합니다. 미해석 항목은 영향 없음으로 처리하지 않습니다.",
  "", "전체 SQL·블록별 관계·미대응 구문 목록은 별도 상세 근거 보고서에서 확인합니다.",
].join("\n");

export const buildSqlChangeReviewTechnicalMarkdown = (review: SqlChangeReviewResult) => [
  "# SQL 변경 검토",
  "",
  review.direction,
  `분석 방식: 범위 보존 토큰 비교 (${review.analysisStatus === "partial" ? "부분 분석" : "지원 범위 내 구문 분석"}). SQL 실행·결과 동등성 검증 없음.`,
  `집계 기준: 구문 분류 ${review.counts.changedCategories}개 / 상세 추가·제거 근거 ${review.counts.evidenceEntries}항목 / 별도 신규 룰 위험 분류 ${review.counts.newRiskCategories === null ? "산정 보류 (부분 분석)" : `${review.counts.newRiskCategories}개`}. 서로 더하지 않습니다.`,
  "## 핵심 결과",
  review.summary,
  "",
  ...review.keyChanges.flatMap((finding, index) => [
    `### ${index + 1}. ${finding.label}`,
    `- 판단: ${finding.statement}`,
    `- 중요 이유: ${finding.whyItMatters}`,
    ...finding.evidence.map((evidence) => `- 근거: ${evidence}`),
    "",
  ]),
  "## 그래서 무엇이 중요한가",
  review.soWhat,
  "",
  "## 다음으로 확인할 질문",
  ...review.nextQuestions.map((question, index) =>
    `${index + 1}. ${question.question}\n   - 이유: ${question.reason}`,
  ),
  "",
  "## 변경 검토 체크리스트",
  ...review.checklist.map((item) => `- [ ] ${item.label}\n  - ${item.reason}`),
  "",
  "## 구조 변경 상세",
  "### 결과 영향 검토 (발생 조건을 충족할 때 달라질 수 있음)",
  ...review.impacts.flatMap(impact => [
    `#### ${impact.label}`,
    `- 원문 관찰: ${impact.statement}`,
    `- 영향 조건 / 확인 필요: ${impact.condition}`,
    `- 판단: ${impact.assessment === "unresolved" ? "결과 영향 판단 보류" : "변경 관찰 + 조건부 영향 가능성 (실행 검증 아님)"}`,
    ...impact.evidence.map(e => `- 상세 위치: ${briefSql(e, 280)}`), "",
  ]),
  ...review.changeGroups.flatMap((group) => [
    `### ${group.label}`,
    ...(group.removed.length > 0 ? group.removed.map((item) => `- 변경 전 전용 구문: ${briefSql(item, 280)}`) : ["- 변경 전 전용 구문: 없음"]),
    ...(group.added.length > 0 ? group.added.map((item) => `- 변경 후 전용 구문: ${briefSql(item, 280)}`) : ["- 변경 후 전용 구문: 없음"]),
    "",
  ]),
  "### 블록별 소스와 관계 (별칭·소속 보존)",
  ...(["before", "after"] as const).flatMap(side => [
    `#### ${side === "before" ? "변경 전" : "변경 후"}`,
    ...review.scopes[side].blocks.map(b => `- ${b.id} / 부모 ${b.parent ?? "없음"} / ${b.context} / ${spanLabel(b.span)} / FROM ${b.sources.map(s => `${s.table} AS ${s.alias}${s.child ? ` (내부 ${s.child})` : ""}`).join(", ") || "없음"}`),
    ...review.scopes[side].relations.map(r => `- ${r.kind}: ${r.left} → ${r.right} / ${r.block} / ${spanLabel(r.span)}`),
  ]),
  "### 원문 전체 (근거 위치의 기준, 0-based 문자 범위 / 1-based 행·열)",
  "#### 변경 전", "```sql", review.scopes.before.sql, "```",
  "#### 변경 후", "```sql", review.scopes.after.sql, "```",
  "## 주의 사항",
  ...review.warnings.map((warning) => `- ${warning}`),
].join("\n");
