export type SqlTable = {
  rawName: string;
  schemaName?: string;
  tableName: string;
  alias?: string;
  description: string;
  entityLabel: string;
  category: string;
  source?: "main" | "subquery";
};

export type JoinRelation = {
  left: string;
  right: string;
  joinType?: string;
  raw: string;
  rightTable?: string;
  explanation?: string;
};

export type StageFilter = {
  condition: string;
  description: string;
  stage: string;
};

export type CteAnalysis = {
  dependencies: string[];
  filters: StageFilter[];
  groupBy: string[];
  name: string;
  role: string;
};

export type GroupByAnalysis = {
  columns: string[];
  description: string;
  stage: string;
};

export type AggregationAnalysis = {
  alias?: string;
  description: string;
  expression: string;
  functionName: string;
  stage: string;
};

export type WindowFunctionAnalysis = {
  alias?: string;
  description: string;
  expression: string;
  functionName: string;
  orderBy?: string;
  partitionBy?: string;
  rows?: string;
  stage: string;
};

export type CaseExpressionAnalysis = {
  alias?: string;
  description: string;
  rules: string[];
  stage: string;
};

export type DerivedColumnAnalysis = {
  alias: string;
  description: string;
  expression: string;
  stage: string;
};

export type SubqueryAnalysis = {
  description: string;
  sql: string;
  stage: string;
  tables: string[];
  type: "exists" | "in" | "scalar" | "derived_table" | "nested";
};

export type SetOperationAnalysis = {
  description: string;
  operator: "UNION" | "UNION ALL" | "EXCEPT" | "INTERSECT";
};

export type AnalysisConfidence = {
  level: "low" | "medium" | "high";
  reasons: string[];
  score: number;
};

export type BusinessIntentType =
  | "lookup"
  | "list_query"
  | "order_list"
  | "analytics_report"
  | "sales_summary"
  | "aggregation_report"
  | "ranking_analysis"
  | "classification"
  | "derived_column_explanation"
  | "staged_query"
  | "data_preparation"
  | "data_insert"
  | "batch_etl"
  | "set_operation"
  | "combined_result";

export type BusinessIntent = {
  confidence: number;
  reasons: string[];
  type: BusinessIntentType;
};

export type SqlExplanation = {
  aggregations: AggregationAnalysis[];
  businessIntent: BusinessIntent;
  summary: string;
  caseExpressions: CaseExpressionAnalysis[];
  confidence: AnalysisConfidence;
  ctes: CteAnalysis[];
  derivedColumns: DerivedColumnAnalysis[];
  finalResult: string;
  filters: StageFilter[];
  groupBy: GroupByAnalysis[];
  havingConditions: StageFilter[];
  notes: string[];
  setOperations: SetOperationAnalysis[];
  subqueries: SubqueryAnalysis[];
  tables: SqlTable[];
  warnings: string[];
  whereConditions: string[];
  joins: JoinRelation[];
  relations: JoinRelation[];
  businessGuesses: string[];
  developerExplanation: string;
  windowFunctions: WindowFunctionAnalysis[];
};

export type SqlAnalysisResult = SqlExplanation;

type DomainRule = {
  category: string;
  entityLabel: string;
  description: string;
  patterns: RegExp[];
  businessGuesses: string[];
};

export const DEFAULT_SQL = `SELECT A.EMP_NO
     , A.EMP_NM
     , B.DEPT_NM
FROM TB_EMP A
JOIN TB_DEPT B
  ON A.DEPT_CD = B.DEPT_CD
WHERE A.USE_YN = 'Y';`;

const DOMAIN_RULES: DomainRule[] = [
  {
    category: "employee",
    entityLabel: "직원",
    description: "직원 정보",
    patterns: [/(^|_)EMP($|_)/, /EMPLOYEE/, /EMPL/, /STAFF/],
    businessGuesses: ["직원 조회 화면", "인사 관리", "권한 관리"],
  },
  {
    category: "department",
    entityLabel: "부서",
    description: "부서 정보",
    patterns: [/(^|_)DEPT($|_)/, /DEPARTMENT/],
    businessGuesses: ["조직도 조회", "부서 관리", "권한 관리"],
  },
  {
    category: "organization",
    entityLabel: "조직",
    description: "조직 정보",
    patterns: [/(^|_)ORG($|_)/, /ORGANIZATION/, /INST/, /OFFICE/],
    businessGuesses: ["조직도 조회", "조직 관리", "기관별 현황"],
  },
  {
    category: "region",
    entityLabel: "지역",
    description: "지역 정보로 추정",
    patterns: [/REGION/, /AREA/],
    businessGuesses: ["지역별 분석", "영업 권역 리포트", "고객 분포 확인"],
  },
  {
    category: "authorization",
    entityLabel: "권한",
    description: "권한 정보",
    patterns: [/AUTH/, /ROLE/, /PERMISSION/, /PRIV/],
    businessGuesses: ["권한 관리", "관리자 화면", "사용자 접근 제어"],
  },
  {
    category: "user",
    entityLabel: "사용자",
    description: "사용자 정보",
    patterns: [/(^|_)USER($|_)/, /ACCOUNT/, /ACCT/],
    businessGuesses: ["사용자 조회 화면", "계정 관리", "권한 관리"],
  },
  {
    category: "code",
    entityLabel: "코드",
    description: "공통 코드 정보로 추정",
    patterns: [/(^|_)CODE($|_)/, /COMM_CD/, /COMMON_CODE/],
    businessGuesses: ["공통 코드 관리", "기준 정보 조회", "관리자 설정"],
  },
  {
    category: "mapping",
    entityLabel: "매핑",
    description: "매핑 기준 정보로 추정",
    patterns: [/MAPPING/, /MAP($|_)/, /_MAP_/],
    businessGuesses: ["기준 정보 매핑", "데이터 변환 규칙 확인", "관리자 설정"],
  },
  {
    category: "meta",
    entityLabel: "메타",
    description: "메타 정보로 추정",
    patterns: [/META/, /METADATA/],
    businessGuesses: ["메타 정보 조회", "시스템 설정 확인", "관리자 설정"],
  },
  {
    category: "customer",
    entityLabel: "고객",
    description: "고객 정보",
    patterns: [/CUSTOMER/, /CUST/],
    businessGuesses: ["고객 조회 화면", "고객 관리", "상담 업무"],
  },
  {
    category: "order",
    entityLabel: "주문",
    description: "주문 정보",
    patterns: [/(^|_)ORDER($|_)/, /ORD/],
    businessGuesses: ["주문 조회 화면", "거래 관리", "정산 확인"],
  },
  {
    category: "product",
    entityLabel: "상품",
    description: "상품 정보",
    patterns: [/PRODUCT/, /PROD/, /ITEM/],
    businessGuesses: ["상품 조회 화면", "상품 관리", "판매 관리"],
  },
  {
    category: "payment",
    entityLabel: "결제",
    description: "결제 정보",
    patterns: [/PAYMENT/, /PAY/, /BILL/],
    businessGuesses: ["결제 조회 화면", "정산 관리", "거래 추적"],
  },
  {
    category: "history",
    entityLabel: "이력",
    description: "이력 정보",
    patterns: [/HIST/, /HISTORY/, /LOG/, /AUDIT/],
    businessGuesses: ["이력 조회 화면", "감사 추적", "변경 내역 확인"],
  },
];

const SQL_KEYWORDS = new Set([
  "AS",
  "ON",
  "WHERE",
  "JOIN",
  "LEFT",
  "RIGHT",
  "INNER",
  "OUTER",
  "FULL",
  "CROSS",
  "GROUP",
  "ORDER",
  "HAVING",
  "LIMIT",
  "OFFSET",
  "FETCH",
  "UNION",
]);

const JOIN_BOUNDARY =
  "\\b(LEFT\\s+OUTER\\s+JOIN|RIGHT\\s+OUTER\\s+JOIN|FULL\\s+OUTER\\s+JOIN|INNER\\s+JOIN|LEFT\\s+JOIN|RIGHT\\s+JOIN|FULL\\s+JOIN|CROSS\\s+JOIN|JOIN|WHERE|GROUP\\s+BY|ORDER\\s+BY|HAVING|LIMIT|OFFSET|FETCH|UNION|INTERSECT|EXCEPT)\\b";

const TOP_LEVEL_BOUNDARY_KEYWORDS = [
  "GROUP BY",
  "ORDER BY",
  "HAVING",
  "LIMIT",
  "OFFSET",
  "FETCH",
  "UNION",
  "INTERSECT",
  "EXCEPT",
];

const SQL_IDENTIFIER_COMPONENT_PATTERN =
  "(?:\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|\\[(?:[^\\]]|\\]\\])*\\]|[A-Za-z0-9_$#]+)";

const SQL_IDENTIFIER_PATTERN = `${SQL_IDENTIFIER_COMPONENT_PATTERN}(?:\\s*\\.\\s*${SQL_IDENTIFIER_COMPONENT_PATTERN})*`;

const tableRefPattern = () =>
  new RegExp(
    `\\b(FROM|LEFT\\s+OUTER\\s+JOIN|RIGHT\\s+OUTER\\s+JOIN|FULL\\s+OUTER\\s+JOIN|INNER\\s+JOIN|LEFT\\s+JOIN|RIGHT\\s+JOIN|FULL\\s+JOIN|CROSS\\s+JOIN|JOIN)\\s+(${SQL_IDENTIFIER_PATTERN})(?:\\s+(?:AS\\s+)?(${SQL_IDENTIFIER_COMPONENT_PATTERN}))?`,
    "gi",
  );

const stripSqlComments = (sql: string) => {
  let result = "";
  let quote: "'" | "\"" | "`" | "]" | null = null;

  for (let index = 0; index < sql.length; index += 1) {
    const char = sql[index];
    const nextChar = sql[index + 1];

    if (quote) {
      result += char;

      if (quote === "'" && char === "'" && nextChar === "'") {
        result += nextChar;
        index += 1;
        continue;
      }

      if (quote === "\"" && char === "\"" && nextChar === "\"") {
        result += nextChar;
        index += 1;
        continue;
      }

      if (quote === "`" && char === "`" && nextChar === "`") {
        result += nextChar;
        index += 1;
        continue;
      }

      if (quote === "]" && char === "]" && nextChar === "]") {
        result += nextChar;
        index += 1;
        continue;
      }

      if (
        (quote === "'" && char === "'") ||
        (quote === "\"" && char === "\"") ||
        (quote === "`" && char === "`") ||
        (quote === "]" && char === "]")
      ) {
        quote = null;
      }

      continue;
    }

    if (char === "-" && nextChar === "-") {
      while (index < sql.length && sql[index] !== "\n") {
        index += 1;
      }

      result += " ";
      continue;
    }

    if (char === "/" && nextChar === "*") {
      index += 2;

      while (index < sql.length && !(sql[index] === "*" && sql[index + 1] === "/")) {
        index += 1;
      }

      index += 1;
      result += " ";
      continue;
    }

    if (char === "'" || char === "\"" || char === "`") {
      quote = char;
      result += char;
      continue;
    }

    if (char === "[") {
      quote = "]";
      result += char;
      continue;
    }

    result += char;
  }

  return result;
};

const collapseSqlWhitespace = (sql: string) => {
  let result = "";
  let quote: "'" | "\"" | "`" | "]" | null = null;
  let previousWasWhitespace = false;

  for (let index = 0; index < sql.length; index += 1) {
    const char = sql[index];
    const nextChar = sql[index + 1];

    if (quote) {
      result += char;

      if (
        ((quote === "'" || quote === "\"" || quote === "`") && char === quote && nextChar === quote) ||
        (quote === "]" && char === "]" && nextChar === "]")
      ) {
        result += nextChar;
        index += 1;
        continue;
      }

      if (
        (quote === "'" && char === "'") ||
        (quote === "\"" && char === "\"") ||
        (quote === "`" && char === "`") ||
        (quote === "]" && char === "]")
      ) {
        quote = null;
      }

      continue;
    }

    if (char === "'" || char === "\"" || char === "`") {
      quote = char;
      result += char;
      previousWasWhitespace = false;
      continue;
    }

    if (char === "[") {
      quote = "]";
      result += char;
      previousWasWhitespace = false;
      continue;
    }

    if (/\s/.test(char)) {
      if (!previousWasWhitespace) {
        result += " ";
        previousWasWhitespace = true;
      }

      continue;
    }

    result += char;
    previousWasWhitespace = false;
  }

  return result.trim();
};

const compactSql = (sql: string) =>
  collapseSqlWhitespace(stripSqlComments(sql));

const trimSqlText = (value: string) => value.trim().replace(/;$/, "").trim();

const isIdentifierChar = (char: string | undefined) =>
  Boolean(char && /[A-Za-z0-9_$#]/.test(char));

const trimIdentifierPunctuation = (identifier: string) =>
  identifier.trim().replace(/[,;]$/g, "");

const unquoteIdentifierPart = (identifier: string) => {
  const trimmed = trimIdentifierPunctuation(identifier);

  if (trimmed.startsWith("\"") && trimmed.endsWith("\"")) {
    return trimmed.slice(1, -1).replace(/""/g, "\"");
  }

  if (trimmed.startsWith("`") && trimmed.endsWith("`")) {
    return trimmed.slice(1, -1).replace(/``/g, "`");
  }

  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    return trimmed.slice(1, -1).replace(/]]/g, "]");
  }

  return trimmed;
};

const splitIdentifierParts = (identifier: string) => {
  const parts: string[] = [];
  let current = "";
  let quote: "\"" | "`" | "]" | null = null;

  for (let index = 0; index < identifier.length; index += 1) {
    const char = identifier[index];
    const nextChar = identifier[index + 1];

    if (quote) {
      current += char;

      if (
        ((quote === "\"" || quote === "`") && char === quote && nextChar === quote) ||
        (quote === "]" && char === "]" && nextChar === "]")
      ) {
        current += nextChar;
        index += 1;
        continue;
      }

      if (
        (quote === "\"" && char === "\"") ||
        (quote === "`" && char === "`") ||
        (quote === "]" && char === "]")
      ) {
        quote = null;
      }

      continue;
    }

    if (char === "\"" || char === "`") {
      quote = char;
      current += char;
      continue;
    }

    if (char === "[") {
      quote = "]";
      current += char;
      continue;
    }

    if (char === ".") {
      const trimmed = current.trim();

      if (trimmed) {
        parts.push(trimmed);
      }

      current = "";
      continue;
    }

    current += char;
  }

  const trimmed = current.trim();

  if (trimmed) {
    parts.push(trimmed);
  }

  return parts.map(unquoteIdentifierPart);
};

const parseTableIdentifier = (identifier: string) => {
  const rawName = trimIdentifierPunctuation(identifier);
  const parts = splitIdentifierParts(rawName);
  const tableName = parts[parts.length - 1] ?? unquoteIdentifierPart(rawName);
  const schemaName = parts.length > 1 ? parts.slice(0, -1).join(".") : undefined;

  return {
    rawName,
    schemaName,
    tableName,
  };
};

const cleanIdentifier = (identifier: string) =>
  splitIdentifierParts(trimIdentifierPunctuation(identifier)).join(".");

const simpleTableName = (tableName: string) => {
  return parseTableIdentifier(tableName).tableName;
};

const normalizeForDomain = (tableName: string) =>
  simpleTableName(tableName)
    .toUpperCase()
    .replace(/^(TB|TBL|TM|TS|TC|M|T)_/, "");

const findDomainRule = (tableName: string) => {
  const normalized = normalizeForDomain(tableName);
  return DOMAIN_RULES.find((rule) =>
    rule.patterns.some((pattern) => pattern.test(normalized)),
  );
};

const unique = <T>(values: T[]) => Array.from(new Set(values));

const matchesKeywordAt = (sql: string, index: number, keyword: string) => {
  const upperSql = sql.toUpperCase();
  const upperKeyword = keyword.toUpperCase();

  if (upperSql.slice(index, index + upperKeyword.length) !== upperKeyword) {
    return false;
  }

  return (
    !isIdentifierChar(sql[index - 1]) &&
    !isIdentifierChar(sql[index + upperKeyword.length])
  );
};

const findMatchingParen = (sql: string, openIndex: number) => {
  let quote: "'" | "\"" | null = null;
  let depth = 0;

  for (let index = openIndex; index < sql.length; index += 1) {
    const char = sql[index];

    if (quote) {
      if (char === quote) {
        const followingChar = sql[index + 1];

        if (followingChar === quote) {
          index += 1;
          continue;
        }

        quote = null;
      }

      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    if (char === "(") {
      depth += 1;
      continue;
    }

    if (char === ")") {
      depth -= 1;

      if (depth === 0) {
        return index;
      }
    }
  }

  return -1;
};

const findTopLevelKeyword = (
  sql: string,
  keywords: string[],
  startIndex = 0,
) => {
  let quote: "'" | "\"" | null = null;
  let depth = 0;

  for (let index = startIndex; index < sql.length; index += 1) {
    const char = sql[index];

    if (quote) {
      if (char === quote) {
        const followingChar = sql[index + 1];

        if (followingChar === quote) {
          index += 1;
          continue;
        }

        quote = null;
      }

      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    if (char === "(") {
      depth += 1;
      continue;
    }

    if (char === ")") {
      depth = Math.max(0, depth - 1);
      continue;
    }

    if (depth === 0) {
      const matchedKeyword = keywords.find((keyword) =>
        matchesKeywordAt(sql, index, keyword),
      );

      if (matchedKeyword) {
        return { index, keyword: matchedKeyword };
      }
    }
  }

  return null;
};

type CteDefinition = {
  body: string;
  endIndex: number;
  name: string;
};

type CteMetadata = {
  names: Set<string>;
  sourceMap: Map<string, string>;
};

const readIdentifier = (sql: string, startIndex: number) => {
  const match = sql
    .slice(startIndex)
    .match(new RegExp(`^${SQL_IDENTIFIER_PATTERN}`, "i"));

  if (!match) {
    return null;
  }

  return {
    endIndex: startIndex + match[0].length,
    value: cleanIdentifier(match[0]),
  };
};

const skipWhitespace = (sql: string, startIndex: number) => {
  let index = startIndex;

  while (/\s/.test(sql[index] ?? "")) {
    index += 1;
  }

  return index;
};

const extractCteDefinitions = (sql: string): CteDefinition[] => {
  const normalized = compactSql(sql);

  if (!matchesKeywordAt(normalized, 0, "WITH")) {
    return [];
  }

  const definitions: CteDefinition[] = [];
  let index = skipWhitespace(normalized, "WITH".length);

  if (matchesKeywordAt(normalized, index, "RECURSIVE")) {
    index = skipWhitespace(normalized, index + "RECURSIVE".length);
  }

  while (index < normalized.length) {
    const identifier = readIdentifier(normalized, index);

    if (!identifier) {
      break;
    }

    const cteName = identifier.value;
    index = skipWhitespace(normalized, identifier.endIndex);

    if (normalized[index] === "(") {
      const columnListEndIndex = findMatchingParen(normalized, index);

      if (columnListEndIndex === -1) {
        break;
      }

      index = skipWhitespace(normalized, columnListEndIndex + 1);
    }

    if (!matchesKeywordAt(normalized, index, "AS")) {
      break;
    }

    index = skipWhitespace(normalized, index + "AS".length);

    if (normalized[index] !== "(") {
      break;
    }

    const bodyEndIndex = findMatchingParen(normalized, index);

    if (bodyEndIndex === -1) {
      break;
    }

    definitions.push({
      body: normalized.slice(index + 1, bodyEndIndex),
      endIndex: bodyEndIndex + 1,
      name: cteName,
    });

    index = skipWhitespace(normalized, bodyEndIndex + 1);

    if (normalized[index] !== ",") {
      break;
    }

    index = skipWhitespace(normalized, index + 1);
  }

  return definitions;
};

const findFirstSourceTable = (
  sql: string,
  cteNames: Set<string>,
  cteSourceMap: Map<string, string>,
) => {
  const normalized = compactSql(sql);

  for (const match of normalized.matchAll(tableRefPattern())) {
    const tableName = cleanIdentifier(match[2] ?? "");
    const upperTableName = tableName.toUpperCase();

    if (!tableName || tableName.startsWith("(")) {
      continue;
    }

    if (cteNames.has(upperTableName)) {
      const sourceTable = cteSourceMap.get(upperTableName);

      if (sourceTable) {
        return sourceTable;
      }

      continue;
    }

    return tableName;
  }

  return undefined;
};

const extractCteMetadata = (sql: string): CteMetadata => {
  const definitions = extractCteDefinitions(sql);
  const names = new Set(definitions.map((definition) => definition.name.toUpperCase()));
  const sourceMap = new Map<string, string>();

  for (let pass = 0; pass < definitions.length; pass += 1) {
    let changed = false;

    definitions.forEach((definition) => {
      const key = definition.name.toUpperCase();

      if (sourceMap.has(key)) {
        return;
      }

      const sourceTable = findFirstSourceTable(definition.body, names, sourceMap);

      if (sourceTable) {
        sourceMap.set(key, sourceTable);
        changed = true;
      }
    });

    if (!changed) {
      break;
    }
  }

  return { names, sourceMap };
};

const parenDepthAt = (sql: string, targetIndex: number) => {
  let quote: "'" | "\"" | null = null;
  let depth = 0;

  for (let index = 0; index < targetIndex; index += 1) {
    const char = sql[index];

    if (quote) {
      if (char === quote) {
        const followingChar = sql[index + 1];

        if (followingChar === quote) {
          index += 1;
          continue;
        }

        quote = null;
      }

      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    if (char === "(") {
      depth += 1;
      continue;
    }

    if (char === ")") {
      depth = Math.max(0, depth - 1);
    }
  }

  return depth;
};

const FROM_LIST_BOUNDARY_KEYWORDS = [
  "WHERE",
  "LEFT OUTER JOIN",
  "RIGHT OUTER JOIN",
  "FULL OUTER JOIN",
  "INNER JOIN",
  "LEFT JOIN",
  "RIGHT JOIN",
  "FULL JOIN",
  "CROSS JOIN",
  "JOIN",
  ...TOP_LEVEL_BOUNDARY_KEYWORDS,
];

const findFromListEnd = (sql: string, startIndex: number) => {
  const baseDepth = parenDepthAt(sql, startIndex);
  let quote: "'" | "\"" | null = null;
  let depth = baseDepth;

  for (let index = startIndex; index < sql.length; index += 1) {
    const char = sql[index];

    if (quote) {
      if (char === quote) {
        const followingChar = sql[index + 1];

        if (followingChar === quote) {
          index += 1;
          continue;
        }

        quote = null;
      }

      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    if (char === "(") {
      depth += 1;
      continue;
    }

    if (char === ")") {
      if (depth === baseDepth) {
        return index;
      }

      depth = Math.max(baseDepth, depth - 1);
      continue;
    }

    if (
      depth === baseDepth &&
      FROM_LIST_BOUNDARY_KEYWORDS.some((keyword) =>
        matchesKeywordAt(sql, index, keyword),
      )
    ) {
      return index;
    }
  }

  return sql.length;
};

const inferTableInfo = (tableName: string) => {
  const rule = findDomainRule(tableName);

  if (rule) {
    return {
      category: rule.category,
      description: rule.description,
      entityLabel: rule.entityLabel,
    };
  }

  return {
    category: "unknown",
    description: `${simpleTableName(tableName)} 업무 데이터로 추정`,
    entityLabel: simpleTableName(tableName),
  };
};

const isIndexInsideSubquery = (
  index: number | undefined,
  subqueries: Array<{ endIndex?: number; startIndex?: number }>,
) =>
  index !== undefined &&
  subqueries.some((subquery) =>
    subquery.startIndex !== undefined &&
    subquery.endIndex !== undefined &&
    index >= subquery.startIndex &&
    index <= subquery.endIndex,
  );

const extractTableRefs = (
  sql: string,
  cteMetadata: CteMetadata,
  subqueries: Array<{ endIndex?: number; startIndex?: number }> = [],
): SqlTable[] => {
  const normalized = compactSql(sql);
  const tables: SqlTable[] = [];
  const seen = new Set<string>();
  const tableByKey = new Map<string, SqlTable>();

  const addTable = (
    rawTableName: string,
    rawAlias?: string,
    source: "main" | "subquery" = "main",
  ) => {
    const parsed = parseTableIdentifier(rawTableName);
    const tableName = parsed.tableName;
    const aliasCandidate = cleanIdentifier(rawAlias ?? "");
    const alias =
      aliasCandidate && !SQL_KEYWORDS.has(aliasCandidate.toUpperCase())
        ? aliasCandidate
        : undefined;

    if (
      !tableName ||
      parsed.rawName.startsWith("(") ||
      cteMetadata.names.has(tableName.toUpperCase())
    ) {
      return;
    }

    const key = `${parsed.rawName.toUpperCase()}::${alias?.toUpperCase() ?? ""}`;

    if (seen.has(key)) {
      const existingTable = tableByKey.get(key);

      if (existingTable && source === "main") {
        existingTable.source = "main";
      } else if (existingTable && source === "subquery" && existingTable.source !== "main") {
        existingTable.source = "subquery";
      }

      return;
    }

    const info = inferTableInfo(tableName);
    const table: SqlTable = {
      rawName: parsed.rawName,
      schemaName: parsed.schemaName,
      tableName,
      alias,
      source,
      ...info,
    };

    tables.push(table);
    seen.add(key);
    tableByKey.set(key, table);
  };

  for (const match of normalized.matchAll(tableRefPattern())) {
    const tableName = cleanIdentifier(match[2] ?? "");
    const alias = cleanIdentifier(match[3] ?? "");

    addTable(
      tableName,
      alias,
      isIndexInsideSubquery(match.index, subqueries) ? "subquery" : "main",
    );
  }

  for (const match of normalized.matchAll(tableRefPattern())) {
    const clauseType = (match[1] ?? "").toUpperCase();

    if (clauseType !== "FROM") {
      continue;
    }

    const segmentStart = (match.index ?? 0) + match[0].length;
    const segmentEnd = findFromListEnd(normalized, segmentStart);
    let segmentIndex = 0;
    const segment = normalized.slice(segmentStart, segmentEnd);

    while (segmentIndex < segment.length) {
      segmentIndex = skipWhitespace(segment, segmentIndex);

      if (segment[segmentIndex] !== ",") {
        break;
      }

      segmentIndex = skipWhitespace(segment, segmentIndex + 1);

      const tableIdentifier = readIdentifier(segment, segmentIndex);

      if (!tableIdentifier) {
        break;
      }

      segmentIndex = skipWhitespace(segment, tableIdentifier.endIndex);

      let alias: string | undefined;

      if (matchesKeywordAt(segment, segmentIndex, "AS")) {
        segmentIndex = skipWhitespace(segment, segmentIndex + "AS".length);
      }

      const aliasIdentifier = readIdentifier(segment, segmentIndex);

      if (
        aliasIdentifier &&
        !SQL_KEYWORDS.has(aliasIdentifier.value.toUpperCase()) &&
        segment[segmentIndex - 1] !== "."
      ) {
        alias = aliasIdentifier.value;
        segmentIndex = aliasIdentifier.endIndex;
      }

      addTable(tableIdentifier.value, alias);
    }
  }

  return tables;
};

const extractVirtualAliasMap = (sql: string, cteMetadata: CteMetadata) => {
  const normalized = compactSql(sql);
  const aliasMap = new Map<string, string>();

  for (const [cteName, sourceTable] of cteMetadata.sourceMap) {
    aliasMap.set(cteName, sourceTable);
  }

  for (const match of normalized.matchAll(tableRefPattern())) {
    const tableName = cleanIdentifier(match[2] ?? "");
    const aliasCandidate = cleanIdentifier(match[3] ?? "");
    const sourceTable = cteMetadata.sourceMap.get(tableName.toUpperCase());

    if (!sourceTable) {
      continue;
    }

    aliasMap.set(tableName.toUpperCase(), sourceTable);

    if (aliasCandidate && !SQL_KEYWORDS.has(aliasCandidate.toUpperCase())) {
      aliasMap.set(aliasCandidate.toUpperCase(), sourceTable);
    }
  }

  const derivedPattern =
    /\b(FROM|JOIN)\s*\(/gi;

  for (const match of normalized.matchAll(derivedPattern)) {
    const openIndex = (match.index ?? 0) + match[0].lastIndexOf("(");
    const closeIndex = findMatchingParen(normalized, openIndex);

    if (closeIndex === -1) {
      continue;
    }

    let aliasIndex = skipWhitespace(normalized, closeIndex + 1);

    if (matchesKeywordAt(normalized, aliasIndex, "AS")) {
      aliasIndex = skipWhitespace(normalized, aliasIndex + "AS".length);
    }

    const alias = readIdentifier(normalized, aliasIndex);

    if (!alias || SQL_KEYWORDS.has(alias.value.toUpperCase())) {
      continue;
    }

    const body = normalized.slice(openIndex + 1, closeIndex);
    const sourceTable = findFirstSourceTable(
      body,
      cteMetadata.names,
      cteMetadata.sourceMap,
    );

    if (sourceTable) {
      aliasMap.set(alias.value.toUpperCase(), sourceTable);
    }
  }

  return aliasMap;
};

const buildAliasMap = (
  tables: SqlTable[],
  virtualAliasMap = new Map<string, string>(),
) => {
  const aliasMap = new Map<string, string>();

  tables.forEach((table) => {
    aliasMap.set(table.tableName.toUpperCase(), table.tableName);
    aliasMap.set(table.rawName.toUpperCase(), table.tableName);
    aliasMap.set(simpleTableName(table.tableName).toUpperCase(), table.tableName);

    if (table.schemaName) {
      aliasMap.set(`${table.schemaName}.${table.tableName}`.toUpperCase(), table.tableName);
    }

    if (table.alias) {
      aliasMap.set(table.alias.toUpperCase(), table.tableName);
    }
  });

  virtualAliasMap.forEach((tableName, alias) => {
    aliasMap.set(alias.toUpperCase(), tableName);
  });

  return aliasMap;
};

const resolveColumnRef = (
  qualifier: string,
  columnName: string,
  aliasMap: Map<string, string>,
) => {
  const cleanedQualifier = cleanIdentifier(qualifier);
  const cleanedColumnName = cleanIdentifier(columnName);
  const tableName = aliasMap.get(cleanedQualifier.toUpperCase()) ?? cleanedQualifier;
  return `${simpleTableName(tableName)}.${cleanedColumnName}`;
};

const normalizeJoinType = (joinType: string) =>
  joinType.replace(/\s+/g, " ").trim().toUpperCase();

const buildJoinExplanation = (
  joinType: string | undefined,
  rightTable: string | undefined,
  left: string,
  right: string,
) => {
  const rightTableName = rightTable ? simpleTableName(rightTable) : "상대 테이블";
  const baseText = `${left}와 ${right} 기준으로 ${rightTableName} 데이터를 확장합니다.`;

  if (joinType?.includes("LEFT")) {
    return `${baseText} LEFT JOIN이므로 매칭 데이터가 없어도 기준 데이터는 유지됩니다.`;
  }

  if (joinType?.includes("RIGHT")) {
    return `${baseText} RIGHT JOIN이므로 오른쪽 테이블 기준 데이터가 유지됩니다.`;
  }

  if (joinType?.includes("FULL")) {
    return `${baseText} FULL JOIN이므로 양쪽 누락 데이터를 모두 보존할 수 있습니다.`;
  }

  if (joinType === "WHERE") {
    return `${baseText} 명시적 JOIN은 아니지만 관계 조건으로 사용된 것으로 추정됩니다.`;
  }

  return `${baseText} INNER JOIN 성격으로 양쪽에 매칭되는 데이터만 결과에 포함됩니다.`;
};

const extractJoinRelations = (
  sql: string,
  aliasMap: Map<string, string>,
  whereConditions: string[] = [],
): JoinRelation[] => {
  const normalized = compactSql(sql);
  const joinPattern = new RegExp(
    `\\b(LEFT\\s+OUTER\\s+JOIN|RIGHT\\s+OUTER\\s+JOIN|FULL\\s+OUTER\\s+JOIN|INNER\\s+JOIN|LEFT\\s+JOIN|RIGHT\\s+JOIN|FULL\\s+JOIN|CROSS\\s+JOIN|JOIN)\\s+(${SQL_IDENTIFIER_PATTERN})(?:\\s+(?:AS\\s+)?(${SQL_IDENTIFIER_COMPONENT_PATTERN}))?\\s+ON\\s+([\\s\\S]*?)(?=${JOIN_BOUNDARY}|$)`,
    "gi",
  );
  const relationPattern = new RegExp(
    `(${SQL_IDENTIFIER_COMPONENT_PATTERN})\\s*\\.\\s*(${SQL_IDENTIFIER_COMPONENT_PATTERN})\\s*(?:\\(\\+\\))?\\s*=\\s*(${SQL_IDENTIFIER_COMPONENT_PATTERN})\\s*\\.\\s*(${SQL_IDENTIFIER_COMPONENT_PATTERN})\\s*(?:\\(\\+\\))?`,
    "gi",
  );
  const relations: JoinRelation[] = [];
  const seen = new Set<string>();

  const addRelationsFromClause = (
    clause: string,
    joinType?: string,
    rightTable?: string,
  ) => {
    for (const relationMatch of clause.matchAll(relationPattern)) {
      const [, leftQualifier, leftColumn, rightQualifier, rightColumn] =
        relationMatch;
      const left = resolveColumnRef(leftQualifier, leftColumn, aliasMap);
      const right = resolveColumnRef(rightQualifier, rightColumn, aliasMap);
      const sortedKey = [left.toUpperCase(), right.toUpperCase()].sort().join("=");

      if (seen.has(sortedKey)) {
        continue;
      }

      relations.push({
        explanation: buildJoinExplanation(joinType, rightTable, left, right),
        left,
        joinType,
        right,
        rightTable,
        raw: relationMatch[0],
      });
      seen.add(sortedKey);
    }
  };

  for (const joinMatch of normalized.matchAll(joinPattern)) {
    const joinType = normalizeJoinType(joinMatch[1] ?? "JOIN");
    const rightTable = cleanIdentifier(joinMatch[2] ?? "");
    const onClause = joinMatch[4] ?? "";

    addRelationsFromClause(onClause, joinType, rightTable);
  }

  whereConditions.forEach((condition) =>
    addRelationsFromClause(condition, "WHERE", undefined),
  );

  return relations;
};

type InternalSubqueryAnalysis = SubqueryAnalysis & {
  endIndex: number;
  startIndex: number;
};

const describeSubquery = (type: SubqueryAnalysis["type"]) => {
  if (type === "exists") {
    return "WHERE EXISTS 조건에 서브쿼리가 포함되어 존재 여부를 확인합니다.";
  }

  if (type === "in") {
    return "IN 조건에 SELECT 서브쿼리가 포함되어 후보 값 목록을 만듭니다.";
  }

  if (type === "derived_table") {
    return "FROM/JOIN 절에 인라인 뷰 형태의 서브쿼리가 포함되어 중간 결과를 테이블처럼 사용합니다.";
  }

  if (type === "nested") {
    return "중첩 서브쿼리가 포함되어 내부 SELECT 결과를 바깥 SQL에서 사용합니다.";
  }

  return "SELECT 절 또는 조건식에 스칼라 서브쿼리가 포함되어 파생 지표를 만듭니다.";
};

const classifySubquery = (
  normalizedSql: string,
  startIndex: number,
  body: string,
): SubqueryAnalysis["type"] => {
  const before = normalizedSql.slice(Math.max(0, startIndex - 80), startIndex);

  if (/\bEXISTS\s*$/i.test(before)) {
    return "exists";
  }

  if (/\bIN\s*$/i.test(before)) {
    return "in";
  }

  if (/\b(FROM|JOIN)\s*$/i.test(before)) {
    return "derived_table";
  }

  if (/\(\s*SELECT\b/i.test(body)) {
    return "nested";
  }

  return "scalar";
};

const extractTableNamesFromSql = (sql: string, cteMetadata: CteMetadata) =>
  unique(
    Array.from(compactSql(sql).matchAll(tableRefPattern()))
      .map((match) => parseTableIdentifier(match[2] ?? "").tableName)
      .filter((tableName) => tableName && !cteMetadata.names.has(tableName.toUpperCase())),
  );

const extractSubqueries = (
  sql: string,
  cteMetadata: CteMetadata,
): InternalSubqueryAnalysis[] => {
  const normalized = compactSql(sql);
  const subqueries: InternalSubqueryAnalysis[] = [];

  for (let index = 0; index < normalized.length; index += 1) {
    if (normalized[index] !== "(") {
      continue;
    }

    const endIndex = findMatchingParen(normalized, index);

    if (endIndex === -1) {
      continue;
    }

    const body = trimSqlText(normalized.slice(index + 1, endIndex));

    if (!/^\s*SELECT\b/i.test(body)) {
      continue;
    }

    const type = classifySubquery(normalized, index, body);

    subqueries.push({
      description: describeSubquery(type),
      endIndex,
      sql: body,
      stage: "전체 SQL",
      startIndex: index,
      tables: extractTableNamesFromSql(body, cteMetadata),
      type,
    });

    index = endIndex;
  }

  return subqueries;
};

const describeSetOperation = (operator: SetOperationAnalysis["operator"]) => {
  if (operator === "UNION ALL") {
    return "여러 SELECT 결과를 중복 제거 없이 합칩니다.";
  }

  if (operator === "UNION") {
    return "여러 SELECT 결과를 합치며 중복 제거가 발생할 수 있습니다.";
  }

  if (operator === "EXCEPT") {
    return "앞 SELECT 결과에서 뒤 SELECT 결과와 겹치는 행을 제외합니다.";
  }

  return "여러 SELECT 결과의 교집합을 구합니다.";
};

const extractSetOperations = (sql: string): SetOperationAnalysis[] => {
  const normalized = compactSql(sql);
  const operations: SetOperationAnalysis[] = [];
  let startIndex = 0;

  while (startIndex < normalized.length) {
    const match = findTopLevelKeyword(
      normalized,
      ["UNION ALL", "UNION", "EXCEPT", "INTERSECT"],
      startIndex,
    );

    if (!match) {
      break;
    }

    const operator = match.keyword.toUpperCase() as SetOperationAnalysis["operator"];

    operations.push({
      description: describeSetOperation(operator),
      operator,
    });

    startIndex = match.index + match.keyword.length;
  }

  return operations;
};

const splitTopLevelAnd = (clause: string) => {
  const parts: string[] = [];
  let current = "";
  let quote: "'" | "\"" | null = null;
  let depth = 0;
  let index = 0;
  let pendingBetween = false;

  while (index < clause.length) {
    const char = clause[index];
    const next = clause.slice(index);

    if (quote) {
      current += char;

      if (char === quote) {
        const followingChar = clause[index + 1];

        if (followingChar === quote) {
          current += followingChar;
          index += 2;
          continue;
        }

        quote = null;
      }

      index += 1;
      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      current += char;
      index += 1;
      continue;
    }

    if (char === "(") {
      depth += 1;
      current += char;
      index += 1;
      continue;
    }

    if (char === ")") {
      depth = Math.max(0, depth - 1);
      current += char;
      index += 1;
      continue;
    }

    if (
      depth === 0 &&
      /^BETWEEN\b/i.test(next) &&
      (index === 0 || !/[A-Za-z0-9_$#]/.test(clause[index - 1] ?? ""))
    ) {
      const betweenText = next.match(/^BETWEEN\b/i)?.[0] ?? "";
      pendingBetween = true;
      current += betweenText;
      index += betweenText.length;
      continue;
    }

    if (depth === 0 && /^\s+AND\s+/i.test(next)) {
      const andText = next.match(/^\s+AND\s+/i)?.[0] ?? "";

      if (pendingBetween) {
        pendingBetween = false;
        current += andText;
        index += andText.length;
        continue;
      }

      const trimmed = trimSqlText(current);

      if (trimmed) {
        parts.push(trimmed);
      }

      current = "";
      index += andText.length;
      continue;
    }

    current += char;
    index += 1;
  }

  const trimmed = trimSqlText(current);

  if (trimmed) {
    parts.push(trimmed);
  }

  return parts;
};

const extractWhereConditions = (sql: string) => {
  const normalized = compactSql(sql);
  const whereMatch = findTopLevelKeyword(normalized, ["WHERE"]);

  if (!whereMatch) {
    return [];
  }

  const clauseStartIndex = whereMatch.index + whereMatch.keyword.length;
  const clauseEndMatch = findTopLevelKeyword(
    normalized,
    TOP_LEVEL_BOUNDARY_KEYWORDS,
    clauseStartIndex,
  );
  const clauseEndIndex = clauseEndMatch?.index ?? normalized.length;
  const clause = trimSqlText(normalized.slice(clauseStartIndex, clauseEndIndex));

  return splitTopLevelAnd(clause);
};

const getMainSql = (sql: string) => {
  const normalized = compactSql(sql);
  const definitions = extractCteDefinitions(normalized);

  if (definitions.length === 0) {
    return normalized;
  }

  return trimSqlText(normalized.slice(definitions[definitions.length - 1].endIndex));
};

const getTopLevelClause = (
  sql: string,
  keyword: string,
  boundaries = TOP_LEVEL_BOUNDARY_KEYWORDS,
) => {
  const normalized = compactSql(sql);
  const match = findTopLevelKeyword(normalized, [keyword]);

  if (!match) {
    return "";
  }

  const startIndex = match.index + match.keyword.length;
  const endMatch = findTopLevelKeyword(normalized, boundaries, startIndex);
  return trimSqlText(normalized.slice(startIndex, endMatch?.index ?? normalized.length));
};

const splitTopLevelComma = (text: string) => {
  const parts: string[] = [];
  let current = "";
  let quote: "'" | "\"" | null = null;
  let depth = 0;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (quote) {
      current += char;

      if (char === quote) {
        const followingChar = text[index + 1];

        if (followingChar === quote) {
          current += followingChar;
          index += 1;
          continue;
        }

        quote = null;
      }

      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      current += char;
      continue;
    }

    if (char === "(") {
      depth += 1;
      current += char;
      continue;
    }

    if (char === ")") {
      depth = Math.max(0, depth - 1);
      current += char;
      continue;
    }

    if (char === "," && depth === 0) {
      const trimmed = trimSqlText(current);

      if (trimmed) {
        parts.push(trimmed);
      }

      current = "";
      continue;
    }

    current += char;
  }

  const trimmed = trimSqlText(current);

  if (trimmed) {
    parts.push(trimmed);
  }

  return parts;
};

const extractSelectItems = (sql: string) => {
  const selectClause = getTopLevelClause(sql, "SELECT", ["FROM"]);
  return selectClause ? splitTopLevelComma(selectClause) : [];
};

const extractAlias = (expression: string) => {
  const asMatch = expression.match(/\s+AS\s+([A-Za-z0-9_$#]+)\s*$/i);

  if (asMatch) {
    return asMatch[1];
  }

  const trailingAliasMatch = expression.match(/\s+([A-Za-z0-9_$#]+)\s*$/);

  if (!trailingAliasMatch) {
    return undefined;
  }

  const alias = trailingAliasMatch[1];

  return SQL_KEYWORDS.has(alias.toUpperCase()) ? undefined : alias;
};

const describeFilter = (condition: string, stage: string) => {
  const upperCondition = condition.toUpperCase();
  const stagePrefix = stage === "최종 결과" ? "최종 결과 단계" : `${stage} 단계`;

  if (/12\s+MONTH/.test(upperCondition) || /INTERVAL\s+'12 MONTHS'/.test(upperCondition)) {
    return `${stagePrefix}: 최근 12개월 데이터만 포함합니다.`;
  }

  if (/\bSTATUS\b[\s\S]*\bIN\b/i.test(condition)) {
    return `${stagePrefix}: 주문 상태 조건으로 PAID, SHIPPED, COMPLETED 같은 유효 주문만 포함합니다.`;
  }

  if (/MONTHLY_SALES\s*>=\s*100000/i.test(condition)) {
    return `${stagePrefix}: 월 매출이 100000 이상인 고객만 최종 결과에 포함합니다.`;
  }

  if (/USE_YN\s*=\s*'Y'/i.test(condition)) {
    return `${stagePrefix}: 현재 사용 중인 데이터만 포함합니다.`;
  }

  if (/\bDEL_YN\b|\bDELETE_YN\b/i.test(condition)) {
    return `${stagePrefix}: 삭제되지 않은 데이터만 포함합니다.`;
  }

  return `${stagePrefix}: ${condition} 조건을 적용합니다.`;
};

const buildStageFilters = (stage: string, sql: string): StageFilter[] =>
  extractWhereConditions(sql).map((condition) => ({
    condition,
    description: describeFilter(condition, stage),
    stage,
  }));

const extractHavingConditions = (sql: string) => {
  const havingClause = getTopLevelClause(sql, "HAVING", [
    "ORDER BY",
    "LIMIT",
    "OFFSET",
    "FETCH",
    "UNION",
    "INTERSECT",
    "EXCEPT",
  ]);

  return havingClause ? splitTopLevelAnd(havingClause) : [];
};

const describeHavingFilter = (condition: string, stage: string) => {
  const stagePrefix = stage === "최종 결과" ? "최종 결과 단계" : `${stage} 단계`;

  if (/SUM\s*\([^)]*TOTAL_AMOUNT[^)]*\)\s*>=\s*1000000/i.test(condition)) {
    return `${stagePrefix}: GROUP BY 이후 집계 결과 중 고객별 총 매출이 1,000,000 이상인 그룹만 포함합니다.`;
  }

  if (/SUM\s*\(/i.test(condition)) {
    return `${stagePrefix}: SUM 집계 결과 조건을 만족하는 그룹만 포함합니다.`;
  }

  if (/COUNT\s*\(/i.test(condition)) {
    return `${stagePrefix}: COUNT 집계 결과 조건을 만족하는 그룹만 포함합니다.`;
  }

  return `${stagePrefix}: GROUP BY 이후 집계 결과에 ${condition} 조건을 적용합니다.`;
};

const buildStageHavingFilters = (stage: string, sql: string): StageFilter[] =>
  extractHavingConditions(sql).map((condition) => ({
    condition,
    description: describeHavingFilter(condition, stage),
    stage,
  }));

const extractGroupByColumns = (sql: string) => {
  const groupByClause = getTopLevelClause(sql, "GROUP BY", [
    "HAVING",
    "ORDER BY",
    "LIMIT",
    "OFFSET",
    "FETCH",
    "UNION",
    "INTERSECT",
    "EXCEPT",
  ]);
  return groupByClause ? splitTopLevelComma(groupByClause) : [];
};

const describeAggregation = (
  functionName: string,
  argument: string,
  alias: string | undefined,
) => {
  const upperAlias = alias?.toUpperCase() ?? "";
  const upperArgument = argument.toUpperCase();

  if (upperAlias.includes("ORDER_COUNT") || upperArgument.includes("DISTINCT")) {
    return `${alias ?? functionName}: 고객별/월별 주문 수를 집계합니다.`;
  }

  if (upperAlias.includes("MONTHLY_SALES") || upperArgument.includes("TOTAL_AMOUNT")) {
    return `${alias ?? functionName}: 고객별 월 매출을 집계합니다.`;
  }

  if (upperAlias.includes("QUANTITY")) {
    return `${alias ?? functionName}: 주문 상품 수량을 집계합니다.`;
  }

  if (upperAlias.includes("DISCOUNT")) {
    return `${alias ?? functionName}: 할인 금액을 집계합니다.`;
  }

  if (upperAlias.includes("GROSS") || /\*\s*.*UNIT_PRICE/i.test(argument)) {
    return `${alias ?? functionName}: 상품 수량과 단가 기반 총액을 집계합니다.`;
  }

  return `${alias ?? functionName}: ${functionName}(${argument}) 집계 지표입니다.`;
};

const extractAggregations = (stage: string, sql: string): AggregationAnalysis[] =>
  extractSelectItems(sql).flatMap((item) => {
    if (/\bOVER\s*\(/i.test(item)) {
      return [];
    }

    const match = item.match(/\b(COUNT|SUM|AVG|MIN|MAX)\s*\(([\s\S]+)\)/i);

    if (!match) {
      return [];
    }

    const functionName = match[1].toUpperCase();
    const argument = trimSqlText(match[2]);
    const alias = extractAlias(item);

    return [
      {
        alias,
        description: describeAggregation(functionName, argument, alias),
        expression: trimSqlText(match[0]),
        functionName,
        stage,
      },
    ];
  });

const extractWindowPart = (overClause: string, keyword: string, boundaries: string[]) => {
  const match = findTopLevelKeyword(overClause, [keyword]);

  if (!match) {
    return undefined;
  }

  const startIndex = match.index + match.keyword.length;
  const endMatch = findTopLevelKeyword(overClause, boundaries, startIndex);
  return trimSqlText(overClause.slice(startIndex, endMatch?.index ?? overClause.length));
};

const describeWindowFunction = (
  functionName: string,
  expression: string,
  alias: string | undefined,
  rows: string | undefined,
  orderBy: string | undefined,
) => {
  const upperAlias = alias?.toUpperCase() ?? "";
  const upperRows = rows?.toUpperCase() ?? "";
  const upperOrderBy = orderBy?.toUpperCase() ?? "";

  if (functionName === "SUM" && (upperAlias.includes("CUMULATIVE") || upperRows.includes("UNBOUNDED PRECEDING"))) {
    return `${alias ?? expression}: 고객별 누적 매출을 계산합니다.`;
  }

  if (functionName === "AVG" && (upperAlias.includes("MOVING") || upperRows.includes("2 PRECEDING"))) {
    const monthInterpretation =
      /\bMONTH\b|_MONTH\b|MONTH_|YYYYMM|YM\b|DATE_TRUNC\s*\(\s*'MONTH'/i.test(upperOrderBy)
        ? " ORDER BY 컬럼이 월 단위 컬럼이라 월별 데이터 기준 최근 3개월 이동 평균으로 해석 가능합니다."
        : " 달력 기준 정확한 3개월 범위라고 단정하지는 않습니다.";

    return `${alias ?? expression}: 현재 행 포함 최근 3개 행 기준 평균(이동 평균)을 계산합니다.${monthInterpretation}`;
  }

  if (functionName === "LAG" || upperAlias.includes("PREV_MONTH")) {
    return `${alias ?? expression}: 전월 매출을 가져옵니다.`;
  }

  if (functionName.includes("RANK") || upperAlias.includes("RANK")) {
    return `${alias ?? expression}: 월별 매출 순위를 계산합니다.`;
  }

  return `${alias ?? expression}: OVER 절 기반 윈도우 함수입니다.`;
};

const extractWindowFunctions = (stage: string, sql: string): WindowFunctionAnalysis[] =>
  extractSelectItems(sql).flatMap((item) => {
    const match = item.match(
      /\b(SUM|AVG|COUNT|MIN|MAX|LAG|LEAD|RANK|DENSE_RANK|ROW_NUMBER)\s*\(([\s\S]*?)\)\s+OVER\s*\(([\s\S]+)\)/i,
    );

    if (!match) {
      return [];
    }

    const functionName = match[1].toUpperCase();
    const expression = trimSqlText(match[2]);
    const overClause = trimSqlText(match[3]);
    const alias = extractAlias(item);
    const partitionBy = extractWindowPart(overClause, "PARTITION BY", [
      "ORDER BY",
      "ROWS BETWEEN",
    ]);
    const orderBy = extractWindowPart(overClause, "ORDER BY", ["ROWS BETWEEN"]);
    const rows = extractWindowPart(overClause, "ROWS BETWEEN", []);

    return [
      {
        alias,
        description: describeWindowFunction(functionName, expression, alias, rows, orderBy),
        expression,
        functionName,
        orderBy,
        partitionBy,
        rows,
        stage,
      },
    ];
  });

const extractCaseExpressions = (stage: string, sql: string): CaseExpressionAnalysis[] =>
  extractSelectItems(sql).flatMap((item) => {
    if (!/^CASE\b/i.test(item)) {
      return [];
    }

    const alias = extractAlias(item);
    const bodyMatch = item.match(/^CASE\s+([\s\S]+?)\s+END/i);
    const body = bodyMatch?.[1] ?? item;
    const rules = Array.from(
      body.matchAll(/WHEN\s+([\s\S]+?)\s+THEN\s+((?:'[^']*')|NULL|[A-Za-z0-9_.$()+\-*/ ]+?)(?=\s+WHEN|\s+ELSE|\s*$)/gi),
    ).map((match) => `${trimSqlText(match[1])}: ${trimSqlText(match[2])}`);
    const elseMatch = body.match(/\bELSE\s+((?:'[^']*')|NULL|[A-Za-z0-9_.$()+\-*/ ]+)/i);

    if (elseMatch) {
      rules.push(`그 외: ${trimSqlText(elseMatch[1])}`);
    }

    const description = alias?.toUpperCase().includes("SEGMENT")
      ? `${alias}: 고객 세그먼트 분류 기준입니다.`
      : alias?.toUpperCase().includes("GROWTH")
        ? `${alias}: 전월 매출 대비 증감률을 계산하는 파생 컬럼입니다.`
        : `${alias ?? "CASE"}: CASE WHEN 조건별 파생 컬럼입니다.`;

    return [{ alias, description, rules, stage }];
  });

const describeDerivedColumn = (alias: string, expression: string) => {
  const upperAlias = alias.toUpperCase();
  const upperExpression = expression.toUpperCase();

  if (upperAlias.includes("ORDER_MONTH") || upperExpression.includes("DATE_TRUNC")) {
    return `${alias}: 주문일을 월 단위로 변환한 분석 기준 컬럼입니다.`;
  }

  if (upperAlias.includes("REGION")) {
    return `${alias}: 지역 정보로 추정되며, 누락 시 UNKNOWN으로 대체될 수 있습니다.`;
  }

  return `${alias}: ${expression} 기반 파생 컬럼입니다.`;
};

const extractDerivedColumns = (stage: string, sql: string): DerivedColumnAnalysis[] =>
  extractSelectItems(sql).flatMap((item) => {
    const alias = extractAlias(item);

    if (/^\(\s*SELECT\b/i.test(item) && alias) {
      return [
        {
          alias,
          description: `${alias}: SELECT 절의 스칼라 서브쿼리 결과를 사용하는 파생 지표입니다.`,
          expression: trimSqlText(item.replace(/\s+AS\s+[A-Za-z0-9_$#]+\s*$/i, "")),
          stage,
        },
      ];
    }

    if (/^CASE\b/i.test(item) || /\bOVER\s*\(/i.test(item) || /\b(COUNT|SUM|AVG|MIN|MAX)\s*\(/i.test(item)) {
      return [];
    }

    if (!alias || !/\s+AS\s+/i.test(item)) {
      return [];
    }

    const expression = trimSqlText(item.replace(/\s+AS\s+[A-Za-z0-9_$#]+\s*$/i, ""));

    return [
      {
        alias,
        description: describeDerivedColumn(alias, expression),
        expression,
        stage,
      },
    ];
  });

const extractCteDependencies = (body: string, cteNames: Set<string>) =>
  unique(
    Array.from(body.matchAll(tableRefPattern()))
      .map((match) => cleanIdentifier(match[2] ?? ""))
      .filter((tableName) => cteNames.has(tableName.toUpperCase())),
  );

const describeCteRole = (
  name: string,
  body: string,
  filters: StageFilter[],
  groupBy: string[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
) => {
  const lowerName = name.toLowerCase();
  const upperBody = body.toUpperCase();

  if (lowerName.includes("recent") && lowerName.includes("order")) {
    return "최근 12개월 주문과 고객/지역 정보를 결합하는 준비 단계입니다.";
  }

  if (lowerName.includes("order_items") || lowerName.includes("item")) {
    return "주문 상품 단위에서 수량, 총액, 할인금액을 집계하는 단계입니다.";
  }

  if (lowerName.includes("monthly") || lowerName.includes("sales")) {
    return "고객별 월 매출과 주문 수를 GROUP BY로 집계하는 단계입니다.";
  }

  if (lowerName.includes("rank") || windowFunctions.length > 0) {
    return "윈도우 함수로 누적 매출, 이동 평균, 전월 매출, 월별 매출 순위를 계산하는 단계입니다.";
  }

  if (groupBy.length > 0 || aggregations.length > 0) {
    return "GROUP BY와 집계 함수를 사용해 분석 지표를 만드는 단계입니다.";
  }

  if (filters.length > 0 && upperBody.includes("JOIN")) {
    return "필터링된 기준 데이터를 다른 업무 데이터와 결합하는 단계입니다.";
  }

  return "다음 단계에서 재사용할 중간 결과를 만드는 CTE 단계입니다.";
};

const buildCteAnalyses = (sql: string): CteAnalysis[] => {
  const definitions = extractCteDefinitions(sql);
  const cteNames = new Set(definitions.map((definition) => definition.name.toUpperCase()));

  return definitions.map((definition) => {
    const filters = buildStageFilters(definition.name, definition.body);
    const groupBy = extractGroupByColumns(definition.body);
    const aggregations = extractAggregations(definition.name, definition.body);
    const windowFunctions = extractWindowFunctions(definition.name, definition.body);

    return {
      dependencies: extractCteDependencies(definition.body, cteNames),
      filters,
      groupBy,
      name: definition.name,
      role: describeCteRole(
        definition.name,
        definition.body,
        filters,
        groupBy,
        aggregations,
        windowFunctions,
      ),
    };
  });
};

const buildGroupByAnalyses = (stages: Array<{ name: string; sql: string }>) =>
  stages.flatMap(({ name, sql }) => {
    const columns = extractGroupByColumns(sql);

    if (columns.length === 0) {
      return [];
    }

    return [
      {
        columns,
        description: `${name} 단계에서 GROUP BY 기준으로 ${columns.join(", ")} 단위 집계를 수행합니다.`,
        stage: name,
      },
    ];
  });

const hasUseYnActiveCondition = (whereConditions: string[]) =>
  /\bUSE_YN\b\s*=\s*'Y'/i.test(whereConditions.join(" "));

const hasDeleteYnActiveCondition = (whereConditions: string[]) =>
  /\b(DEL_YN|DELETE_YN)\b\s*=\s*'N'/i.test(whereConditions.join(" "));

const statusConditionPhrase = (whereConditions: string[]) => {
  const whereText = whereConditions.join(" ");

  if (/\b(STS_CD|STTS_CD|STATUS_CD)\b\s*=\s*'ACTIVE'/i.test(whereText)) {
    return "활성 상태인";
  }

  return "";
};

const joinKoreanList = (items: string[]) => {
  if (items.length <= 1) {
    return items[0] ?? "";
  }

  return `${items.slice(0, -1).join(", ")} 및 ${items[items.length - 1]}`;
};

const isInsertSelectSql = (sql: string) => {
  const normalized = compactSql(sql);
  return /\bINSERT\s+INTO\b/i.test(normalized) && /\bSELECT\b/i.test(normalized);
};

const extractInsertTarget = (sql: string) => {
  const match = compactSql(sql).match(new RegExp(`\\bINSERT\\s+INTO\\s+(${SQL_IDENTIFIER_PATTERN})`, "i"));
  return match ? simpleTableName(match[1]) : undefined;
};

const isAnalyticsIntent = (businessIntent: BusinessIntent) =>
  [
    "analytics_report",
    "sales_summary",
    "aggregation_report",
    "ranking_analysis",
  ].includes(businessIntent.type);

const hasRankingWindow = (windowFunctions: WindowFunctionAnalysis[]) =>
  windowFunctions.some((windowFunction) =>
    /RANK|ROW_NUMBER/i.test(`${windowFunction.functionName} ${windowFunction.alias ?? ""}`),
  );

const hasSalesSignal = (
  tables: SqlTable[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
  groupBy: GroupByAnalysis[] = [],
) => {
  const text = [
    ...tables.map((table) => `${table.tableName} ${table.entityLabel} ${table.category}`),
    ...groupBy.flatMap((group) => group.columns),
    ...aggregations.map((aggregation) => `${aggregation.alias ?? ""} ${aggregation.expression} ${aggregation.description}`),
    ...windowFunctions.map((windowFunction) => `${windowFunction.alias ?? ""} ${windowFunction.expression} ${windowFunction.description}`),
    ...caseExpressions.map((caseExpression) => `${caseExpression.alias ?? ""} ${caseExpression.description}`),
  ].join(" ");

  return /SALES|SALE|REVENUE|AMOUNT|TOTAL_AMOUNT|매출|판매|금액/i.test(text);
};

const hasCustomerSalesAnalytics = (
  tables: SqlTable[],
  ctes: CteAnalysis[],
  groupBy: GroupByAnalysis[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
) => {
  const hasCustomerSignal =
    tables.some((table) => table.category === "customer") ||
    /CUSTOMER|고객/i.test(
      [
        ...groupBy.flatMap((group) => group.columns),
        ...aggregations.map((aggregation) => `${aggregation.alias ?? ""} ${aggregation.expression}`),
        ...windowFunctions.map((windowFunction) => `${windowFunction.alias ?? ""} ${windowFunction.expression}`),
        ...caseExpressions.map((caseExpression) => `${caseExpression.alias ?? ""} ${caseExpression.description}`),
      ].join(" "),
    );
  const text = [
    ...aggregations.map((aggregation) => `${aggregation.alias ?? ""} ${aggregation.description}`),
    ...windowFunctions.map((windowFunction) => `${windowFunction.alias ?? ""} ${windowFunction.description}`),
    ...caseExpressions.map((caseExpression) => `${caseExpression.alias ?? ""} ${caseExpression.description}`),
  ].join(" ");

  return (
    hasCustomerSignal &&
    /MONTHLY_SALES|월 매출|매출/i.test(text) &&
    (ctes.length >= 2 || windowFunctions.length > 0 || caseExpressions.length > 0)
  );
};

const buildBusinessIntent = (
  sql: string,
  tables: SqlTable[],
  ctes: CteAnalysis[],
  setOperations: SetOperationAnalysis[],
  groupBy: GroupByAnalysis[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
): BusinessIntent => {
  const reasons: string[] = [];
  const categories = new Set(tables.map((table) => table.category));

  if (groupBy.length > 0) {
    reasons.push("GROUP BY가 있어 상세 목록보다 집계/분석 성격이 강합니다.");
  }

  if (aggregations.length > 0) {
    reasons.push("COUNT, SUM, AVG 같은 집계 지표를 생성합니다.");
  }

  if (windowFunctions.length > 0) {
    reasons.push("윈도우 함수로 누적, 이동 평균, 전월 값, 순위를 계산합니다.");
  }

  if (caseExpressions.some((caseExpression) => caseExpression.alias?.toUpperCase().includes("SEGMENT"))) {
    reasons.push("CASE 문으로 고객 세그먼트를 분류합니다.");
  }

  if (isInsertSelectSql(sql)) {
    return {
      confidence: 0.88,
      reasons: [
        "INSERT INTO ... SELECT 형태로 조회 결과를 대상 테이블에 적재합니다.",
        ...reasons,
      ],
      type: "batch_etl",
    };
  }

  if (setOperations.length > 0) {
    return {
      confidence: 0.72,
      reasons: [
        `${setOperations.map((operation) => operation.operator).join(", ")} 연산으로 여러 SELECT 결과를 결합하거나 비교합니다.`,
        ...reasons,
      ],
      type: "combined_result",
    };
  }

  if (
    hasCustomerSalesAnalytics(
      tables,
      ctes,
      groupBy,
      aggregations,
      windowFunctions,
      caseExpressions,
    )
  ) {
    return {
      confidence: Math.min(0.95, 0.65 + reasons.length * 0.08),
      reasons,
      type: "analytics_report",
    };
  }

  if (hasRankingWindow(windowFunctions) && aggregations.length === 0 && groupBy.length === 0) {
    return {
      confidence: 0.82,
      reasons,
      type: "ranking_analysis",
    };
  }

  if (caseExpressions.length > 0 && aggregations.length === 0 && windowFunctions.length === 0 && groupBy.length === 0) {
    return {
      confidence: 0.78,
      reasons: [
        "CASE WHEN으로 조건별 라벨이나 파생 값을 만듭니다.",
        ...reasons,
      ],
      type: "classification",
    };
  }

  if (aggregations.length > 0 || groupBy.length > 0) {
    const type: BusinessIntentType =
      categories.has("product") || hasSalesSignal(tables, aggregations, windowFunctions, caseExpressions, groupBy)
        ? "sales_summary"
        : "aggregation_report";

    return {
      confidence: Math.min(0.9, 0.62 + reasons.length * 0.08),
      reasons,
      type,
    };
  }

  if (ctes.length > 0) {
    return {
      confidence: 0.72,
      reasons: [
        "CTE를 사용해 중간 결과를 단계적으로 구성합니다.",
        ...reasons,
      ],
      type: "staged_query",
    };
  }

  if (categories.has("order")) {
    return {
      confidence: 0.7,
      reasons: ["집계나 윈도우 함수 없이 주문 조건을 조회합니다."],
      type: "order_list",
    };
  }

  const hasJoinOrFilter = tables.length > 1 || /\bWHERE\b/i.test(compactSql(sql));

  return {
    confidence: hasJoinOrFilter ? 0.62 : 0.55,
    reasons: hasJoinOrFilter ? ["집계나 윈도우 함수 없이 조건에 맞는 목록을 조회합니다."] : reasons,
    type: hasJoinOrFilter ? "list_query" : "lookup",
  };
};

const buildSummary = (
  tables: SqlTable[],
  whereConditions: string[],
  businessIntent: BusinessIntent,
  ctes: CteAnalysis[],
  groupBy: GroupByAnalysis[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
  sql: string,
) => {
  if (tables.length === 0) {
    if (businessIntent.type === "batch_etl" || businessIntent.type === "data_insert") {
      const target = extractInsertTarget(sql);
      return target
        ? `${target} 테이블에 조회 결과를 적재하는 배치성 SQL`
        : "INSERT INTO SELECT로 조회 결과를 적재하는 배치성 SQL";
    }

    return "입력된 SQL에서 조회 대상을 식별하지 못했습니다.";
  }

  if (businessIntent.type === "batch_etl" || businessIntent.type === "data_insert") {
    const target = extractInsertTarget(sql);
    return target
      ? `${target} 테이블에 조회 결과를 적재하는 배치성 SQL`
      : "INSERT INTO SELECT로 조회 결과를 적재하는 배치성 SQL";
  }

  if (
    businessIntent.type === "analytics_report" &&
    hasCustomerSalesAnalytics(
      tables,
      ctes,
      groupBy,
      aggregations,
      windowFunctions,
      caseExpressions,
    )
  ) {
    return "고객별 월 매출 분석, CRM 대시보드, VIP 고객 선별을 위한 리포트 SQL";
  }

  if (businessIntent.type === "sales_summary") {
    return "상품 또는 주문 기준의 매출 집계 SQL";
  }

  if (businessIntent.type === "combined_result" || businessIntent.type === "set_operation") {
    return "여러 SELECT 결과를 합치거나 비교하는 SQL";
  }

  if (businessIntent.type === "aggregation_report") {
    return "GROUP BY와 분석 함수를 사용하는 집계/리포트 SQL";
  }

  if (businessIntent.type === "ranking_analysis") {
    return "윈도우 함수로 순위를 계산하는 분석 SQL";
  }

  if (businessIntent.type === "classification" || businessIntent.type === "derived_column_explanation") {
    return "CASE WHEN 조건으로 상태나 분류 라벨을 만드는 SQL";
  }

  if (businessIntent.type === "staged_query" || businessIntent.type === "data_preparation") {
    return "CTE로 중간 데이터를 단계적으로 준비해 조회하는 SQL";
  }

  const categories = new Set(tables.map((table) => table.category));
  const hasEmployee = categories.has("employee");
  const hasDepartment = categories.has("department");
  const hasActiveCondition = hasUseYnActiveCondition(whereConditions);

  if (hasEmployee && hasDepartment && hasActiveCondition) {
    return "현재 재직 중인 직원과 소속 부서를 조회하는 SQL";
  }

  if (businessIntent.type === "order_list") {
    return "조건에 맞는 주문 목록을 조회하는 SQL";
  }

  const labels = unique(tables.map((table) => table.entityLabel));
  const target = `${joinKoreanList(labels)} 정보`;
  const prefix = hasActiveCondition
    ? hasEmployee
      ? "현재 재직 중인 "
      : "현재 사용 중인 "
    : "";

  return `${prefix}${target}를 조회하는 SQL`;
};

const buildFilterPhrase = (tables: SqlTable[], whereConditions: string[]) => {
  const phrases: string[] = [];
  const primaryLabel = tables[0]?.entityLabel ?? "데이터";

  if (hasUseYnActiveCondition(whereConditions)) {
    phrases.push(primaryLabel === "직원" ? "현재 재직 중인" : "현재 사용 중인");
  }

  if (hasDeleteYnActiveCondition(whereConditions)) {
    phrases.push("삭제되지 않은");
  }

  const statusPhrase = statusConditionPhrase(whereConditions);

  if (statusPhrase) {
    phrases.push(statusPhrase);
  }

  if (phrases.length > 0) {
    return unique(phrases).join(" ");
  }

  return whereConditions.length > 0 ? "조건에 맞는" : "전체";
};

const buildBusinessGuesses = (
  tables: SqlTable[],
  relations: JoinRelation[],
  businessIntent: BusinessIntent,
  ctes: CteAnalysis[] = [],
  groupBy: GroupByAnalysis[] = [],
  aggregations: AggregationAnalysis[] = [],
  windowFunctions: WindowFunctionAnalysis[] = [],
  caseExpressions: CaseExpressionAnalysis[] = [],
) => {
  const categories = new Set(tables.map((table) => table.category));

  if (
    businessIntent.type === "analytics_report" &&
    hasCustomerSalesAnalytics(
      tables,
      ctes,
      groupBy,
      aggregations,
      windowFunctions,
      caseExpressions,
    )
  ) {
    return [
      "고객 매출 분석",
      "CRM 대시보드",
      "VIP 고객 선별",
      "월별 매출 리포트",
      "영업 실적 분석",
      "정산/거래 관리 보조",
    ];
  }

  if (businessIntent.type === "batch_etl" || businessIntent.type === "data_insert") {
    return ["배치 데이터 적재", "리포트 테이블 갱신", "ETL/데이터 마트 생성"];
  }

  if (businessIntent.type === "sales_summary") {
    return ["상품별 매출 집계", "판매 실적 리포트", "정산/거래 관리 보조"];
  }

  if (businessIntent.type === "combined_result" || businessIntent.type === "set_operation") {
    return ["통합 결과 조회", "데이터 비교", "여러 조건 결과 결합"];
  }

  if (businessIntent.type === "aggregation_report" || businessIntent.type === "analytics_report") {
    return ["분석 리포트", "운영 대시보드", "성과 지표 모니터링"];
  }

  if (businessIntent.type === "ranking_analysis") {
    return ["사용자 순위 분석", "랭킹 화면", "성과 순위 리포트"];
  }

  if (businessIntent.type === "classification" || businessIntent.type === "derived_column_explanation") {
    return ["상태 라벨링", "분류 기준 표시", "운영 상태 조회"];
  }

  if (businessIntent.type === "staged_query" || businessIntent.type === "data_preparation") {
    return ["단계적 데이터 준비", "중간 결과 검증", "업무 데이터 조회 전처리"];
  }

  if (businessIntent.type === "order_list") {
    return ["주문 목록 조회", "거래 검색 화면", "주문 상태 확인"];
  }

  if (categories.has("employee") && categories.has("department")) {
    return ["직원 조회 화면", "조직도 조회", "권한 관리"];
  }

  if (categories.has("user") && categories.has("authorization")) {
    return ["사용자 권한 관리", "관리자 화면", "접근 권한 점검"];
  }

  if (categories.has("department") || categories.has("organization")) {
    return ["조직도 조회", "조직 관리", "권한 관리"];
  }

  if (relations.length > 0 && categories.has("code")) {
    return ["기준 정보 조회", "코드명 표시", "관리자 검색 화면"];
  }

  const guesses = unique(
    tables.flatMap((table) => {
      const rule = DOMAIN_RULES.find((domainRule) => domainRule.category === table.category);
      return rule?.businessGuesses ?? [];
    }),
  );

  return guesses.length > 0
    ? guesses.slice(0, 3)
    : ["업무 데이터 조회 화면", "관리자 검색 화면", "배치 대상 확인"];
};

const buildDeveloperExplanation = (
  tables: SqlTable[],
  relations: JoinRelation[],
  whereConditions: string[],
  ctes: CteAnalysis[] = [],
  businessIntent?: BusinessIntent,
  aggregations: AggregationAnalysis[] = [],
  windowFunctions: WindowFunctionAnalysis[] = [],
  caseExpressions: CaseExpressionAnalysis[] = [],
  sql = "",
) => {
  if (businessIntent?.type === "batch_etl" || businessIntent?.type === "data_insert") {
    const target = extractInsertTarget(sql);
    const targetText = target ? `${target} 테이블에 ` : "대상 테이블에 ";

    return `이 SQL은 단순 조회가 아니라 INSERT INTO SELECT 형태로 조회 결과를 ${targetText}적재하는 배치성 SQL입니다. SELECT 절과 WHERE 조건은 적재 대상 데이터를 선별하는 기준입니다.`;
  }

  if (tables.length === 0) {
    return "FROM 또는 JOIN 절에서 테이블을 찾지 못했습니다. SQL 형태를 확인한 뒤 다시 분석해야 합니다.";
  }

  if (businessIntent?.type === "analytics_report") {
    const cteFlow = ctes.length > 0
      ? `${ctes.map((cte) => cte.name).join(" -> ")} 흐름으로 중간 데이터를 단계적으로 만듭니다. `
      : "";
    const aggregationText = aggregations.length > 0
      ? "GROUP BY와 집계 함수로 주문 수, 월 매출, 수량, 할인 금액 같은 지표를 만듭니다. "
      : "";
    const windowText = windowFunctions.length > 0
      ? "윈도우 함수로 누적 매출, 최근 3개월 이동 평균, 전월 매출, 월별 매출 순위를 계산합니다. "
      : "";
    const caseText = caseExpressions.length > 0
      ? "CASE 문으로 증감률 또는 고객 세그먼트 같은 파생 결과를 만듭니다."
      : "";

    return `이 SQL은 단순 목록 조회가 아니라 고객별 월 매출 분석을 위한 리포트 SQL입니다. ${cteFlow}${aggregationText}${windowText}${caseText}`.trim();
  }

  if (businessIntent?.type === "sales_summary") {
    const groupText = aggregations.length > 0
      ? "GROUP BY와 SUM/COUNT 같은 집계 함수로 판매 수량, 매출 합계, 건수 같은 요약 지표를 만듭니다."
      : "GROUP BY 기준으로 데이터를 요약합니다.";

    return `이 SQL은 상세 목록 조회보다 상품 또는 주문 기준 매출 요약에 가깝습니다. ${groupText}`;
  }

  if (businessIntent?.type === "combined_result" || businessIntent?.type === "set_operation") {
    return "이 SQL은 UNION, EXCEPT, INTERSECT 같은 set operation으로 여러 SELECT 결과를 합치거나 비교합니다.";
  }

  if (businessIntent?.type === "aggregation_report") {
    return "이 SQL은 GROUP BY 또는 집계 함수를 사용해 기준별 요약 지표를 만드는 리포트성 SQL입니다.";
  }

  if (businessIntent?.type === "ranking_analysis") {
    return "이 SQL은 윈도우 함수의 RANK 또는 ROW_NUMBER 계열 계산으로 조건에 맞는 데이터의 순위를 산출합니다.";
  }

  if (businessIntent?.type === "classification" || businessIntent?.type === "derived_column_explanation") {
    return "이 SQL은 CASE WHEN 조건으로 원본 상태값이나 수치 조건을 사람이 읽기 쉬운 분류 라벨 또는 파생 컬럼으로 변환합니다.";
  }

  if (businessIntent?.type === "staged_query" || businessIntent?.type === "data_preparation") {
    const cteFlow = ctes.length > 0
      ? `${ctes.map((cte) => cte.name).join(" -> ")} 흐름으로 `
      : "";

    return `이 SQL은 ${cteFlow}중간 결과를 단계적으로 준비한 뒤 최종 SELECT에서 필요한 데이터를 조회합니다. GROUP BY가 없어 집계 SQL로 단정하지 않습니다.`;
  }

  const [baseTable, ...joinedTables] = tables;
  const filterPhrase = buildFilterPhrase(tables, whereConditions);
  const target = `${baseTable.entityLabel} 목록`;
  const joinedDescriptions = unique(
    joinedTables.map((table) => table.description),
  );
  const joinText =
    joinedDescriptions.length > 0
      ? `${joinKoreanList(joinedDescriptions)}를 연결하여 `
      : "";
  const relationText =
    relations.length > 0
      ? " JOIN 조건으로 테이블 간 기준 컬럼을 맞춥니다."
      : "";

  return `이 SQL은 ${baseTable.entityLabel} 테이블을 기준으로 ${joinText}${filterPhrase} ${target}을 조회합니다.${relationText}`;
};

const buildFinalResultDescription = (
  tables: SqlTable[],
  businessIntent: BusinessIntent,
  ctes: CteAnalysis[],
  groupBy: GroupByAnalysis[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
  derivedColumns: DerivedColumnAnalysis[],
) => {
  const resultParts: string[] = [];

  if (businessIntent.type === "batch_etl" || businessIntent.type === "data_insert") {
    return "최종 결과는 SELECT로 선별된 데이터를 INSERT 대상 테이블에 적재하는 입력 데이터로 사용됩니다.";
  }

  if (businessIntent.type === "combined_result" || businessIntent.type === "set_operation") {
    return "최종 결과는 여러 SELECT 결과를 set operation으로 결합하거나 비교한 데이터입니다.";
  }

  if (
    aggregations.length > 0 &&
    hasCustomerSalesAnalytics(
      tables,
      ctes,
      groupBy,
      aggregations,
      windowFunctions,
      caseExpressions,
    )
  ) {
    resultParts.push("주문 수, 고객별 월 매출, 상품 수량, 할인 금액 같은 집계 지표");
  } else if (businessIntent.type === "sales_summary") {
    resultParts.push("GROUP BY 기준별 판매 수량, 매출 합계, 건수 같은 집계 지표");
  } else if (aggregations.length > 0) {
    resultParts.push("GROUP BY 기준별 COUNT, SUM, AVG 같은 집계 지표");
  }

  if (windowFunctions.length > 0) {
    if (businessIntent.type === "ranking_analysis") {
      resultParts.push("윈도우 함수로 계산한 순위 값");
    } else {
      resultParts.push("누적 매출, 최근 3개 행 기준 이동 평균, 전월 매출, 월별 매출 순위");
    }
  }

  if (caseExpressions.some((caseExpression) => caseExpression.alias?.toUpperCase().includes("SEGMENT"))) {
    resultParts.push("TOP_10, HIGH_VALUE, REPEAT_BUYER, NORMAL 고객 세그먼트");
  }

  if (caseExpressions.some((caseExpression) => caseExpression.alias?.toUpperCase().includes("GROWTH"))) {
    resultParts.push("전월 대비 매출 증감률");
  }

  if (derivedColumns.some((column) => column.alias.toUpperCase().includes("REGION"))) {
    resultParts.push("지역 정보");
  }

  if (resultParts.length === 0) {
    return "최종 SELECT에 명시된 컬럼을 조회합니다.";
  }

  return `최종 결과는 ${joinKoreanList(unique(resultParts))}를 포함합니다.`;
};

const buildNotes = (
  tables: SqlTable[],
  businessIntent: BusinessIntent,
  ctes: CteAnalysis[],
  groupBy: GroupByAnalysis[] = [],
  aggregations: AggregationAnalysis[] = [],
  windowFunctions: WindowFunctionAnalysis[] = [],
  caseExpressions: CaseExpressionAnalysis[] = [],
) => {
  const notes: string[] = [];

  tables
    .filter((table) =>
      ["unknown", "region", "code", "mapping", "meta"].includes(table.category),
    )
    .forEach((table) => {
      notes.push(`${table.tableName}의 업무 의미는 테이블명 기준 추정입니다. 실제 코드/ERD 확인이 필요합니다.`);
    });

  if (isAnalyticsIntent(businessIntent)) {
    const signals = [
      groupBy.length > 0 ? "GROUP BY" : "",
      aggregations.length > 0 ? "집계 함수" : "",
      windowFunctions.length > 0 ? "윈도우 함수" : "",
      caseExpressions.length > 0 ? "CASE 문" : "",
    ].filter(Boolean);

    if (signals.length > 0) {
      notes.push(`${joinKoreanList(signals)} 구조 신호를 근거로 단순 목록 조회보다 분석/리포트 성격으로 판단했습니다.`);
    }
  }

  if (ctes.length > 0) {
    notes.push("CTE 이름과 내부 SELECT 구조를 근거로 단계별 역할을 추정했습니다.");
  }

  return unique(notes);
};

const maxParenthesisDepth = (sql: string) => {
  const normalized = compactSql(sql);
  let quote: "'" | "\"" | "`" | "]" | null = null;
  let depth = 0;
  let maxDepth = 0;

  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];
    const nextChar = normalized[index + 1];

    if (quote) {
      if (
        ((quote === "'" || quote === "\"" || quote === "`") && char === quote && nextChar === quote) ||
        (quote === "]" && char === "]" && nextChar === "]")
      ) {
        index += 1;
        continue;
      }

      if (
        (quote === "'" && char === "'") ||
        (quote === "\"" && char === "\"") ||
        (quote === "`" && char === "`") ||
        (quote === "]" && char === "]")
      ) {
        quote = null;
      }

      continue;
    }

    if (char === "'" || char === "\"" || char === "`") {
      quote = char;
      continue;
    }

    if (char === "[") {
      quote = "]";
      continue;
    }

    if (char === "(") {
      depth += 1;
      maxDepth = Math.max(maxDepth, depth);
      continue;
    }

    if (char === ")") {
      depth = Math.max(0, depth - 1);
    }
  }

  return maxDepth;
};

const buildConfidence = (
  sql: string,
  tables: SqlTable[],
  relations: JoinRelation[],
  ctes: CteAnalysis[],
  filters: StageFilter[],
  havingConditions: StageFilter[],
  groupBy: GroupByAnalysis[],
  aggregations: AggregationAnalysis[],
  windowFunctions: WindowFunctionAnalysis[],
  caseExpressions: CaseExpressionAnalysis[],
  subqueries: SubqueryAnalysis[],
  setOperations: SetOperationAnalysis[],
): AnalysisConfidence => {
  const reasons: string[] = [];
  let score = 0.45;

  if (/\bSELECT\b/i.test(compactSql(sql))) {
    score += 0.08;
    reasons.push("SELECT 구조가 확인됨");
  }

  if (tables.length > 0) {
    score += 0.12;
    reasons.push(`${tables.length}개 테이블 후보가 추출됨`);
  }

  if (relations.length > 0) {
    score += 0.08;
    reasons.push("JOIN 또는 관계 조건이 확인됨");
  }

  if (filters.length > 0) {
    score += 0.04;
    reasons.push("WHERE 조건이 추출됨");
  }

  if (havingConditions.length > 0) {
    score += 0.04;
    reasons.push("HAVING 집계 필터가 추출됨");
  }

  if (ctes.length > 0) {
    score += 0.06;
    reasons.push("CTE 구조가 확인됨");
  }

  if (groupBy.length > 0) {
    score += 0.05;
    reasons.push("GROUP BY 기준이 확인됨");
  }

  if (aggregations.length > 0) {
    score += 0.05;
    reasons.push("집계 함수가 확인됨");
  }

  if (windowFunctions.length > 0) {
    score += 0.05;
    reasons.push("OVER 기반 윈도우 함수가 확인됨");
  }

  if (caseExpressions.length > 0) {
    score += 0.04;
    reasons.push("CASE 분류가 확인됨");
  }

  if (subqueries.length > 0) {
    score -= 0.12;
    reasons.push("서브쿼리가 있어 정규식 분석 신뢰도를 중간 수준으로 조정");
  }

  if (setOperations.length > 0) {
    score -= 0.08;
    reasons.push("UNION/EXCEPT/INTERSECT 계열 set operation이 포함됨");
  }

  if (maxParenthesisDepth(sql) >= 4) {
    score -= 0.08;
    reasons.push("중첩 괄호가 깊어 일부 절 추출이 제한될 수 있음");
  }

  if (tables.length === 0) {
    score -= 0.2;
    reasons.push("FROM/JOIN 테이블 후보가 충분히 추출되지 않음");
  }

  const normalizedScore = Math.max(0.15, Math.min(0.95, Number(score.toFixed(2))));
  const level: AnalysisConfidence["level"] =
    normalizedScore >= 0.75 ? "high" : normalizedScore >= 0.45 ? "medium" : "low";

  return {
    level,
    reasons: unique(reasons),
    score: normalizedScore,
  };
};

const buildWarnings = (
  tables: SqlTable[],
  relations: JoinRelation[],
  confidence: AnalysisConfidence,
  subqueries: SubqueryAnalysis[],
  setOperations: SetOperationAnalysis[],
) => {
  const warnings = [
    "정규식 기반 분석이므로 중첩 서브쿼리나 DBMS 특화 문법은 일부 누락될 수 있습니다.",
  ];

  if (subqueries.length > 0) {
    warnings.push("서브쿼리는 탐지 중심으로 분석했으며 내부 조건의 완전한 AST 해석은 제한될 수 있습니다.");
  }

  if (setOperations.length > 0) {
    warnings.push("UNION/EXCEPT/INTERSECT 계열 SQL은 각 SELECT 블록별 상세 의미가 일부 단순화될 수 있습니다.");
  }

  if (relations.some((relation) => relation.joinType === "WHERE")) {
    warnings.push("WHERE 절의 테이블 간 비교 조건은 명시적 JOIN이 아니라 관계 조건으로 사용된 것으로 추정됩니다.");
  }

  if (
    tables.some((table) =>
      ["unknown", "region", "code", "mapping", "meta"].includes(table.category),
    )
  ) {
    warnings.push("테이블명만으로 업무 의미를 단정하지 않고 추정했습니다.");
  }

  if (confidence.level === "low") {
    warnings.push("주요 SQL 절 추출이 충분하지 않아 분석 결과를 수동으로 확인해야 합니다.");
  }

  return unique(warnings);
};

export function analyzeSql(sql: string): SqlExplanation {
  const cteMetadata = extractCteMetadata(sql);
  const subqueries = extractSubqueries(sql, cteMetadata);
  const setOperations = extractSetOperations(sql);
  const tables = extractTableRefs(sql, cteMetadata, subqueries);
  const virtualAliasMap = extractVirtualAliasMap(sql, cteMetadata);
  const aliasMap = buildAliasMap(tables, virtualAliasMap);
  const mainSql = getMainSql(sql);
  const whereConditions = extractWhereConditions(mainSql);
  const relations = extractJoinRelations(sql, aliasMap, whereConditions);
  const cteDefinitions = extractCteDefinitions(sql);
  const ctes = buildCteAnalyses(sql);
  const stages = [
    ...cteDefinitions.map((definition) => ({
      name: definition.name,
      sql: definition.body,
    })),
    { name: "최종 결과", sql: mainSql },
  ];
  const filters = stages.flatMap(({ name, sql: stageSql }) =>
    buildStageFilters(name, stageSql),
  );
  const havingConditions = stages.flatMap(({ name, sql: stageSql }) =>
    buildStageHavingFilters(name, stageSql),
  );
  const groupBy = buildGroupByAnalyses(stages);
  const aggregations = stages.flatMap(({ name, sql: stageSql }) =>
    extractAggregations(name, stageSql),
  );
  const windowFunctions = stages.flatMap(({ name, sql: stageSql }) =>
    extractWindowFunctions(name, stageSql),
  );
  const caseExpressions = stages.flatMap(({ name, sql: stageSql }) =>
    extractCaseExpressions(name, stageSql),
  );
  const derivedColumns = stages.flatMap(({ name, sql: stageSql }) =>
    extractDerivedColumns(name, stageSql),
  );
  const businessIntent = buildBusinessIntent(
    sql,
    tables,
    ctes,
    setOperations,
    groupBy,
    aggregations,
    windowFunctions,
    caseExpressions,
  );
  const businessGuesses = buildBusinessGuesses(
    tables,
    relations,
    businessIntent,
    ctes,
    groupBy,
    aggregations,
    windowFunctions,
    caseExpressions,
  );
  const finalResult = buildFinalResultDescription(
    tables,
    businessIntent,
    ctes,
    groupBy,
    aggregations,
    windowFunctions,
    caseExpressions,
    derivedColumns,
  );
  const notes = buildNotes(
    tables,
    businessIntent,
    ctes,
    groupBy,
    aggregations,
    windowFunctions,
    caseExpressions,
  );
  const confidence = buildConfidence(
    sql,
    tables,
    relations,
    ctes,
    filters,
    havingConditions,
    groupBy,
    aggregations,
    windowFunctions,
    caseExpressions,
    subqueries,
    setOperations,
  );
  const warnings = buildWarnings(
    tables,
    relations,
    confidence,
    subqueries,
    setOperations,
  );

  return {
    aggregations,
    businessIntent,
    summary: buildSummary(
      tables,
      whereConditions,
      businessIntent,
      ctes,
      groupBy,
      aggregations,
      windowFunctions,
      caseExpressions,
      sql,
    ),
    caseExpressions,
    confidence,
    ctes,
    derivedColumns,
    finalResult,
    filters,
    groupBy,
    havingConditions,
    notes,
    setOperations,
    subqueries,
    tables,
    warnings,
    whereConditions,
    joins: relations,
    relations,
    businessGuesses,
    developerExplanation: buildDeveloperExplanation(
      tables,
      relations,
      whereConditions,
      ctes,
      businessIntent,
      aggregations,
      windowFunctions,
      caseExpressions,
      sql,
    ),
    windowFunctions,
  };
}

export function explainSql(sql: string): SqlExplanation {
  return analyzeSql(sql);
}
