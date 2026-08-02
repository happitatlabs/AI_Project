import {
  analyzeSql,
  type BusinessIntentType,
  type SqlAnalysisResult,
} from "./sqlExplainer.js";

export type MultiSqlStatement = {
  id: string;
  title: string;
  sql: string;
  analysis?: SqlAnalysisResult;
  warnings: string[];
  error?: string;
};

export type TableUsageSummary = {
  tableName: string;
  rawNames: string[];
  schemaNames: string[];
  count: number;
  statementIds: string[];
  businessIntents: BusinessIntentType[];
};

export type JoinUsageSummary = {
  left: string;
  right: string;
  count: number;
  joinTypes: string[];
  statementIds: string[];
};

export type ConditionUsageSummary = {
  condition: string;
  normalizedCondition: string;
  count: number;
  stages: string[];
  statementIds: string[];
};

export type MultiSqlAnalysisResult = {
  statements: MultiSqlStatement[];
  tableUsage: TableUsageSummary[];
  joinUsage: JoinUsageSummary[];
  conditionUsage: ConditionUsageSummary[];
  businessIntentSummary: Record<string, number>;
  warnings: string[];
};

const trimStatement = (value: string) => value.trim().replace(/;+\s*$/g, "").trim();

const unique = <T>(values: T[]) => Array.from(new Set(values));

const isOpenRoutineDefinition = (statement: string) =>
  /\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|PACKAGE(?:\s+BODY)?)\b/i.test(statement) &&
  !/\bEND(?:\s+[A-Za-z0-9_$#]+)?\s*;\s*$/i.test(statement.trim());

export const splitSqlStatements = (input: string) => {
  const statements: string[] = [];
  let current = "";
  let quote: "'" | "\"" | "`" | "]" | null = null;
  let lineComment = false;
  let blockComment = false;

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const nextChar = input[index + 1];

    if (lineComment) {
      current += char;

      if (char === "\n") {
        lineComment = false;
      }

      continue;
    }

    if (blockComment) {
      current += char;

      if (char === "*" && nextChar === "/") {
        current += nextChar;
        index += 1;
        blockComment = false;
      }

      continue;
    }

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

    if (char === "-" && nextChar === "-") {
      current += char;
      current += nextChar;
      index += 1;
      lineComment = true;
      continue;
    }

    if (char === "/" && nextChar === "*") {
      current += char;
      current += nextChar;
      index += 1;
      blockComment = true;
      continue;
    }

    if (char === "'" || char === "\"" || char === "`") {
      current += char;
      quote = char;
      continue;
    }

    if (char === "[") {
      current += char;
      quote = "]";
      continue;
    }

    if (char === ";") {
      const routineCandidate = `${current};`;

      if (isOpenRoutineDefinition(routineCandidate)) {
        current += char;
        continue;
      }

      const statement = trimStatement(current);

      if (statement) {
        statements.push(statement);
      }

      current = "";
      continue;
    }

    current += char;
  }

  const statement = trimStatement(current);

  if (statement) {
    statements.push(statement);
  }

  return statements;
};

const tableUsageKey = (table: SqlAnalysisResult["tables"][number]) =>
  `${table.schemaName ?? ""}.${table.tableName}`.toUpperCase();

const joinUsageKey = (left: string, right: string) =>
  [left.toUpperCase(), right.toUpperCase()].sort().join("=");

export const normalizeConditionPattern = (condition: string) =>
  condition
    .replace(/'((?:''|[^'])*)'/g, "?")
    .replace(/\b\d{4}-\d{2}-\d{2}\b/g, "?")
    .replace(/\b\d+(?:\.\d+)?\b/g, "?")
    .replace(/\s+/g, " ")
    .trim();

const sortByCountThenName = <T extends { count: number }>(
  values: T[],
  getName: (value: T) => string,
) =>
  values.sort((left, right) => {
    if (right.count !== left.count) {
      return right.count - left.count;
    }

    return getName(left).localeCompare(getName(right));
  });

const pushUnique = <T>(target: T[], value: T) => {
  if (!target.includes(value)) {
    target.push(value);
  }
};

export const analyzeMultipleSql = (input: string): MultiSqlAnalysisResult => {
  const rawStatements = splitSqlStatements(input);
  const statements: MultiSqlStatement[] = rawStatements.map((sql, index) => {
    const id = `SQL-${String(index + 1).padStart(3, "0")}`;

    try {
      const analysis = analyzeSql(sql);

      return {
        analysis,
        id,
        sql,
        title: `${id} ${analysis.summary}`,
        warnings: [...analysis.warnings],
      };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : "SQL 분석 중 오류가 발생했습니다.",
        id,
        sql,
        title: `${id} 분석 실패`,
        warnings: ["해당 SQL은 분석 중 오류가 발생해 집계에서 제외했습니다."],
      };
    }
  });

  const tableUsageMap = new Map<string, TableUsageSummary>();
  const joinUsageMap = new Map<string, JoinUsageSummary>();
  const conditionUsageMap = new Map<string, ConditionUsageSummary>();
  const businessIntentSummary: Record<string, number> = {};
  const warnings: string[] = [];

  statements.forEach((statement) => {
    if (statement.error) {
      warnings.push(`${statement.id}: ${statement.error}`);
      return;
    }

    const analysis = statement.analysis;

    if (!analysis) {
      return;
    }

    const businessIntent = analysis.businessIntent.type;
    businessIntentSummary[businessIntent] = (businessIntentSummary[businessIntent] ?? 0) + 1;

    analysis.tables.forEach((table) => {
      const key = tableUsageKey(table);
      const existing = tableUsageMap.get(key) ?? {
        businessIntents: [],
        count: 0,
        rawNames: [],
        schemaNames: [],
        statementIds: [],
        tableName: table.tableName,
      };

      existing.count += 1;
      pushUnique(existing.rawNames, table.rawName);

      if (table.schemaName) {
        pushUnique(existing.schemaNames, table.schemaName);
      }

      pushUnique(existing.statementIds, statement.id);
      pushUnique(existing.businessIntents, businessIntent);
      tableUsageMap.set(key, existing);
    });

    analysis.joins.forEach((join) => {
      const key = joinUsageKey(join.left, join.right);
      const existing = joinUsageMap.get(key) ?? {
        count: 0,
        joinTypes: [],
        left: join.left,
        right: join.right,
        statementIds: [],
      };

      existing.count += 1;

      if (join.joinType) {
        pushUnique(existing.joinTypes, join.joinType);
      }

      pushUnique(existing.statementIds, statement.id);
      joinUsageMap.set(key, existing);
    });

    [...analysis.filters, ...analysis.havingConditions].forEach((filter) => {
      const normalizedCondition = normalizeConditionPattern(filter.condition);
      const existing = conditionUsageMap.get(normalizedCondition) ?? {
        condition: filter.condition,
        count: 0,
        normalizedCondition,
        stages: [],
        statementIds: [],
      };

      existing.count += 1;
      pushUnique(existing.stages, filter.stage);
      pushUnique(existing.statementIds, statement.id);
      conditionUsageMap.set(normalizedCondition, existing);
    });

    warnings.push(...analysis.warnings.map((warning) => `${statement.id}: ${warning}`));
  });

  return {
    businessIntentSummary,
    conditionUsage: sortByCountThenName(
      Array.from(conditionUsageMap.values()),
      (condition) => condition.normalizedCondition,
    ),
    joinUsage: sortByCountThenName(
      Array.from(joinUsageMap.values()),
      (join) => `${join.left} ${join.right}`,
    ),
    statements,
    tableUsage: sortByCountThenName(
      Array.from(tableUsageMap.values()).map((table) => ({
        ...table,
        businessIntents: unique(table.businessIntents),
        rawNames: unique(table.rawNames),
        schemaNames: unique(table.schemaNames),
        statementIds: unique(table.statementIds),
      })),
      (table) => table.tableName,
    ),
    warnings: unique(warnings),
  };
};

export const buildMultiSqlMarkdownReport = (result: MultiSqlAnalysisResult) => {
  const businessIntentLines = Object.entries(result.businessIntentSummary)
    .sort(([leftName, leftCount], [rightName, rightCount]) =>
      rightCount === leftCount ? leftName.localeCompare(rightName) : rightCount - leftCount,
    )
    .map(([type, count]) => `- ${type}: ${count}개`);

  return [
    "# 다건 SQL 분석 보고서",
    "",
    "## 요약",
    `- 분석 SQL: ${result.statements.length}개`,
    `- 사용 테이블: ${result.tableUsage.length}개`,
    `- JOIN 관계: ${result.joinUsage.length}개`,
    `- 조건 패턴: ${result.conditionUsage.length}개`,
    `- warnings: ${result.warnings.length}개`,
    "",
    "## 테이블 사용 현황",
    ...(
      result.tableUsage.length > 0
        ? result.tableUsage.map(
          (table) =>
            `- ${table.tableName}: ${table.count}회 / SQL ${table.statementIds.join(", ")} / 업무 ${table.businessIntents.join(", ")}`,
        )
        : ["- 사용 테이블이 없습니다."]
    ),
    "",
    "## 반복 JOIN 관계",
    ...(
      result.joinUsage.length > 0
        ? result.joinUsage.map(
          (join) =>
            `- ${join.left} -> ${join.right}: ${join.count}회 / ${join.statementIds.join(", ")}`,
        )
        : ["- JOIN 관계가 없습니다."]
    ),
    "",
    "## 반복 조건 패턴",
    ...(
      result.conditionUsage.length > 0
        ? result.conditionUsage.map(
          (condition) =>
            `- ${condition.normalizedCondition}: ${condition.count}회 / ${condition.statementIds.join(", ")}`,
        )
        : ["- 조건 패턴이 없습니다."]
    ),
    "",
    "## 업무 목적 분포",
    ...(businessIntentLines.length > 0 ? businessIntentLines : ["- 업무 목적을 찾지 못했습니다."]),
    "",
    "## SQL별 요약",
    ...result.statements.map((statement) =>
      `- ${statement.id}: ${statement.analysis?.summary ?? statement.error ?? "분석 결과 없음"}`,
    ),
    "",
    "## 주의 사항",
    ...(result.warnings.length > 0 ? result.warnings.map((warning) => `- ${warning}`) : ["- 별도 주의 사항이 없습니다."]),
  ].join("\n");
};
