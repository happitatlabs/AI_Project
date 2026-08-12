import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const source = fs.readFileSync(path.resolve("src/sqlExplainer.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`;
const { analyzeSql, explainSql } = await import(moduleUrl);

const maskingSource = fs.readFileSync(path.resolve("src/sqlMasking.ts"), "utf8");
const compiledMasking = ts.transpileModule(maskingSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
});
const maskingModuleUrl = `data:text/javascript;base64,${Buffer.from(compiledMasking.outputText).toString("base64")}`;
const { maskSensitiveSql, maskSensitiveText } = await import(maskingModuleUrl);

const compileTsFile = (inputPath, outputPath) => {
  const input = fs.readFileSync(path.resolve(inputPath), "utf8");
  const compiledOutput = ts.transpileModule(input, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020,
    },
  });

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, compiledOutput.outputText, "utf8");
};

const tempModuleRoot = fs.mkdtempSync(path.join(os.tmpdir(), "sql-explainer-ai-"));
compileTsFile("src/sqlExplainer.ts", path.join(tempModuleRoot, "src/sqlExplainer.js"));
compileTsFile("src/sqlMasking.ts", path.join(tempModuleRoot, "src/sqlMasking.js"));
compileTsFile("src/computedAnalysis.ts", path.join(tempModuleRoot, "src/computedAnalysis.js"));
compileTsFile("src/aiDataInsights.ts", path.join(tempModuleRoot, "src/aiDataInsights.js"));
compileTsFile("src/aiDataInsightsState.ts", path.join(tempModuleRoot, "src/aiDataInsightsState.js"));
compileTsFile("src/dataInsightReport.ts", path.join(tempModuleRoot, "src/dataInsightReport.js"));
compileTsFile("src/aiExplanation.ts", path.join(tempModuleRoot, "src/aiExplanation.js"));
compileTsFile("src/aiDocumentDraft.ts", path.join(tempModuleRoot, "src/aiDocumentDraft.js"));
compileTsFile("src/aiMultiDocumentDraft.ts", path.join(tempModuleRoot, "src/aiMultiDocumentDraft.js"));
compileTsFile("src/aiExplanationState.ts", path.join(tempModuleRoot, "src/aiExplanationState.js"));
compileTsFile("src/multiSqlAnalysis.ts", path.join(tempModuleRoot, "src/multiSqlAnalysis.js"));
compileTsFile("src/multiAiExplanation.ts", path.join(tempModuleRoot, "src/multiAiExplanation.js"));
compileTsFile("src/tableAssetMap.ts", path.join(tempModuleRoot, "src/tableAssetMap.js"));
compileTsFile("src/systemGraph.ts", path.join(tempModuleRoot, "src/systemGraph.js"));
compileTsFile("src/riskDetector.ts", path.join(tempModuleRoot, "src/riskDetector.js"));
compileTsFile("src/diagnosticNarrative.ts", path.join(tempModuleRoot, "src/diagnosticNarrative.js"));
compileTsFile("src/reportModel.ts", path.join(tempModuleRoot, "src/reportModel.js"));
compileTsFile("api/ai-provider.ts", path.join(tempModuleRoot, "api/ai-provider.js"));
compileTsFile("api/ai-explain.ts", path.join(tempModuleRoot, "api/ai-explain.js"));
compileTsFile("api/ai-document-draft.ts", path.join(tempModuleRoot, "api/ai-document-draft.js"));
compileTsFile("api/ai-multi-document-draft.ts", path.join(tempModuleRoot, "api/ai-multi-document-draft.js"));
compileTsFile("api/ai-data-insights.ts", path.join(tempModuleRoot, "api/ai-data-insights.js"));
compileTsFile("src/cloudflareWorker.ts", path.join(tempModuleRoot, "src/cloudflareWorker.js"));

const { buildAiSqlExplanationPayload } = await import(
  pathToFileURL(path.join(tempModuleRoot, "src/aiExplanation.js")).href
);
const {
  COMPUTED_ANALYSIS_CONTRACT_VERSION,
  calculateComputedAnalysis,
  inspectDataInput,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/computedAnalysis.js")).href);
const {
  buildAiDataInsightsPayload,
  normalizeAiDataInsights,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/aiDataInsights.js")).href);
const {
  buildDataInsightMarkdownReport,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/dataInsightReport.js")).href);
const {
  buildAiSqlDocumentDraftPayload,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/aiDocumentDraft.js")).href);
const {
  buildAiMultiSqlDocumentDraftPayload,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/aiMultiDocumentDraft.js")).href);
const { preserveAnalysisWithAiError } = await import(
  pathToFileURL(path.join(tempModuleRoot, "src/aiExplanationState.js")).href
);
const { handleAiExplainRequest } = await import(
  pathToFileURL(path.join(tempModuleRoot, "api/ai-explain.js")).href
);
const { handleAiDocumentDraftRequest } = await import(
  pathToFileURL(path.join(tempModuleRoot, "api/ai-document-draft.js")).href
);
const { handleAiMultiDocumentDraftRequest } = await import(
  pathToFileURL(path.join(tempModuleRoot, "api/ai-multi-document-draft.js")).href
);
const { handleAiDataInsightsRequest } = await import(
  pathToFileURL(path.join(tempModuleRoot, "api/ai-data-insights.js")).href
);
const { default: cloudflareWorker } = await import(
  pathToFileURL(path.join(tempModuleRoot, "src/cloudflareWorker.js")).href
);
const {
  analyzeMultipleSql,
  buildMultiSqlMarkdownReport,
  normalizeConditionPattern,
  splitSqlStatements,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/multiSqlAnalysis.js")).href);
const { buildMultiSqlAiAnalysis } = await import(
  pathToFileURL(path.join(tempModuleRoot, "src/multiAiExplanation.js")).href
);
const {
  buildTableAssetMap,
  buildTableAssetMapMarkdownSection,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/tableAssetMap.js")).href);
const {
  analyzeImpact,
  buildSystemGraph,
  buildSystemGraphMarkdownSection,
  getSystemGraphView,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/systemGraph.js")).href);
const { analyzeSqlRisks } = await import(
  pathToFileURL(path.join(tempModuleRoot, "src/riskDetector.js")).href
);
const {
  buildMultiSqlNarrative,
  buildSingleSqlNarrative,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/diagnosticNarrative.js")).href);
const {
  buildMarkdownReport,
  buildPasteDocument,
  buildPrintableHtmlReport,
  buildRiskFindingsCsv,
  buildSqlExplainerReport,
  buildTableUsageCsv,
  defaultReportOptions,
} = await import(pathToFileURL(path.join(tempModuleRoot, "src/reportModel.js")).href);

const normalize = (value) => String(value).replace(/\s+/g, " ").trim();

const readFixture = (name) =>
  fs.readFileSync(path.resolve("tests/fixtures", name), "utf8");

const renderExplanationText = (analysis) =>
  normalize(
    [
      analysis.summary,
      analysis.developerExplanation,
      analysis.finalResult,
      `${analysis.confidence.level} ${analysis.confidence.score}`,
      ...analysis.confidence.reasons,
      ...analysis.tables.map((table) => `${table.rawName} ${table.schemaName ?? ""} ${table.tableName} ${table.source ?? ""} ${table.description}`),
      ...analysis.joins.map((join) => `${join.raw} ${join.explanation ?? ""}`),
      ...analysis.ctes.map((cte) => `${cte.name} ${cte.role}`),
      ...analysis.filters.map((filter) => `${filter.stage} ${filter.condition} ${filter.description}`),
      ...analysis.havingConditions.map((filter) => `${filter.stage} HAVING ${filter.condition} ${filter.description}`),
      ...analysis.groupBy.map((group) => `${group.stage} GROUP BY ${group.columns.join(", ")} ${group.description}`),
      ...analysis.aggregations.map((aggregation) => `${aggregation.stage} ${aggregation.functionName} ${aggregation.alias ?? ""} ${aggregation.description}`),
      ...analysis.windowFunctions.map((windowFunction) => `${windowFunction.stage} ${windowFunction.functionName} ${windowFunction.alias ?? ""} ${windowFunction.description}`),
      ...analysis.caseExpressions.flatMap((caseExpression) => [
        `${caseExpression.stage} ${caseExpression.alias ?? ""} ${caseExpression.description}`,
        ...caseExpression.rules,
      ]),
      ...analysis.derivedColumns.map((column) => `${column.alias} ${column.description}`),
      ...analysis.subqueries.map((subquery) => `${subquery.type} ${subquery.description} ${subquery.tables.join(", ")}`),
      ...analysis.setOperations.map((operation) => `${operation.operator} ${operation.description}`),
      ...analysis.advancedFeatures.map((feature) => `${feature.type} ${feature.evidence} ${feature.dialect ?? ""} ${feature.description}`),
      ...analysis.businessGuesses,
      ...analysis.notes,
      ...analysis.warnings,
    ].join("\n"),
  );

const assertIncludesAll = (text, keywords) => {
  for (const keyword of keywords) {
    assert.match(text, new RegExp(keyword), `Expected explanation to include: ${keyword}`);
  }
};

const assertIncludesNone = (text, keywords) => {
  for (const keyword of keywords) {
    assert.doesNotMatch(text, new RegExp(keyword), `Expected explanation not to include: ${keyword}`);
  }
};

const assertIntentIn = (analysis, expectedTypes) => {
  assert.ok(
    expectedTypes.includes(analysis.businessIntent.type),
    `Expected intent ${analysis.businessIntent.type} to be one of ${expectedTypes.join(", ")}`,
  );
};

const findCte = (analysis, name) =>
  analysis.ctes.find((cte) => cte.name.toLowerCase() === name.toLowerCase());

const stageItems = (items, stage) =>
  items.filter((item) => item.stage.toLowerCase() === stage.toLowerCase());

const maskedSql = maskSensitiveSql(`SELECT customer_id, customer_email, phone, api_token, request_uuid
FROM customers
WHERE customer_email = 'abc@example.com'
  AND phone = '010-1234-5678'
  AND request_uuid = '550e8400-e29b-41d4-a716-446655440000'
  AND api_token = 'sk_test_abcdefghijklmnopqrstuvwxyz123456'
  AND customer_id = 123456789012345
  AND status = 'PAID';`);
const normalizedMaskedSql = normalize(maskedSql);

assert.match(normalizedMaskedSql, /customer_email = '\[REDACTED_EMAIL\]'/);
assert.match(normalizedMaskedSql, /phone = '\[REDACTED_PHONE\]'/);
assert.match(normalizedMaskedSql, /request_uuid = '\[REDACTED_UUID\]'/);
assert.match(normalizedMaskedSql, /api_token = '\[REDACTED_TOKEN\]'/);
assert.match(normalizedMaskedSql, /customer_id = \[REDACTED_NUMBER\]/);
assert.match(normalizedMaskedSql, /SELECT customer_id, customer_email, phone, api_token, request_uuid FROM customers WHERE/);
assert.match(normalizedMaskedSql, /status = 'PAID'/);

const fallbackMaskedSql = maskSensitiveSql(`SELECT * FROM users WHERE password = 'plain-secret';`);
assert.match(fallbackMaskedSql, /password = '\[REDACTED_VALUE\]'/);
assert.equal(
  maskSensitiveText("alice@example.com / 010-1234-5678 / 12345678-1234-4123-8123-123456789abc"),
  "[REDACTED_EMAIL] / [REDACTED_PHONE] / [REDACTED_UUID]",
);

const sensitiveAnalysisSql = `SELECT customer_email, phone
FROM customers
WHERE customer_email = 'abc@example.com'
  AND phone = '010-1234-5678'
  AND api_token = 'sk_test_abcdefghijklmnopqrstuvwxyz123456';`;
const sensitiveAnalysis = analyzeSql(sensitiveAnalysisSql);
const aiPayload = buildAiSqlExplanationPayload(sensitiveAnalysisSql, sensitiveAnalysis);
const serializedPayload = JSON.stringify(aiPayload);

assert.match(aiPayload.maskedSql, /\[REDACTED_EMAIL\]/);
assert.match(aiPayload.maskedSql, /\[REDACTED_PHONE\]/);
assert.match(aiPayload.maskedSql, /\[REDACTED_TOKEN\]/);
assert.doesNotMatch(serializedPayload, /abc@example\.com/);
assert.doesNotMatch(serializedPayload, /010-1234-5678/);
assert.doesNotMatch(serializedPayload, /sk_test_abcdefghijklmnopqrstuvwxyz123456/);
assert.match(aiPayload.instructions, /분석 결과에 없는 사실을 단정하지 마라/);
assert.match(aiPayload.instructions, /uncertaintyNotes/);

const missingKeyResult = await handleAiExplainRequest(
  { analysis: sensitiveAnalysis, sql: sensitiveAnalysisSql },
  {
    env: {},
    fetcher: async () => {
      throw new Error("fetch should not be called without API key");
    },
  },
);
assert.equal(missingKeyResult.status, 500);
assert.match(missingKeyResult.body.error, /OPENAI_API_KEY/);

let sentOpenAiRequest = "";
const mockRouteResult = await handleAiExplainRequest(
  { analysis: sensitiveAnalysis, sql: sensitiveAnalysisSql },
  {
    env: {
      OPENAI_API_KEY: "test-key",
      OPENAI_MODEL: "test-model",
    },
    fetcher: async (_url, init) => {
      sentOpenAiRequest = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          output_text: JSON.stringify({
            summary: "마스킹된 SQL을 기반으로 고객 연락처 조건을 설명합니다.",
            dataFlowExplanation: "customers 테이블에서 조건에 맞는 데이터를 조회합니다.",
            businessPurpose: "고객 정보 확인 목적의 조회로 추정됩니다.",
            juniorDeveloperExplanation: "WHERE 조건으로 이메일과 전화번호 조건을 적용합니다.",
            performanceNotes: ["조건 컬럼 인덱스가 있으면 조회 비용이 줄 수 있습니다."],
            riskNotes: ["마스킹 후에도 컬럼명은 전달됩니다."],
            refactoringSuggestions: ["필요 컬럼만 명시하는 방식을 유지합니다."],
            uncertaintyNotes: ["실제 업무 목적은 테이블명 기준 추정입니다."],
          }),
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockRouteResult.status, 200);
assert.equal(mockRouteResult.body.explanation.summary, "마스킹된 SQL을 기반으로 고객 연락처 조건을 설명합니다.");
assert.match(sentOpenAiRequest, /\[REDACTED_EMAIL\]/);
assert.match(sentOpenAiRequest, /\[REDACTED_PHONE\]/);
assert.doesNotMatch(sentOpenAiRequest, /abc@example\.com/);
assert.doesNotMatch(sentOpenAiRequest, /010-1234-5678/);

let sentOllamaUrl = "";
let sentOllamaRequest = "";
const mockOllamaResult = await handleAiExplainRequest(
  { analysis: sensitiveAnalysis, sql: sensitiveAnalysisSql },
  {
    env: {
      AI_MODEL: "llama3.1",
      AI_PROVIDER: "ollama",
    },
    fetcher: async (url, init) => {
      sentOllamaUrl = String(url);
      sentOllamaRequest = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          done: true,
          message: {
            content: `\`\`\`json
${JSON.stringify({
  summary: "Ollama가 마스킹된 SQL을 설명합니다.",
  dataFlowExplanation: "customers 테이블 조건을 기준으로 데이터를 조회합니다.",
  businessPurpose: "고객 조건 조회로 추정됩니다.",
  juniorDeveloperExplanation: "민감 값은 마스킹된 상태로 설명합니다.",
  performanceNotes: [],
  riskNotes: ["컬럼명은 AI 요청에 포함될 수 있습니다."],
  refactoringSuggestions: [],
  uncertaintyNotes: ["실제 업무 맥락은 SQL만으로 단정하지 않습니다."],
})}
\`\`\``,
            role: "assistant",
          },
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockOllamaResult.status, 200);
assert.equal(mockOllamaResult.body.explanation.summary, "Ollama가 마스킹된 SQL을 설명합니다.");
assert.equal(sentOllamaUrl, "http://localhost:11434/api/chat");
const sentOllamaBody = JSON.parse(sentOllamaRequest);
assert.equal(sentOllamaBody.model, "llama3.1");
assert.equal(sentOllamaBody.stream, false);
assert.equal(sentOllamaBody.format.type, "object");
assert.match(sentOllamaRequest, /\[REDACTED_EMAIL\]/);
assert.doesNotMatch(sentOllamaRequest, /abc@example\.com/);

let sentAzureUrl = "";
let sentAzureRequest = "";
let sentAzureHeaders = {};
const mockAzureResult = await handleAiExplainRequest(
  { analysis: sensitiveAnalysis, sql: sensitiveAnalysisSql },
  {
    env: {
      AI_PROVIDER: "azure_openai",
      AZURE_OPENAI_API_KEY: "azure-test-key",
      AZURE_OPENAI_ENDPOINT: "https://example-resource.openai.azure.com",
      AZURE_OPENAI_MODEL: "sql-explainer-deployment",
    },
    fetcher: async (url, init) => {
      sentAzureUrl = String(url);
      sentAzureRequest = String(init?.body ?? "");
      sentAzureHeaders = init?.headers ?? {};
      return new Response(
        JSON.stringify({
          output_text: JSON.stringify({
            summary: "Azure OpenAI가 마스킹된 SQL을 설명합니다.",
            dataFlowExplanation: "룰 기반 분석 결과를 우선해 흐름을 설명합니다.",
            businessPurpose: "고객 조건 조회로 추정됩니다.",
            juniorDeveloperExplanation: "SQL 구조를 신규 개발자 관점으로 풀어 설명합니다.",
            performanceNotes: [],
            riskNotes: [],
            refactoringSuggestions: [],
            uncertaintyNotes: [],
          }),
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockAzureResult.status, 200);
assert.equal(mockAzureResult.body.explanation.summary, "Azure OpenAI가 마스킹된 SQL을 설명합니다.");
assert.equal(sentAzureUrl, "https://example-resource.openai.azure.com/openai/v1/responses");
assert.equal(sentAzureHeaders["api-key"], "azure-test-key");
const sentAzureBody = JSON.parse(sentAzureRequest);
assert.equal(sentAzureBody.model, "sql-explainer-deployment");
assert.match(sentAzureRequest, /\[REDACTED_PHONE\]/);
assert.doesNotMatch(sentAzureRequest, /010-1234-5678/);

const onboardingDraftPayload = buildAiSqlDocumentDraftPayload(
  sensitiveAnalysisSql,
  sensitiveAnalysis,
  "onboarding",
);
const operationDraftPayload = buildAiSqlDocumentDraftPayload(
  sensitiveAnalysisSql,
  sensitiveAnalysis,
  "operation",
);
const serializedDraftPayload = JSON.stringify(onboardingDraftPayload);
assert.equal(onboardingDraftPayload.documentType, "onboarding");
assert.match(onboardingDraftPayload.maskedSql, /\[REDACTED_EMAIL\]/);
assert.match(onboardingDraftPayload.maskedSql, /\[REDACTED_PHONE\]/);
assert.doesNotMatch(serializedDraftPayload, /abc@example\.com/);
assert.match(onboardingDraftPayload.instructions, /신규 개발자 온보딩 문서/);
assert.match(operationDraftPayload.instructions, /운영\/장애 점검 문서/);
assert.notEqual(onboardingDraftPayload.instructions, operationDraftPayload.instructions);

const missingOllamaModelDraftResult = await handleAiDocumentDraftRequest(
  { analysis: sensitiveAnalysis, documentType: "onboarding", sql: sensitiveAnalysisSql },
  {
    env: {
      AI_PROVIDER: "ollama",
    },
    fetcher: async () => {
      throw new Error("fetch should not be called without model");
    },
  },
);
assert.equal(missingOllamaModelDraftResult.status, 500);
assert.match(missingOllamaModelDraftResult.body.error, /OLLAMA_MODEL|AI_MODEL/);

let sentDocumentDraftUrl = "";
let sentDocumentDraftRequest = "";
const mockDocumentDraftResult = await handleAiDocumentDraftRequest(
  { analysis: sensitiveAnalysis, documentType: "refactoring", sql: sensitiveAnalysisSql },
  {
    env: {
      AI_MODEL: "qwen3:14b",
      AI_PROVIDER: "ollama",
    },
    fetcher: async (url, init) => {
      sentDocumentDraftUrl = String(url);
      sentDocumentDraftRequest = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          done: true,
          message: {
            content: JSON.stringify({
              businessContext: "고객 연락처 조건 조회로 추정됩니다.",
              dataFlow: "customers 테이블에서 조건을 적용해 결과를 조회합니다.",
              keyConditions: ["customer_email = [REDACTED_EMAIL]", "phone = [REDACTED_PHONE]"],
              keyTables: ["customers"],
              markdown: "# 고객 연락처 조건 SQL 문서\n\n## 개요\n마스킹된 조건을 기준으로 설명합니다.",
              onboardingNotes: "민감 값은 마스킹된 상태로 확인합니다.",
              overview: "고객 연락처 조건을 포함한 SQL 문서 초안입니다.",
              refactoringSuggestions: ["민감 조건 사용 시 접근 권한을 확인합니다."],
              risks: ["컬럼명은 AI 요청에 포함될 수 있습니다."],
              targetAudience: "신규 개발자 및 유지보수 담당자",
              title: "고객 연락처 조건 SQL 문서",
              uncertaintyNotes: ["실제 업무 목적은 SQL만으로 단정하지 않습니다."],
            }),
            role: "assistant",
          },
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockDocumentDraftResult.status, 200);
assert.equal(mockDocumentDraftResult.body.draft.title, "고객 연락처 조건 SQL 문서");
assert.match(mockDocumentDraftResult.body.draft.markdown, /고객 연락처 조건 SQL 문서/);
assert.equal(sentDocumentDraftUrl, "http://localhost:11434/api/chat");
const sentDocumentDraftBody = JSON.parse(sentDocumentDraftRequest);
assert.equal(sentDocumentDraftBody.model, "qwen3:14b");
assert.equal(sentDocumentDraftBody.format.type, "object");
assert.match(sentDocumentDraftRequest, /refactoring/);
assert.match(sentDocumentDraftRequest, /\[REDACTED_EMAIL\]/);
assert.doesNotMatch(sentDocumentDraftRequest, /abc@example\.com/);

const preservedAnalysis = preserveAnalysisWithAiError(sensitiveAnalysis, "AI failed");
assert.equal(preservedAnalysis.analysis, sensitiveAnalysis);
assert.equal(preservedAnalysis.aiState.status, "error");
assert.equal(preservedAnalysis.aiState.errorMessage, "AI failed");
const narrativeAfterAiError = buildSingleSqlNarrative(
  sensitiveAnalysisSql,
  preservedAnalysis.analysis,
);
assert.ok(narrativeAfterAiError.keyFindings.length > 0);
assert.ok(narrativeAfterAiError.nextQuestions.length > 0);

const splitInput = `SELECT 'value;still literal' AS memo FROM orders;
-- SELECT * FROM fake_table; this semicolon is a comment
SELECT customer_id FROM customers WHERE memo = 'a;b';
/* block comment; with fake SQL; */
INSERT INTO audit_orders SELECT order_id FROM orders WHERE order_id = 123456789012;`;
const splitStatements = splitSqlStatements(splitInput);
assert.equal(splitStatements.length, 3);
assert.match(splitStatements[0], /value;still literal/);
assert.match(splitStatements[1], /fake_table/);
assert.match(splitStatements[1], /memo = 'a;b'/);
assert.match(splitStatements[2], /block comment; with fake SQL/);
assert.equal(normalizeConditionPattern("o.status = 'PAID'"), "o.status = ?");
assert.equal(normalizeConditionPattern("o.customer_id = 123456789012"), "o.customer_id = ?");

const routineStatements = splitSqlStatements(readFixture("refresh-monthly-snapshot-procedure.sql"));
assert.equal(routineStatements.length, 1);
assert.match(routineStatements[0], /CREATE PROCEDURE refresh_monthly_order_snapshot/i);
assert.match(routineStatements[0], /INSERT INTO monthly_order_snapshot/i);

const multiFixtureInput = [
  readFixture("simple-order-list.sql"),
  readFixture("product-sales-summary.sql"),
  readFixture("insert-select-batch.sql"),
  readFixture("union-orders.sql"),
].join("\n\n");
const multiAnalysis = analyzeMultipleSql(multiFixtureInput);
assert.equal(multiAnalysis.statements.length, 4);
assert.equal(multiAnalysis.businessIntentSummary.order_list, 1);
assert.equal(multiAnalysis.businessIntentSummary.sales_summary, 1);
assert.equal(multiAnalysis.businessIntentSummary.batch_etl, 1);
assert.equal(multiAnalysis.businessIntentSummary.combined_result, 1);
assert.ok(multiAnalysis.tableUsage.some((table) => table.tableName === "orders" && table.count >= 2));
assert.ok(multiAnalysis.tableUsage.some((table) => table.tableName === "order_items"));
assert.ok(multiAnalysis.joinUsage.some((join) => /orders\.customer_id|customers\.customer_id/i.test(`${join.left} ${join.right}`)));
assert.ok(multiAnalysis.conditionUsage.some((condition) => /status/i.test(condition.normalizedCondition)));
const multiReport = buildMultiSqlMarkdownReport(multiAnalysis);
assert.match(multiReport, /다건 SQL 분석 보고서/);
assert.match(multiReport, /orders/);
assert.match(multiReport, /batch_etl/);

const multiAiAnalysis = buildMultiSqlAiAnalysis(multiAnalysis, analyzeSqlRisks(multiAnalysis));
const multiAiPayload = buildAiSqlExplanationPayload(
  `${multiFixtureInput}\n\nSELECT * FROM customers WHERE email = 'abc@example.com';`,
  multiAiAnalysis,
);
const serializedMultiAiPayload = JSON.stringify(multiAiPayload);
assert.match(multiAiPayload.instructions, /multiSqlContext/);
assert.equal(multiAiPayload.analysis.multiSqlContext.statementCount, 4);
assert.equal(multiAiPayload.analysis.multiSqlContext.successfulSql, 4);
assert.ok(multiAiPayload.analysis.tables.some((table) => table.tableName === "orders"));
assert.ok(multiAiPayload.analysis.joins.some((join) => /customer_id/i.test(`${join.left} ${join.right}`)));
assert.ok(multiAiPayload.analysis.filters.some((filter) => /status/i.test(filter.condition)));
assert.ok(Array.isArray(multiAiPayload.analysis.derivedColumns));
assert.match(serializedMultiAiPayload, /\[REDACTED_EMAIL\]/);
assert.doesNotMatch(serializedMultiAiPayload, /abc@example\.com/);

const tableAssetMap = buildTableAssetMap(multiAnalysis);
assert.ok(tableAssetMap.tables.length >= multiAnalysis.tableUsage.length);
assert.ok(tableAssetMap.summary.tableCount >= multiAnalysis.tableUsage.length);
assert.ok(tableAssetMap.summary.coreTableCount >= 1);

const ordersAsset = tableAssetMap.tables.find((table) => table.tableName === "orders");
assert.ok(ordersAsset);
assert.ok(ordersAsset.usedBySql.some((usedSql) => usedSql.statementId === "SQL-001"));
assert.ok(ordersAsset.joinTargets.some((target) => target.tableName === "customers"));
assert.ok(ordersAsset.conditions.some((condition) => /status\s*=\s*\?/i.test(condition.normalizedCondition)));
assert.equal(ordersAsset.importance, "high");
assert.ok(tableAssetMap.coreTables.some((table) => table.tableName === "orders"));
assert.ok((ordersAsset.businessIntentSummary.order_list ?? 0) >= 1);

const snapshotAsset = tableAssetMap.tables.find((table) => table.tableName === "monthly_order_snapshot");
assert.ok(snapshotAsset);
assert.equal(snapshotAsset.isInsertTarget, true);
assert.ok(snapshotAsset.businessGuesses.some((guess) => /배치|적재/i.test(guess)));

const tableAssetReport = buildTableAssetMapMarkdownSection(tableAssetMap);
assert.match(tableAssetReport, /테이블 자산 지도/);
assert.match(tableAssetReport, /핵심 테이블 후보/);
assert.match(tableAssetReport, /monthly_order_snapshot/);

const multiNarrative = buildMultiSqlNarrative(
  multiAnalysis,
  tableAssetMap,
  analyzeSqlRisks(multiAnalysis),
);
assert.equal(multiNarrative.title, "자산 지도 핵심 결과");
assert.equal(multiNarrative.keyFindings.length, 3);
assert.ok(multiNarrative.keyFindings.some((finding) => finding.id.startsWith("multi-core-table-")));
assert.ok(multiNarrative.keyFindings.some((finding) => finding.id.startsWith("multi-priority-sql-")));
assert.ok(multiNarrative.priorityTargets.some((target) => target.target?.type === "table"));
assert.ok(multiNarrative.nextQuestions.some((question) => question.id === "multi-core-table-impact"));
assert.ok(multiNarrative.nextQuestions.some((question) => question.id === "multi-write-order"));
assert.doesNotMatch(JSON.stringify(multiNarrative), /증감률|시계열 추세|변화 기여도|이상치/);

const multiDocumentRiskAnalysis = analyzeSqlRisks(multiAnalysis);
const multiDocumentSystemGraph = buildSystemGraph(multiAnalysis);
const sensitiveMultiDocumentSql = `${multiFixtureInput}

SELECT order_id
FROM orders
WHERE customer_email = 'abc@example.com'
  AND api_token = 'sk_test_abcdefghijklmnopqrstuvwxyz123456';`;
const multiDocumentPayload = buildAiMultiSqlDocumentDraftPayload({
  documentType: "asset_analysis",
  multiAnalysis,
  riskAnalysis: multiDocumentRiskAnalysis,
  sql: sensitiveMultiDocumentSql,
  systemGraph: multiDocumentSystemGraph,
  tableAssetMap,
});
const serializedMultiDocumentPayload = JSON.stringify(multiDocumentPayload);
assert.equal(multiDocumentPayload.documentType, "asset_analysis");
assert.match(multiDocumentPayload.instructions, /레거시 SQL 묶음 문서화 도우미/);
assert.match(multiDocumentPayload.instructions, /문서 유형: 레거시 자산 분석/);
assert.equal(multiDocumentPayload.analysis.multiSqlContext.statementCount, 4);
assert.equal(multiDocumentPayload.analysis.multiSqlContext.tableAssetSummary.tableCount, tableAssetMap.summary.tableCount);
assert.ok(multiDocumentPayload.analysis.multiSqlContext.tableAssetSummary.coreTables.includes("orders"));
assert.equal(multiDocumentPayload.analysis.multiSqlContext.systemGraphSummary.nodeCount, multiDocumentSystemGraph.summary.nodeCount);
assert.match(serializedMultiDocumentPayload, /\[REDACTED_EMAIL\]/);
assert.match(serializedMultiDocumentPayload, /\[REDACTED_TOKEN\]/);
assert.doesNotMatch(serializedMultiDocumentPayload, /abc@example\.com/);
assert.doesNotMatch(serializedMultiDocumentPayload, /sk_test_abcdefghijklmnopqrstuvwxyz123456/);

const missingMultiDraftModelResult = await handleAiMultiDocumentDraftRequest(
  { documentType: "asset_analysis", sql: multiFixtureInput },
  {
    env: {
      AI_PROVIDER: "ollama",
    },
    fetcher: async () => {
      throw new Error("fetch should not be called without model");
    },
  },
);
assert.equal(missingMultiDraftModelResult.status, 500);
assert.match(missingMultiDraftModelResult.body.error, /OLLAMA_MODEL|AI_MODEL/);

let sentMultiDraftUrl = "";
let sentMultiDraftRequest = "";
const mockMultiDraftResult = await handleAiMultiDocumentDraftRequest(
  { documentType: "operation", sql: sensitiveMultiDocumentSql },
  {
    env: {
      AI_MODEL: "qwen3:14b",
      AI_PROVIDER: "ollama",
    },
    fetcher: async (url, init) => {
      sentMultiDraftUrl = String(url);
      sentMultiDraftRequest = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          done: true,
          message: {
            content: JSON.stringify({
              businessAreaSummary: "주문 조회, 집계, 적재 SQL 묶음으로 추정됩니다.",
              coreTables: ["orders", "order_items", "monthly_order_snapshot"],
              dataFlowSummary: "orders와 order_items를 읽고 일부 결과를 snapshot 테이블에 적재합니다.",
              joinSummary: ["orders와 customers의 customer_id 관계가 반복됩니다."],
              markdown: "# 주문 SQL 묶음 운영 문서\n\n## 개요\n주문 관련 SQL 묶음의 운영 관점 초안입니다.",
              onboardingPath: ["orders 테이블 사용 SQL부터 확인합니다.", "적재 대상 테이블을 확인합니다."],
              operationChecklist: ["배치 SQL 실행 전 대상 테이블을 확인합니다."],
              overview: "여러 주문 SQL을 운영 관점으로 정리한 문서입니다.",
              refactoringSuggestions: ["반복 조건과 JOIN을 공통화할 수 있는지 검토합니다."],
              riskSummary: ["정적 분석 기준 리스크 finding을 검토해야 합니다."],
              sqlGroupSummary: ["조회 SQL과 집계 SQL, 적재 SQL이 함께 포함됩니다."],
              systemContext: "주문 데이터를 중심으로 조회와 적재 흐름이 함께 보입니다.",
              tableUsageSummary: ["orders 테이블이 여러 SQL에서 반복 사용됩니다."],
              targetAudience: "운영 담당자와 유지보수 개발자",
              title: "주문 SQL 묶음 운영 문서",
              uncertaintyNotes: ["실제 배치 스케줄은 SQL만으로 단정할 수 없습니다."],
            }),
            role: "assistant",
          },
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockMultiDraftResult.status, 200);
assert.equal(mockMultiDraftResult.body.draft.title, "주문 SQL 묶음 운영 문서");
assert.match(mockMultiDraftResult.body.draft.markdown, /주문 SQL 묶음 운영 문서/);
assert.equal(sentMultiDraftUrl, "http://localhost:11434/api/chat");
const sentMultiDraftBody = JSON.parse(sentMultiDraftRequest);
assert.equal(sentMultiDraftBody.model, "qwen3:14b");
assert.equal(sentMultiDraftBody.format.type, "object");
assert.match(sentMultiDraftRequest, /operation/);
assert.match(sentMultiDraftRequest, /\[REDACTED_EMAIL\]/);
assert.match(sentMultiDraftRequest, /\[REDACTED_TOKEN\]/);
assert.doesNotMatch(sentMultiDraftRequest, /abc@example\.com/);

const systemGraphInput = [
  readFixture("simple-order-list.sql"),
  readFixture("cte-without-aggregation.sql"),
  readFixture("insert-select-batch.sql"),
  readFixture("sales-dashboard-view.sql"),
  readFixture("refresh-monthly-snapshot-procedure.sql"),
].join("\n\n");
const systemGraphAnalysis = analyzeMultipleSql(systemGraphInput);
assert.equal(systemGraphAnalysis.statements.length, 5);

const systemGraph = buildSystemGraph(systemGraphAnalysis);
assert.ok(systemGraph.summary.nodeCount > 0);
assert.ok(systemGraph.summary.edgeCount > 0);
assert.ok(systemGraph.summary.tableNodeCount >= 3);
assert.ok(systemGraph.summary.sqlNodeCount >= 5);
assert.ok(systemGraph.summary.cteNodeCount >= 1);
assert.equal(systemGraph.summary.viewNodeCount, 1);
assert.equal(systemGraph.summary.procedureNodeCount, 1);
assert.ok(systemGraph.summary.loadFlowCount >= 2);

const ordersNode = systemGraph.nodes.find((node) => node.type === "table" && node.label === "orders");
assert.ok(ordersNode);
const snapshotNode = systemGraph.nodes.find((node) => node.type === "table" && node.label === "monthly_order_snapshot");
assert.ok(snapshotNode);
const viewNode = systemGraph.nodes.find((node) => node.type === "view" && node.label === "sales_dashboard");
assert.ok(viewNode);
const procedureNode = systemGraph.nodes.find((node) => node.type === "procedure" && node.label === "refresh_monthly_order_snapshot");
assert.ok(procedureNode);
assert.ok(procedureNode.warnings.some((warning) => /부분 분석|동적 SQL/i.test(warning)));

assert.ok(systemGraph.edges.some((edge) => edge.type === "reads" && edge.to === ordersNode.id));
assert.ok(systemGraph.edges.some((edge) => edge.type === "joins" && /customer_id/i.test(edge.label)));
assert.ok(systemGraph.edges.some((edge) => edge.type === "transforms_to" && edge.from === ordersNode.id && edge.to === snapshotNode.id));
assert.ok(systemGraph.edges.some((edge) => edge.type === "depends_on" && edge.to === viewNode.id || edge.type === "transforms_to" && edge.to === viewNode.id));
assert.ok(systemGraph.edges.some((edge) => edge.type === "writes" && edge.to === procedureNode.id));
assert.ok(systemGraph.edges.some((edge) => edge.type === "depends_on" && /CTE/.test(edge.label)));

const loadFlowView = getSystemGraphView(systemGraph, "load_flow");
assert.ok(loadFlowView.edges.every((edge) => ["writes", "transforms_to"].includes(edge.type)));
assert.ok(loadFlowView.edges.some((edge) => edge.to === snapshotNode.id));

const cteFlowView = getSystemGraphView(systemGraph, "cte_flow");
assert.ok(cteFlowView.nodes.some((node) => node.type === "cte"));
assert.ok(cteFlowView.edges.some((edge) => edge.type === "depends_on"));

const ordersImpact = analyzeImpact(systemGraph, ordersNode.id, { direction: "both", maxDepth: 3 });
assert.ok(ordersImpact.downstream.some((impact) => impact.label === "SQL-001"));
assert.ok(ordersImpact.downstream.some((impact) => impact.label === "monthly_order_snapshot"));
assert.ok(ordersImpact.downstream.some((impact) => impact.label === "sales_dashboard"));

const snapshotImpact = analyzeImpact(systemGraph, snapshotNode.id, { direction: "upstream", maxDepth: 3 });
assert.ok(snapshotImpact.upstream.some((impact) => impact.label === "orders"));

const systemGraphReport = buildSystemGraphMarkdownSection(systemGraph);
assert.match(systemGraphReport, /시스템 의존성 지도/);
assert.match(systemGraphReport, /SQL 의존성/);
assert.match(systemGraphReport, /적재\/변환 흐름/);
assert.match(systemGraphReport, /sales_dashboard/);

const riskFixtureInput = [
  readFixture("risk-select-star.sql"),
  readFixture("risk-update-delete-no-where.sql"),
  readFixture("risk-implicit-join.sql"),
  readFixture("risk-many-joins.sql"),
  readFixture("risk-date-like-hardcoded-pii.sql"),
  readFixture("risk-aggregation-no-group.sql"),
  readFixture("risk-count-only-no-group-ok.sql"),
  readFixture("risk-date-function-select-ok.sql"),
  readFixture("risk-duplicate-a.sql"),
  readFixture("risk-duplicate-b.sql"),
].join("\n\n");
const riskAnalysis = analyzeMultipleSql(riskFixtureInput);
const riskFindings = analyzeSqlRisks(riskAnalysis);
const findingsByCategory = (category) =>
  riskFindings.findings.filter((finding) => finding.category === category);

assert.ok(findingsByCategory("select_star").some((finding) => finding.statementId === "SQL-001"));
assert.equal(findingsByCategory("unsafe_update_delete").length, 2);
assert.ok(findingsByCategory("unsafe_update_delete").every((finding) => finding.severity === "critical"));
assert.ok(findingsByCategory("implicit_join").some((finding) => finding.statementId === "SQL-004"));
assert.ok(findingsByCategory("too_many_joins").some((finding) => finding.statementId === "SQL-005"));
assert.ok(findingsByCategory("date_function_on_column").some((finding) => finding.statementId === "SQL-006"));
assert.ok(findingsByCategory("leading_wildcard_like").some((finding) => finding.statementId === "SQL-006"));
assert.ok(findingsByCategory("hardcoded_code_value").some((finding) => finding.statementId === "SQL-006"));
assert.ok(findingsByCategory("personal_info_condition").some((finding) => finding.statementId === "SQL-006"));
assert.ok(findingsByCategory("suspicious_aggregation").some((finding) => finding.statementId === "SQL-007"));
assert.ok(findingsByCategory("duplicate_sql_pattern").some((finding) => finding.statementId === "SQL-010"));
assert.ok(findingsByCategory("duplicate_sql_pattern").some((finding) => finding.statementId === "SQL-011"));
assert.ok(!findingsByCategory("suspicious_aggregation").some((finding) => finding.statementId === "SQL-008"));
assert.ok(!findingsByCategory("date_function_on_column").some((finding) => finding.statementId === "SQL-009"));
assert.ok(riskFindings.summary.critical >= 2);
assert.ok(riskFindings.summary.total >= 10);

const writeRiskMultiAnalysis = analyzeMultipleSql(`UPDATE orders
SET status = 'CANCELLED';

DELETE FROM order_items;`);
const writeRiskMultiNarrative = buildMultiSqlNarrative(
  writeRiskMultiAnalysis,
  buildTableAssetMap(writeRiskMultiAnalysis),
  analyzeSqlRisks(writeRiskMultiAnalysis),
);
assert.ok(writeRiskMultiNarrative.keyFindings.some((finding) => finding.id.startsWith("multi-risk-")));
assert.ok(writeRiskMultiNarrative.nextQuestions.some((question) => question.id === "multi-write-order"));
assert.ok(writeRiskMultiNarrative.nextQuestions.some((question) => question.id === "multi-risk-concentration"));

const reportTableAssetMap = buildTableAssetMap(systemGraphAnalysis);
const documentationReport = buildSqlExplainerReport({
  aiDocumentDraft: {
    businessAreaSummary: "주문 조회, 스냅샷 적재, 대시보드 View 흐름으로 추정됩니다.",
    coreTables: ["orders", "monthly_order_snapshot", "sales_dashboard"],
    dataFlowSummary: "orders를 읽고 monthly_order_snapshot에 적재한 뒤 sales_dashboard View에서 재사용합니다.",
    joinSummary: ["orders와 customers의 customer_id 관계가 확인됩니다."],
    markdown: "# 주문 시스템 자산 분석 초안\n\n## 개요\n주문 데이터 흐름을 문서화합니다.",
    onboardingPath: ["orders 테이블을 먼저 확인합니다.", "적재 대상과 View 의존성을 확인합니다."],
    operationChecklist: ["적재 SQL 실행 전 대상 테이블을 확인합니다."],
    overview: "주문 SQL 묶음의 문서 초안입니다.",
    refactoringSuggestions: ["반복 조건을 공통화할 수 있는지 검토합니다."],
    riskSummary: ["Procedure 내부 로직은 정규식 기반 부분 분석입니다."],
    sqlGroupSummary: ["조회 SQL, CTE SQL, 적재 SQL, View/Procedure SQL이 포함됩니다."],
    systemContext: "주문 데이터를 중심으로 조회, 적재, 대시보드 의존성이 함께 보입니다.",
    tableUsageSummary: ["orders가 주요 원천 테이블 후보입니다."],
    targetAudience: "신규 개발자와 유지보수 담당자",
    title: "주문 시스템 자산 분석 초안",
    uncertaintyNotes: ["실제 배치 스케줄은 SQL만으로 단정하지 않습니다."],
  },
  aiExplanation: {
    businessPurpose: "주문과 월별 스냅샷 흐름을 설명하는 보고서로 추정됩니다.",
    dataFlowExplanation: "orders에서 읽은 데이터를 monthly_order_snapshot과 sales_dashboard로 연결합니다.",
    juniorDeveloperExplanation: "orders 테이블을 먼저 보고 적재 대상과 View 의존성을 확인합니다.",
    performanceNotes: ["JOIN 키 인덱스를 확인합니다."],
    refactoringSuggestions: ["반복 조건을 공통 View로 정리할 수 있습니다."],
    riskNotes: ["Procedure 내부 동적 SQL은 별도 확인합니다."],
    summary: "주문 데이터 기반 시스템 지도 보고서입니다.",
    uncertaintyNotes: ["실제 배치 스케줄은 SQL만으로 알 수 없습니다."],
  },
  generatedAt: "2026-07-26T00:00:00.000Z",
  multiAnalysis: systemGraphAnalysis,
  options: {
    ...defaultReportOptions,
    includeAiDocumentDraft: true,
    includeAiExplanation: true,
    includeRawSql: true,
  },
  riskAnalysis: riskFindings,
  systemGraph,
  tableAssetMap: reportTableAssetMap,
});
assert.equal(documentationReport.summary.totalSql, 5);
assert.equal(documentationReport.summary.viewCount, 1);
assert.equal(documentationReport.summary.procedureCount, 1);
assert.ok(documentationReport.tables.some((table) => table.tableName === "orders"));
assert.ok(documentationReport.riskSqls.some((risk) => risk.id === "SQL-003" && risk.score >= 20));
assert.ok(documentationReport.riskSqls.some((risk) => risk.reasons.some((reason) => /Procedure/i.test(reason))));
assert.equal(documentationReport.riskFindingSummary.total, riskFindings.summary.total);
assert.ok(documentationReport.riskFindings.some((finding) => finding.category === "unsafe_update_delete"));
assert.ok(documentationReport.juniorDeveloperGuide.some((guide) => /orders|테이블/i.test(guide)));
assert.equal(documentationReport.aiDocumentDraft.title, "주문 시스템 자산 분석 초안");
assert.equal(documentationReport.aiExplanation.summary, "주문 데이터 기반 시스템 지도 보고서입니다.");

const markdownDocumentationReport = buildMarkdownReport(documentationReport);
assert.match(markdownDocumentationReport, /SQL Explainer 분석 보고서/);
assert.match(markdownDocumentationReport, /위험 SQL 목록/);
assert.match(markdownDocumentationReport, /리스크 \/ 개선 포인트/);
assert.match(markdownDocumentationReport, /신규 개발자 설명/);
assert.match(markdownDocumentationReport, /AI 설명 보강/);
assert.match(markdownDocumentationReport, /AI 문서 초안/);
assert.match(markdownDocumentationReport, /주문 시스템 자산 분석 초안/);
assert.match(markdownDocumentationReport, /```sql/);

const tableUsageCsv = buildTableUsageCsv(documentationReport);
assert.match(tableUsageCsv, /table_name,usage_count,importance/);
assert.match(tableUsageCsv, /orders/);
assert.match(tableUsageCsv, /monthly_order_snapshot/);

const riskFindingsCsv = buildRiskFindingsCsv(documentationReport);
assert.match(riskFindingsCsv, /severity,statement_id,category,title,evidence,recommendation,confidence/);
assert.match(riskFindingsCsv, /unsafe_update_delete/);

const notionDocument = buildPasteDocument(documentationReport, "notion");
assert.match(notionDocument, /^# SQL Explainer 분석 보고서/);
assert.match(notionDocument, /## 위험 SQL/);
assert.match(notionDocument, /## 리스크 \/ 개선 포인트/);
assert.match(notionDocument, /## AI 문서 초안/);

const confluenceDocument = buildPasteDocument(documentationReport, "confluence");
assert.match(confluenceDocument, /^h1\. SQL Explainer 분석 보고서/);
assert.match(confluenceDocument, /h2\. 위험 SQL/);
assert.match(confluenceDocument, /h2\. 리스크 \/ 개선 포인트/);
assert.match(confluenceDocument, /h2\. AI 문서 초안/);

const printableHtmlReport = buildPrintableHtmlReport(documentationReport);
assert.match(printableHtmlReport, /<!doctype html>/);
assert.match(printableHtmlReport, /PDF로 저장/);
assert.match(printableHtmlReport, /사용 테이블 목록/);
assert.match(printableHtmlReport, /리스크 \/ 개선 포인트/);
assert.match(printableHtmlReport, /AI 문서 초안/);
assert.match(printableHtmlReport, /주문 시스템 자산 분석 초안/);

const complex = analyzeSql(readFixture("complex-sales-analysis.sql"));
const complexText = renderExplanationText(complex);

assert.equal(explainSql(readFixture("complex-sales-analysis.sql")).summary, complex.summary);
assert.equal(complex.businessIntent.type, "analytics_report");
assert.equal(complex.ctes.length, 4);
assert.ok(Array.isArray(complex.joins));
assert.equal(complex.joins.length, complex.relations.length);
assert.ok(complex.confidence);
assert.ok(["medium", "high"].includes(complex.confidence.level));
assert.ok(Array.isArray(complex.warnings));

const recentOrders = findCte(complex, "recent_orders");
assert.ok(recentOrders);
assert.ok(recentOrders.filters.some((filter) => /12 months/i.test(filter.condition)));
assert.ok(recentOrders.filters.some((filter) => /status\s+IN/i.test(filter.condition)));

const orderItemsAggregations = stageItems(complex.aggregations, "order_items_summary");
assert.ok(orderItemsAggregations.some((aggregation) => aggregation.functionName === "COUNT"));
assert.ok(orderItemsAggregations.some((aggregation) => aggregation.functionName === "SUM"));

const monthlyGroupBy = stageItems(complex.groupBy, "customer_monthly_sales");
assert.ok(monthlyGroupBy.length > 0);
assert.ok(monthlyGroupBy.some((group) => group.columns.some((column) => /customer_id/i.test(column))));
assert.ok(monthlyGroupBy.some((group) => group.columns.some((column) => /order_month/i.test(column))));
assert.ok(
  complex.derivedColumns.some((column) =>
    column.stage === "recent_orders" && column.alias === "order_month",
  ),
);

const rankedWindows = stageItems(complex.windowFunctions, "ranked_customers");
for (const functionName of ["SUM", "AVG", "LAG", "RANK"]) {
  assert.ok(
    rankedWindows.some((windowFunction) => windowFunction.functionName === functionName),
    `Expected ranked_customers to include ${functionName}`,
  );
}

assert.ok(
  complex.filters.some((filter) =>
    filter.stage === "최종 결과" && /monthly_sales\s*>=\s*100000/i.test(filter.condition),
  ),
);
assertIncludesAll(complexText, [
  "고객별 월 매출",
  "최근 12개월",
  "주문 상태",
  "GROUP BY",
  "집계",
  "누적 매출",
  "현재 행 포함 최근 3개 행 기준 평균",
  "월별 데이터 기준 최근 3개월 이동 평균",
  "전월 매출",
  "월별 매출 순위",
  "고객 세그먼트",
  "CRM",
  "VIP",
  "월 매출이 100000 이상",
]);
assertIncludesNone(complexText, ["주문 목록 조회"]);

const simpleEmployee = analyzeSql(`SELECT A.EMP_NO, A.EMP_NM, B.DEPT_NM
FROM TB_EMP A
JOIN TB_DEPT B ON A.DEPT_CD = B.DEPT_CD
WHERE A.USE_YN = 'Y';`);
assertIntentIn(simpleEmployee, ["lookup", "list_query"]);
assert.match(simpleEmployee.summary, /현재 재직 중인 직원과 소속 부서/);
assert.deepEqual(
  simpleEmployee.joins.map((join) => `${join.left}->${join.right}`),
  ["TB_EMP.DEPT_CD->TB_DEPT.DEPT_CD"],
);

const simpleOrderList = analyzeSql(readFixture("simple-order-list.sql"));
const simpleOrderText = renderExplanationText(simpleOrderList);
assertIntentIn(simpleOrderList, ["order_list", "list_query"]);
assert.equal(simpleOrderList.groupBy.length, 0);
assert.equal(simpleOrderList.aggregations.length, 0);
assert.equal(simpleOrderList.windowFunctions.length, 0);
assert.equal(simpleOrderList.caseExpressions.length, 0);
assert.ok(simpleOrderList.tables.some((table) => table.category === "order"));
assert.ok(simpleOrderList.filters.length > 0);
assertIncludesAll(simpleOrderText, ["주문", "목록", "조회"]);
assertIncludesNone(simpleOrderText, ["CRM", "VIP", "고객별 월 매출 분석", "윈도우 함수", "고객 세그먼트"]);

const productSales = analyzeSql(readFixture("product-sales-summary.sql"));
const productSalesText = renderExplanationText(productSales);
assertIntentIn(productSales, ["sales_summary", "aggregation_report"]);
assert.ok(productSales.groupBy.length > 0);
assert.ok(productSales.aggregations.some((aggregation) => aggregation.functionName === "SUM"));
assert.ok(productSales.aggregations.some((aggregation) => aggregation.functionName === "COUNT"));
assert.equal(productSales.windowFunctions.length, 0);
assert.equal(productSales.caseExpressions.length, 0);
assertIncludesAll(productSalesText, ["매출", "집계", "GROUP BY"]);
assertIncludesNone(productSalesText, ["윈도우 함수", "CRM", "VIP", "고객 세그먼트"]);

const userRanking = analyzeSql(readFixture("user-ranking-window.sql"));
const userRankingText = renderExplanationText(userRanking);
assert.equal(userRanking.businessIntent.type, "ranking_analysis");
assert.ok(userRanking.windowFunctions.some((windowFunction) => windowFunction.functionName === "RANK"));
assert.ok(userRanking.windowFunctions.some((windowFunction) => windowFunction.functionName === "ROW_NUMBER"));
assert.equal(userRanking.groupBy.length, 0);
assert.equal(userRanking.aggregations.length, 0);
assertIncludesAll(userRankingText, ["순위", "윈도우 함수"]);
assertIncludesNone(userRankingText, ["CRM", "VIP", "고객 세그먼트"]);

const statusCase = analyzeSql(readFixture("status-case-classification.sql"));
const statusCaseText = renderExplanationText(statusCase);
assertIntentIn(statusCase, ["classification", "derived_column_explanation"]);
assert.equal(statusCase.caseExpressions.length, 1);
assertIncludesAll(statusCaseText, ["CASE", "상태", "분류", "결제완료", "배송중", "완료", "확인필요"]);
assert.equal(statusCase.groupBy.length, 0);
assert.equal(statusCase.windowFunctions.length, 0);
assertIncludesNone(statusCaseText, ["윈도우 함수", "CRM", "VIP"]);

const stagedCte = analyzeSql(readFixture("cte-without-aggregation.sql"));
const stagedCteText = renderExplanationText(stagedCte);
assertIntentIn(stagedCte, ["staged_query", "data_preparation"]);
assert.equal(stagedCte.ctes.length, 2);
assert.equal(stagedCte.groupBy.length, 0);
assert.equal(stagedCte.aggregations.length, 0);
assert.equal(stagedCte.windowFunctions.length, 0);
assert.equal(stagedCte.caseExpressions.length, 0);
assertIncludesAll(stagedCteText, ["CTE", "단계"]);
assertIncludesNone(stagedCteText, ["윈도우 함수", "고객 세그먼트", "CRM", "VIP", "매출 집계"]);

const insertSelect = analyzeSql(readFixture("insert-select-batch.sql"));
const insertSelectText = renderExplanationText(insertSelect);
assertIntentIn(insertSelect, ["data_insert", "batch_etl"]);
assertIncludesAll(insertSelectText, ["INSERT", "적재", "배치"]);
assert.equal(insertSelect.groupBy.length, 0);
assert.equal(insertSelect.aggregations.length, 0);
assert.equal(insertSelect.windowFunctions.length, 0);
assert.equal(insertSelect.caseExpressions.length, 0);
assertIncludesNone(insertSelectText, ["단순 조회 SQL", "목록 조회", "CRM", "VIP"]);

const safeSimpleNarrativeSql = `SELECT order_id
FROM orders
WHERE created_at >= DATE '2026-01-01';`;
const safeSimpleNarrative = buildSingleSqlNarrative(
  safeSimpleNarrativeSql,
  analyzeSql(safeSimpleNarrativeSql),
);
assert.equal(safeSimpleNarrative.title, "SQL 핵심 결과");
assert.equal(safeSimpleNarrative.keyFindings.length, 3);
assert.ok(safeSimpleNarrative.keyFindings.some((finding) => finding.id === "single-risk-none"));
assert.ok(safeSimpleNarrative.nextQuestions.some((question) => question.id === "single-date-boundary"));
assert.ok(!safeSimpleNarrative.nextQuestions.some((question) => question.id === "single-aggregation-grain"));
assert.doesNotMatch(JSON.stringify(safeSimpleNarrative), /증감률|시계열 추세|변화 기여도|이상치/);

const numericFilterNarrativeSql = "SELECT order_id FROM orders WHERE total_amount >= 100000;";
const numericFilterNarrative = buildSingleSqlNarrative(
  numericFilterNarrativeSql,
  analyzeSql(numericFilterNarrativeSql),
);
assert.ok(!numericFilterNarrative.nextQuestions.some((question) => question.id === "single-date-boundary"));

const productSalesNarrative = buildSingleSqlNarrative(
  readFixture("product-sales-summary.sql"),
  productSales,
);
assert.ok(productSalesNarrative.keyFindings.some((finding) => finding.id === "single-structure-join-aggregation"));
assert.ok(productSalesNarrative.nextQuestions.some((question) => question.id === "single-join-key-uniqueness"));
assert.ok(productSalesNarrative.nextQuestions.some((question) => question.id === "single-aggregation-grain"));
assert.ok(!productSalesNarrative.nextQuestions.some((question) => question.id === "single-intermediate-grain"));

const stagedCteNarrative = buildSingleSqlNarrative(
  readFixture("cte-without-aggregation.sql"),
  stagedCte,
);
assert.ok(stagedCteNarrative.nextQuestions.some((question) => question.id === "single-intermediate-grain"));
assert.ok(!stagedCteNarrative.nextQuestions.some((question) => question.id === "single-aggregation-grain"));

const complexNarrative = buildSingleSqlNarrative(readFixture("complex-sales-analysis.sql"), complex);
assert.ok(complexNarrative.nextQuestions.some((question) => question.id === "single-intermediate-grain"));
assert.ok(complexNarrative.nextQuestions.some((question) => question.id === "single-aggregation-grain"));

const unsafeWriteNarrativeSql = "UPDATE orders SET status = 'CANCELLED';";
const unsafeWriteNarrative = buildSingleSqlNarrative(
  unsafeWriteNarrativeSql,
  analyzeSql(unsafeWriteNarrativeSql),
);
assert.ok(unsafeWriteNarrative.keyFindings.some((finding) => finding.id.startsWith("single-risk-")));
assert.ok(unsafeWriteNarrative.nextQuestions.some((question) => question.id === "single-write-row-count"));
assert.ok(unsafeWriteNarrative.nextQuestions.some((question) => question.id === "single-write-rollback"));

const schemaQualified = analyzeSql(readFixture("schema-qualified-tables.sql"));
const schemaOrderTable = schemaQualified.tables.find((table) => table.rawName === "public.orders");
const schemaCustomerTable = schemaQualified.tables.find((table) => table.rawName === "crm.customers");
assert.ok(schemaOrderTable);
assert.equal(schemaOrderTable.tableName, "orders");
assert.equal(schemaOrderTable.schemaName, "public");
assert.equal(schemaOrderTable.alias, "o");
assert.ok(schemaCustomerTable);
assert.equal(schemaCustomerTable.tableName, "customers");
assert.equal(schemaCustomerTable.schemaName, "crm");
assert.ok(schemaQualified.joins.some((join) => join.left === "customers.customer_id" || join.right === "customers.customer_id"));

const quotedIdentifiers = analyzeSql(readFixture("quoted-identifiers.sql"));
const quotedText = renderExplanationText(quotedIdentifiers);
assert.ok(quotedIdentifiers.tables.some((table) => table.tableName === "Order Table"));
assert.ok(quotedIdentifiers.tables.some((table) => table.tableName === "Customer Table"));
assert.ok(quotedIdentifiers.joins.some((join) => /Customer ID/.test(`${join.left} ${join.right}`)));
assertIncludesAll(quotedText, ["Order Table", "Customer Table"]);

const commentsIgnored = analyzeSql(readFixture("comments-ignored.sql"));
const commentsText = renderExplanationText(commentsIgnored);
assert.ok(commentsIgnored.tables.some((table) => table.tableName === "orders"));
assert.ok(!commentsIgnored.tables.some((table) => /fake/i.test(table.tableName)));
assert.ok(!commentsIgnored.filters.some((filter) => /fake/i.test(filter.condition)));
assertIncludesNone(commentsText, ["fake_orders", "fake_customers", "fake_payments"]);

const havingSales = analyzeSql(readFixture("having-sales-filter.sql"));
const havingText = renderExplanationText(havingSales);
assertIntentIn(havingSales, ["sales_summary", "aggregation_report", "analytics_report"]);
assert.equal(havingSales.havingConditions.length, 1);
assert.match(havingSales.havingConditions[0].condition, /SUM\(o.total_amount\)\s*>=\s*1000000/i);
assertIncludesAll(havingText, ["HAVING", "집계 결과", "1,000,000 이상"]);

const existsSubquery = analyzeSql(readFixture("exists-subquery.sql"));
const existsText = renderExplanationText(existsSubquery);
assert.ok(existsSubquery.subqueries.some((subquery) => subquery.type === "exists"));
assert.ok(existsSubquery.tables.some((table) => table.tableName === "orders" && table.source === "subquery"));
assert.equal(existsSubquery.confidence.level, "medium");
assertIncludesAll(existsText, ["EXISTS", "서브쿼리", "orders"]);

const scalarSubquery = analyzeSql(readFixture("scalar-subquery.sql"));
const scalarText = renderExplanationText(scalarSubquery);
assert.ok(scalarSubquery.subqueries.some((subquery) => subquery.type === "scalar"));
assert.ok(scalarSubquery.tables.some((table) => table.tableName === "orders" && table.source === "subquery"));
assert.ok(scalarSubquery.derivedColumns.some((column) => column.alias === "order_count"));
assertIncludesAll(scalarText, ["스칼라 서브쿼리", "파생 지표", "order_count"]);

const unionOrders = analyzeSql(readFixture("union-orders.sql"));
const unionText = renderExplanationText(unionOrders);
assertIntentIn(unionOrders, ["combined_result", "set_operation"]);
assert.equal(unionOrders.setOperations.length, 1);
assert.equal(unionOrders.setOperations[0].operator, "UNION ALL");
assertIncludesAll(unionText, ["UNION ALL", "중복 제거 없이", "여러 SELECT 결과"]);
assertIncludesNone(unionText, ["CRM", "VIP"]);

const recursiveCte = analyzeSql(readFixture("recursive-cte-org.sql"));
assert.ok(recursiveCte.advancedFeatures.some((feature) => feature.type === "recursive_cte"));
assert.ok(recursiveCte.advancedFeatures.some((feature) => feature.type === "dialect_specific" && feature.dialect?.includes("PostgreSQL")) === false);
assertIncludesAll(renderExplanationText(recursiveCte), ["WITH RECURSIVE", "재귀 CTE", "고급 문법"]);

const mergeSnapshot = analyzeSql(readFixture("merge-customer-snapshot.sql"));
assert.ok(mergeSnapshot.advancedFeatures.some((feature) => feature.type === "merge"));
assertIncludesAll(renderExplanationText(mergeSnapshot), ["MERGE INTO", "UPDATE 또는 INSERT"]);

const updateFrom = analyzeSql(readFixture("update-from-customer-segment.sql"));
assert.ok(updateFrom.advancedFeatures.some((feature) => feature.type === "update_from"));
assertIncludesAll(renderExplanationText(updateFrom), ["UPDATE ... FROM", "갱신"]);

const deleteUsing = analyzeSql(readFixture("delete-using-order-errors.sql"));
assert.ok(deleteUsing.advancedFeatures.some((feature) => feature.type === "delete_using"));
assertIncludesAll(renderExplanationText(deleteUsing), ["DELETE FROM ... USING", "삭제"]);

const pivotSales = analyzeSql(readFixture("pivot-monthly-sales.sql"));
assert.ok(pivotSales.advancedFeatures.some((feature) => feature.type === "pivot"));
assertIncludesAll(renderExplanationText(pivotSales), ["PIVOT", "교차 집계"]);

const unpivotStatus = analyzeSql(readFixture("unpivot-status-counts.sql"));
assert.ok(unpivotStatus.advancedFeatures.some((feature) => feature.type === "unpivot"));
assertIncludesAll(renderExplanationText(unpivotStatus), ["UNPIVOT", "행 형태"]);

const lateralJsonArray = analyzeSql(readFixture("lateral-json-array.sql"));
assert.ok(lateralJsonArray.advancedFeatures.some((feature) => feature.type === "lateral"));
assert.ok(lateralJsonArray.advancedFeatures.some((feature) => feature.type === "json"));
assert.ok(lateralJsonArray.advancedFeatures.some((feature) => feature.type === "array"));
assertIncludesAll(renderExplanationText(lateralJsonArray), ["LATERAL", "JSON", "배열"]);

const applyJson = analyzeSql(readFixture("apply-json.sql"));
assert.ok(applyJson.advancedFeatures.some((feature) => feature.type === "apply"));
assert.ok(applyJson.advancedFeatures.some((feature) => feature.type === "json"));
assertIncludesAll(renderExplanationText(applyJson), ["APPLY", "OPENJSON", "SQL Server"]);

const dynamicSql = analyzeSql(readFixture("dynamic-sql.sql"));
assert.ok(dynamicSql.advancedFeatures.some((feature) => feature.type === "dynamic_sql"));
assert.ok(dynamicSql.warnings.some((warning) => /동적 SQL/.test(warning)));
assertIncludesAll(renderExplanationText(dynamicSql), ["동적 SQL", "최종 문장"]);

const deeplyNested = analyzeSql(readFixture("deeply-nested.sql"));
assert.ok(deeplyNested.advancedFeatures.some((feature) => feature.type === "deep_nesting"));
assert.ok(deeplyNested.confidence.reasons.some((reason) => /중첩 괄호/.test(reason)));
assert.ok(deeplyNested.warnings.some((warning) => /중첩 깊이/.test(warning)));

const postgresDialect = analyzeSql(readFixture("dialect-postgresql.sql"));
assert.ok(postgresDialect.advancedFeatures.some((feature) => feature.type === "dialect_specific" && feature.dialect?.includes("PostgreSQL")));
assert.ok(postgresDialect.advancedFeatures.some((feature) => feature.type === "json"));

const oracleDialect = analyzeSql(readFixture("dialect-oracle.sql"));
assert.ok(oracleDialect.advancedFeatures.some((feature) => feature.type === "dialect_specific" && feature.dialect?.includes("Oracle")));

const sqlServerDialect = analyzeSql(readFixture("dialect-sqlserver.sql"));
assert.ok(sqlServerDialect.advancedFeatures.some((feature) => feature.type === "dialect_specific" && feature.dialect?.includes("SQL Server")));

const mysqlDialect = analyzeSql(readFixture("dialect-mysql.sql"));
assert.ok(mysqlDialect.advancedFeatures.some((feature) => feature.type === "dialect_specific" && feature.dialect?.includes("MySQL")));
assert.ok(mysqlDialect.advancedFeatures.some((feature) => feature.type === "json"));

const quotedKeywordLiteral = analyzeSql(`SELECT order_id FROM sales.orders WHERE status = 'PIVOT JOIN SELECT -- not syntax';`);
assert.equal(quotedKeywordLiteral.advancedFeatures.some((feature) => ["pivot", "dynamic_sql"].includes(feature.type)), false);

const advancedCommentsIgnored = analyzeSql(readFixture("advanced-comments-ignored.sql"));
assert.equal(advancedCommentsIgnored.advancedFeatures.length, 0);

const groupOnly = analyzeSql(`SELECT customer_id, COUNT(*) AS order_count, SUM(total_amount) AS monthly_sales
FROM orders
GROUP BY customer_id;`);
assertIntentIn(groupOnly, ["sales_summary", "aggregation_report"]);
assert.ok(groupOnly.groupBy.length > 0);
assert.ok(groupOnly.aggregations.length >= 2);
assert.equal(groupOnly.windowFunctions.length, 0);

const windowOnly = analyzeSql(`SELECT customer_id,
  SUM(monthly_sales) OVER (PARTITION BY customer_id ORDER BY order_month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_sales
FROM customer_monthly_sales;`);
assertIntentIn(windowOnly, ["analytics_report", "ranking_analysis"]);
assert.match(renderExplanationText(windowOnly), /누적 매출/);

const caseOnly = analyzeSql(`SELECT customer_id,
  CASE
    WHEN monthly_sales_rank <= 10 THEN 'TOP_10'
    WHEN monthly_sales >= 1000000 THEN 'HIGH_VALUE'
    ELSE 'NORMAL'
  END AS customer_segment
FROM ranked_customers;`);
assertIntentIn(caseOnly, ["classification", "derived_column_explanation", "analytics_report"]);
assert.match(renderExplanationText(caseOnly), /고객 세그먼트|분류/);

const whereJoin = analyzeSql(`SELECT *
FROM legacy_orders o, legacy_customers c
WHERE o.customer_id = c.customer_id
  AND o.status = 'PAID';`);
assert.ok(
  whereJoin.joins.some((join) =>
    /명시적 JOIN은 아니지만 관계 조건으로 사용된 것으로 추정/.test(join.explanation ?? ""),
  ),
);

const genericTables = analyzeSql(`SELECT m.mapping_id, cd.code_name, mt.meta_value
FROM tb_mappings m
JOIN tb_codes cd ON cd.code_id = m.code_id
JOIN tb_meta mt ON mt.meta_id = m.meta_id;`);
assert.ok(genericTables.tables.some((table) => /추정/.test(table.description)));
assertIncludesAll(renderExplanationText(genericTables), ["추정"]);

const dataInspection = inspectDataInput(readFixture("data-analysis-sample.csv"));
assert.equal(dataInspection.ok, true);
assert.ok(dataInspection.columnOptions.metricColumns.includes("processed_count"));
assert.ok(dataInspection.columnOptions.timeColumns.includes("period"));
assert.ok(dataInspection.columnOptions.groupColumns.includes("team"));

const dataCalculation = calculateComputedAnalysis(dataInspection, {
  datasetName: "처리량 샘플",
  groupColumn: "team",
  metricColumn: "processed_count",
  timeColumn: "period",
});
assert.equal(dataCalculation.ok, true);
assert.equal(dataCalculation.result.scope.rowCount, 8);
assert.equal(dataCalculation.result.scope.validMetricRowCount, 8);
assert.equal(dataCalculation.result.contractVersion, COMPUTED_ANALYSIS_CONTRACT_VERSION);
assert.deepEqual(dataCalculation.result.calculationBasis.dataQuality, {
  excludedMetricRowCount: 0,
  inputRowCount: 8,
  invalidPeriodRowCount: 0,
  validMetricRowCount: 8,
});
assert.deepEqual(dataCalculation.result.calculationBasis.time, {
  aggregation: "sum_by_period",
  endPeriod: "2026-08",
  granularity: "month",
  periodCount: 4,
  recurrenceAssessment: "not_evaluated",
  startPeriod: "2026-05",
  trendAvailability: "calculated",
  validPeriodRowCount: 8,
});
assert.deepEqual(dataCalculation.result.calculationBasis.comparison, {
  aggregation: "sum_by_group",
  baseline: "group_average",
  displayedGroupCount: 2,
  groupCount: 2,
});
assert.equal(dataCalculation.result.calculationBasis.outlierDetection.iqrMultiplier, 1.5);
assert.equal(dataCalculation.result.calculationBasis.outlierDetection.zScoreThreshold, 2.5);
assert.equal(dataCalculation.result.summary.find((metric) => metric.id === "total")?.value, 755);
assert.equal(dataCalculation.result.summary.find((metric) => metric.id === "max")?.value, 182);
assert.equal(dataCalculation.result.summary.find((metric) => metric.id === "min")?.value, 65);
assert.equal(dataCalculation.result.trend?.pattern, "sustained_increase");
assert.equal(Math.round(dataCalculation.result.trend?.changeRate ?? 0), 47);
assert.equal(dataCalculation.result.comparisons[0]?.group, "A");
assert.ok(dataCalculation.result.outliers.some((outlier) => outlier.value === 182 && outlier.method === "iqr"));
assert.ok(dataCalculation.result.insightCandidates.some((candidate) => candidate.type === "trend"));
assert.ok(dataCalculation.result.insightCandidates.some((candidate) => candidate.type === "comparison"));
assert.ok(dataCalculation.result.insightCandidates.some((candidate) => candidate.type === "contribution"));
assert.ok(dataCalculation.result.insightCandidates.some((candidate) => candidate.type === "outlier"));
assert.equal(dataCalculation.result.reportFindings.length, 4);
assert.ok(dataCalculation.result.reportFindings.some((finding) => finding.type === "trend"));
assert.ok(dataCalculation.result.reportFindings.some((finding) => finding.type === "comparison"));
assert.ok(dataCalculation.result.reportFindings.some((finding) => finding.type === "contribution"));
assert.ok(dataCalculation.result.reportFindings.some((finding) => finding.type === "review"));
assert.ok(dataCalculation.result.reportFindings.some((finding) => /추가 확인 대상으로 정리/.test(finding.statements.join(" "))));
assert.equal(dataCalculation.result.changeContributions[0]?.group, "A");
assert.equal("rows" in dataCalculation.result, false);
assert.ok(dataCalculation.result.facts.every((fact) => fact.source === "mechanical_calculation"));

const dataQualityInspection = inspectDataInput(readFixture("data-analysis-data-quality.csv"));
const dataQualityCalculation = calculateComputedAnalysis(dataQualityInspection, {
  groupColumn: "team",
  metricColumn: "processed_count",
  timeColumn: "period",
});
assert.equal(dataQualityCalculation.ok, true);
assert.deepEqual(dataQualityCalculation.result.calculationBasis.dataQuality, {
  excludedMetricRowCount: 1,
  inputRowCount: 4,
  invalidPeriodRowCount: 1,
  validMetricRowCount: 3,
});
assert.equal(dataQualityCalculation.result.calculationBasis.time?.startPeriod, "2026-01");
assert.equal(dataQualityCalculation.result.calculationBasis.time?.endPeriod, "2026-03");
assert.equal(dataQualityCalculation.result.calculationBasis.time?.periodCount, 2);
assert.equal(dataQualityCalculation.result.calculationBasis.comparison?.groupCount, 2);

const yearlyAggregateInspection = inspectDataInput(readFixture("data-analysis-yearly-aggregate.csv"));
assert.equal(yearlyAggregateInspection.ok, true);
assert.equal(yearlyAggregateInspection.columnOptions.analysisPlan.recommendedTimeColumn, "연도");
assert.equal(yearlyAggregateInspection.columnOptions.analysisPlan.recommendedMetricColumn, "티켓판매액");
assert.equal(yearlyAggregateInspection.columnOptions.analysisPlan.recommendedGroupColumn, "지역");
assert.equal(
  yearlyAggregateInspection.columnOptions.profiles.find((profile) => profile.column === "연도")?.primaryRole,
  "time",
);
assert.ok(yearlyAggregateInspection.columnOptions.analysisPlan.questionSuggestions.some((question) => /기간별 변화/.test(question)));
assert.ok(yearlyAggregateInspection.columnOptions.analysisPlan.warnings.some((warning) => /전체·합계/.test(warning)));

const yearlyAggregateCalculation = calculateComputedAnalysis(yearlyAggregateInspection, {
  groupColumn: yearlyAggregateInspection.columnOptions.analysisPlan.recommendedGroupColumn,
  metricColumn: yearlyAggregateInspection.columnOptions.analysisPlan.recommendedMetricColumn,
  timeColumn: yearlyAggregateInspection.columnOptions.analysisPlan.recommendedTimeColumn,
});
assert.equal(yearlyAggregateCalculation.ok, true);
assert.equal(yearlyAggregateCalculation.result.summary.find((metric) => metric.id === "total")?.value, 650);
assert.equal(yearlyAggregateCalculation.result.calculationBasis.dataQuality.excludedAggregateRowCount, 3);
assert.equal(yearlyAggregateCalculation.result.calculationBasis.dataQuality.validMetricRowCount, 6);
assert.equal(yearlyAggregateCalculation.result.calculationBasis.time?.granularity, "year");
assert.equal(yearlyAggregateCalculation.result.calculationBasis.time?.startPeriod, "2023");
assert.equal(yearlyAggregateCalculation.result.calculationBasis.time?.endPeriod, "2025");
assert.equal(yearlyAggregateCalculation.result.comparisons.some((comparison) => comparison.group === "전체"), false);
assert.equal(yearlyAggregateCalculation.result.calculationBasis.crossAnalysis?.valueCoverage, "complete");
assert.equal(yearlyAggregateCalculation.result.changeContributions[0]?.group, "경기");
assert.ok(yearlyAggregateCalculation.result.reportFindings.some((finding) => finding.type === "contribution"));
assert.ok(yearlyAggregateCalculation.result.followUpQuestions.some((item) => /장르/.test(item.question)));
assert.ok(yearlyAggregateCalculation.result.warnings.some((warning) => /전체·합계/.test(warning)));

const mixedAggregationInspection = inspectDataInput(readFixture("data-analysis-mixed-aggregation.csv"));
assert.equal(mixedAggregationInspection.ok, true);
assert.deepEqual(mixedAggregationInspection.columnOptions.analysisPlan.aggregationStructure.categoryColumns, ["region", "genre"]);
assert.equal(mixedAggregationInspection.columnOptions.analysisPlan.aggregationStructure.aggregateRowCount, 6);
assert.deepEqual(mixedAggregationInspection.columnOptions.analysisPlan.aggregationStructure.levels, [
  { level: 0, rowCount: 2 },
  { level: 1, rowCount: 4 },
  { level: 2, rowCount: 4 },
]);
assert.ok(mixedAggregationInspection.columnOptions.editable.groupColumns.includes("region"));

const mixedAggregationCalculation = calculateComputedAnalysis(mixedAggregationInspection, {
  groupColumn: "region",
  metricColumn: "value",
  timeColumn: "year",
});
assert.equal(mixedAggregationCalculation.ok, true);
assert.equal(mixedAggregationCalculation.result.calculationBasis.dataQuality.excludedAggregateRowCount, 6);
assert.equal(mixedAggregationCalculation.result.summary.find((metric) => metric.id === "total")?.value, 340);
assert.equal(mixedAggregationCalculation.result.comparisons.some((comparison) => comparison.group === "All"), false);
assert.equal(mixedAggregationCalculation.result.calculationBasis.outlierDetection.evaluatedRowCount, 4);

const singlePeriodInspection = inspectDataInput(readFixture("data-analysis-single-period.csv"));
const singlePeriodCalculation = calculateComputedAnalysis(singlePeriodInspection, {
  metricColumn: "value",
  timeColumn: "period",
});
assert.equal(singlePeriodCalculation.ok, true);
assert.equal(singlePeriodCalculation.result.trend, undefined);
assert.equal(singlePeriodCalculation.result.calculationBasis.time?.trendAvailability, "insufficient_periods");
assert.equal(singlePeriodCalculation.result.calculationBasis.time?.periodCount, 1);

const jsonDataInspection = inspectDataInput(JSON.stringify([
  { period: "2026-01", team: "A", value: 10 },
  { period: "2026-02", team: "A", value: 12 },
]));
assert.equal(jsonDataInspection.ok, true);
assert.equal(jsonDataInspection.format, "json");

const stableDataInspection = inspectDataInput(`period,value
2026-01,10
2026-02,10
2026-03,10
2026-04,10`);
const stableDataCalculation = calculateComputedAnalysis(stableDataInspection, {
  metricColumn: "value",
  timeColumn: "period",
});
assert.equal(stableDataCalculation.ok, true);
assert.equal(stableDataCalculation.result.insightCandidates.length, 0);
assert.ok(stableDataCalculation.result.warnings.some((warning) => /강제로 만들지 않습니다/.test(warning)));

const sensitiveDataInspection = inspectDataInput(`period,customer_email,amount
2026-01,alice@example.com,10
2026-01,bob@example.com,8
2026-02,alice@example.com,20
2026-02,bob@example.com,9
2026-03,alice@example.com,30
2026-03,bob@example.com,11
2026-04,alice@example.com,90
2026-04,bob@example.com,12`);
const sensitiveDataCalculation = calculateComputedAnalysis(sensitiveDataInspection, {
  groupColumn: "customer_email",
  metricColumn: "amount",
  timeColumn: "period",
});
assert.equal(sensitiveDataCalculation.ok, true);
const dataInsightsPayload = buildAiDataInsightsPayload(
  sensitiveDataCalculation.result,
  sensitiveAnalysis,
);
const serializedDataInsightsPayload = JSON.stringify(dataInsightsPayload);
assert.match(dataInsightsPayload.instructions, /원본 행 데이터는 제공되지 않았으며/);
assert.match(dataInsightsPayload.instructions, /제공되지 않은 숫자를 생성하지 않는다/);
assert.match(dataInsightsPayload.instructions, /반복 주기나 계절성을 추정하지 마라/);
assert.doesNotMatch(serializedDataInsightsPayload, /alice@example\.com/);
assert.doesNotMatch(serializedDataInsightsPayload, /bob@example\.com/);
assert.doesNotMatch(serializedDataInsightsPayload, /customer_email/);
assert.match(serializedDataInsightsPayload, /그룹 1/);
assert.equal("rows" in dataInsightsPayload.computedAnalysis, false);
assert.equal(dataInsightsPayload.computedAnalysis.contractVersion, COMPUTED_ANALYSIS_CONTRACT_VERSION);
assert.ok(dataInsightsPayload.computedAnalysis.changeContributions.length > 0);
assert.ok(dataInsightsPayload.computedAnalysis.changeContributions.every((item) => /^그룹/.test(item.group)));
assert.equal(dataInsightsPayload.computedAnalysis.calculationBasis.time?.recurrenceAssessment, "not_evaluated");

const normalizedDataInsights = normalizeAiDataInsights({
  conclusion: "계산 결과를 우선 확인하세요.",
  insights: [
    {
      candidateId: "candidate-trend",
      checks: ["업무 환경 변화 여부를 추가 확인하세요."],
      interpretation: ["최근 흐름의 지속 여부를 확인할 필요가 있습니다."],
      proposals: ["다음 기간에도 같은 기준으로 모니터링하세요."],
      title: "처리 흐름 변화",
    },
    {
      candidateId: "candidate-not-found",
      checks: [],
      interpretation: ["제외되어야 합니다."],
      proposals: [],
      title: "근거 없는 후보",
    },
    {
      candidateId: "candidate-comparison",
      checks: [],
      interpretation: ["50% 증가했습니다."],
      proposals: [],
      title: "숫자 50 포함",
    },
  ],
  uncertaintyNotes: ["원인은 추가 확인이 필요합니다."],
}, dataCalculation.result);
assert.equal(normalizedDataInsights.insights.length, 2);
assert.equal(normalizedDataInsights.insights[1]?.interpretation.length, 0);
assert.ok(normalizedDataInsights.validationWarnings.some((warning) => /계산 근거가 확인되지 않은 항목|숫자 표현/.test(warning)));

const dataInsightReport = buildDataInsightMarkdownReport(
  dataCalculation.result,
  normalizedDataInsights,
);
assert.match(dataInsightReport, /## 분석 개요/);
assert.match(dataInsightReport, /## 계산 기준 및 주의 사항/);
assert.match(dataInsightReport, /기간 범위: 2026-05 ~ 2026-08/);
assert.match(dataInsightReport, /## 핵심 지표/);
assert.match(dataInsightReport, /## 주요 결과/);
assert.match(dataInsightReport, /관찰된 사실/);
assert.match(dataInsightReport, /확인 필요 사항/);
assert.doesNotMatch(dataInsightReport, /중요도:/);
assert.doesNotMatch(dataInsightReport, /이상치 후보/);

const missingDataCalculationRoute = await handleAiDataInsightsRequest(
  {},
  {
    env: {
      OPENAI_API_KEY: "test-key",
      OPENAI_MODEL: "test-model",
    },
    fetcher: async () => {
      throw new Error("invalid data must not call provider");
    },
  },
);
assert.equal(missingDataCalculationRoute.status, 400);
assert.match(missingDataCalculationRoute.body.error, /기계식 계산 결과/);

const invalidContractDataRoute = await handleAiDataInsightsRequest(
  {
    computedAnalysis: {
      ...dataCalculation.result,
      contractVersion: "computed-analysis-v0",
    },
  },
  {
    env: {},
    fetcher: async () => {
      throw new Error("invalid contract must not call provider");
    },
  },
);
assert.equal(invalidContractDataRoute.status, 400);
assert.match(invalidContractDataRoute.body.error, /기계식 계산 결과/);

const rawRowsDataRoute = await handleAiDataInsightsRequest(
  {
    computedAnalysis: {
      ...dataCalculation.result,
      rows: [{ processed_count: "999", team: "not-for-ai" }],
    },
  },
  {
    env: {},
    fetcher: async () => {
      throw new Error("raw rows must not call provider");
    },
  },
);
assert.equal(rawRowsDataRoute.status, 400);
assert.match(rawRowsDataRoute.body.error, /원본 행 데이터는 AI 요청에 포함할 수 없습니다/);

const noCandidateRoute = await handleAiDataInsightsRequest(
  { computedAnalysis: stableDataCalculation.result },
  {
    env: {
      OPENAI_API_KEY: "test-key",
      OPENAI_MODEL: "test-model",
    },
    fetcher: async () => {
      throw new Error("empty candidates must not call provider");
    },
  },
);
assert.equal(noCandidateRoute.status, 400);
assert.match(noCandidateRoute.body.error, /인사이트 후보가 없습니다/);

let sentDataInsightsRequest = "";
const mockDataInsightsRoute = await handleAiDataInsightsRequest(
  { computedAnalysis: sensitiveDataCalculation.result, sqlAnalysis: sensitiveAnalysis },
  {
    env: {
      OPENAI_API_KEY: "test-key",
      OPENAI_MODEL: "test-model",
    },
    fetcher: async (_url, init) => {
      sentDataInsightsRequest = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          output_text: JSON.stringify({
            conclusion: "기계식 계산 결과와 함께 변화 요인을 확인하세요.",
            insights: [
              {
                candidateId: "candidate-trend",
                checks: ["업무 조건 변화 여부를 확인하세요."],
                interpretation: ["최근 변화 흐름은 운영 관점에서 확인할 가치가 있습니다."],
                proposals: ["같은 기준으로 다음 기간을 점검하세요."],
                title: "최근 변화 흐름",
              },
            ],
            uncertaintyNotes: ["원인은 계산 결과만으로 확정할 수 없습니다."],
          }),
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      );
    },
  },
);
assert.equal(mockDataInsightsRoute.status, 200);
assert.equal(mockDataInsightsRoute.body.insights.insights.length, 1);
assert.doesNotMatch(sentDataInsightsRequest, /alice@example\.com/);
assert.doesNotMatch(sentDataInsightsRequest, /bob@example\.com/);
assert.doesNotMatch(sentDataInsightsRequest, /"rows"/);

const workerAssets = {
  fetch: async () => new Response("asset response", { status: 200 }),
};
const unconfiguredWorkerRuntime = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/runtime-config"),
  { ASSETS: workerAssets },
);
assert.equal(unconfiguredWorkerRuntime.status, 200);
assert.deepEqual(await unconfiguredWorkerRuntime.json(), {
  aiConfigured: false,
  aiEnabled: false,
  authenticated: false,
  loginRequired: false,
});

const protectedWorkerEnv = {
  AI_PROVIDER: "openai",
  ASSETS: workerAssets,
  DEMO_PASSWORD: "demo-password",
  DEMO_SESSION_SECRET: "test-session-secret",
  DEMO_USERNAME: "demo-user",
  OPENAI_API_KEY: "test-key",
  OPENAI_MODEL: "test-model",
};

const publicWorkerAssetResponse = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/"),
  protectedWorkerEnv,
);
assert.equal(await publicWorkerAssetResponse.text(), "asset response");

const signedOutWorkerRuntime = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/runtime-config"),
  protectedWorkerEnv,
);
assert.deepEqual(await signedOutWorkerRuntime.json(), {
  aiConfigured: true,
  aiEnabled: false,
  authenticated: false,
  loginRequired: true,
});

const unauthenticatedAiResponse = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/ai-explain", {
    body: "{}",
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
  }),
  protectedWorkerEnv,
);
assert.equal(unauthenticatedAiResponse.status, 401);
assert.match((await unauthenticatedAiResponse.json()).error, /로그인한 테스트 계정/);

const invalidLoginResponse = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/auth/login", {
    body: JSON.stringify({ password: "wrong-password", username: "demo-user" }),
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
  }),
  protectedWorkerEnv,
);
assert.equal(invalidLoginResponse.status, 401);
assert.match((await invalidLoginResponse.json()).error, /아이디 또는 비밀번호/);

const loginResponse = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/auth/login", {
    body: JSON.stringify({ password: "demo-password", username: "demo-user" }),
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
  }),
  protectedWorkerEnv,
);
assert.equal(loginResponse.status, 200);
assert.equal((await loginResponse.clone().json()).authenticated, true);
assert.equal((await loginResponse.clone().json()).aiEnabled, true);
const loginCookie = loginResponse.headers.get("Set-Cookie") ?? "";
assert.match(loginCookie, /__Host-sql-diagnoser-demo=/);
assert.match(loginCookie, /HttpOnly/);
assert.match(loginCookie, /Secure/);
assert.match(loginCookie, /SameSite=Strict/);
const sessionCookie = loginCookie.split(";")[0];

const protectedWorkerInvalidAiRequest = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/ai-explain", {
    body: "{}",
    headers: {
      Cookie: sessionCookie,
      "Content-Type": "application/json",
    },
    method: "POST",
  }),
  protectedWorkerEnv,
);
assert.equal(protectedWorkerInvalidAiRequest.status, 400);
assert.match((await protectedWorkerInvalidAiRequest.json()).error, /분석할 SQL/);

const authenticatedWorkerRuntime = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/runtime-config", {
    headers: { Cookie: sessionCookie },
  }),
  protectedWorkerEnv,
);
assert.deepEqual(await authenticatedWorkerRuntime.json(), {
  aiConfigured: true,
  aiEnabled: true,
  authenticated: true,
  loginRequired: true,
  username: "demo-user",
});

const logoutResponse = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/auth/logout", {
    headers: { Cookie: sessionCookie },
    method: "POST",
  }),
  protectedWorkerEnv,
);
assert.equal(logoutResponse.status, 200);
assert.match(logoutResponse.headers.get("Set-Cookie") ?? "", /Max-Age=0/);

const localOllamaWorkerRuntime = await cloudflareWorker.fetch(
  new Request("https://sql-diagnoser-demo.example/api/runtime-config", {
    headers: { Cookie: sessionCookie },
  }),
  {
    AI_PROVIDER: "ollama",
    ASSETS: workerAssets,
    DEMO_PASSWORD: "demo-password",
    DEMO_SESSION_SECRET: "test-session-secret",
    DEMO_USERNAME: "demo-user",
    OLLAMA_BASE_URL: "http://localhost:11434",
    OLLAMA_MODEL: "qwen3:14b",
  },
);
assert.equal((await localOllamaWorkerRuntime.json()).aiEnabled, false);

console.log("sqlExplainer tests passed");
