import { splitSqlStatements } from "./multiSqlAnalysis.js";
import { tokenizeSql } from "./sqlChangeScope.js";

export const SIGNUP_CREDITS = 10;
export const CREDIT_OPERATIONS = {
  single: { label: "SQL 단건 AI 진단", cost: 1 },
  multi: { label: "SQL 다건 AI 진단", cost: 2 },
  document: { label: "단건 AI 문서화", cost: 1 },
  multiDocument: { label: "다건 AI 문서화", cost: 2 },
  insights: { label: "데이터 인사이트", cost: 3 },
  rewrite: { label: "변경 후 SQL 추천", cost: 3 },
} as const;
export type CreditOperation = keyof typeof CREDIT_OPERATIONS;
export type CreditBalance = { remaining: number | null; unlimited: boolean };
export const CREDIT_PACKS = [30, 100, 300].map(credits => ({
  id: `credits-${credits}`, credits, price: null, currency: "KRW", available: false,
}));

// Costs come from the operation and SQL on the server, never a submitted credit amount.
export function resolveCreditOperation(path: string, body: unknown): CreditOperation {
  if (path === "/api/ai-data-insights") return "insights";
  if (path === "/api/ai-sql-rewrite") return "rewrite";
  if (path === "/api/ai-multi-document-draft") return "multiDocument";
  const value = body && typeof body === "object" ? body as { sql?: unknown; mode?: unknown } : {};
  // Ignore comment-only fragments and protect quoted semicolons, including dollar strings.
  const tokens = typeof value.sql === "string" ? tokenizeSql(value.sql).tokens : [];
  const statementText = tokens.map(token => token.kind === "hint" ? "" : token.kind === "literal" ? "'value'" : token.kind === "quoted" ? '"identifier"' : token.text).join(" ");
  const multi = value.mode === "multi" || splitSqlStatements(statementText).length > 1;
  if (path === "/api/ai-document-draft") return multi ? "multiDocument" : "document";
  return multi ? "multi" : "single";
}

export const creditCostLabel = (operation: CreditOperation) => {
  const cost = CREDIT_OPERATIONS[operation].cost;
  return `${cost} Credit${cost === 1 ? "" : "s"}`;
};
