import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { DataInsightWorkspace } from "./DataInsightWorkspace";
import {
  AI_SQL_DOCUMENT_TYPE_OPTIONS,
  type AiSqlDocumentDraft,
  type AiSqlDocumentDraftResponse,
  type AiSqlDocumentType,
} from "./aiDocumentDraft";
import {
  type AiMultiSqlDocumentDraft,
  type AiMultiSqlDocumentDraftResponse,
} from "./aiMultiDocumentDraft";
import type { AiSqlExplainResponse } from "./aiExplanation";
import {
  errorAiExplanationState,
  idleAiExplanationState,
  loadingAiExplanationState,
  preserveAnalysisWithAiError,
  successAiExplanationState,
  type AiExplanationState,
} from "./aiExplanationState";
import {
  analyzeMultipleSql,
  type MultiSqlAnalysisResult,
} from "./multiSqlAnalysis";
import { buildMultiSqlAiAnalysis } from "./multiAiExplanation";
import {
  buildMarkdownReport,
  buildPasteDocument,
  buildPrintableHtmlReport,
  buildRiskFindingsCsv,
  buildSqlExplainerReport,
  buildTableUsageCsv,
  defaultReportOptions,
  type ReportOptions,
} from "./reportModel";
import {
  analyzeSqlRisks,
  type SqlRiskSeverity,
} from "./riskDetector";
import { DEFAULT_SQL, explainSql, type SqlExplanation } from "./sqlExplainer";
import { SQL_PRESETS } from "./sqlPresets";
import {
  analyzeImpact,
  buildSystemGraph,
  getSystemGraphView,
  type ImpactNode,
  type SystemGraphEdge,
  type SystemGraphMode,
  type SystemGraphNode,
} from "./systemGraph";
import {
  buildTableAssetMap,
  type TableAssetProfile,
} from "./tableAssetMap";

const isDemoMode = import.meta.env.VITE_DEMO_MODE === "true";
const buildAiFeatureEnabled = import.meta.env.VITE_ENABLE_AI_FEATURES !== "false";

type ResultSectionProps = {
  title: string;
  children: ReactNode;
  className?: string;
  variant?: "wide";
};

function ResultSection({ title, children, className, variant }: ResultSectionProps) {
  return (
    <section className={`result-section ${variant ?? ""} ${className ?? ""}`.trim()}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

type CollapsibleSectionProps = {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  description?: string;
};

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
  description,
}: CollapsibleSectionProps) {
  return (
    <details className="collapsible-section rule-detail-toggle" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {description ? <small>{description}</small> : null}
      </summary>
      <div className="collapsible-content">{children}</div>
    </details>
  );
}

const confidenceLevelLabel = (level: SqlExplanation["confidence"]["level"]) => {
  if (level === "high") {
    return "높음";
  }

  if (level === "medium") {
    return "보통";
  }

  return "낮음";
};

const joinOrNone = (items: string[]) => items.length > 0 ? items.join(", ") : "없음";

function SingleRuleAnalysisDetails({ analysis }: { analysis: SqlExplanation }) {
  return (
    <div className="detail-summary-grid">
      <section className="detail-summary-block wide">
        <h3>룰 기반 한 줄 설명</h3>
        <p>{analysis.summary}</p>
      </section>
      <section className="detail-summary-block">
        <h3>신뢰도</h3>
        <p>
          {confidenceLevelLabel(analysis.confidence.level)} / 점수 {analysis.confidence.score}
        </p>
        <ul>
          {analysis.confidence.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>사용 테이블</h3>
        <p>{joinOrNone(analysis.tables.map((table) => table.rawName))}</p>
      </section>
      <section className="detail-summary-block">
        <h3>JOIN 관계</h3>
        <ul>
          {analysis.relations.length > 0 ? (
            analysis.relations.map((relation) => (
              <li key={`${relation.left}-${relation.right}`}>
                {relation.left} -&gt; {relation.right}
              </li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>WHERE / HAVING</h3>
        <ul>
          {[...analysis.filters, ...analysis.havingConditions].length > 0 ? (
            [...analysis.filters, ...analysis.havingConditions].map((filter) => (
              <li key={`${filter.stage}-${filter.condition}`}>
                {filter.stage}: {filter.condition}
              </li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>분석 요소</h3>
        <ul>
          <li>CTE {analysis.ctes.length}개</li>
          <li>GROUP BY {analysis.groupBy.length}개</li>
          <li>집계 {analysis.aggregations.length}개</li>
          <li>윈도우 함수 {analysis.windowFunctions.length}개</li>
          <li>CASE {analysis.caseExpressions.length}개</li>
          <li>서브쿼리 {analysis.subqueries.length}개</li>
          <li>SET 연산 {analysis.setOperations.length}개</li>
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>업무 추정 근거</h3>
        <ul>
          {analysis.businessIntent.reasons.length > 0 ? (
            analysis.businessIntent.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block wide">
        <h3>주의 사항</h3>
        <ul>
          {[...analysis.notes, ...analysis.warnings].length > 0 ? (
            [...analysis.notes, ...analysis.warnings].map((warning) => (
              <li key={warning}>{warning}</li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
    </div>
  );
}

function MultiRuleAnalysisDetails({
  multiAnalysis,
}: {
  multiAnalysis: MultiSqlAnalysisResult;
}) {
  return (
    <div className="detail-summary-grid">
      <section className="detail-summary-block wide">
        <h3>SQL별 룰 기반 요약</h3>
        {multiAnalysis.statements.length > 0 ? (
          <ol>
            {multiAnalysis.statements.map((statement) => (
              <li key={statement.id}>
                <strong>{statement.id}</strong>
                <span>{statement.analysis?.summary ?? statement.error}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p>분석할 SQL이 없습니다.</p>
        )}
      </section>
      <section className="detail-summary-block">
        <h3>테이블 사용 현황</h3>
        <ul>
          {multiAnalysis.tableUsage.length > 0 ? (
            multiAnalysis.tableUsage.map((table) => (
              <li key={`${table.schemaNames.join(".")}-${table.tableName}`}>
                {table.tableName}: {table.count}회
              </li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>반복 JOIN 관계</h3>
        <ul>
          {multiAnalysis.joinUsage.length > 0 ? (
            multiAnalysis.joinUsage.map((join) => (
              <li key={`${join.left}-${join.right}`}>
                {join.left} -&gt; {join.right}: {join.count}회
              </li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>반복 조건 패턴</h3>
        <ul>
          {multiAnalysis.conditionUsage.length > 0 ? (
            multiAnalysis.conditionUsage.map((condition) => (
              <li key={condition.normalizedCondition}>
                {condition.normalizedCondition}: {condition.count}회
              </li>
            ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block">
        <h3>업무 목적 분포</h3>
        <ul>
          {Object.keys(multiAnalysis.businessIntentSummary).length > 0 ? (
            Object.entries(multiAnalysis.businessIntentSummary)
              .sort(([, leftCount], [, rightCount]) => rightCount - leftCount)
              .map(([type, count]) => (
                <li key={type}>
                  {type}: {count}개
                </li>
              ))
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
      <section className="detail-summary-block wide">
        <h3>다건 분석 주의 사항</h3>
        <ul>
          {multiAnalysis.warnings.length > 0 ? (
            multiAnalysis.warnings.map((warning) => <li key={warning}>{warning}</li>)
          ) : (
            <li>없음</li>
          )}
        </ul>
      </section>
    </div>
  );
}

type AnalysisMode = "single" | "multi" | "data";
type CopyResult = "copied" | "selected" | "failed";
type CopyStatus = "idle" | CopyResult;
type RiskFilter = "all" | SqlRiskSeverity;
type ReportActionStatus =
  | "idle"
  | "markdown"
  | "csv"
  | "pdf"
  | "notion"
  | "confluence"
  | "failed";
type AiDocumentDraftState =
  | { status: "idle"; draft?: undefined; errorMessage?: undefined }
  | { status: "loading"; draft?: undefined; errorMessage?: undefined }
  | { status: "success"; draft: AiSqlDocumentDraft; errorMessage?: undefined }
  | { status: "error"; draft?: undefined; errorMessage: string };
type AiMultiDocumentDraftState =
  | { status: "idle"; draft?: undefined; errorMessage?: undefined }
  | { status: "loading"; draft?: undefined; errorMessage?: undefined }
  | { status: "success"; draft: AiMultiSqlDocumentDraft; errorMessage?: undefined }
  | { status: "error"; draft?: undefined; errorMessage: string };
type DemoAccessState = {
  aiConfigured: boolean;
  authenticated: boolean;
  loginRequired: boolean;
  status: "checking" | "public" | "unauthenticated" | "authenticated";
  username?: string;
};
type RuntimeConfig = {
  aiConfigured: boolean;
  aiEnabled: boolean;
  authenticated: boolean;
  loginRequired: boolean;
  username?: string;
};

const readRuntimeConfig = (value: unknown): RuntimeConfig | undefined => {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  const config = value as {
    aiConfigured?: unknown;
    aiEnabled?: unknown;
    authenticated?: unknown;
    loginRequired?: unknown;
    username?: unknown;
  };

  if (typeof config.aiEnabled !== "boolean") {
    return undefined;
  }

  return {
    aiConfigured: config.aiConfigured === true,
    aiEnabled: config.aiEnabled,
    authenticated: config.authenticated === true,
    loginRequired: config.loginRequired === true,
    username: typeof config.username === "string" ? config.username : undefined,
  };
};

type DemoLoginScreenProps = {
  errorMessage?: string;
  isChecking?: boolean;
  isSubmitting: boolean;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onUsernameChange: (value: string) => void;
  password: string;
  username: string;
};

function DemoLoginScreen({
  errorMessage,
  isChecking = false,
  isSubmitting,
  onPasswordChange,
  onSubmit,
  onUsernameChange,
  password,
  username,
}: DemoLoginScreenProps) {
  return (
    <main className="demo-login-shell">
      <section className="demo-login-panel" aria-labelledby="demo-login-title">
        <p className="eyebrow">Protected SQL Diagnoser</p>
        <h1 id="demo-login-title">테스트 계정 로그인</h1>
        <p className="demo-login-description">
          지정된 테스트 계정으로 로그인하면 AI 설명 보강과 문서 초안을 사용할 수 있습니다.
        </p>

        {isChecking ? (
          <p className="demo-login-checking" role="status">접근 상태를 확인하고 있습니다.</p>
        ) : (
          <form className="demo-login-form" onSubmit={onSubmit}>
            <label htmlFor="demo-username">
              아이디
              <input
                id="demo-username"
                autoComplete="username"
                disabled={isSubmitting}
                value={username}
                onChange={(event) => onUsernameChange(event.target.value)}
              />
            </label>
            <label htmlFor="demo-password">
              비밀번호
              <input
                id="demo-password"
                autoComplete="current-password"
                disabled={isSubmitting}
                type="password"
                value={password}
                onChange={(event) => onPasswordChange(event.target.value)}
              />
            </label>
            {errorMessage ? <p className="demo-login-error" role="alert">{errorMessage}</p> : null}
            <button className="primary-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "로그인 확인 중" : "로그인"}
            </button>
          </form>
        )}

        <p className="demo-login-help">
          테스트 계정이 없거나 로그인할 수 없으면 데모 관리자에게 요청하세요.
        </p>
      </section>
    </main>
  );
}

const tableAssetImportanceLabel = (importance: TableAssetProfile["importance"]) => {
  if (importance === "high") {
    return "핵심";
  }

  if (importance === "medium") {
    return "중요";
  }

  return "일반";
};

const tableAssetRoleLabel = (role: TableAssetProfile["role"]) => {
  const labels: Record<TableAssetProfile["role"], string> = {
    core: "핵심",
    log: "로그",
    mapping: "매핑",
    master: "마스터",
    reference: "참조",
    report: "리포트/적재",
    staging: "스테이징",
    transaction: "거래",
    unknown: "미분류",
  };

  return labels[role];
};

const systemGraphModes: Array<{ label: string; mode: SystemGraphMode }> = [
  { label: "전체", mode: "overview" },
  { label: "테이블 관계", mode: "table_relations" },
  { label: "SQL 의존성", mode: "sql_dependencies" },
  { label: "CTE 흐름", mode: "cte_flow" },
  { label: "적재 흐름", mode: "load_flow" },
];

const systemNodeTypeLabel = (type: SystemGraphNode["type"]) => {
  const labels: Record<SystemGraphNode["type"], string> = {
    cte: "CTE",
    procedure: "Procedure",
    sql: "SQL",
    table: "Table",
    view: "View",
  };

  return labels[type];
};

const systemEdgeTypeLabel = (type: SystemGraphEdge["type"]) => {
  const labels: Record<SystemGraphEdge["type"], string> = {
    calls: "호출",
    depends_on: "의존",
    filters: "조건",
    joins: "JOIN",
    reads: "읽음",
    transforms_to: "변환/적재",
    writes: "쓰기",
  };

  return labels[type];
};

const reportActionStatusText = (status: ReportActionStatus) => {
  const labels: Record<ReportActionStatus, string> = {
    confluence: "Confluence용 문서를 클립보드에 복사했습니다.",
    csv: "Excel용 CSV 파일을 다운로드했습니다.",
    failed: "보고서 작업에 실패했습니다. 브라우저 팝업 또는 클립보드 권한을 확인하세요.",
    idle: "보고서 옵션을 선택한 뒤 필요한 형식으로 내보낼 수 있습니다.",
    markdown: "Markdown 보고서를 다운로드했습니다.",
    notion: "Notion용 문서를 클립보드에 복사했습니다.",
    pdf: "PDF 저장용 인쇄 화면을 열었습니다.",
  };

  return labels[status];
};

const riskSeverityLabel = (severity: SqlRiskSeverity) => {
  const labels: Record<SqlRiskSeverity, string> = {
    critical: "치명",
    high: "높음",
    low: "낮음",
    medium: "보통",
  };

  return labels[severity];
};

const riskFilterOptions: Array<{ label: string; value: RiskFilter }> = [
  { label: "전체", value: "all" },
  { label: "치명", value: "critical" },
  { label: "높음", value: "high" },
  { label: "보통", value: "medium" },
  { label: "낮음", value: "low" },
];

const DEFAULT_MULTI_SQL = SQL_PRESETS
  .filter((preset) =>
    ["simple-order-list", "product-sales-summary", "cte-monthly-sales", "insert-select-batch", "union-orders"].includes(preset.id),
  )
  .map((preset) => preset.sql)
  .join("\n\n");

function App() {
  const [runtimeAiFeatureEnabled, setRuntimeAiFeatureEnabled] =
    useState(buildAiFeatureEnabled);
  const [demoAccessState, setDemoAccessState] = useState<DemoAccessState>(() => ({
    aiConfigured: false,
    authenticated: false,
    loginRequired: false,
    status: isDemoMode ? "checking" : "public",
  }));
  const [demoUsername, setDemoUsername] = useState("");
  const [demoPassword, setDemoPassword] = useState("");
  const [demoLoginState, setDemoLoginState] = useState<{
    errorMessage?: string;
    status: "idle" | "loading";
  }>({ status: "idle" });
  const [demoLogoutState, setDemoLogoutState] = useState<"idle" | "loading" | "error">("idle");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("single");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [multiSql, setMultiSql] = useState(DEFAULT_MULTI_SQL);
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [analysis, setAnalysis] = useState<SqlExplanation>(() =>
    explainSql(DEFAULT_SQL),
  );
  const [multiAnalysis, setMultiAnalysis] = useState<MultiSqlAnalysisResult>(() =>
    analyzeMultipleSql(DEFAULT_MULTI_SQL),
  );
  const [aiState, setAiState] = useState<AiExplanationState>(() =>
    idleAiExplanationState(),
  );
  const [multiAiState, setMultiAiState] = useState<AiExplanationState>(() =>
    idleAiExplanationState(),
  );
  const [aiDocumentType, setAiDocumentType] =
    useState<AiSqlDocumentType>("onboarding");
  const [aiDocumentDraftState, setAiDocumentDraftState] =
    useState<AiDocumentDraftState>({ status: "idle" });
  const [documentDraftCopyStatus, setDocumentDraftCopyStatus] =
    useState<CopyStatus>("idle");
  const [multiAiDocumentType, setMultiAiDocumentType] =
    useState<AiSqlDocumentType>("asset_analysis");
  const [multiAiDocumentDraftState, setMultiAiDocumentDraftState] =
    useState<AiMultiDocumentDraftState>({ status: "idle" });
  const [multiDocumentDraftCopyStatus, setMultiDocumentDraftCopyStatus] =
    useState<CopyStatus>("idle");
  const [copyStatus, setCopyStatus] = useState<
    "idle" | "copied" | "selected" | "failed"
  >("idle");
  const [reportActionStatus, setReportActionStatus] =
    useState<ReportActionStatus>("idle");
  const [reportOptions, setReportOptions] =
    useState<ReportOptions>(defaultReportOptions);
  const [selectedTableAssetKey, setSelectedTableAssetKey] = useState("");
  const [systemGraphMode, setSystemGraphMode] = useState<SystemGraphMode>("overview");
  const [selectedSystemNodeId, setSelectedSystemNodeId] = useState("");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const isAiFeatureEnabled = runtimeAiFeatureEnabled;

  const applyRuntimeConfig = useCallback((config: RuntimeConfig) => {
    setRuntimeAiFeatureEnabled(config.aiEnabled);
    setDemoAccessState({
      aiConfigured: config.aiConfigured,
      authenticated: config.authenticated,
      loginRequired: config.loginRequired,
      status: config.loginRequired
        ? config.authenticated ? "authenticated" : "unauthenticated"
        : "public",
      username: config.username,
    });
  }, []);

  const refreshDemoRuntimeConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/runtime-config", {
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("runtime config unavailable");
      }

      const config = readRuntimeConfig(await response.json());

      if (!config) {
        throw new Error("runtime config invalid");
      }

      applyRuntimeConfig(config);
      return config;
    } catch {
      // Static-only and local Vite deployments retain build-time AI behavior.
      setRuntimeAiFeatureEnabled(buildAiFeatureEnabled);
      setDemoAccessState({
        aiConfigured: false,
        authenticated: false,
        loginRequired: false,
        status: "public",
      });
      return undefined;
    }
  }, [applyRuntimeConfig]);

  useEffect(() => {
    void refreshDemoRuntimeConfig();
  }, [refreshDemoRuntimeConfig]);
  const hasSingleAiRepresentative =
    aiState.status === "success" || aiDocumentDraftState.status === "success";
  const hasMultiAiRepresentative =
    multiAiState.status === "success" || multiAiDocumentDraftState.status === "success";

  const tableAssetMap = useMemo(
    () => buildTableAssetMap(multiAnalysis),
    [multiAnalysis],
  );
  const selectedTableAsset =
    tableAssetMap.tables.find((table) => table.key === selectedTableAssetKey) ??
    tableAssetMap.tables[0];
  const systemGraph = useMemo(
    () => buildSystemGraph(multiAnalysis),
    [multiAnalysis],
  );
  const sqlRiskAnalysis = useMemo(
    () => analyzeSqlRisks(multiAnalysis),
    [multiAnalysis],
  );
  const filteredRiskFindings = useMemo(
    () =>
      riskFilter === "all"
        ? sqlRiskAnalysis.findings
        : sqlRiskAnalysis.findings.filter((finding) => finding.severity === riskFilter),
    [riskFilter, sqlRiskAnalysis],
  );
  const systemGraphView = useMemo(
    () => getSystemGraphView(systemGraph, systemGraphMode),
    [systemGraph, systemGraphMode],
  );
  const systemGraphNodeMap = useMemo(
    () => new Map(systemGraph.nodes.map((node) => [node.id, node])),
    [systemGraph],
  );
  const primarySystemNode = useMemo(() => {
    const incidentCount = (nodeId: string) =>
      systemGraph.edges.filter((edge) => edge.from === nodeId || edge.to === nodeId).length;
    const tableNodes = systemGraph.nodes.filter((node) => node.type === "table");

    return (
      [...tableNodes].sort((left, right) => {
        const countDiff = incidentCount(right.id) - incidentCount(left.id);

        return countDiff === 0 ? left.label.localeCompare(right.label) : countDiff;
      })[0] ?? systemGraph.nodes[0]
    );
  }, [systemGraph]);
  const selectedSystemNode =
    systemGraph.nodes.find((node) => node.id === selectedSystemNodeId) ??
    primarySystemNode;
  const selectedSystemNodeIdForImpact = selectedSystemNode?.id;
  const selectedSystemImpact = useMemo(
    () =>
      selectedSystemNodeIdForImpact
        ? analyzeImpact(systemGraph, selectedSystemNodeIdForImpact, {
            direction: "both",
            maxDepth: 3,
          })
        : undefined,
    [selectedSystemNodeIdForImpact, systemGraph],
  );
  const reportAiExplanation =
    reportOptions.includeAiExplanation && multiAiState.status === "success"
      ? multiAiState.explanation
      : undefined;
  const reportAiDocumentDraft =
    reportOptions.includeAiDocumentDraft && multiAiDocumentDraftState.status === "success"
      ? multiAiDocumentDraftState.draft
      : undefined;
  const documentationReport = useMemo(
    () =>
      buildSqlExplainerReport({
        aiDocumentDraft: reportAiDocumentDraft,
        aiExplanation: reportAiExplanation,
        multiAnalysis,
        options: reportOptions,
        riskAnalysis: sqlRiskAnalysis,
        systemGraph,
        tableAssetMap,
      }),
    [
      multiAnalysis,
      reportAiDocumentDraft,
      reportAiExplanation,
      reportOptions,
      sqlRiskAnalysis,
      systemGraph,
      tableAssetMap,
    ],
  );
  const markdownReportText = useMemo(
    () => buildMarkdownReport(documentationReport),
    [documentationReport],
  );
  const notionReportText = useMemo(
    () => buildPasteDocument(documentationReport, "notion"),
    [documentationReport],
  );
  const confluenceReportText = useMemo(
    () => buildPasteDocument(documentationReport, "confluence"),
    [documentationReport],
  );
  const tableUsageCsv = useMemo(
    () => buildTableUsageCsv(documentationReport),
    [documentationReport],
  );
  const riskFindingsCsv = useMemo(
    () => buildRiskFindingsCsv(documentationReport),
    [documentationReport],
  );
  const printableReportHtml = useMemo(
    () => buildPrintableHtmlReport(documentationReport),
    [documentationReport],
  );

  const reportText = useMemo(() => {
    if (analysisMode === "multi") {
      return markdownReportText;
    }

    const tableLines =
      analysis.tables.length > 0
        ? analysis.tables
            .map((table) => {
              const raw = table.rawName !== table.tableName ? ` (${table.rawName})` : "";
              const schema = table.schemaName ? ` / 스키마: ${table.schemaName}` : "";
              const source = table.source === "subquery" ? " / 출처: 서브쿼리" : "";
              return `- ${table.tableName}${raw} : ${table.description}${schema}${source}`;
            })
            .join("\n")
        : "- 사용 테이블을 찾지 못했습니다.";
    const relationLines =
      analysis.relations.length > 0
        ? analysis.relations
            .map((relation) => `${relation.left}\n↓\n${relation.right}`)
            .join("\n\n")
        : "JOIN 관계를 찾지 못했습니다.";
    const whereLines =
      analysis.filters.length > 0
        ? analysis.filters
            .map((filter) => `- ${filter.stage}: ${filter.condition}\n  ${filter.description}`)
            .join("\n")
        : "- WHERE 조건이 없습니다.";
    const havingLines =
      analysis.havingConditions.length > 0
        ? analysis.havingConditions
            .map((filter) => `- ${filter.stage}: ${filter.condition}\n  ${filter.description}`)
            .join("\n")
        : "- HAVING 조건이 없습니다.";
    const cteLines =
      analysis.ctes.length > 0
        ? analysis.ctes
            .map((cte) => {
              const dependencies =
                cte.dependencies.length > 0
                  ? `\n  의존: ${cte.dependencies.join(", ")}`
                  : "";
              return `- ${cte.name}: ${cte.role}${dependencies}`;
            })
            .join("\n")
        : "- CTE가 없습니다.";
    const groupByLines =
      analysis.groupBy.length > 0
        ? analysis.groupBy
            .map((group) => `- ${group.stage}: ${group.columns.join(", ")}`)
            .join("\n")
        : "- GROUP BY가 없습니다.";
    const aggregationLines =
      analysis.aggregations.length > 0
        ? analysis.aggregations
            .map((aggregation) => `- ${aggregation.stage}: ${aggregation.description}`)
            .join("\n")
        : "- 집계 지표가 없습니다.";
    const windowLines =
      analysis.windowFunctions.length > 0
        ? analysis.windowFunctions
            .map((windowFunction) => `- ${windowFunction.stage}: ${windowFunction.description}`)
            .join("\n")
        : "- 윈도우 함수가 없습니다.";
    const caseLines =
      analysis.caseExpressions.length > 0
        ? analysis.caseExpressions
            .map((caseExpression) => {
              const rules = caseExpression.rules
                .map((rule) => `  - ${rule}`)
                .join("\n");
              return `- ${caseExpression.stage}: ${caseExpression.description}\n${rules}`;
            })
            .join("\n")
        : "- CASE 문이 없습니다.";
    const businessLines = analysis.businessGuesses
      .map((guess) => `- ${guess}`)
      .join("\n");
    const subqueryLines =
      analysis.subqueries.length > 0
        ? analysis.subqueries
            .map((subquery) => {
              const tables =
                subquery.tables.length > 0
                  ? `\n  테이블: ${subquery.tables.join(", ")}`
                  : "";
              return `- ${subquery.type}: ${subquery.description}${tables}`;
            })
            .join("\n")
        : "- 서브쿼리가 없습니다.";
    const setOperationLines =
      analysis.setOperations.length > 0
        ? analysis.setOperations
            .map((operation) => `- ${operation.operator}: ${operation.description}`)
            .join("\n")
        : "- UNION/EXCEPT/INTERSECT가 없습니다.";
    const confidenceLines = [
      `- ${confidenceLevelLabel(analysis.confidence.level)} (${analysis.confidence.score})`,
      ...analysis.confidence.reasons.map((reason) => `- 근거: ${reason}`),
    ].join("\n");
    const reasonLines =
      analysis.businessIntent.reasons.length > 0
        ? analysis.businessIntent.reasons.map((reason) => `- ${reason}`).join("\n")
        : "- 별도 업무 목적 근거가 없습니다.";
    const noteLines =
      analysis.notes.length > 0 || analysis.warnings.length > 0
        ? [...analysis.notes, ...analysis.warnings].map((note) => `- ${note}`).join("\n")
        : "- 별도 주의 사항이 없습니다.";
    const aiDocumentDraftLines =
      aiDocumentDraftState.status === "success"
        ? ["", "AI 문서 초안", aiDocumentDraftState.draft.markdown]
        : [];

    return [
      "한 줄 설명",
      analysis.summary,
      "",
      "사용 테이블",
      tableLines,
      "",
      "JOIN 관계",
      relationLines,
      "",
      "CTE 처리 흐름",
      cteLines,
      "",
      "WHERE 조건",
      whereLines,
      "",
      "HAVING 조건",
      havingLines,
      "",
      "GROUP BY / 집계 기준",
      groupByLines,
      "",
      "집계 지표",
      aggregationLines,
      "",
      "윈도우 함수 분석",
      windowLines,
      "",
      "CASE / 파생 컬럼",
      caseLines,
      "",
      "서브쿼리",
      subqueryLines,
      "",
      "SET 연산",
      setOperationLines,
      "",
      "최종 조회 결과",
      analysis.finalResult,
      "",
      "업무 추정",
      businessLines,
      "",
      "분석 신뢰도",
      confidenceLines,
      "",
      "추정 근거",
      reasonLines,
      "",
      "신규 개발자 설명",
      analysis.developerExplanation,
      "",
      "주의 사항",
      noteLines,
      ...aiDocumentDraftLines,
    ].join("\n");
  }, [aiDocumentDraftState, analysis, analysisMode, markdownReportText]);

  const runAnalysis = () => {
    setAnalysis(explainSql(sql));
    setAiState(idleAiExplanationState());
    setAiDocumentDraftState({ status: "idle" });
    setDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const runMultiAnalysis = () => {
    setMultiAnalysis(analyzeMultipleSql(multiSql));
    setSelectedTableAssetKey("");
    setSelectedSystemNodeId("");
    setRiskFilter("all");
    setMultiAiState(idleAiExplanationState());
    setMultiAiDocumentDraftState({ status: "idle" });
    setMultiDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const updateSingleSql = (nextSql: string) => {
    setSql(nextSql);
    setSelectedPresetId("");
    setAiState(idleAiExplanationState());
    setAiDocumentDraftState({ status: "idle" });
    setDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const updateMultiSql = (nextSql: string) => {
    setMultiSql(nextSql);
    setMultiAiState(idleAiExplanationState());
    setMultiAiDocumentDraftState({ status: "idle" });
    setMultiDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const loadMultiSample = () => {
    setMultiSql(DEFAULT_MULTI_SQL);
    setMultiAnalysis(analyzeMultipleSql(DEFAULT_MULTI_SQL));
    setSelectedTableAssetKey("");
    setSelectedSystemNodeId("");
    setRiskFilter("all");
    setMultiAiState(idleAiExplanationState());
    setMultiAiDocumentDraftState({ status: "idle" });
    setMultiDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const changeAnalysisMode = (mode: AnalysisMode) => {
    setAnalysisMode(mode);
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const loadPreset = (presetId: string) => {
    setSelectedPresetId(presetId);

    const preset = SQL_PRESETS.find((candidate) => candidate.id === presetId);

    if (!preset) {
      return;
    }

    setSql(preset.sql);
    setAiState(idleAiExplanationState());
    setAiDocumentDraftState({ status: "idle" });
    setDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const requestAiExplanation = async () => {
    const trimmedSql = sql.trim();

    if (!isAiFeatureEnabled || !trimmedSql || aiState.status === "loading") {
      return;
    }

    const latestAnalysis = explainSql(trimmedSql);
    setAnalysis(latestAnalysis);
    setAiState(loadingAiExplanationState());
    setCopyStatus("idle");
    setReportActionStatus("idle");

    try {
      const response = await fetch("/api/ai-explain", {
        body: JSON.stringify({
          analysis: latestAnalysis,
          sql: trimmedSql,
        }),
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const responseBody = await response.json();

      if (!response.ok) {
        const errorMessage =
          typeof responseBody?.error === "string"
            ? responseBody.error
            : "AI 설명 보강 요청에 실패했습니다.";
        throw new Error(errorMessage);
      }

      const data = responseBody as AiSqlExplainResponse;
      setAiState(successAiExplanationState(data.explanation));
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : "AI 설명 보강 요청에 실패했습니다.";
      const failedState = preserveAnalysisWithAiError(latestAnalysis, errorMessage);

      setAnalysis(failedState.analysis);
      setAiState(failedState.aiState);
    }
  };

  const retryAiExplanation = () => {
    void requestAiExplanation();
  };

  const requestMultiAiExplanation = async () => {
    const trimmedSql = multiSql.trim();

    if (!isAiFeatureEnabled || !trimmedSql || multiAiState.status === "loading") {
      return;
    }

    const latestMultiAnalysis = analyzeMultipleSql(trimmedSql);
    const latestRiskAnalysis = analyzeSqlRisks(latestMultiAnalysis);
    const aiAnalysis = buildMultiSqlAiAnalysis(latestMultiAnalysis, latestRiskAnalysis);

    setMultiAnalysis(latestMultiAnalysis);
    setRiskFilter("all");
    setMultiAiState(loadingAiExplanationState());
    setCopyStatus("idle");
    setReportActionStatus("idle");

    try {
      const response = await fetch("/api/ai-explain", {
        body: JSON.stringify({
          analysis: aiAnalysis,
          sql: trimmedSql,
        }),
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const responseBody = await response.json();

      if (!response.ok) {
        const errorMessage =
          typeof responseBody?.error === "string"
            ? responseBody.error
            : "다건 AI 설명 보강 요청에 실패했습니다.";
        throw new Error(errorMessage);
      }

      const data = responseBody as AiSqlExplainResponse;
      setMultiAiState(successAiExplanationState(data.explanation));
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : "다건 AI 설명 보강 요청에 실패했습니다.";

      setMultiAiState(errorAiExplanationState(errorMessage));
    }
  };

  const retryMultiAiExplanation = () => {
    void requestMultiAiExplanation();
  };

  const requestAiDocumentDraft = async () => {
    const trimmedSql = sql.trim();

    if (!isAiFeatureEnabled || !trimmedSql || aiDocumentDraftState.status === "loading") {
      return;
    }

    const latestAnalysis = explainSql(trimmedSql);
    setAnalysis(latestAnalysis);
    setAiDocumentDraftState({ status: "loading" });
    setDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");

    try {
      const response = await fetch("/api/ai-document-draft", {
        body: JSON.stringify({
          analysis: latestAnalysis,
          documentType: aiDocumentType,
          sql: trimmedSql,
        }),
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const responseBody = await response.json();

      if (!response.ok) {
        const errorMessage =
          typeof responseBody?.error === "string"
            ? responseBody.error
            : "AI 문서 초안 생성 요청에 실패했습니다.";
        throw new Error(errorMessage);
      }

      const data = responseBody as AiSqlDocumentDraftResponse;
      setAiDocumentDraftState({
        draft: data.draft,
        status: "success",
      });
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : "AI 문서 초안 생성 요청에 실패했습니다.";

      setAiDocumentDraftState({
        errorMessage,
        status: "error",
      });
    }
  };

  const retryAiDocumentDraft = () => {
    void requestAiDocumentDraft();
  };

  const requestMultiAiDocumentDraft = async () => {
    const trimmedSql = multiSql.trim();

    if (!isAiFeatureEnabled || !trimmedSql || multiAiDocumentDraftState.status === "loading") {
      return;
    }

    const latestMultiAnalysis = analyzeMultipleSql(trimmedSql);
    setMultiAnalysis(latestMultiAnalysis);
    setRiskFilter("all");
    setMultiAiDocumentDraftState({ status: "loading" });
    setMultiDocumentDraftCopyStatus("idle");
    setCopyStatus("idle");
    setReportActionStatus("idle");

    try {
      const response = await fetch("/api/ai-multi-document-draft", {
        body: JSON.stringify({
          documentType: multiAiDocumentType,
          sql: trimmedSql,
        }),
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const responseBody = await response.json();

      if (!response.ok) {
        const errorMessage =
          typeof responseBody?.error === "string"
            ? responseBody.error
            : "AI 다건 문서 초안 생성 요청에 실패했습니다.";
        throw new Error(errorMessage);
      }

      const data = responseBody as AiMultiSqlDocumentDraftResponse;
      setMultiAiDocumentDraftState({
        draft: data.draft,
        status: "success",
      });
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : "AI 다건 문서 초안 생성 요청에 실패했습니다.";

      setMultiAiDocumentDraftState({
        errorMessage,
        status: "error",
      });
    }
  };

  const retryMultiAiDocumentDraft = () => {
    void requestMultiAiDocumentDraft();
  };

  const updateReportOption = (
    optionName: keyof ReportOptions,
    checked: boolean,
  ) => {
    setReportOptions((currentOptions) => ({
      ...currentOptions,
      [optionName]: checked,
    }));
    setCopyStatus("idle");
    setReportActionStatus("idle");
  };

  const downloadTextFile = (
    fileName: string,
    content: string,
    mimeType: string,
  ) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const copyTextToClipboard = async (
    text: string,
    fallbackElementId?: string,
  ): Promise<CopyResult> => {
    try {
      await navigator.clipboard.writeText(text);
      return "copied";
    } catch {
      const reportElement = fallbackElementId
        ? document.getElementById(fallbackElementId)
        : undefined;

      if (reportElement instanceof HTMLTextAreaElement) {
        reportElement.focus();
        reportElement.select();

        try {
          return document.execCommand("copy") ? "copied" : "selected";
        } catch {
          return "selected";
        }
      }

      const temporaryElement = document.createElement("textarea");
      temporaryElement.value = text;
      temporaryElement.setAttribute("readonly", "true");
      temporaryElement.style.position = "fixed";
      temporaryElement.style.left = "-9999px";
      document.body.appendChild(temporaryElement);
      temporaryElement.select();

      try {
        return document.execCommand("copy") ? "copied" : "failed";
      } catch {
        return "failed";
      } finally {
        temporaryElement.remove();
      }
    }
  };

  const downloadMarkdownReport = () => {
    downloadTextFile(
      "sql-explainer-report.md",
      markdownReportText,
      "text/markdown;charset=utf-8",
    );
    setReportActionStatus("markdown");
  };

  const downloadTableUsageCsv = () => {
    downloadTextFile(
      "sql-table-usage.csv",
      `\uFEFF${tableUsageCsv}`,
      "text/csv;charset=utf-8",
    );
    setReportActionStatus("csv");
  };

  const downloadRiskFindingsCsv = () => {
    downloadTextFile(
      "sql-risk-findings.csv",
      `\uFEFF${riskFindingsCsv}`,
      "text/csv;charset=utf-8",
    );
    setReportActionStatus("csv");
  };

  const openPrintableReport = () => {
    const reportWindow = window.open("", "_blank");

    if (!reportWindow) {
      setReportActionStatus("failed");
      return;
    }

    reportWindow.document.open();
    reportWindow.document.write(printableReportHtml);
    reportWindow.document.close();
    reportWindow.focus();
    window.setTimeout(() => reportWindow.print(), 250);
    setReportActionStatus("pdf");
  };

  const copyPasteReport = async (target: "notion" | "confluence") => {
    const result = await copyTextToClipboard(
      target === "notion" ? notionReportText : confluenceReportText,
    );

    setReportActionStatus(result === "failed" ? "failed" : target);
  };

  const copyReport = async () => {
    setCopyStatus(await copyTextToClipboard(reportText, "report-output"));
  };

  const copyAiDocumentDraftMarkdown = async () => {
    if (aiDocumentDraftState.status !== "success") {
      return;
    }

    setDocumentDraftCopyStatus(
      await copyTextToClipboard(
        aiDocumentDraftState.draft.markdown,
        "ai-document-draft-markdown",
      ),
    );
  };

  const copyMultiAiDocumentDraftMarkdown = async () => {
    if (multiAiDocumentDraftState.status !== "success") {
      return;
    }

    setMultiDocumentDraftCopyStatus(
      await copyTextToClipboard(
        multiAiDocumentDraftState.draft.markdown,
        "multi-ai-document-draft-markdown",
      ),
    );
  };

  const submitDemoLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!demoUsername.trim() || !demoPassword) {
      setDemoLoginState({
        errorMessage: "아이디와 비밀번호를 모두 입력하세요.",
        status: "idle",
      });
      return;
    }

    setDemoLoginState({ status: "loading" });

    try {
      const response = await fetch("/api/auth/login", {
        body: JSON.stringify({
          password: demoPassword,
          username: demoUsername.trim(),
        }),
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
        method: "POST",
      });
      const body = await response.json().catch(() => undefined);

      if (!response.ok) {
        throw new Error(
          typeof body?.error === "string"
            ? body.error
            : "로그인에 실패했습니다. 입력한 계정을 확인하세요.",
        );
      }

      setDemoPassword("");
      setDemoLoginState({ status: "idle" });
      await refreshDemoRuntimeConfig();
    } catch (error) {
      setDemoLoginState({
        errorMessage: error instanceof Error
          ? error.message
          : "로그인에 실패했습니다. 잠시 후 다시 시도하세요.",
        status: "idle",
      });
    }
  };

  const logoutDemo = async () => {
    setDemoLogoutState("loading");

    try {
      const response = await fetch("/api/auth/logout", {
        credentials: "same-origin",
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("logout failed");
      }

      setDemoPassword("");
      setDemoLogoutState("idle");
      await refreshDemoRuntimeConfig();
    } catch {
      setDemoLogoutState("error");
    }
  };

  const showDemoLogin =
    demoAccessState.status === "unauthenticated"
    || (isDemoMode && demoAccessState.status === "checking");

  if (showDemoLogin) {
    return (
      <DemoLoginScreen
        errorMessage={demoLoginState.errorMessage}
        isChecking={demoAccessState.status === "checking"}
        isSubmitting={demoLoginState.status === "loading"}
        password={demoPassword}
        username={demoUsername}
        onPasswordChange={setDemoPassword}
        onSubmit={(event) => void submitDemoLogin(event)}
        onUsernameChange={setDemoUsername}
      />
    );
  }

  return (
    <main
      className={`app-shell ${isDemoMode ? "demo-mode" : ""} ${!isAiFeatureEnabled ? "ai-disabled" : ""}`.trim()}
    >
      <section className="workspace">
        <header className="app-header">
          <div>
            <p className="eyebrow">Legacy SQL Mapper</p>
            <h1>SQL 설명기 MVP 0.1</h1>
          </div>
          {demoAccessState.status === "authenticated" ? (
            <div className="demo-session-control">
              <span>{demoAccessState.username ?? "테스트 사용자"} 로그인됨</span>
              <button
                className="text-button"
                disabled={demoLogoutState === "loading"}
                type="button"
                onClick={() => void logoutDemo()}
              >
                {demoLogoutState === "loading" ? "로그아웃 중" : "로그아웃"}
              </button>
              {demoLogoutState === "error" ? (
                <small role="alert">로그아웃 처리에 실패했습니다.</small>
              ) : null}
            </div>
          ) : null}
        </header>

        <details className="scope-notice" open>
          <summary>지원 범위 / 한계</summary>
          <p>
            현재 버전은 정규식 기반 SQL 분석기입니다. 일반적인 SELECT,
            JOIN, CTE, GROUP BY, HAVING, 윈도우 함수, CASE, 서브쿼리, SET
            연산을 분석하지만, 모든 DBMS 방언과 복잡한 중첩 SQL을 완전하게
            지원하지는 않습니다.
          </p>
        </details>

        {isDemoMode ? (
          <aside className="demo-safety-banner" aria-label="보호된 데모 안내">
            <strong>보호된 데모 환경</strong>
            <p>
              이 화면은 승인된 테스트 계정에서만 사용합니다. SQL을 실행하지 않고 브라우저에
              저장하지 않지만, 실제 운영 SQL·개인정보·고객 식별값은 입력하지 마세요. AI 보강은
              로그인 후에만 사용할 수 있으며, 마스킹된 SQL과 분석 결과만 provider에 전송됩니다.
            </p>
          </aside>
        ) : null}

        {demoAccessState.status === "authenticated" && !isAiFeatureEnabled ? (
          <aside className="demo-provider-status" role="status">
            로그인은 완료되었지만 AI provider 설정이 아직 준비되지 않았습니다. Worker의 Azure OpenAI,
            OpenAI 또는 보호된 HTTPS Ollama 설정을 확인하세요.
          </aside>
        ) : null}

        <div className="mode-toggle" role="tablist" aria-label="분석 모드">
          <button
            aria-selected={analysisMode === "single"}
            className={analysisMode === "single" ? "mode-button active" : "mode-button"}
            role="tab"
            type="button"
            onClick={() => changeAnalysisMode("single")}
          >
            단건 SQL
          </button>
          <button
            aria-selected={analysisMode === "multi"}
            className={analysisMode === "multi" ? "mode-button active" : "mode-button"}
            role="tab"
            type="button"
            onClick={() => changeAnalysisMode("multi")}
          >
            다건 SQL
          </button>
          <button
            aria-selected={analysisMode === "data"}
            className={analysisMode === "data" ? "mode-button active" : "mode-button"}
            role="tab"
            type="button"
            onClick={() => changeAnalysisMode("data")}
          >
            데이터 인사이트
          </button>
        </div>

        {analysisMode === "single" ? (
          <>
        <section className="preset-panel" aria-label="예제 SQL 프리셋">
          <label className="input-label compact" htmlFor="sql-preset">
            예제 SQL
          </label>
          <select
            id="sql-preset"
            value={selectedPresetId}
            onChange={(event) => loadPreset(event.target.value)}
          >
            <option value="">예제 선택</option>
            {SQL_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))}
          </select>
        </section>

        <section className="sql-input-panel" aria-label="SQL 입력">
          <label className="input-label" htmlFor="sql-input">
            SQL 입력
          </label>
          <textarea
            id="sql-input"
            value={sql}
            onChange={(event) => updateSingleSql(event.target.value)}
            spellCheck={false}
          />
        </section>

        <div className="action-row">
          <button className="primary-button" type="button" onClick={runAnalysis}>
            분석
          </button>
          {isAiFeatureEnabled ? (
            <button
              className="secondary-button"
              type="button"
              disabled={!sql.trim() || aiState.status === "loading"}
              onClick={() => void requestAiExplanation()}
            >
              {aiState.status === "loading" ? "AI 설명 요청 중" : "AI로 설명 보강하기"}
            </button>
          ) : null}
        </div>

        {isAiFeatureEnabled ? (
          <p className="ai-privacy-note">
            AI 설명 보강을 사용하면 마스킹된 SQL과 분석 결과가 AI 처리 요청에
            사용됩니다. 민감한 운영 SQL이나 개인정보가 포함된 SQL은 입력 전
            확인해 주세요.
          </p>
        ) : null}

        <section
          className={`result-grid ${hasSingleAiRepresentative ? "ai-representative-mode" : ""}`.trim()}
          aria-live="polite"
        >
          <ResultSection title="한 줄 설명" className="rule-analysis-section" variant="wide">
            <p className="summary-text">{analysis.summary}</p>
          </ResultSection>

          <ResultSection title="분석 신뢰도" className="rule-analysis-section">
            <ul className="analysis-list compact">
              <li>
                <strong>{confidenceLevelLabel(analysis.confidence.level)}</strong>
                <span>점수 {analysis.confidence.score}</span>
              </li>
              {analysis.confidence.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </ResultSection>

          <ResultSection title="사용 테이블" className="rule-analysis-section">
            {analysis.tables.length > 0 ? (
              <ul className="table-list">
                {analysis.tables.map((table) => (
                  <li key={`${table.rawName}-${table.alias ?? ""}`}>
                    <span className="table-name">{table.tableName}</span>
                    <span className="table-description">{table.description}</span>
                    {table.rawName !== table.tableName ? (
                      <span className="alias-label">원본 {table.rawName}</span>
                    ) : null}
                    {table.schemaName ? (
                      <span className="alias-label">스키마 {table.schemaName}</span>
                    ) : null}
                    {table.alias ? (
                      <span className="alias-label">별칭 {table.alias}</span>
                    ) : null}
                    {table.source === "subquery" ? (
                      <span className="alias-label">서브쿼리</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">사용 테이블을 찾지 못했습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="HAVING 조건" className="rule-analysis-section">
            {analysis.havingConditions.length > 0 ? (
              <ul className="condition-list">
                {analysis.havingConditions.map((filter) => (
                  <li key={`${filter.stage}-${filter.condition}`}>
                    <strong>{filter.stage}</strong>
                    <code>{filter.condition}</code>
                    <span>{filter.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">HAVING 조건이 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="WHERE 조건" className="rule-analysis-section">
            {analysis.filters.length > 0 ? (
              <ul className="condition-list">
                {analysis.filters.map((filter) => (
                  <li key={`${filter.stage}-${filter.condition}`}>
                    <strong>{filter.stage}</strong>
                    <code>{filter.condition}</code>
                    <span>{filter.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">WHERE 조건이 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="JOIN 관계" className="rule-analysis-section">
            {analysis.relations.length > 0 ? (
              <div className="relation-list">
                {analysis.relations.map((relation) => (
                  <div
                    className="relation-diagram"
                    key={`${relation.left}-${relation.right}`}
                  >
                    <code>{relation.left}</code>
                    <span aria-hidden="true">↓</span>
                    <code>{relation.right}</code>
                    {relation.joinType ? (
                      <small>{relation.joinType}</small>
                    ) : null}
                    {relation.explanation ? (
                      <p>{relation.explanation}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-text">JOIN 관계를 찾지 못했습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="CTE 처리 흐름" className="rule-analysis-section" variant="wide">
            {analysis.ctes.length > 0 ? (
              <ol className="analysis-list">
                {analysis.ctes.map((cte) => (
                  <li key={cte.name}>
                    <strong>{cte.name}</strong>
                    <span>{cte.role}</span>
                    {cte.dependencies.length > 0 ? (
                      <code>의존: {cte.dependencies.join(", ")}</code>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="empty-text">CTE가 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="GROUP BY / 집계 기준" className="rule-analysis-section">
            {analysis.groupBy.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.groupBy.map((group) => (
                  <li key={`${group.stage}-${group.columns.join("-")}`}>
                    <strong>{group.stage}</strong>
                    <span>{group.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">GROUP BY가 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="집계 지표" className="rule-analysis-section">
            {analysis.aggregations.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.aggregations.map((aggregation) => (
                  <li key={`${aggregation.stage}-${aggregation.expression}-${aggregation.alias ?? ""}`}>
                    <strong>{aggregation.alias ?? aggregation.expression}</strong>
                    <span>{aggregation.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">집계 지표가 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="윈도우 함수 분석" className="rule-analysis-section">
            {analysis.windowFunctions.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.windowFunctions.map((windowFunction) => (
                  <li key={`${windowFunction.stage}-${windowFunction.alias ?? windowFunction.expression}`}>
                    <strong>{windowFunction.alias ?? windowFunction.functionName}</strong>
                    <span>{windowFunction.description}</span>
                    {windowFunction.partitionBy ? (
                      <code>PARTITION BY {windowFunction.partitionBy}</code>
                    ) : null}
                    {windowFunction.orderBy ? (
                      <code>ORDER BY {windowFunction.orderBy}</code>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">윈도우 함수가 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="CASE / 파생 컬럼" className="rule-analysis-section">
            {analysis.caseExpressions.length > 0 || analysis.derivedColumns.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.caseExpressions.map((caseExpression) => (
                  <li key={`${caseExpression.stage}-${caseExpression.alias ?? "case"}`}>
                    <strong>{caseExpression.alias ?? "CASE"}</strong>
                    <span>{caseExpression.description}</span>
                    {caseExpression.rules.map((rule) => (
                      <code key={rule}>{rule}</code>
                    ))}
                  </li>
                ))}
                {analysis.derivedColumns.map((column) => (
                  <li key={`${column.stage}-${column.alias}`}>
                    <strong>{column.alias}</strong>
                    <span>{column.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">CASE 문 또는 파생 컬럼이 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="서브쿼리 / SET 연산" className="rule-analysis-section" variant="wide">
            {analysis.subqueries.length > 0 || analysis.setOperations.length > 0 ? (
              <ul className="analysis-list compact">
                {analysis.subqueries.map((subquery) => (
                  <li key={`${subquery.type}-${subquery.sql}`}>
                    <strong>{subquery.type}</strong>
                    <span>{subquery.description}</span>
                    {subquery.tables.length > 0 ? (
                      <code>테이블: {subquery.tables.join(", ")}</code>
                    ) : null}
                  </li>
                ))}
                {analysis.setOperations.map((operation) => (
                  <li key={operation.operator}>
                    <strong>{operation.operator}</strong>
                    <span>{operation.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-text">서브쿼리 또는 SET 연산이 없습니다.</p>
            )}
          </ResultSection>

          <ResultSection title="최종 조회 결과" className="rule-analysis-section" variant="wide">
            <p className="developer-text">{analysis.finalResult}</p>
          </ResultSection>

          <ResultSection title="업무 추정" className="rule-analysis-section">
            <ul className="business-list">
              {analysis.businessGuesses.map((guess) => (
                <li key={guess}>{guess}</li>
              ))}
            </ul>
          </ResultSection>

          <ResultSection title="신규 개발자 설명" className="rule-analysis-section" variant="wide">
            <p className="developer-text">{analysis.developerExplanation}</p>
          </ResultSection>

          <ResultSection title="AI 설명 보강" className="ai-output-section" variant="wide">
            {aiState.status === "idle" ? (
              <p className="empty-text">
                필요할 때만 AI 설명 보강을 요청할 수 있습니다. 룰 기반 분석
                결과는 AI 없이도 계속 표시됩니다.
              </p>
            ) : null}
            {aiState.status === "loading" ? (
              <p className="developer-text">AI 설명을 생성하는 중입니다.</p>
            ) : null}
            {aiState.status === "error" ? (
              <div className="ai-error">
                <p>{aiState.errorMessage}</p>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={retryAiExplanation}
                >
                  다시 시도
                </button>
              </div>
            ) : null}
            {aiState.status === "success" ? (
              <div className="ai-explanation">
                <section>
                  <h3>AI 한 줄 요약</h3>
                  <p>{aiState.explanation.summary}</p>
                </section>
                <section>
                  <h3>AI 데이터 흐름 설명</h3>
                  <p>{aiState.explanation.dataFlowExplanation}</p>
                </section>
                <section>
                  <h3>AI 업무 목적</h3>
                  <p>{aiState.explanation.businessPurpose}</p>
                </section>
                <section>
                  <h3>신규 개발자용 설명</h3>
                  <p>{aiState.explanation.juniorDeveloperExplanation}</p>
                </section>
                <section>
                  <h3>성능/운영 주의</h3>
                  <ul>
                    {aiState.explanation.performanceNotes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                    {aiState.explanation.riskNotes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h3>리팩토링 제안</h3>
                  <ul>
                    {aiState.explanation.refactoringSuggestions.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </section>
                <section>
                  <h3>불확실한 부분</h3>
                  <ul>
                    {[
                      ...aiState.explanation.uncertaintyNotes,
                      ...(analysis.confidence.level !== "high"
                        ? [`룰 기반 분석 신뢰도: ${confidenceLevelLabel(analysis.confidence.level)}`]
                        : []),
                      ...analysis.warnings,
                    ].map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </section>
              </div>
            ) : null}
          </ResultSection>

          <ResultSection title="AI 문서 초안" className="ai-output-section" variant="wide">
            <div className="document-draft-toolbar">
              <label className="input-label compact" htmlFor="ai-document-type">
                문서 유형
              </label>
              <select
                id="ai-document-type"
                value={aiDocumentType}
                onChange={(event) => {
                  setAiDocumentType(event.target.value as AiSqlDocumentType);
                  setAiDocumentDraftState({ status: "idle" });
                  setDocumentDraftCopyStatus("idle");
                }}
              >
                {AI_SQL_DOCUMENT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                className="secondary-button"
                type="button"
                disabled={!sql.trim() || aiDocumentDraftState.status === "loading"}
                onClick={() => void requestAiDocumentDraft()}
              >
                {aiDocumentDraftState.status === "loading"
                  ? "AI 문서 초안 생성 중"
                  : "AI 문서 초안 생성"}
              </button>
            </div>

            {aiDocumentDraftState.status === "idle" ? (
              <p className="empty-text">
                선택한 문서 유형에 맞춰 팀 문서에 붙여넣을 수 있는 Markdown 초안을 생성합니다.
              </p>
            ) : null}
            {aiDocumentDraftState.status === "loading" ? (
              <p className="developer-text">AI 문서 초안을 생성하는 중입니다.</p>
            ) : null}
            {aiDocumentDraftState.status === "error" ? (
              <div className="ai-error">
                <p>{aiDocumentDraftState.errorMessage}</p>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={retryAiDocumentDraft}
                >
                  다시 시도
                </button>
              </div>
            ) : null}
            {aiDocumentDraftState.status === "success" ? (
              <div className="document-draft-result">
                <div className="ai-explanation">
                  <section>
                    <h3>제목</h3>
                    <p>{aiDocumentDraftState.draft.title}</p>
                  </section>
                  <section>
                    <h3>개요</h3>
                    <p>{aiDocumentDraftState.draft.overview}</p>
                  </section>
                  <section>
                    <h3>업무 맥락</h3>
                    <p>{aiDocumentDraftState.draft.businessContext}</p>
                  </section>
                  <section>
                    <h3>데이터 흐름</h3>
                    <p>{aiDocumentDraftState.draft.dataFlow}</p>
                  </section>
                  <section>
                    <h3>핵심 테이블</h3>
                    <ul>
                      {aiDocumentDraftState.draft.keyTables.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h3>주요 조건</h3>
                    <ul>
                      {aiDocumentDraftState.draft.keyConditions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h3>위험 요약</h3>
                    <ul>
                      {aiDocumentDraftState.draft.risks.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h3>리팩토링 제안</h3>
                    <ul>
                      {aiDocumentDraftState.draft.refactoringSuggestions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h3>신규 개발자 메모</h3>
                    <p>{aiDocumentDraftState.draft.onboardingNotes}</p>
                  </section>
                  <section>
                    <h3>불확실한 부분</h3>
                    <ul>
                      {[
                        ...aiDocumentDraftState.draft.uncertaintyNotes,
                        ...analysis.warnings,
                      ].map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                </div>

                <div className="report-header">
                  <p className="report-help">문서 초안 Markdown</p>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void copyAiDocumentDraftMarkdown()}
                  >
                    {documentDraftCopyStatus === "copied"
                      ? "복사됨"
                      : documentDraftCopyStatus === "selected"
                        ? "선택됨"
                        : documentDraftCopyStatus === "failed"
                          ? "복사 실패"
                          : "Markdown 복사"}
                  </button>
                </div>
                <textarea
                  id="ai-document-draft-markdown"
                  className="report-output"
                  value={aiDocumentDraftState.draft.markdown}
                  readOnly
                  aria-label="AI 문서 초안 Markdown"
                />
              </div>
            ) : null}
          </ResultSection>

          {hasSingleAiRepresentative ? (
            <CollapsibleSection
              title="상세 분석 근거"
              description="룰 기반 파서가 추출한 구조 값"
            >
              <SingleRuleAnalysisDetails analysis={analysis} />
            </CollapsibleSection>
          ) : null}

          <ResultSection title="추정 근거" className="rule-analysis-section" variant="wide">
            <ul className="analysis-list compact">
              {analysis.businessIntent.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </ResultSection>

          <ResultSection title="주의 사항" className="rule-analysis-section" variant="wide">
            <ul className="analysis-list compact">
              {analysis.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
              {analysis.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </ResultSection>

          <ResultSection title="복사 가능한 보고서" className="report-section" variant="wide">
            <div className="report-header">
              <p className="report-help">
                분석 결과를 문서나 메신저에 붙여넣기 쉬운 형태로 정리했습니다.
              </p>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void copyReport()}
              >
                {copyStatus === "copied"
                  ? "복사됨"
                  : copyStatus === "selected"
                    ? "선택됨"
                  : copyStatus === "failed"
                    ? "복사 실패"
                    : "보고서 복사"}
              </button>
            </div>
            <textarea
              id="report-output"
              className="report-output"
              value={reportText}
              readOnly
              aria-label="복사 가능한 보고서"
            />
          </ResultSection>
        </section>
          </>
        ) : analysisMode === "data" ? (
          <DataInsightWorkspace aiFeatureEnabled={isAiFeatureEnabled} />
        ) : (
          <>
            <section className="sql-input-panel" aria-label="다건 SQL 입력">
              <div className="input-header">
                <label className="input-label no-border" htmlFor="multi-sql-input">
                  다건 SQL 입력
                </label>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={loadMultiSample}
                >
                  샘플 다건 SQL
                </button>
              </div>
              <textarea
                id="multi-sql-input"
                value={multiSql}
                onChange={(event) => updateMultiSql(event.target.value)}
                spellCheck={false}
              />
            </section>

            <div className="action-row">
              <button
                className="primary-button"
                type="button"
                onClick={runMultiAnalysis}
              >
                다건 분석
              </button>
              {isAiFeatureEnabled ? (
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!multiSql.trim() || multiAiState.status === "loading"}
                  onClick={() => void requestMultiAiExplanation()}
                >
                  {multiAiState.status === "loading"
                    ? "다건 AI 설명 요청 중"
                    : "AI로 설명 보강하기"}
                </button>
              ) : null}
            </div>

            {isAiFeatureEnabled ? (
              <p className="ai-privacy-note">
                다건 AI 설명 보강을 사용하면 마스킹된 SQL 묶음과 다건 분석
                결과가 AI 처리 요청에 사용됩니다. 민감한 운영 SQL이나 개인정보가
                포함된 SQL은 입력 전 확인해 주세요.
              </p>
            ) : null}

            <section
              className={`result-grid multi-result-mode ${hasMultiAiRepresentative ? "ai-representative-mode" : ""}`.trim()}
              aria-live="polite"
            >
              <ResultSection title="다건 분석 요약" className="summary-section" variant="wide">
                <div className="summary-metrics">
                  <div>
                    <strong>{multiAnalysis.statements.length}</strong>
                    <span>분석 SQL</span>
                  </div>
                  <div>
                    <strong>{tableAssetMap.summary.tableCount}</strong>
                    <span>사용 테이블</span>
                  </div>
                  <div>
                    <strong>{tableAssetMap.summary.coreTableCount}</strong>
                    <span>핵심 후보</span>
                  </div>
                  <div>
                    <strong>{multiAnalysis.joinUsage.length}</strong>
                    <span>JOIN 관계</span>
                  </div>
                  <div>
                    <strong>{multiAnalysis.conditionUsage.length}</strong>
                    <span>조건 패턴</span>
                  </div>
                  <div>
                    <strong>{multiAnalysis.warnings.length}</strong>
                    <span>Warnings</span>
                  </div>
                </div>
              </ResultSection>

              <ResultSection title="AI 다건 설명 보강" className="ai-output-section" variant="wide">
                {multiAiState.status === "idle" ? (
                  <p className="empty-text">
                    필요할 때만 다건 AI 설명 보강을 요청할 수 있습니다. 여러
                    SQL의 테이블 사용, JOIN, 조건, 리스크, 업무 목적 분포를
                    문서형 설명으로 보강합니다.
                  </p>
                ) : null}
                {multiAiState.status === "loading" ? (
                  <p className="developer-text">다건 AI 설명을 생성하는 중입니다.</p>
                ) : null}
                {multiAiState.status === "error" ? (
                  <div className="ai-error">
                    <p>{multiAiState.errorMessage}</p>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={retryMultiAiExplanation}
                    >
                      다시 시도
                    </button>
                  </div>
                ) : null}
                {multiAiState.status === "success" ? (
                  <div className="ai-explanation">
                    <section>
                      <h3>AI 한 줄 요약</h3>
                      <p>{multiAiState.explanation.summary}</p>
                    </section>
                    <section>
                      <h3>AI 업무 흐름 설명</h3>
                      <p>{multiAiState.explanation.dataFlowExplanation}</p>
                    </section>
                    <section>
                      <h3>AI 업무 목적</h3>
                      <p>{multiAiState.explanation.businessPurpose}</p>
                    </section>
                    <section>
                      <h3>신규 개발자용 설명</h3>
                      <p>{multiAiState.explanation.juniorDeveloperExplanation}</p>
                    </section>
                    <section>
                      <h3>위험/운영 주의</h3>
                      <ul>
                        {multiAiState.explanation.performanceNotes.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                        {multiAiState.explanation.riskNotes.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </section>
                    <section>
                      <h3>리팩토링 제안</h3>
                      <ul>
                        {multiAiState.explanation.refactoringSuggestions.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </section>
                    <section>
                      <h3>불확실한 부분</h3>
                      <ul>
                        {[
                          ...multiAiState.explanation.uncertaintyNotes,
                          ...multiAnalysis.warnings,
                        ].map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </section>
                  </div>
                ) : null}
              </ResultSection>

              <ResultSection title="핵심 테이블 후보" className="asset-section" variant="wide">
                {tableAssetMap.coreTables.length > 0 ? (
                  <div className="core-table-strip">
                    {tableAssetMap.coreTables.slice(0, 6).map((table) => (
                      <button
                        className="core-table-card"
                        key={table.key}
                        type="button"
                        onClick={() => setSelectedTableAssetKey(table.key)}
                      >
                        <span className="asset-table-badge">
                          {tableAssetImportanceLabel(table.importance)}
                        </span>
                        <strong>{table.tableName}</strong>
                        <span>
                          사용 SQL {table.usageCount}개 / JOIN 대상 {table.joinTargets.length}개
                        </span>
                        <code>{table.importanceScore}점</code>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="empty-text">반복 사용 패턴이 충분한 핵심 테이블 후보가 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="테이블 자산 지도" className="asset-section" variant="wide">
                {tableAssetMap.tables.length > 0 ? (
                  <div className="asset-map-layout">
                    <div className="asset-table-list" aria-label="테이블 목록">
                      {tableAssetMap.tables.map((table) => (
                        <button
                          aria-pressed={selectedTableAsset?.key === table.key}
                          className={`asset-table-button ${
                            selectedTableAsset?.key === table.key ? "active" : ""
                          }`.trim()}
                          key={table.key}
                          type="button"
                          onClick={() => setSelectedTableAssetKey(table.key)}
                        >
                          <span className="asset-table-badge">
                            {tableAssetImportanceLabel(table.importance)}
                          </span>
                          <strong>{table.tableName}</strong>
                          <small>
                            SQL {table.usageCount}개 / JOIN {table.joinTargets.length}개 / 조건 {table.conditions.length}개
                          </small>
                        </button>
                      ))}
                    </div>

                    {selectedTableAsset ? (
                      <article className="asset-table-detail">
                        <header className="asset-detail-header">
                          <div>
                            <span className="asset-table-badge">
                              {tableAssetRoleLabel(selectedTableAsset.role)}
                            </span>
                            <h3>{selectedTableAsset.tableName}</h3>
                          </div>
                          <div className="asset-score">
                            <strong>{selectedTableAsset.importanceScore}</strong>
                            <span>핵심도 점수</span>
                          </div>
                        </header>

                        <div className="asset-detail-grid">
                          <section className="asset-detail-section">
                            <h4>사용 SQL</h4>
                            <ul>
                              {selectedTableAsset.usedBySql.map((usedSql) => (
                                <li key={usedSql.statementId}>
                                  <strong>{usedSql.statementId}</strong>
                                  <span>{usedSql.summary}</span>
                                  <code>{usedSql.businessIntent}</code>
                                </li>
                              ))}
                            </ul>
                          </section>

                          <section className="asset-detail-section">
                            <h4>JOIN 대상</h4>
                            {selectedTableAsset.joinTargets.length > 0 ? (
                              <ul>
                                {selectedTableAsset.joinTargets.map((join) => (
                                  <li key={join.tableName}>
                                    <strong>{join.tableName}</strong>
                                    <span>
                                      {join.count}회 / SQL {join.statementIds.join(", ")}
                                    </span>
                                    {join.columnPairs.length > 0 ? (
                                      <code>
                                        {join.columnPairs
                                          .map((pair) => `${pair.sourceColumn} -> ${pair.targetColumn}`)
                                          .join(", ")}
                                      </code>
                                    ) : null}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="empty-text">JOIN 대상이 없습니다.</p>
                            )}
                          </section>

                          <section className="asset-detail-section">
                            <h4>주요 조건</h4>
                            {selectedTableAsset.conditions.length > 0 ? (
                              <ul>
                                {selectedTableAsset.conditions.slice(0, 8).map((condition) => (
                                  <li key={condition.normalizedCondition}>
                                    <strong>{condition.normalizedCondition}</strong>
                                    <span>
                                      {condition.count}회 / 단계 {condition.stages.join(", ")}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="empty-text">테이블에 연결된 조건이 없습니다.</p>
                            )}
                          </section>

                          <section className="asset-detail-section">
                            <h4>업무 추정</h4>
                            {selectedTableAsset.businessGuesses.length > 0 ? (
                              <ul>
                                {selectedTableAsset.businessGuesses.map((guess) => (
                                  <li key={guess}>{guess}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="empty-text">업무 추정 근거가 부족합니다.</p>
                            )}
                            {Object.keys(selectedTableAsset.businessIntentSummary).length > 0 ? (
                              <p className="asset-detail-note">
                                유형 분포: {Object.entries(selectedTableAsset.businessIntentSummary)
                                  .map(([type, count]) => `${type} ${count}개`)
                                  .join(", ")}
                              </p>
                            ) : null}
                          </section>

                          <section className="asset-detail-section wide">
                            <h4>주의 사항</h4>
                            {selectedTableAsset.warnings.length > 0 ? (
                              <ul>
                                {selectedTableAsset.warnings.map((warning) => (
                                  <li key={warning}>{warning}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="empty-text">별도 주의 사항이 없습니다.</p>
                            )}
                          </section>
                        </div>
                      </article>
                    ) : null}
                  </div>
                ) : (
                  <p className="empty-text">테이블 자산 지도를 만들 분석 결과가 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="시스템 지도 / 영향도 분석" className="asset-section" variant="wide">
                <div className="system-map-toolbar">
                  <div className="graph-mode-toggle" aria-label="시스템 지도 보기 방식">
                    {systemGraphModes.map((mode) => (
                      <button
                        aria-pressed={systemGraphMode === mode.mode}
                        className={`graph-mode-button ${
                          systemGraphMode === mode.mode ? "active" : ""
                        }`.trim()}
                        key={mode.mode}
                        type="button"
                        onClick={() => setSystemGraphMode(mode.mode)}
                      >
                        {mode.label}
                      </button>
                    ))}
                  </div>
                  <p>{systemGraphView.description}</p>
                </div>

                <div className="system-map-layout">
                  <div className="system-map-main">
                    <div className="system-graph-summary">
                      <div>
                        <strong>{systemGraph.summary.nodeCount}</strong>
                        <span>노드</span>
                      </div>
                      <div>
                        <strong>{systemGraph.summary.edgeCount}</strong>
                        <span>연결</span>
                      </div>
                      <div>
                        <strong>{systemGraph.summary.cteNodeCount}</strong>
                        <span>CTE</span>
                      </div>
                      <div>
                        <strong>{systemGraph.summary.loadFlowCount}</strong>
                        <span>적재 흐름</span>
                      </div>
                      <div>
                        <strong>{systemGraph.summary.warningCount}</strong>
                        <span>주의</span>
                      </div>
                    </div>

                    <div className="system-edge-list">
                      <h3>{systemGraphView.title}</h3>
                      {systemGraphView.edges.length > 0 ? (
                        systemGraphView.edges.slice(0, 60).map((edge) => {
                          const fromNode = systemGraphNodeMap.get(edge.from);
                          const toNode = systemGraphNodeMap.get(edge.to);

                          return (
                            <article className="system-edge-card" key={edge.id}>
                              <button
                                className={`system-node-chip ${fromNode?.type ?? "unknown"}`.trim()}
                                disabled={!fromNode}
                                type="button"
                                onClick={() => fromNode ? setSelectedSystemNodeId(fromNode.id) : undefined}
                              >
                                <span>{fromNode ? systemNodeTypeLabel(fromNode.type) : "Unknown"}</span>
                                <strong>{fromNode?.label ?? edge.from}</strong>
                              </button>
                              <div className="system-edge-meta">
                                <span>{systemEdgeTypeLabel(edge.type)}</span>
                                <code>{edge.label}</code>
                                <small>SQL {edge.sourceStatementIds.join(", ")}</small>
                              </div>
                              <span className="edge-arrow">-&gt;</span>
                              <button
                                className={`system-node-chip ${toNode?.type ?? "unknown"}`.trim()}
                                disabled={!toNode}
                                type="button"
                                onClick={() => toNode ? setSelectedSystemNodeId(toNode.id) : undefined}
                              >
                                <span>{toNode ? systemNodeTypeLabel(toNode.type) : "Unknown"}</span>
                                <strong>{toNode?.label ?? edge.to}</strong>
                              </button>
                            </article>
                          );
                        })
                      ) : (
                        <p className="empty-text">이 보기에서 표시할 관계가 없습니다.</p>
                      )}
                    </div>
                  </div>

                  <aside className="system-node-panel">
                    {selectedSystemNode ? (
                      <>
                        <header className="system-node-header">
                          <span className={`system-node-type ${selectedSystemNode.type}`}>
                            {systemNodeTypeLabel(selectedSystemNode.type)}
                          </span>
                          <h3>{selectedSystemNode.label}</h3>
                          {selectedSystemNode.description ? (
                            <p>{selectedSystemNode.description}</p>
                          ) : null}
                        </header>

                        <div className="system-node-facts">
                          <div>
                            <strong>{selectedSystemNode.sourceStatementIds.length}</strong>
                            <span>관련 SQL</span>
                          </div>
                          <div>
                            <strong>{selectedSystemNode.importance ?? "low"}</strong>
                            <span>중요도</span>
                          </div>
                          <div>
                            <strong>{selectedSystemNode.confidenceLevel ?? "추정"}</strong>
                            <span>신뢰도</span>
                          </div>
                        </div>

                        <section className="impact-section">
                          <h4>상위 의존</h4>
                          {selectedSystemImpact?.upstream.length ? (
                            <ul className="impact-list">
                              {selectedSystemImpact.upstream.slice(0, 10).map((impact: ImpactNode) => (
                                <li key={`${impact.nodeId}-${impact.viaEdgeId}`}>
                                  <button
                                    type="button"
                                    onClick={() => setSelectedSystemNodeId(impact.nodeId)}
                                  >
                                    <strong>{impact.label}</strong>
                                    <span>
                                      {systemNodeTypeLabel(impact.type)} / {impact.depth}단계 / {impact.viaEdgeLabel}
                                    </span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="empty-text">상위 의존 관계가 없습니다.</p>
                          )}
                        </section>

                        <section className="impact-section">
                          <h4>하위 영향</h4>
                          {selectedSystemImpact?.downstream.length ? (
                            <ul className="impact-list">
                              {selectedSystemImpact.downstream.slice(0, 10).map((impact: ImpactNode) => (
                                <li key={`${impact.nodeId}-${impact.viaEdgeId}`}>
                                  <button
                                    type="button"
                                    onClick={() => setSelectedSystemNodeId(impact.nodeId)}
                                  >
                                    <strong>{impact.label}</strong>
                                    <span>
                                      {systemNodeTypeLabel(impact.type)} / {impact.depth}단계 / {impact.viaEdgeLabel}
                                    </span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="empty-text">하위 영향 관계가 없습니다.</p>
                          )}
                        </section>

                        <section className="impact-section">
                          <h4>주의 사항</h4>
                          {selectedSystemImpact?.warnings.length ? (
                            <ul className="impact-warning-list">
                              {selectedSystemImpact.warnings.map((warning) => (
                                <li key={warning}>{warning}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="empty-text">선택 노드의 별도 주의 사항이 없습니다.</p>
                          )}
                        </section>
                      </>
                    ) : (
                      <p className="empty-text">선택할 시스템 노드가 없습니다.</p>
                    )}
                  </aside>
                </div>
              </ResultSection>

              <ResultSection title="리스크 / 개선 포인트" className="risk-section" variant="wide">
                <div className="risk-analysis-panel">
                  <div className="risk-summary-grid">
                    <div className="critical">
                      <strong>{sqlRiskAnalysis.summary.critical}</strong>
                      <span>치명</span>
                    </div>
                    <div className="high">
                      <strong>{sqlRiskAnalysis.summary.high}</strong>
                      <span>높음</span>
                    </div>
                    <div className="medium">
                      <strong>{sqlRiskAnalysis.summary.medium}</strong>
                      <span>보통</span>
                    </div>
                    <div className="low">
                      <strong>{sqlRiskAnalysis.summary.low}</strong>
                      <span>낮음</span>
                    </div>
                    <div>
                      <strong>{sqlRiskAnalysis.summary.total}</strong>
                      <span>전체 Finding</span>
                    </div>
                  </div>

                  <div className="risk-filter-row" aria-label="리스크 심각도 필터">
                    {riskFilterOptions.map((option) => (
                      <button
                        aria-pressed={riskFilter === option.value}
                        className={`risk-filter-button ${
                          riskFilter === option.value ? "active" : ""
                        }`.trim()}
                        key={option.value}
                        type="button"
                        onClick={() => setRiskFilter(option.value)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>

                  {filteredRiskFindings.length > 0 ? (
                    <div className="risk-finding-list">
                      {filteredRiskFindings.map((finding) => (
                        <article
                          className={`risk-finding-card ${finding.severity}`.trim()}
                          key={finding.id}
                        >
                          <header>
                            <span className={`risk-severity ${finding.severity}`}>
                              {riskSeverityLabel(finding.severity)}
                            </span>
                            <div>
                              <strong>{finding.statementId} · {finding.title}</strong>
                              <small>{finding.category} / confidence {finding.confidence}</small>
                            </div>
                          </header>
                          <p>{finding.message}</p>
                          <dl>
                            <div>
                              <dt>근거</dt>
                              <dd>{finding.evidence}</dd>
                            </div>
                            <div>
                              <dt>추천 개선</dt>
                              <dd>{finding.recommendation}</dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-text">선택한 심각도의 리스크 finding이 없습니다.</p>
                  )}
                </div>
              </ResultSection>

              <ResultSection title="SQL별 분석 결과" className="rule-analysis-section" variant="wide">
                {multiAnalysis.statements.length > 0 ? (
                  <ol className="analysis-list">
                    {multiAnalysis.statements.map((statement) => (
                      <li key={statement.id}>
                        <strong>{statement.id}</strong>
                        <span>{statement.analysis?.summary ?? statement.error}</span>
                        {statement.analysis ? (
                          <code>{statement.analysis.businessIntent.type}</code>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="empty-text">분석할 SQL이 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="테이블 사용 현황" className="rule-analysis-section">
                {multiAnalysis.tableUsage.length > 0 ? (
                  <ul className="analysis-list compact">
                    {multiAnalysis.tableUsage.map((table) => (
                      <li key={`${table.schemaNames.join(".")}-${table.tableName}`}>
                        <strong>{table.tableName}</strong>
                        <span>{table.count}회 사용 / SQL {table.statementIds.join(", ")}</span>
                        {table.schemaNames.length > 0 ? (
                          <code>스키마: {table.schemaNames.join(", ")}</code>
                        ) : null}
                        <code>업무: {table.businessIntents.join(", ")}</code>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-text">사용 테이블이 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="반복 JOIN 관계" className="rule-analysis-section">
                {multiAnalysis.joinUsage.length > 0 ? (
                  <ul className="analysis-list compact">
                    {multiAnalysis.joinUsage.map((join) => (
                      <li key={`${join.left}-${join.right}`}>
                        <strong>{`${join.left} -> ${join.right}`}</strong>
                        <span>{join.count}회 / SQL {join.statementIds.join(", ")}</span>
                        {join.joinTypes.length > 0 ? (
                          <code>{join.joinTypes.join(", ")}</code>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-text">JOIN 관계가 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="반복 조건 패턴" className="rule-analysis-section">
                {multiAnalysis.conditionUsage.length > 0 ? (
                  <ul className="analysis-list compact">
                    {multiAnalysis.conditionUsage.map((condition) => (
                      <li key={condition.normalizedCondition}>
                        <strong>{condition.normalizedCondition}</strong>
                        <span>{condition.count}회 / SQL {condition.statementIds.join(", ")}</span>
                        <code>단계: {condition.stages.join(", ")}</code>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-text">반복 조건 패턴이 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="업무 목적 분포" className="rule-analysis-section">
                {Object.keys(multiAnalysis.businessIntentSummary).length > 0 ? (
                  <ul className="business-list">
                    {Object.entries(multiAnalysis.businessIntentSummary)
                      .sort(([, leftCount], [, rightCount]) => rightCount - leftCount)
                      .map(([type, count]) => (
                        <li key={type}>{type}: {count}개</li>
                      ))}
                  </ul>
                ) : (
                  <p className="empty-text">업무 목적 분포가 없습니다.</p>
                )}
              </ResultSection>

              <ResultSection title="다건 분석 주의 사항" className="rule-analysis-section" variant="wide">
                {multiAnalysis.warnings.length > 0 ? (
                  <ul className="analysis-list compact">
                    {multiAnalysis.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-text">별도 주의 사항이 없습니다.</p>
                )}
              </ResultSection>

              {hasMultiAiRepresentative ? (
                <CollapsibleSection
                  title="상세 분석 근거"
                  description="SQL별 룰 기반 분석과 반복 패턴"
                >
                  <MultiRuleAnalysisDetails multiAnalysis={multiAnalysis} />
                </CollapsibleSection>
              ) : null}

              <ResultSection title="AI 다건 문서 초안" className="ai-output-section" variant="wide">
                <div className="document-draft-toolbar">
                  <label className="input-label compact" htmlFor="multi-ai-document-type">
                    문서 유형
                  </label>
                  <select
                    id="multi-ai-document-type"
                    value={multiAiDocumentType}
                    onChange={(event) => {
                      setMultiAiDocumentType(event.target.value as AiSqlDocumentType);
                      setMultiAiDocumentDraftState({ status: "idle" });
                      setMultiDocumentDraftCopyStatus("idle");
                    }}
                  >
                    {AI_SQL_DOCUMENT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={!multiSql.trim() || multiAiDocumentDraftState.status === "loading"}
                    onClick={() => void requestMultiAiDocumentDraft()}
                  >
                    {multiAiDocumentDraftState.status === "loading"
                      ? "다건 문서 초안 생성 중"
                      : "AI 다건 문서 초안 생성"}
                  </button>
                </div>

                {multiAiDocumentDraftState.status === "idle" ? (
                  <p className="empty-text">
                    여러 SQL의 테이블 사용, 시스템 흐름, 리스크, 온보딩 경로를
                    팀 문서용 Markdown 초안으로 생성합니다.
                  </p>
                ) : null}
                {multiAiDocumentDraftState.status === "loading" ? (
                  <p className="developer-text">AI 다건 문서 초안을 생성하는 중입니다.</p>
                ) : null}
                {multiAiDocumentDraftState.status === "error" ? (
                  <div className="ai-error">
                    <p>{multiAiDocumentDraftState.errorMessage}</p>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={retryMultiAiDocumentDraft}
                    >
                      다시 시도
                    </button>
                  </div>
                ) : null}
                {multiAiDocumentDraftState.status === "success" ? (
                  <div className="document-draft-result">
                    <div className="ai-explanation">
                      <section>
                        <h3>제목</h3>
                        <p>{multiAiDocumentDraftState.draft.title}</p>
                      </section>
                      <section>
                        <h3>업무 영역 요약</h3>
                        <p>{multiAiDocumentDraftState.draft.businessAreaSummary}</p>
                      </section>
                      <section>
                        <h3>시스템 맥락</h3>
                        <p>{multiAiDocumentDraftState.draft.systemContext}</p>
                      </section>
                      <section>
                        <h3>데이터 흐름 요약</h3>
                        <p>{multiAiDocumentDraftState.draft.dataFlowSummary}</p>
                      </section>
                      <section>
                        <h3>핵심 테이블</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.coreTables.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>테이블 사용 요약</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.tableUsageSummary.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>JOIN 요약</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.joinSummary.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>SQL 그룹 요약</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.sqlGroupSummary.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>위험 요약</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.riskSummary.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>리팩토링 제안</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.refactoringSuggestions.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>신규 개발자 온보딩 경로</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.onboardingPath.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>운영 체크리스트</h3>
                        <ul>
                          {multiAiDocumentDraftState.draft.operationChecklist.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h3>불확실한 부분</h3>
                        <ul>
                          {[
                            ...multiAiDocumentDraftState.draft.uncertaintyNotes,
                            ...multiAnalysis.warnings,
                          ].map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                    </div>

                    <div className="report-header">
                      <p className="report-help">다건 문서 초안 Markdown</p>
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => void copyMultiAiDocumentDraftMarkdown()}
                      >
                        {multiDocumentDraftCopyStatus === "copied"
                          ? "복사됨"
                          : multiDocumentDraftCopyStatus === "selected"
                            ? "선택됨"
                            : multiDocumentDraftCopyStatus === "failed"
                              ? "복사 실패"
                              : "Markdown 복사"}
                      </button>
                    </div>
                    <textarea
                      id="multi-ai-document-draft-markdown"
                      className="report-output"
                      value={multiAiDocumentDraftState.draft.markdown}
                      readOnly
                      aria-label="AI 다건 문서 초안 Markdown"
                    />
                  </div>
                ) : null}
              </ResultSection>

              <ResultSection title="보고서 / 문서화" className="report-section" variant="wide">
                <div className="documentation-panel">
                  <div className="report-options-grid" aria-label="보고서 포함 옵션">
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeTableAssetMap}
                        onChange={(event) =>
                          updateReportOption("includeTableAssetMap", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>테이블 자산 지도 포함</strong>
                        <small>핵심 테이블, JOIN 대상, 주요 조건을 포함합니다.</small>
                      </span>
                    </label>
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeSystemGraph}
                        onChange={(event) =>
                          updateReportOption("includeSystemGraph", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>시스템 지도 포함</strong>
                        <small>SQL 의존성, CTE 흐름, 적재 흐름을 포함합니다.</small>
                      </span>
                    </label>
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeWarnings}
                        onChange={(event) =>
                          updateReportOption("includeWarnings", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>Warnings 포함</strong>
                        <small>정규식 기반 추정과 수동 확인 사항을 포함합니다.</small>
                      </span>
                    </label>
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeRawSql}
                        onChange={(event) =>
                          updateReportOption("includeRawSql", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>원본 SQL 포함</strong>
                        <small>팀 문서 공유 전 민감 정보 포함 여부를 확인하세요.</small>
                      </span>
                    </label>
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeAiExplanation}
                        onChange={(event) =>
                          updateReportOption("includeAiExplanation", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>AI 설명 보강 포함</strong>
                        <small>성공한 AI 보강 결과가 있을 때만 포함됩니다.</small>
                      </span>
                    </label>
                    <label className="report-option">
                      <input
                        type="checkbox"
                        checked={reportOptions.includeAiDocumentDraft}
                        onChange={(event) =>
                          updateReportOption("includeAiDocumentDraft", event.currentTarget.checked)
                        }
                      />
                      <span>
                        <strong>AI 문서 초안 포함</strong>
                        <small>성공한 다건 문서 초안이 있을 때만 포함됩니다.</small>
                      </span>
                    </label>
                  </div>

                  <div className="documentation-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={downloadMarkdownReport}
                    >
                      Markdown 다운로드
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={openPrintableReport}
                    >
                      PDF 보고서 열기
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={downloadTableUsageCsv}
                    >
                      Excel용 CSV 다운로드
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={downloadRiskFindingsCsv}
                    >
                      리스크 CSV 다운로드
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => void copyPasteReport("notion")}
                    >
                      Notion용 복사
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => void copyPasteReport("confluence")}
                    >
                      Confluence용 복사
                    </button>
                  </div>

                  <p className={`report-action-status ${reportActionStatus}`}>
                    {reportActionStatusText(reportActionStatus)}
                  </p>

                  <div className="report-preview-grid">
                    <section>
                      <h3>보고서 요약</h3>
                      <ul>
                        <li>SQL {documentationReport.summary.totalSql}개</li>
                        <li>테이블 {documentationReport.summary.tableCount}개</li>
                        <li>JOIN {documentationReport.summary.joinCount}개</li>
                        <li>리스크 Finding {documentationReport.riskFindingSummary.total}개</li>
                      </ul>
                    </section>
                    <section>
                      <h3>위험 SQL 미리보기</h3>
                      {documentationReport.riskSqls.length > 0 ? (
                        <ul className="risk-preview-list">
                          {documentationReport.riskSqls.slice(0, 5).map((risk) => (
                            <li key={risk.id}>
                              <strong>{risk.id}</strong>
                              <span>{risk.riskLevel} / {risk.score}점</span>
                              <small>{risk.reasons[0]}</small>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="empty-text">위험 신호가 있는 SQL이 없습니다.</p>
                      )}
                    </section>
                  </div>
                </div>
              </ResultSection>

              <ResultSection title="복사 가능한 다건 분석 보고서" className="report-section" variant="wide">
                <div className="report-header">
                  <p className="report-help">
                    여러 SQL의 테이블 사용, 자산 지도, 시스템 의존성 지도를 Markdown으로 정리했습니다.
                  </p>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void copyReport()}
                  >
                    {copyStatus === "copied"
                      ? "복사됨"
                      : copyStatus === "selected"
                        ? "선택됨"
                        : copyStatus === "failed"
                          ? "복사 실패"
                          : "보고서 복사"}
                  </button>
                </div>
                <textarea
                  id="report-output"
                  className="report-output"
                  value={reportText}
                  readOnly
                  aria-label="복사 가능한 다건 분석 보고서"
                />
              </ResultSection>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

export default App;
