import {
  computedInsightLabel,
  formatComputedNumber,
  type ComputedAnalysisResult,
} from "./computedAnalysis.js";
import type { AiDataInsightsResult } from "./aiDataInsights.js";

const markdownList = (items: string[], fallback: string) =>
  items.length > 0
    ? items.map((item) => item.startsWith("- ") ? item : `- ${item}`).join("\n")
    : `- ${fallback}`;

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
  const basis = analysis.calculationBasis;
  const basisLines = [
    `- 입력 행: ${formatComputedNumber(basis.dataQuality.inputRowCount)}건`,
    `- 숫자 계산 행: ${formatComputedNumber(basis.dataQuality.validMetricRowCount)}건`,
    `- 숫자값 제외 행: ${formatComputedNumber(basis.dataQuality.excludedMetricRowCount)}건`,
    `- 요약 계산: 합계, 산술 평균, 최대값, 최소값을 기계식으로 계산`,
    `- 이상치 후보 기준: IQR ${basis.outlierDetection.iqrMultiplier}배 또는 Z-score ${basis.outlierDetection.zScoreThreshold} 이상`,
  ];

  if (basis.time) {
    const granularityLabel = basis.time.granularity === "day"
      ? "일 단위"
      : basis.time.granularity === "month"
        ? "월 단위"
        : "혼합 단위";
    basisLines.push(
      `- 기간 범위: ${basis.time.startPeriod} ~ ${basis.time.endPeriod} (${formatComputedNumber(basis.time.periodCount)}개 기간, ${granularityLabel})`,
      `- 추세 계산: 기간별 합계 비교${basis.time.trendAvailability === "calculated" ? "" : " (비교 가능한 기간이 부족함)"}`,
      "- 반복 주기/계절성: 이번 계산에서는 평가하지 않음",
    );
  }

  if (basis.comparison) {
    basisLines.push(
      `- 그룹 비교: ${formatComputedNumber(basis.comparison.groupCount)}개 그룹의 합계를 그룹 평균과 비교`,
      `- 화면/보고서 표시 그룹: 상위 ${formatComputedNumber(basis.comparison.displayedGroupCount)}개`,
    );
  }

  if (basis.dataQuality.invalidPeriodRowCount !== undefined) {
    basisLines.push(`- 시간 형식 제외 행: ${formatComputedNumber(basis.dataQuality.invalidPeriodRowCount)}건`);
  }
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
    `- 데이터 범위: 입력 ${formatComputedNumber(analysis.scope.rowCount)}행 / 계산 ${formatComputedNumber(analysis.scope.validMetricRowCount)}행`,
    `- 지표 컬럼: ${analysis.scope.metricColumn}`,
    `- 시간 컬럼: ${analysis.scope.timeColumn || "미선택"}`,
    `- 그룹 컬럼: ${analysis.scope.groupColumn || "미선택"}`,
    "",
    "## 계산 기준 및 데이터 범위",
    markdownList(basisLines, "계산 기준 정보가 없습니다."),
    "",
    "## 핵심 지표",
    markdownList(summaryLines, "계산된 핵심 지표가 없습니다."),
    "",
    "## 주요 인사이트",
    ...(insightLines.length > 0
      ? insightLines
      : ["- AI 인사이트는 선택 실행 기능입니다. 현재는 기계식 계산 결과만 표시합니다."]),
    "## 기계식 분석 근거",
    "### 추세",
    markdownList(trendLines, "시간 컬럼 또는 기간 데이터가 부족해 추세를 계산하지 않았습니다."),
    "",
    "### 그룹 비교",
    markdownList(comparisonLines, "그룹 비교 결과가 없습니다."),
    "",
    "### 이상치 후보",
    markdownList(outlierLines, "계산 기준을 벗어난 이상치 후보가 없습니다."),
    "",
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
