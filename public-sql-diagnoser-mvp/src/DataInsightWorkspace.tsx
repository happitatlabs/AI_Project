import { useMemo, useState, type ChangeEvent } from "react";
import type { AiDataInsightsResponse } from "./aiDataInsights";
import {
  errorAiDataInsightsState,
  idleAiDataInsightsState,
  loadingAiDataInsightsState,
  successAiDataInsightsState,
  type AiDataInsightsState,
} from "./aiDataInsightsState";
import {
  DEFAULT_DATA_ANALYSIS_SAMPLE,
  calculateComputedAnalysis,
  computedInsightLabel,
  computedTrendLabel,
  formatComputedNumber,
  formatComputedPercent,
  inspectDataInput,
  type ComputedAnalysisResult,
  type DataInputFormat,
} from "./computedAnalysis";
import { buildDataInsightMarkdownReport } from "./dataInsightReport";
import type { SqlAnalysisResult } from "./sqlExplainer";

type CopyStatus = "idle" | "copied" | "selected" | "failed";

type DataInsightWorkspaceProps = {
  aiFeatureEnabled: boolean;
  sqlAnalysis?: SqlAnalysisResult;
};

const copyText = async (text: string, outputId: string): Promise<CopyStatus> => {
  try {
    await navigator.clipboard.writeText(text);
    return "copied";
  } catch {
    const element = document.getElementById(outputId) as HTMLTextAreaElement | null;

    if (!element) {
      return "failed";
    }

    element.focus();
    element.select();
    return "selected";
  }
};

const downloadText = (fileName: string, content: string) => {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const selectedColumn = (current: string, candidates: string[], recommended?: string) =>
  candidates.includes(current) ? current : recommended && candidates.includes(recommended) ? recommended : "";

const candidateFacts = (analysis: ComputedAnalysisResult, candidateId: string) => {
  const candidate = analysis.insightCandidates.find((item) => item.id === candidateId);
  const factMap = new Map(analysis.facts.map((fact) => [fact.id, fact]));

  return candidate?.evidenceFactIds
    .map((factId) => factMap.get(factId)?.statement)
    .filter((statement): statement is string => Boolean(statement)) ?? [];
};

export function DataInsightWorkspace({
  aiFeatureEnabled,
  sqlAnalysis,
}: DataInsightWorkspaceProps) {
  const [input, setInput] = useState(DEFAULT_DATA_ANALYSIS_SAMPLE);
  const [inputFormat, setInputFormat] = useState<DataInputFormat>("auto");
  const [datasetName, setDatasetName] = useState("처리 건수 예제 데이터");
  const [metricColumn, setMetricColumn] = useState("");
  const [timeColumn, setTimeColumn] = useState("");
  const [groupColumn, setGroupColumn] = useState("");
  const [analysis, setAnalysis] = useState<ComputedAnalysisResult>();
  const [calculationError, setCalculationError] = useState("");
  const [aiState, setAiState] = useState<AiDataInsightsState>(() => idleAiDataInsightsState());
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");

  const inspection = useMemo(
    () => inspectDataInput(input, inputFormat),
    [input, inputFormat],
  );
  const effectiveMetricColumn = selectedColumn(
    metricColumn,
    inspection.columnOptions.metricColumns,
    inspection.columnOptions.recommended.metricColumn,
  );
  const effectiveTimeColumn = selectedColumn(
    timeColumn,
    inspection.columnOptions.timeColumns,
    inspection.columnOptions.recommended.timeColumn,
  );
  const effectiveGroupColumn = selectedColumn(
    groupColumn,
    inspection.columnOptions.groupColumns,
    inspection.columnOptions.recommended.groupColumn,
  );
  const markdownReport = useMemo(
    () => buildDataInsightMarkdownReport(
      analysis,
      aiState.status === "success" ? aiState.insights : undefined,
    ),
    [aiState, analysis],
  );

  const resetComputedResult = () => {
    setAnalysis(undefined);
    setCalculationError("");
    setAiState(idleAiDataInsightsState());
    setCopyStatus("idle");
  };

  const updateInput = (nextInput: string) => {
    setInput(nextInput);
    resetComputedResult();
  };

  const loadSample = () => {
    setInput(DEFAULT_DATA_ANALYSIS_SAMPLE);
    setInputFormat("auto");
    setDatasetName("처리 건수 예제 데이터");
    setMetricColumn("");
    setTimeColumn("");
    setGroupColumn("");
    resetComputedResult();
  };

  const loadFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const contents = await file.text();
    setInput(contents);
    setInputFormat(file.name.toLowerCase().endsWith(".json") ? "json" : "csv");
    setDatasetName(file.name.replace(/\.[^.]+$/, ""));
    setMetricColumn("");
    setTimeColumn("");
    setGroupColumn("");
    resetComputedResult();
    event.target.value = "";
  };

  const runCalculation = () => {
    setCopyStatus("idle");

    if (!inspection.ok) {
      setAnalysis(undefined);
      setCalculationError(inspection.error);
      setAiState(idleAiDataInsightsState());
      return;
    }

    if (!effectiveMetricColumn) {
      setAnalysis(undefined);
      setCalculationError("숫자로 계산할 지표 컬럼을 선택하세요.");
      setAiState(idleAiDataInsightsState());
      return;
    }

    const outcome = calculateComputedAnalysis(inspection, {
      datasetName,
      groupColumn: effectiveGroupColumn || undefined,
      metricColumn: effectiveMetricColumn,
      timeColumn: effectiveTimeColumn || undefined,
    });

    if (!outcome.ok) {
      setAnalysis(undefined);
      setCalculationError(outcome.error);
      setAiState(idleAiDataInsightsState());
      return;
    }

    setAnalysis(outcome.result);
    setCalculationError("");
    setAiState(idleAiDataInsightsState());
  };

  const requestAiInsights = async () => {
    if (
      !aiFeatureEnabled ||
      !analysis ||
      analysis.insightCandidates.length === 0 ||
      aiState.status === "loading"
    ) {
      return;
    }

    setAiState(loadingAiDataInsightsState());
    setCopyStatus("idle");

    try {
      const response = await fetch("/api/ai-data-insights", {
        body: JSON.stringify({
          computedAnalysis: analysis,
          sqlAnalysis,
        }),
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const responseBody = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof responseBody?.error === "string"
            ? responseBody.error
            : "AI 인사이트 요청에 실패했습니다.",
        );
      }

      const data = responseBody as AiDataInsightsResponse;
      setAiState(successAiDataInsightsState(data.insights));
    } catch (error) {
      setAiState(errorAiDataInsightsState(
        error instanceof Error ? error.message : "AI 인사이트 요청에 실패했습니다.",
      ));
    }
  };

  const downloadReport = () => {
    downloadText("data-insight-report.md", markdownReport);
  };

  return (
    <>
      <section className="data-input-panel sql-input-panel" aria-label="데이터 입력">
        <div className="input-header data-input-header">
          <label className="input-label no-border" htmlFor="data-input">
            CSV 또는 JSON 데이터 입력
          </label>
          <div className="data-input-actions">
            <select
              aria-label="데이터 형식"
              value={inputFormat}
              onChange={(event) => {
                setInputFormat(event.target.value as DataInputFormat);
                resetComputedResult();
              }}
            >
              <option value="auto">형식 자동 감지</option>
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
            <label className="secondary-button file-input-button">
              파일 불러오기
              <input accept=".csv,.json,text/csv,application/json" type="file" onChange={(event) => void loadFile(event)} />
            </label>
            <button className="secondary-button" type="button" onClick={loadSample}>
              예제 데이터
            </button>
          </div>
        </div>
        <textarea
          id="data-input"
          value={input}
          onChange={(event) => updateInput(event.target.value)}
          spellCheck={false}
          aria-describedby="data-input-local-note"
        />
      </section>

      <p id="data-input-local-note" className="data-local-note">
        원본 행 데이터는 이 브라우저에서만 파싱하고 계산합니다. AI 해석을 실행해도 원본 행은 전송하지 않으며, 계산된 수치·근거 ID·마스킹된 범주 정보만 사용합니다.
      </p>

      <section className="data-config-panel" aria-label="계산 기준 설정">
        <div className="data-config-grid">
          <label className="data-config-field">
            <span>분석 대상 이름</span>
            <input
              value={datasetName}
              onChange={(event) => {
                setDatasetName(event.target.value);
                resetComputedResult();
              }}
              placeholder="예: 2026년 처리 건수"
            />
          </label>
          <label className="data-config-field">
            <span>숫자 지표</span>
            <select
              value={effectiveMetricColumn}
              onChange={(event) => {
                setMetricColumn(event.target.value);
                resetComputedResult();
              }}
            >
              <option value="">선택하세요</option>
              {inspection.columnOptions.metricColumns.map((column) => (
                <option key={column} value={column}>{column}</option>
              ))}
            </select>
          </label>
          <label className="data-config-field">
            <span>시간 컬럼</span>
            <select
              value={effectiveTimeColumn}
              onChange={(event) => {
                setTimeColumn(event.target.value);
                resetComputedResult();
              }}
            >
              <option value="">추세 계산 안 함</option>
              {inspection.columnOptions.timeColumns.map((column) => (
                <option key={column} value={column}>{column}</option>
              ))}
            </select>
          </label>
          <label className="data-config-field">
            <span>그룹 컬럼</span>
            <select
              value={effectiveGroupColumn}
              onChange={(event) => {
                setGroupColumn(event.target.value);
                resetComputedResult();
              }}
            >
              <option value="">그룹 비교 안 함</option>
              {inspection.columnOptions.groupColumns.map((column) => (
                <option key={column} value={column}>{column}</option>
              ))}
            </select>
          </label>
        </div>
        {inspection.ok ? (
          <p className="data-config-help">
            감지된 형식: {inspection.format.toUpperCase()} / 행 {formatComputedNumber(inspection.rows.length)}개 / 컬럼 {inspection.columns.join(", ") || "없음"}
          </p>
        ) : (
          <p className="data-input-error">{inspection.error}</p>
        )}
      </section>

      <div className="action-row data-action-row">
        <button className="primary-button" type="button" onClick={runCalculation}>
          기계식 계산 실행
        </button>
        {aiFeatureEnabled ? (
          <button
            className="secondary-button"
            type="button"
            disabled={!analysis || analysis.insightCandidates.length === 0 || aiState.status === "loading"}
            onClick={() => void requestAiInsights()}
          >
            {aiState.status === "loading" ? "AI 인사이트 해석 중" : "AI로 인사이트 해석"}
          </button>
        ) : null}
      </div>

      {calculationError ? <p className="data-input-error calculation-error">{calculationError}</p> : null}

      {analysis ? (
        <div className="data-result-grid">
          <section className="result-section data-result-section wide">
            <h2>기계식 계산 결과</h2>
            <p className="report-help">
              원본 데이터에서 프로그램이 계산한 검증 가능한 수치입니다. AI는 이 결과를 바꾸거나 다시 계산하지 않습니다.
            </p>
            <div className="summary-metrics data-summary-metrics">
              {analysis.summary.map((metric) => (
                <div key={metric.id}>
                  <strong>{formatComputedNumber(metric.value)}</strong>
                  <span>{metric.label}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="result-section data-result-section wide">
            <h2>계산 기준 및 데이터 범위</h2>
            <p className="report-help">
              아래 기준은 프로그램이 적용한 계산 범위입니다. AI 해석은 이 기준과 근거 사실을 벗어나지 않습니다.
            </p>
            <ul className="analysis-list compact">
              <li>
                <strong>계산 대상</strong>
                <span>
                  입력 {formatComputedNumber(analysis.calculationBasis.dataQuality.inputRowCount)}행 / 숫자 계산 {formatComputedNumber(analysis.calculationBasis.dataQuality.validMetricRowCount)}행 / 제외 {formatComputedNumber(analysis.calculationBasis.dataQuality.excludedMetricRowCount)}행
                </span>
              </li>
              {analysis.calculationBasis.time ? (
                <li>
                  <strong>기간별 추세</strong>
                  <span>
                    {analysis.calculationBasis.time.startPeriod} ~ {analysis.calculationBasis.time.endPeriod} / {formatComputedNumber(analysis.calculationBasis.time.periodCount)}개 기간 / {analysis.calculationBasis.time.granularity === "day" ? "일 단위" : analysis.calculationBasis.time.granularity === "month" ? "월 단위" : "혼합 단위"}
                    {analysis.calculationBasis.time.trendAvailability === "insufficient_periods" ? " / 비교 가능한 기간 부족" : ""}
                  </span>
                </li>
              ) : null}
              {analysis.calculationBasis.dataQuality.invalidPeriodRowCount !== undefined ? (
                <li>
                  <strong>시간 형식 제외</strong>
                  <span>{formatComputedNumber(analysis.calculationBasis.dataQuality.invalidPeriodRowCount)}행</span>
                </li>
              ) : null}
              {analysis.calculationBasis.comparison ? (
                <li>
                  <strong>그룹 비교</strong>
                  <span>
                    {formatComputedNumber(analysis.calculationBasis.comparison.groupCount)}개 그룹 합계를 그룹 평균과 비교 / 표시 {formatComputedNumber(analysis.calculationBasis.comparison.displayedGroupCount)}개
                  </span>
                </li>
              ) : null}
              <li>
                <strong>이상치 후보</strong>
                <span>
                  IQR {analysis.calculationBasis.outlierDetection.iqrMultiplier}배 또는 Z-score {analysis.calculationBasis.outlierDetection.zScoreThreshold} 이상 / 후보 {formatComputedNumber(analysis.calculationBasis.outlierDetection.candidateCount)}건
                </span>
              </li>
              {analysis.calculationBasis.time ? (
                <li>
                  <strong>반복 주기</strong>
                  <span>현재 계산에서는 반복 주기나 계절성을 평가하지 않습니다.</span>
                </li>
              ) : null}
            </ul>
          </section>

          <section className="result-section data-result-section">
            <h2>추세</h2>
            {analysis.trend ? (
              <ul className="analysis-list compact">
                <li>
                  <strong>{computedTrendLabel(analysis.trend.pattern)}</strong>
                  <span>
                    {analysis.trend.currentPeriod} {formatComputedNumber(analysis.trend.currentValue)} / 이전 기간 {analysis.trend.previousPeriod} {formatComputedNumber(analysis.trend.previousValue)}
                    {analysis.trend.changeRate !== undefined ? ` (${formatComputedPercent(analysis.trend.changeRate)})` : ""}
                  </span>
                </li>
                {analysis.trend.periods.map((period) => (
                  <li key={period.period}>
                    <strong>{period.period}</strong>
                    <span>{formatComputedNumber(period.value)} / 계산 행 {formatComputedNumber(period.rowCount)}건</span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty-text">시간 컬럼을 선택하면 기간별 추세를 계산합니다.</p>}
          </section>

          <section className="result-section data-result-section">
            <h2>그룹 비교</h2>
            {analysis.comparisons.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.comparisons.slice(0, 10).map((comparison) => (
                  <li key={comparison.factId}>
                    <strong>{comparison.rank}위 {comparison.group}</strong>
                    <span>
                      {formatComputedNumber(comparison.value)} / 전체 비중 {formatComputedPercent(comparison.ratio)} / 평균 대비 {formatComputedNumber(comparison.differenceFromAverage)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty-text">그룹 컬럼을 선택하면 항목 간 합계와 비중을 비교합니다.</p>}
          </section>

          <section className="result-section data-result-section">
            <h2>이상치 후보</h2>
            {analysis.outliers.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.outliers.map((outlier) => (
                  <li key={outlier.factId}>
                    <strong>{outlier.reason}</strong>
                    <span>
                      {outlier.group ? `${outlier.group} / ` : ""}{outlier.period ? `${outlier.period} / ` : ""}{formatComputedNumber(outlier.value)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty-text">IQR 또는 Z-score 기준을 벗어난 값이 없습니다.</p>}
          </section>

          <section className="result-section data-result-section">
            <h2>계산된 인사이트 후보</h2>
            {analysis.insightCandidates.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.insightCandidates.map((candidate) => (
                  <li key={candidate.id}>
                    <strong>{candidate.title} · 중요도 {computedInsightLabel(candidate.importance)}</strong>
                    <span>{candidate.importanceReasons.join(" / ")}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="empty-text">설정된 계산 기준을 넘는 추세·비교·이상치 후보가 없습니다. AI 인사이트를 강제로 만들지 않습니다.</p>}
          </section>

          <section className="result-section data-result-section wide ai-output-section" aria-live="polite">
            <h2>AI 인사이트</h2>
            <p className="report-help">
              AI는 기계식 후보의 해석, 확인 필요 사항, 제안만 작성합니다. 사실과 수치는 프로그램 계산 결과를 그대로 표시합니다.
            </p>
            {!aiFeatureEnabled ? (
              <p className="empty-text">현재 환경에서는 AI 기능이 비활성화되어 있습니다.</p>
            ) : aiState.status === "idle" ? (
              <p className="empty-text">기계식 계산 결과를 확인한 뒤 AI 해석을 선택 실행할 수 있습니다.</p>
            ) : aiState.status === "loading" ? (
              <p className="developer-text">계산된 인사이트 후보의 해석을 생성하는 중입니다.</p>
            ) : aiState.status === "error" ? (
              <div className="ai-error">
                <p>{aiState.errorMessage}</p>
                <button className="secondary-button" type="button" onClick={() => void requestAiInsights()}>
                  다시 시도
                </button>
              </div>
            ) : (
              <div className="data-ai-insights">
                {aiState.insights.insights.length > 0 ? aiState.insights.insights.map((insight) => {
                  const candidate = analysis.insightCandidates.find((item) => item.id === insight.candidateId);
                  const facts = candidateFacts(analysis, insight.candidateId);

                  return (
                    <section key={insight.candidateId} className="data-ai-insight">
                      <h3>{insight.title}</h3>
                      <p className="data-importance">
                        중요도 {candidate ? computedInsightLabel(candidate.importance) : "계산 결과 확인 필요"}
                        {candidate ? ` · ${candidate.importanceReasons.join(" / ")}` : ""}
                      </p>
                      <div>
                        <strong>관찰된 사실</strong>
                        <ul>{facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
                      </div>
                      <div>
                        <strong>해석</strong>
                        <ul>{insight.interpretation.length > 0 ? insight.interpretation.map((item) => <li key={item}>{item}</li>) : <li>AI 해석이 없습니다.</li>}</ul>
                      </div>
                      <div>
                        <strong>확인 필요 사항</strong>
                        <ul>{insight.checks.length > 0 ? insight.checks.map((item) => <li key={item}>{item}</li>) : <li>추가 확인 항목이 없습니다.</li>}</ul>
                      </div>
                      <div>
                        <strong>제안</strong>
                        <ul>{insight.proposals.length > 0 ? insight.proposals.map((item) => <li key={item}>{item}</li>) : <li>별도 제안이 없습니다.</li>}</ul>
                      </div>
                    </section>
                  );
                }) : <p className="empty-text">AI가 추가 해석이 필요하지 않다고 판단했습니다. 기계식 계산 결과를 확인하세요.</p>}
                <section className="data-ai-conclusion">
                  <h3>결론</h3>
                  <p>{aiState.insights.conclusion}</p>
                </section>
                {[...aiState.insights.uncertaintyNotes, ...aiState.insights.validationWarnings].length > 0 ? (
                  <section className="data-ai-conclusion">
                    <h3>확인 및 주의 사항</h3>
                    <ul>{[...aiState.insights.uncertaintyNotes, ...aiState.insights.validationWarnings].map((item) => <li key={item}>{item}</li>)}</ul>
                  </section>
                ) : null}
              </div>
            )}
          </section>

          <section className="result-section data-result-section wide report-section">
            <div className="report-header">
              <div>
                <h2>복사 가능한 데이터 분석 보고서</h2>
                <p className="report-help">사실, 해석, 확인 필요 사항, 제안을 구분한 Markdown 보고서입니다.</p>
              </div>
              <div className="documentation-actions">
                <button className="secondary-button" type="button" onClick={() => void copyText(markdownReport, "data-insight-report-output").then(setCopyStatus)}>
                  {copyStatus === "copied" ? "복사됨" : copyStatus === "selected" ? "선택됨" : copyStatus === "failed" ? "복사 실패" : "Markdown 복사"}
                </button>
                <button className="secondary-button" type="button" onClick={downloadReport}>
                  Markdown 다운로드
                </button>
              </div>
            </div>
            <textarea
              id="data-insight-report-output"
              className="report-output"
              value={markdownReport}
              readOnly
              aria-label="데이터 분석 Markdown 보고서"
            />
          </section>
        </div>
      ) : null}
    </>
  );
}
