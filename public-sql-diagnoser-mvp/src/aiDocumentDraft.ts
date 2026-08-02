import {
  buildAiSqlExplanationPayload,
  type AiSqlAnalysisPayload,
  type AiSqlExplanationAnalysisInput,
} from "./aiExplanation.js";
import type { SqlAnalysisResult } from "./sqlExplainer.js";

export type AiSqlDocumentType =
  | "onboarding"
  | "operation"
  | "refactoring"
  | "asset_analysis";

export type AiSqlDocumentDraft = {
  title: string;
  overview: string;
  targetAudience: string;
  businessContext: string;
  dataFlow: string;
  keyTables: string[];
  keyConditions: string[];
  risks: string[];
  refactoringSuggestions: string[];
  onboardingNotes: string;
  markdown: string;
  uncertaintyNotes: string[];
};

export type AiSqlDocumentDraftPayload = {
  analysis: AiSqlAnalysisPayload;
  documentType: AiSqlDocumentType;
  documentTypeLabel: string;
  instructions: string;
  maskedSql: string;
};

export type AiSqlDocumentDraftResponse = {
  draft: AiSqlDocumentDraft;
};

export const AI_SQL_DOCUMENT_TYPE_OPTIONS: Array<{
  description: string;
  label: string;
  value: AiSqlDocumentType;
}> = [
  {
    description: "신규 개발자가 SQL의 목적과 흐름을 빠르게 이해하도록 작성합니다.",
    label: "신규 개발자 온보딩",
    value: "onboarding",
  },
  {
    description: "운영 점검, 장애 대응, 실행 위험 확인에 초점을 둡니다.",
    label: "운영/장애 점검",
    value: "operation",
  },
  {
    description: "구조 개선, 성능 개선, 중복 제거 후보를 검토합니다.",
    label: "리팩토링 검토",
    value: "refactoring",
  },
  {
    description: "레거시 시스템 자산 지도에 붙일 테이블/업무 맥락을 정리합니다.",
    label: "레거시 자산 분석",
    value: "asset_analysis",
  },
];

export const AI_SQL_DOCUMENT_DRAFT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    title: { type: "string" },
    overview: { type: "string" },
    targetAudience: { type: "string" },
    businessContext: { type: "string" },
    dataFlow: { type: "string" },
    keyTables: {
      type: "array",
      items: { type: "string" },
    },
    keyConditions: {
      type: "array",
      items: { type: "string" },
    },
    risks: {
      type: "array",
      items: { type: "string" },
    },
    refactoringSuggestions: {
      type: "array",
      items: { type: "string" },
    },
    onboardingNotes: { type: "string" },
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
    "businessContext",
    "dataFlow",
    "keyTables",
    "keyConditions",
    "risks",
    "refactoringSuggestions",
    "onboardingNotes",
    "markdown",
    "uncertaintyNotes",
  ],
} as const;

const documentTypeInstruction: Record<AiSqlDocumentType, string> = {
  asset_analysis:
    "레거시 시스템 자산 분석 문서로 작성하라. 테이블의 역할, 의존성, 업무 흐름, 후속 자산 지도화에 필요한 단서를 중심으로 정리하라.",
  onboarding:
    "신규 개발자 온보딩 문서로 작성하라. 처음 보는 개발자가 SQL의 목적, 입력 테이블, 조건, 결과 의미를 빠르게 이해하도록 정리하라.",
  operation:
    "운영/장애 점검 문서로 작성하라. 실행 전 확인할 조건, 위험 가능성, 데이터 영향 범위, 운영상 주의점을 중심으로 정리하라.",
  refactoring:
    "리팩토링 검토 문서로 작성하라. 중복 제거, 명확성, 성능 가능성, 유지보수성 개선 후보를 중심으로 정리하라.",
};

const documentTypeLabel = (type: AiSqlDocumentType) =>
  AI_SQL_DOCUMENT_TYPE_OPTIONS.find((option) => option.value === type)?.label ??
  "신규 개발자 온보딩";

export const normalizeAiSqlDocumentType = (
  value: unknown,
): AiSqlDocumentType => {
  if (
    value === "onboarding" ||
    value === "operation" ||
    value === "refactoring" ||
    value === "asset_analysis"
  ) {
    return value;
  }

  return "onboarding";
};

const buildDocumentDraftInstructions = (documentType: AiSqlDocumentType) => `너는 SQL 문서 초안 작성 도우미다.
입력으로 마스킹된 SQL과 룰 기반 분석 결과가 제공된다.
AI는 SQL 분석 엔진이 아니라 문서화 보강 레이어다.
룰 기반 분석 결과를 기준으로만 작성하고, 분석 결과에 없는 업무 사실을 단정하지 마라.
테이블명만 보고 업무 의미를 확정하지 마라.
불확실한 정보는 반드시 "추정"으로 표현하고 uncertaintyNotes에 적어라.
성능 위험은 "가능성" 또는 "확인 필요"로 표현하라.
실제 데이터량, 실행 계획, 인덱스, 장애 이력, 운영 주기를 아는 척하지 마라.
문서는 한국어로 작성하라.
문서 유형: ${documentTypeLabel(documentType)}
문서 유형별 작성 지침: ${documentTypeInstruction[documentType]}
markdown 필드는 팀 문서에 바로 붙여넣을 수 있는 Markdown 초안이어야 한다.
markdown에는 제목, 개요, 대상 독자, 업무 맥락, 데이터 흐름, 핵심 테이블, 주요 조건, 위험 요약, 리팩토링 제안, 신규 개발자 메모, 불확실한 부분을 포함하라.
반드시 지정된 JSON 스키마에 맞춰 응답하라.`;

export const buildAiSqlDocumentDraftPayload = (
  sql: string,
  analysis: SqlAnalysisResult | AiSqlExplanationAnalysisInput,
  documentType: AiSqlDocumentType,
): AiSqlDocumentDraftPayload => {
  const basePayload = buildAiSqlExplanationPayload(sql, analysis);

  return {
    analysis: basePayload.analysis,
    documentType,
    documentTypeLabel: documentTypeLabel(documentType),
    instructions: buildDocumentDraftInstructions(documentType),
    maskedSql: basePayload.maskedSql,
  };
};

const stringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const buildFallbackMarkdown = (draft: Omit<AiSqlDocumentDraft, "markdown">) =>
  [
    `# ${draft.title || "SQL 문서 초안"}`,
    "",
    "## 개요",
    draft.overview,
    "",
    "## 대상 독자",
    draft.targetAudience,
    "",
    "## 업무 맥락",
    draft.businessContext,
    "",
    "## 데이터 흐름",
    draft.dataFlow,
    "",
    "## 핵심 테이블",
    ...(draft.keyTables.length > 0 ? draft.keyTables.map((item) => `- ${item}`) : ["- 추정할 핵심 테이블이 없습니다."]),
    "",
    "## 주요 조건",
    ...(draft.keyConditions.length > 0 ? draft.keyConditions.map((item) => `- ${item}`) : ["- 주요 조건이 없습니다."]),
    "",
    "## 위험 요약",
    ...(draft.risks.length > 0 ? draft.risks.map((item) => `- ${item}`) : ["- 별도 위험 요약이 없습니다."]),
    "",
    "## 리팩토링 제안",
    ...(draft.refactoringSuggestions.length > 0
      ? draft.refactoringSuggestions.map((item) => `- ${item}`)
      : ["- 별도 리팩토링 제안이 없습니다."]),
    "",
    "## 신규 개발자 메모",
    draft.onboardingNotes,
    "",
    "## 불확실한 부분",
    ...(draft.uncertaintyNotes.length > 0
      ? draft.uncertaintyNotes.map((item) => `- ${item}`)
      : ["- 별도 불확실성 메모가 없습니다."]),
  ].join("\n");

export const normalizeAiSqlDocumentDraft = (value: unknown): AiSqlDocumentDraft => {
  const initialRecord =
    value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidate =
    initialRecord.draft && typeof initialRecord.draft === "object"
      ? initialRecord.draft
      : value;
  const record =
    candidate && typeof candidate === "object" ? candidate as Record<string, unknown> : {};
  const draftWithoutMarkdown = {
    businessContext: typeof record.businessContext === "string" ? record.businessContext : "",
    dataFlow: typeof record.dataFlow === "string" ? record.dataFlow : "",
    keyConditions: stringArray(record.keyConditions),
    keyTables: stringArray(record.keyTables),
    onboardingNotes: typeof record.onboardingNotes === "string" ? record.onboardingNotes : "",
    overview: typeof record.overview === "string" ? record.overview : "",
    refactoringSuggestions: stringArray(record.refactoringSuggestions),
    risks: stringArray(record.risks),
    targetAudience: typeof record.targetAudience === "string" ? record.targetAudience : "",
    title: typeof record.title === "string" ? record.title : "SQL 문서 초안",
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

export const parseAiSqlDocumentDraftResponse = (
  value: unknown,
): AiSqlDocumentDraftResponse => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};

  return {
    draft: normalizeAiSqlDocumentDraft(record.draft ?? value),
  };
};
