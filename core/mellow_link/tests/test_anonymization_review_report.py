from __future__ import annotations

import json

from mellow_link.services.anonymization import (
    AnonymizationAsset,
    AnonymizationRunRequest,
    AnonymizationService,
    build_debug_anonymization_report_from_bundle,
)


def _review_sample_sml() -> str:
    return "\n".join(
        [
            "[SML v1]",
            "presentation_file: review_deck.pptx",
            "slide_count: 2",
            "",
            "[SLIDE 1]",
            "title: 차세대 ERP 구축 사업",
            "texts:",
            "- 고객사: 한국전력공사",
            "- 기관명: 산업통상자원부",
            "- 담당자: 홍길동 PM",
            "- 프로젝트명: Project Apollo Modernization",
            "- 이메일: hgd@example.com",
            "",
            "[SLIDE 2]",
            "title: 정산 통합 사업",
            "texts:",
            "- 한국지역난방공사와 공동 추진",
            "- API /finance/payments",
        ]
    )


def _run_review_pipeline():
    return AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_review_report",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_review_001",
                    name="review_deck.pptx",
                    temp_file_id="temp_review_001",
                    kind_hint="presentation",
                    content_text=_review_sample_sml(),
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )


def _label_less_person_filter_sml() -> str:
    return "\n".join(
        [
            "[SML v1]",
            "presentation_file: person_filter_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 분석 범위 검토",
            "texts:",
            "- 원가 분석 시스템 구축",
            "- 업무 흐름도 및 데이터 처리 구조",
            "- 담당 홍길동",
            "- 문의: 홍길동 / hgd@example.com",
            "- ABC컨설팅",
            "- 홍길동 분석 시스템 구축",
        ]
    )


def _run_label_less_person_filter_pipeline():
    return AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_person_filter",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_person_filter_001",
                    name="person_filter_deck.pptx",
                    temp_file_id="temp_person_filter_001",
                    kind_hint="presentation",
                    content_text=_label_less_person_filter_sml(),
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )


def test_review_report_summarizes_role_tokens_and_detected_types():
    result = _run_review_pipeline()

    assert result.review_report is not None
    report = result.review_report

    role_counts = {item.role_kind: item.generated_count for item in report.role_token_summary}
    type_counts = {item.type_key: item.count for item in report.detected_original_types}

    assert role_counts["business_name"] == 1
    assert role_counts["client_name"] == 1
    assert role_counts["organization_name"] == 1
    assert role_counts["person_name"] == 1
    assert role_counts["project_name"] == 1
    assert role_counts["email"] == 1

    assert type_counts["business_name"] == 1
    assert type_counts["client_name"] == 1
    assert type_counts["organization_name"] == 1
    assert type_counts["person_name"] == 1
    assert type_counts["project_name"] == 1
    assert type_counts["email"] == 1


def test_review_report_splits_label_less_candidates_without_leaking_raw_values():
    result = _run_review_pipeline()

    assert result.review_report is not None
    report = result.review_report

    assert report.status == "blocked"
    assert report.llm_send_allowed is False
    assert report.label_less_risks
    assert report.label_less_warnings

    assert any(item.entity_type_guess == "organization_name" for item in report.label_less_risks)
    assert any(item.entity_type_guess == "business_name" for item in report.label_less_warnings)

    preview_text = report.asset_previews[0].preview_text
    assert "[RISK_ORG_CANDIDATE]" in preview_text
    assert "[WARNING_BUSINESS_CANDIDATE]" in preview_text

    report_dump = json.dumps(report.model_dump(), ensure_ascii=False)
    for raw_value in (
        "차세대 ERP 구축 사업",
        "정산 통합 사업",
        "한국전력공사",
        "한국지역난방공사",
        "산업통상자원부",
        "홍길동",
        "hgd@example.com",
    ):
        assert raw_value not in report_dump


def test_review_report_preview_is_safe_and_human_readable():
    result = _run_review_pipeline()

    assert result.review_report is not None
    preview_text = result.review_report.asset_previews[0].preview_text

    assert "[CLIENT]" in preview_text
    assert "[ORG]" in preview_text
    assert "[PERSON]" in preview_text
    assert "[PROJECT]" in preview_text
    assert "[EMAIL]" in preview_text
    assert "[RISK_ORG_CANDIDATE]" in preview_text
    assert "[WARNING_BUSINESS_CANDIDATE]" in preview_text

    for raw_value in (
        "한국전력공사",
        "산업통상자원부",
        "홍길동",
        "Project Apollo Modernization",
        "hgd@example.com",
        "한국지역난방공사",
        "정산 통합 사업",
    ):
        assert raw_value not in preview_text


def test_safe_bundle_masks_label_less_candidates_without_promoting_mapping():
    result = _run_review_pipeline()

    canonical = result.safe_bundle.sources[0].content
    stats = result.safe_bundle.sources[0].replacement_stats

    assert "[RISK_ORG_CANDIDATE]" in canonical
    assert "한국지역난방공사" not in canonical
    assert "한국전력공사" not in canonical
    assert "CLIENT_001" in canonical
    assert "ORG_001" in canonical
    assert "PERSON_001" in canonical
    assert "PROJECT_001" in canonical
    assert "EMAIL_001" in canonical
    assert stats["client_name"] == 1
    assert stats["organization_name"] == 1
    assert stats["person_name"] == 1
    assert stats["project_name"] == 1
    assert stats["email"] == 1


def test_label_less_person_filter_keeps_consulting_terms_and_masks_real_person_and_org():
    result = _run_label_less_person_filter_pipeline()

    assert result.review_report is not None
    report = result.review_report
    preview_text = report.asset_previews[0].preview_text
    canonical = result.safe_bundle.sources[0].content
    report_dump = json.dumps(report.model_dump(), ensure_ascii=False)
    stats = result.safe_bundle.sources[0].replacement_stats

    assert any(item.entity_type_guess == "person_name" for item in report.label_less_risks)
    assert any(item.entity_type_guess == "organization_name" for item in report.label_less_risks)
    assert any(item.entity_type_guess == "low_conf_term" for item in report.label_less_warnings)
    assert "[RISK_PERSON_CANDIDATE]" in preview_text
    assert "[RISK_ORG_CANDIDATE]" in preview_text
    assert "[LOW_CONF_TERM_CANDIDATE]" not in preview_text
    assert "홍길동" not in preview_text
    assert "ABC컨설팅" not in preview_text

    assert "원가 분석 시스템 구축" in canonical
    assert "업무 흐름도 및 데이터 처리 구조" in canonical
    assert "홍길동 분석 시스템 구축" in canonical
    assert "[LOW_CONF_TERM_CANDIDATE]" not in canonical
    assert "담당 [RISK_PERSON_CANDIDATE]" in canonical
    assert "문의: [RISK_PERSON_CANDIDATE] / EMAIL_001" in canonical
    assert "[RISK_ORG_CANDIDATE]" in canonical
    assert "ABC컨설팅" not in canonical

    for term in ("원가", "분석", "시스템", "업무", "흐름도", "데이터", "처리", "구조", "구축"):
        assert term in canonical

    assert stats.get("person_name", 0) == 0
    assert stats.get("organization_name", 0) == 0
    assert stats["email"] == 1
    for raw_value in ("홍길동", "ABC컨설팅"):
        assert raw_value not in report_dump


def test_low_conf_terms_do_not_replace_safe_bundle_text():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: quality_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 원가 관리 검토",
            "texts:",
            "- 원가 시스템의 원가 관리 요구조건 파악",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_low_conf_no_replace",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_low_conf_no_replace",
                    name="quality_deck.pptx",
                    temp_file_id="temp_low_conf_no_replace",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )


def _org_alias_sml(*, include_explicit_client: bool) -> str:
    lines = [
        "[SML v1]",
        "presentation_file: busan_milk_deck.pptx",
        "slide_count: 1",
        "",
        "[SLIDE 1]",
        "title: 부산우유 컨설팅 개요",
        "texts:",
    ]
    if include_explicit_client:
        lines.append("- 고객사: 부산우유 주식회사")
    lines.extend(
        [
            "- 부산우유의 비전",
            "- 부산우유 기초설계서",
            "- 부산우유 원가 시스템 개선",
        ]
    )
    return "\n".join(lines)


def _run_org_alias_pipeline(*, include_explicit_client: bool):
    project_id = "proj_org_alias_explicit" if include_explicit_client else "proj_org_alias_contextual"
    asset_id = "asset_org_alias_explicit" if include_explicit_client else "asset_org_alias_contextual"
    return AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id=project_id,
            assets=[
                AnonymizationAsset(
                    asset_id=asset_id,
                    name="busan_milk_deck.pptx",
                    temp_file_id=f"temp_{asset_id}",
                    kind_hint="presentation",
                    content_text=_org_alias_sml(include_explicit_client=include_explicit_client),
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    canonical = result.safe_bundle.sources[0].content
    assert "원가 시스템의 원가 관리 요구조건 파악" in canonical
    assert "[LOW_CONF_TERM_CANDIDATE]" not in canonical


def test_generic_business_phrases_are_not_replaced_as_org_or_project_candidates():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: generic_terms_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 문서 요약",
            "texts:",
            "- 배경과 필요성",
            "- 기능 진단 및 평가",
            "- 비전",
            "- 기초설계서",
            "- 운영방안",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_generic_terms",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_generic_terms",
                    name="generic_terms_deck.pptx",
                    temp_file_id="temp_generic_terms",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    canonical = result.safe_bundle.sources[0].content
    preview_text = result.review_report.asset_previews[0].preview_text if result.review_report else ""
    assert "배경과 필요성" in canonical
    assert "기능 진단 및 평가" in canonical
    assert "비전" in canonical
    assert "기초설계서" in canonical
    assert "운영방안" in canonical
    assert "[RISK_ORG_CANDIDATE]" not in canonical
    assert "[WARNING_PROJECT_CANDIDATE]" not in canonical
    assert "[RISK_ORG_CANDIDATE]" not in preview_text
    assert "[WARNING_PROJECT_CANDIDATE]" not in preview_text


def test_explicit_org_name_is_still_masked_in_safe_bundle():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: explicit_org_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 원가 시스템 개선",
            "texts:",
            "- 부산우유 주식회사의 원가 시스템 개선",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_explicit_org",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_explicit_org",
                    name="explicit_org_deck.pptx",
                    temp_file_id="temp_explicit_org",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    canonical = result.safe_bundle.sources[0].content
    assert "[RISK_ORG_CANDIDATE]" in canonical
    assert "부산우유 주식회사" not in canonical
    assert "원가 시스템 개선" in canonical


def test_contextual_org_alias_is_promoted_to_high_confidence_org_token():
    result = _run_org_alias_pipeline(include_explicit_client=False)

    assert result.review_report is not None
    canonical = result.safe_bundle.sources[0].content
    preview_text = result.review_report.asset_previews[0].preview_text
    report_dump = json.dumps(result.review_report.model_dump(), ensure_ascii=False)
    stats = result.safe_bundle.sources[0].replacement_stats

    assert "부산우유" not in canonical
    assert "ORG_001" in canonical
    assert "ORG_001의 비전" in canonical
    assert "ORG_001 기초설계서" in canonical
    assert "ORG_001 원가 시스템 개선" in canonical
    assert "부산우유" not in preview_text
    assert "[ORG]" in preview_text
    assert "부산우유" not in report_dump
    assert stats["organization_name"] == 1


def test_explicit_client_alias_reuses_single_high_confidence_token_and_keeps_debug_evidence():
    result = _run_org_alias_pipeline(include_explicit_client=True)

    assert result.review_report is not None
    canonical = result.safe_bundle.sources[0].content
    preview_text = result.review_report.asset_previews[0].preview_text
    stats = result.safe_bundle.sources[0].replacement_stats
    debug_report = build_debug_anonymization_report_from_bundle(
        result.safe_bundle,
        review_report=result.review_report,
    )
    candidate_debug = debug_report.get("candidate_debug") or []

    assert "부산우유" not in canonical
    assert canonical.count("CLIENT_001") >= 4
    assert "CLIENT_001의 비전" in canonical
    assert "CLIENT_001 기초설계서" in canonical
    assert "CLIENT_001 원가 시스템 개선" in canonical
    assert "부산우유" not in preview_text
    assert "[CLIENT]" in preview_text
    assert stats["client_name"] == 1
    assert any(item["raw_value"] == "부산우유" for item in candidate_debug)
    assert any("부산우유의 비전" in item["source_line"] for item in candidate_debug)
    assert any("부산우유 기초설계서" in item["source_line"] for item in candidate_debug)
    assert all(item["reason"] for item in candidate_debug)


def test_preview_quality_summary_tracks_overredaction_signals_without_low_conf_replacement():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: preview_quality_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 문서 점검",
            "texts:",
            "- 배경과 필요성",
            "- 원가 시스템의 원가 관리 요구조건 파악",
            "- 기능 진단 및 평가",
            "- 비전",
            "- 기초설계서",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_preview_quality",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_preview_quality",
                    name="preview_quality_deck.pptx",
                    temp_file_id="temp_preview_quality",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    assert result.review_report is not None
    report = result.review_report
    canonical = result.safe_bundle.sources[0].content
    assert report.preview_quality_status in {"pass", "warning"}
    assert report.low_conf_replacements_blocked == 0
    assert report.replacement_ratio >= 0.0
    assert report.candidate_density >= 0.0
    assert report.hidden_line_ratio >= 0.0
    assert "원가 시스템의 원가 관리 요구조건 파악" in canonical
    assert "[LOW_CONF_TERM_CANDIDATE]" not in canonical


def test_review_report_does_not_revive_low_conf_for_consulting_overview_phrases():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: overview_quality_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 사업의 개요",
            "texts:",
            "- 방향성 수립",
            "- 차세대 경영정보시스템 구축 BPR/ISMP 수립 컨설팅",
            "- 현 시스템과 개선안의 이익분석",
            "- 경영정보시스템의 운영 환경과 기능 분석을 통하여 개선점을 도출하고 최적화된 모델을 구축할 수 있는 구체적인 이행 계획을 수립하고자 함",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_overview_quality",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_overview_quality",
                    name="overview_quality_deck.pptx",
                    temp_file_id="temp_overview_quality",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    assert result.review_report is not None
    report = result.review_report
    low_conf_warnings = [
        item for item in list(report.label_less_warnings or [])
        if str(getattr(item, "entity_type_guess", "") or "").strip() == "low_conf_term"
    ]
    preview_text = report.asset_previews[0].preview_text

    assert low_conf_warnings == []
    assert "[LOW_CONF_TERM_CANDIDATE]" not in preview_text


def test_preview_quality_tracks_candidate_density_and_hidden_line_ratio():
    result = _run_label_less_person_filter_pipeline()

    assert result.review_report is not None
    report = result.review_report
    assert report.candidate_density > 0.0
    assert report.hidden_line_ratio >= 0.0


def test_cost_accounting_terms_are_preserved_in_safe_source_without_dept_candidate_masking():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: cost_terms_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 원가 배부 기준",
            "texts:",
            "- 원가 배부 기준",
            "- 제조경비 배부",
            "- 재료비와 노무비",
            "- 손익분석",
            "- 주관부서: 재무팀",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_cost_terms_preserved",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_cost_terms_preserved",
                    name="cost_terms_deck.pptx",
                    temp_file_id="temp_cost_terms_preserved",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    assert result.review_report is not None
    canonical = result.safe_bundle.sources[0].content
    preview_text = result.review_report.asset_previews[0].preview_text
    report_dump = json.dumps(result.review_report.model_dump(), ensure_ascii=False)

    assert "원가 배부 기준" in canonical
    assert "제조경비 배부" in canonical
    assert "재료비와 노무비" in canonical
    assert "손익분석" in canonical
    assert "[RISK_DEPT_CANDIDATE]" not in canonical
    assert "[RISK_DEPT_CANDIDATE]" not in preview_text
    assert "[RISK_DEPT_CANDIDATE]" not in report_dump
    assert "재무팀" not in canonical
    assert "DEPT_001" in canonical
    assert "재무팀" not in preview_text
    assert "[DEPARTMENT]" in preview_text


def test_bpr_requirement_lines_do_not_create_person_risks_without_explicit_names():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: bpr_requirement_deck.pptx",
            "slide_count: 2",
            "",
            "[SLIDE 1]",
            "title: Ⅴ. 이행계획 수립",
            "texts:",
            "- 이행계획 수립",
            "- 추진조직과 요구사항 정의",
            "",
            "[SLIDE 2]",
            "tables:",
            "| 통합재무 정보 | SFR-A-021 | 예산변경서 작성 | 필수 | 예산담당자가 예산전용신청서 작성하고 승인요청/승인/반려 처리를 할 수 있는 업무 |",
            "| - | TER-001 | 테스트 계획 수립 및 실시 | 필수 | 테스트 계획 수립 및 실시를 위한 요건 |",
            "notes:",
            "- 작성자: 홍길동",
        ]
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_bpr_person_guard",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_bpr_person_guard",
                    name="bpr_requirement_deck.pptx",
                    temp_file_id="temp_bpr_person_guard",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    assert result.review_report is not None
    report = result.review_report
    canonical = result.safe_bundle.sources[0].content

    person_risks = [item for item in report.label_less_risks if item.entity_type_guess == "person_name"]
    assert len(person_risks) == 0
    assert "이행계획 수립" in canonical
    assert "추진조직과 요구사항 정의" in canonical
    assert "작성자: PERSON_001" in canonical
