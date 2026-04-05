from __future__ import annotations

import re
from typing import Callable

SINGLE_QUOTED_LITERAL_RE = re.compile(r"('(?:''|[^'])*')")

BREAK_KEYWORDS = [
    "FULL OUTER JOIN",
    "ORDER BY",
    "GROUP BY",
    "INNER JOIN",
    "LEFT JOIN",
    "RIGHT JOIN",
    "FULL JOIN",
    "CROSS JOIN",
    "SELECT",
    "FROM",
    "JOIN",
    "ON",
    "WHERE",
    "HAVING",
    "AND",
    "OR",
]

INLINE_KEYWORDS = [
    "AS",
    "IN",
    "EXISTS",
    "NOT",
    "NULL",
    "IS",
]

BREAK_KEYWORD_RE = re.compile(
    r"\s*(?P<keyword>"
    + "|".join(re.escape(keyword) for keyword in BREAK_KEYWORDS)
    + r")\b",
    flags=re.IGNORECASE,
)


def _transform_outside_literals(sql_text: str, transform: Callable[[str], str]) -> str:
    parts = SINGLE_QUOTED_LITERAL_RE.split(sql_text)
    for index in range(0, len(parts), 2):
        parts[index] = transform(parts[index])
    return "".join(parts)


def _collapse_whitespace(chunk: str) -> str:
    chunk = re.sub(r"\s+", " ", chunk)
    return re.sub(r"\s*,\s*", ", ", chunk)


def _uppercase_inline_keywords(chunk: str) -> str:
    for keyword in INLINE_KEYWORDS:
        chunk = re.sub(
            rf"\b{re.escape(keyword)}\b",
            keyword,
            chunk,
            flags=re.IGNORECASE,
        )
    return chunk


def _break_major_clauses(chunk: str) -> str:
    return BREAK_KEYWORD_RE.sub(
        lambda match: "\n" + match.group("keyword").upper(),
        chunk,
    )


def normalize_sql(sql_text: str) -> str:
    normalized = _transform_outside_literals(sql_text, _collapse_whitespace)
    normalized = _transform_outside_literals(normalized, _uppercase_inline_keywords)
    normalized = _transform_outside_literals(normalized, _break_major_clauses)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    return normalized.strip()
