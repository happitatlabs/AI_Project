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
