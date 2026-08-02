import type { MultiSqlAnalysisResult } from "./multiSqlAnalysis.js";
import type { AnalysisConfidence, SqlAnalysisResult } from "./sqlExplainer.js";

export type SystemGraphNodeType =
  | "table"
  | "sql"
  | "cte"
  | "view"
  | "procedure";

export type SystemGraphEdgeType =
  | "reads"
  | "writes"
  | "joins"
  | "filters"
  | "depends_on"
  | "transforms_to"
  | "calls";

export type SystemGraphMode =
  | "overview"
  | "table_relations"
  | "sql_dependencies"
  | "cte_flow"
  | "load_flow";

export type SystemGraphNode = {
  id: string;
  type: SystemGraphNodeType;
  label: string;
  description?: string;
  importance?: "high" | "medium" | "low";
  confidenceLevel?: AnalysisConfidence["level"];
  sourceStatementIds: string[];
  warnings: string[];
};

export type SystemGraphEdge = {
  id: string;
  type: SystemGraphEdgeType;
  from: string;
  to: string;
  label: string;
  sourceStatementIds: string[];
  confidenceLevel: AnalysisConfidence["level"];
  warnings: string[];
};

export type SystemGraph = {
  nodes: SystemGraphNode[];
  edges: SystemGraphEdge[];
  summary: {
    nodeCount: number;
    edgeCount: number;
    tableNodeCount: number;
    sqlNodeCount: number;
    cteNodeCount: number;
    viewNodeCount: number;
    procedureNodeCount: number;
    readDependencyCount: number;
    joinRelationCount: number;
    loadFlowCount: number;
    warningCount: number;
  };
  warnings: string[];
};

export type SystemGraphView = {
  mode: SystemGraphMode;
  title: string;
  description: string;
  nodes: SystemGraphNode[];
  edges: SystemGraphEdge[];
  warnings: string[];
};

export type ImpactDirection = "upstream" | "downstream" | "both";

export type ImpactNode = {
  nodeId: string;
  label: string;
  type: SystemGraphNodeType;
  depth: number;
  viaEdgeId: string;
  viaEdgeLabel: string;
};

export type ImpactAnalysisResult = {
  node?: SystemGraphNode;
  upstream: ImpactNode[];
  downstream: ImpactNode[];
  warnings: string[];
};

const identifierPattern = "(?:\"[^\"]+\"|`[^`]+`|\\[[^\\]]+\\]|[A-Za-z0-9_$#]+)";
const objectNamePattern = `${identifierPattern}(?:\\s*\\.\\s*${identifierPattern})*`;

const unique = <T>(values: T[]) => Array.from(new Set(values));

const pushUnique = <T>(target: T[], value: T) => {
  if (!target.includes(value)) {
    target.push(value);
  }
};

const compactSql = (sql: string) => sql.replace(/\s+/g, " ").trim();

const cleanIdentifier = (identifier: string) =>
  identifier
    .trim()
    .replace(/[,;]$/g, "")
    .replace(/^["`\[]|["`\]]$/g, "");

const splitObjectName = (rawName: string) => {
  const normalizedRawName = rawName.replace(/\s*\.\s*/g, ".");
  const parts = normalizedRawName.split(".").map(cleanIdentifier).filter(Boolean);
  const objectName = parts[parts.length - 1] ?? cleanIdentifier(normalizedRawName);
  const schemaName = parts.length > 1 ? parts.slice(0, -1).join(".") : undefined;

  return {
    objectName,
    rawName: normalizedRawName,
    schemaName,
  };
};

const normalizedObjectKey = (name: string, schemaName?: string) =>
  `${schemaName ? `${schemaName}.` : ""}${name}`.toLowerCase();

const tableNodeId = (tableName: string, schemaName?: string) =>
  `table:${normalizedObjectKey(tableName, schemaName)}`;

const sqlNodeId = (statementId: string) => `sql:${statementId.toLowerCase()}`;

const cteNodeId = (statementId: string, cteName: string) =>
  `cte:${statementId.toLowerCase()}:${cteName.toLowerCase()}`;

const viewNodeId = (viewName: string, schemaName?: string) =>
  `view:${normalizedObjectKey(viewName, schemaName)}`;

const procedureNodeId = (procedureName: string, schemaName?: string) =>
  `procedure:${normalizedObjectKey(procedureName, schemaName)}`;

const importanceRank = {
  low: 1,
  medium: 2,
  high: 3,
};

const confidenceRank = {
  low: 1,
  medium: 2,
  high: 3,
};

const edgeTypeRank: Record<SystemGraphEdgeType, number> = {
  transforms_to: 1,
  writes: 2,
  joins: 3,
  depends_on: 4,
  reads: 5,
  filters: 6,
  calls: 7,
};

const edgeTypeLabel: Record<SystemGraphEdgeType, string> = {
  calls: "호출",
  depends_on: "의존",
  filters: "조건",
  joins: "JOIN",
  reads: "읽음",
  transforms_to: "변환/적재",
  writes: "쓰기",
};

const nodeTypeLabel: Record<SystemGraphNodeType, string> = {
  cte: "CTE",
  procedure: "Procedure",
  sql: "SQL",
  table: "Table",
  view: "View",
};

const mergeImportance = (
  current: SystemGraphNode["importance"],
  next: SystemGraphNode["importance"],
) => {
  if (!current) {
    return next;
  }

  if (!next) {
    return current;
  }

  return importanceRank[next] > importanceRank[current] ? next : current;
};

const mergeConfidence = (
  current: AnalysisConfidence["level"] | undefined,
  next: AnalysisConfidence["level"] | undefined,
) => {
  if (!current) {
    return next;
  }

  if (!next) {
    return current;
  }

  return confidenceRank[next] < confidenceRank[current] ? next : current;
};

const extractInsertTarget = (sql: string) => {
  const match = sql.match(new RegExp(`\\bINSERT\\s+INTO\\s+(${objectNamePattern})`, "i"));

  if (!match) {
    return undefined;
  }

  return splitObjectName(match[1]);
};

const extractCreateObject = (sql: string) => {
  const viewMatch = sql.match(
    new RegExp(`\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?(?:MATERIALIZED\\s+)?VIEW\\s+(${objectNamePattern})\\s+AS\\b`, "i"),
  );

  if (viewMatch) {
    return {
      ...splitObjectName(viewMatch[1]),
      type: "view" as const,
    };
  }

  const procedureMatch = sql.match(
    new RegExp(`\\bCREATE\\s+(?:OR\\s+REPLACE\\s+)?(?:PROCEDURE|FUNCTION|PACKAGE(?:\\s+BODY)?)\\s+(${objectNamePattern})`, "i"),
  );

  if (procedureMatch) {
    return {
      ...splitObjectName(procedureMatch[1]),
      type: "procedure" as const,
    };
  }

  return undefined;
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

const tableNodeIdFromAnalysisTable = (table: SqlAnalysisResult["tables"][number]) =>
  tableNodeId(table.tableName, table.schemaName);

const buildTableLookup = (analysis: SqlAnalysisResult) => {
  const lookup = new Map<string, SqlAnalysisResult["tables"][number]>();

  analysis.tables.forEach((table) => {
    lookup.set(table.tableName.toLowerCase(), table);
    lookup.set(table.rawName.toLowerCase(), table);

    if (table.schemaName) {
      lookup.set(`${table.schemaName}.${table.tableName}`.toLowerCase(), table);
    }

    if (table.alias) {
      lookup.set(table.alias.toLowerCase(), table);
    }
  });

  return lookup;
};

const addNode = (
  nodes: Map<string, SystemGraphNode>,
  node: SystemGraphNode,
) => {
  const existing = nodes.get(node.id);

  if (!existing) {
    nodes.set(node.id, {
      ...node,
      sourceStatementIds: unique(node.sourceStatementIds),
      warnings: unique(node.warnings),
    });
    return;
  }

  existing.description = existing.description ?? node.description;
  existing.importance = mergeImportance(existing.importance, node.importance);
  existing.confidenceLevel = mergeConfidence(existing.confidenceLevel, node.confidenceLevel);
  node.sourceStatementIds.forEach((statementId) => pushUnique(existing.sourceStatementIds, statementId));
  node.warnings.forEach((warning) => pushUnique(existing.warnings, warning));
};

const addEdge = (
  edges: Map<string, SystemGraphEdge>,
  edge: Omit<SystemGraphEdge, "id">,
) => {
  if (edge.from === edge.to) {
    return;
  }

  const id = `${edge.type}:${edge.from}->${edge.to}:${edge.label}`.toLowerCase();
  const existing = edges.get(id);

  if (!existing) {
    edges.set(id, {
      ...edge,
      id,
      sourceStatementIds: unique(edge.sourceStatementIds),
      warnings: unique(edge.warnings),
    });
    return;
  }

  existing.confidenceLevel = mergeConfidence(existing.confidenceLevel, edge.confidenceLevel) ?? existing.confidenceLevel;
  edge.sourceStatementIds.forEach((statementId) => pushUnique(existing.sourceStatementIds, statementId));
  edge.warnings.forEach((warning) => pushUnique(existing.warnings, warning));
};

const statementNode = (
  statementId: string,
  analysis: SqlAnalysisResult,
  warnings: string[],
): SystemGraphNode => ({
  confidenceLevel: analysis.confidence.level,
  description: analysis.summary,
  id: sqlNodeId(statementId),
  importance: analysis.confidence.level === "high" ? "medium" : "low",
  label: statementId,
  sourceStatementIds: [statementId],
  type: "sql",
  warnings,
});

const tableNode = (
  statementId: string,
  table: SqlAnalysisResult["tables"][number],
  importance: SystemGraphNode["importance"] = "low",
): SystemGraphNode => ({
  confidenceLevel: undefined,
  description: table.description,
  id: tableNodeIdFromAnalysisTable(table),
  importance,
  label: table.tableName,
  sourceStatementIds: [statementId],
  type: "table",
  warnings: table.source === "subquery" ? ["서브쿼리 내부에서 탐지된 테이블입니다."] : [],
});

const insertTargetNode = (
  statementId: string,
  target: ReturnType<typeof extractInsertTarget>,
): SystemGraphNode | undefined => {
  if (!target) {
    return undefined;
  }

  return {
    description: "INSERT INTO 대상 테이블로 추정",
    id: tableNodeId(target.objectName, target.schemaName),
    importance: "medium",
    label: target.objectName,
    sourceStatementIds: [statementId],
    type: "table",
    warnings: ["INSERT INTO 대상이므로 배치/적재 흐름 영향 확인이 필요합니다."],
  };
};

const addReadEdges = (
  edges: Map<string, SystemGraphEdge>,
  statementId: string,
  analysis: SqlAnalysisResult,
  ownerNodeId: string,
  ownerLabel: string,
) => {
  analysis.tables.forEach((table) => {
    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: ownerNodeId,
      label: table.source === "subquery" ? "서브쿼리 읽음" : "읽음",
      sourceStatementIds: [statementId],
      to: tableNodeIdFromAnalysisTable(table),
      type: "reads",
      warnings: table.source === "subquery"
        ? [`${ownerLabel}에서 서브쿼리 테이블로 탐지했습니다.`]
        : [],
    });
  });
};

const addJoinEdges = (
  edges: Map<string, SystemGraphEdge>,
  statementId: string,
  analysis: SqlAnalysisResult,
) => {
  const tableLookup = buildTableLookup(analysis);

  analysis.joins.forEach((join) => {
    const left = splitColumnRef(join.left);
    const right = splitColumnRef(join.right);

    if (!left || !right) {
      return;
    }

    const leftTable = tableLookup.get(left.tableName.toLowerCase());
    const rightTable = tableLookup.get(right.tableName.toLowerCase());
    const leftNodeId = leftTable ? tableNodeIdFromAnalysisTable(leftTable) : tableNodeId(left.tableName);
    const rightNodeId = rightTable ? tableNodeIdFromAnalysisTable(rightTable) : tableNodeId(right.tableName);

    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: leftNodeId,
      label: `${join.joinType ?? "JOIN"} ${left.columnName} = ${right.columnName}`,
      sourceStatementIds: [statementId],
      to: rightNodeId,
      type: "joins",
      warnings: [],
    });
  });
};

const addCteFlow = (
  nodes: Map<string, SystemGraphNode>,
  edges: Map<string, SystemGraphEdge>,
  statementId: string,
  analysis: SqlAnalysisResult,
) => {
  const cteNames = new Set(analysis.ctes.map((cte) => cte.name.toLowerCase()));
  const tableLookup = buildTableLookup(analysis);
  const sqlId = sqlNodeId(statementId);

  analysis.ctes.forEach((cte) => {
    const currentCteNodeId = cteNodeId(statementId, cte.name);

    addNode(nodes, {
      confidenceLevel: analysis.confidence.level,
      description: cte.role,
      id: currentCteNodeId,
      importance: "medium",
      label: cte.name,
      sourceStatementIds: [statementId],
      type: "cte",
      warnings: ["CTE 의존성은 정규식 기반으로 추정했습니다."],
    });

    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: sqlId,
      label: "CTE 사용",
      sourceStatementIds: [statementId],
      to: currentCteNodeId,
      type: "depends_on",
      warnings: [],
    });

    cte.dependencies.forEach((dependency) => {
      const normalizedDependency = dependency.toLowerCase();

      if (cteNames.has(normalizedDependency)) {
        addEdge(edges, {
          confidenceLevel: analysis.confidence.level,
          from: cteNodeId(statementId, dependency),
          label: "CTE 단계 흐름",
          sourceStatementIds: [statementId],
          to: currentCteNodeId,
          type: "depends_on",
          warnings: [],
        });
        return;
      }

      const table = tableLookup.get(normalizedDependency);

      if (table) {
        addEdge(edges, {
          confidenceLevel: analysis.confidence.level,
          from: tableNodeIdFromAnalysisTable(table),
          label: "CTE 입력",
          sourceStatementIds: [statementId],
          to: currentCteNodeId,
          type: "depends_on",
          warnings: [],
        });
      }
    });
  });
};

const addLoadFlow = (
  nodes: Map<string, SystemGraphNode>,
  edges: Map<string, SystemGraphEdge>,
  statementId: string,
  analysis: SqlAnalysisResult,
  insertTarget: ReturnType<typeof extractInsertTarget>,
) => {
  const targetNode = insertTargetNode(statementId, insertTarget);

  if (!targetNode) {
    return;
  }

  const sqlId = sqlNodeId(statementId);
  addNode(nodes, targetNode);

  addEdge(edges, {
    confidenceLevel: analysis.confidence.level,
    from: sqlId,
    label: "INSERT 대상",
    sourceStatementIds: [statementId],
    to: targetNode.id,
    type: "writes",
    warnings: [],
  });

  analysis.tables.forEach((table) => {
    const sourceNodeId = tableNodeIdFromAnalysisTable(table);

    if (sourceNodeId === targetNode.id) {
      return;
    }

    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: sourceNodeId,
      label: "INSERT INTO SELECT 적재 흐름",
      sourceStatementIds: [statementId],
      to: targetNode.id,
      type: "transforms_to",
      warnings: ["SELECT 결과를 INSERT 대상 테이블로 적재하는 흐름으로 추정했습니다."],
    });
  });
};

const addCreateObjectFlow = (
  nodes: Map<string, SystemGraphNode>,
  edges: Map<string, SystemGraphEdge>,
  statementId: string,
  analysis: SqlAnalysisResult,
  createObject: ReturnType<typeof extractCreateObject>,
) => {
  if (!createObject) {
    return;
  }

  const sqlId = sqlNodeId(statementId);
  const objectNodeId = createObject.type === "view"
    ? viewNodeId(createObject.objectName, createObject.schemaName)
    : procedureNodeId(createObject.objectName, createObject.schemaName);
  const objectLabel = createObject.objectName;

  addNode(nodes, {
    confidenceLevel: analysis.confidence.level,
    description: createObject.type === "view"
      ? "CREATE VIEW로 정의된 조회 객체"
      : "CREATE PROCEDURE/FUNCTION/PACKAGE로 감지된 실행 객체",
    id: objectNodeId,
    importance: createObject.type === "view" ? "medium" : "low",
    label: objectLabel,
    sourceStatementIds: [statementId],
    type: createObject.type,
    warnings: createObject.type === "procedure"
      ? ["Procedure 내부 SQL은 부분 분석이며 동적 SQL은 누락될 수 있습니다."]
      : [],
  });

  addEdge(edges, {
    confidenceLevel: analysis.confidence.level,
    from: sqlId,
    label: createObject.type === "view" ? "VIEW 정의" : "Procedure 정의",
    sourceStatementIds: [statementId],
    to: objectNodeId,
    type: "writes",
    warnings: [],
  });

  analysis.tables.forEach((table) => {
    const sourceNodeId = tableNodeIdFromAnalysisTable(table);

    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: objectNodeId,
      label: createObject.type === "view" ? "VIEW 테이블 의존" : "Procedure 테이블 의존",
      sourceStatementIds: [statementId],
      to: sourceNodeId,
      type: "depends_on",
      warnings: createObject.type === "procedure"
        ? ["Procedure 내부 SQL 의존성은 정규식 기반으로 추정했습니다."]
        : [],
    });

    addEdge(edges, {
      confidenceLevel: analysis.confidence.level,
      from: sourceNodeId,
      label: createObject.type === "view" ? "VIEW 소스" : "Procedure 입력 후보",
      sourceStatementIds: [statementId],
      to: objectNodeId,
      type: "transforms_to",
      warnings: [],
    });
  });
};

const sortedNodes = (nodes: SystemGraphNode[]) =>
  nodes.sort((left, right) => {
    const leftRank = left.importance ? importanceRank[left.importance] : 0;
    const rightRank = right.importance ? importanceRank[right.importance] : 0;

    if (rightRank !== leftRank) {
      return rightRank - leftRank;
    }

    if (left.type !== right.type) {
      return left.type.localeCompare(right.type);
    }

    return left.label.localeCompare(right.label);
  });

const sortedEdges = (edges: SystemGraphEdge[]) =>
  edges.sort((left, right) => {
    if (edgeTypeRank[left.type] !== edgeTypeRank[right.type]) {
      return edgeTypeRank[left.type] - edgeTypeRank[right.type];
    }

    return `${left.from} ${left.to}`.localeCompare(`${right.from} ${right.to}`);
  });

export const buildSystemGraph = (multiAnalysis: MultiSqlAnalysisResult): SystemGraph => {
  const nodes = new Map<string, SystemGraphNode>();
  const edges = new Map<string, SystemGraphEdge>();
  const warnings: string[] = [];

  multiAnalysis.statements.forEach((statement) => {
    const analysis = statement.analysis;

    if (!analysis) {
      warnings.push(`${statement.id}: 분석 실패 SQL은 시스템 지도에서 제외했습니다.`);
      return;
    }

    const sqlId = sqlNodeId(statement.id);
    const createObject = extractCreateObject(statement.sql);
    const insertTarget = extractInsertTarget(statement.sql);

    addNode(nodes, statementNode(statement.id, analysis, statement.warnings));

    if (analysis.setOperations.length > 0) {
      warnings.push(`${statement.id}: SET 연산 SQL은 SELECT 블록별 세부 의존성이 단순화될 수 있습니다.`);
    }

    analysis.tables.forEach((table) => {
      addNode(nodes, tableNode(statement.id, table, table.source === "subquery" ? "low" : "medium"));
    });

    addReadEdges(edges, statement.id, analysis, sqlId, statement.id);
    addJoinEdges(edges, statement.id, analysis);
    addCteFlow(nodes, edges, statement.id, analysis);
    addLoadFlow(nodes, edges, statement.id, analysis, insertTarget);
    addCreateObjectFlow(nodes, edges, statement.id, analysis, createObject);
  });

  const graphNodes = sortedNodes(Array.from(nodes.values()).map((node) => ({
    ...node,
    sourceStatementIds: unique(node.sourceStatementIds),
    warnings: unique(node.warnings),
  })));
  const graphEdges = sortedEdges(Array.from(edges.values()).map((edge) => ({
    ...edge,
    sourceStatementIds: unique(edge.sourceStatementIds),
    warnings: unique(edge.warnings),
  })));
  const graphWarnings = unique([
    ...warnings,
    ...graphNodes.flatMap((node) => node.warnings.map((warning) => `${node.label}: ${warning}`)),
    ...graphEdges.flatMap((edge) => edge.warnings.map((warning) => `${edge.label}: ${warning}`)),
  ]);

  return {
    edges: graphEdges,
    nodes: graphNodes,
    summary: {
      cteNodeCount: graphNodes.filter((node) => node.type === "cte").length,
      edgeCount: graphEdges.length,
      joinRelationCount: graphEdges.filter((edge) => edge.type === "joins").length,
      loadFlowCount: graphEdges.filter((edge) => ["transforms_to", "writes"].includes(edge.type)).length,
      nodeCount: graphNodes.length,
      procedureNodeCount: graphNodes.filter((node) => node.type === "procedure").length,
      readDependencyCount: graphEdges.filter((edge) => edge.type === "reads").length,
      sqlNodeCount: graphNodes.filter((node) => node.type === "sql").length,
      tableNodeCount: graphNodes.filter((node) => node.type === "table").length,
      viewNodeCount: graphNodes.filter((node) => node.type === "view").length,
      warningCount: graphWarnings.length,
    },
    warnings: graphWarnings,
  };
};

const viewConfig: Record<SystemGraphMode, Omit<SystemGraphView, "nodes" | "edges" | "warnings">> = {
  cte_flow: {
    description: "CTE 단계와 CTE가 의존하는 테이블/이전 CTE를 보여줍니다.",
    mode: "cte_flow",
    title: "CTE 처리 흐름",
  },
  load_flow: {
    description: "INSERT INTO SELECT와 View 정의처럼 원천 데이터가 결과 객체로 이동하는 흐름입니다.",
    mode: "load_flow",
    title: "적재/변환 흐름",
  },
  overview: {
    description: "SQL, 테이블, CTE, View, Procedure 사이의 주요 연결을 함께 보여줍니다.",
    mode: "overview",
    title: "전체 시스템 지도",
  },
  sql_dependencies: {
    description: "각 SQL이 어떤 테이블을 읽고 어떤 테이블이나 View를 쓰는지 보여줍니다.",
    mode: "sql_dependencies",
    title: "SQL 의존성",
  },
  table_relations: {
    description: "JOIN과 적재 흐름을 기준으로 테이블 사이 관계를 보여줍니다.",
    mode: "table_relations",
    title: "테이블 관계",
  },
};

const edgeMatchesMode = (edge: SystemGraphEdge, mode: SystemGraphMode, nodes: Map<string, SystemGraphNode>) => {
  if (mode === "overview") {
    return true;
  }

  if (mode === "table_relations") {
    return edge.type === "joins" || edge.type === "transforms_to";
  }

  if (mode === "sql_dependencies") {
    return edge.type === "reads" || edge.type === "writes";
  }

  if (mode === "load_flow") {
    return edge.type === "writes" || edge.type === "transforms_to";
  }

  const fromNode = nodes.get(edge.from);
  const toNode = nodes.get(edge.to);

  return (
    mode === "cte_flow" &&
    (fromNode?.type === "cte" || toNode?.type === "cte") &&
    (edge.type === "depends_on" || edge.type === "reads" || edge.type === "transforms_to")
  );
};

export const getSystemGraphView = (
  graph: SystemGraph,
  mode: SystemGraphMode,
): SystemGraphView => {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const edges = graph.edges.filter((edge) => edgeMatchesMode(edge, mode, nodesById));
  const nodeIds = new Set(edges.flatMap((edge) => [edge.from, edge.to]));
  const nodes = graph.nodes.filter((node) => nodeIds.has(node.id));
  const visibleLabels = new Set([
    ...nodes.map((node) => node.label),
    ...edges.flatMap((edge) => [edge.label, ...edge.sourceStatementIds]),
  ]);
  const warnings = mode === "overview"
    ? graph.warnings
    : graph.warnings.filter((warning) =>
      Array.from(visibleLabels).some((label) => warning.includes(label)),
    );

  return {
    ...viewConfig[mode],
    edges,
    nodes,
    warnings,
  };
};

const downstreamNeighbor = (edge: SystemGraphEdge, nodeId: string) => {
  if (
    edge.from === nodeId &&
    ["calls", "joins", "transforms_to", "writes"].includes(edge.type)
  ) {
    return edge.to;
  }

  if (
    edge.to === nodeId &&
    ["depends_on", "filters", "joins", "reads"].includes(edge.type)
  ) {
    return edge.from;
  }

  return undefined;
};

const upstreamNeighbor = (edge: SystemGraphEdge, nodeId: string) => {
  if (
    edge.from === nodeId &&
    ["depends_on", "filters", "joins", "reads"].includes(edge.type)
  ) {
    return edge.to;
  }

  if (
    edge.to === nodeId &&
    ["joins", "transforms_to", "writes"].includes(edge.type)
  ) {
    return edge.from;
  }

  return undefined;
};

const traverseImpact = (
  graph: SystemGraph,
  nodeId: string,
  direction: Exclude<ImpactDirection, "both">,
  maxDepth: number,
) => {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const visited = new Set([nodeId]);
  const queue: Array<{ depth: number; nodeId: string }> = [{ depth: 0, nodeId }];
  const result: ImpactNode[] = [];

  while (queue.length > 0) {
    const current = queue.shift();

    if (!current || current.depth >= maxDepth) {
      continue;
    }

    graph.edges.forEach((edge) => {
      const nextNodeId = direction === "downstream"
        ? downstreamNeighbor(edge, current.nodeId)
        : upstreamNeighbor(edge, current.nodeId);

      if (!nextNodeId || visited.has(nextNodeId)) {
        return;
      }

      const node = nodesById.get(nextNodeId);

      if (!node) {
        return;
      }

      visited.add(nextNodeId);
      result.push({
        depth: current.depth + 1,
        label: node.label,
        nodeId: node.id,
        type: node.type,
        viaEdgeId: edge.id,
        viaEdgeLabel: `${edgeTypeLabel[edge.type]}: ${edge.label}`,
      });
      queue.push({ depth: current.depth + 1, nodeId: nextNodeId });
    });
  }

  return result.sort((left, right) => {
    if (left.depth !== right.depth) {
      return left.depth - right.depth;
    }

    return left.label.localeCompare(right.label);
  });
};

export const analyzeImpact = (
  graph: SystemGraph,
  nodeId: string,
  options: {
    direction?: ImpactDirection;
    maxDepth?: number;
  } = {},
): ImpactAnalysisResult => {
  const node = graph.nodes.find((candidate) => candidate.id === nodeId);
  const direction = options.direction ?? "both";
  const maxDepth = options.maxDepth ?? 3;

  if (!node) {
    return {
      downstream: [],
      upstream: [],
      warnings: [`${nodeId} 노드를 시스템 지도에서 찾지 못했습니다.`],
    };
  }

  const upstream = direction === "downstream"
    ? []
    : traverseImpact(graph, nodeId, "upstream", maxDepth);
  const downstream = direction === "upstream"
    ? []
    : traverseImpact(graph, nodeId, "downstream", maxDepth);

  return {
    downstream,
    node,
    upstream,
    warnings: unique([
      ...node.warnings,
      ...(upstream.length + downstream.length === 0
        ? ["선택 노드와 연결된 영향 관계가 충분히 탐지되지 않았습니다."]
        : []),
    ]),
  };
};

const nodeLabel = (node: SystemGraphNode | undefined) =>
  node ? `${node.label} (${nodeTypeLabel[node.type]})` : "알 수 없는 노드";

const edgeLine = (edge: SystemGraphEdge, nodesById: Map<string, SystemGraphNode>) =>
  `- ${nodeLabel(nodesById.get(edge.from))} -> ${nodeLabel(nodesById.get(edge.to))}: ${edgeTypeLabel[edge.type]} / ${edge.label} / SQL ${edge.sourceStatementIds.join(", ")}`;

export const buildSystemGraphMarkdownSection = (graph: SystemGraph) => {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const sqlDependencyEdges = graph.edges.filter((edge) => edge.type === "reads" || edge.type === "writes");
  const tableRelationEdges = graph.edges.filter((edge) => edge.type === "joins");
  const cteFlowEdges = graph.edges.filter((edge) => {
    const fromNode = nodesById.get(edge.from);
    const toNode = nodesById.get(edge.to);
    return fromNode?.type === "cte" || toNode?.type === "cte";
  });
  const loadFlowEdges = graph.edges.filter((edge) => edge.type === "writes" || edge.type === "transforms_to");

  return [
    "## 시스템 의존성 지도",
    "",
    "### 요약",
    `- 노드: ${graph.summary.nodeCount}개`,
    `- 연결: ${graph.summary.edgeCount}개`,
    `- 테이블: ${graph.summary.tableNodeCount}개`,
    `- SQL: ${graph.summary.sqlNodeCount}개`,
    `- CTE: ${graph.summary.cteNodeCount}개`,
    `- View: ${graph.summary.viewNodeCount}개`,
    `- Procedure: ${graph.summary.procedureNodeCount}개`,
    `- 적재/변환 흐름: ${graph.summary.loadFlowCount}개`,
    "",
    "### SQL 의존성",
    ...(sqlDependencyEdges.length > 0
      ? sqlDependencyEdges.slice(0, 20).map((edge) => edgeLine(edge, nodesById))
      : ["- SQL 의존성을 찾지 못했습니다."]),
    "",
    "### 테이블 관계",
    ...(tableRelationEdges.length > 0
      ? tableRelationEdges.slice(0, 20).map((edge) => edgeLine(edge, nodesById))
      : ["- 테이블 간 JOIN 관계를 찾지 못했습니다."]),
    "",
    "### CTE 처리 흐름",
    ...(cteFlowEdges.length > 0
      ? cteFlowEdges.slice(0, 20).map((edge) => edgeLine(edge, nodesById))
      : ["- CTE 처리 흐름이 없습니다."]),
    "",
    "### 적재/변환 흐름",
    ...(loadFlowEdges.length > 0
      ? loadFlowEdges.slice(0, 20).map((edge) => edgeLine(edge, nodesById))
      : ["- INSERT INTO SELECT 또는 View 적재 흐름을 찾지 못했습니다."]),
    "",
    "### 주의 사항",
    ...(graph.warnings.length > 0
      ? graph.warnings.slice(0, 20).map((warning) => `- ${warning}`)
      : ["- 별도 주의 사항이 없습니다."]),
  ].join("\n");
};
