from __future__ import annotations

from mellow_link.services.anonymization import (
    AnonymizationAsset,
    AnonymizationRunRequest,
    AnonymizationService,
    CanonicalAnonymizedSource,
    DocumentEntityTokenizer,
    MaskingLevel,
    build_preview_masked_text,
)
from mellow_link.services.anonymization.masking_policy import MaskingPolicyApplier


def _sample_sml() -> str:
    return "\n".join(
        [
            "[SML v1]",
            "presentation_file: consulting_deck.pptx",
            "slide_count: 1",
            "",
            "[SLIDE 1]",
            "title: 차세대 ERP 구축 사업",
            "texts:",
            "- 고객사: 한국전력공사",
            "- 기관명: 산업통상자원부",
            "- 주관부서: 디지털전환본부",
            "- 담당자: 홍길동 PM",
            "- 프로젝트명: Project Apollo Modernization",
            "- 계약명: 2026 ERP 통합 고도화 계약",
            "- 수행사: 주식회사 아크테크",
            "- 사업명: 에너지 데이터 통합 사업",
            "- 이메일: hgd@example.com",
            "- 전화: 02-1234-5678",
            "- 주소: 서울특별시 중구 세종대로 110",
            "- API /finance/payments",
        ]
    )


def test_document_entity_tokenizer_targets_sml_only():
    tokenizer = DocumentEntityTokenizer()

    sml_tokens = tokenizer.tokenize(
        AnonymizationAsset(
            asset_id="asset_sml",
            name="deck.pptx",
            temp_file_id="temp_sml",
            kind_hint="presentation",
            content_text=_sample_sml(),
        )
    )
    regular_doc_tokens = tokenizer.tokenize(
        AnonymizationAsset(
            asset_id="asset_doc",
            name="notes.md",
            temp_file_id="temp_doc",
            kind_hint="doc",
            content_text="고객사: 한국전력공사\n담당자: 홍길동",
        )
    )

    token_map = {token.kind: token.value for token in sml_tokens}
    assert token_map["client_name"] == "한국전력공사"
    assert token_map["organization_name"] == "산업통상자원부"
    assert token_map["department_name"] == "디지털전환본부"
    assert token_map["person_name"] == "홍길동"
    assert token_map["project_name"] == "Project Apollo Modernization"
    assert token_map["contract_name"] == "2026 ERP 통합 고도화 계약"
    assert token_map["company_name"] == "주식회사 아크테크"
    assert token_map["business_name"] == "에너지 데이터 통합 사업"
    assert token_map["email"] == "hgd@example.com"
    assert token_map["phone"] == "02-1234-5678"
    assert token_map["address"] == "서울특별시 중구 세종대로 110"
    assert regular_doc_tokens == []


def test_sml_document_entities_use_role_preserving_replacements():
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_doc_sml",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_001",
                    name="deck.pptx",
                    temp_file_id="temp_001",
                    kind_hint="presentation",
                    content_text=_sample_sml(),
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    )

    canonical = result.safe_bundle.sources[0].content
    stats = result.safe_bundle.sources[0].replacement_stats

    for original in (
        "한국전력공사",
        "산업통상자원부",
        "디지털전환본부",
        "홍길동",
        "Project Apollo Modernization",
        "2026 ERP 통합 고도화 계약",
        "주식회사 아크테크",
        "에너지 데이터 통합 사업",
        "hgd@example.com",
        "02-1234-5678",
        "서울특별시 중구 세종대로 110",
    ):
        assert original not in canonical

    for token in (
        "CLIENT_001",
        "ORG_001",
        "DEPT_001",
        "PERSON_001",
        "PROJECT_001",
        "CONTRACT_001",
        "COMPANY_001",
        "BUSINESS_001",
        "EMAIL_001",
        "PHONE_001",
        "ADDRESS_001",
        "API_001",
    ):
        assert token in canonical

    assert stats["client_name"] == 1
    assert stats["organization_name"] == 1
    assert stats["department_name"] == 1
    assert stats["person_name"] == 1
    assert stats["project_name"] == 1
    assert stats["contract_name"] == 1
    assert stats["company_name"] == 1
    assert stats["business_name"] == 1
    assert stats["email"] == 1
    assert stats["phone"] == 1
    assert stats["address"] == 1
    assert stats["api_path"] == 1


def test_preview_and_full_masked_policy_cover_document_tokens():
    preview = build_preview_masked_text("CLIENT_001 works with PERSON_001 via EMAIL_001 at ADDRESS_001")
    masked = MaskingPolicyApplier().apply_source(
        CanonicalAnonymizedSource(
            asset_id="asset_001",
            level=MaskingLevel.FULL,
            content="CLIENT_001 PERSON_001 EMAIL_001 ADDRESS_001",
        ),
        MaskingLevel.FULL_MASKED,
    )

    assert "[CLIENT]" in preview
    assert "[PERSON]" in preview
    assert "[EMAIL]" in preview
    assert "[ADDRESS]" in preview
    assert "CLIENT_001" not in masked.content
    assert "PERSON_001" not in masked.content
    assert masked.content == "MASKED_NODE MASKED_NODE MASKED_NODE MASKED_NODE"


def test_label_less_person_candidates_skip_consulting_terms_and_keep_real_names():
    tokenizer = DocumentEntityTokenizer()

    assert list(tokenizer.iter_label_less_person_candidates("원가 분석 시스템 구축")) == []
    assert list(tokenizer.iter_label_less_person_candidates("업무 흐름도 및 데이터 처리 구조")) == []
    assert list(tokenizer.iter_label_less_person_candidates("홍길동")) == []
    assert list(tokenizer.iter_label_less_person_candidates("홍길동 분석 시스템 구축")) == []
    assert list(tokenizer.iter_label_less_person_candidates("담당 홍길동")) == ["홍길동"]
    assert list(tokenizer.iter_label_less_person_candidates("홍길동 부장")) == ["홍길동"]
    assert list(tokenizer.iter_label_less_person_candidates("문의: 홍길동 / hgd@example.com")) == ["홍길동"]


def test_department_detection_preserves_cost_accounting_terms():
    tokenizer = DocumentEntityTokenizer()

    assert tokenizer._looks_like_department("재무팀") is True
    assert tokenizer._looks_like_department("회계부") is True
    assert tokenizer._looks_like_department("전산실") is True
    assert tokenizer._looks_like_department("생산관리팀") is True
    assert tokenizer._looks_like_department("인사부서") is True

    assert tokenizer._looks_like_department("배부") is False
    assert tokenizer._looks_like_department("원가배부") is False
    assert tokenizer._looks_like_department("공통비 배부") is False
    assert tokenizer._looks_like_department("제조경비 배부") is False

    assert list(tokenizer.iter_low_conf_term_candidates("제조경비 배부")) == []


def test_person_candidates_skip_bpr_requirement_lines_but_keep_explicit_role_context():
    tokenizer = DocumentEntityTokenizer()

    assert list(tokenizer.iter_label_less_person_candidates("예산담당자가 예산전용신청서 작성하고 승인요청", section="tables")) == []
    assert list(tokenizer.iter_label_less_person_candidates("실무담당자의 변화 스폰서/담당자 임명을 통한", section="texts")) == []
    assert list(tokenizer.iter_label_less_person_candidates("교육을 담당하고, Go Live 이후", section="texts")) == []
    assert list(tokenizer.iter_label_less_person_candidates("손해배상 책임", section="texts")) == []
    assert list(tokenizer.iter_label_less_person_candidates("| 통합재무 정보 | SFR-A-021 | 예산변경서 작성 | 필수 | 예산담당자가 예산전용신청서 작성하고 승인요청", section="tables")) == []
    assert list(tokenizer.iter_low_conf_term_candidates("| - | TER-001 | 테스트 계획 수립 및 실시 | 필수 | 테스트 계획 수립 및 실시를 위한 요건", section="tables")) == []

    assert list(tokenizer.iter_label_less_person_candidates("담당 홍길동", section="texts")) == ["홍길동"]
    assert list(tokenizer.iter_label_less_person_candidates("작성자: 홍길동", section="texts")) == ["홍길동"]
    assert list(tokenizer.iter_label_less_person_candidates("문의: 홍길동 / hgd@example.com", section="texts")) == ["홍길동"]
    assert list(tokenizer.iter_label_less_person_candidates("홍길동 부장", section="texts")) == ["홍길동"]
