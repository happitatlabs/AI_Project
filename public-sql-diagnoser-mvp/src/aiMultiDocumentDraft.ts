import {
  AI_SQL_DOCUMENT_TYPE_OPTIONS,
  normalizeAiSqlDocumentType,
  type AiSqlDocumentType,
} from "./aiDocumentDraft.js";
import type { MultiSqlAnalysisResult } from "./multiSqlAnalysis.js";
import type { SqlRiskAnalysisResult } from "./riskDetector.js";
import { maskSensitiveSql } from "./sqlMasking.js";
import type { SystemGraph } from "./systemGraph.js";
import type { TableAssetMap } from "./tableAssetMap.js";

export type AiMultiSqlDocumentDraft = {
  title: string;
  overview: string;
  targetAudience: string;
  businessAreaSummary: string;
  systemContext: string;
  dataFlowSummary: string;
  coreTables: string[];
  tableUsageSummary: string[];
  joinSummary: string[];
  sqlGroupSummary: string[];
  riskSummary: string[];
  refactoringSuggestions: string[];
  onboardingPath: string[];
  operationChecklist: string[];
  markdown: string;
  uncertaintyNotes: string[];
};

export type AiMultiSqlDocumentDraftPayload = {
  analysis: {
    businessIntent: {
      confidence: number;
      reasons: string[];
      type: string;
    };
    confidence: {
      level: "low" | "medium" | "high";
      reasons: string[];
      score: number;
    };
    multiSqlContext: {
      businessIntentSummary: MultiSqlAnalysisResult["businessIntentSummary"];
      conditionUsage: MultiSqlAnalysisResult["conditionUsage"];
      failedSql: number;
      riskFindings: Array<{
        category: string;
        evidence: string;
        recommendation: string;
        severity: string;
        statementId: string;
        title: string;
      }>;
      riskSummary: SqlRiskAnalysisResult["summary"];
      statementCount: number;
      statementSummaries: Array<{
        businessIntent: string;
        confidenceLevel: string;
        id: string;
        summary: string;
        tableNames: string[];
        warningCount: number;
      }>;
      successfulSql: number;
      systemGraphSummary: {
        edgeCount: number;
        loadFlowCount: number;
        nodeCount: number;
        procedureNodeCount: number;
        viewNodeCount: number;
        warnings: string[];
      };
      tableAssetSummary: {
        coreTableCount: number;
        coreTables: string[];
        tableCount: number;
        warnings: string[];
      };
      topJoinUsage: MultiSqlAnalysisResult["joinUsage"];
      topTableUsage: MultiSqlAnalysisResult["tableUsage"];
      warnings: string[];
    };
    warnings: string[];
  };
  documentType: AiSqlDocumentType;
  documentTypeLabel: string;
  instructions: string;
  maskedSql: string;
};

export type AiMultiSqlDocumentDraftResponse = {
  draft: AiMultiSqlDocumentDraft;
};

export const AI_MULTI_SQL_DOCUMENT_DRAFT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    title: { type: "string" },
    overview: { type: "string" },
    targetAudience: { type: "string" },
    businessAreaSummary: { type: "string" },
    systemContext: { type: "string" },
    dataFlowSummary: { type: "string" },
    coreTables: {
      type: "array",
      items: { type: "string" },
    },
    tableUsageSummary: {
      type: "array",
      items: { type: "string" },
    },
    joinSummary: {
      type: "array",
      items: { type: "string" },
    },
    sqlGroupSummary: {
      type: "array",
      items: { type: "string" },
    },
    riskSummary: {
      type: "array",
      items: { type: "string" },
    },
    refactoringSuggestions: {
      type: "array",
      items: { type: "string" },
    },
    onboardingPath: {
      type: "array",
      items: { type: "string" },
    },
    operationChecklist: {
      type: "array",
      items: { type: "string" },
    },
    markdown: { type: "string" },
    uncertaintyNotes: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: [
    "title",
    "overview",
    "targetAudience",
    "businessAreaSummary",
    "systemContext",
    "dataFlowSummary",
    "coreTables",
    "tableUsageSummary",
    "joinSummary",
    "sqlGroupSummary",
    "riskSummary",
    "refactoringSuggestions",
    "onboardingPath",
    "operationChecklist",
    "markdown",
    "uncertaintyNotes",
  ],
} as const;

const unique = <T>(values: T[]) => Array.from(new Set(values));

const documentTypeLabel = (type: AiSqlDocumentType) =>
  AI_SQL_DOCUMENT_TYPE_OPTIONS.find((option) => option.value === type)?.label ??
  "신규 개발자 온보딩";

const maskAnalysisValue = (value: unknown): unknown => {
  if (typeof value === "string") {
    return maskSensitiveSql(value);
  }

  if (Array.isArray(value)) {
    return value.map(maskAnalysisValue);
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, maskAnalysisValue(item)]),
    );
  }

  return value;
};

const countSuccessfulStatements = (multiAnalysis: MultiSqlAnalysisResult) =>
  multiAnalysis.statements.filter((statement) => statement.analysis).length;

const dominantBusinessIntent = (
  businessIntentSummary: MultiSqlAnalysisResult["businessIntentSummary"],
) => {
  const [dominantType] =
    Object.entries(businessIntentSummary)
      .sort(([leftType, leftCount], [rightType, rightCount]) =>
        rightCount === leftCount
          ? leftType.localeCompare(rightType)
          : rightCount - leftCount,
      )[0] ?? [];

  return dominantType ?? "list_query";
};

const buildMultiConfidence = (
  multiAnalysis: MultiSqlAnalysisResult,
  tableAssetMap: TableAssetMap,
  systemGraph: SystemGraph,
) => {
  const analyses = multiAnalysis.statements
    .map((statement) => statement.analysis)
    .filter((analysis): analysis is NonNullable<typeof analysis> => Boolean(analysis));
  const averageScore =
    analyses.length > 0
      ? analyses.reduce((sum, analysis) => sum + analysis.confidence.score, 0) / analyses.length
      : 0.25;
  const warningPenalty = Math.min(
    0.25,
    (multiAnalysis.warnings.length + tableAssetMap.warnings.length + systemGraph.warnings.length) * 0.02,
  );
  const score = Math.max(0.1, Math.round((averageScore - warningPenalty) * 100) / 100);

  return {
    level: score >= 0.72 ? "high" as const : score >= 0.45 ? "medium" as const : "low" as const,
    reasons: [
      `분석 SQL ${multiAnalysis.statements.length}개 중 ${countSuccessfulStatements(multiAnalysis)}개가 구조화되었습니다.`,
      `테이블 ${multiAnalysis.tableUsage.length}개, JOIN ${multiAnalysis.joinUsage.length}개, 조건 패턴 ${multiAnalysis.conditionUsage.length}개가 집계되었습니다.`,
      `시스템 지도 노드 ${systemGraph.summary.nodeCount}개, 연결 ${systemGraph.summary.edgeCount}개가 추출되었습니다.`,
      `핵심 테이블 후보 ${tableAssetMap.summary.coreTableCount}개가 계산되었습니다.`,
    ],
    score,
  };
};

const buildDocumentInstructions = (documentType: AiSqlDocumentType) => `너는 레거시 SQL 묶음 문서화 도우미다.
입력은 여러 SQL의 마스킹된 원문과 룰 기반 다건 분석 결과다.
AI는 분석을 대체하지 않고 문서 초안만 작성한다.
여러 SQL을 하나의 시스템/업무 흐름 관점으로 설명하라.
반복 사용 테이블과 JOIN은 핵심 후보로만 표현하라.
테이블명만 보고 업무를 확정하지 말고 "추정"으로 표현하라.
리스크는 가능성 또는 검토 필요로 표현하라.
실행 계획, 실제 데이터량, 인덱스 상태, 장애 이력, 배치 스케줄을 아는 척하지 마라.
신규 개발자가 어떤 순서로 읽어야 하는지 onboardingPath에 제시하라.
operationChecklist에는 운영/장애 점검 시 확인할 항목을 넣어라.
문서는 한국어로 작성하라.
문서 유형: ${documentTypeLabel(documentType)}
markdown 필드는 팀 문서에 바로 붙여넣을 수 있는 Markdown 초안이어야 한다.
markdown에는 제목, 개요, 업무 영역 요약, 시스템 맥락, 데이터 흐름, 핵심 테이블, 테이블 사용 요약, JOIN 요약, SQL 그룹 요약, 위험 요약, 리팩토링 제안, 신규 개발자 온보딩 경로, 운영 체크리스트, 불확실한 부분을 포함하라.
반드시 지정된 JSON 스키마에 맞춰 응답하라.`;

export const buildAiMultiSqlDocumentDraftPayload = ({
  documentType,
  multiAnalysis,
  riskAnalysis,
  sql,
  systemGraph,
  tableAssetMap,
}: {
  documentType: AiSqlDocumentType;
  multiAnalysis: MultiSqlAnalysisResult;
  riskAnalysis: SqlRiskAnalysisResult;
  sql: string;
  systemGraph: SystemGraph;
  tableAssetMap: TableAssetMap;
}): AiMultiSqlDocumentDraftPayload => {
  const normalizedDocumentType = normalizeAiSqlDocumentType(documentType);
  const successfulSql = countSuccessfulStatements(multiAnalysis);
  const statementSummaries = multiAnalysis.statements.map((statement) => ({
    businessIntent: statement.analysis?.businessIntent.type ?? "unknown",
    confidenceLevel: statement.analysis?.confidence.level ?? "unknown",
    id: statement.id,
    summary: statement.analysis?.summary ?? statement.error ?? "분석 결과 없음",
    tableNames: unique(statement.analysis?.tables.map((table) => table.tableName) ?? []),
    warningCount: statement.warnings.length + (statement.analysis?.warnings.length ?? 0),
  }));
  const warnings = unique([
    ...multiAnalysis.warnings,
    ...tableAssetMap.warnings,
    ...systemGraph.warnings,
    "다건 AI 문서 초안은 여러 SQL의 정적 분석 결과를 기반으로 생성된 추정 문서입니다.",
  ]);
  const analysis: AiMultiSqlDocumentDraftPayload["analysis"] = {
      businessIntent: {
        confidence: Math.min(0.85, 0.55 + Object.keys(multiAnalysis.businessIntentSummary).length * 0.07),
        reasons: [
          `업무 목적 분포: ${
            Object.entries(multiAnalysis.businessIntentSummary)
              .map(([type, count]) => `${type} ${count}개`)
              .join(", ") || "없음"
          }`,
        ],
        type: dominantBusinessIntent(multiAnalysis.businessIntentSummary),
      },
      confidence: buildMultiConfidence(multiAnalysis, tableAssetMap, systemGraph),
      multiSqlContext: {
        businessIntentSummary: multiAnalysis.businessIntentSummary,
        conditionUsage: multiAnalysis.conditionUsage.slice(0, 40),
        failedSql: multiAnalysis.statements.length - successfulSql,
        riskFindings: riskAnalysis.findings.slice(0, 40).map((finding) => ({
          category: finding.category,
          evidence: finding.evidence,
          recommendation: finding.recommendation,
          severity: finding.severity,
          statementId: finding.statementId,
          title: finding.title,
        })),
        riskSummary: riskAnalysis.summary,
        statementCount: multiAnalysis.statements.length,
        statementSummaries,
        successfulSql,
        systemGraphSummary: {
          edgeCount: systemGraph.summary.edgeCount,
          loadFlowCount: systemGraph.summary.loadFlowCount,
          nodeCount: systemGraph.summary.nodeCount,
          procedureNodeCount: systemGraph.summary.procedureNodeCount,
          viewNodeCount: systemGraph.summary.viewNodeCount,
          warnings: systemGraph.warnings.slice(0, 20),
        },
        tableAssetSummary: {
          coreTableCount: tableAssetMap.summary.coreTableCount,
          coreTables: tableAssetMap.coreTables.slice(0, 12).map((table) => table.tableName),
          tableCount: tableAssetMap.summary.tableCount,
          warnings: tableAssetMap.warnings.slice(0, 20),
        },
        topJoinUsage: multiAnalysis.joinUsage.slice(0, 40),
        topTableUsage: multiAnalysis.tableUsage.slice(0, 40),
        warnings,
      },
      warnings,
    };

  return {
    analysis: maskAnalysisValue(analysis) as AiMultiSqlDocumentDraftPayload["analysis"],
    documentType: normalizedDocumentType,
    documentTypeLabel: documentTypeLabel(normalizedDocumentType),
    instructions: buildDocumentInstructions(normalizedDocumentType),
    maskedSql: maskSensitiveSql(sql),
  };
};

const stringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const buildFallbackMarkdown = (draft: Omit<AiMultiSqlDocumentDraft, "markdown">) =>
  [
    `# ${draft.title || "다건 SQL 문서 초안"}`,
    "",
    "## 개요",
    draft.overview,
    "",
    "## 대상 독자",
    draft.targetAudience,
    "",
    "## 업무 영역 요약",
    draft.businessAreaSummary,
    "",
    "## 시스템 맥락",
    draft.systemContext,
    "",
    "## 데이터 흐름 요약",
    draft.dataFlowSummary,
    "",
    "## 핵심 테이블",
    ...(draft.coreTables.length > 0 ? draft.coreTables.map((item) => `- ${item}`) : ["- 핵심 테이블 후보가 없습니다."]),
    "",
    "## 테이블 사용 요약",
    ...(draft.tableUsageSummary.length > 0 ? draft.tableUsageSummary.map((item) => `- ${item}`) : ["- 테이블 사용 요약이 없습니다."]),
    "",
    "## JOIN 요약",
    ...(draft.joinSummary.length > 0 ? draft.joinSummary.map((item) => `- ${item}`) : ["- JOIN 요약이 없습니다."]),
    "",
    "## SQL 그룹 요약",
    ...(draft.sqlGroupSummary.length > 0 ? draft.sqlGroupSummary.map((item) => `- ${item}`) : ["- SQL 그룹 요약이 없습니다."]),
    "",
    "## 위험 요약",
    ...(draft.riskSummary.length > 0 ? draft.riskSummary.map((item) => `- ${item}`) : ["- 위험 요약이 없습니다."]),
    "",
    "## 리팩토링 제안",
    ...(draft.refactoringSuggestions.length > 0 ? draft.refactoringSuggestions.map((item) => `- ${item}`) : ["- 리팩토링 제안이 없습니다."]),
    "",
    "## 신규 개발자 온보딩 경로",
    ...(draft.onboardingPath.length > 0 ? draft.onboardingPath.map((item) => `- ${item}`) : ["- 온보딩 경로가 없습니다."]),
    "",
    "## 운영 체크리스트",
    ...(draft.operationChecklist.length > 0 ? draft.operationChecklist.map((item) => `- ${item}`) : ["- 운영 체크리스트가 없습니다."]),
    "",
    "## 불확실한 부분",
    ...(draft.uncertaintyNotes.length > 0 ? draft.uncertaintyNotes.map((item) => `- ${item}`) : ["- 불확실성 메모가 없습니다."]),
  ].join("\n");

export const normalizeAiMultiSqlDocumentDraft = (value: unknown): AiMultiSqlDocumentDraft => {
  const initialRecord =
    value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidate =
    initialRecord.draft && typeof initialRecord.draft === "object"
      ? initialRecord.draft
      : value;
  const record =
    candidate && typeof candidate === "object" ? candidate as Record<string, unknown> : {};
  const draftWithoutMarkdown = {
    businessAreaSummary:
      typeof record.businessAreaSummary === "string" ? record.businessAreaSummary : "",
    coreTables: stringArray(record.coreTables),
    dataFlowSummary: typeof record.dataFlowSummary === "string" ? record.dataFlowSummary : "",
    joinSummary: stringArray(record.joinSummary),
    onboardingPath: stringArray(record.onboardingPath),
    operationChecklist: stringArray(record.operationChecklist),
    overview: typeof record.overview === "string" ? record.overview : "",
    refactoringSuggestions: stringArray(record.refactoringSuggestions),
    riskSummary: stringArray(record.riskSummary),
    sqlGroupSummary: stringArray(record.sqlGroupSummary),
    systemContext: typeof record.systemContext === "string" ? record.systemContext : "",
    tableUsageSummary: stringArray(record.tableUsageSummary),
    targetAudience: typeof record.targetAudience === "string" ? record.targetAudience : "",
    title: typeof record.title === "string" ? record.title : "다건 SQL 문서 초안",
    uncertaintyNotes: stringArray(record.uncertaintyNotes),
  };

  return {
    ...draftWithoutMarkdown,
    markdown:
      typeof record.markdown === "string" && record.markdown.trim()
        ? record.markdown
        : buildFallbackMarkdown(draftWithoutMarkdown),
  };
};

export const parseAiMultiSqlDocumentDraftResponse = (
  value: unknown,
): AiMultiSqlDocumentDraftResponse => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};

  return {
    draft: normalizeAiMultiSqlDocumentDraft(record.draft ?? value),
  };
};
