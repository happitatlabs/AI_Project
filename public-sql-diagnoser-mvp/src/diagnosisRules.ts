export type Severity = "warning" | "info";

export type DiagnosisResult = {
  id: string;
  severity: Severity;
  title: string;
  description: string;
  recommendation: string;
};

export const QUERY_PURPOSES = [
  { value: "GENERAL", label: "일반 조회" },
  { value: "STATISTICS", label: "통계 조회" },
  { value: "ADMIN", label: "관리자 조회" },
  { value: "HISTORY", label: "이력 조회" },
  { value: "BATCH", label: "배치 작업" },
] as const;

export type QueryPurpose = (typeof QUERY_PURPOSES)[number]["value"];

export const PURPOSE_LABELS = Object.fromEntries(
  QUERY_PURPOSES.map((purpose) => [purpose.value, purpose.label]),
) as Record<QueryPurpose, string>;

const RULE_ORDER = [
  "useYn",
  "deleteYn",
  "status",
  "authority",
  "period",
] as const;

type DiagnosisRuleKey = (typeof RULE_ORDER)[number];

type RuleContext = {
  displayColumns: string;
  matchedColumns: string[];
  purpose: QueryPurpose;
  purposeLabel: string;
  severity: Severity;
};

type RuleDefinition = {
  id: string;
  columns: string[];
  conditionColumns?: string[];
  description: (context: RuleContext) => string;
  recommendation: (context: RuleContext) => string;
  title: (context: RuleContext) => string;
};

const exampleColumn = (matchedColumns: string[], fallbackColumn: string) =>
  matchedColumns[0] ?? fallbackColumn;

const useYnRecommendation = ({ matchedColumns, purpose }: RuleContext) => {
  const column = exampleColumn(matchedColumns, "use_yn");

  if (purpose === "ADMIN") {
    return `관리 화면에서 비활성 데이터를 의도적으로 포함하는지 명확히 표시\n예시: WHERE ${column} IN ('Y', 'N')`;
  }

  if (purpose === "STATISTICS") {
    return `통계 산식에 비활성 데이터가 포함되는지 집계 기준을 명확히 결정\n예시: WHERE ${column} = 'Y'`;
  }

  if (purpose === "HISTORY") {
    return `이력 조회에서 현재 유효 데이터만 볼지 전체 이력을 볼지 기준 명시\n예시: WHERE ${column} = 'Y'`;
  }

  if (purpose === "BATCH") {
    return `배치 대상에 비활성 데이터가 포함되어도 되는지 확인\n예시: WHERE ${column} = 'Y'`;
  }

  return `일반 사용자 조회 시 비활성 데이터 제외\n예시: WHERE ${column} = 'Y'`;
};

const deleteYnRecommendation = ({ matchedColumns, purpose }: RuleContext) => {
  const column = exampleColumn(matchedColumns, "del_yn");

  if (purpose === "BATCH") {
    return `배치 대상에 삭제 데이터가 포함되어도 되는지 확인\n예시: WHERE ${column} = 'N'`;
  }

  if (purpose === "STATISTICS") {
    return `삭제 데이터가 집계 모수에 포함되는지 통계 기준을 명확히 결정\n예시: WHERE ${column} = 'N'`;
  }

  if (purpose === "ADMIN") {
    return `관리 조회에서 삭제 데이터까지 보여줄지 화면 범위를 명확히 표시\n예시: WHERE ${column} IN ('Y', 'N')`;
  }

  if (purpose === "HISTORY") {
    return `삭제 상태 변경 이력을 포함할지 조회 목적에 맞게 결정\n예시: WHERE ${column} = 'N'`;
  }

  return `삭제 또는 폐기 데이터가 일반 결과에 섞이지 않도록 제외\n예시: WHERE ${column} = 'N'`;
};

const statusRecommendation = ({ matchedColumns, purpose }: RuleContext) => {
  const column = exampleColumn(matchedColumns, "status_cd");

  if (purpose === "HISTORY") {
    return `이력 조회에서도 상태 기준을 명확히 하여 업무 단계별 데이터를 구분\n예시: WHERE ${column} IN ('ACTIVE', 'CLOSED')`;
  }

  if (purpose === "STATISTICS") {
    return `집계 기준에 포함할 상태 범위를 먼저 확정\n예시: WHERE ${column} IN ('ACTIVE', 'CLOSED')`;
  }

  return `업무 상태 기준으로 조회 대상 범위를 제한\n예시: WHERE ${column} = 'ACTIVE'`;
};

const authorityRecommendation = ({ matchedColumns, purpose }: RuleContext) => {
  const column = exampleColumn(matchedColumns, "dept_cd");

  if (purpose === "ADMIN") {
    return `관리자 조회라도 담당 기관 또는 권한 범위를 적용\n예시: WHERE ${column} = :authorityCode`;
  }

  if (purpose === "BATCH") {
    return `배치 처리 범위가 특정 기관 또는 부서로 제한되어야 하는지 확인\n예시: WHERE ${column} = :targetOrgCode`;
  }

  if (purpose === "STATISTICS") {
    return `기관별 통계인지 전체 통계인지 집계 범위를 명확히 결정\n예시: WHERE ${column} = :statisticsOrgCode`;
  }

  if (purpose === "HISTORY") {
    return `이력 데이터도 사용자 권한 범위 안에서 조회되도록 제한 여부 확인\n예시: WHERE ${column} = :userOrgCode`;
  }

  return `사용자 소속 기관 또는 권한 범위 밖의 데이터 노출 방지\n예시: WHERE ${column} = :userOrgCode`;
};

const periodRecommendation = ({ matchedColumns, purpose }: RuleContext) => {
  const column = exampleColumn(matchedColumns, "reg_dt");

  if (purpose === "HISTORY") {
    return `이력 조회는 기간 조건을 필수로 두어 과도한 조회와 오래된 이력 혼입을 방지\n예시: WHERE ${column} >= :startDate AND ${column} < :endDate`;
  }

  if (purpose === "BATCH") {
    return `배치 처리 대상 기간이 의도한 범위인지 확인\n예시: WHERE ${column} >= :batchStartDate AND ${column} < :batchEndDate`;
  }

  return `조회 성능과 업무 범위를 위해 기간 조건 필요 여부 검토\n예시: WHERE ${column} >= :startDate AND ${column} < :endDate`;
};

const RULE_DEFINITIONS: Record<DiagnosisRuleKey, RuleDefinition> = {
  useYn: {
    id: "missing-use-yn",
    columns: ["use_yn"],
    title: ({ displayColumns }) => `${displayColumns} 조건이 없습니다.`,
    description: ({ displayColumns, purposeLabel }) =>
      `${purposeLabel} 목적에서 ${displayColumns} 컬럼이 있지만 WHERE 절에 사용 여부 조건이 없습니다.`,
    recommendation: useYnRecommendation,
  },
  deleteYn: {
    id: "missing-delete-yn",
    columns: ["del_yn", "delete_yn"],
    title: ({ displayColumns }) => `${displayColumns} 조건이 없습니다.`,
    description: ({ displayColumns, purposeLabel }) =>
      `${purposeLabel} 목적에서 ${displayColumns} 컬럼이 있지만 WHERE 절에 삭제 여부 조건이 없습니다.`,
    recommendation: deleteYnRecommendation,
  },
  status: {
    id: "missing-status",
    columns: ["status_cd", "stts_cd"],
    title: ({ displayColumns }) => `${displayColumns} 상태 조건이 없습니다.`,
    description: ({ displayColumns, purposeLabel }) =>
      `${purposeLabel} 목적에서 ${displayColumns} 컬럼이 있지만 WHERE 절에 상태 조건이 없습니다.`,
    recommendation: statusRecommendation,
  },
  authority: {
    id: "missing-authority-org",
    columns: ["dept_cd", "org_cd", "inst_cd"],
    conditionColumns: ["dept_cd", "org_cd", "inst_cd"],
    title: () =>
      "dept_cd/org_cd/inst_cd 기준 권한 또는 기관 조건이 없습니다.",
    description: ({ purposeLabel }) =>
      `${purposeLabel} 목적에서 기관 또는 부서 컬럼이 있지만 WHERE 절에 권한 범위 조건이 없습니다.`,
    recommendation: authorityRecommendation,
  },
  period: {
    id: "missing-period",
    columns: ["reg_dt", "created_at"],
    conditionColumns: ["reg_dt", "created_at"],
    title: ({ severity }) =>
      severity === "warning"
        ? "reg_dt/created_at 기간 조건이 없습니다."
        : "reg_dt/created_at 기간 조건 검토가 필요합니다.",
    description: ({ purposeLabel }) =>
      `${purposeLabel} 목적에서 등록일 또는 생성일 컬럼이 있지만 WHERE 절에 기간 조건이 없습니다.`,
    recommendation: periodRecommendation,
  },
};

export const RULES = {
  GENERAL: {
    useYn: "warning",
    deleteYn: "warning",
    status: "warning",
    authority: "warning",
    period: "info",
  },
  STATISTICS: {
    useYn: "info",
    deleteYn: "info",
    status: "info",
    authority: "info",
    period: "info",
  },
  ADMIN: {
    useYn: "info",
    deleteYn: "info",
    status: "info",
    authority: "warning",
    period: "info",
  },
  HISTORY: {
    useYn: "info",
    deleteYn: "info",
    status: "warning",
    authority: "info",
    period: "warning",
  },
  BATCH: {
    useYn: "info",
    deleteYn: "info",
    status: "info",
    authority: "info",
    period: "info",
  },
} satisfies Record<QueryPurpose, Record<DiagnosisRuleKey, Severity>>;

const stripSqlComments = (sql: string) =>
  sql
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/--.*$/gm, " ");

const normalizeSql = (sql: string) =>
  stripSqlComments(sql).toLowerCase().replace(/\s+/g, " ").trim();

const parseColumns = (columns: string) =>
  columns
    .toLowerCase()
    .split(/[\s,;]+/)
    .map((column) => column.trim())
    .filter(Boolean);

const extractWhereClause = (sql: string) => {
  const normalized = normalizeSql(sql);
  const whereMatch = normalized.match(/\bwhere\b([\s\S]*)/);

  if (!whereMatch) {
    return "";
  }

  return whereMatch[1]
    .split(
      /\b(group\s+by|order\s+by|having|limit|offset|fetch|union|intersect|except)\b/,
    )[0]
    .trim();
};

const hasWhereColumnCondition = (whereClause: string, columnNames: string[]) =>
  columnNames.some((columnName) => {
    const pattern = new RegExp(
      `(?:^|[^a-z0-9_])(?:[a-z0-9_]+\\.)?${columnName}(?=$|[^a-z0-9_])`,
      "i",
    );
    return pattern.test(whereClause);
  });

const displayColumnsFor = (
  ruleKey: DiagnosisRuleKey,
  matchedColumns: string[],
) => {
  if (ruleKey === "authority") {
    return "dept_cd/org_cd/inst_cd";
  }

  if (ruleKey === "period") {
    return "reg_dt/created_at";
  }

  return matchedColumns.join("/");
};

export function diagnoseSql(
  columns: string,
  sql: string,
  purpose: QueryPurpose = "GENERAL",
): DiagnosisResult[] {
  const parsedColumns = parseColumns(columns);
  const whereClause = extractWhereClause(sql);
  const purposeRules = RULES[purpose] ?? RULES.GENERAL;
  const purposeLabel = PURPOSE_LABELS[purpose] ?? PURPOSE_LABELS.GENERAL;

  return RULE_ORDER.flatMap((ruleKey) => {
    const ruleDefinition = RULE_DEFINITIONS[ruleKey];
    const matchedColumns = ruleDefinition.columns.filter((columnName) =>
      parsedColumns.includes(columnName),
    );

    if (matchedColumns.length === 0) {
      return [];
    }

    const conditionColumns = ruleDefinition.conditionColumns ?? matchedColumns;

    if (hasWhereColumnCondition(whereClause, conditionColumns)) {
      return [];
    }

    const severity = purposeRules[ruleKey];
    const context: RuleContext = {
      displayColumns: displayColumnsFor(ruleKey, matchedColumns),
      matchedColumns,
      purpose,
      purposeLabel,
      severity,
    };

    return [
      {
        id: ruleDefinition.id,
        severity,
        title: ruleDefinition.title(context),
        description: ruleDefinition.description(context),
        recommendation: ruleDefinition.recommendation(context),
      },
    ];
  });
}
