import {
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

  const summaryLines = analysis.summary.map(
    (metric) => `- ${metric.label}: ${formatComputedNumber(metric.value)}`,
  );
  const basis = analysis.calculationBasis;
  const basisLines = [
    `- 입력 행: ${formatComputedNumber(basis.dataQuality.inputRowCount)}건`,
    `- 숫자 계산 행: ${formatComputedNumber(basis.dataQuality.validMetricRowCount)}건`,
    `- 숫자값 제외 행: ${formatComputedNumber(basis.dataQuality.excludedMetricRowCount)}건`,
    `- 요약 계산: 합계, 산술 평균, 최대값, 최소값을 기계식으로 계산`,
    `- 추가 확인 값 기준: IQR ${basis.outlierDetection.iqrMultiplier}배 또는 Z-score ${basis.outlierDetection.zScoreThreshold} 이상`,
  ];

  if (basis.dataQuality.excludedAggregateRowCount) {
    basisLines.push(`- 전체·합계 행 분리: ${formatComputedNumber(basis.dataQuality.excludedAggregateRowCount)}건은 중복 비교를 막기 위해 계산에서 제외`);
  }

  if (basis.time) {
    const granularityLabel = basis.time.granularity === "day"
      ? "일 단위"
      : basis.time.granularity === "month"
        ? "월 단위"
        : basis.time.granularity === "year"
          ? "연도 단위"
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

  if (basis.crossAnalysis) {
    basisLines.push(
      `- 기간×그룹 변화 분해: ${basis.crossAnalysis.previousPeriod} → ${basis.crossAnalysis.currentPeriod}, 비교 가능 그룹 ${formatComputedNumber(basis.crossAnalysis.comparableGroupCount)}개`,
      `- 변화 분해 범위: ${basis.crossAnalysis.valueCoverage === "complete" ? "두 기간의 그룹 값이 모두 있어 전체 변화 기준으로 비교" : "일부 그룹의 기간 값이 누락되어 비교 가능한 그룹 기준으로만 비교"}`,
    );
  }

  if (basis.dataQuality.invalidPeriodRowCount !== undefined) {
    basisLines.push(`- 시간 형식 제외 행: ${formatComputedNumber(basis.dataQuality.invalidPeriodRowCount)}건`);
  }
  const aiInsightByCandidateId = new Map(
    (aiInsights?.insights ?? []).map((insight) => [insight.candidateId, insight]),
  );
  const selectedFindingIds = Array.from(new Set([
    ...(aiInsights?.insights ?? []).map((insight) => insight.candidateId),
    ...analysis.reportFindings.map((finding) => finding.id),
  ])).slice(0, 3);
  const reportFindings = selectedFindingIds
    .map((findingId) => analysis.reportFindings.find((finding) => finding.id === findingId))
    .filter((finding): finding is ComputedAnalysisResult["reportFindings"][number] => Boolean(finding));
  const resultLines = reportFindings.flatMap((finding, index) => {
    const aiInsight = aiInsightByCandidateId.get(finding.id);

    return [
      `### 결과 ${index + 1}. ${aiInsight?.title || finding.title}`,
      "- 관찰된 사실:",
      ...finding.statements.map((statement) => `  - ${statement}`),
      "- 해석:",
      ...(aiInsight
        ? aiInsight.interpretation.length > 0
          ? aiInsight.interpretation.map((item) => `  - ${item}`)
          : ["  - AI 해석이 없습니다."]
        : ["  - 기계식 계산 결과만 정리했습니다. AI 해석 보강을 실행하면 해석을 추가할 수 있습니다."]),
      "- 확인 필요 사항:",
      ...(aiInsight
        ? aiInsight.checks.length > 0
          ? aiInsight.checks.map((item) => `  - ${item}`)
          : ["  - 추가 확인 항목이 없습니다."]
        : ["  - AI 해석 보강 전에는 별도 확인 항목을 생성하지 않습니다."]),
      "- 제안:",
      ...(aiInsight
        ? aiInsight.proposals.length > 0
          ? aiInsight.proposals.map((item) => `  - ${item}`)
          : ["  - 별도 제안이 없습니다."]
        : ["  - AI 해석 보강 전에는 별도 제안을 생성하지 않습니다."]),
      "",
    ];
  });

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
    "## 핵심 지표",
    markdownList(summaryLines, "계산된 핵심 지표가 없습니다."),
    "",
    "## 주요 결과",
    ...(resultLines.length > 0
      ? resultLines
      : ["- 계산 기준을 넘는 뚜렷한 변화, 비교 결과 또는 추가 확인 항목이 없어 핵심 결과를 별도로 만들지 않았습니다."]),
    "",
    "## 결론",
    aiInsights?.conclusion || "핵심 지표와 주요 결과를 우선 확인하고, 필요할 때 AI 해석 보강을 실행하세요.",
    "",
    "## 계산 기준 및 주의 사항",
    markdownList(basisLines, "계산 기준 정보가 없습니다."),
    "",
    "### 주의 사항",
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
