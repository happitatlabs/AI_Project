from __future__ import annotations

import re

CLAUSE_STOP = r"(?=\bGROUP BY\b|\bHAVING\b|\bORDER BY\b|$)"

WHERE_SECTION_RE = re.compile(
    rf"\bWHERE\b(?P<body>.*?){CLAUSE_STOP}",
    flags=re.IGNORECASE | re.DOTALL,
)
GROUP_SECTION_RE = re.compile(
    r"\bGROUP BY\b(?P<body>.*?)(?=\bHAVING\b|\bORDER BY\b|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
HAVING_SECTION_RE = re.compile(
    r"\bHAVING\b(?P<body>.*?)(?=\bORDER BY\b|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
SUBQUERY_RE = re.compile(r"\(\s*SELECT\b.*?\)", flags=re.IGNORECASE | re.DOTALL)


def _compact(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s+\)", ")", text)


def _extract_join_style(normalized_sql: str) -> dict[str, object] | None:
    lines = [line.strip() for line in normalized_sql.splitlines()]
    evidence: list[str] = []
    join_types: list[str] = []

    for index, line in enumerate(lines):
        if "JOIN" not in line.upper():
            continue

        evidence.append(line)
        match = re.match(
            r"(?P<join_type>(?:INNER|LEFT|RIGHT|FULL OUTER|FULL|CROSS)?\s*JOIN)\b",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            join_types.append(_compact(match.group("join_type")).upper())

        if index + 1 < len(lines) and lines[index + 1].upper().startswith("ON "):
            evidence.append(lines[index + 1])

    if not evidence:
        return None

    ordered_types = list(dict.fromkeys(join_types or ["JOIN"]))
    description = (
        "Uses explicit "
        + ", ".join(ordered_types)
        + " clauses with ON predicates to connect source tables."
    )
    return {
        "type": "join_style",
        "description": description,
        "evidence": list(dict.fromkeys(evidence)),
    }


def _extract_where_condition_style(normalized_sql: str) -> dict[str, object] | None:
    match = WHERE_SECTION_RE.search(normalized_sql)
    if not match:
        return None

    where_body = _compact(match.group("body"))
    connectors = []
    if re.search(r"\bAND\b", where_body, flags=re.IGNORECASE):
        connectors.append("AND")
    if re.search(r"\bOR\b", where_body, flags=re.IGNORECASE):
        connectors.append("OR")

    predicate_hints = []
    for keyword in ("IN", "EXISTS", "BETWEEN", "LIKE"):
        if re.search(rf"\b{keyword}\b", where_body, flags=re.IGNORECASE):
            predicate_hints.append(keyword)

    if connectors:
        connector_text = "/".join(connectors) + "-connected"
    else:
        connector_text = "direct"

    if predicate_hints:
        predicate_text = ", ".join(predicate_hints) + "-based"
    else:
        predicate_text = "simple"

    description = (
        f"Applies {connector_text} row filters in WHERE and relies on "
        f"{predicate_text} predicates."
    )
    return {
        "type": "where_condition_style",
        "description": description,
        "evidence": [f"WHERE {where_body}"],
    }


def _extract_subquery_usage(normalized_sql: str) -> dict[str, object] | None:
    matches = [_compact(match.group(0)) for match in SUBQUERY_RE.finditer(normalized_sql)]
    if not matches:
        return None

    description = "Uses nested SELECT subqueries as part of the filtering logic."
    return {
        "type": "subquery_usage",
        "description": description,
        "evidence": list(dict.fromkeys(matches)),
    }


def _extract_grouping_style(normalized_sql: str) -> dict[str, object] | None:
    group_match = GROUP_SECTION_RE.search(normalized_sql)
    if not group_match:
        return None

    group_body = _compact(group_match.group("body"))
    columns = [column.strip() for column in group_body.split(",") if column.strip()]
    description = "Groups aggregated rows by " + ", ".join(columns) + "."

    evidence = [f"GROUP BY {group_body}"]
    having_match = HAVING_SECTION_RE.search(normalized_sql)
    if having_match:
        having_body = _compact(having_match.group("body"))
        description += " Applies a HAVING filter after aggregation."
        evidence.append(f"HAVING {having_body}")

    return {
        "type": "grouping_style",
        "description": description,
        "evidence": evidence,
    }


def extract_patterns(normalized_sql: str) -> list[dict[str, object]]:
    extractors = [
        _extract_join_style,
        _extract_where_condition_style,
        _extract_subquery_usage,
        _extract_grouping_style,
    ]

    patterns: list[dict[str, object]] = []
    for extractor in extractors:
        pattern = extractor(normalized_sql)
        if pattern:
            patterns.append(pattern)
    return patterns
