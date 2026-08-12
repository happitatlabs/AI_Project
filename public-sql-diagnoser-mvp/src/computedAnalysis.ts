export type DataInputFormat = "auto" | "csv" | "json";

export type DataRow = Record<string, string>;

export type DataColumnRole = "aggregate_marker" | "category" | "identifier" | "metric" | "time" | "unknown";

export type DataColumnProfile = {
  column: string;
  confidence: "high" | "low" | "medium";
  primaryRole: DataColumnRole;
  reasons: string[];
  roles: DataColumnRole[];
  statistics: {
    aggregateMarkerCount: number;
    nonEmptyCount: number;
    numericRatio: number;
    timeRatio: number;
    uniqueCount: number;
    uniqueRatio: number;
  };
};

export type DataAggregationLevel = {
  level: number;
  rowCount: number;
};

export type DataAggregationStructure = {
  aggregateRowCount: number;
  categoryColumns: string[];
  levels: DataAggregationLevel[];
};

export type DataAnalysisPlan = {
  aggregationStructure: DataAggregationStructure;
  groupCandidates: string[];
  metricCandidates: string[];
  questionSuggestions: string[];
  recommendedGroupColumn?: string;
  recommendedMetricColumn?: string;
  recommendedTimeColumn?: string;
  warnings: string[];
};

export type DataColumnOptions = {
  analysisPlan: DataAnalysisPlan;
  editable: {
    groupColumns: string[];
    metricColumns: string[];
    timeColumns: string[];
  };
  groupColumns: string[];
  metricColumns: string[];
  profiles: DataColumnProfile[];
  recommended: {
    groupColumn?: string;
    metricColumn?: string;
    timeColumn?: string;
  };
  timeColumns: string[];
};

export type DataInputInspection =
  | {
      columnOptions: DataColumnOptions;
      columns: string[];
      format: Exclude<DataInputFormat, "auto">;
      ok: true;
      rows: DataRow[];
      warnings: string[];
    }
  | {
      columnOptions: DataColumnOptions;
      columns: string[];
      error: string;
      ok: false;
      rows: DataRow[];
      warnings: string[];
    };

export type ComputedAnalysisConfig = {
  datasetName?: string;
  groupColumn?: string;
  metricColumn: string;
  timeColumn?: string;
};

export type ComputedFactCategory = "summary" | "trend" | "comparison" | "contribution" | "outlier";

export type ComputedFact = {
  category: ComputedFactCategory;
  id: string;
  label: string;
  source: "mechanical_calculation";
  statement: string;
  values: Record<string, number | string>;
};

export type ComputedSummaryMetric = {
  factId: string;
  id: "total" | "average" | "max" | "min" | "count";
  label: string;
  value: number;
};

export type ComputedTrend = {
  changeRate?: number;
  currentPeriod: string;
  currentValue: number;
  direction: "increase" | "decrease" | "stable" | "mixed";
  evidenceFactIds: string[];
  pattern:
    | "sustained_increase"
    | "sustained_decrease"
    | "stable"
    | "latest_surge"
    | "latest_drop"
    | "mixed";
  periods: Array<{
    period: string;
    rowCount: number;
    value: number;
  }>;
  previousPeriod: string;
  previousValue: number;
};

export type ComputedComparison = {
  differenceFromAverage: number;
  factId: string;
  group: string;
  rank: number;
  ratio: number;
  value: number;
};

export type ComputedChangeContribution = {
  contributionRate: number;
  currentValue: number;
  factId: string;
  group: string;
  previousValue: number;
  valueChange: number;
};

export type ComputedCrossAnalysisBasis = {
  aggregation: "sum_by_period_and_group";
  comparableGroupCount: number;
  currentPeriod: string;
  previousPeriod: string;
  skippedIncompleteGroupCount: number;
  valueCoverage: "complete" | "partial";
};

export type ComputedOutlierCandidate = {
  deviation?: number;
  factId: string;
  group?: string;
  method: "iqr" | "z_score";
  period?: string;
  reason: string;
  rowNumber: number;
  value: number;
};

export type ComputedInsightCandidate = {
  evidenceFactIds: string[];
  id: string;
  importance: "high" | "medium" | "low";
  importanceReasons: string[];
  importanceScore: number;
  title: string;
  type: "trend" | "comparison" | "contribution" | "outlier";
};

export type ComputedReportFinding = {
  evidenceFactIds: string[];
  id: string;
  statements: string[];
  title: string;
  type: "trend" | "comparison" | "contribution" | "review";
};

export type ComputedFollowUpQuestion = {
  id: string;
  question: string;
  rationale: string;
};

export type ComputedTimeCalculationBasis = {
  aggregation: "sum_by_period";
  endPeriod: string;
  granularity: "day" | "month" | "mixed" | "year";
  periodCount: number;
  recurrenceAssessment: "not_evaluated";
  startPeriod: string;
  trendAvailability: "calculated" | "insufficient_periods";
  validPeriodRowCount: number;
};

export type ComputedComparisonCalculationBasis = {
  aggregation: "sum_by_group";
  baseline: "group_average";
  displayedGroupCount: number;
  groupCount: number;
};

export type ComputedOutlierDetectionBasis = {
  candidateCount: number;
  evaluatedRowCount: number;
  iqrMultiplier: number;
  methods: Array<"iqr" | "z_score">;
  zScoreThreshold: number;
};

export type ComputedCalculationBasis = {
  comparison?: ComputedComparisonCalculationBasis;
  crossAnalysis?: ComputedCrossAnalysisBasis;
  dataQuality: {
    excludedAggregateRowCount?: number;
    excludedMetricRowCount: number;
    inputRowCount: number;
    invalidPeriodRowCount?: number;
    validMetricRowCount: number;
  };
  outlierDetection: ComputedOutlierDetectionBasis;
  summary: {
    average: "arithmetic_mean";
    count: "valid_numeric_rows";
    extrema: "min_max";
    total: "sum";
  };
  time?: ComputedTimeCalculationBasis;
};

export const COMPUTED_ANALYSIS_CONTRACT_VERSION = "computed-analysis-v2" as const;

export type ComputedAnalysisResult = {
  analysisPlan: DataAnalysisPlan;
  calculationBasis: ComputedCalculationBasis;
  changeContributions: ComputedChangeContribution[];
  comparisons: ComputedComparison[];
  config: ComputedAnalysisConfig;
  contractVersion: typeof COMPUTED_ANALYSIS_CONTRACT_VERSION;
  facts: ComputedFact[];
  followUpQuestions: ComputedFollowUpQuestion[];
  insightCandidates: ComputedInsightCandidate[];
  outliers: ComputedOutlierCandidate[];
  reportFindings: ComputedReportFinding[];
  scope: {
    columnCount: number;
    datasetName?: string;
    groupColumn?: string;
    metricColumn: string;
    rowCount: number;
    timeColumn?: string;
    validMetricRowCount: number;
  };
  summary: ComputedSummaryMetric[];
  trend?: ComputedTrend;
  warnings: string[];
};

export type ComputedAnalysisOutcome =
  | { error: string; ok: false; warnings: string[] }
  | { ok: true; result: ComputedAnalysisResult };

const MAX_ANALYSIS_ROWS = 20000;
const MAX_COMPARISON_ITEMS = 20;
const MAX_OUTLIERS = 10;
const IQR_MULTIPLIER = 1.5;
const Z_SCORE_THRESHOLD = 2.5;

export const DEFAULT_DATA_ANALYSIS_SAMPLE = `period,team,processed_count
2026-05,A,82
2026-05,B,65
2026-06,A,88
2026-06,B,70
2026-07,A,105
2026-07,B,77
2026-08,A,182
2026-08,B,86`;

const emptyColumnOptions = (): DataColumnOptions => ({
  analysisPlan: {
    aggregationStructure: {
      aggregateRowCount: 0,
      categoryColumns: [],
      levels: [],
    },
    groupCandidates: [],
    metricCandidates: [],
    questionSuggestions: [],
    warnings: [],
  },
  editable: {
    groupColumns: [],
    metricColumns: [],
    timeColumns: [],
  },
  groupColumns: [],
  metricColumns: [],
  profiles: [],
  recommended: {},
  timeColumns: [],
});

const unique = <T>(values: T[]) => Array.from(new Set(values));

const formatNumber = (value: number, maximumFractionDigits = 2) =>
  new Intl.NumberFormat("ko-KR", { maximumFractionDigits }).format(value);

const formatPercent = (value: number) => `${formatNumber(value, 1)}%`;

const toCellText = (value: unknown) => {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value);
};

const parseNumericValue = (value: string) => {
  const normalized = value.trim().replace(/,/g, "").replace(/\s+/g, "");

  if (!normalized || !/^-?(?:\d+\.?\d*|\.\d+)$/.test(normalized)) {
    return undefined;
  }

  const numericValue = Number(normalized);
  return Number.isFinite(numericValue) ? numericValue : undefined;
};

const normalizePeriod = (value: string) => {
  const normalized = value.trim();
  const yearOnly = normalized.match(/^(\d{4})$/);

  if (yearOnly) {
    const year = Number(yearOnly[1]);

    if (year < 1000 || year > 9999) {
      return undefined;
    }

    return {
      granularity: "year" as const,
      key: String(year),
      label: String(year),
      sortValue: Date.UTC(year, 0, 1),
    };
  }

  const matched = normalized.match(/^(\d{4})[-/.]?(\d{1,2})(?:[-/.](\d{1,2}))?$/);

  if (!matched) {
    return undefined;
  }

  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = matched[3] ? Number(matched[3]) : 1;

  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return undefined;
  }

  const date = new Date(Date.UTC(year, month - 1, day));

  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return undefined;
  }

  const monthLabel = `${year}-${String(month).padStart(2, "0")}`;

  return {
    granularity: matched[3] ? "day" as const : "month" as const,
    key: matched[3] ? `${monthLabel}-${String(day).padStart(2, "0")}` : monthLabel,
    label: matched[3] ? `${monthLabel}-${String(day).padStart(2, "0")}` : monthLabel,
    sortValue: date.getTime(),
  };
};

const splitCsvLine = (input: string, delimiter: string) => {
  const values: string[] = [];
  let current = "";
  let quoted = false;

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const nextChar = input[index + 1];

    if (char === '"') {
      if (quoted && nextChar === '"') {
        current += '"';
        index += 1;
        continue;
      }

      quoted = !quoted;
      continue;
    }

    if (char === delimiter && !quoted) {
      values.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  values.push(current.trim());
  return values;
};

const parseCsvRows = (input: string, delimiter: string) => {
  const rows: string[][] = [];
  let current: string[] = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const nextChar = input[index + 1];

    if (char === '"') {
      if (quoted && nextChar === '"') {
        value += '"';
        index += 1;
        continue;
      }

      quoted = !quoted;
      continue;
    }

    if (char === delimiter && !quoted) {
      current.push(value.trim());
      value = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }

      current.push(value.trim());

      if (current.some((item) => item.length > 0)) {
        rows.push(current);
      }

      current = [];
      value = "";
      continue;
    }

    value += char;
  }

  current.push(value.trim());

  if (current.some((item) => item.length > 0)) {
    rows.push(current);
  }

  if (quoted) {
    throw new Error("CSV 따옴표가 닫히지 않았습니다.");
  }

  return rows;
};

const detectCsvDelimiter = (input: string) => {
  const firstLine = input.replace(/^\uFEFF/, "").split(/\r?\n/).find((line) => line.trim()) ?? "";
  const candidates = [",", "\t", ";"];

  return candidates
    .map((candidate) => ({
      candidate,
      count: splitCsvLine(firstLine, candidate).length - 1,
    }))
    .sort((left, right) => right.count - left.count)[0]?.candidate ?? ",";
};

const normalizeHeaders = (headers: string[]) => {
  const used = new Map<string, number>();

  return headers.map((header, index) => {
    const base = header.trim() || `column_${index + 1}`;
    const count = used.get(base) ?? 0;
    used.set(base, count + 1);
    return count === 0 ? base : `${base}_${count + 1}`;
  });
};

const collectColumns = (rows: DataRow[]) => {
  const columns: string[] = [];

  rows.forEach((row) => {
    Object.keys(row).forEach((column) => {
      if (!columns.includes(column)) {
        columns.push(column);
      }
    });
  });

  return columns;
};

const columnNameScore = (column: string, patterns: RegExp[]) =>
  patterns.some((pattern) => pattern.test(column)) ? 1 : 0;

const metricNamePatterns = [/amount|count|value|sales|quantity|volume|건수|처리|매출|수량|금액|비용|인원|규모/i];
const timeNamePatterns = [/year|month|date|period|time|연도|년도|년월|일자|날짜|월|기간/i];
const groupNamePatterns = [/group|team|region|type|category|department|부서|팀|지역|구분|그룹|장르|규모/i];
const identifierNamePatterns = [/(^|[_\s])(id|key|uuid|code|no|number)([_\s]|$)/i, /아이디|식별|번호|코드/i];
const aggregateMarkerPattern = /^(?:전체(?:\s*합계)?|합계|총계|소계|all|total|grand\s*total|subtotal)$/i;

const isAggregateLikeValue = (value: string) => aggregateMarkerPattern.test(value.trim());

const ratio = (numerator: number, denominator: number) => denominator === 0 ? 0 : numerator / denominator;

const buildColumnProfile = (rows: DataRow[], column: string): DataColumnProfile => {
  const values = rows.map((row) => row[column] ?? "").filter((value) => value.trim());
  const uniqueValues = unique(values);
  const numericCount = values.filter((value) => parseNumericValue(value) !== undefined).length;
  const timeCount = values.filter((value) => normalizePeriod(value) !== undefined).length;
  const aggregateMarkerCount = values.filter(isAggregateLikeValue).length;
  const numericRatio = ratio(numericCount, values.length);
  const timeRatio = ratio(timeCount, values.length);
  const uniqueRatio = ratio(uniqueValues.length, values.length);
  const maximumGroups = Math.max(2, Math.min(50, Math.floor(rows.length / 2)));
  const metric = values.length >= 2 && numericRatio >= 0.6;
  const time = values.length >= 2 && timeRatio >= 0.6;
  const identifier = values.length >= 2 && (
    (columnNameScore(column, identifierNamePatterns) > 0 && uniqueRatio >= 0.6) ||
    (values.length >= 5 && uniqueRatio >= 0.95)
  );
  const category = values.length >= 2 && uniqueValues.length >= 2 && uniqueValues.length <= maximumGroups && numericRatio < 0.5;
  const roles: DataColumnRole[] = [];

  if (time) {
    roles.push("time");
  }
  if (metric) {
    roles.push("metric");
  }
  if (category) {
    roles.push("category");
  }
  if (identifier) {
    roles.push("identifier");
  }
  if (aggregateMarkerCount > 0) {
    roles.push("aggregate_marker");
  }

  const primaryRole: DataColumnRole = time
    ? "time"
    : metric
      ? "metric"
      : identifier
        ? "identifier"
        : category
          ? "category"
          : aggregateMarkerCount > 0
            ? "aggregate_marker"
            : "unknown";
  const primaryRatio = primaryRole === "time"
    ? timeRatio
    : primaryRole === "metric"
      ? numericRatio
      : primaryRole === "identifier"
        ? uniqueRatio
        : primaryRole === "category"
          ? 1 - uniqueRatio
          : 0;
  const nameMatchesRole = (
    (primaryRole === "time" && columnNameScore(column, timeNamePatterns) > 0) ||
    (primaryRole === "metric" && columnNameScore(column, metricNamePatterns) > 0) ||
    (primaryRole === "category" && columnNameScore(column, groupNamePatterns) > 0) ||
    (primaryRole === "identifier" && columnNameScore(column, identifierNamePatterns) > 0)
  );
  const confidence: DataColumnProfile["confidence"] = primaryRatio >= 0.9 && (nameMatchesRole || primaryRole === "time" || primaryRole === "metric")
    ? "high"
    : primaryRatio >= 0.6 || nameMatchesRole
      ? "medium"
      : "low";
  const reasons: string[] = [];

  if (primaryRole === "time") {
    reasons.push(`값의 ${formatPercent(timeRatio * 100)}가 기간 형식입니다.`);
  } else if (primaryRole === "metric") {
    reasons.push(`값의 ${formatPercent(numericRatio * 100)}가 숫자 형식입니다.`);
  } else if (primaryRole === "category") {
    reasons.push(`${formatNumber(uniqueValues.length)}개의 반복 범주 값이 있습니다.`);
  } else if (primaryRole === "identifier") {
    reasons.push(`값의 ${formatPercent(uniqueRatio * 100)}가 서로 달라 식별자 가능성이 있습니다.`);
  }

  if (nameMatchesRole) {
    reasons.push("컬럼명이 역할을 뒷받침합니다.");
  }
  if (aggregateMarkerCount > 0) {
    reasons.push(`전체·합계 표기 ${formatNumber(aggregateMarkerCount)}개가 감지되었습니다.`);
  }

  return {
    column,
    confidence,
    primaryRole,
    reasons,
    roles: roles.length > 0 ? roles : ["unknown"],
    statistics: {
      aggregateMarkerCount,
      nonEmptyCount: values.length,
      numericRatio,
      timeRatio,
      uniqueCount: uniqueValues.length,
      uniqueRatio,
    },
  };
};

const isAggregateLikeRow = (row: DataRow, categoryColumns: string[]) =>
  categoryColumns.some((column) => isAggregateLikeValue(row[column] ?? ""));

const buildAggregationStructure = (
  rows: DataRow[],
  categoryColumns: string[],
): DataAggregationStructure => {
  const levelCounts = new Map<number, number>();
  let aggregateRowCount = 0;

  rows.forEach((row) => {
    const nonAggregateDimensionCount = categoryColumns.filter((column) => {
      const value = (row[column] ?? "").trim();
      return Boolean(value) && !isAggregateLikeValue(value);
    }).length;

    levelCounts.set(
      nonAggregateDimensionCount,
      (levelCounts.get(nonAggregateDimensionCount) ?? 0) + 1,
    );

    if (isAggregateLikeRow(row, categoryColumns)) {
      aggregateRowCount += 1;
    }
  });

  return {
    aggregateRowCount,
    categoryColumns,
    levels: Array.from(levelCounts.entries())
      .map(([level, rowCount]) => ({ level, rowCount }))
      .sort((left, right) => left.level - right.level),
  };
};

const buildColumnOptions = (rows: DataRow[], columns: string[]): DataColumnOptions => {
  const profiles = columns.map((column) => buildColumnProfile(rows, column));
  const profileByColumn = new Map(profiles.map((profile) => [profile.column, profile]));
  const metricColumns = profiles
    .filter((profile) => profile.roles.includes("metric") && profile.primaryRole !== "time")
    .map((profile) => profile.column);
  const timeColumns = profiles
    .filter((profile) => profile.roles.includes("time"))
    .map((profile) => profile.column);
  const groupColumns = profiles
    .filter((profile) => profile.roles.includes("category") && profile.primaryRole !== "identifier" && profile.primaryRole !== "time")
    .map((profile) => profile.column);
  const aggregationStructure = buildAggregationStructure(rows, groupColumns);
  const recommendedMetric = [...metricColumns].sort((left, right) => {
    const leftProfile = profileByColumn.get(left);
    const rightProfile = profileByColumn.get(right);
    const leftScore = columnNameScore(left, metricNamePatterns) + (leftProfile?.confidence === "high" ? 2 : leftProfile?.confidence === "medium" ? 1 : 0);
    const rightScore = columnNameScore(right, metricNamePatterns) + (rightProfile?.confidence === "high" ? 2 : rightProfile?.confidence === "medium" ? 1 : 0);
    return rightScore - leftScore || columns.indexOf(left) - columns.indexOf(right);
  })[0];
  const recommendedTime = [...timeColumns].sort((left, right) => {
    const leftScore = columnNameScore(left, timeNamePatterns);
    const rightScore = columnNameScore(right, timeNamePatterns);
    return rightScore - leftScore || columns.indexOf(left) - columns.indexOf(right);
  })[0];
  const recommendedGroup = [...groupColumns].sort((left, right) => {
    const leftScore = columnNameScore(left, groupNamePatterns);
    const rightScore = columnNameScore(right, groupNamePatterns);
    return rightScore - leftScore || columns.indexOf(left) - columns.indexOf(right);
  })[0];
  const questionSuggestions: string[] = [];

  if (recommendedMetric && recommendedTime && recommendedGroup) {
    questionSuggestions.push(`${recommendedMetric}의 기간별 변화는 어떤 ${recommendedGroup}에서 주로 발생했습니까?`);
    questionSuggestions.push(`${recommendedGroup}별 ${recommendedMetric} 차이는 최근 기간에 어떻게 달라졌습니까?`);
  } else if (recommendedMetric && recommendedTime) {
    questionSuggestions.push(`${recommendedMetric}은 기간에 따라 어떤 흐름을 보입니까?`);
  } else if (recommendedMetric && recommendedGroup) {
    questionSuggestions.push(`${recommendedGroup}별 ${recommendedMetric} 차이는 어떻습니까?`);
  } else if (recommendedMetric) {
    questionSuggestions.push(`${recommendedMetric}의 분포와 큰 값·작은 값을 먼저 확인합니다.`);
  }

  const planWarnings: string[] = [];

  if (!recommendedMetric) {
    planWarnings.push("숫자 지표를 확신 있게 감지하지 못했습니다. 분석 기준에서 지표 컬럼을 직접 선택하세요.");
  }
  if (aggregationStructure.aggregateRowCount > 0) {
    planWarnings.push("전체·합계 표기가 감지되었습니다. 범주 컬럼의 상위 집계 행은 중복 비교를 막기 위해 자동으로 분리합니다.");
  }
  const editableMetricColumns = profiles
    .filter((profile) => profile.statistics.numericRatio > 0)
    .map((profile) => profile.column);
  const editableTimeColumns = profiles
    .filter((profile) => profile.statistics.nonEmptyCount >= 2)
    .map((profile) => profile.column);
  const editableGroupColumns = profiles
    .filter((profile) => profile.statistics.uniqueCount >= 2)
    .map((profile) => profile.column);

  return {
    analysisPlan: {
      aggregationStructure,
      groupCandidates: groupColumns,
      metricCandidates: metricColumns,
      questionSuggestions,
      recommendedGroupColumn: recommendedGroup,
      recommendedMetricColumn: recommendedMetric,
      recommendedTimeColumn: recommendedTime,
      warnings: planWarnings,
    },
    editable: {
      groupColumns: editableGroupColumns,
      metricColumns: editableMetricColumns,
      timeColumns: editableTimeColumns,
    },
    groupColumns,
    metricColumns,
    profiles,
    recommended: {
      groupColumn: recommendedGroup,
      metricColumn: recommendedMetric,
      timeColumn: recommendedTime,
    },
    timeColumns,
  };
};

const successfulInspection = (
  format: Exclude<DataInputFormat, "auto">,
  rows: DataRow[],
  warnings: string[],
): DataInputInspection => {
  const columns = collectColumns(rows);
  return {
    columnOptions: buildColumnOptions(rows, columns),
    columns,
    format,
    ok: true,
    rows,
    warnings,
  };
};

const failedInspection = (error: string, warnings: string[] = []): DataInputInspection => ({
  columnOptions: emptyColumnOptions(),
  columns: [],
  error,
  ok: false,
  rows: [],
  warnings,
});

export const inspectDataInput = (
  input: string,
  inputFormat: DataInputFormat = "auto",
): DataInputInspection => {
  const normalizedInput = input.replace(/^\uFEFF/, "").trim();

  if (!normalizedInput) {
    return failedInspection("분석할 CSV 또는 JSON 데이터를 입력하세요.");
  }

  const inferredFormat: Exclude<DataInputFormat, "auto"> =
    inputFormat === "auto"
      ? (/^[\[{]/.test(normalizedInput) ? "json" : "csv")
      : inputFormat;

  try {
    if (inferredFormat === "json") {
      const parsed = JSON.parse(normalizedInput) as unknown;
      const sourceRows = Array.isArray(parsed)
        ? parsed
        : parsed && typeof parsed === "object" && Array.isArray((parsed as Record<string, unknown>).data)
          ? (parsed as Record<string, unknown>).data as unknown[]
          : undefined;

      if (!sourceRows) {
        return failedInspection("JSON은 객체 배열 또는 data 배열을 포함한 객체여야 합니다.");
      }

      const warnings: string[] = [];
      const rows = sourceRows
        .filter((row) => row && typeof row === "object" && !Array.isArray(row))
        .slice(0, MAX_ANALYSIS_ROWS)
        .map((row) =>
          Object.fromEntries(
            Object.entries(row as Record<string, unknown>).map(([key, value]) => [key, toCellText(value)]),
          ),
        );

      if (rows.length === 0) {
        return failedInspection("분석 가능한 JSON 객체 행을 찾지 못했습니다.");
      }

      if (sourceRows.length > MAX_ANALYSIS_ROWS) {
        warnings.push(`성능 보호를 위해 처음 ${formatNumber(MAX_ANALYSIS_ROWS)}행만 계산했습니다.`);
      }

      if (rows.length !== sourceRows.length && sourceRows.length <= MAX_ANALYSIS_ROWS) {
        warnings.push("객체가 아닌 JSON 항목은 계산에서 제외했습니다.");
      }

      return successfulInspection("json", rows, warnings);
    }

    const delimiter = detectCsvDelimiter(normalizedInput);
    const rawRows = parseCsvRows(normalizedInput, delimiter);

    if (rawRows.length < 2) {
      return failedInspection("CSV에는 헤더 1행과 데이터 1행 이상이 필요합니다.");
    }

    const headers = normalizeHeaders(rawRows[0]);
    const warnings: string[] = [];
    const dataRows = rawRows.slice(1, MAX_ANALYSIS_ROWS + 1).map((values, rowIndex) => {
      if (values.length !== headers.length) {
        warnings.push(`${rowIndex + 2}행의 컬럼 수가 헤더와 달라 빈 값 또는 초과 값이 조정되었습니다.`);
      }

      return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
    });

    if (rawRows.length - 1 > MAX_ANALYSIS_ROWS) {
      warnings.push(`성능 보호를 위해 처음 ${formatNumber(MAX_ANALYSIS_ROWS)}행만 계산했습니다.`);
    }

    return successfulInspection("csv", dataRows, unique(warnings));
  } catch (error) {
    return failedInspection(
      error instanceof Error ? `데이터를 해석하지 못했습니다: ${error.message}` : "데이터를 해석하지 못했습니다.",
    );
  }
};

const percentile = (values: number[], ratio: number) => {
  if (values.length === 0) {
    return 0;
  }

  const position = (values.length - 1) * ratio;
  const lowerIndex = Math.floor(position);
  const upperIndex = Math.ceil(position);

  if (lowerIndex === upperIndex) {
    return values[lowerIndex];
  }

  const lowerValue = values[lowerIndex];
  const upperValue = values[upperIndex];
  return lowerValue + (upperValue - lowerValue) * (position - lowerIndex);
};

const populationStandardDeviation = (values: number[], average: number) => {
  if (values.length === 0) {
    return 0;
  }

  const variance = values.reduce((total, value) => total + (value - average) ** 2, 0) / values.length;
  return Math.sqrt(variance);
};

const importanceFromScore = (score: number): ComputedInsightCandidate["importance"] => {
  if (score >= 70) {
    return "high";
  }

  if (score >= 40) {
    return "medium";
  }

  return "low";
};

const buildTrend = (
  rows: Array<{ period?: ReturnType<typeof normalizePeriod>; value: number }>,
  warnings: string[],
  facts: ComputedFact[],
) => {
  const rowsWithPeriod = rows.filter((row): row is { period: NonNullable<ReturnType<typeof normalizePeriod>>; value: number } => Boolean(row.period));

  if (rowsWithPeriod.length < 2) {
    warnings.push("시간 컬럼에서 비교 가능한 기간이 2개 이상 필요해 추세를 계산하지 않았습니다.");
    return undefined;
  }

  const periodMap = new Map<string, { label: string; rowCount: number; sortValue: number; value: number }>();

  rowsWithPeriod.forEach((row) => {
    const existing = periodMap.get(row.period.key) ?? {
      label: row.period.label,
      rowCount: 0,
      sortValue: row.period.sortValue,
      value: 0,
    };
    existing.rowCount += 1;
    existing.value += row.value;
    periodMap.set(row.period.key, existing);
  });

  const periods = Array.from(periodMap.values())
    .sort((left, right) => left.sortValue - right.sortValue)
    .map(({ label, rowCount, value }) => ({ period: label, rowCount, value }));

  if (periods.length < 2) {
    warnings.push("시간 컬럼에 서로 다른 기간이 2개 이상 없어 추세를 계산하지 않았습니다.");
    return undefined;
  }

  const previous = periods[periods.length - 2];
  const current = periods[periods.length - 1];
  const changeRate = previous.value === 0
    ? undefined
    : ((current.value - previous.value) / Math.abs(previous.value)) * 100;
  const average = periods.reduce((total, period) => total + period.value, 0) / periods.length;
  const tolerance = Math.max(Math.abs(average) * 0.03, 0.000001);
  const differences = periods.slice(1).map((period, index) => period.value - periods[index].value);
  const sustainedIncrease = periods.length >= 3 && differences.every((difference) => difference >= -tolerance) && differences.some((difference) => difference > tolerance);
  const sustainedDecrease = periods.length >= 3 && differences.every((difference) => difference <= tolerance) && differences.some((difference) => difference < -tolerance);
  const stable = differences.every((difference) => Math.abs(difference) <= tolerance);
  const direction: ComputedTrend["direction"] = stable
    ? "stable"
    : current.value > previous.value
      ? "increase"
      : current.value < previous.value
        ? "decrease"
        : "mixed";
  const pattern: ComputedTrend["pattern"] = sustainedIncrease
    ? "sustained_increase"
    : sustainedDecrease
      ? "sustained_decrease"
      : stable
        ? "stable"
        : (changeRate ?? 0) >= 15
          ? "latest_surge"
          : (changeRate ?? 0) <= -15
            ? "latest_drop"
            : "mixed";
  const currentFactId = "trend-current";
  const changeFactId = "trend-change";
  const patternFactId = "trend-pattern";

  facts.push({
    category: "trend",
    id: currentFactId,
    label: "최근 기간 값",
    source: "mechanical_calculation",
    statement: `${current.period} 집계값은 ${formatNumber(current.value)}입니다.`,
    values: { period: current.period, value: current.value },
  });

  if (changeRate === undefined) {
    facts.push({
      category: "trend",
      id: changeFactId,
      label: "이전 기간 대비",
      source: "mechanical_calculation",
      statement: `${previous.period} 값이 0이어서 증감률을 계산하지 않았습니다.`,
      values: { currentValue: current.value, previousValue: previous.value },
    });
  } else {
    const directionLabel = changeRate > 0 ? "증가" : changeRate < 0 ? "감소" : "변화 없음";
    facts.push({
      category: "trend",
      id: changeFactId,
      label: "이전 기간 대비",
      source: "mechanical_calculation",
      statement: `${current.period} 값은 ${previous.period}의 ${formatNumber(previous.value)} 대비 ${formatPercent(Math.abs(changeRate))} ${directionLabel}했습니다.`,
      values: {
        changeRate,
        currentPeriod: current.period,
        currentValue: current.value,
        previousPeriod: previous.period,
        previousValue: previous.value,
      },
    });
  }

  const patternLabel: Record<ComputedTrend["pattern"], string> = {
    latest_drop: "최근 기간의 큰 폭 감소",
    latest_surge: "최근 기간의 큰 폭 증가",
    mixed: "기간별 혼합 흐름",
    stable: "일정한 수준 유지",
    sustained_decrease: "지속 감소 흐름",
    sustained_increase: "지속 증가 흐름",
  };
  facts.push({
    category: "trend",
    id: patternFactId,
    label: "추세 패턴",
    source: "mechanical_calculation",
    statement: `${periods.length}개 기간의 집계값을 기준으로 ${patternLabel[pattern]}이 계산되었습니다.`,
    values: { periodCount: periods.length, pattern },
  });

  return {
    changeRate,
    currentPeriod: current.period,
    currentValue: current.value,
    direction,
    evidenceFactIds: [currentFactId, changeFactId, patternFactId],
    pattern,
    periods,
    previousPeriod: previous.period,
    previousValue: previous.value,
  } satisfies ComputedTrend;
};

const buildComparisons = (
  rows: Array<{ group?: string; value: number }>,
  groupColumn: string | undefined,
  total: number,
  warnings: string[],
  facts: ComputedFact[],
) => {
  if (!groupColumn) {
    return [];
  }

  const groups = new Map<string, number>();

  rows.forEach((row) => {
    const group = row.group?.trim() || "(값 없음)";
    groups.set(group, (groups.get(group) ?? 0) + row.value);
  });

  if (groups.size < 2) {
    warnings.push("그룹 컬럼에 비교 가능한 값이 2개 이상 없어 그룹 비교를 계산하지 않았습니다.");
    return [];
  }

  const groupAverage = total / groups.size;
  const sorted = Array.from(groups.entries())
    .map(([group, value]) => ({ group, value }))
    .sort((left, right) => right.value - left.value || left.group.localeCompare(right.group));

  if (sorted.length > MAX_COMPARISON_ITEMS) {
    warnings.push(`그룹 비교는 상위 ${MAX_COMPARISON_ITEMS}개만 표시합니다.`);
  }

  const comparisons = sorted.slice(0, MAX_COMPARISON_ITEMS).map(({ group, value }, index) => {
    const factId = `comparison-${index + 1}`;
    const ratio = total === 0 ? 0 : (value / total) * 100;
    const differenceFromAverage = value - groupAverage;
    facts.push({
      category: "comparison",
      id: factId,
      label: `${group} 그룹 비교`,
      source: "mechanical_calculation",
      statement: `${group}의 합계는 ${formatNumber(value)}이며 전체 합계의 ${formatPercent(ratio)}입니다.`,
      values: { differenceFromAverage, group, ratio, value },
    });

    return {
      differenceFromAverage,
      factId,
      group,
      rank: index + 1,
      ratio,
      value,
    } satisfies ComputedComparison;
  });

  return comparisons;
};

const buildChangeContributions = (
  rows: Array<{
    group?: string;
    period?: NonNullable<ReturnType<typeof normalizePeriod>>;
    value: number;
  }>,
  trend: ComputedTrend | undefined,
  groupColumn: string | undefined,
  warnings: string[],
  facts: ComputedFact[],
) => {
  if (!trend || !groupColumn) {
    return {
      contributions: [],
      basis: undefined,
    };
  }

  const groups = new Map<string, {
    currentFound: boolean;
    currentValue: number;
    previousFound: boolean;
    previousValue: number;
  }>();

  rows.forEach((row) => {
    if (!row.period || (row.period.label !== trend.currentPeriod && row.period.label !== trend.previousPeriod)) {
      return;
    }

    const group = row.group?.trim() || "(값 없음)";
    const entry = groups.get(group) ?? {
      currentFound: false,
      currentValue: 0,
      previousFound: false,
      previousValue: 0,
    };

    if (row.period.label === trend.currentPeriod) {
      entry.currentFound = true;
      entry.currentValue += row.value;
    } else {
      entry.previousFound = true;
      entry.previousValue += row.value;
    }

    groups.set(group, entry);
  });

  const comparableGroups = Array.from(groups.entries())
    .filter(([, value]) => value.currentFound && value.previousFound)
    .map(([group, value]) => ({
      currentValue: value.currentValue,
      group,
      previousValue: value.previousValue,
      valueChange: value.currentValue - value.previousValue,
    }));
  const skippedIncompleteGroupCount = groups.size - comparableGroups.length;
  const totalChange = trend.currentValue - trend.previousValue;

  if (comparableGroups.length < 2 || totalChange === 0) {
    return {
      contributions: [],
      basis: undefined,
    };
  }

  const valueCoverage: ComputedCrossAnalysisBasis["valueCoverage"] = skippedIncompleteGroupCount === 0
    ? "complete"
    : "partial";

  if (valueCoverage === "partial") {
    warnings.push("기간×그룹 변화 기여도는 두 기간에 모두 기록된 그룹만 비교했습니다. 누락된 그룹이 있어 전체 변화와 완전히 일치하지 않을 수 있습니다.");
  }

  const sameDirection = comparableGroups.filter((group) => totalChange > 0 ? group.valueChange > 0 : group.valueChange < 0);
  const rankedGroups = (sameDirection.length > 0 ? sameDirection : comparableGroups)
    .sort((left, right) => totalChange > 0
      ? right.valueChange - left.valueChange || left.group.localeCompare(right.group)
      : left.valueChange - right.valueChange || left.group.localeCompare(right.group))
    .slice(0, MAX_COMPARISON_ITEMS);
  const contributions = rankedGroups.map((group, index) => {
    const factId = `contribution-${index + 1}`;
    const contributionRate = (group.valueChange / totalChange) * 100;
    const scope = valueCoverage === "complete"
      ? "전체 순변화"
      : "비교 가능한 그룹의 순변화";
    const changeLabel = group.valueChange > 0 ? "증가" : "감소";

    facts.push({
      category: "contribution",
      id: factId,
      label: `${group.group} 변화 기여도`,
      source: "mechanical_calculation",
      statement: `${trend.previousPeriod}~${trend.currentPeriod} ${scope} 중 ${group.group}의 변화는 ${formatNumber(Math.abs(group.valueChange))} ${changeLabel}이며, 순변화 대비 ${formatPercent(Math.abs(contributionRate))}입니다.`,
      values: {
        contributionRate,
        currentPeriod: trend.currentPeriod,
        currentValue: group.currentValue,
        group: group.group,
        previousPeriod: trend.previousPeriod,
        previousValue: group.previousValue,
        valueChange: group.valueChange,
      },
    });

    return {
      contributionRate,
      currentValue: group.currentValue,
      factId,
      group: group.group,
      previousValue: group.previousValue,
      valueChange: group.valueChange,
    } satisfies ComputedChangeContribution;
  });

  return {
    contributions,
    basis: {
      aggregation: "sum_by_period_and_group",
      comparableGroupCount: comparableGroups.length,
      currentPeriod: trend.currentPeriod,
      previousPeriod: trend.previousPeriod,
      skippedIncompleteGroupCount,
      valueCoverage,
    } satisfies ComputedCrossAnalysisBasis,
  };
};

const buildOutliers = (
  rows: Array<{ group?: string; period?: string; rowNumber: number; value: number }>,
  average: number,
  warnings: string[],
  facts: ComputedFact[],
) => {
  if (rows.length < 4) {
    warnings.push("값이 4건 미만이어서 IQR 이상치 후보를 계산하지 않았습니다.");
    return [];
  }

  const sortedValues = rows.map((row) => row.value).sort((left, right) => left - right);
  const q1 = percentile(sortedValues, 0.25);
  const q3 = percentile(sortedValues, 0.75);
  const iqr = q3 - q1;
  const lowerBound = q1 - iqr * IQR_MULTIPLIER;
  const upperBound = q3 + iqr * IQR_MULTIPLIER;
  const standardDeviation = populationStandardDeviation(sortedValues, average);
  const candidates = rows
    .map((row) => {
      if (iqr > 0 && (row.value < lowerBound || row.value > upperBound)) {
        return {
          ...row,
          deviation: row.value > upperBound ? row.value - upperBound : row.value - lowerBound,
          method: "iqr" as const,
          reason: row.value > upperBound
            ? `IQR 상한 ${formatNumber(upperBound)}을 초과했습니다.`
            : `IQR 하한 ${formatNumber(lowerBound)}보다 낮습니다.`,
        };
      }

      const zScore = standardDeviation > 0 ? (row.value - average) / standardDeviation : 0;

      if (Math.abs(zScore) >= Z_SCORE_THRESHOLD) {
        return {
          ...row,
          deviation: zScore,
          method: "z_score" as const,
          reason: `평균 대비 표준화 편차 ${formatNumber(zScore, 2)}가 기준을 벗어났습니다.`,
        };
      }

      return undefined;
    })
    .filter((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate))
    .sort((left, right) => Math.abs(right.deviation) - Math.abs(left.deviation))
    .slice(0, MAX_OUTLIERS);

  if (candidates.length === 0) {
    return [];
  }

  return candidates.map((candidate, index) => {
    const factId = `outlier-${index + 1}`;
    const qualifier = [candidate.period, candidate.group].filter(Boolean).join(" / ");
    facts.push({
      category: "outlier",
      id: factId,
      label: "이상치 후보",
      source: "mechanical_calculation",
      statement: `${qualifier ? `${qualifier}의 ` : ""}값 ${formatNumber(candidate.value)}은 ${candidate.reason} 이상치 후보이며 오류로 단정하지 않습니다.`,
      values: {
        ...(candidate.group ? { group: candidate.group } : {}),
        ...(candidate.period ? { period: candidate.period } : {}),
        value: candidate.value,
      },
    });

    return {
      deviation: candidate.deviation,
      factId,
      group: candidate.group,
      method: candidate.method,
      period: candidate.period,
      reason: candidate.reason,
      rowNumber: candidate.rowNumber,
      value: candidate.value,
    } satisfies ComputedOutlierCandidate;
  });
};

const buildTimeCalculationBasis = (
  rows: Array<{ period?: NonNullable<ReturnType<typeof normalizePeriod>> }>,
) => {
  const periods = new Map<string, {
    granularity: "day" | "month" | "year";
    label: string;
    sortValue: number;
  }>();
  let validPeriodRowCount = 0;

  rows.forEach((row) => {
    if (!row.period) {
      return;
    }

    validPeriodRowCount += 1;
    periods.set(row.period.key, {
      granularity: row.period.granularity,
      label: row.period.label,
      sortValue: row.period.sortValue,
    });
  });

  const sortedPeriods = Array.from(periods.values())
    .sort((left, right) => left.sortValue - right.sortValue);

  if (sortedPeriods.length === 0) {
    return undefined;
  }

  const granularities = unique(sortedPeriods.map((period) => period.granularity));

  return {
    aggregation: "sum_by_period",
    endPeriod: sortedPeriods[sortedPeriods.length - 1].label,
    granularity: granularities.length === 1 ? granularities[0] : "mixed",
    periodCount: sortedPeriods.length,
    recurrenceAssessment: "not_evaluated",
    startPeriod: sortedPeriods[0].label,
    trendAvailability: sortedPeriods.length >= 2 ? "calculated" : "insufficient_periods",
    validPeriodRowCount,
  } satisfies ComputedTimeCalculationBasis;
};

const buildComparisonCalculationBasis = (
  rows: Array<{ group?: string }>,
  groupColumn: string | undefined,
  comparisons: ComputedComparison[],
) => {
  if (!groupColumn) {
    return undefined;
  }

  return {
    aggregation: "sum_by_group",
    baseline: "group_average",
    displayedGroupCount: comparisons.length,
    groupCount: unique(rows.map((row) => row.group?.trim() || "(값 없음)")).length,
  } satisfies ComputedComparisonCalculationBasis;
};

const buildInsightCandidates = (
  trend: ComputedTrend | undefined,
  comparisons: ComputedComparison[],
  changeContributions: ComputedChangeContribution[],
  outliers: ComputedOutlierCandidate[],
) => {
  const candidates: ComputedInsightCandidate[] = [];

  const meaningfulTrend = trend && (
    Math.abs(trend.changeRate ?? 0) >= 5 ||
    ["sustained_increase", "sustained_decrease", "latest_surge", "latest_drop"].includes(trend.pattern)
  );

  if (trend && meaningfulTrend) {
    const score = Math.min(
      100,
      30 + Math.min(45, Math.abs(trend.changeRate ?? 0)) +
      (trend.pattern === "sustained_increase" || trend.pattern === "sustained_decrease" ? 20 : 0) +
      (trend.pattern === "latest_surge" || trend.pattern === "latest_drop" ? 15 : 0),
    );
    const titleMap: Record<ComputedTrend["pattern"], string> = {
      latest_drop: "최근 기간 감소 흐름",
      latest_surge: "최근 기간 증가 흐름",
      mixed: "기간별 변화 흐름",
      stable: "기간별 안정 흐름",
      sustained_decrease: "지속 감소 흐름",
      sustained_increase: "지속 증가 흐름",
    };
    candidates.push({
      evidenceFactIds: trend.evidenceFactIds,
      id: "candidate-trend",
      importance: importanceFromScore(score),
      importanceReasons: [
        "기간별 집계값을 기계식으로 비교했습니다.",
        trend.pattern === "sustained_increase" || trend.pattern === "sustained_decrease"
          ? "여러 기간에 걸친 같은 방향의 변화가 계산되었습니다."
          : "최근 기간과 직전 기간의 변화가 계산되었습니다.",
      ],
      importanceScore: Math.round(score),
      title: titleMap[trend.pattern],
      type: "trend",
    });
  }

  const leadingContribution = changeContributions[0];

  if (leadingContribution && Math.abs(leadingContribution.contributionRate) >= 25) {
    const score = Math.min(100, 35 + Math.min(55, Math.abs(leadingContribution.contributionRate)));
    candidates.push({
      evidenceFactIds: [leadingContribution.factId],
      id: "candidate-contribution",
      importance: importanceFromScore(score),
      importanceReasons: [
        "두 기간에 모두 기록된 그룹의 변화량을 기계식으로 비교했습니다.",
        "전체 또는 비교 가능한 그룹의 순변화에서 비중이 큰 그룹이 계산되었습니다.",
      ],
      importanceScore: Math.round(score),
      title: "기간 변화 기여도",
      type: "contribution",
    });
  }

  if (comparisons.length >= 2) {
    const highest = comparisons[0];
    const lowest = comparisons[comparisons.length - 1];
    const ratioGap = highest.ratio - lowest.ratio;

    if (ratioGap >= 10) {
      const score = Math.min(100, 30 + ratioGap * 1.5);
      candidates.push({
        evidenceFactIds: [highest.factId, lowest.factId],
        id: "candidate-comparison",
        importance: importanceFromScore(score),
        importanceReasons: [
          "상위와 하위 그룹의 합계 및 전체 비중을 기계식으로 비교했습니다.",
          "그룹 간 계산된 차이가 보고 기준을 넘었습니다.",
        ],
        importanceScore: Math.round(score),
        title: "그룹 간 차이",
        type: "comparison",
      });
    }
  }

  outliers.slice(0, 3).forEach((outlier, index) => {
    const score = outlier.method === "iqr" ? 78 : 65;
    candidates.push({
      evidenceFactIds: [outlier.factId],
      id: `candidate-outlier-${index + 1}`,
      importance: importanceFromScore(score),
      importanceReasons: [
        `${outlier.method === "iqr" ? "IQR" : "표준화 편차"} 기준으로 이상치 후보가 계산되었습니다.`,
        "이상치 후보는 데이터 오류가 아니라 추가 확인 대상입니다.",
      ],
      importanceScore: score,
      title: "이상치 후보 확인",
      type: "outlier",
    });
  });

  return candidates
    .sort((left, right) => right.importanceScore - left.importanceScore || left.id.localeCompare(right.id))
    .slice(0, 8);
};

const reportFindingTitle = (type: ComputedInsightCandidate["type"]) => {
  if (type === "trend") {
    return "주요 변화";
  }

  if (type === "contribution") {
    return "변화 기여도";
  }

  if (type === "comparison") {
    return "비교 결과";
  }

  return "추가 확인 항목";
};

const reportOutlierStatement = (outlier: ComputedOutlierCandidate) => {
  const qualifier = [outlier.period, outlier.group].filter(Boolean).join(" / ");
  const subject = qualifier ? `${qualifier}의 값 ${formatNumber(outlier.value)}` : `값 ${formatNumber(outlier.value)}`;

  return `${subject}은 프로그램의 통계 기준에서 일반 범위와 차이가 확인되어 추가 확인 대상으로 정리했습니다. 원인은 데이터만으로 단정할 수 없습니다.`;
};

const buildReportFindings = (
  facts: ComputedFact[],
  candidates: ComputedInsightCandidate[],
  outliers: ComputedOutlierCandidate[],
) => {
  const factMap = new Map(facts.map((fact) => [fact.id, fact]));
  const outlierMap = new Map(outliers.map((outlier) => [outlier.factId, outlier]));

  return candidates.flatMap((candidate) => {
    const statements = candidate.type === "outlier"
      ? candidate.evidenceFactIds
        .map((factId) => outlierMap.get(factId))
        .filter((outlier): outlier is ComputedOutlierCandidate => Boolean(outlier))
        .map(reportOutlierStatement)
      : candidate.evidenceFactIds
        .map((factId) => factMap.get(factId)?.statement)
        .filter((statement): statement is string => Boolean(statement));

    if (statements.length === 0) {
      return [];
    }

    return [{
      evidenceFactIds: candidate.evidenceFactIds,
      id: candidate.id,
      statements,
      title: reportFindingTitle(candidate.type),
      type: candidate.type === "outlier" ? "review" : candidate.type,
    } satisfies ComputedReportFinding];
  });
};

const buildFollowUpQuestions = (
  analysisPlan: DataAnalysisPlan,
  config: ComputedAnalysisConfig,
  trend: ComputedTrend | undefined,
  comparisons: ComputedComparison[],
  changeContributions: ComputedChangeContribution[],
  outliers: ComputedOutlierCandidate[],
) => {
  const questions: ComputedFollowUpQuestion[] = [];
  const alternateGroup = analysisPlan.groupCandidates.find((column) => column !== config.groupColumn);

  if (trend && !config.groupColumn && analysisPlan.recommendedGroupColumn) {
    questions.push({
      id: "follow-up-trend-group",
      question: `기간별 변화는 어떤 ${analysisPlan.recommendedGroupColumn}에서 발생했습니까?`,
      rationale: "기간별 합계 변화가 계산되어 비교 기준별 분해가 가능합니다.",
    });
  }

  if (changeContributions.length > 0 && alternateGroup) {
    questions.push({
      id: "follow-up-contribution-drilldown",
      question: `변화 기여도가 큰 그룹을 ${alternateGroup} 기준으로 다시 나누면 차이가 어디에서 나타납니까?`,
      rationale: "기간×그룹 변화 기여도를 계산했으며 다른 범주로 세부 분해할 수 있습니다.",
    });
  }

  if (comparisons.length >= 2 && config.timeColumn) {
    questions.push({
      id: "follow-up-comparison-over-time",
      question: "상위와 하위 그룹의 차이는 기간에 따라 유지되었습니까?",
      rationale: "그룹별 합계 차이와 기간 컬럼이 모두 확인되었습니다.",
    });
  }

  if (outliers.length > 0) {
    questions.push({
      id: "follow-up-review-values",
      question: "추가 확인 항목은 입력 오류가 아닌 특정 조건이나 집계 수준 차이로 설명될 수 있습니까?",
      rationale: "통계 기준과 차이가 있는 값이 계산되어 원인 확인이 필요합니다.",
    });
  }

  return questions.length > 0
    ? questions.slice(0, 3)
    : analysisPlan.questionSuggestions.slice(0, 2).map((question, index) => ({
      id: `follow-up-plan-${index + 1}`,
      question,
      rationale: "자동 감지한 컬럼 역할을 기준으로 제안한 분석 질문입니다.",
    }));
};

export const calculateComputedAnalysis = (
  inspection: DataInputInspection,
  config: ComputedAnalysisConfig,
): ComputedAnalysisOutcome => {
  if (!inspection.ok) {
    return {
      error: inspection.error,
      ok: false,
      warnings: inspection.warnings,
    };
  }

  if (!config.metricColumn || !inspection.columns.includes(config.metricColumn)) {
    return {
      error: "계산할 숫자 컬럼을 선택하세요.",
      ok: false,
      warnings: inspection.warnings,
    };
  }

  const warnings = [...inspection.warnings];
  const normalizedConfig: ComputedAnalysisConfig = {
    datasetName: config.datasetName?.trim() || undefined,
    groupColumn: config.groupColumn && inspection.columns.includes(config.groupColumn)
      ? config.groupColumn
      : undefined,
    metricColumn: config.metricColumn,
    timeColumn: config.timeColumn && inspection.columns.includes(config.timeColumn)
      ? config.timeColumn
      : undefined,
  };
  const numericRows = inspection.rows.flatMap((row, index) => {
    const value = parseNumericValue(row[normalizedConfig.metricColumn] ?? "");

    if (value === undefined) {
      return [];
    }

    const period = normalizedConfig.timeColumn
      ? normalizePeriod(row[normalizedConfig.timeColumn] ?? "")
      : undefined;
    const group = normalizedConfig.groupColumn
      ? row[normalizedConfig.groupColumn]?.trim() || "(값 없음)"
      : undefined;

    return [{
      group,
      isAggregateLike: isAggregateLikeRow(
        row,
        inspection.columnOptions.analysisPlan.aggregationStructure.categoryColumns,
      ) || Boolean(normalizedConfig.groupColumn && group && isAggregateLikeValue(group)),
      period,
      rowNumber: index + 2,
      value,
    }];
  });

  const invalidMetricCount = inspection.rows.length - numericRows.length;

  if (invalidMetricCount > 0) {
    warnings.push(`${invalidMetricCount}행은 숫자 컬럼 값이 아니어서 계산에서 제외했습니다.`);
  }

  if (numericRows.length === 0) {
    return {
      error: "선택한 컬럼에서 계산 가능한 숫자 값을 찾지 못했습니다.",
      ok: false,
      warnings: unique(warnings),
    };
  }

  const aggregateLikeRows = numericRows.filter((row) => row.isAggregateLike);
  const analysisRows = aggregateLikeRows.length > 0 && aggregateLikeRows.length < numericRows.length
    ? numericRows.filter((row) => !row.isAggregateLike)
    : numericRows;
  const excludedAggregateRowCount = numericRows.length - analysisRows.length;

  if (excludedAggregateRowCount > 0) {
    warnings.push(`${excludedAggregateRowCount}행은 감지된 범주 컬럼에서 전체·합계로 해석되어 요약, 비교, 이상치 계산에서 제외했습니다.`);
  } else if (aggregateLikeRows.length === numericRows.length && aggregateLikeRows.length > 0) {
    warnings.push("선택한 그룹 컬럼의 모든 값이 전체·합계로 해석되어 자동 제외하지 않았습니다. 원본 집계 수준을 확인하세요.");
  }

  const invalidPeriodRowCount = normalizedConfig.timeColumn
    ? analysisRows.filter((row) => !row.period).length
    : undefined;

  if (invalidPeriodRowCount && invalidPeriodRowCount > 0) {
    warnings.push(`${invalidPeriodRowCount}행은 시간 형식을 해석하지 못해 추세 계산에서 제외될 수 있습니다.`);
  }

  const values = analysisRows.map((row) => row.value);
  const total = values.reduce((sum, value) => sum + value, 0);
  const average = total / values.length;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const facts: ComputedFact[] = [];
  const summaryDefinitions: Array<{
    id: ComputedSummaryMetric["id"];
    label: string;
    statement: string;
    value: number;
  }> = [
    {
      id: "count",
      label: "계산 대상 건수",
      statement: `숫자로 계산된 데이터는 ${formatNumber(values.length)}건입니다.`,
      value: values.length,
    },
    {
      id: "total",
      label: "합계",
      statement: `선택한 지표의 합계는 ${formatNumber(total)}입니다.`,
      value: total,
    },
    {
      id: "average",
      label: "평균",
      statement: `선택한 지표의 평균은 ${formatNumber(average)}입니다.`,
      value: average,
    },
    {
      id: "max",
      label: "최대값",
      statement: `선택한 지표의 최대값은 ${formatNumber(max)}입니다.`,
      value: max,
    },
    {
      id: "min",
      label: "최소값",
      statement: `선택한 지표의 최소값은 ${formatNumber(min)}입니다.`,
      value: min,
    },
  ];
  const summary = summaryDefinitions.map((definition) => {
    const factId = `summary-${definition.id}`;
    facts.push({
      category: "summary",
      id: factId,
      label: definition.label,
      source: "mechanical_calculation",
      statement: definition.statement,
      values: { value: definition.value },
    });

    return {
      factId,
      id: definition.id,
      label: definition.label,
      value: definition.value,
    } satisfies ComputedSummaryMetric;
  });
  const timeCalculationBasis = normalizedConfig.timeColumn
    ? buildTimeCalculationBasis(analysisRows)
    : undefined;
  const trend = normalizedConfig.timeColumn
    ? buildTrend(analysisRows, warnings, facts)
    : undefined;
  const comparisons = buildComparisons(analysisRows, normalizedConfig.groupColumn, total, warnings, facts);
  const changeContributionResult = buildChangeContributions(
    analysisRows,
    trend,
    normalizedConfig.groupColumn,
    warnings,
    facts,
  );
  const outliers = buildOutliers(
    analysisRows.map((row) => ({
      group: row.group,
      period: row.period?.label,
      rowNumber: row.rowNumber,
      value: row.value,
    })),
    average,
    warnings,
    facts,
  );
  const calculationBasis: ComputedCalculationBasis = {
    comparison: buildComparisonCalculationBasis(analysisRows, normalizedConfig.groupColumn, comparisons),
    ...(changeContributionResult.basis ? { crossAnalysis: changeContributionResult.basis } : {}),
    dataQuality: {
      ...(excludedAggregateRowCount > 0 ? { excludedAggregateRowCount } : {}),
      excludedMetricRowCount: invalidMetricCount,
      inputRowCount: inspection.rows.length,
      ...(invalidPeriodRowCount !== undefined ? { invalidPeriodRowCount } : {}),
      validMetricRowCount: analysisRows.length,
    },
    outlierDetection: {
      candidateCount: outliers.length,
      evaluatedRowCount: analysisRows.length,
      iqrMultiplier: IQR_MULTIPLIER,
      methods: ["iqr", "z_score"],
      zScoreThreshold: Z_SCORE_THRESHOLD,
    },
    summary: {
      average: "arithmetic_mean",
      count: "valid_numeric_rows",
      extrema: "min_max",
      total: "sum",
    },
    ...(timeCalculationBasis ? { time: timeCalculationBasis } : {}),
  };
  const insightCandidates = buildInsightCandidates(
    trend,
    comparisons,
    changeContributionResult.contributions,
    outliers,
  );
  const reportFindings = buildReportFindings(facts, insightCandidates, outliers);
  const followUpQuestions = buildFollowUpQuestions(
    inspection.columnOptions.analysisPlan,
    normalizedConfig,
    trend,
    comparisons,
    changeContributionResult.contributions,
    outliers,
  );

  if (insightCandidates.length === 0) {
    warnings.push("계산 기준을 넘는 추세·그룹 차이·이상치 후보가 없어 AI 인사이트를 강제로 만들지 않습니다.");
  }

  return {
    ok: true,
    result: {
      analysisPlan: inspection.columnOptions.analysisPlan,
      calculationBasis,
      changeContributions: changeContributionResult.contributions,
      comparisons,
      config: normalizedConfig,
      contractVersion: COMPUTED_ANALYSIS_CONTRACT_VERSION,
      facts,
      followUpQuestions,
      insightCandidates,
      outliers,
      reportFindings,
      scope: {
        columnCount: inspection.columns.length,
        datasetName: normalizedConfig.datasetName,
        groupColumn: normalizedConfig.groupColumn,
        metricColumn: normalizedConfig.metricColumn,
        rowCount: inspection.rows.length,
        timeColumn: normalizedConfig.timeColumn,
        validMetricRowCount: analysisRows.length,
      },
      summary,
      trend,
      warnings: unique(warnings),
    },
  };
};

export const computedInsightLabel = (importance: ComputedInsightCandidate["importance"]) => {
  if (importance === "high") {
    return "높음";
  }

  if (importance === "medium") {
    return "보통";
  }

  return "낮음";
};

export const computedTrendLabel = (pattern: ComputedTrend["pattern"]) => {
  const labels: Record<ComputedTrend["pattern"], string> = {
    latest_drop: "최근 기간 급감",
    latest_surge: "최근 기간 급증",
    mixed: "혼합 흐름",
    stable: "일정한 수준",
    sustained_decrease: "지속 감소",
    sustained_increase: "지속 증가",
  };

  return labels[pattern];
};

export const formatComputedNumber = formatNumber;
export const formatComputedPercent = formatPercent;
