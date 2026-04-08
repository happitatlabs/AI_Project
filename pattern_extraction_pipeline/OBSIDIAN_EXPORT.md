---
title: Pattern Extraction Pipeline - Minimal Skeleton
tags:
  - sql
  - pattern-extraction
  - training-data
  - pipeline
created: 2026-04-06
---

# Pattern Extraction Pipeline 구축 메모

## 개요

익명화된 SQL / 구조 자산에서 실무 패턴을 추출하고, 향후 추천 엔진이 사용할 학습 재료(JSON / bundle)로 저장하는 최소 실행 파이프라인을 별도 프로젝트로 구축했다.

이번 작업 범위는 추천 엔진 본체가 아니라, 추천 엔진이 사용할 **학습 재료 생성 파이프라인**이다.

## 핵심 목표

- 샘플 SQL 1개 입력
- normalization 수행
- 패턴 최소 1개 이상 추출
- 결과 JSON 저장
- training bundle 생성

## 절대 제약 반영

- 멜로우 엔진 본체 코드 수정 없음
- 추천 로직 구현 없음
- 벡터 DB 연동 없음
- 과도한 추상화 없음
- 실제 실행 가능한 최소 골격만 구현

## 파이프라인 단계

1. `input_loader`
   - 익명화된 SQL / 구조 자산 입력 로드
2. `normalizer`
   - SQL 공백 / 키워드 정리
   - 의미 변경 없이 구조 유지
3. `pattern_extractor`
   - `join_style`
   - `where_condition_style`
   - `subquery_usage`
   - `grouping_style`
4. `pattern_serializer`
   - 결과를 JSON 파일로 저장
5. `training_bundle_builder`
   - 추출 결과를 bundle JSON으로 묶음

## 결과 포맷

```json
{
  "source_id": "string",
  "normalized_sql": "string",
  "patterns": [
    {
      "type": "string",
      "description": "string",
      "evidence": ["string"]
    }
  ]
}
```

## 생성 파일 목록

- `pattern_extraction_pipeline/pipeline/README.md`
- `pattern_extraction_pipeline/pipeline/input_loader.py`
- `pattern_extraction_pipeline/pipeline/normalizer.py`
- `pattern_extraction_pipeline/pipeline/pattern_extractor.py`
- `pattern_extraction_pipeline/pipeline/pattern_serializer.py`
- `pattern_extraction_pipeline/pipeline/training_bundle_builder.py`
- `pattern_extraction_pipeline/pipeline/main.py`
- `pattern_extraction_pipeline/OBSIDIAN_EXPORT.md`

## 디렉터리 구조

```text
pattern_extraction_pipeline/
├─ OBSIDIAN_EXPORT.md
└─ pipeline/
   ├─ README.md
   ├─ input_loader.py
   ├─ normalizer.py
   ├─ pattern_extractor.py
   ├─ pattern_serializer.py
   ├─ training_bundle_builder.py
   ├─ main.py
   └─ output/
      ├─ sample_sql_001_patterns.json
      └─ training_bundle.json
```

## 실행 방법

프로젝트 루트에서:

```powershell
python pattern_extraction_pipeline/pipeline/main.py
```

또는 `pipeline` 디렉터리에서:

```powershell
python main.py
```

## 실행 결과 경로

- 결과 JSON: `pattern_extraction_pipeline/pipeline/output/sample_sql_001_patterns.json`
- bundle JSON: `pattern_extraction_pipeline/pipeline/output/training_bundle.json`

## 검증 결과

2026-04-06 기준 실제 실행 검증 완료.

- 샘플 SQL 입력 성공
- normalization 수행 성공
- 4개 패턴 추출 성공
- 결과 JSON 저장 성공
- training bundle 저장 성공

추출된 패턴 예시:

- `join_style`
- `where_condition_style`
- `subquery_usage`
- `grouping_style`

## 파일 코드

### `pipeline/README.md`

```markdown
# Pattern Extraction Pipeline

익명화된 SQL 자산에서 실무 패턴을 추출해 추천 엔진이 사용할 학습 재료로 저장하는 최소 실행 골격입니다.

## 구성 단계

1. `input_loader`: SQL 입력 로드
2. `normalizer`: SQL 포맷 정리
3. `pattern_extractor`: 패턴 추출 및 evidence 수집
4. `pattern_serializer`: 결과 JSON 저장
5. `training_bundle_builder`: 결과를 bundle로 묶기

## 결과 스키마

```json
{
  "source_id": "string",
  "normalized_sql": "string",
  "patterns": [
    {
      "type": "string",
      "description": "string",
      "evidence": ["string"]
    }
  ]
}
```

## 실행 방법

프로젝트 루트에서:

```powershell
python pattern_extraction_pipeline/pipeline/main.py
```

또는 `pipeline` 디렉터리에서:

```powershell
python main.py
```

실행 후 `pipeline/output/` 아래에 패턴 결과 JSON과 training bundle JSON이 생성됩니다.
```

### `pipeline/input_loader.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


def load_source(
    source_id: str,
    sql_text: str,
    structure_asset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not source_id.strip():
        raise ValueError("source_id must not be empty.")
    if not sql_text.strip():
        raise ValueError("sql_text must not be empty.")

    return {
        "source_id": source_id.strip(),
        "sql": sql_text.strip(),
        "structure_asset": structure_asset or {},
    }


def load_source_from_file(
    file_path: str | Path,
    source_id: str | None = None,
    structure_asset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(file_path)
    sql_text = path.read_text(encoding="utf-8")
    return load_source(source_id or path.stem, sql_text, structure_asset)
```

### `pipeline/normalizer.py`

```python
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
```

### `pipeline/pattern_extractor.py`

```python
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
```

### `pipeline/pattern_serializer.py`

```python
from __future__ import annotations

import json
from pathlib import Path


def build_pattern_result(
    source_id: str,
    normalized_sql: str,
    patterns: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "normalized_sql": normalized_sql,
        "patterns": patterns,
    }


def save_pattern_result(result: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
```

### `pipeline/training_bundle_builder.py`

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def build_training_bundle(
    results: list[dict[str, object]],
    output_path: str | Path,
) -> tuple[dict[str, object], Path]:
    bundle = {
        "bundle_name": "pattern_training_bundle",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "item_count": len(results),
        "source_ids": [result["source_id"] for result in results],
        "items": results,
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return bundle, path
```

### `pipeline/main.py`

```python
from __future__ import annotations

import json
from pathlib import Path

from input_loader import load_source
from normalizer import normalize_sql
from pattern_extractor import extract_patterns
from pattern_serializer import build_pattern_result, save_pattern_result
from training_bundle_builder import build_training_bundle

SAMPLE_SQL = """
select
    o.customer_id,
    c.customer_name,
    sum(o.total_amount) as total_amount
from orders o
inner join customers c on c.customer_id = o.customer_id
where o.status = 'APPROVED'
  and o.customer_id in (
      select customer_id
      from customer_segments
      where segment_code = 'VIP'
  )
group by o.customer_id, c.customer_name
having sum(o.total_amount) > 1000
"""


def run_pipeline(source_id: str = "sample_sql_001", sql_text: str = SAMPLE_SQL) -> dict[str, object]:
    source = load_source(source_id=source_id, sql_text=sql_text)
    normalized_sql = normalize_sql(source["sql"])
    patterns = extract_patterns(normalized_sql)

    if not patterns:
        raise RuntimeError("No patterns were extracted from the normalized SQL.")

    result = build_pattern_result(
        source_id=source["source_id"],
        normalized_sql=normalized_sql,
        patterns=patterns,
    )

    output_dir = Path(__file__).resolve().parent / "output"
    result_path = save_pattern_result(
        result,
        output_dir / f"{source['source_id']}_patterns.json",
    )
    _, bundle_path = build_training_bundle(
        [result],
        output_dir / "training_bundle.json",
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved result JSON: {result_path}")
    print(f"Saved training bundle: {bundle_path}")
    return result


if __name__ == "__main__":
    run_pipeline()
```

## 샘플 실행 결과 요약

```json
{
  "source_id": "sample_sql_001",
  "patterns": [
    {
      "type": "join_style",
      "description": "Uses explicit INNER JOIN clauses with ON predicates to connect source tables."
    },
    {
      "type": "where_condition_style",
      "description": "Applies AND-connected row filters in WHERE and relies on IN-based predicates."
    },
    {
      "type": "subquery_usage",
      "description": "Uses nested SELECT subqueries as part of the filtering logic."
    },
    {
      "type": "grouping_style",
      "description": "Groups aggregated rows by o.customer_id, c.customer_name. Applies a HAVING filter after aggregation."
    }
  ]
}
```

## 메모

- 현재 구현은 최소 실행 골격이다.
- 실제 익명화 파이프라인 산출물 연동은 `load_source_from_file()` 또는 별도 asset adapter를 확장하면 된다.
- 추천 로직 / 랭킹 / 벡터화 / 임베딩 저장은 이번 범위에 포함하지 않았다.
