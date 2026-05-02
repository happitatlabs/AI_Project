from __future__ import annotations

import re
from pathlib import Path


CRITERIA_PATH = Path(__file__).parent / "fixtures" / "type_surface_review_criteria.md"
SAMPLES_PATH = Path(__file__).parent / "fixtures" / "type_surface_test_samples_v1.md"


def _criterion_count(text: str, prefix: str) -> int:
    return len(re.findall(rf"^- \[{re.escape(prefix)}\d{{2}}\]", text, flags=re.MULTILINE))


def test_type_surface_review_criteria_file_exists_and_has_template():
    text = CRITERIA_PATH.read_text(encoding="utf-8")

    assert "# Type Surface Review Criteria v1" in text
    assert "# Type Surface Review Report" in text
    assert "input_type_expected: document / code / mixed" in text
    assert "| severity | category | finding | expected | suggested_fix |" in text


def test_type_surface_review_criteria_covers_common_and_all_input_types():
    text = CRITERIA_PATH.read_text(encoding="utf-8")

    for heading in (
        "## Common Criteria",
        "## Document Criteria",
        "## Code Criteria",
        "## Mixed Criteria",
    ):
        assert heading in text


def test_type_surface_review_criteria_has_minimum_fail_and_warn_items():
    text = CRITERIA_PATH.read_text(encoding="utf-8")

    for prefix in (
        "COMMON-F",
        "COMMON-W",
        "DOCUMENT-F",
        "DOCUMENT-W",
        "CODE-F",
        "CODE-W",
        "MIXED-F",
        "MIXED-W",
    ):
        assert _criterion_count(text, prefix) >= 5


def test_type_surface_review_criteria_fixes_external_status_wording():
    text = CRITERIA_PATH.read_text(encoding="utf-8")

    for label in (
        "실행 착수 가능",
        "조건 확인 후 실행",
        "검증 후 적용",
        "실행 불가",
    ):
        assert label in text


def test_type_surface_review_samples_cover_document_code_and_mixed():
    text = SAMPLES_PATH.read_text(encoding="utf-8")

    assert "## CODE Sample: SQL JOIN Query" in text
    assert "## CODE Sample: Pre-save Validation Logic" in text
    assert "## DOCUMENT Sample: Approval Process Description" in text
    assert "## MIXED Sample: Description Plus SQL" in text
    for heading in ("핵심 문제:", "영향:", "권장 조치:", "검증 포인트:", "문제:", "선택지:", "결론:", "문서 요약:"):
        assert heading in text
