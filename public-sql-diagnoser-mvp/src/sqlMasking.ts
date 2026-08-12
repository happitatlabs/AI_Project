const EMAIL_PATTERN = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;
const PHONE_PATTERN = /(?:\+?\d{1,3}[-.\s]?)?(?:0\d{1,2}|01\d)[-.\s]?\d{3,4}[-.\s]?\d{4}\b/;
const UUID_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i;
const LONG_TOKEN_PATTERN =
  /\b(?:sk|pk|api|tok|token|secret|bearer|key)[_-]?[A-Za-z0-9_-]{16,}\b/i;
const LONG_RANDOM_PATTERN = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]{24,}$/;
const LONG_NUMBER_PATTERN = /\b\d{12,}\b/;
const SENSITIVE_COLUMN_PATTERN =
  /\b(email|mail|phone|mobile|tel|token|secret|password|passwd|api_?key|access_?key|refresh_?key|uuid|guid|ssn|resident|account_?no|card_?no|customer_?id|user_?id)\b/i;

const escapeSqlLiteral = (value: string) => value.replace(/'/g, "''");

const unescapeSqlLiteral = (value: string) => value.replace(/''/g, "'");

const extractImmediateColumnContext = (prefix: string) => {
  const match = prefix.match(
    /(?:^|[\s(])([A-Za-z0-9_$#."`\[\]]+)\s*(?:=|<>|!=|LIKE|IN\s*\(?)\s*$/i,
  );

  return match?.[1] ?? "";
};

const classifySensitiveValue = (value: string, prefix: string) => {
  const unescapedValue = unescapeSqlLiteral(value).trim();
  const columnContext = extractImmediateColumnContext(prefix);
  const hasSensitiveColumnContext = SENSITIVE_COLUMN_PATTERN.test(columnContext);

  if (EMAIL_PATTERN.test(unescapedValue)) {
    return "[REDACTED_EMAIL]";
  }

  if (PHONE_PATTERN.test(unescapedValue)) {
    return "[REDACTED_PHONE]";
  }

  if (UUID_PATTERN.test(unescapedValue)) {
    return "[REDACTED_UUID]";
  }

  if (
    LONG_TOKEN_PATTERN.test(unescapedValue) ||
    LONG_RANDOM_PATTERN.test(unescapedValue)
  ) {
    return "[REDACTED_TOKEN]";
  }

  if (LONG_NUMBER_PATTERN.test(unescapedValue)) {
    return "[REDACTED_NUMBER]";
  }

  if (hasSensitiveColumnContext && unescapedValue.length > 0) {
    return "[REDACTED_VALUE]";
  }

  return null;
};

const maskStringLiterals = (sql: string) =>
  sql.replace(/'((?:''|[^'])*)'/g, (literal, value, offset) => {
    const replacement = classifySensitiveValue(value, sql.slice(0, offset));

    if (!replacement) {
      return literal;
    }

    return `'${escapeSqlLiteral(replacement)}'`;
  });

const maskBareSensitiveValues = (sql: string) =>
  sql
    .replace(UUID_PATTERN, "[REDACTED_UUID]")
    .replace(LONG_TOKEN_PATTERN, "[REDACTED_TOKEN]")
    .replace(LONG_NUMBER_PATTERN, "[REDACTED_NUMBER]");

export const maskSensitiveSql = (sql: string) =>
  maskBareSensitiveValues(maskStringLiterals(sql));

export const maskSensitiveText = (value: string) =>
  value
    .replace(new RegExp(EMAIL_PATTERN.source, "gi"), "[REDACTED_EMAIL]")
    .replace(new RegExp(PHONE_PATTERN.source, "g"), "[REDACTED_PHONE]")
    .replace(new RegExp(UUID_PATTERN.source, "gi"), "[REDACTED_UUID]")
    .replace(new RegExp(LONG_TOKEN_PATTERN.source, "gi"), "[REDACTED_TOKEN]")
    .replace(new RegExp(LONG_NUMBER_PATTERN.source, "g"), "[REDACTED_NUMBER]");
