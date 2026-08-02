import type { MultiSqlAnalysisResult, MultiSqlStatement } from "./multiSqlAnalysis.js";

export type SqlRiskSeverity = "critical" | "high" | "medium" | "low";

export type SqlRiskCategory =
  | "select_star"
  | "unsafe_update_delete"
  | "implicit_join"
  | "too_many_joins"
  | "duplicate_sql_pattern"
  | "date_function_on_column"
  | "leading_wildcard_like"
  | "suspicious_aggregation"
  | "hardcoded_code_value"
  | "personal_info_condition";

export type SqlRiskFinding = {
  id: string;
  statementId: string;
  category: SqlRiskCategory;
  severity: SqlRiskSeverity;
  title: string;
  message: string;
  evidence: string;
  recommendation: string;
  confidence: "low" | "medium" | "high";
};

export type SqlRiskAnalysisResult = {
  findings: SqlRiskFinding[];
  summary: {
    total: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
};

type RiskDraft = Omit<SqlRiskFinding, "id" | "statementId">;

const severityRank: Record<SqlRiskSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const unique = <T>(values: T[]) => Array.from(new Set(values));

const compactSql = (sql: string) => sql.replace(/\s+/g, " ").trim();

const stripComments = (sql: string) => {
  let result = "";
  let quote: "'" | "\"" | "`" | "]" | null = null;
  let lineComment = false;
  let blockComment = false;

  for (let index = 0; index < sql.length; index += 1) {
    const char = sql[index];
    const nextChar = sql[index + 1];

    if (lineComment) {
      if (char === "\n") {
        result += char;
        lineComment = false;
      }

      continue;
    }

    if (blockComment) {
      if (char === "*" && nextChar === "/") {
        index += 1;
        blockComment = false;
      }

      continue;
    }

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

    if (char === "-" && nextChar === "-") {
      lineComment = true;
      index += 1;
      continue;
    }

    if (char === "/" && nextChar === "*") {
      blockComment = true;
      index += 1;
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

const normalizeSqlPattern = (sql: string) =>
  compactSql(stripComments(sql))
    .replace(/'((?:''|[^'])*)'/g, "?")
    .replace(/\bDATE\s+'\d{4}-\d{2}-\d{2}'/gi, "DATE ?")
    .replace(/\b\d{4}-\d{2}-\d{2}\b/g, "?")
    .replace(/\b\d+(?:\.\d+)?\b/g, "?")
    .replace(/\s*;\s*$/g, "")
    .toUpperCase();

const hasWhere = (sql: string) => /\bWHERE\b/i.test(sql);

const extractSelectList = (sql: string) => {
  const normalized = compactSql(sql);
  const match = normalized.match(/\bSELECT\b\s+([\s\S]*?)\s+\bFROM\b/i);

  return match?.[1] ?? "";
};

const splitTopLevelComma = (value: string) => {
  const parts: string[] = [];
  let current = "";
  let depth = 0;
  let quote: "'" | "\"" | "`" | "]" | null = null;

  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    const nextChar = value[index + 1];

    if (quote) {
      current += char;

      if (
        ((quote === "'" || quote === "\"" || quote === "`") && char === quote && nextChar === quote) ||
        (quote === "]" && char === "]" && nextChar === "]")
      ) {
        current += nextChar;
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
      current += char;
      continue;
    }

    if (char === "[") {
      quote = "]";
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
      parts.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  if (current.trim()) {
    parts.push(current.trim());
  }

  return parts;
};

const findWhereClause = (sql: string) => {
  const normalized = compactSql(sql);
  const match = normalized.match(/\bWHERE\b\s+([\s\S]*?)(?:\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|\bUNION\b|\bEXCEPT\b|\bINTERSECT\b|$)/i);

  return match?.[1] ?? "";
};

const addFinding = (findings: RiskDraft[], finding: RiskDraft) => {
  if (
    findings.some((existing) =>
      existing.category === finding.category &&
      existing.evidence === finding.evidence &&
      existing.title === finding.title,
    )
  ) {
    return;
  }

  findings.push(finding);
};

const detectSelectStar = (sql: string, findings: RiskDraft[], joinCount: number) => {
  const selectList = extractSelectList(sql);

  if (!/(^|,)\s*(?:[A-Za-z0-9_$#"`\[\]]+\s*\.\s*)?\*\s*(?:,|$)/.test(selectList)) {
    return;
  }

  addFinding(findings, {
    category: "select_star",
    confidence: "high",
    evidence: `SELECT ${selectList}`,
    message: "SELECT * 사용으로 컬럼 추가/삭제 시 화면, API, 배치 결과에 예상치 못한 영향이 생길 수 있습니다.",
    recommendation: "필요한 컬럼만 명시하고 컬럼 변경 영향 범위를 줄이세요.",
    severity: joinCount >= 3 ? "high" : "medium",
    title: "SELECT * 사용",
  });
};

const detectUnsafeUpdateDelete = (sql: string, findings: RiskDraft[]) => {
  const normalized = compactSql(sql);

  if (!/^\s*(UPDATE|DELETE)\b/i.test(normalized) || hasWhere(normalized)) {
    return;
  }

  const command = normalized.match(/^\s*(UPDATE|DELETE)\b/i)?.[1]?.toUpperCase() ?? "UPDATE/DELETE";

  addFinding(findings, {
    category: "unsafe_update_delete",
    confidence: "high",
    evidence: normalized.slice(0, 160),
    message: `${command} 문에 WHERE 조건이 없어 전체 데이터 변경 또는 삭제 위험이 있습니다.`,
    recommendation: "WHERE 조건을 추가하고 실행 전 영향 건수, 트랜잭션, 백업 여부를 확인하세요.",
    severity: "critical",
    title: "WHERE 없는 UPDATE/DELETE",
  });
};

const detectImplicitJoin = (sql: string, findings: RiskDraft[]) => {
  const normalized = compactSql(sql);
  const fromMatch = normalized.match(/\bFROM\b\s+([\s\S]*?)(?:\bWHERE\b|\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|$)/i);
  const fromClause = fromMatch?.[1] ?? "";

  if (!fromClause.includes(",") || /\bJOIN\b/i.test(fromClause)) {
    return;
  }

  addFinding(findings, {
    category: "implicit_join",
    confidence: "medium",
    evidence: `FROM ${fromClause}`,
    message: "쉼표 기반 암묵적 JOIN은 JOIN 조건 누락 시 Cartesian product가 발생하기 쉽고 의도 파악이 어렵습니다.",
    recommendation: "명시적 JOIN ... ON 구문으로 바꾸고 테이블 간 연결 조건을 분리해 표현하세요.",
    severity: "high",
    title: "암묵적 JOIN 사용",
  });
};

const detectTooManyJoins = (joinCount: number, findings: RiskDraft[]) => {
  if (joinCount < 5) {
    return;
  }

  addFinding(findings, {
    category: "too_many_joins",
    confidence: "high",
    evidence: `JOIN ${joinCount}개`,
    message: "JOIN 수가 많아 실행 계획, 인덱스, 업무 규칙을 함께 확인해야 합니다.",
    recommendation: "기준 테이블과 필터 우선순위를 확인하고, 필요하면 CTE/View로 단계를 나누세요.",
    severity: joinCount >= 8 ? "high" : "medium",
    title: "JOIN 수 과다",
  });
};

const detectDateFunctionOnColumn = (sql: string, findings: RiskDraft[]) => {
  const whereClause = findWhereClause(sql);

  if (!whereClause) {
    return;
  }

  const patterns = [
    /\b(?:TO_CHAR|TRUNC|DATE_TRUNC|CAST|CONVERT)\s*\([^)]*(?:_DATE|DATE_|DATE\b|_AT\b|AT\b)[^)]*\)/gi,
    /\b(?:TO_CHAR|TRUNC|DATE_TRUNC|CAST|CONVERT)\s*\(\s*[A-Za-z0-9_$#"`\[\].]*(?:date|_dt|_at)[A-Za-z0-9_$#"`\[\].]*/gi,
  ];

  patterns.forEach((pattern) => {
    for (const match of whereClause.matchAll(pattern)) {
      addFinding(findings, {
        category: "date_function_on_column",
        confidence: "medium",
        evidence: match[0],
        message: "WHERE 조건에서 날짜 컬럼에 함수가 적용되어 일반 인덱스 사용이 어려울 수 있습니다.",
        recommendation: "컬럼 원형을 유지한 범위 조건으로 바꾸는 방식을 검토하세요.",
        severity: "medium",
        title: "날짜 컬럼 함수 사용",
      });
    }
  });
};

const detectLeadingWildcardLike = (sql: string, findings: RiskDraft[]) => {
  const normalized = compactSql(sql);
  const patterns = [
    /\bLIKE\s+'%[^']*%'/gi,
    /\bLIKE\s+'%'\s*\|\|/gi,
    /\bLIKE\s+CONCAT\s*\(\s*'%'/gi,
  ];

  patterns.forEach((pattern) => {
    for (const match of normalized.matchAll(pattern)) {
      addFinding(findings, {
        category: "leading_wildcard_like",
        confidence: "high",
        evidence: match[0],
        message: "앞쪽 와일드카드 LIKE 검색은 일반 B-tree 인덱스 활용이 어려울 수 있습니다.",
        recommendation: "전문 검색, trigram index, 별도 검색 인덱스 또는 prefix 검색 정책을 검토하세요.",
        severity: "medium",
        title: "LIKE 앞쪽 와일드카드 검색",
      });
    }
  });
};

const isAggregateExpression = (expression: string) =>
  /\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(/i.test(expression);

const detectSuspiciousAggregation = (sql: string, findings: RiskDraft[]) => {
  const selectList = extractSelectList(sql);

  if (!selectList || !isAggregateExpression(selectList) || /\bGROUP\s+BY\b/i.test(sql)) {
    return;
  }

  const expressions = splitTopLevelComma(selectList);
  const aggregateExpressions = expressions.filter(isAggregateExpression);
  const nonAggregateExpressions = expressions.filter((expression) => !isAggregateExpression(expression));

  if (aggregateExpressions.length === 1 && nonAggregateExpressions.length === 0 && /^COUNT\s*\(\s*\*\s*\)/i.test(aggregateExpressions[0])) {
    return;
  }

  if (nonAggregateExpressions.length === 0) {
    return;
  }

  addFinding(findings, {
    category: "suspicious_aggregation",
    confidence: "medium",
    evidence: `SELECT ${selectList}`,
    message: "집계 함수와 비집계 컬럼이 함께 있지만 GROUP BY가 없어 DBMS에 따라 오류 또는 의도와 다른 결과가 날 수 있습니다.",
    recommendation: "집계 기준 컬럼을 GROUP BY에 명시하거나 집계 전용 SELECT로 분리하세요.",
    severity: "high",
    title: "GROUP BY 없는 집계 의심",
  });
};

const detectHardcodedCodeValues = (sql: string, findings: RiskDraft[]) => {
  const normalized = compactSql(sql);
  const codeValuePattern =
    /\b(?:status|state|type|code|cd|use_yn|yn|grade|role|category|channel)\b\s*(?:=|IN\s*\()\s*([^)\s;]+(?:\s*,\s*[^)\s;]+)*)/gi;

  for (const match of normalized.matchAll(codeValuePattern)) {
    const evidence = match[0];
    const values = unique(Array.from(evidence.matchAll(/'([^']+)'/g)).map((valueMatch) => valueMatch[1]));

    if (values.length === 0) {
      continue;
    }

    addFinding(findings, {
      category: "hardcoded_code_value",
      confidence: "medium",
      evidence,
      message: "상태, 유형, 코드값이 SQL에 하드코딩되어 코드 체계 변경 시 SQL 수정 누락 위험이 있습니다.",
      recommendation: "코드 테이블 JOIN, 파라미터화, 상수 관리 또는 문서화를 검토하세요.",
      severity: values.length >= 5 ? "medium" : "low",
      title: "하드코딩 코드값",
    });
  }
};

const detectPersonalInfoCondition = (sql: string, findings: RiskDraft[]) => {
  const whereClause = findWhereClause(sql);

  if (!whereClause) {
    return;
  }

  const piiPattern =
    /\b[A-Za-z0-9_$#"`\[\].]*(email|phone|mobile|tel|ssn|resident_no|rrn|birth|customer_name|user_name|name|address|card_no)[A-Za-z0-9_$#"`\[\].]*\b\s*(=|LIKE|IN\b|BETWEEN\b)/gi;

  for (const match of whereClause.matchAll(piiPattern)) {
    const column = match[0];
    const severity = /ssn|resident_no|rrn|card_no/i.test(column) ? "high" : "medium";

    addFinding(findings, {
      category: "personal_info_condition",
      confidence: "medium",
      evidence: column,
      message: "개인정보로 추정되는 컬럼이 조건에 사용되어 로그, 문서 공유, AI 전송 시 주의가 필요합니다.",
      recommendation: "마스킹, 접근 권한, 로그 적재 여부, 문서 공유 범위를 확인하세요.",
      severity,
      title: "개인정보 조건 사용 가능성",
    });
  }
};

const buildFindingId = (
  statementId: string,
  category: SqlRiskCategory,
  index: number,
) => `${statementId}-${category}-${String(index + 1).padStart(2, "0")}`;

const analyzeStatementRisks = (statement: MultiSqlStatement): SqlRiskFinding[] => {
  const sql = stripComments(statement.sql);
  const joinCount = statement.analysis?.joins.length ?? 0;
  const drafts: RiskDraft[] = [];

  detectSelectStar(sql, drafts, joinCount);
  detectUnsafeUpdateDelete(sql, drafts);
  detectImplicitJoin(sql, drafts);
  detectTooManyJoins(joinCount, drafts);
  detectDateFunctionOnColumn(sql, drafts);
  detectLeadingWildcardLike(sql, drafts);
  detectSuspiciousAggregation(sql, drafts);
  detectHardcodedCodeValues(sql, drafts);
  detectPersonalInfoCondition(sql, drafts);

  return drafts.map((draft, index) => ({
    ...draft,
    id: buildFindingId(statement.id, draft.category, index),
    statementId: statement.id,
  }));
};

const duplicatePatternFinding = (
  statementId: string,
  duplicatedStatementIds: string[],
  pattern: string,
): SqlRiskFinding => ({
  category: "duplicate_sql_pattern",
  confidence: "medium",
  evidence: pattern.slice(0, 220),
  id: buildFindingId(statementId, "duplicate_sql_pattern", 0),
  message: `리터럴만 다른 유사 SQL 패턴이 ${duplicatedStatementIds.join(", ")}에서 반복됩니다.`,
  recommendation: "공통 View, 공통 DAO/query template, 파라미터화로 중복 변경 위험을 줄이세요.",
  severity: "medium",
  statementId,
  title: "중복 SQL 패턴",
});

export const analyzeSqlRisks = (
  multiAnalysis: MultiSqlAnalysisResult,
): SqlRiskAnalysisResult => {
  const findings: SqlRiskFinding[] = multiAnalysis.statements.flatMap(analyzeStatementRisks);
  const patternMap = new Map<string, string[]>();

  multiAnalysis.statements.forEach((statement) => {
    const pattern = normalizeSqlPattern(statement.sql);
    const statementIds = patternMap.get(pattern) ?? [];
    statementIds.push(statement.id);
    patternMap.set(pattern, statementIds);
  });

  patternMap.forEach((statementIds, pattern) => {
    if (statementIds.length < 2) {
      return;
    }

    statementIds.forEach((statementId) => {
      findings.push(duplicatePatternFinding(statementId, statementIds, pattern));
    });
  });

  const sortedFindings = findings.sort((left, right) => {
    if (severityRank[left.severity] !== severityRank[right.severity]) {
      return severityRank[left.severity] - severityRank[right.severity];
    }

    if (left.statementId !== right.statementId) {
      return left.statementId.localeCompare(right.statementId);
    }

    return left.category.localeCompare(right.category);
  });

  return {
    findings: sortedFindings,
    summary: {
      critical: sortedFindings.filter((finding) => finding.severity === "critical").length,
      high: sortedFindings.filter((finding) => finding.severity === "high").length,
      low: sortedFindings.filter((finding) => finding.severity === "low").length,
      medium: sortedFindings.filter((finding) => finding.severity === "medium").length,
      total: sortedFindings.length,
    },
  };
};
