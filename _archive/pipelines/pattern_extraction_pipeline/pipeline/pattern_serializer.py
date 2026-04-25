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
