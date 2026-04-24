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
