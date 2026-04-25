from __future__ import annotations

from mellow_link.services.anonymization import build_display_review_report, to_display_text

from .test_anonymization_review_report import _run_review_pipeline


def test_display_adapter_converts_internal_candidate_markers_to_display_markers():
    rendered = to_display_text("[RISK_PERSON_CANDIDATE]의 [RISK_ORG_CANDIDATE] 제안")

    assert rendered == "[PERSON]의 [ORG] 제안"


def test_display_adapter_converts_internal_role_tokens_to_display_markers():
    rendered = to_display_text("CLIENT_001의 PROJECT_001 구축")

    assert rendered == "[CLIENT]의 [PROJECT] 구축"


def test_display_adapter_keeps_internal_review_report_and_safe_bundle_unchanged():
    result = _run_review_pipeline()

    assert result.review_report is not None
    raw_preview = result.review_report.asset_previews[0].preview_text
    display_report = build_display_review_report(result.review_report)
    display_preview = display_report["asset_previews"][0]["preview_text"]
    canonical = result.safe_bundle.sources[0].content

    assert "[RISK_ORG_CANDIDATE]" in raw_preview
    assert "[WARNING_BUSINESS_CANDIDATE]" in raw_preview
    assert "[ORG]" in display_preview
    assert "[BUSINESS]" in display_preview
    assert "[RISK_ORG_CANDIDATE]" not in display_preview
    assert "[WARNING_BUSINESS_CANDIDATE]" not in display_preview
    assert "[RISK_ORG_CANDIDATE]" in result.review_report.asset_previews[0].preview_text
    assert "CLIENT_001" in canonical
    assert "[CLIENT]" not in canonical


def test_display_adapter_never_restores_raw_sensitive_text():
    result = _run_review_pipeline()

    assert result.review_report is not None
    display_report = build_display_review_report(result.review_report)
    serialized = str(display_report)

    for raw_value in (
        "한국전력공사",
        "산업통상자원부",
        "홍길동",
        "Project Apollo Modernization",
        "hgd@example.com",
        "한국지역난방공사",
    ):
        assert raw_value not in serialized
