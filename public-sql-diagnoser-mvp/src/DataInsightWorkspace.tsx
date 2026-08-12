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

const AUTO_COLUMN = "__auto__";
const DISABLED_COLUMN = "__none__";

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

const selectedColumn = (current: string, candidates: string[], recommended?: string) => {
  if (current === DISABLED_COLUMN) {
    return "";
  }

  if (current !== AUTO_COLUMN && candidates.includes(current)) {
    return current;
  }

  return recommended && candidates.includes(recommended) ? recommended : "";
};

const selectionSourceLabel = (value: string, selected: string) => {
  if (!selected) {
    return "미감지";
  }

  return value === AUTO_COLUMN ? "자동 감지" : "직접 선택";
};

const selectValue = (value: string, candidates: string[], allowDisabled = false) =>
  value === AUTO_COLUMN || (allowDisabled && value === DISABLED_COLUMN) || candidates.includes(value)
    ? value
    : AUTO_COLUMN;

const confidenceLabel = (confidence: "high" | "low" | "medium") => (
  confidence === "high" ? "높음" : confidence === "medium" ? "보통" : "낮음"
);

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
  const [metricColumn, setMetricColumn] = useState(AUTO_COLUMN);
  const [timeColumn, setTimeColumn] = useState(AUTO_COLUMN);
  const [groupColumn, setGroupColumn] = useState(AUTO_COLUMN);
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
    inspection.columnOptions.editable.metricColumns,
    inspection.columnOptions.recommended.metricColumn,
  );
  const effectiveTimeColumn = selectedColumn(
    timeColumn,
    inspection.columnOptions.editable.timeColumns,
    inspection.columnOptions.recommended.timeColumn,
  );
  const effectiveGroupColumn = selectedColumn(
    groupColumn,
    inspection.columnOptions.editable.groupColumns,
    inspection.columnOptions.recommended.groupColumn,
  );
  const markdownReport = useMemo(
    () => buildDataInsightMarkdownReport(
      analysis,
      aiState.status === "success" ? aiState.insights : undefined,
    ),
    [aiState, analysis],
  );
  const primaryReportFindings = useMemo(
    () => analysis?.reportFindings.slice(0, 3) ?? [],
    [analysis],
  );
  const detectedRoles = [
    {
      column: effectiveTimeColumn,
      label: "시간",
      source: selectionSourceLabel(timeColumn, effectiveTimeColumn),
    },
    {
      column: effectiveMetricColumn,
      label: "핵심 지표",
      source: selectionSourceLabel(metricColumn, effectiveMetricColumn),
    },
    {
      column: effectiveGroupColumn,
      label: "비교 기준",
      source: selectionSourceLabel(groupColumn, effectiveGroupColumn),
    },
  ];

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
    setMetricColumn(AUTO_COLUMN);
    setTimeColumn(AUTO_COLUMN);
    setGroupColumn(AUTO_COLUMN);
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
    setMetricColumn(AUTO_COLUMN);
    setTimeColumn(AUTO_COLUMN);
    setGroupColumn(AUTO_COLUMN);
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
      setCalculationError("숫자 지표를 자동으로 감지하지 못했습니다. 분석 기준 직접 수정에서 지표 컬럼을 선택하세요.");
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

  const applyRecommendedPlan = () => {
    setMetricColumn(AUTO_COLUMN);
    setTimeColumn(AUTO_COLUMN);
    setGroupColumn(AUTO_COLUMN);
    resetComputedResult();
  };

  const requestAiInsights = async () => {
    if (
      !aiFeatureEnabled ||
      !analysis ||
      analysis.reportFindings.length === 0 ||
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

      <section className="data-config-panel" aria-label="자동 분석 제안">
        <div className="data-recommendation-header">
          <div>
            <h2>자동 분석 제안</h2>
            <p>입력 데이터를 먼저 읽고 시간, 수치 지표, 비교 기준을 감지했습니다. 아래 기준으로 바로 분석하거나 필요한 경우에만 수정하세요.</p>
          </div>
          <button className="secondary-button" type="button" disabled={!inspection.ok} onClick={applyRecommendedPlan}>
            추천 기준 적용
          </button>
        </div>
        {inspection.ok ? (
          <>
            <div className="data-role-summary" aria-label="감지한 분석 역할">
              {detectedRoles.map((role) => {
                const profile = inspection.columnOptions.profiles.find((item) => item.column === role.column);

                return (
                  <article key={role.label} className="data-role-item">
                    <strong>{role.label}</strong>
                    <span>{role.column || "감지하지 못함"}</span>
                    <small>
                      {role.source}{profile ? ` · 신뢰도 ${confidenceLabel(profile.confidence)}` : ""}
                    </small>
                    {profile?.reasons[0] ? <p>{profile.reasons[0]}</p> : null}
                  </article>
                );
              })}
            </div>
            {inspection.columnOptions.analysisPlan.aggregationStructure.categoryColumns.length > 0 ? (
              <p className="data-aggregation-note">
                <strong>집계 구조 감지</strong>
                {inspection.columnOptions.analysisPlan.aggregationStructure.categoryColumns.join(" · ")} 기준 / {inspection.columnOptions.analysisPlan.aggregationStructure.levels.map((item) => `수준 ${item.level}: ${formatComputedNumber(item.rowCount)}행`).join(", ")}
                {inspection.columnOptions.analysisPlan.aggregationStructure.aggregateRowCount > 0 ? ` / 전체·합계 행 ${formatComputedNumber(inspection.columnOptions.analysisPlan.aggregationStructure.aggregateRowCount)}행` : ""}
              </p>
            ) : null}
            {inspection.columnOptions.analysisPlan.questionSuggestions.length > 0 ? (
              <section className="data-question-plan" aria-label="추천 분석 질문">
                <h3>추천 분석 질문</h3>
                <ul>
                  {inspection.columnOptions.analysisPlan.questionSuggestions.map((question) => <li key={question}>{question}</li>)}
                </ul>
              </section>
            ) : null}
            {inspection.columnOptions.analysisPlan.warnings.length > 0 ? (
              <ul className="data-plan-warnings">
                {inspection.columnOptions.analysisPlan.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            ) : null}
            <p className="data-config-help">
              감지된 형식: {inspection.format.toUpperCase()} / 행 {formatComputedNumber(inspection.rows.length)}개 / 컬럼 {inspection.columns.join(", ") || "없음"}
            </p>
            <details className="collapsible-section data-config-overrides">
              <summary>
                <span>분석 기준 직접 수정</span>
                <small>자동 감지 결과가 데이터 의미와 다를 때만 수정합니다.</small>
              </summary>
              <div className="collapsible-content">
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
                      value={selectValue(metricColumn, inspection.columnOptions.editable.metricColumns)}
                      onChange={(event) => {
                        setMetricColumn(event.target.value);
                        resetComputedResult();
                      }}
                    >
                      <option value={AUTO_COLUMN}>자동 감지: {effectiveMetricColumn || "결과 없음"}</option>
                      {inspection.columnOptions.editable.metricColumns.map((column) => (
                        <option key={column} value={column}>{column}</option>
                      ))}
                    </select>
                  </label>
                  <label className="data-config-field">
                    <span>시간 컬럼</span>
                    <select
                      value={selectValue(timeColumn, inspection.columnOptions.editable.timeColumns, true)}
                      onChange={(event) => {
                        setTimeColumn(event.target.value);
                        resetComputedResult();
                      }}
                    >
                      <option value={AUTO_COLUMN}>자동 감지: {effectiveTimeColumn || "결과 없음"}</option>
                      <option value={DISABLED_COLUMN}>추세 계산 안 함</option>
                      {inspection.columnOptions.editable.timeColumns.map((column) => (
                        <option key={column} value={column}>{column}</option>
                      ))}
                    </select>
                  </label>
                  <label className="data-config-field">
                    <span>그룹 컬럼</span>
                    <select
                      value={selectValue(groupColumn, inspection.columnOptions.editable.groupColumns, true)}
                      onChange={(event) => {
                        setGroupColumn(event.target.value);
                        resetComputedResult();
                      }}
                    >
                      <option value={AUTO_COLUMN}>자동 감지: {effectiveGroupColumn || "결과 없음"}</option>
                      <option value={DISABLED_COLUMN}>그룹 비교 안 함</option>
                      {inspection.columnOptions.editable.groupColumns.map((column) => (
                        <option key={column} value={column}>{column}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            </details>
          </>
        ) : (
          <p className="data-input-error">{inspection.error}</p>
        )}
      </section>

      <div className="action-row data-action-row">
        <button className="primary-button" type="button" onClick={runCalculation}>
          추천 분석 실행
        </button>
        {aiFeatureEnabled ? (
          <button
            className="secondary-button"
            type="button"
            disabled={!analysis || analysis.reportFindings.length === 0 || aiState.status === "loading"}
            onClick={() => void requestAiInsights()}
          >
            {aiState.status === "loading" ? "AI 문장 보강 중" : "AI로 보고서 문장 보강"}
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

          <section className="result-section data-result-section wide data-report-results">
            <h2>보고서용 핵심 결과</h2>
            <p className="report-help">
              자료에 바로 옮길 수 있도록 기계식 계산 결과를 핵심 사실 중심으로 정리했습니다. 해석과 제안은 필요할 때 AI 보강으로 추가합니다.
            </p>
            {primaryReportFindings.length > 0 ? (
              <div className="data-report-findings">
                {primaryReportFindings.map((finding, index) => (
                  <article key={finding.id} className={`data-report-finding ${finding.type}`}>
                    <span>결과 {index + 1}</span>
                    <h3>{finding.title}</h3>
                    <ul>
                      {finding.statements.map((statement) => <li key={statement}>{statement}</li>)}
                    </ul>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty-text">계산 기준을 넘는 뚜렷한 변화, 비교 결과 또는 추가 확인 항목이 없어 핵심 결과를 별도로 만들지 않았습니다.</p>
            )}
          </section>

          <section className="result-section data-result-section wide data-follow-up-section">
            <h2>다음으로 확인할 질문</h2>
            <p className="report-help">
              현재 계산 결과를 바탕으로 이어서 살펴볼 수 있는 질문입니다. 다른 비교 기준을 선택해 같은 데이터를 다시 계산할 수 있습니다.
            </p>
            {analysis.followUpQuestions.length > 0 ? (
              <ol className="data-follow-up-questions">
                {analysis.followUpQuestions.map((item) => (
                  <li key={item.id}>
                    <strong>{item.question}</strong>
                    <span>{item.rationale}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="empty-text">현재 기준에서 이어서 제안할 분석 질문이 없습니다.</p>
            )}
          </section>

          <section className="result-section data-result-section wide ai-output-section" aria-live="polite">
            <h2>AI 해석 보강</h2>
            <p className="report-help">
              AI는 보고서용 핵심 결과에 해석, 확인 필요 사항, 제안만 덧붙입니다. 사실과 수치는 프로그램 계산 결과를 그대로 표시합니다.
            </p>
            {!aiFeatureEnabled ? (
              <p className="empty-text">현재 환경에서는 AI 기능이 비활성화되어 있습니다.</p>
            ) : aiState.status === "idle" ? (
              <p className="empty-text">AI 해석은 선택 기능입니다. 위 핵심 결과는 AI 없이도 보고서에 포함됩니다.</p>
            ) : aiState.status === "loading" ? (
              <p className="developer-text">보고서용 핵심 결과의 해석을 생성하는 중입니다.</p>
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
                  const finding = analysis.reportFindings.find((item) => item.id === insight.candidateId);
                  const facts = finding?.statements ?? candidateFacts(analysis, insight.candidateId);

                  return (
                    <section key={insight.candidateId} className="data-ai-insight">
                      <h3>{insight.title || finding?.title || "AI 해석"}</h3>
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

          <details className="collapsible-section data-verification-details">
            <summary>
              <span>계산 검증 상세</span>
              <small>기간·그룹·통계 기준과 AI 해석 선택 우선순위를 확인합니다.</small>
            </summary>
            <div className="collapsible-content detail-summary-grid">
              <section className="detail-summary-block wide">
                <h3>계산 기준 및 데이터 범위</h3>
                <ul>
                  <li>
                    <strong>계산 대상</strong>
                    입력 {formatComputedNumber(analysis.calculationBasis.dataQuality.inputRowCount)}행 / 숫자 계산 {formatComputedNumber(analysis.calculationBasis.dataQuality.validMetricRowCount)}행 / 제외 {formatComputedNumber(analysis.calculationBasis.dataQuality.excludedMetricRowCount)}행
                  </li>
                  {analysis.calculationBasis.time ? (
                    <li>
                      <strong>기간별 추세</strong>
                      {analysis.calculationBasis.time.startPeriod} ~ {analysis.calculationBasis.time.endPeriod} / {formatComputedNumber(analysis.calculationBasis.time.periodCount)}개 기간 / {analysis.calculationBasis.time.granularity === "day" ? "일 단위" : analysis.calculationBasis.time.granularity === "month" ? "월 단위" : analysis.calculationBasis.time.granularity === "year" ? "연도 단위" : "혼합 단위"}
                      {analysis.calculationBasis.time.trendAvailability === "insufficient_periods" ? " / 비교 가능한 기간 부족" : ""}
                    </li>
                  ) : null}
                  {analysis.calculationBasis.dataQuality.invalidPeriodRowCount !== undefined ? (
                    <li>
                      <strong>시간 형식 제외</strong>
                      {formatComputedNumber(analysis.calculationBasis.dataQuality.invalidPeriodRowCount)}행
                    </li>
                  ) : null}
                  {analysis.calculationBasis.dataQuality.excludedAggregateRowCount ? (
                    <li>
                      <strong>전체·합계 행 분리</strong>
                      {formatComputedNumber(analysis.calculationBasis.dataQuality.excludedAggregateRowCount)}행은 {analysis.analysisPlan.aggregationStructure.categoryColumns.join(" · ") || "범주"}의 상위 집계 행으로 해석되어 비교와 이상치 계산에서 제외
                    </li>
                  ) : null}
                  {analysis.analysisPlan.aggregationStructure.categoryColumns.length > 0 ? (
                    <li>
                      <strong>집계 수준</strong>
                      {analysis.analysisPlan.aggregationStructure.levels.map((item) => `수준 ${item.level} ${formatComputedNumber(item.rowCount)}행`).join(" / ")}
                    </li>
                  ) : null}
                  {analysis.calculationBasis.comparison ? (
                    <li>
                      <strong>그룹 비교</strong>
                      {formatComputedNumber(analysis.calculationBasis.comparison.groupCount)}개 그룹 합계를 그룹 평균과 비교 / 표시 {formatComputedNumber(analysis.calculationBasis.comparison.displayedGroupCount)}개
                    </li>
                  ) : null}
                  <li>
                    <strong>통계적 추가 확인 값</strong>
                    IQR {analysis.calculationBasis.outlierDetection.iqrMultiplier}배 또는 Z-score {analysis.calculationBasis.outlierDetection.zScoreThreshold} 이상 / {formatComputedNumber(analysis.calculationBasis.outlierDetection.candidateCount)}건
                  </li>
                  {analysis.calculationBasis.time ? (
                    <li>
                      <strong>반복 주기</strong>
                      현재 계산에서는 반복 주기나 계절성을 평가하지 않습니다.
                    </li>
                  ) : null}
                </ul>
              </section>

              <section className="detail-summary-block">
                <h3>기간별 추세 계산</h3>
                {analysis.trend ? (
                  <ul>
                    <li>
                      <strong>{computedTrendLabel(analysis.trend.pattern)}</strong>
                      {analysis.trend.currentPeriod} {formatComputedNumber(analysis.trend.currentValue)} / 이전 기간 {analysis.trend.previousPeriod} {formatComputedNumber(analysis.trend.previousValue)}
                      {analysis.trend.changeRate !== undefined ? ` (${formatComputedPercent(analysis.trend.changeRate)})` : ""}
                    </li>
                    {analysis.trend.periods.map((period) => (
                      <li key={period.period}>
                        <strong>{period.period}</strong>
                        {formatComputedNumber(period.value)} / 계산 행 {formatComputedNumber(period.rowCount)}건
                      </li>
                    ))}
                  </ul>
                ) : <p>시간 컬럼을 선택하면 기간별 추세를 계산합니다.</p>}
              </section>

              <section className="detail-summary-block">
                <h3>그룹 비교 계산</h3>
                {analysis.comparisons.length > 0 ? (
                  <ul>
                    {analysis.comparisons.slice(0, 10).map((comparison) => (
                      <li key={comparison.factId}>
                        <strong>{comparison.rank}위 {comparison.group}</strong>
                        {formatComputedNumber(comparison.value)} / 전체 비중 {formatComputedPercent(comparison.ratio)} / 평균 대비 {formatComputedNumber(comparison.differenceFromAverage)}
                      </li>
                    ))}
                  </ul>
                ) : <p>그룹 컬럼을 선택하면 항목 간 합계와 비중을 비교합니다.</p>}
              </section>

              <section className="detail-summary-block">
                <h3>기간×그룹 변화 분해</h3>
                {analysis.changeContributions.length > 0 && analysis.calculationBasis.crossAnalysis ? (
                  <>
                    <p>
                      {analysis.calculationBasis.crossAnalysis.previousPeriod} → {analysis.calculationBasis.crossAnalysis.currentPeriod} / 비교 가능 그룹 {formatComputedNumber(analysis.calculationBasis.crossAnalysis.comparableGroupCount)}개
                      {analysis.calculationBasis.crossAnalysis.valueCoverage === "partial" ? " / 일부 그룹의 기간 값이 누락되어 비교 가능한 그룹 기준" : " / 전체 그룹 기준"}
                    </p>
                    <ul>
                      {analysis.changeContributions.slice(0, 10).map((contribution) => (
                        <li key={contribution.factId}>
                          <strong>{contribution.group}</strong>
                          {formatComputedNumber(Math.abs(contribution.valueChange))} 변화 / 순변화 대비 {formatComputedPercent(Math.abs(contribution.contributionRate))}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : <p>시간과 그룹 컬럼을 함께 선택하면 두 기간의 변화가 어느 그룹에서 발생했는지 분해합니다.</p>}
              </section>

              <section className="detail-summary-block">
                <h3>통계적 추가 확인 값</h3>
                {analysis.outliers.length > 0 ? (
                  <ul>
                    {analysis.outliers.map((outlier) => (
                      <li key={outlier.factId}>
                        <strong>{outlier.reason}</strong>
                        {outlier.group ? `${outlier.group} / ` : ""}{outlier.period ? `${outlier.period} / ` : ""}{formatComputedNumber(outlier.value)}
                      </li>
                    ))}
                  </ul>
                ) : <p>IQR 또는 Z-score 기준을 벗어난 값이 없습니다.</p>}
              </section>

              <section className="detail-summary-block">
                <h3>AI 해석 선택 우선순위</h3>
                <p>내부 계산 기준입니다. 점수와 선정 사유는 보고서 본문에 표시하지 않습니다.</p>
                {analysis.insightCandidates.length > 0 ? (
                  <ul>
                    {analysis.insightCandidates.map((candidate) => (
                      <li key={candidate.id}>
                        <strong>{candidate.title} · {computedInsightLabel(candidate.importance)}</strong>
                        {candidate.importanceReasons.join(" / ")}
                      </li>
                    ))}
                  </ul>
                ) : <p>AI 해석을 선택할 내부 우선순위가 없습니다.</p>}
              </section>
            </div>
          </details>
        </div>
      ) : null}
    </>
  );
}
