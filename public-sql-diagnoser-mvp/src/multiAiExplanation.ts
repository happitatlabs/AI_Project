import type { AiSqlExplanationAnalysisInput } from "./aiExplanation.js";
import type { MultiSqlAnalysisResult } from "./multiSqlAnalysis.js";
import type { SqlRiskAnalysisResult } from "./riskDetector.js";
import type {
  AggregationAnalysis,
  BusinessIntentType,
  CaseExpressionAnalysis,
  CteAnalysis,
  DerivedColumnAnalysis,
  GroupByAnalysis,
  SqlAnalysisResult,
  StageFilter,
  WindowFunctionAnalysis,
} from "./sqlExplainer.js";

const unique = <T>(values: T[]) => Array.from(new Set(values));

const flattenAnalysisItems = <T>(
  multiAnalysis: MultiSqlAnalysisResult,
  getItems: (analysis: SqlAnalysisResult) => T[],
  annotate: (item: T, statementId: string) => T,
) =>
  multiAnalysis.statements.flatMap((statement) =>
    statement.analysis
      ? getItems(statement.analysis).map((item) => annotate(item, statement.id))
      : [],
  );

const countSuccessfulStatements = (multiAnalysis: MultiSqlAnalysisResult) =>
  multiAnalysis.statements.filter((statement) => statement.analysis).length;

const buildMultiConfidence = (
  multiAnalysis: MultiSqlAnalysisResult,
): SqlAnalysisResult["confidence"] => {
  const analyses = multiAnalysis.statements
    .map((statement) => statement.analysis)
    .filter((analysis): analysis is SqlAnalysisResult => Boolean(analysis));
  const averageScore =
    analyses.length > 0
      ? analyses.reduce((sum, analysis) => sum + analysis.confidence.score, 0) / analyses.length
      : 0.25;
  const scorePenalty = Math.min(0.2, multiAnalysis.warnings.length * 0.03);
  const score = Math.max(0.1, Math.round((averageScore - scorePenalty) * 100) / 100);
  const level: SqlAnalysisResult["confidence"]["level"] =
    score >= 0.72 && multiAnalysis.warnings.length <= 2
      ? "high"
      : score >= 0.45
        ? "medium"
        : "low";

  return {
    level,
    reasons: [
      `분석 SQL ${multiAnalysis.statements.length}개 중 ${countSuccessfulStatements(multiAnalysis)}개가 구조화되었습니다.`,
      `테이블 ${multiAnalysis.tableUsage.length}개, JOIN ${multiAnalysis.joinUsage.length}개, 조건 패턴 ${multiAnalysis.conditionUsage.length}개가 집계되었습니다.`,
      ...(multiAnalysis.warnings.length > 0
        ? [`다건 분석 warning ${multiAnalysis.warnings.length}개가 있어 일부 해석은 추정입니다.`]
        : ["다건 분석 warning이 없어 구조 추출 신뢰도가 높습니다."]),
    ],
    score,
  };
};

const dominantBusinessIntent = (
  businessIntentSummary: MultiSqlAnalysisResult["businessIntentSummary"],
): BusinessIntentType => {
  const [dominantType] =
    Object.entries(businessIntentSummary)
      .sort(([leftType, leftCount], [rightType, rightCount]) =>
        rightCount === leftCount
          ? leftType.localeCompare(rightType)
          : rightCount - leftCount,
      )[0] ?? [];

  return (dominantType as BusinessIntentType | undefined) ?? "list_query";
};

const buildMultiBusinessIntent = (
  multiAnalysis: MultiSqlAnalysisResult,
): SqlAnalysisResult["businessIntent"] => {
  const intentEntries = Object.entries(multiAnalysis.businessIntentSummary)
    .sort(([leftType, leftCount], [rightType, rightCount]) =>
      rightCount === leftCount
        ? leftType.localeCompare(rightType)
        : rightCount - leftCount,
    );
  const distribution = intentEntries
    .map(([type, count]) => `${type} ${count}개`)
    .join(", ");

  return {
    confidence: Math.min(0.85, 0.55 + intentEntries.length * 0.07),
    reasons: distribution
      ? [`다건 SQL 업무 목적 분포: ${distribution}`]
      : ["업무 목적 분포가 없어 일반 조회 계열로 추정했습니다."],
    type: dominantBusinessIntent(multiAnalysis.businessIntentSummary),
  };
};

export const buildMultiSqlAiAnalysis = (
  multiAnalysis: MultiSqlAnalysisResult,
  riskAnalysis: SqlRiskAnalysisResult,
): AiSqlExplanationAnalysisInput => {
  const statementSummaries = multiAnalysis.statements.map((statement) => ({
    businessIntent: statement.analysis?.businessIntent.type ?? "unknown",
    confidenceLevel: statement.analysis?.confidence.level ?? "unknown",
    id: statement.id,
    summary: statement.analysis?.summary ?? statement.error ?? "분석 결과 없음",
    tableNames: statement.analysis?.tables.map((table) => table.tableName) ?? [],
    warningCount: statement.warnings.length + (statement.analysis?.warnings.length ?? 0),
  }));

  return {
    aggregations: flattenAnalysisItems<AggregationAnalysis>(
      multiAnalysis,
      (analysis) => analysis.aggregations,
      (aggregation, statementId) => ({
        ...aggregation,
        stage: `${statementId} / ${aggregation.stage}`,
      }),
    ),
    businessIntent: buildMultiBusinessIntent(multiAnalysis),
    caseExpressions: flattenAnalysisItems<CaseExpressionAnalysis>(
      multiAnalysis,
      (analysis) => analysis.caseExpressions,
      (caseExpression, statementId) => ({
        ...caseExpression,
        stage: `${statementId} / ${caseExpression.stage}`,
      }),
    ),
    confidence: buildMultiConfidence(multiAnalysis),
    ctes: flattenAnalysisItems<CteAnalysis>(
      multiAnalysis,
      (analysis) => analysis.ctes,
      (cte, statementId) => ({
        ...cte,
        name: `${statementId}:${cte.name}`,
      }),
    ),
    derivedColumns: flattenAnalysisItems<DerivedColumnAnalysis>(
      multiAnalysis,
      (analysis) => analysis.derivedColumns,
      (column, statementId) => ({
        ...column,
        stage: `${statementId} / ${column.stage}`,
      }),
    ),
    filters: multiAnalysis.conditionUsage.map<StageFilter>((condition) => ({
      condition: condition.normalizedCondition,
      description: `${condition.count}개 SQL에서 반복 사용된 WHERE/HAVING 조건 패턴으로 추정됩니다.`,
      stage: `다건 조건 / ${condition.statementIds.join(", ")}`,
    })),
    groupBy: flattenAnalysisItems<GroupByAnalysis>(
      multiAnalysis,
      (analysis) => analysis.groupBy,
      (groupBy, statementId) => ({
        ...groupBy,
        stage: `${statementId} / ${groupBy.stage}`,
      }),
    ),
    havingConditions: flattenAnalysisItems<StageFilter>(
      multiAnalysis,
      (analysis) => analysis.havingConditions,
      (condition, statementId) => ({
        ...condition,
        stage: `${statementId} / ${condition.stage}`,
      }),
    ),
    joins: multiAnalysis.joinUsage.map((join) => ({
      explanation: `${join.count}개 SQL에서 반복되는 JOIN 관계입니다.`,
      joinType: join.joinTypes.join(", ") || undefined,
      left: join.left,
      raw: `${join.left} -> ${join.right}`,
      right: join.right,
      rightTable: join.right,
    })),
    multiSqlContext: {
      businessIntentSummary: multiAnalysis.businessIntentSummary,
      conditionUsage: multiAnalysis.conditionUsage.slice(0, 30),
      failedSql: multiAnalysis.statements.length - countSuccessfulStatements(multiAnalysis),
      riskFindings: riskAnalysis.findings.slice(0, 30).map((finding) => ({
        category: finding.category,
        evidence: finding.evidence,
        id: finding.id,
        recommendation: finding.recommendation,
        severity: finding.severity,
        statementId: finding.statementId,
        title: finding.title,
      })),
      riskSummary: riskAnalysis.summary,
      statementCount: multiAnalysis.statements.length,
      statementSummaries,
      successfulSql: countSuccessfulStatements(multiAnalysis),
      topJoinUsage: multiAnalysis.joinUsage.slice(0, 30),
      topTableUsage: multiAnalysis.tableUsage.slice(0, 30),
      warnings: multiAnalysis.warnings,
    },
    setOperations: flattenAnalysisItems(
      multiAnalysis,
      (analysis) => analysis.setOperations,
      (operation, statementId) => ({
        ...operation,
        description: `${statementId}: ${operation.description}`,
      }),
    ),
    subqueries: flattenAnalysisItems(
      multiAnalysis,
      (analysis) => analysis.subqueries,
      (subquery, statementId) => ({
        ...subquery,
        stage: `${statementId} / ${subquery.stage}`,
      }),
    ),
    tables: multiAnalysis.tableUsage.map((table) => ({
      category: "multi_sql_usage",
      description: `${table.count}개 SQL에서 사용되었습니다. 업무 의미는 SQL 사용 패턴 기반 추정입니다.`,
      entityLabel: table.tableName,
      rawName: table.rawNames[0] ?? table.tableName,
      schemaName: table.schemaNames[0],
      source: "main",
      tableName: table.tableName,
    })),
    warnings: unique([
      ...multiAnalysis.warnings,
      "다건 AI 설명은 여러 SQL의 구조화 분석 결과를 요약한 보강 설명입니다.",
      "개별 SQL의 세부 DBMS 방언이나 실행 계획은 별도 확인이 필요합니다.",
    ]),
    windowFunctions: flattenAnalysisItems<WindowFunctionAnalysis>(
      multiAnalysis,
      (analysis) => analysis.windowFunctions,
      (windowFunction, statementId) => ({
        ...windowFunction,
        stage: `${statementId} / ${windowFunction.stage}`,
      }),
    ),
  };
};
