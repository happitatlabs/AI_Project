export type SqlRewriteRuleSet = {
  version: 1;
  rules: Array<{ id: string; instruction: string }>;
};

// Future rule storage/resolution plugs in here; no custom rules are active yet.
export const resolveSqlRewriteRules = (): SqlRewriteRuleSet => ({ version: 1, rules: [] });
