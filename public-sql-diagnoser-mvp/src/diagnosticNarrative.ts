import type { MultiSqlAnalysisResult, MultiSqlStatement } from "./multiSqlAnalysis.js";
import { analyzeSqlRisks, type SqlRiskAnalysisResult, type SqlRiskFinding } from "./riskDetector.js";
import type { SqlAnalysisResult } from "./sqlExplainer.js";
import type { TableAssetMap, TableAssetProfile } from "./tableAssetMap.js";

export type DiagnosticTarget = {
  id?: string;
  name?: string;
  type: "column" | "condition" | "join" | "sql" | "table";
};

export type DiagnosticFindingSeverity = "critical" | "info" | "notice" | "warning";

export type DiagnosticNarrativeFinding = {
  evidence: string[];
  id: string;
  label: string;
  severity: DiagnosticFindingSeverity;
  statement: string;
  target?: DiagnosticTarget;
};

export type DiagnosticNarrativePriorityTarget = {
  id: string;
  label: string;
  reasons: string[];
  severity: DiagnosticFindingSeverity;
  target?: DiagnosticTarget;
};

export type DiagnosticNarrativeQuestion = {
  id: string;
  question: string;
  reason: string;
  target?: DiagnosticTarget;
};

export type DiagnosticNarrative = {
  keyFindings: DiagnosticNarrativeFinding[];
  nextQuestions: DiagnosticNarrativeQuestion[];
  priorityTargets: DiagnosticNarrativePriorityTarget[];
  soWhat: {
    rationale?: string;
    statement: string;
  };
  title: string;
};

const MAX_KEY_FINDINGS = 3;
const MAX_NEXT_QUESTIONS = 3;
const MAX_PRIORITY_TARGETS = 3;

const unique = <T>(items: T[]) => Array.from(new Set(items));

const severityRank: Record<DiagnosticFindingSeverity, number> = {
  critical: 0,
  warning: 1,
  notice: 2,
  info: 3,
};

const riskSeverity = (severity: SqlRiskFinding["severity"]): DiagnosticFindingSeverity => {
  if (severity === "critical") {
    return "critical";
  }

  if (severity === "high") {
    return "warning";
  }

  return "notice";
};

const writeOperation = (sql: string) => {
  const match = sql.match(/\b(INSERT|UPDATE|DELETE|MERGE)\b/i);
  return match?.[1]?.toUpperCase();
};

const hasDateCondition = (analysis: SqlAnalysisResult) =>
  [...analysis.filters, ...analysis.havingConditions].some((filter) =>
    /(date|day|month|year|기간|일자|날짜|월|년|current_date|current_timestamp|interval|timestamp|to_date|date_trunc|\d{4}-\d{2}-\d{2})/i.test(filter.condition),
  );

const hasLeftJoin = (analysis: SqlAnalysisResult) =>
  analysis.joins.some((join) => /\bLEFT(?:\s+OUTER)?\b/i.test(join.joinType ?? join.raw));

const primarySingleStructure = (sql: string, analysis: SqlAnalysisResult): DiagnosticNarrativeFinding => {
  const operation = writeOperation(sql);
  const tableCount = analysis.tables.length;
  const joinCount = analysis.joins.length;
  const cteCount = analysis.ctes.length;
  const subqueryCount = analysis.subqueries.length;
  const aggregationCount = analysis.aggregations.length;
  const groupByCount = analysis.groupBy.length;

  if (operation) {
    return {
      evidence: [`${operation} 문`, `${tableCount}개 테이블 추출`],
      id: "single-structure-write",
      label: "변경 구조",
      severity: "warning",
      statement: `이 SQL은 ${operation} 작업이며, 추출된 ${tableCount}개 테이블과 조건을 기준으로 데이터 변경 범위를 결정합니다.`,
    };
  }

  if (joinCount > 0 && aggregationCount > 0) {
    return {
      evidence: [`테이블 ${tableCount}개`, `JOIN ${joinCount}개`, `집계 ${aggregationCount}개`, `GROUP BY ${groupByCount}개`],
      id: "single-structure-join-aggregation",
      label: "집계 전 조인 경로",
      severity: joinCount >= 4 ? "warning" : "notice",
      statement: `${tableCount}개 테이블을 ${joinCount}개 JOIN으로 연결한 뒤 ${aggregationCount}개의 집계 지표를 계산합니다.`,
    };
  }

  if (cteCount > 0 || subqueryCount > 0) {
    return {
      evidence: [`CTE ${cteCount}개`, `서브쿼리 ${subqueryCount}개`],
      id: "single-structure-staged",
      label: "중간 결과 의존성",
      severity: cteCount + subqueryCount >= 3 ? "warning" : "notice",
      statement: `${cteCount > 0 ? `${cteCount}개의 CTE` : ""}${cteCount > 0 && subqueryCount > 0 ? "와 " : ""}${subqueryCount > 0 ? `${subqueryCount}개의 서브쿼리` : ""}를 사용해 중간 결과를 단계적으로 구성합니다.`,
    };
  }

  if (aggregationCount > 0 || groupByCount > 0) {
    return {
      evidence: [`집계 ${aggregationCount}개`, `GROUP BY ${groupByCount}개`],
      id: "single-structure-aggregation",
      label: "집계 기준",
      severity: "notice",
      statement: `${aggregationCount}개의 집계 지표를 ${groupByCount > 0 ? "그룹 기준과 함께" : "전체 범위에서"} 계산합니다.`,
    };
  }

  if (joinCount > 0) {
    return {
      evidence: [`테이블 ${tableCount}개`, `JOIN ${joinCount}개`],
      id: "single-structure-join",
      label: "테이블 연결",
      severity: joinCount >= 4 ? "warning" : "notice",
      statement: `${tableCount}개 테이블이 ${joinCount}개의 JOIN 관계로 연결되어 조회 범위를 구성합니다.`,
    };
  }

  if (analysis.filters.length > 0 || analysis.havingConditions.length > 0) {
    return {
      evidence: [`WHERE/HAVING ${analysis.filters.length + analysis.havingConditions.length}개`],
      id: "single-structure-filter",
      label: "조회 범위 조건",
      severity: "info",
      statement: `${tableCount > 0 ? `${tableCount}개 테이블을 기준으로 ` : ""}${analysis.filters.length + analysis.havingConditions.length}개의 조건이 결과 범위를 제한합니다.`,
    };
  }

  return {
    evidence: [`테이블 ${tableCount}개`],
    id: "single-structure-simple",
    label: "조회 구조",
    severity: "info",
    statement: `${tableCount > 0 ? `${tableCount}개 테이블을 참조하는` : "테이블 참조를 찾지 못한"} 단순 구조로 분석되었습니다.`,
  };
};

const buildSingleRiskAnalysis = (sql: string, analysis: SqlAnalysisResult): SqlRiskAnalysisResult =>
  analyzeSqlRisks({
    businessIntentSummary: { [analysis.businessIntent.type]: 1 },
    conditionUsage: [],
    joinUsage: [],
    statements: [{
      analysis,
      id: "SQL-001",
      sql,
      title: analysis.summary,
      warnings: analysis.warnings,
    }],
    tableUsage: [],
    warnings: [],
  });

const singleRiskSoWhat = (risk: SqlRiskFinding) => {
  const messages: Partial<Record<SqlRiskFinding["category"], string>> = {
    date_function_on_column: "날짜 컬럼에 적용한 함수는 실행 계획과 인덱스 사용 방식에 영향을 줄 수 있으므로, 실제 실행 계획을 확인하기 전에는 성능 문제로 단정하지 말아야 합니다.",
    hardcoded_code_value: "코드값이 여러 SQL에 직접 작성되면 업무 정의가 바뀔 때 수정 지점이 늘어날 수 있어 기준의 일관성을 먼저 확인해야 합니다.",
    implicit_join: "명시적 JOIN이 아닌 테이블 연결은 조건 누락 여부를 읽기 어렵게 만들어 결과 정확성 검토가 우선입니다.",
    leading_wildcard_like: "앞쪽 와일드카드 검색은 데이터량과 인덱스 구성에 따라 부담이 달라질 수 있으므로, 실제 사용량과 실행 계획을 함께 확인해야 합니다.",
    personal_info_condition: "개인정보로 추정되는 조건은 SQL 자체의 정확성 외에도 로그, 문서 공유, AI 보강 범위를 함께 점검해야 합니다.",
    select_star: "결과 컬럼이 스키마에 따라 달라질 수 있어, 이 SQL을 사용하는 화면·API·배치의 변경 영향 확인이 우선입니다.",
    suspicious_aggregation: "집계 기준과 조인 단위가 맞지 않으면 합계가 달라질 수 있어, 실제 행 수와 키 유일성 검토가 우선입니다.",
    too_many_joins: "여러 테이블이 하나의 경로에 연결되면 조인 조건 하나의 차이가 결과 행 수에 영향을 줄 수 있어, 정확성 검토가 우선입니다.",
    unsafe_update_delete: "쓰기 SQL은 대상 범위가 의도와 다르면 복구 범위가 커질 수 있어, 실행 전 대상 행과 롤백 준비를 먼저 확인해야 합니다.",
  };

  return messages[risk.category] ?? "룰 기반으로 감지된 구조 신호는 실제 데이터나 실행 계획을 확인하기 전에는 원인으로 단정할 수 없으므로, 근거와 영향 범위를 먼저 검토해야 합니다.";
};

const buildSingleSoWhat = (
  sql: string,
  analysis: SqlAnalysisResult,
  primaryRisk: SqlRiskFinding | undefined,
) => {
  if (primaryRisk) {
    return {
      rationale: primaryRisk.title,
      statement: singleRiskSoWhat(primaryRisk),
    };
  }

  if (writeOperation(sql)) {
    return {
      statement: "이 SQL은 데이터를 변경하므로, 구조가 단순해 보여도 대상 범위와 실행 순서가 의도와 일치하는지 확인하는 것이 가장 중요합니다.",
    };
  }

  if (analysis.joins.length > 0 && analysis.aggregations.length > 0) {
    return {
      statement: "집계값의 정확성은 정렬이나 표현보다 조인 전후의 행 단위에 더 크게 좌우될 수 있어, 조인 키와 집계 기준의 일치를 먼저 확인해야 합니다.",
    };
  }

  if (analysis.ctes.length > 0 || analysis.subqueries.length > 0) {
    return {
      statement: "중간 결과가 여러 단계로 이어지므로, 각 단계의 조건과 행 단위가 최종 결과의 의도와 같은지 확인하는 것이 유지보수에 중요합니다.",
    };
  }

  if (analysis.joins.length > 0) {
    return {
      statement: "테이블 연결이 있는 조회에서는 결과 행 수와 누락 여부가 조인 키의 관계에 따라 달라질 수 있어, 키의 유일성과 선택적 연결 여부를 먼저 확인해야 합니다.",
    };
  }

  return {
    statement: "현재 구조는 복잡한 위험 신호가 두드러지지 않지만, SQL이 표현하는 조회 범위가 실제 업무 대상과 일치하는지는 별도로 확인해야 합니다.",
  };
};

const addQuestion = (
  questions: DiagnosticNarrativeQuestion[],
  question: DiagnosticNarrativeQuestion,
) => {
  if (questions.some((item) => item.question === question.question) || questions.length >= MAX_NEXT_QUESTIONS) {
    return;
  }

  questions.push(question);
};

const buildSingleQuestions = (
  sql: string,
  analysis: SqlAnalysisResult,
  primaryRisk: SqlRiskFinding | undefined,
) => {
  const questions: DiagnosticNarrativeQuestion[] = [];
  const operation = writeOperation(sql);
  const firstRelation = analysis.relations[0] ?? analysis.joins[0];

  if (operation) {
    addQuestion(questions, {
      id: "single-write-row-count",
      question: "동일한 조건으로 실행 전 대상 행 수를 SELECT로 확인했나요?",
      reason: `${operation} SQL은 실제 데이터 변경 범위를 결정합니다.`,
      target: { type: "sql" },
    });
    addQuestion(questions, {
      id: "single-write-rollback",
      question: "실행 순서, 트랜잭션, 롤백 방법이 준비되어 있나요?",
      reason: "데이터 변경 후에는 구조 분석만으로 복구 가능 여부를 판단할 수 없습니다.",
      target: { type: "sql" },
    });
  }

  // Correctness questions that can change the meaning of the query take precedence.
  if (hasLeftJoin(analysis) && analysis.filters.length > 0) {
    addQuestion(questions, {
      id: "single-left-join-filter",
      question: "LEFT JOIN 이후 WHERE 조건이 일치하지 않는 행을 제거해 사실상 INNER JOIN처럼 작동하지 않는지 확인했나요?",
      reason: "LEFT JOIN과 WHERE 조건이 함께 추출되었습니다.",
      target: { type: "join" },
    });
  }

  if (analysis.aggregations.length > 0 || analysis.groupBy.length > 0) {
    addQuestion(questions, {
      id: "single-aggregation-grain",
      question: "집계 전에 조인으로 행이 증가하지 않았고, GROUP BY 기준이 의도한 분석 단위와 일치하나요?",
      reason: "집계 또는 GROUP BY 구조가 추출되었습니다.",
      target: { type: "column" },
    });
  }

  if (analysis.ctes.length > 0 || analysis.subqueries.length > 0) {
    addQuestion(questions, {
      id: "single-intermediate-grain",
      question: "CTE 또는 서브쿼리의 중간 결과 행 단위가 최종 조회·집계 단위와 일치하나요?",
      reason: "중간 결과를 만드는 구조가 추출되었습니다.",
      target: { type: "sql" },
    });
  }

  if (analysis.joins.length > 0 && firstRelation) {
    addQuestion(questions, {
      id: "single-join-key-uniqueness",
      question: `${firstRelation.left}와 ${firstRelation.right}의 조인 키는 각 테이블에서 의도한 관계로 유일한가요?`,
      reason: "조인 관계가 추출되었지만 실제 1:1, 1:N, N:M 여부는 SQL만으로 확정할 수 없습니다.",
      target: { name: `${firstRelation.left} -> ${firstRelation.right}`, type: "join" },
    });
    addQuestion(questions, {
      id: "single-join-row-count",
      question: "조인 전후 행 수가 의도한 수준으로 변하는지 확인했나요?",
      reason: "조인 키의 중복 여부는 조회 결과와 집계값에 영향을 줄 수 있습니다.",
      target: { type: "join" },
    });
  }

  if (hasDateCondition(analysis)) {
    addQuestion(questions, {
      id: "single-date-boundary",
      question: "날짜 조건의 시작·종료 경계와 여러 위치의 기간 기준이 같은 업무 범위를 표현하나요?",
      reason: "날짜 또는 기간으로 보이는 조건이 추출되었습니다.",
      target: { type: "condition" },
    });
  }

  if (primaryRisk?.category === "select_star") {
    addQuestion(questions, {
      id: "single-select-star-consumers",
      question: "이 SQL의 결과를 사용하는 화면·API·배치에서 실제로 필요한 컬럼만 명시할 수 있나요?",
      reason: "SELECT * 사용 신호가 감지되었습니다.",
      target: { type: "column" },
    });
  }

  if (primaryRisk?.category === "hardcoded_code_value") {
    addQuestion(questions, {
      id: "single-hardcoded-definition",
      question: "직접 작성된 코드값이 공통 코드나 업무 규칙과 같은 정의를 사용하나요?",
      reason: "하드코딩된 코드값 신호가 감지되었습니다.",
      target: { type: "condition" },
    });
  }

  if (primaryRisk?.category === "personal_info_condition") {
    addQuestion(questions, {
      id: "single-personal-information-handling",
      question: "개인정보로 추정되는 조건이 로그·문서·AI 보강 범위에 노출되지 않도록 처리되어 있나요?",
      reason: "개인정보 조건 사용 가능성 신호가 감지되었습니다.",
      target: { type: "condition" },
    });
  }

  if (questions.length === 0 && analysis.filters.length > 0) {
    addQuestion(questions, {
      id: "single-filter-scope",
      question: "WHERE 조건이 실제 업무 대상 범위를 의도대로 제한하나요?",
      reason: "조회 범위를 제한하는 조건이 추출되었습니다.",
      target: { type: "condition" },
    });
  }

  if (questions.length === 0) {
    addQuestion(questions, {
      id: "single-result-use",
      question: "이 조회 결과를 사용하는 화면·배치·보고서의 기대 범위가 현재 SQL 구조와 일치하나요?",
      reason: "구조상 추가 위험 신호는 뚜렷하지 않아 결과 사용처와 조회 목적의 일치를 확인하는 것이 자연스럽습니다.",
      target: { type: "sql" },
    });
  }

  return questions;
};

export const buildSingleSqlNarrative = (
  sql: string,
  analysis: SqlAnalysisResult,
): DiagnosticNarrative => {
  const riskAnalysis = buildSingleRiskAnalysis(sql, analysis);
  const primaryRisk = riskAnalysis.findings[0];
  const keyFindings: DiagnosticNarrativeFinding[] = [
    {
      evidence: [analysis.businessIntent.type, ...analysis.businessIntent.reasons],
      id: "single-purpose",
      label: "SQL 목적",
      severity: "info",
      statement: analysis.summary,
    },
    primarySingleStructure(sql, analysis),
    primaryRisk
      ? {
          evidence: [primaryRisk.evidence, primaryRisk.recommendation],
          id: `single-risk-${primaryRisk.id}`,
          label: "우선 확인 리스크",
          severity: riskSeverity(primaryRisk.severity),
          statement: `${primaryRisk.message} 우선 확인: ${primaryRisk.recommendation}`,
          target: { id: primaryRisk.id, type: "sql" },
        }
      : {
          evidence: ["룰 기반 리스크 finding 없음"],
          id: "single-risk-none",
          label: "우선 확인 리스크",
          severity: "info",
          statement: "현재 파서와 룰 기준으로 우선 확인이 필요한 명확한 구조 위험은 발견되지 않았습니다.",
        },
  ];

  return {
    keyFindings: keyFindings.slice(0, MAX_KEY_FINDINGS),
    nextQuestions: buildSingleQuestions(sql, analysis, primaryRisk),
    priorityTargets: [],
    soWhat: buildSingleSoWhat(sql, analysis, primaryRisk),
    title: "SQL 핵심 결과",
  };
};

const riskWeight = (severity: SqlRiskFinding["severity"]) => {
  if (severity === "critical") {
    return 8;
  }

  if (severity === "high") {
    return 6;
  }

  if (severity === "medium") {
    return 3;
  }

  return 1;
};

type StatementPriority = {
  reasons: string[];
  riskFindings: SqlRiskFinding[];
  score: number;
  statement: MultiSqlStatement;
};

const buildStatementPriorities = (
  multiAnalysis: MultiSqlAnalysisResult,
  riskAnalysis: SqlRiskAnalysisResult,
) => {
  const risksByStatement = new Map<string, SqlRiskFinding[]>();

  riskAnalysis.findings.forEach((finding) => {
    const findings = risksByStatement.get(finding.statementId) ?? [];
    findings.push(finding);
    risksByStatement.set(finding.statementId, findings);
  });

  return multiAnalysis.statements
    .map((statement) => {
      const analysis = statement.analysis;
      const riskFindings = risksByStatement.get(statement.id) ?? [];
      const operation = writeOperation(statement.sql);
      const reasons = unique([
        ...(analysis && analysis.tables.length > 0 ? [`테이블 ${analysis.tables.length}개 참조`] : []),
        ...(analysis && analysis.joins.length > 0 ? [`JOIN ${analysis.joins.length}개`] : []),
        ...(analysis && analysis.ctes.length > 0 ? [`CTE ${analysis.ctes.length}개`] : []),
        ...(analysis && analysis.subqueries.length > 0 ? [`서브쿼리 ${analysis.subqueries.length}개`] : []),
        ...(operation ? [`${operation} 작업`] : []),
        ...(riskFindings.length > 0 ? [`리스크 신호 ${riskFindings.length}개`] : []),
      ]);
      const score =
        (analysis?.tables.length ?? 0) * 3 +
        (analysis?.joins.length ?? 0) * 2 +
        (analysis?.ctes.length ?? 0) * 2 +
        (analysis?.subqueries.length ?? 0) * 2 +
        (analysis?.aggregations.length ?? 0) +
        (operation ? 4 : 0) +
        riskFindings.reduce((total, finding) => total + riskWeight(finding.severity), 0) +
        statement.warnings.length;

      return {
        reasons,
        riskFindings,
        score,
        statement,
      } satisfies StatementPriority;
    })
    .sort((left, right) => right.score - left.score || left.statement.id.localeCompare(right.statement.id));
};

const primaryMultiSoWhat = (
  coreTable: TableAssetProfile | undefined,
  repeatedCondition: MultiSqlAnalysisResult["conditionUsage"][number] | undefined,
  primaryPriority: StatementPriority | undefined,
) => {
  if (coreTable && coreTable.usageCount > 1) {
    return {
      rationale: `${coreTable.tableName} 참조 집중`,
      statement: `${coreTable.tableName} 테이블의 스키마나 주요 컬럼 변경은 ${coreTable.usageCount}개 SQL에 영향을 줄 수 있어, 개별 SQL 수보다 이 테이블의 변경 영향 범위를 먼저 확인하는 것이 중요합니다.`,
    };
  }

  if (repeatedCondition && repeatedCondition.count > 1) {
    return {
      rationale: "반복 조건 패턴",
      statement: "같은 조건이 여러 SQL에서 반복되면 업무 정의가 분산될 수 있어, 조건별 표현 차이보다 동일한 기준을 사용하는지 먼저 확인하는 것이 중요합니다.",
    };
  }

  if (primaryPriority) {
    return {
      rationale: `${primaryPriority.statement.id} 구조 집중`,
      statement: "복잡한 구조와 리스크 신호가 일부 SQL에 집중되면 전체 자산을 동시에 검토하기보다, 우선순위가 높은 SQL의 정확성과 영향 범위를 먼저 확인하는 편이 효율적입니다.",
    };
  }

  return {
    statement: "현재 자산은 반복 의존성이나 리스크 신호가 충분히 드러나지 않아, 실제 사용처와 변경 이력을 함께 확인해야 우선순위를 더 구체화할 수 있습니다.",
  };
};

const buildMultiQuestions = (
  multiAnalysis: MultiSqlAnalysisResult,
  coreTable: TableAssetProfile | undefined,
  repeatedCondition: MultiSqlAnalysisResult["conditionUsage"][number] | undefined,
  primaryPriority: StatementPriority | undefined,
  riskAnalysis: SqlRiskAnalysisResult,
) => {
  const questions: DiagnosticNarrativeQuestion[] = [];

  if (coreTable && coreTable.usageCount > 0) {
    addQuestion(questions, {
      id: "multi-core-table-impact",
      question: `${coreTable.tableName} 테이블 구조가 변경되면 영향을 받는 SQL은 무엇인가요?`,
      reason: `${coreTable.usageCount}개 SQL이 이 테이블을 참조합니다.`,
      target: { id: coreTable.key, name: coreTable.tableName, type: "table" },
    });
  }

  if (repeatedCondition && repeatedCondition.count > 1) {
    addQuestion(questions, {
      id: "multi-repeated-condition-definition",
      question: `반복되는 조건 "${repeatedCondition.normalizedCondition}"은 같은 업무 기준을 표현하나요?`,
      reason: `${repeatedCondition.count}개 SQL에서 같은 정규화 조건 패턴이 추출되었습니다.`,
      target: { name: repeatedCondition.normalizedCondition, type: "condition" },
    });
  }

  const writePriority = multiAnalysis.statements.find((statement) => Boolean(writeOperation(statement.sql)));

  if (writePriority) {
    addQuestion(questions, {
      id: "multi-write-order",
      question: `${writePriority.id}와 같은 쓰기 SQL의 실행 순서, 대상 범위, 롤백 방법이 문서화되어 있나요?`,
      reason: "데이터 변경 SQL이 추출되었습니다.",
      target: { id: writePriority.id, name: writePriority.id, type: "sql" },
    });
  }

  if (primaryPriority && primaryPriority.statement.analysis?.joins.length) {
    addQuestion(questions, {
      id: "multi-complex-join",
      question: `${primaryPriority.statement.id}의 조인 키와 집계 단위가 실제 업무 핵심 경로와 일치하나요?`,
      reason: "테이블 연결과 구조 복잡도가 상대적으로 높은 SQL로 분류되었습니다.",
      target: { id: primaryPriority.statement.id, name: primaryPriority.statement.id, type: "sql" },
    });
  }

  const concentratedRisk = primaryPriority?.riskFindings[0] ?? riskAnalysis.findings[0];

  if (concentratedRisk) {
    addQuestion(questions, {
      id: "multi-risk-concentration",
      question: `위험 신호가 있는 ${concentratedRisk.statementId}부터 근거와 영향 범위를 검토할 수 있나요?`,
      reason: `${concentratedRisk.title} 신호가 해당 SQL에서 추출되었습니다.`,
      target: { id: concentratedRisk.statementId, name: concentratedRisk.statementId, type: "sql" },
    });
  }

  if (questions.length === 0 && multiAnalysis.tableUsage.length > 0) {
    const table = multiAnalysis.tableUsage[0];
    addQuestion(questions, {
      id: "multi-table-usage",
      question: `${table.tableName} 테이블을 참조하는 SQL이 같은 업무 경계를 공유하나요?`,
      reason: "자산에서 반복 참조되는 테이블이 추출되었습니다.",
      target: { name: table.tableName, type: "table" },
    });
  }

  return questions;
};

export const buildMultiSqlNarrative = (
  multiAnalysis: MultiSqlAnalysisResult,
  tableAssetMap: TableAssetMap,
  riskAnalysis: SqlRiskAnalysisResult,
): DiagnosticNarrative => {
  const priorities = buildStatementPriorities(multiAnalysis, riskAnalysis);
  const primaryPriority = priorities[0];
  const coreTable = tableAssetMap.tables[0];
  const repeatedCondition = multiAnalysis.conditionUsage.find((condition) => condition.count > 1);
  const keyFindings: DiagnosticNarrativeFinding[] = [];

  if (coreTable) {
    keyFindings.push({
      evidence: [`참조 SQL ${coreTable.usageCount}개`, `JOIN 대상 ${coreTable.joinTargets.length}개`],
      id: `multi-core-table-${coreTable.key}`,
      label: "핵심 의존 테이블",
      severity: coreTable.importance === "high" ? "warning" : "notice",
      statement: `전체 ${multiAnalysis.statements.length}개 SQL 중 ${coreTable.usageCount}개가 ${coreTable.tableName} 테이블을 참조합니다.`,
      target: { id: coreTable.key, name: coreTable.tableName, type: "table" },
    });
  } else {
    keyFindings.push({
      evidence: [`분석 SQL ${multiAnalysis.statements.length}개`],
      id: "multi-no-table",
      label: "자산 범위",
      severity: "info",
      statement: `전체 ${multiAnalysis.statements.length}개 SQL에서 반복 참조되는 테이블을 찾지 못했습니다.`,
    });
  }

  if (primaryPriority) {
    const analysis = primaryPriority.statement.analysis;
    const structuralSummary = analysis
      ? `${analysis.tables.length}개 테이블, JOIN ${analysis.joins.length}개${analysis.ctes.length > 0 ? `, CTE ${analysis.ctes.length}개` : ""}${analysis.subqueries.length > 0 ? `, 서브쿼리 ${analysis.subqueries.length}개` : ""}`
      : "구조 추출 실패";

    keyFindings.push({
      evidence: primaryPriority.reasons,
      id: `multi-priority-sql-${primaryPriority.statement.id}`,
      label: "우선 확인 SQL",
      severity: primaryPriority.riskFindings.length > 0 ? riskSeverity(primaryPriority.riskFindings[0].severity) : "notice",
      statement: `${primaryPriority.statement.id}은 ${structuralSummary}로, 현재 자산에서 상대적으로 먼저 검토할 구조입니다.`,
      target: { id: primaryPriority.statement.id, name: primaryPriority.statement.id, type: "sql" },
    });
  }

  if (repeatedCondition) {
    keyFindings.push({
      evidence: [`반복 SQL ${repeatedCondition.count}개`, `대상 ${repeatedCondition.statementIds.join(", ")}`],
      id: `multi-condition-${repeatedCondition.normalizedCondition}`,
      label: "반복 조건 패턴",
      severity: "notice",
      statement: `조건 패턴 "${repeatedCondition.normalizedCondition}"이 ${repeatedCondition.count}개 SQL에서 반복됩니다.`,
      target: { name: repeatedCondition.normalizedCondition, type: "condition" },
    });
  } else if (riskAnalysis.findings.length > 0) {
    const risk = riskAnalysis.findings[0];
    const riskCount = riskAnalysis.findings.filter((finding) => finding.statementId === risk.statementId).length;

    keyFindings.push({
      evidence: [risk.evidence, risk.recommendation],
      id: `multi-risk-${risk.id}`,
      label: "리스크 집중",
      severity: riskSeverity(risk.severity),
      statement: `${risk.statementId}에 ${riskCount}개의 리스크 신호가 있으며, ${risk.title}부터 확인할 필요가 있습니다.`,
      target: { id: risk.statementId, name: risk.statementId, type: "sql" },
    });
  } else {
    keyFindings.push({
      evidence: ["반복 조건 및 리스크 집중 없음"],
      id: "multi-risk-none",
      label: "구조 위험 신호",
      severity: "info",
      statement: "현재 룰 기준에서 특정 SQL에 집중된 명확한 구조 위험 신호는 발견되지 않았습니다.",
    });
  }

  const priorityTargets: DiagnosticNarrativePriorityTarget[] = [];

  if (coreTable) {
    priorityTargets.push({
      id: `priority-table-${coreTable.key}`,
      label: coreTable.tableName,
      reasons: [
        `${coreTable.usageCount}개 SQL이 참조`,
        `JOIN 대상 ${coreTable.joinTargets.length}개`,
        ...(coreTable.isInsertTarget ? ["적재 대상 테이블"] : []),
      ],
      severity: coreTable.importance === "high" ? "warning" : "notice",
      target: { id: coreTable.key, name: coreTable.tableName, type: "table" },
    });
  }

  if (primaryPriority) {
    priorityTargets.push({
      id: `priority-sql-${primaryPriority.statement.id}`,
      label: `${primaryPriority.statement.id} · ${primaryPriority.statement.analysis?.summary ?? "분석 실패 SQL"}`,
      reasons: primaryPriority.reasons.length > 0 ? primaryPriority.reasons : ["구조 추출 실패 여부 확인 필요"],
      severity: primaryPriority.riskFindings.length > 0 ? riskSeverity(primaryPriority.riskFindings[0].severity) : "notice",
      target: { id: primaryPriority.statement.id, name: primaryPriority.statement.id, type: "sql" },
    });
  }

  if (repeatedCondition) {
    priorityTargets.push({
      id: `priority-condition-${repeatedCondition.normalizedCondition}`,
      label: repeatedCondition.normalizedCondition,
      reasons: [`${repeatedCondition.count}개 SQL에서 반복`, `SQL ${repeatedCondition.statementIds.join(", ")}`],
      severity: "notice",
      target: { name: repeatedCondition.normalizedCondition, type: "condition" },
    });
  }

  return {
    keyFindings: keyFindings.slice(0, MAX_KEY_FINDINGS),
    nextQuestions: buildMultiQuestions(
      multiAnalysis,
      coreTable,
      repeatedCondition,
      primaryPriority,
      riskAnalysis,
    ),
    priorityTargets: priorityTargets
      .sort((left, right) => severityRank[left.severity] - severityRank[right.severity] || left.label.localeCompare(right.label))
      .slice(0, MAX_PRIORITY_TARGETS),
    soWhat: primaryMultiSoWhat(coreTable, repeatedCondition, primaryPriority),
    title: "자산 지도 핵심 결과",
  };
};
