import { analyzeMultipleSql } from "./multiSqlAnalysis.js";
import { analyzeSqlRisks, type SqlRiskFinding } from "./riskDetector.js";
import { analyzeSql, type SqlAnalysisResult } from "./sqlExplainer.js";

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

const normalizeComparable = (value: string) => compact(value).toUpperCase();

const detectOperation = (sql: string) => {
  const compactSql = compact(sql.replace(/--[^\r\n]*/g, " ").replace(/\/\*[\s\S]*?\*\//g, " "));

  if (/\bMERGE\s+INTO\b/i.test(compactSql)) {
    return "MERGE";
  }

  if (/\bINSERT\s+INTO\b/i.test(compactSql)) {
    return "INSERT";
  }

  if (/^\s*UPDATE\b/i.test(compactSql)) {
    return "UPDATE";
  }

  if (/^\s*DELETE\b/i.test(compactSql)) {
    return "DELETE";
  }

  if (/\bSELECT\b/i.test(compactSql)) {
    return "SELECT";
  }

  return "UNKNOWN";
};

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

const tableValues = (analysis: SqlAnalysisResult) =>
  unique(analysis.tables.map((table) => table.rawName));

const joinValues = (analysis: SqlAnalysisResult) =>
  unique(analysis.joins.map((join) => `${join.left} → ${join.right}${join.joinType ? ` (${join.joinType})` : ""}`));

const filterValues = (analysis: SqlAnalysisResult) =>
  unique(
    [...analysis.filters, ...analysis.havingConditions].map(
      (filter) => `${filter.stage}: ${compact(filter.condition)}`,
    ),
  );

const groupByValues = (analysis: SqlAnalysisResult) =>
  unique(analysis.groupBy.map((group) => `${group.stage}: ${group.columns.join(", ")}`));

const aggregationValues = (analysis: SqlAnalysisResult) =>
  unique(
    analysis.aggregations.map(
      (aggregation) =>
        `${aggregation.stage}: ${aggregation.functionName} ${compact(aggregation.expression)}${aggregation.alias ? ` AS ${aggregation.alias}` : ""}`,
    ),
  );

const stagedStructureValues = (analysis: SqlAnalysisResult) =>
  unique([
    ...analysis.ctes.map((cte) => `CTE ${cte.name}${cte.dependencies.length > 0 ? ` ← ${cte.dependencies.join(", ")}` : ""}`),
    ...analysis.subqueries.map((subquery) => `${subquery.type} 서브쿼리 (${subquery.stage})`),
    ...analysis.setOperations.map((operation) => operation.operator),
    ...analysis.windowFunctions.map((windowFunction) =>
      `${windowFunction.stage}: ${windowFunction.functionName} OVER${windowFunction.alias ? ` AS ${windowFunction.alias}` : ""}`,
    ),
  ]);

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

export const buildSqlChangeReview = (
  beforeSql: string,
  afterSql: string,
): SqlChangeReviewResult => {
  if (!beforeSql.trim() || !afterSql.trim()) {
    throw new Error("변경 전 SQL과 변경 후 SQL을 모두 입력해 주세요.");
  }

  const beforeAnalysis = analyzeSql(beforeSql);
  const afterAnalysis = analyzeSql(afterSql);
  const beforeOperation = detectOperation(beforeSql);
  const afterOperation = detectOperation(afterSql);
  const beforeTarget = detectWriteTarget(beforeSql, beforeOperation);
  const afterTarget = detectWriteTarget(afterSql, afterOperation);
  const beforeRisks = risksFor(beforeSql);
  const afterRisks = risksFor(afterSql);
  const introducedRisks = newRisks(beforeRisks, afterRisks);
  const changeGroups = [
    collectionDiff("tables", "참조 테이블", tableValues(beforeAnalysis), tableValues(afterAnalysis)),
    collectionDiff("joins", "JOIN 관계", joinValues(beforeAnalysis), joinValues(afterAnalysis)),
    collectionDiff("filters", "WHERE / HAVING 조건", filterValues(beforeAnalysis), filterValues(afterAnalysis)),
    collectionDiff("group-by", "GROUP BY 기준", groupByValues(beforeAnalysis), groupByValues(afterAnalysis)),
    collectionDiff("aggregations", "집계 지표", aggregationValues(beforeAnalysis), aggregationValues(afterAnalysis)),
    collectionDiff("staged-structure", "CTE / 서브쿼리 / 윈도우 / SET", stagedStructureValues(beforeAnalysis), stagedStructureValues(afterAnalysis)),
  ];
  const changedGroups = changeGroups.filter((group) => group.added.length > 0 || group.removed.length > 0);
  const findings: SqlChangeFinding[] = [];
  const questions: SqlChangeQuestion[] = [];
  const operationChanged = beforeOperation !== afterOperation;
  const targetChanged = normalizeComparable(beforeTarget ?? "") !== normalizeComparable(afterTarget ?? "");
  const removedAllFilters =
    isWriteOperation(afterOperation) &&
    beforeAnalysis.filters.length + beforeAnalysis.havingConditions.length > 0 &&
    afterAnalysis.filters.length + afterAnalysis.havingConditions.length === 0;
  const filterChanges = changedGroups.find((group) => group.id === "filters");
  const joinChanges = changedGroups.find((group) => group.id === "joins");
  const tableChanges = changedGroups.find((group) => group.id === "tables");
  const aggregationChanges = changedGroups.filter((group) => ["aggregations", "group-by"].includes(group.id));

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
      statement: `조건이 ${filterChanges.removed.length}개 제거되고 ${filterChanges.added.length}개 추가되었습니다.`,
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
      statement: `JOIN 관계가 ${joinChanges.removed.length}개 제거되고 ${joinChanges.added.length}개 추가되었습니다.`,
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
      label: "집계 단위 변경",
      severity: "notice",
      statement: "GROUP BY 기준 또는 집계 지표가 변경되었습니다.",
      whyItMatters: "집계 단위의 변화는 같은 데이터에서도 결과 숫자의 의미를 바꿀 수 있습니다.",
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
      question: "변경된 집계 기준이 기대하는 한 행의 업무 단위와 일치하나요?",
      reason: "GROUP BY 또는 집계 지표 변화가 감지되었습니다.",
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
    (targetChanged && (beforeTarget || afterTarget) ? 1 : 0) +
    introducedRisks.length;
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
  const summary = changeCount > 0
    ? `변경 전후 구조에서 ${changeCount}개의 추가·제거 또는 위험 변화를 확인했습니다.`
    : "파서가 인식한 주요 SQL 구조는 변경 전후 동일합니다.";
  const soWhat = severity === "critical"
    ? "이 변경은 데이터 변경 범위나 쓰기 대상에 직접 영향을 줄 수 있습니다. 배포 전에 대상 행 수와 복구 방법을 먼저 확인해야 합니다."
    : severity === "warning"
      ? "조건이나 JOIN 변화는 실제 결과 범위를 바꿀 수 있습니다. 문장 차이보다 행 수와 관계 수 검증이 우선입니다."
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
    ...beforeAnalysis.warnings.map((warning) => `변경 전: ${warning}`),
    ...afterAnalysis.warnings.map((warning) => `변경 후: ${warning}`),
    "구조 비교는 SQL을 실행하지 않으며 실제 행 수, 실행 계획, 제약조건을 확인하지 않습니다.",
  ]);

  return {
    afterAnalysis,
    beforeAnalysis,
    checklist,
    changeCount,
    changeGroups,
    keyChanges,
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

export const buildSqlChangeReviewMarkdown = (review: SqlChangeReviewResult) => [
  "# SQL 변경 검토",
  "",
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
  ...review.changeGroups.flatMap((group) => [
    `### ${group.label}`,
    ...(group.removed.length > 0 ? group.removed.map((item) => `- 제거: ${item}`) : ["- 제거: 없음"]),
    ...(group.added.length > 0 ? group.added.map((item) => `- 추가: ${item}`) : ["- 추가: 없음"]),
    "",
  ]),
  "## 주의 사항",
  ...review.warnings.map((warning) => `- ${warning}`),
].join("\n");
