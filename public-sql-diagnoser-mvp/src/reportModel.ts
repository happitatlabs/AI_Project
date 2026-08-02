import type { AiSqlDocumentDraft } from "./aiDocumentDraft.js";
import type { AiSqlExplanation } from "./aiExplanation.js";
import type { AiMultiSqlDocumentDraft } from "./aiMultiDocumentDraft.js";
import type { MultiSqlAnalysisResult } from "./multiSqlAnalysis.js";
import type { SqlRiskAnalysisResult, SqlRiskFinding } from "./riskDetector.js";
import type { SystemGraph } from "./systemGraph.js";
import type { TableAssetMap } from "./tableAssetMap.js";

export type ReportOptions = {
  includeAiDocumentDraft: boolean;
  includeAiExplanation: boolean;
  includeSystemGraph: boolean;
  includeTableAssetMap: boolean;
  includeWarnings: boolean;
  includeRawSql: boolean;
};

export type ReportSummary = {
  totalSql: number;
  successfulSql: number;
  failedSql: number;
  tableCount: number;
  joinCount: number;
  conditionPatternCount: number;
  cteCount: number;
  viewCount: number;
  procedureCount: number;
  warningCount: number;
  confidence: {
    high: number;
    medium: number;
    low: number;
  };
};

export type SqlReportItem = {
  id: string;
  summary: string;
  businessIntent: string;
  confidenceLevel: "low" | "medium" | "high" | "unknown";
  tableNames: string[];
  joinCount: number;
  cteCount: number;
  warningCount: number;
  hasInsertSelect: boolean;
  hasProcedure: boolean;
  hasSubqueries: boolean;
  hasSetOperations: boolean;
  hasWhere: boolean;
  warnings: string[];
  rawSql?: string;
};

export type TableReportItem = {
  tableName: string;
  usageCount: number;
  importance: string;
  importanceScore: number;
  joinTargets: string[];
  conditionPatterns: string[];
  businessGuesses: string[];
  isInsertTarget: boolean;
};

export type JoinReportItem = {
  left: string;
  right: string;
  count: number;
  joinTypes: string[];
  statementIds: string[];
};

export type BusinessIntentReportItem = {
  type: string;
  count: number;
};

export type RiskLevel = "high" | "medium" | "low";

export type RiskSqlReportItem = {
  id: string;
  summary: string;
  riskLevel: RiskLevel;
  score: number;
  reasons: string[];
  checkPoints: string[];
};

export type SystemGraphReportItem = {
  from: string;
  to: string;
  type: string;
  label: string;
  statementIds: string[];
};

export type AiDocumentDraftReportItem = AiSqlDocumentDraft | AiMultiSqlDocumentDraft;

export type SqlExplainerReport = {
  title: string;
  generatedAt: string;
  options: ReportOptions;
  summary: ReportSummary;
  executiveSummary: string[];
  sqlSummaries: SqlReportItem[];
  tables: TableReportItem[];
  joins: JoinReportItem[];
  businessIntents: BusinessIntentReportItem[];
  riskSqls: RiskSqlReportItem[];
  systemGraph: SystemGraphReportItem[];
  riskFindings: SqlRiskFinding[];
  riskFindingSummary: SqlRiskAnalysisResult["summary"];
  juniorDeveloperGuide: string[];
  aiDocumentDraft?: AiDocumentDraftReportItem;
  aiExplanation?: AiSqlExplanation;
  warnings: string[];
};

export const defaultReportOptions: ReportOptions = {
  includeAiDocumentDraft: false,
  includeAiExplanation: false,
  includeRawSql: false,
  includeSystemGraph: true,
  includeTableAssetMap: true,
  includeWarnings: true,
};

const unique = <T>(values: T[]) => Array.from(new Set(values));

const compactSql = (sql: string) => sql.replace(/\s+/g, " ").trim();

const hasInsertSelect = (sql: string) =>
  /\bINSERT\s+INTO\b[\s\S]*\bSELECT\b/i.test(sql);

const hasProcedure = (sql: string) =>
  /\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|PACKAGE(?:\s+BODY)?)\b/i.test(sql);

const hasWhere = (sql: string) => /\bWHERE\b/i.test(sql);

const riskLevelFromScore = (score: number): RiskLevel => {
  if (score >= 60) {
    return "high";
  }

  if (score >= 30) {
    return "medium";
  }

  return "low";
};

const buildSqlReportItems = (
  multiAnalysis: MultiSqlAnalysisResult,
  options: ReportOptions,
): SqlReportItem[] =>
  multiAnalysis.statements.map((statement) => {
    const analysis = statement.analysis;
    const statementWarnings = unique([
      ...statement.warnings,
      ...(analysis?.warnings ?? []),
    ]);

    return {
      businessIntent: analysis?.businessIntent.type ?? "unknown",
      confidenceLevel: analysis?.confidence.level ?? "unknown",
      cteCount: analysis?.ctes.length ?? 0,
      hasInsertSelect: hasInsertSelect(statement.sql),
      hasProcedure: hasProcedure(statement.sql),
      hasSetOperations: (analysis?.setOperations.length ?? 0) > 0,
      hasSubqueries: (analysis?.subqueries.length ?? 0) > 0,
      hasWhere: hasWhere(statement.sql),
      id: statement.id,
      joinCount: analysis?.joins.length ?? 0,
      rawSql: options.includeRawSql ? statement.sql : undefined,
      summary: analysis?.summary ?? statement.error ?? "분석 결과 없음",
      tableNames: unique(analysis?.tables.map((table) => table.tableName) ?? []),
      warningCount: statementWarnings.length,
      warnings: statementWarnings,
    };
  });

const buildRiskSqlItems = (sqlSummaries: SqlReportItem[]): RiskSqlReportItem[] =>
  sqlSummaries
    .map((item) => {
      let score = 0;
      const reasons: string[] = [];
      const checkPoints: string[] = [];

      if (item.confidenceLevel === "low" || item.confidenceLevel === "unknown") {
        score += 30;
        reasons.push("분석 신뢰도가 낮거나 분석 실패 상태입니다.");
        checkPoints.push("파서가 놓친 테이블, 조건, DBMS 특화 문법을 수동 확인합니다.");
      } else if (item.confidenceLevel === "medium") {
        score += 10;
        reasons.push("분석 신뢰도가 중간 수준입니다.");
      }

      if (item.warningCount >= 3) {
        score += 20;
        reasons.push(`warnings가 ${item.warningCount}개 있습니다.`);
      } else if (item.warningCount > 0) {
        score += 10;
        reasons.push("warnings가 있어 해석상 주의가 필요합니다.");
      }

      if (item.hasInsertSelect) {
        score += 20;
        reasons.push("INSERT INTO SELECT 적재 SQL입니다.");
        checkPoints.push("대상 테이블, 적재 기간, 중복 적재 가능성을 확인합니다.");
      }

      if (item.hasProcedure) {
        score += 20;
        reasons.push("Procedure/Function/Package 정의가 포함되어 부분 분석 대상입니다.");
        checkPoints.push("동적 SQL, 트랜잭션, 스케줄러 호출 여부를 확인합니다.");
      }

      if (item.joinCount >= 5) {
        score += 15;
        reasons.push(`JOIN 관계가 ${item.joinCount}개로 많습니다.`);
        checkPoints.push("JOIN 키와 기준 테이블이 업무 규칙과 맞는지 확인합니다.");
      }

      if (item.tableNames.length >= 5) {
        score += 15;
        reasons.push(`사용 테이블이 ${item.tableNames.length}개로 많습니다.`);
      }

      if (item.hasSubqueries) {
        score += 10;
        reasons.push("서브쿼리가 포함되어 일부 내부 조건이 단순화될 수 있습니다.");
      }

      if (item.hasSetOperations) {
        score += 10;
        reasons.push("UNION/EXCEPT/INTERSECT 계열 SET 연산이 포함되어 있습니다.");
      }

      if (!item.hasWhere && item.tableNames.length > 0) {
        score += 10;
        reasons.push("WHERE 조건이 없어 대량 조회 가능성이 있습니다.");
        checkPoints.push("운영 환경에서 실행 범위와 인덱스 사용 여부를 확인합니다.");
      }

      if (item.cteCount >= 3) {
        score += 10;
        reasons.push(`CTE 단계가 ${item.cteCount}개로 많습니다.`);
      }

      return {
        checkPoints: checkPoints.length > 0 ? unique(checkPoints) : ["업무 담당자와 실행 목적을 확인합니다."],
        id: item.id,
        reasons: reasons.length > 0 ? unique(reasons) : ["별도 위험 신호가 낮습니다."],
        riskLevel: riskLevelFromScore(score),
        score,
        summary: item.summary,
      };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }

      return left.id.localeCompare(right.id);
    });

const confidenceSummary = (sqlSummaries: SqlReportItem[]) => ({
  high: sqlSummaries.filter((item) => item.confidenceLevel === "high").length,
  low: sqlSummaries.filter((item) => item.confidenceLevel === "low" || item.confidenceLevel === "unknown").length,
  medium: sqlSummaries.filter((item) => item.confidenceLevel === "medium").length,
});

const buildTableReportItems = (tableAssetMap: TableAssetMap): TableReportItem[] =>
  tableAssetMap.tables.map((table) => ({
    businessGuesses: table.businessGuesses,
    conditionPatterns: table.conditions.slice(0, 5).map((condition) => condition.normalizedCondition),
    importance: table.importance,
    importanceScore: table.importanceScore,
    isInsertTarget: table.isInsertTarget,
    joinTargets: table.joinTargets.map((joinTarget) => joinTarget.tableName),
    tableName: table.tableName,
    usageCount: table.usageCount,
  }));

const buildSystemGraphReportItems = (systemGraph: SystemGraph): SystemGraphReportItem[] => {
  const nodeMap = new Map(systemGraph.nodes.map((node) => [node.id, node]));

  return systemGraph.edges.slice(0, 80).map((edge) => ({
    from: nodeMap.get(edge.from)?.label ?? edge.from,
    label: edge.label,
    statementIds: edge.sourceStatementIds,
    to: nodeMap.get(edge.to)?.label ?? edge.to,
    type: edge.type,
  }));
};

const buildExecutiveSummary = (
  summary: ReportSummary,
  tableAssetMap: TableAssetMap,
  riskSqls: RiskSqlReportItem[],
  systemGraph: SystemGraph,
) => {
  const coreTables = tableAssetMap.coreTables.slice(0, 5).map((table) => table.tableName);
  const highRiskSqls = riskSqls.filter((risk) => risk.riskLevel === "high");
  const loadEdges = systemGraph.edges.filter((edge) => edge.type === "transforms_to");

  return [
    `${summary.totalSql}개 SQL에서 ${summary.tableCount}개 테이블과 ${summary.joinCount}개 JOIN 관계를 추출했습니다.`,
    coreTables.length > 0
      ? `핵심 테이블 후보는 ${coreTables.join(", ")}입니다.`
      : "반복 사용 패턴이 충분한 핵심 테이블 후보는 아직 없습니다.",
    loadEdges.length > 0
      ? `${loadEdges.length}개의 INSERT/View 기반 적재 또는 변환 흐름을 확인했습니다.`
      : "명확한 적재/변환 흐름은 확인되지 않았습니다.",
    highRiskSqls.length > 0
      ? `높은 위험도로 분류된 SQL은 ${highRiskSqls.map((risk) => risk.id).join(", ")}입니다.`
      : "높은 위험도로 분류된 SQL은 없습니다.",
  ];
};

const buildJuniorDeveloperGuide = (
  tableAssetMap: TableAssetMap,
  riskSqls: RiskSqlReportItem[],
  sqlSummaries: SqlReportItem[],
) => {
  const coreTables = tableAssetMap.coreTables.slice(0, 3).map((table) => table.tableName);
  const firstSqls = sqlSummaries.slice(0, 3).map((sql) => sql.id);
  const batchSqls = sqlSummaries.filter((sql) => sql.hasInsertSelect).map((sql) => sql.id);
  const highRiskSqls = riskSqls.filter((risk) => risk.riskLevel === "high").map((risk) => risk.id);

  return [
    coreTables.length > 0
      ? `먼저 ${coreTables.join(", ")} 테이블의 사용 SQL과 JOIN 대상을 확인합니다.`
      : "먼저 테이블 사용 현황에서 반복 등장하는 테이블을 확인합니다.",
    firstSqls.length > 0
      ? `초기 파악용 SQL은 ${firstSqls.join(", ")} 순서로 읽는 것이 좋습니다.`
      : "분석 가능한 SQL이 없어 원문 SQL 정리가 먼저 필요합니다.",
    batchSqls.length > 0
      ? `${batchSqls.join(", ")}는 적재/배치성 SQL이므로 대상 테이블과 실행 주기를 확인합니다.`
      : "명확한 INSERT INTO SELECT 배치 SQL은 확인되지 않았습니다.",
    highRiskSqls.length > 0
      ? `위험도가 높은 ${highRiskSqls.join(", ")}는 담당자 확인 후 문서화합니다.`
      : "높은 위험도 SQL은 없지만 warnings가 있는 SQL은 수동 검토합니다.",
  ];
};

export const buildSqlExplainerReport = ({
  aiDocumentDraft,
  aiExplanation,
  generatedAt,
  multiAnalysis,
  options = defaultReportOptions,
  riskAnalysis,
  systemGraph,
  tableAssetMap,
  title = "SQL Explainer 분석 보고서",
}: {
  aiDocumentDraft?: AiDocumentDraftReportItem;
  aiExplanation?: AiSqlExplanation;
  generatedAt?: string;
  multiAnalysis: MultiSqlAnalysisResult;
  options?: ReportOptions;
  riskAnalysis?: SqlRiskAnalysisResult;
  systemGraph: SystemGraph;
  tableAssetMap: TableAssetMap;
  title?: string;
}): SqlExplainerReport => {
  const mergedOptions = { ...defaultReportOptions, ...options };
  const sqlSummaries = buildSqlReportItems(multiAnalysis, mergedOptions);
  const riskSqls = buildRiskSqlItems(sqlSummaries);
  const warnings = unique([
    ...(mergedOptions.includeWarnings ? multiAnalysis.warnings : []),
    ...(mergedOptions.includeWarnings ? tableAssetMap.warnings : []),
    ...(mergedOptions.includeWarnings ? systemGraph.warnings : []),
    ...(mergedOptions.includeAiExplanation && !aiExplanation
      ? ["AI 설명 보강 결과가 없어 보고서에 포함하지 않았습니다."]
      : []),
    ...(mergedOptions.includeAiDocumentDraft && !aiDocumentDraft
      ? ["AI 문서 초안 결과가 없어 보고서에 포함하지 않았습니다."]
      : []),
  ]);
  const summary: ReportSummary = {
    conditionPatternCount: multiAnalysis.conditionUsage.length,
    confidence: confidenceSummary(sqlSummaries),
    cteCount: multiAnalysis.statements.reduce(
      (total, statement) => total + (statement.analysis?.ctes.length ?? 0),
      0,
    ),
    failedSql: multiAnalysis.statements.filter((statement) => statement.error).length,
    joinCount: multiAnalysis.joinUsage.length,
    procedureCount: systemGraph.summary.procedureNodeCount,
    successfulSql: multiAnalysis.statements.filter((statement) => statement.analysis).length,
    tableCount: tableAssetMap.summary.tableCount,
    totalSql: multiAnalysis.statements.length,
    viewCount: systemGraph.summary.viewNodeCount,
    warningCount: warnings.length,
  };

  return {
    aiDocumentDraft: mergedOptions.includeAiDocumentDraft ? aiDocumentDraft : undefined,
    aiExplanation: mergedOptions.includeAiExplanation ? aiExplanation : undefined,
    businessIntents: Object.entries(multiAnalysis.businessIntentSummary)
      .map(([type, count]) => ({ count, type }))
      .sort((left, right) => right.count - left.count || left.type.localeCompare(right.type)),
    executiveSummary: buildExecutiveSummary(summary, tableAssetMap, riskSqls, systemGraph),
    generatedAt: generatedAt ?? new Date().toISOString(),
    joins: multiAnalysis.joinUsage.map((join) => ({
      count: join.count,
      joinTypes: join.joinTypes,
      left: join.left,
      right: join.right,
      statementIds: join.statementIds,
    })),
    juniorDeveloperGuide: buildJuniorDeveloperGuide(tableAssetMap, riskSqls, sqlSummaries),
    options: mergedOptions,
    riskFindings: riskAnalysis?.findings ?? [],
    riskFindingSummary: riskAnalysis?.summary ?? {
      critical: 0,
      high: 0,
      low: 0,
      medium: 0,
      total: 0,
    },
    riskSqls,
    sqlSummaries,
    summary,
    systemGraph: mergedOptions.includeSystemGraph ? buildSystemGraphReportItems(systemGraph) : [],
    tables: mergedOptions.includeTableAssetMap ? buildTableReportItems(tableAssetMap) : [],
    title,
    warnings,
  };
};

const riskLevelLabel = (level: RiskLevel) => {
  if (level === "high") {
    return "높음";
  }

  if (level === "medium") {
    return "보통";
  }

  return "낮음";
};

const markdownList = (items: string[], fallback: string) =>
  items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : `- ${fallback}`;

export const buildMarkdownReport = (report: SqlExplainerReport) => {
  const aiSection = report.aiExplanation
    ? [
        "## AI 설명 보강",
        "",
        `- 한 줄 요약: ${report.aiExplanation.summary}`,
        `- 업무 목적: ${report.aiExplanation.businessPurpose}`,
        "",
        "### 신규 개발자용 AI 설명",
        report.aiExplanation.juniorDeveloperExplanation,
        "",
        "### AI 불확실성",
        markdownList(report.aiExplanation.uncertaintyNotes, "별도 불확실성 메모가 없습니다."),
      ].join("\n")
    : "";
  const aiDocumentDraftSection = report.aiDocumentDraft
    ? [
        "## AI 문서 초안",
        "",
        report.aiDocumentDraft.markdown,
      ].join("\n")
    : "";

  return [
    `# ${report.title}`,
    "",
    `- 생성 시각: ${report.generatedAt}`,
    `- 분석 SQL: ${report.summary.totalSql}개`,
    `- 사용 테이블: ${report.summary.tableCount}개`,
    `- JOIN 관계: ${report.summary.joinCount}개`,
    `- CTE: ${report.summary.cteCount}개`,
    `- View 후보: ${report.summary.viewCount}개`,
    `- Procedure 후보: ${report.summary.procedureCount}개`,
    `- Warnings: ${report.summary.warningCount}개`,
    "",
    "## Executive Summary",
    "",
    markdownList(report.executiveSummary, "요약할 내용이 없습니다."),
    "",
    "## 사용 테이블 목록",
    "",
    ...(report.tables.length > 0
      ? report.tables.map(
          (table) =>
            `- ${table.tableName}: 사용 SQL ${table.usageCount}개, 핵심도 ${table.importance}(${table.importanceScore}점), JOIN 대상 ${table.joinTargets.join(", ") || "없음"}, 주요 조건 ${table.conditionPatterns.join(", ") || "없음"}, 업무 추정 ${table.businessGuesses.join(", ") || "없음"}`,
        )
      : ["- 테이블 자산 지도 포함 옵션이 꺼져 있거나 테이블이 없습니다."]),
    "",
    "## 주요 JOIN 관계",
    "",
    ...(report.joins.length > 0
      ? report.joins.map(
          (join) =>
            `- ${join.left} -> ${join.right}: ${join.count}회 / SQL ${join.statementIds.join(", ")}`,
        )
      : ["- JOIN 관계가 없습니다."]),
    "",
    "## SQL별 요약",
    "",
    ...report.sqlSummaries.flatMap((sql) => [
      `### ${sql.id}`,
      `- 설명: ${sql.summary}`,
      `- 업무 목적: ${sql.businessIntent}`,
      `- 신뢰도: ${sql.confidenceLevel}`,
      `- 사용 테이블: ${sql.tableNames.join(", ") || "없음"}`,
      `- JOIN 수: ${sql.joinCount}`,
      `- Warnings: ${sql.warningCount}개`,
      ...(sql.rawSql ? ["", "```sql", sql.rawSql, "```"] : []),
      "",
    ]),
    "## 업무 목적 분류",
    "",
    ...(report.businessIntents.length > 0
      ? report.businessIntents.map((intent) => `- ${intent.type}: ${intent.count}개`)
      : ["- 업무 목적 분류가 없습니다."]),
    "",
    "## 위험 SQL 목록",
    "",
    ...(report.riskSqls.length > 0
      ? report.riskSqls.map(
          (risk) =>
            `- ${risk.id}: 위험도 ${riskLevelLabel(risk.riskLevel)}(${risk.score}점) / ${risk.reasons.join(" ")}`,
        )
      : ["- 위험 신호가 있는 SQL이 없습니다."]),
    "",
    "## 리스크 / 개선 포인트",
    "",
    `- 전체 Finding: ${report.riskFindingSummary.total}개`,
    `- Critical: ${report.riskFindingSummary.critical}개`,
    `- High: ${report.riskFindingSummary.high}개`,
    `- Medium: ${report.riskFindingSummary.medium}개`,
    `- Low: ${report.riskFindingSummary.low}개`,
    "",
    ...(report.riskFindings.length > 0
      ? report.riskFindings.map(
          (finding) =>
            `- ${finding.statementId}: [${finding.severity}] ${finding.title}\n  - 근거: ${finding.evidence}\n  - 개선: ${finding.recommendation}`,
        )
      : ["- 리스크 finding이 없습니다."]),
    "",
    "## 시스템 지도 요약",
    "",
    ...(report.systemGraph.length > 0
      ? report.systemGraph.slice(0, 40).map(
          (edge) =>
            `- ${edge.from} -> ${edge.to}: ${edge.type} / ${edge.label} / SQL ${edge.statementIds.join(", ")}`,
        )
      : ["- 시스템 지도 포함 옵션이 꺼져 있거나 관계가 없습니다."]),
    "",
    "## 신규 개발자 설명",
    "",
    markdownList(report.juniorDeveloperGuide, "신규 개발자 안내를 만들 근거가 부족합니다."),
    "",
    ...(aiSection ? [aiSection, ""] : []),
    ...(aiDocumentDraftSection ? [aiDocumentDraftSection, ""] : []),
    "## 주의 사항",
    "",
    markdownList(report.warnings, "별도 주의 사항이 없습니다."),
  ].join("\n");
};

const csvEscape = (value: unknown) => {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const buildTableUsageCsv = (report: SqlExplainerReport) => {
  const header = [
    "table_name",
    "usage_count",
    "importance",
    "importance_score",
    "join_targets",
    "condition_patterns",
    "business_guesses",
    "is_insert_target",
  ];
  const rows = report.tables.map((table) => [
    table.tableName,
    table.usageCount,
    table.importance,
    table.importanceScore,
    table.joinTargets.join("; "),
    table.conditionPatterns.join("; "),
    table.businessGuesses.join("; "),
    table.isInsertTarget ? "Y" : "N",
  ]);

  return [header, ...rows]
    .map((row) => row.map(csvEscape).join(","))
    .join("\n");
};

export const buildRiskFindingsCsv = (report: SqlExplainerReport) => {
  const header = [
    "severity",
    "statement_id",
    "category",
    "title",
    "evidence",
    "recommendation",
    "confidence",
  ];
  const rows = report.riskFindings.map((finding) => [
    finding.severity,
    finding.statementId,
    finding.category,
    finding.title,
    finding.evidence,
    finding.recommendation,
    finding.confidence,
  ]);

  return [header, ...rows]
    .map((row) => row.map(csvEscape).join(","))
    .join("\n");
};

export const buildPasteDocument = (
  report: SqlExplainerReport,
  target: "notion" | "confluence",
) => {
  const title = target === "notion"
    ? `# ${report.title}`
    : `h1. ${report.title}`;
  const sectionPrefix = target === "notion" ? "##" : "h2.";
  const codeFence = target === "notion" ? "```" : "{code}";
  const aiDraftSection = report.aiDocumentDraft
    ? [
        `${sectionPrefix} AI 문서 초안`,
        report.aiDocumentDraft.markdown,
        "",
      ]
    : [];

  return [
    title,
    "",
    `${sectionPrefix} 분석 대상 요약`,
    `- SQL ${report.summary.totalSql}개, 테이블 ${report.summary.tableCount}개, JOIN ${report.summary.joinCount}개`,
    `- warnings ${report.summary.warningCount}개`,
    "",
    `${sectionPrefix} 핵심 요약`,
    markdownList(report.executiveSummary, "요약할 내용이 없습니다."),
    "",
    `${sectionPrefix} 위험 SQL`,
    ...(report.riskSqls.length > 0
      ? report.riskSqls.slice(0, 10).map(
          (risk) => `- ${risk.id}: ${riskLevelLabel(risk.riskLevel)} / ${risk.reasons.join(" ")}`,
        )
      : ["- 위험 신호가 있는 SQL이 없습니다."]),
    "",
    `${sectionPrefix} 리스크 / 개선 포인트`,
    ...(report.riskFindings.length > 0
      ? report.riskFindings.slice(0, 15).map(
          (finding) =>
            `- ${finding.statementId}: [${finding.severity}] ${finding.title} / 개선: ${finding.recommendation}`,
        )
      : ["- 리스크 finding이 없습니다."]),
    "",
    `${sectionPrefix} 신규 개발자 설명`,
    markdownList(report.juniorDeveloperGuide, "신규 개발자 안내를 만들 근거가 부족합니다."),
    "",
    ...aiDraftSection,
    ...(report.options.includeRawSql
      ? [
          `${sectionPrefix} 원본 SQL`,
          ...report.sqlSummaries.flatMap((sql) =>
            sql.rawSql
              ? [`### ${sql.id}`, codeFence === "```" ? "```sql" : codeFence, sql.rawSql, codeFence, ""]
              : [],
          ),
        ]
      : []),
  ].join("\n");
};

const escapeHtml = (value: unknown) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const htmlList = (items: string[], fallback: string) =>
  `<ul>${(items.length > 0 ? items : [fallback])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ul>`;

export const buildPrintableHtmlReport = (report: SqlExplainerReport) => `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(report.title)}</title>
  <style>
    body { margin: 32px; color: #0f172a; font-family: Arial, "Noto Sans KR", sans-serif; line-height: 1.6; }
    h1, h2, h3 { page-break-after: avoid; }
    h1 { font-size: 28px; }
    h2 { margin-top: 28px; border-bottom: 1px solid #d8e0ea; padding-bottom: 6px; font-size: 20px; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: fixed; }
    th, td { border: 1px solid #d8e0ea; padding: 8px; text-align: left; vertical-align: top; word-break: break-word; }
    th { background: #f1f5f9; }
    code, pre { font-family: Consolas, "Liberation Mono", monospace; }
    pre { white-space: pre-wrap; border: 1px solid #d8e0ea; border-radius: 6px; padding: 10px; background: #f8fafc; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .summary div { border: 1px solid #d8e0ea; border-radius: 6px; padding: 10px; background: #f8fafc; }
    @media print { body { margin: 18mm; } .no-print { display: none; } }
  </style>
</head>
<body>
  <button class="no-print" onclick="window.print()">PDF로 저장</button>
  <h1>${escapeHtml(report.title)}</h1>
  <p>생성 시각: ${escapeHtml(report.generatedAt)}</p>
  <section class="summary">
    <div><strong>${report.summary.totalSql}</strong><br />분석 SQL</div>
    <div><strong>${report.summary.tableCount}</strong><br />사용 테이블</div>
    <div><strong>${report.summary.joinCount}</strong><br />JOIN 관계</div>
    <div><strong>${report.summary.warningCount}</strong><br />Warnings</div>
  </section>
  <h2>Executive Summary</h2>
  ${htmlList(report.executiveSummary, "요약할 내용이 없습니다.")}
  <h2>사용 테이블 목록</h2>
  <table>
    <thead><tr><th>테이블</th><th>사용 SQL</th><th>핵심도</th><th>JOIN 대상</th><th>업무 추정</th></tr></thead>
    <tbody>
      ${report.tables.map((table) => `<tr><td>${escapeHtml(table.tableName)}</td><td>${table.usageCount}</td><td>${escapeHtml(`${table.importance} ${table.importanceScore}`)}</td><td>${escapeHtml(table.joinTargets.join(", "))}</td><td>${escapeHtml(table.businessGuesses.join(", "))}</td></tr>`).join("")}
    </tbody>
  </table>
  <h2>위험 SQL 목록</h2>
  ${htmlList(
    report.riskSqls.map((risk) => `${risk.id}: ${riskLevelLabel(risk.riskLevel)} ${risk.score}점 - ${risk.reasons.join(" ")}`),
    "위험 신호가 있는 SQL이 없습니다.",
  )}
  <h2>리스크 / 개선 포인트</h2>
  <table>
    <thead><tr><th>심각도</th><th>SQL</th><th>항목</th><th>근거</th><th>개선</th></tr></thead>
    <tbody>
      ${report.riskFindings.slice(0, 40).map((finding) => `<tr><td>${escapeHtml(finding.severity)}</td><td>${escapeHtml(finding.statementId)}</td><td>${escapeHtml(finding.title)}</td><td>${escapeHtml(finding.evidence)}</td><td>${escapeHtml(finding.recommendation)}</td></tr>`).join("")}
    </tbody>
  </table>
  <h2>신규 개발자 설명</h2>
  ${htmlList(report.juniorDeveloperGuide, "신규 개발자 안내를 만들 근거가 부족합니다.")}
  ${report.aiDocumentDraft ? `<h2>AI 문서 초안</h2><pre>${escapeHtml(report.aiDocumentDraft.markdown)}</pre>` : ""}
  <h2>주의 사항</h2>
  ${htmlList(report.warnings, "별도 주의 사항이 없습니다.")}
</body>
</html>`;
