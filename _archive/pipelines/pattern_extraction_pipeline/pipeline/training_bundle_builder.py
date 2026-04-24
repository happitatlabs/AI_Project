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
