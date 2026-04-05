import json
from pathlib import Path

import yaml


SAMPLE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "modules"
    / "rebuild_assistant"
    / "samples"
    / "07_order_closure_false_positive_minimal"
)


def test_order_closure_false_positive_sample_manifest_is_followup_only():
    manifest = json.loads((SAMPLE_ROOT / "input_manifest.json").read_text(encoding="utf-8"))
    assertions = yaml.safe_load((SAMPLE_ROOT / "expected_assertions.yaml").read_text(encoding="utf-8"))

    assert manifest["sample_id"] == "07_order_closure_false_positive_minimal"
    assert manifest["expected_focus"]["sample_role"] == "heuristic_followup_reference"
    assert manifest["expected_focus"]["false_positive_risk"] == "domain_anchor_spillover"
    assert assertions["assertions"]["draft_notes"]["regression_status"] == "not_included"
    assert "order_closure" in assertions["assertions"]["intended_observation"]["disallowed_domain_anchors"]


def test_order_closure_false_positive_sample_uses_suspicious_tokens_without_business_anchor():
    asset_paths = [
        SAMPLE_ROOT / "assets" / "review_queue_controller.py",
        SAMPLE_ROOT / "assets" / "review_queue_page.html",
        SAMPLE_ROOT / "assets" / "review_queue.sql",
        SAMPLE_ROOT / "assets" / "schema.sql",
        SAMPLE_ROOT / "assets" / "usecase.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in asset_paths)

    assert "review_required" in text
    assert "display_order" in text
    assert "closeDialog" in text
    assert "order_closure" not in text
    assert "주문 마감" not in text
