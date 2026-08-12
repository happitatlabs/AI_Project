import type { SqlAnalysisResult } from "./sqlExplainer.js";
import { maskSensitiveSql } from "./sqlMasking.js";

export type AiSqlExplanation = {
  summary: string;
  dataFlowExplanation: string;
  businessPurpose: string;
  juniorDeveloperExplanation: string;
  performanceNotes: string[];
  riskNotes: string[];
  refactoringSuggestions: string[];
  uncertaintyNotes: string[];
};

export type AiSqlAnalysisPayload = Pick<
  SqlAnalysisResult,
  | "aggregations"
  | "advancedFeatures"
  | "businessIntent"
  | "caseExpressions"
  | "confidence"
  | "ctes"
  | "derivedColumns"
  | "filters"
  | "groupBy"
  | "havingConditions"
  | "joins"
  | "setOperations"
  | "subqueries"
  | "tables"
  | "warnings"
  | "windowFunctions"
> & {
  multiSqlContext?: unknown;
};

export type AiSqlExplanationAnalysisInput = Partial<AiSqlAnalysisPayload> & {
  [key: string]: unknown;
};

export type AiSqlExplainRequest = {
  analysis: AiSqlAnalysisPayload;
  instructions: string;
  maskedSql: string;
};

export type AiSqlExplainResponse = {
  explanation: AiSqlExplanation;
};

export const AI_SQL_EXPLANATION_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    summary: { type: "string" },
    dataFlowExplanation: { type: "string" },
    businessPurpose: { type: "string" },
    juniorDeveloperExplanation: { type: "string" },
    performanceNotes: {
      type: "array",
      items: { type: "string" },
    },
    riskNotes: {
      type: "array",
      items: { type: "string" },
    },
    refactoringSuggestions: {
      type: "array",
      items: { type: "string" },
    },
    uncertaintyNotes: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: [
    "summary",
    "dataFlowExplanation",
    "businessPurpose",
    "juniorDeveloperExplanation",
    "performanceNotes",
    "riskNotes",
    "refactoringSuggestions",
    "uncertaintyNotes",
  ],
} as const;

const AI_SQL_EXPLANATION_INSTRUCTIONS = `너는 SQL 설명 보강 도우미다.
입력으로 마스킹된 SQL과 룰 기반 분석 결과가 제공된다.
입력은 단건 SQL 또는 다건 SQL일 수 있다. multiSqlContext가 있으면 여러 SQL의 테이블 사용, JOIN, 조건, 리스크, 업무 목적 분포를 함께 반영하라.
룰 기반 분석 결과를 우선하고, 분석 결과에 없는 사실을 단정하지 마라.
테이블명만 보고 업무 의미를 확정하지 마라.
불확실한 내용은 uncertaintyNotes에 적어라.
성능상 주의사항은 가능성으로 표현하라.
SQL 실행 결과나 실제 데이터 분포를 아는 척하지 마라.
한국어로 설명하라.
신규 개발자가 이해할 수 있는 수준으로 설명하라.
반드시 지정된 JSON 스키마에 맞춰 응답하라.`;

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

const arrayValue = <T>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];

const defaultBusinessIntent: SqlAnalysisResult["businessIntent"] = {
  confidence: 0.5,
  reasons: ["AI 설명 보강용 기본 업무 목적입니다."],
  type: "list_query",
};

const defaultConfidence: SqlAnalysisResult["confidence"] = {
  level: "medium",
  reasons: ["AI 설명 보강용 분석 입력입니다."],
  score: 0.5,
};

const buildAnalysisPayload = (
  analysis: SqlAnalysisResult | AiSqlExplanationAnalysisInput,
): AiSqlAnalysisPayload => {
  const input = analysis as AiSqlExplanationAnalysisInput;
  const businessIntent =
    input.businessIntent && typeof input.businessIntent === "object"
      ? input.businessIntent as SqlAnalysisResult["businessIntent"]
      : defaultBusinessIntent;
  const confidence =
    input.confidence && typeof input.confidence === "object"
      ? input.confidence as SqlAnalysisResult["confidence"]
      : defaultConfidence;

  return {
    advancedFeatures: arrayValue(input.advancedFeatures),
    aggregations: arrayValue(input.aggregations),
    businessIntent,
    caseExpressions: arrayValue(input.caseExpressions),
    confidence,
    ctes: arrayValue(input.ctes),
    derivedColumns: arrayValue(input.derivedColumns),
    filters: arrayValue(input.filters),
    groupBy: arrayValue(input.groupBy),
    havingConditions: arrayValue(input.havingConditions),
    joins: arrayValue(input.joins),
    multiSqlContext: input.multiSqlContext,
    setOperations: arrayValue(input.setOperations),
    subqueries: arrayValue(input.subqueries),
    tables: arrayValue(input.tables),
    warnings: arrayValue(input.warnings),
    windowFunctions: arrayValue(input.windowFunctions),
  };
};

export const buildAiSqlExplanationPayload = (
  sql: string,
  analysis: SqlAnalysisResult | AiSqlExplanationAnalysisInput,
): AiSqlExplainRequest => ({
  analysis: maskAnalysisValue(buildAnalysisPayload(analysis)) as AiSqlAnalysisPayload,
  instructions: AI_SQL_EXPLANATION_INSTRUCTIONS,
  maskedSql: maskSensitiveSql(sql),
});

const stringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

export const normalizeAiSqlExplanation = (value: unknown): AiSqlExplanation => {
  const initialRecord =
    value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidate =
    initialRecord.explanation && typeof initialRecord.explanation === "object"
      ? initialRecord.explanation
      : value;
  const record =
    candidate && typeof candidate === "object" ? candidate as Record<string, unknown> : {};

  return {
    summary: typeof record.summary === "string" ? record.summary : "",
    dataFlowExplanation:
      typeof record.dataFlowExplanation === "string" ? record.dataFlowExplanation : "",
    businessPurpose:
      typeof record.businessPurpose === "string" ? record.businessPurpose : "",
    juniorDeveloperExplanation:
      typeof record.juniorDeveloperExplanation === "string"
        ? record.juniorDeveloperExplanation
        : "",
    performanceNotes: stringArray(record.performanceNotes),
    riskNotes: stringArray(record.riskNotes),
    refactoringSuggestions: stringArray(record.refactoringSuggestions),
    uncertaintyNotes: stringArray(record.uncertaintyNotes),
  };
};

export const parseAiSqlExplanationResponse = (value: unknown): AiSqlExplainResponse => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return {
    explanation: normalizeAiSqlExplanation(record.explanation ?? value),
  };
};
