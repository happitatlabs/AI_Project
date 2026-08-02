import type { QueryPurpose } from "./diagnosisRules";

export type SqlRecommendation = {
  type: "format" | "condition" | "performance";
  title: string;
  description: string;
  sql: string;
  caution?: string;
};

const CONDITION_BOUNDARY =
  /\b(group\s+by|order\s+by|having|limit|offset|fetch|union|intersect|except)\b/i;

const KEYWORDS = [
  "select",
  "from",
  "where",
  "left outer join",
  "right outer join",
  "inner join",
  "left join",
  "right join",
  "full join",
  "join",
  "group by",
  "order by",
  "having",
  "union all",
  "union",
  "and",
  "or",
  "on",
  "as",
];

const normalizeColumns = (columns: string[]) =>
  columns.map((column) => column.trim().toLowerCase()).filter(Boolean);

const splitSqlByStringLiteral = (sql: string) => sql.split(/('(?:''|[^'])*')/g);

const transformOutsideStringLiterals = (
  sql: string,
  transform: (chunk: string) => string,
) =>
  splitSqlByStringLiteral(sql)
    .map((chunk, index) => (index % 2 === 1 ? chunk : transform(chunk)))
    .join("");

const uppercaseKeywords = (sql: string) =>
  transformOutsideStringLiterals(sql, (chunk) => {
    let next = chunk;

    KEYWORDS.forEach((keyword) => {
      const pattern = new RegExp(
        `\\b${keyword.replace(/\s+/g, "\\s+")}\\b`,
        "gi",
      );
      next = next.replace(pattern, keyword.toUpperCase());
    });

    return next;
  });

const normalizeEquals = (sql: string) =>
  transformOutsideStringLiterals(sql, (chunk) =>
    chunk.replace(/([^<>=!])\s*=\s*(?!=|>)/g, "$1 = "),
  );

const addLineBreaksAroundKeywords = (sql: string) =>
  transformOutsideStringLiterals(sql, (chunk) =>
    chunk
      .replace(/\s+\bFROM\b\s+/gi, "\nFROM ")
      .replace(/\s+\bWHERE\b\s+/gi, "\nWHERE ")
      .replace(/\s+\b(LEFT OUTER JOIN|RIGHT OUTER JOIN|INNER JOIN|LEFT JOIN|RIGHT JOIN|FULL JOIN|JOIN)\b\s+/gi, "\n$1 ")
      .replace(/\s+\b(AND|OR)\b\s+/gi, "\n  $1 ")
      .replace(/\s+\b(GROUP BY|ORDER BY|HAVING|UNION ALL|UNION)\b\s+/gi, "\n$1 "),
  );

const formatSelectListIfSimple = (sql: string) => {
  const selectMatch = sql.match(/^SELECT\s+([\s\S]+?)\nFROM\s+/i);

  if (!selectMatch) {
    return sql;
  }

  const selectList = selectMatch[1].trim();

  if (!selectList.includes(",") || /[()]/.test(selectList)) {
    return sql;
  }

  const formattedSelectList = selectList
    .split(",")
    .map((column) => `  ${column.trim()}`)
    .join(",\n");

  return sql.replace(
    /^SELECT\s+([\s\S]+?)\nFROM\s+/i,
    `SELECT\n${formattedSelectList}\nFROM `,
  );
};

const cleanupLineWhitespace = (sql: string) =>
  sql
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line, index, lines) => line.trim() || index === lines.length - 1)
    .join("\n")
    .trim();

const removeTrailingSemicolon = (sql: string) => sql.trim().replace(/;$/, "");

const hasWhereClause = (sql: string) => /\bWHERE\b/i.test(sql);

const extractWhereClause = (sql: string) => {
  const normalized = sql.replace(/\s+/g, " ");
  const whereMatch = normalized.match(/\bwhere\b([\s\S]*)/i);

  if (!whereMatch) {
    return "";
  }

  return whereMatch[1].split(CONDITION_BOUNDARY)[0].trim();
};

const hasColumnCondition = (whereClause: string, columnName: string) => {
  const pattern = new RegExp(
    `(?:^|[^a-z0-9_])(?:[a-z0-9_]+\\.)?${columnName}(?=$|[^a-z0-9_])`,
    "i",
  );
  return pattern.test(whereClause);
};

const countKeyword = (sql: string, keyword: string) =>
  (sql.match(new RegExp(`\\b${keyword}\\b`, "gi")) ?? []).length;

const isComplexSql = (sql: string) => {
  const normalized = sql.trim();

  return (
    countKeyword(normalized, "join") >= 2 ||
    /\bGROUP\s+BY\b/i.test(normalized) ||
    /\bUNION\b/i.test(normalized) ||
    /^\s*WITH\b/i.test(normalized) ||
    /\(\s*SELECT\b/i.test(normalized)
  );
};

const buildManualReviewRecommendation = (
  type: SqlRecommendation["type"],
  title: string,
  formattedSql: string,
): SqlRecommendation => ({
  type,
  title,
  description:
    "JOIN 2개 이상, GROUP BY, UNION, 서브쿼리, WITH 절이 포함된 복잡한 SQL은 자동 변경 대신 수동 검토를 권장합니다.",
  sql: formattedSql,
  caution:
    "복잡한 SQL에서는 조건 추가나 성능 튜닝이 결과 건수와 의미를 바꿀 수 있습니다.",
});

export const formatSqlSafely = (sql: string) => {
  const compact = transformOutsideStringLiterals(sql.trim(), (chunk) =>
    chunk.replace(/[ \t\r\n]+/g, " "),
  );
  const formatted = cleanupLineWhitespace(
    formatSelectListIfSimple(
      addLineBreaksAroundKeywords(normalizeEquals(uppercaseKeywords(compact))),
    ),
  );

  return formatted || sql.trim();
};

const appendWhereConditions = (sql: string, conditions: string[]) => {
  const baseSql = removeTrailingSemicolon(sql);

  if (conditions.length === 0) {
    return baseSql;
  }

  if (!hasWhereClause(baseSql)) {
    const [firstCondition, ...restConditions] = conditions;
    const rest = restConditions
      .map((condition) => `  AND ${condition}`)
      .join("\n");

    return [baseSql, `WHERE ${firstCondition}`, rest].filter(Boolean).join("\n");
  }

  const conditionBlock = conditions
    .map((condition) => `  AND ${condition}`)
    .join("\n");
  const boundaryMatch = baseSql.match(
    /\n(GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|FETCH)\b/i,
  );

  if (!boundaryMatch || boundaryMatch.index === undefined) {
    return `${baseSql}\n${conditionBlock}`;
  }

  return `${baseSql.slice(0, boundaryMatch.index)}\n${conditionBlock}${baseSql.slice(
    boundaryMatch.index,
  )}`;
};

const buildConditionRecommendation = (
  columns: string[],
  sql: string,
  purpose: QueryPurpose,
): SqlRecommendation => {
  const formattedSql = formatSqlSafely(sql);

  if (isComplexSql(sql)) {
    return buildManualReviewRecommendation(
      "condition",
      "후보 B: 조건 보강",
      formattedSql,
    );
  }

  if (purpose !== "GENERAL") {
    return {
      type: "condition",
      title: "후보 B: 조건 보강",
      description:
        "현재 조회 목적은 일반 조회가 아니므로 조건을 자동 확정하지 않고 진단 결과를 기준으로 수동 검토하는 후보입니다.",
      sql: formattedSql,
      caution:
        "통계, 관리자, 이력, 배치 목적에서는 누락 조건이 업무상 의도된 설계일 수 있습니다.",
    };
  }

  const whereClause = extractWhereClause(sql);
  const conditions: string[] = [];

  if (columns.includes("use_yn") && !hasColumnCondition(whereClause, "use_yn")) {
    conditions.push("use_yn = 'Y'");
  }

  if (columns.includes("del_yn") && !hasColumnCondition(whereClause, "del_yn")) {
    conditions.push("del_yn = 'N'");
  }

  if (
    columns.includes("delete_yn") &&
    !hasColumnCondition(whereClause, "delete_yn")
  ) {
    conditions.push("delete_yn = 'N'");
  }

  if (
    columns.includes("status_cd") &&
    !hasColumnCondition(whereClause, "status_cd")
  ) {
    conditions.push("status_cd = /* 상태값 확인 필요 */ :statusCode");
  }

  if (columns.includes("stts_cd") && !hasColumnCondition(whereClause, "stts_cd")) {
    conditions.push("stts_cd = /* 상태값 확인 필요 */ :statusCode");
  }

  if (conditions.length === 0) {
    return {
      type: "condition",
      title: "후보 B: 조건 보강",
      description:
        "일반 조회에서 우선 보강할 사용 여부, 삭제 여부, 상태 조건 누락은 감지되지 않았습니다.",
      sql: formattedSql,
    };
  }

  return {
    type: "condition",
    title: "후보 B: 조건 보강",
    description:
      "일반 조회 기준으로 자주 필요한 운영 조건을 WHERE 절에 추가한 개선 후보입니다.",
    sql: appendWhereConditions(formattedSql, conditions),
    caution:
      "status_cd, stts_cd의 실제 코드값은 기관/프로젝트 기준 코드표를 확인한 뒤 확정해야 합니다.",
  };
};

const replaceSelectStar = (sql: string, columns: string[]) => {
  const columnList = columns.map((column) => `  ${column}`).join(",\n");
  return sql.replace(/\bSELECT\s+\*/i, `SELECT\n${columnList}`);
};

const nextDateLiteral = (dateText: string) => {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
};

const buildDateFunctionRangeSql = (sql: string) => {
  const patterns = [
    /\bTO_CHAR\s*\(\s*(reg_dt|created_at)\s*,\s*'[^']+'\s*\)\s*=\s*'(\d{4}-\d{2}-\d{2})'/i,
    /\bDATE_FORMAT\s*\(\s*(reg_dt|created_at)\s*,\s*'[^']+'\s*\)\s*=\s*'(\d{4}-\d{2}-\d{2})'/i,
    /\bCAST\s*\(\s*(reg_dt|created_at)\s+AS\s+[^)]+\)\s*=\s*'(\d{4}-\d{2}-\d{2})'/i,
  ];

  for (const pattern of patterns) {
    const match = sql.match(pattern);

    if (match) {
      const [, columnName, dateText] = match;
      const nextDate = nextDateLiteral(dateText);
      return sql.replace(
        pattern,
        `${columnName} >= DATE '${dateText}'\n  AND ${columnName} < DATE '${nextDate}'`,
      );
    }
  }

  return sql;
};

const hasDateFunctionPattern = (sql: string) =>
  /\b(TO_CHAR|DATE_FORMAT|CAST|CONVERT)\s*\(/i.test(sql) &&
  /\b(reg_dt|created_at)\b/i.test(sql);

const hasLeadingWildcardLike = (sql: string) => /\bLIKE\s+'%[^']*'/i.test(sql);

const buildPerformanceRecommendation = (
  columns: string[],
  sql: string,
): SqlRecommendation => {
  const formattedSql = formatSqlSafely(sql);

  if (isComplexSql(sql)) {
    return buildManualReviewRecommendation(
      "performance",
      "후보 C: 성능 개선",
      formattedSql,
    );
  }

  const descriptions: string[] = [];
  const cautions: string[] = [];
  let performanceSql = formattedSql;

  if (/\bSELECT\s+\*/i.test(sql)) {
    if (columns.length > 0 && columns.length <= 12) {
      performanceSql = replaceSelectStar(performanceSql, columns);
      descriptions.push(
        "SELECT * 대신 입력된 컬럼 목록을 명시한 후보입니다.",
      );
    } else {
      descriptions.push(
        "SELECT * 사용이 감지되었습니다. 컬럼이 많으므로 자동 치환보다 필요한 컬럼만 명시하는 방향을 권장합니다.",
      );
      cautions.push("필요 컬럼 기준은 화면, API 응답, 권한 정책을 함께 확인해야 합니다.");
    }
  }

  if (hasDateFunctionPattern(sql)) {
    const replacedSql = buildDateFunctionRangeSql(performanceSql);

    if (replacedSql !== performanceSql) {
      performanceSql = replacedSql;
      descriptions.push(
        "날짜 컬럼에 함수가 적용된 조건을 인덱스 사용 가능성이 높은 범위 조건 후보로 바꾸었습니다.",
      );
    } else {
      descriptions.push(
        "날짜 컬럼 함수 사용이 감지되었습니다. 날짜값 추출이 불확실하여 자동 변경 대신 범위 조건으로 수동 검토를 권장합니다.",
      );
    }
  }

  if (hasLeadingWildcardLike(sql)) {
    descriptions.push(
      "LIKE 앞쪽 와일드카드 패턴이 감지되었습니다.",
    );
    cautions.push(
      "LIKE '%검색어%' 형태는 일반 B-tree 인덱스 사용이 어려울 수 있습니다. 전문 검색 인덱스나 검색 정책을 검토하세요.",
    );
  }

  if (descriptions.length === 0) {
    descriptions.push(
      "현재 MVP 규칙에서 뚜렷한 성능 개선 패턴은 감지되지 않았습니다.",
    );
  }

  return {
    type: "performance",
    title: "후보 C: 성능 개선",
    description: descriptions.join(" "),
    sql: performanceSql,
    caution: cautions.length > 0 ? cautions.join(" ") : undefined,
  };
};

export function recommendSql(
  columns: string[],
  sql: string,
  purpose: QueryPurpose,
): SqlRecommendation[] {
  const normalizedColumns = normalizeColumns(columns);
  const formattedSql = formatSqlSafely(sql);

  return [
    {
      type: "format",
      title: "후보 A: 포맷 정리",
      description:
        "기존 SQL 의미를 최대한 바꾸지 않고 키워드, 줄바꿈, 비교 연산자 공백만 정리한 후보입니다.",
      sql: formattedSql,
    },
    buildConditionRecommendation(normalizedColumns, sql, purpose),
    buildPerformanceRecommendation(normalizedColumns, sql),
  ];
}
