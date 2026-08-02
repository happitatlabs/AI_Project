import {
  normalizeConditionPattern,
  type MultiSqlAnalysisResult,
} from "./multiSqlAnalysis.js";
import type {
  AnalysisConfidence,
  BusinessIntentType,
  SqlAnalysisResult,
} from "./sqlExplainer.js";

export type TableAssetRole =
  | "core"
  | "transaction"
  | "master"
  | "reference"
  | "log"
  | "mapping"
  | "staging"
  | "report"
  | "unknown";

export type TableAssetImportance = "high" | "medium" | "low";

export type TableAssetUsageSql = {
  statementId: string;
  summary: string;
  businessIntent: BusinessIntentType;
  confidenceLevel: AnalysisConfidence["level"];
};

export type TableAssetJoinTarget = {
  tableName: string;
  columnPairs: Array<{
    sourceColumn: string;
    targetColumn: string;
  }>;
  count: number;
  joinTypes: string[];
  statementIds: string[];
};

export type TableAssetCondition = {
  columnName?: string;
  normalizedCondition: string;
  count: number;
  statementIds: string[];
  stages: string[];
  examples: string[];
};

export type TableAssetProfile = {
  key: string;
  tableName: string;
  rawNames: string[];
  schemaNames: string[];
  description: string;
  role: TableAssetRole;
  importance: TableAssetImportance;
  importanceScore: number;
  usageCount: number;
  usedBySql: TableAssetUsageSql[];
  joinTargets: TableAssetJoinTarget[];
  conditions: TableAssetCondition[];
  businessIntentSummary: Partial<Record<BusinessIntentType, number>>;
  businessGuesses: string[];
  isInsertTarget: boolean;
  isReadSource: boolean;
  warnings: string[];
};

export type TableAssetMap = {
  tables: TableAssetProfile[];
  coreTables: TableAssetProfile[];
  summary: {
    tableCount: number;
    coreTableCount: number;
    joinRelationCount: number;
    insertTargetCount: number;
    analyticsRelatedTableCount: number;
  };
  warnings: string[];
};

type MutableTableAssetProfile = Omit<
  TableAssetProfile,
  "conditions" | "joinTargets" | "usedBySql"
> & {
  conditionMap: Map<string, TableAssetCondition>;
  joinTargetMap: Map<string, TableAssetJoinTarget>;
  usedBySqlMap: Map<string, TableAssetUsageSql>;
};

const unique = <T>(values: T[]) => Array.from(new Set(values));

const pushUnique = <T>(target: T[], value: T) => {
  if (!target.includes(value)) {
    target.push(value);
  }
};

const cleanIdentifier = (identifier: string) =>
  identifier
    .trim()
    .replace(/[,;]$/g, "")
    .replace(/^["`\[]|["`\]]$/g, "");

const splitTableName = (rawName: string) => {
  const cleaned = rawName.trim();
  const parts = cleaned.split(".").map(cleanIdentifier).filter(Boolean);
  const tableName = parts[parts.length - 1] ?? cleanIdentifier(cleaned);
  const schemaName = parts.length > 1 ? parts.slice(0, -1).join(".") : undefined;

  return {
    schemaName,
    tableName,
  };
};

const tableKey = (tableName: string, schemaName?: string) =>
  `${schemaName ?? ""}.${tableName}`.toUpperCase();

const tableKeyFromAnalysisTable = (table: SqlAnalysisResult["tables"][number]) =>
  tableKey(table.tableName, table.schemaName);

const createProfile = (
  tableName: string,
  options: {
    description?: string;
    rawName?: string;
    schemaName?: string;
    isInsertTarget?: boolean;
    isReadSource?: boolean;
  } = {},
): MutableTableAssetProfile => ({
  businessGuesses: [],
  businessIntentSummary: {},
  conditionMap: new Map(),
  description: options.description ?? `${tableName} 업무 데이터로 추정`,
  importance: "low",
  importanceScore: 0,
  isInsertTarget: Boolean(options.isInsertTarget),
  isReadSource: options.isReadSource ?? true,
  joinTargetMap: new Map(),
  key: tableKey(tableName, options.schemaName),
  rawNames: options.rawName ? [options.rawName] : [tableName],
  role: "unknown",
  schemaNames: options.schemaName ? [options.schemaName] : [],
  tableName,
  usageCount: 0,
  usedBySqlMap: new Map(),
  warnings: [],
});

const ensureProfile = (
  profiles: Map<string, MutableTableAssetProfile>,
  tableName: string,
  options: {
    description?: string;
    rawName?: string;
    schemaName?: string;
    isInsertTarget?: boolean;
    isReadSource?: boolean;
  } = {},
) => {
  const key = tableKey(tableName, options.schemaName);
  const existing = profiles.get(key);

  if (existing) {
    if (options.rawName) {
      pushUnique(existing.rawNames, options.rawName);
    }

    if (options.schemaName) {
      pushUnique(existing.schemaNames, options.schemaName);
    }

    if (options.description && existing.description.includes("추정")) {
      existing.description = options.description;
    }

    existing.isInsertTarget ||= Boolean(options.isInsertTarget);
    existing.isReadSource ||= options.isReadSource ?? false;
    return existing;
  }

  const profile = createProfile(tableName, options);
  profiles.set(key, profile);
  return profile;
};

const extractInsertTarget = (sql: string) => {
  const match = sql.match(/\bINSERT\s+INTO\s+([A-Za-z0-9_$#."`\[\]]+(?:\s*\.\s*[A-Za-z0-9_$#."`\[\]]+)?)/i);

  if (!match) {
    return undefined;
  }

  const rawName = match[1].replace(/\s+/g, "");
  const parsed = splitTableName(rawName);

  return {
    rawName,
    ...parsed,
  };
};

const splitColumnRef = (columnRef: string) => {
  const parts = columnRef.split(".").map(cleanIdentifier).filter(Boolean);

  if (parts.length < 2) {
    return undefined;
  }

  return {
    columnName: parts[parts.length - 1],
    tableName: parts.length > 2 ? parts[parts.length - 2] : parts[0],
  };
};

const inferRole = (profile: MutableTableAssetProfile): TableAssetRole => {
  const text = [
    profile.tableName,
    ...profile.rawNames,
    profile.description,
    ...Object.keys(profile.businessIntentSummary),
  ].join(" ").toUpperCase();

  if (/STG|STAGING|TEMP|TMP|WORK/.test(text)) {
    return "staging";
  }

  if (/SNAPSHOT|SUMMARY|REPORT|MART|DASHBOARD/.test(text) || profile.isInsertTarget) {
    return "report";
  }

  if (/HIST|HISTORY|LOG|AUDIT/.test(text)) {
    return "log";
  }

  if (/MAPPING|(^|_)MAP($|_)/.test(text)) {
    return "mapping";
  }

  if (/CODE|REGION|AREA|META/.test(text)) {
    return "reference";
  }

  if (/ORDER|PAYMENT|ITEM|TRANS|TXN|SALES/.test(text)) {
    return "transaction";
  }

  if (/CUSTOMER|CUST|PRODUCT|USER|EMP|DEPT|ACCOUNT/.test(text)) {
    return "master";
  }

  return "unknown";
};

const hasAnalyticsIntent = (profile: MutableTableAssetProfile) =>
  Object.keys(profile.businessIntentSummary).some((type) =>
    ["analytics_report", "sales_summary", "ranking_analysis", "aggregation_report"].includes(type),
  );

const calculateImportanceScore = (profile: MutableTableAssetProfile) =>
  profile.usedBySqlMap.size * 3 +
  profile.joinTargetMap.size * 2 +
  profile.conditionMap.size +
  Object.keys(profile.businessIntentSummary).length * 2 +
  (profile.isInsertTarget ? 5 : 0) +
  (hasAnalyticsIntent(profile) ? 3 : 0);

const importanceFromScore = (score: number): TableAssetImportance => {
  if (score >= 15) {
    return "high";
  }

  if (score >= 7) {
    return "medium";
  }

  return "low";
};

const businessIntentLabel = (intent: string) => {
  const labels: Record<string, string> = {
    aggregation_report: "집계 리포트",
    analytics_report: "분석 리포트",
    batch_etl: "배치 적재",
    classification: "분류/라벨링",
    combined_result: "통합 결과 조회",
    data_insert: "데이터 적재",
    list_query: "목록 조회",
    lookup: "조회",
    order_list: "주문 조회",
    ranking_analysis: "순위 분석",
    sales_summary: "매출 집계",
    set_operation: "결과 결합",
    staged_query: "단계적 조회",
  };

  return labels[intent] ?? intent;
};

const buildBusinessGuesses = (profile: MutableTableAssetProfile) =>
  unique(
    Object.entries(profile.businessIntentSummary)
      .sort(([, leftCount], [, rightCount]) => rightCount - leftCount)
      .map(([intent]) => businessIntentLabel(intent)),
  );

const buildAliasMap = (analysis: SqlAnalysisResult) => {
  const aliasMap = new Map<string, string>();

  analysis.tables.forEach((table) => {
    aliasMap.set(table.tableName.toUpperCase(), table.tableName);
    aliasMap.set(table.rawName.toUpperCase(), table.tableName);

    if (table.schemaName) {
      aliasMap.set(`${table.schemaName}.${table.tableName}`.toUpperCase(), table.tableName);
    }

    if (table.alias) {
      aliasMap.set(table.alias.toUpperCase(), table.tableName);
    }
  });

  return aliasMap;
};

const conditionColumnPattern =
  /([A-Za-z0-9_$#"`\[\]]+)\s*\.\s*([A-Za-z0-9_$#"`\[\]]+)/g;

const addConditionToProfiles = (
  profiles: Map<string, MutableTableAssetProfile>,
  statementId: string,
  analysis: SqlAnalysisResult,
  condition: { condition: string; stage: string },
) => {
  const aliasMap = buildAliasMap(analysis);
  let attached = false;

  for (const match of condition.condition.matchAll(conditionColumnPattern)) {
    const qualifier = cleanIdentifier(match[1]);
    const columnName = cleanIdentifier(match[2]);
    const tableName = aliasMap.get(qualifier.toUpperCase());

    if (!tableName) {
      continue;
    }

    const table = analysis.tables.find((candidate) => candidate.tableName === tableName);
    const profile = ensureProfile(profiles, tableName, {
      description: table?.description,
      rawName: table?.rawName,
      schemaName: table?.schemaName,
    });
    const normalizedCondition = normalizeConditionPattern(
      condition.condition.replace(match[0], `${tableName}.${columnName}`),
    );
    const existing = profile.conditionMap.get(normalizedCondition) ?? {
      columnName,
      count: 0,
      examples: [],
      normalizedCondition,
      stages: [],
      statementIds: [],
    };

    existing.count += 1;
    pushUnique(existing.statementIds, statementId);
    pushUnique(existing.stages, condition.stage);
    pushUnique(existing.examples, condition.condition);
    profile.conditionMap.set(normalizedCondition, existing);
    attached = true;
  }

  return attached;
};

const addJoinTarget = (
  profile: MutableTableAssetProfile,
  targetTableName: string,
  sourceColumn: string,
  targetColumn: string,
  statementId: string,
  joinType?: string,
) => {
  const existing = profile.joinTargetMap.get(targetTableName) ?? {
    columnPairs: [],
    count: 0,
    joinTypes: [],
    statementIds: [],
    tableName: targetTableName,
  };

  existing.count += 1;

  if (!existing.columnPairs.some((pair) => pair.sourceColumn === sourceColumn && pair.targetColumn === targetColumn)) {
    existing.columnPairs.push({ sourceColumn, targetColumn });
  }

  if (joinType) {
    pushUnique(existing.joinTypes, joinType);
  }

  pushUnique(existing.statementIds, statementId);
  profile.joinTargetMap.set(targetTableName, existing);
};

export const buildTableAssetMap = (multiAnalysis: MultiSqlAnalysisResult): TableAssetMap => {
  const profiles = new Map<string, MutableTableAssetProfile>();
  const warnings: string[] = [];

  multiAnalysis.statements.forEach((statement) => {
    const analysis = statement.analysis;

    if (!analysis) {
      return;
    }

    const insertTarget = extractInsertTarget(statement.sql);

    if (insertTarget) {
      const insertProfile = ensureProfile(profiles, insertTarget.tableName, {
        isInsertTarget: true,
        isReadSource: false,
        rawName: insertTarget.rawName,
        schemaName: insertTarget.schemaName,
      });

      insertProfile.usedBySqlMap.set(statement.id, {
        businessIntent: analysis.businessIntent.type,
        confidenceLevel: analysis.confidence.level,
        statementId: statement.id,
        summary: analysis.summary,
      });
      insertProfile.businessIntentSummary[analysis.businessIntent.type] =
        (insertProfile.businessIntentSummary[analysis.businessIntent.type] ?? 0) + 1;
    }

    analysis.tables.forEach((table) => {
      const profile = ensureProfile(profiles, table.tableName, {
        description: table.description,
        isReadSource: true,
        rawName: table.rawName,
        schemaName: table.schemaName,
      });

      profile.usedBySqlMap.set(statement.id, {
        businessIntent: analysis.businessIntent.type,
        confidenceLevel: analysis.confidence.level,
        statementId: statement.id,
        summary: analysis.summary,
      });
      profile.businessIntentSummary[analysis.businessIntent.type] =
        (profile.businessIntentSummary[analysis.businessIntent.type] ?? 0) + 1;
    });

    analysis.joins.forEach((join) => {
      const left = splitColumnRef(join.left);
      const right = splitColumnRef(join.right);

      if (!left || !right) {
        return;
      }

      const leftProfile = ensureProfile(profiles, left.tableName);
      const rightProfile = ensureProfile(profiles, right.tableName);

      addJoinTarget(
        leftProfile,
        right.tableName,
        left.columnName,
        right.columnName,
        statement.id,
        join.joinType,
      );
      addJoinTarget(
        rightProfile,
        left.tableName,
        right.columnName,
        left.columnName,
        statement.id,
        join.joinType,
      );
    });

    [...analysis.filters, ...analysis.havingConditions].forEach((condition) => {
      const attached = addConditionToProfiles(profiles, statement.id, analysis, condition);

      if (!attached) {
        warnings.push(`${statement.id}: ${condition.condition} 조건은 테이블별 조건으로 확정하지 못했습니다.`);
      }
    });
  });

  const tables = Array.from(profiles.values()).map((profile) => {
    profile.usageCount = profile.usedBySqlMap.size;
    profile.role = inferRole(profile);
    profile.importanceScore = calculateImportanceScore(profile);
    profile.importance = importanceFromScore(profile.importanceScore);
    profile.businessGuesses = buildBusinessGuesses(profile);

    if (profile.description.includes("추정")) {
      profile.warnings.push(`${profile.tableName}의 업무 의미는 테이블명 기준 추정입니다.`);
    }

    if (profile.importance === "high") {
      profile.warnings.push("여러 SQL/업무 유형에서 반복 사용되어 핵심 테이블 후보입니다.");
    }

    if (profile.isInsertTarget) {
      profile.warnings.push("INSERT INTO 대상 테이블로 사용되어 배치/적재 흐름 확인이 필요합니다.");
    }

    const {
      conditionMap,
      joinTargetMap,
      usedBySqlMap,
      ...profileBase
    } = profile;

    return {
      ...profileBase,
      businessGuesses: unique(profile.businessGuesses),
      conditions: Array.from(conditionMap.values()).sort((left, right) => right.count - left.count),
      joinTargets: Array.from(joinTargetMap.values()).sort((left, right) => right.count - left.count),
      rawNames: unique(profile.rawNames),
      schemaNames: unique(profile.schemaNames),
      usedBySql: Array.from(usedBySqlMap.values()).sort((left, right) =>
        left.statementId.localeCompare(right.statementId),
      ),
      warnings: unique(profile.warnings),
    } satisfies TableAssetProfile;
  }).sort((left, right) => {
    if (right.importanceScore !== left.importanceScore) {
      return right.importanceScore - left.importanceScore;
    }

    return left.tableName.localeCompare(right.tableName);
  });

  const coreTables = tables.filter((table) => table.importance === "high");
  const analyticsRelatedTableCount = tables.filter((table) =>
    Object.keys(table.businessIntentSummary).some((intent) =>
      ["analytics_report", "sales_summary", "ranking_analysis", "aggregation_report"].includes(intent),
    ),
  ).length;

  return {
    coreTables,
    summary: {
      analyticsRelatedTableCount,
      coreTableCount: coreTables.length,
      insertTargetCount: tables.filter((table) => table.isInsertTarget).length,
      joinRelationCount: tables.reduce((total, table) => total + table.joinTargets.length, 0),
      tableCount: tables.length,
    },
    tables,
    warnings: unique(warnings),
  };
};

const importanceLabel = (importance: TableAssetImportance) => {
  if (importance === "high") {
    return "높음";
  }

  if (importance === "medium") {
    return "보통";
  }

  return "낮음";
};

export const buildTableAssetMapMarkdownSection = (assetMap: TableAssetMap) => [
  "## 테이블 자산 지도",
  "",
  "### 요약",
  `- 전체 테이블: ${assetMap.summary.tableCount}개`,
  `- 핵심 테이블 후보: ${assetMap.summary.coreTableCount}개`,
  `- JOIN 연결: ${assetMap.summary.joinRelationCount}개`,
  `- INSERT 대상 테이블: ${assetMap.summary.insertTargetCount}개`,
  `- 분석/리포트 관련 테이블: ${assetMap.summary.analyticsRelatedTableCount}개`,
  "",
  "### 핵심 테이블 후보",
  ...(
    assetMap.coreTables.length > 0
      ? assetMap.coreTables.map(
        (table) =>
          `- ${table.tableName}: 핵심도 ${importanceLabel(table.importance)}(${table.importanceScore}점), 사용 SQL ${table.usageCount}개, JOIN 대상 ${table.joinTargets.length}개`,
      )
      : ["- 핵심 테이블 후보가 없습니다."]
  ),
  "",
  "### 테이블별 상세",
  ...assetMap.tables.flatMap((table) => [
    `#### ${table.tableName}`,
    `- 역할: ${table.role}로 추정`,
    `- 핵심도: ${importanceLabel(table.importance)} (${table.importanceScore}점)`,
    `- 사용 SQL: ${table.usedBySql.map((sql) => sql.statementId).join(", ") || "없음"}`,
    `- JOIN 대상: ${table.joinTargets.map((join) => join.tableName).join(", ") || "없음"}`,
    `- 주요 조건: ${table.conditions.slice(0, 5).map((condition) => condition.normalizedCondition).join(", ") || "없음"}`,
    `- 업무 추정: ${table.businessGuesses.join(", ") || "없음"}`,
    "",
  ]),
].join("\n");
