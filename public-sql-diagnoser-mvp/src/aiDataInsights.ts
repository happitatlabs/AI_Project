import type {
  ComputedAnalysisResult,
  ComputedInsightCandidate,
} from "./computedAnalysis.js";
import type { SqlAnalysisResult } from "./sqlExplainer.js";
import { maskSensitiveText } from "./sqlMasking.js";

export type AiDataInsight = {
  candidateId: string;
  checks: string[];
  interpretation: string[];
  proposals: string[];
  title: string;
};

export type AiDataInsightsResult = {
  conclusion: string;
  insights: AiDataInsight[];
  uncertaintyNotes: string[];
  validationWarnings: string[];
};

export type AiDataInsightsPayload = {
  computedAnalysis: {
    comparisons: Array<{
      differenceFromAverage: number;
      factId: string;
      group: string;
      rank: number;
      ratio: number;
      value: number;
    }>;
    facts: Array<{
      category: string;
      id: string;
      label: string;
      values: Record<string, number | string>;
    }>;
    insightCandidates: ComputedInsightCandidate[];
    outliers: Array<{
      deviation?: number;
      factId: string;
      group?: string;
      method: string;
      period?: string;
      reason: string;
      value: number;
    }>;
    scope: Omit<ComputedAnalysisResult["scope"], "datasetName">;
    summary: ComputedAnalysisResult["summary"];
    trend?: ComputedAnalysisResult["trend"];
    warnings: string[];
  };
  instructions: string;
  sqlContext?: {
    businessIntent: string;
    summary: string;
    tables: string[];
    warnings: string[];
  };
};

export type AiDataInsightsResponse = {
  insights: AiDataInsightsResult;
};

export const AI_DATA_INSIGHTS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    conclusion: { type: "string" },
    insights: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          candidateId: { type: "string" },
          checks: { type: "array", items: { type: "string" } },
          interpretation: { type: "array", items: { type: "string" } },
          proposals: { type: "array", items: { type: "string" } },
          title: { type: "string" },
        },
        required: ["candidateId", "checks", "interpretation", "proposals", "title"],
      },
    },
    uncertaintyNotes: { type: "array", items: { type: "string" } },
  },
  required: ["conclusion", "insights", "uncertaintyNotes"],
} as const;

const AI_DATA_INSIGHTS_INSTRUCTIONS = `너는 기계식 계산 결과를 해석하는 데이터 분석 보조자다.
입력의 computedAnalysis는 프로그램이 계산한 검증 가능한 수치 결과다.
원본 행 데이터는 제공되지 않았으며, 계산 결과를 대체하거나 재계산해서는 안 된다.
insightCandidates에 있는 후보만 선택하고 candidateId를 그대로 사용하라.
facts는 프로그램이 출력할 관찰 사실의 근거 ID다. AI는 사실, 숫자, 날짜, 비율, 건수를 새로 쓰지 말고 candidateId와 해석 문장만 작성하라.
제공되지 않은 숫자를 생성하지 않는다.
계산 결과를 임의로 수정하지 않는다.
원인을 데이터 없이 단정하지 않는다.
인과관계가 확인되지 않은 경우 "가능성이 있다", "추가 확인이 필요하다"처럼 표현한다.
이상치 후보를 데이터 오류라고 단정하지 않는다.
의미 있는 인사이트가 없으면 insights를 빈 배열로 반환한다.
insights는 최대 3개로 제한한다.
importance와 importanceReasons는 기계식 후보에 이미 계산되어 있으므로 AI가 새로 평가하거나 변경하지 않는다.
해석, 확인 필요 사항, 제안, 결론에는 숫자 또는 날짜를 쓰지 않는다. 수치는 프로그램의 사실 섹션에서만 표시된다.
sqlContext가 있더라도 실제 실행 결과, 데이터 분포, 인덱스, 장애 이력은 알 수 없다고 전제한다.
한국어로 작성하고 반드시 지정된 JSON 스키마에 맞춰 응답하라.`;

const unique = <T>(values: T[]) => Array.from(new Set(values));

const stringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const cleanText = (value: unknown) =>
  typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";

const textWithoutNumbers = (value: unknown) => {
  const text = cleanText(value);
  return text && !/[0-9]/.test(text) ? text : "";
};

const textArrayWithoutNumbers = (value: unknown) =>
  stringArray(value)
    .map(textWithoutNumbers)
    .filter(Boolean)
    .slice(0, 4);

const buildGroupAliasMap = (analysis: ComputedAnalysisResult) => {
  const map = new Map<string, string>();
  let groupIndex = 1;

  analysis.comparisons.forEach((comparison) => {
    if (!map.has(comparison.group)) {
      map.set(comparison.group, `그룹 ${groupIndex}`);
      groupIndex += 1;
    }
  });

  analysis.outliers.forEach((outlier) => {
    if (outlier.group && !map.has(outlier.group)) {
      map.set(outlier.group, `그룹 ${groupIndex}`);
      groupIndex += 1;
    }
  });

  return map;
};

const maskText = (value: string) => maskSensitiveText(value);

const toSafeComputedAnalysis = (
  analysis: ComputedAnalysisResult,
): AiDataInsightsPayload["computedAnalysis"] => {
  const groupAliasMap = buildGroupAliasMap(analysis);
  const safeGroup = (group: string | undefined) => group ? groupAliasMap.get(group) ?? "그룹" : undefined;
  const safeValues = (values: Record<string, number | string>) =>
    Object.fromEntries(
      Object.entries(values).map(([key, value]) => [
        key,
        key === "group" && typeof value === "string" ? safeGroup(value) ?? "그룹" :
          typeof value === "string" ? maskText(value) : value,
      ]),
    ) as Record<string, number | string>;

  return {
    comparisons: analysis.comparisons.slice(0, 12).map((comparison) => ({
      ...comparison,
      group: safeGroup(comparison.group) ?? "그룹",
    })),
    facts: analysis.facts.map((fact) => ({
      category: fact.category,
      id: fact.id,
      label: fact.category === "comparison" ? "그룹 비교" : maskText(fact.label),
      values: safeValues(fact.values),
    })),
    insightCandidates: analysis.insightCandidates.map((candidate) => ({
      ...candidate,
      importanceReasons: candidate.importanceReasons.map(maskText),
      title: maskText(candidate.title),
    })),
    outliers: analysis.outliers.slice(0, 10).map((outlier) => ({
      ...outlier,
      group: safeGroup(outlier.group),
      reason: maskText(outlier.reason),
    })),
    scope: {
      columnCount: analysis.scope.columnCount,
      groupColumn: analysis.scope.groupColumn ? "group" : undefined,
      metricColumn: "metric",
      rowCount: analysis.scope.rowCount,
      timeColumn: analysis.scope.timeColumn ? "time" : undefined,
      validMetricRowCount: analysis.scope.validMetricRowCount,
    },
    summary: analysis.summary,
    trend: analysis.trend,
    warnings: analysis.warnings.map(maskText),
  };
};

const buildSqlContext = (analysis: SqlAnalysisResult | undefined) => {
  if (!analysis) {
    return undefined;
  }

  return {
    businessIntent: analysis.businessIntent.type,
    summary: maskText(analysis.summary),
    tables: analysis.tables.map((table) => maskText(table.tableName)).slice(0, 12),
    warnings: analysis.warnings.map(maskText).slice(0, 12),
  };
};

export const buildAiDataInsightsPayload = (
  computedAnalysis: ComputedAnalysisResult,
  sqlAnalysis?: SqlAnalysisResult,
): AiDataInsightsPayload => ({
  computedAnalysis: toSafeComputedAnalysis(computedAnalysis),
  instructions: AI_DATA_INSIGHTS_INSTRUCTIONS,
  sqlContext: buildSqlContext(sqlAnalysis),
});

export const isComputedAnalysisResult = (value: unknown): value is ComputedAnalysisResult => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};

  return (
    Array.isArray(record.summary) &&
    Array.isArray(record.facts) &&
    Array.isArray(record.insightCandidates) &&
    Array.isArray(record.warnings) &&
    Boolean(record.scope && typeof record.scope === "object")
  );
};

export const normalizeAiDataInsights = (
  value: unknown,
  computedAnalysis: ComputedAnalysisResult,
): AiDataInsightsResult => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const candidateMap = new Map(
    computedAnalysis.insightCandidates.map((candidate) => [candidate.id, candidate]),
  );
  const validationWarnings: string[] = [];
  const selectedCandidateIds = new Set<string>();
  const insights = (Array.isArray(record.insights) ? record.insights : [])
    .flatMap((item) => {
      const insight = item && typeof item === "object" ? item as Record<string, unknown> : {};
      const candidateId = cleanText(insight.candidateId);
      const candidate = candidateMap.get(candidateId);

      if (!candidate || selectedCandidateIds.has(candidateId)) {
        validationWarnings.push("AI가 계산 결과에 없는 인사이트 후보를 반환해 제외했습니다.");
        return [];
      }

      selectedCandidateIds.add(candidateId);
      const title = textWithoutNumbers(insight.title);
      const interpretation = textArrayWithoutNumbers(insight.interpretation);
      const checks = textArrayWithoutNumbers(insight.checks);
      const proposals = textArrayWithoutNumbers(insight.proposals);

      if (
        [cleanText(insight.title), ...stringArray(insight.interpretation), ...stringArray(insight.checks), ...stringArray(insight.proposals)]
          .some((text) => /[0-9]/.test(text))
      ) {
        validationWarnings.push("AI 해석에 계산 결과 외 숫자 표현이 있어 해당 숫자 문장을 제외했습니다.");
      }

      return [{
        candidateId,
        checks,
        interpretation,
        proposals,
        title: title || candidate.title,
      } satisfies AiDataInsight];
    })
    .slice(0, 3);
  const conclusion = textWithoutNumbers(record.conclusion);
  const uncertaintyNotes = textArrayWithoutNumbers(record.uncertaintyNotes);

  if (cleanText(record.conclusion) && !conclusion) {
    validationWarnings.push("AI 결론에 숫자 표현이 있어 계산 결과와 분리하기 위해 제외했습니다.");
  }

  if (stringArray(record.uncertaintyNotes).some((note) => /[0-9]/.test(note))) {
    validationWarnings.push("AI 불확실성 메모의 숫자 표현을 제외했습니다.");
  }

  return {
    conclusion: conclusion || "기계식 계산 결과와 근거 사실을 우선 확인하세요.",
    insights,
    uncertaintyNotes: unique([
      ...uncertaintyNotes,
      ...computedAnalysis.warnings,
      ...(computedAnalysis.insightCandidates.length === 0
        ? ["계산 기준을 넘는 인사이트 후보가 없어 해석을 제한했습니다."]
        : []),
    ]),
    validationWarnings: unique(validationWarnings),
  };
};

export const parseAiDataInsightsResponse = (
  value: unknown,
  computedAnalysis: ComputedAnalysisResult,
): AiDataInsightsResponse => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};

  return {
    insights: normalizeAiDataInsights(record.insights ?? value, computedAnalysis),
  };
};
