import {
  computedInsightLabel,
  formatComputedNumber,
  type ComputedAnalysisResult,
} from "./computedAnalysis.js";
import type { AiDataInsightsResult } from "./aiDataInsights.js";

const markdownList = (items: string[], fallback: string) =>
  items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : `- ${fallback}`;

export const buildDataInsightMarkdownReport = (
  analysis: ComputedAnalysisResult | undefined,
  aiInsights?: AiDataInsightsResult,
) => {
  if (!analysis) {
    return [
      "# 데이터 분석 보고서",
      "",
      "계산 결과가 없습니다. CSV 또는 JSON 데이터를 입력하고 기계식 계산을 실행하세요.",
    ].join("\n");
  }

  const factMap = new Map(analysis.facts.map((fact) => [fact.id, fact]));
  const summaryLines = analysis.summary.map(
    (metric) => `- ${metric.label}: ${formatComputedNumber(metric.value)}`,
  );
  const trendLines = analysis.trend
    ? analysis.trend.evidenceFactIds
      .map((factId) => factMap.get(factId)?.statement)
      .filter((statement): statement is string => Boolean(statement))
    : [];
  const comparisonLines = analysis.comparisons
    .slice(0, 10)
    .map((comparison) => factMap.get(comparison.factId)?.statement)
    .filter((statement): statement is string => Boolean(statement));
  const outlierLines = analysis.outliers
    .map((outlier) => factMap.get(outlier.factId)?.statement)
    .filter((statement): statement is string => Boolean(statement));
  const insightLines = aiInsights?.insights.flatMap((insight, index) => {
    const candidate = analysis.insightCandidates.find((item) => item.id === insight.candidateId);
    const facts = candidate?.evidenceFactIds
      .map((factId) => factMap.get(factId)?.statement)
      .filter((statement): statement is string => Boolean(statement)) ?? [];

    return [
      `### 인사이트 ${index + 1}. ${insight.title}`,
      `- 중요도: ${candidate ? computedInsightLabel(candidate.importance) : "계산 결과 확인 필요"}${candidate ? ` (${candidate.importanceScore}점)` : ""}`,
      "- 중요도 근거:",
      ...(candidate?.importanceReasons.map((reason) => `  - ${reason}`) ?? ["  - 계산 근거를 확인하세요."]),
      "- 관찰된 사실:",
      ...(facts.length > 0 ? facts.map((fact) => `  - ${fact}`) : ["  - 연결된 기계식 사실이 없습니다."]),
      "- 해석:",
      ...(insight.interpretation.length > 0 ? insight.interpretation.map((item) => `  - ${item}`) : ["  - AI 해석이 없습니다."]),
      "- 확인 필요 사항:",
      ...(insight.checks.length > 0 ? insight.checks.map((item) => `  - ${item}`) : ["  - 추가 확인 항목이 없습니다."]),
      "- 제안:",
      ...(insight.proposals.length > 0 ? insight.proposals.map((item) => `  - ${item}`) : ["  - 별도 제안이 없습니다."]),
      "",
    ];
  }) ?? [];

  return [
    "# 데이터 분석 보고서",
    "",
    "## 분석 개요",
    `- 분석 대상: ${analysis.scope.datasetName || "로컬 입력 데이터"}`,
    `- 입력 행: ${formatComputedNumber(analysis.scope.rowCount)}건`,
    `- 계산 행: ${formatComputedNumber(analysis.scope.validMetricRowCount)}건`,
    `- 지표 컬럼: ${analysis.scope.metricColumn}`,
    `- 시간 컬럼: ${analysis.scope.timeColumn || "미선택"}`,
    `- 그룹 컬럼: ${analysis.scope.groupColumn || "미선택"}`,
    "",
    "## 핵심 지표",
    markdownList(summaryLines, "계산된 핵심 지표가 없습니다."),
    "",
    "## 기계식 추세 분석",
    markdownList(trendLines, "시간 컬럼 또는 기간 데이터가 부족해 추세를 계산하지 않았습니다."),
    "",
    "## 기계식 그룹 비교",
    markdownList(comparisonLines, "그룹 비교 결과가 없습니다."),
    "",
    "## 기계식 이상치 후보",
    markdownList(outlierLines, "계산 기준을 벗어난 이상치 후보가 없습니다."),
    "",
    "## 주요 인사이트",
    ...(insightLines.length > 0
      ? insightLines
      : ["- AI 인사이트는 선택 실행 기능입니다. 현재는 기계식 계산 결과만 표시합니다."]),
    "## 결론",
    aiInsights?.conclusion || "기계식 계산 결과를 우선 확인하고, 필요할 때 AI 해석을 실행하세요.",
    "",
    "## 주의 사항",
    markdownList(
      [
        ...analysis.warnings,
        ...(aiInsights?.validationWarnings ?? []),
        ...(aiInsights?.uncertaintyNotes ?? []),
      ],
      "별도 주의 사항이 없습니다.",
    ),
  ].join("\n");
};
