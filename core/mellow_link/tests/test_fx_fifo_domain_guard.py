from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import _result_package_markdown, _surface_filtered_result_package, build_result_package
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)
from mellow_link.services.refactoring_support_engine.explanation_presenter import (
    ExplanationPresenter,
)

from .refactoring_support_test_utils import build_safe_bundle, load_sample_case


def _sample_project():
    return SimpleNamespace(
        id="proj_fx_fifo_guard",
        project_name="외화 FIFO 검증",
        client_name="FIFO 사례",
        template_key="rebuild_assistant",
        constraints_json="[]",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def _contains_sql_like_token(text: str) -> bool:
    patterns = (
        r"\b(?:TN|TB|TR|IB|GL|P|PKG|PK|PROC|PRC|FN|FNC|SP|VW|IDX|SEQ)_[A-Z0-9_$#]+\b",
        r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:AMT|SEQ|ID|CD|CODE|YN|FLAG|STATUS|RATE|DATE|NO|NUM|QTY|CNT|KEY|REF)[A-Z0-9$#]*\b",
        r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|JOIN|FROM|WHERE|GROUP\s+BY|ORDER\s+BY)\b",
    )
    upper_text = str(text or "").upper()
    return any(re.search(pattern, upper_text) for pattern in patterns)


def _contains_operational_forbidden_surface(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "sql",
            "table",
            "procedure",
            "trigger",
            "column",
            "데이터 접근",
            "ui",
            "재설계",
            "분리 구조",
            "계층 분리",
        )
    )


def _fx_fifo_result(goal: str | None = None):
    bundle = build_safe_bundle(
        [
            {
                "name": "TN_FORINS.sql",
                "content": """
CREATE TABLE TN_FORINS (
    ACCT_SEQ VARCHAR2(50),
    TR_DATE VARCHAR2(8),
    TR_DATE_SEQ NUMBER,
    RMN_FAMT NUMBER,
    RMN_AMT NUMBER,
    EXCH_RATE NUMBER,
    MNEY_UNIT VARCHAR2(5)
);
                """,
            },
            {
                "name": "P_FOROUT.prc",
                "content": """
CREATE OR REPLACE procedure P_FOROUT IS
BEGIN
    FOR clr IN (
        SELECT ACCT_SEQ, TR_DATE, TR_DATE_SEQ, RMN_FAMT, RMN_AMT, EXCH_RATE
        FROM TN_FORINS
        ORDER BY TR_DATE, TR_DATE_SEQ
    ) LOOP
        INSERT INTO TN_FOROUD (OUTF_AMT, OUT_AMT0, GAP_AMT) VALUES (10, 1000, 50);
    END LOOP;
END;
                """,
            },
            {
                "name": "P_BKCHNO.prc",
                "content": """
CREATE OR REPLACE procedure P_BKCHNO IS
BEGIN
    w_USER_JE_CATEGORY_NAME := 'deposit';
    INSERT INTO TN_BKCHIT (OCCR_PART, MNEY_UNIT) VALUES ('exchange p/l', 'USD');
    INSERT INTO GL_INTERFACE (REFERENCE4, REFERENCE6, USER_JE_CATEGORY_NAME, CURRENCY_CODE)
    VALUES ('CHK-20260418', '1', 'deposit', 'USD');
END;
                """,
            },
            {
                "name": "GL_INTERFACE.sql",
                "content": """
CREATE TABLE GL_INTERFACE (
    REFERENCE4 VARCHAR2(50),
    REFERENCE6 VARCHAR2(50),
    USER_JE_CATEGORY_NAME VARCHAR2(25),
    CURRENCY_CODE VARCHAR2(5),
    ENTERED_DR NUMBER,
    ENTERED_CR NUMBER
);
                """,
            },
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=goal or "외화 입출금 FIFO 처리 흐름을 재구성해줘",
        safe_bundle=bundle,
        constraints=[
            "승인(order) 도메인으로 해석하지 마라",
            "워크플로우/승인/권한 모델로 확장하지 마라",
            "외화 입금, 출금, FIFO lot, 환차손익, 전표, GL 흐름만 다뤄라",
        ],
    )
    return prepared, service.build_result(prepared)


def test_fx_fifo_domain_guard_avoids_workflow_classification_and_language():
    prepared, result = _fx_fifo_result()

    assert "order" not in prepared.signals.concepts
    assert prepared.signals.concepts[0] == "외화 입출금 FIFO"
    assert prepared.signals.status_permissions == []
    assert prepared.signals.search_filters == []
    assert prepared.signals.save_validation == []
    assert result.primary_judgment != "workflow"
    assert result.narrative_axis != "workflow"
    assert result.narrative_axis != "access_control"
    assert any("FIFO" in item or "lot" in item.lower() for item in result.core_business_rules)
    assert any("환차손익" in item for item in result.core_business_rules)
    assert any("GL" in item or "전표" in item for item in result.core_business_rules)
    assert all("승인" not in item.statement and "워크플로우" not in item.statement for item in result.decision_items)
    assert all("승인" not in item.goal and "워크플로우" not in item.goal for item in result.execution_plan)
    assert all("승인" not in item and "워크플로우" not in item for item in result.recommended_directions)


def test_fx_fifo_result_prefers_current_state_analysis_before_redesign_language():
    _, result = _fx_fifo_result()

    summary_text = " ".join(result.executive_summary_v2[:2])
    analysis_lines = list(result.analysis_summary)
    object_lines = analysis_lines[1:]
    front_text = " ".join([result.report_purpose, result.one_line_conclusion, *list(result.executive_summary_v2[:2])])
    execution_support_text = " ".join(
        " ".join(item.related_contracts).strip() for item in result.execution_plan
    ) + " " + " ".join(result.recommended_directions)
    execution_text = " ".join(
        " ".join([item.goal, *item.tasks]).strip()
        for item in result.execution_plan
    )

    assert result.narrative_axis == "fx_fifo"
    assert result.analysis_summary[0].startswith("핵심 데이터 흐름은")
    assert result.executive_summary_v2[0].startswith("현행 분석:")
    assert "회계 처리 소스 묶음" in result.one_line_conclusion
    assert "분리 구조" not in result.one_line_conclusion
    assert "계층 분리" not in result.one_line_conclusion
    assert "재설계" not in result.one_line_conclusion
    assert not _contains_sql_like_token(front_text)
    assert not _contains_sql_like_token(summary_text)
    assert not _contains_sql_like_token(execution_support_text)
    assert not _contains_sql_like_token(execution_text)
    assert not _contains_operational_forbidden_surface(front_text)
    assert not _contains_operational_forbidden_surface(summary_text)
    assert not _contains_operational_forbidden_surface(execution_text)
    assert 3 <= len(object_lines) <= 5
    assert all(re.match(r"^[^:]+: .+$", line) for line in object_lines)
    assert all(not re.search(r"\b(?:table|procedure|trigger)\b", line, flags=re.IGNORECASE) for line in object_lines)
    assert all("TN_" not in line and "GL_INTERFACE" not in line for line in object_lines)
    assert "detector_id=" not in result.primary_judgment_reason


def test_fx_fifo_question_axis_changes_operational_emphasis_for_journal_linkage():
    generic_goal = "이 SQL/프로시저가 실제로 어떤 처리 흐름과 계산 규칙으로 동작하는지 분석해줘."
    journal_goal = "이 SQL/프로시저가 전표 생성 기준과 GL 연결, 거래 키 기준으로 어떻게 이어지는지 분석해줘."

    _, generic_result = _fx_fifo_result(goal=generic_goal)
    _, journal_result = _fx_fifo_result(goal=journal_goal)

    assert generic_result.family_classification.family == "operational_source"
    assert journal_result.family_classification.family == "operational_source"
    assert generic_result.question_axis in {"processing_flow", "calculation_rule"}
    assert journal_result.question_axis == "journal_linkage"
    assert journal_result.canonical_payload is not None
    assert journal_result.canonical_payload.request_context.question_axis == "journal_linkage"
    assert generic_result.report_purpose != journal_result.report_purpose
    assert "전표/GL 연결" in journal_result.report_purpose
    assert "진단" in journal_result.report_purpose
    assert any("전표" in item and ("거래 기준번호" in item or "거래 키" in item or "GL" in item) for item in journal_result.report_questions)
    assert journal_result.analysis_summary[0].startswith("핵심 데이터 흐름은 lot 계산 결과, 전표 생성 기준")
    object_text = " ".join(journal_result.analysis_summary[1:])
    assert "전표" in object_text
    assert "회계 인터페이스" in object_text or "거래 기준번호" in object_text or "거래 키" in object_text


def test_fx_fifo_narrative_augmentation_keeps_operational_analysis_governance():
    prepared, result = _fx_fifo_result()

    class FakeLLM:
        def get_model_for_mode(self, mode):
            return "qwen3.5:9b"

        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": result.report_purpose,
                        "primary_judgment_reason": result.primary_judgment_reason,
                        "one_line_conclusion": result.one_line_conclusion,
                        "executive_summary_v2": [
                            result.executive_summary_v2[0],
                            "핵심 흐름: 외화 입금 lot, FIFO lot 소진, 환차손익 계산, 전표 및 회계 인터페이스가 같은 거래 체인으로 이어집니다.",
                            result.executive_summary_v2[2],
                            "개선 제안: 현행 흐름을 확인한 뒤 trigger 책임 축소와 계산 로직 분리를 후속 검토합니다.",
                        ],
                    },
                    ensure_ascii=False,
                ),
                model="qwen3.5:9b",
            )

    augmented = NarrativeAugmentationService().augment_sync(
        prepared=prepared,
        result=result,
        llm_service=FakeLLM(),
    )

    top_text = " ".join(
        [
            augmented.report_purpose,
            augmented.one_line_conclusion,
            *list(augmented.executive_summary_v2[:3]),
        ]
    )

    assert augmented.extensions["narrative"]["source"] == "ai"
    assert augmented.extensions["narrative"]["axis"] == "fx_fifo"
    assert augmented.executive_summary_v2[0].startswith("현행 분석:")
    assert augmented.one_line_conclusion.startswith("본 자산은")
    assert not _contains_sql_like_token(top_text)
    assert "FIFO" in top_text or "lot" in top_text.lower()
    assert "detector_id=" not in top_text
    assert "validation_guard_leak" not in top_text
    assert "재설계" not in " ".join([augmented.report_purpose, augmented.one_line_conclusion, augmented.executive_summary_v2[0]])


def test_fx_fifo_narrative_augmentation_rejects_detector_name_and_redesign_first_summary():
    prepared, result = _fx_fifo_result()

    class BadLLM:
        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": "validation_guard_leak을 근거로 분리 구조를 우선 검토하는 보고서입니다.",
                        "primary_judgment_reason": "layer_leak 기준으로 재설계를 먼저 추진해야 합니다.",
                        "one_line_conclusion": "TN_FORINS와 GL_INTERFACE를 서비스로 재설계하는 것이 우선입니다.",
                        "executive_summary_v2": [
                            "재설계 우선: validation_guard_leak과 layer_leak을 먼저 해소해야 합니다.",
                            "핵심 객체: TN_FORINS, GL_INTERFACE",
                        ],
                    },
                    ensure_ascii=False,
                ),
                model="qwen3.5:9b",
            )

    augmented = NarrativeAugmentationService().augment_sync(
        prepared=prepared,
        result=result,
        llm_service=BadLLM(),
    )

    assert augmented.report_purpose == result.report_purpose
    assert augmented.one_line_conclusion == result.one_line_conclusion
    assert augmented.extensions["narrative"]["source"] == "deterministic_fallback"
    assert augmented.extensions["narrative"]["validation_passed"] is False
    assert augmented.extensions["narrative"]["failure_reason"] in {
        "detector_name_exposure",
        "operational_governance_violation",
    }


def test_fx_fifo_internal_markdown_defaults_to_deck_only():
    _, result = _fx_fifo_result()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_fx_fifo_guard"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    internal_markdown = _result_package_markdown(pkg, surface_mode="internal")
    internal_full_markdown = _result_package_markdown(pkg, surface_mode="internal", internal_export_mode="full")

    assert "## 참고 구조 비교" not in internal_markdown
    assert "## 참고 구조 비교" in internal_full_markdown
    assert "승인 트리거" not in internal_markdown
    assert "워크플로우" not in internal_markdown
    assert "## 분석 목적" in internal_markdown
    assert "## 현행 분석 요약" in internal_markdown
    assert "## 검토 순서" in internal_markdown
    assert "## 컨설팅 개요" not in internal_markdown
    assert "FIFO" in internal_markdown or "lot" in internal_markdown.lower()


def test_fx_fifo_question_axis_outputs_are_information_separated():
    goals = {
        "structure": "이 SQL/프로시저가 실제로 어떤 처리 흐름으로 동작하는지 분석해줘.",
        "diagnosis": "이 SQL/프로시저가 전표 생성 기준과 GL 연결, 거래 키 기준에서 어디가 어긋날 수 있는지 진단해줘.",
        "decision": "이 SQL/프로시저의 계산 규칙 선택지와 추천 기준을 비교해서 정리해줘.",
    }
    outputs = {}
    for role_name, goal in goals.items():
        _, result = _fx_fifo_result(goal=goal)
        pkg = build_result_package(
            _sample_project(),
            {"status": "completed", "run_id": f"run_fx_fifo_{role_name}"},
            result,
            assets=[],
            polish_bundle=None,
            app_version="0.1.0",
        )
        outputs[role_name] = (result, pkg, _result_package_markdown(pkg, surface_mode="internal"))

    structure_result, structure_pkg, structure_md = outputs["structure"]
    diagnosis_result, diagnosis_pkg, diagnosis_md = outputs["diagnosis"]
    decision_result, decision_pkg, decision_md = outputs["decision"]

    assert structure_result.family_classification.family == "operational_source"
    assert diagnosis_result.family_classification.family == "operational_source"
    assert decision_result.family_classification.family in {"operational_source", "option_comparison"}
    assert structure_pkg["consulting_deck"]["information_role"] == "structure"
    assert diagnosis_pkg["consulting_deck"]["information_role"] == "diagnosis"
    assert decision_pkg["consulting_deck"]["information_role"] == "decision"

    assert [line for line in structure_md.splitlines() if line.startswith("## ")] == [
        "## 분석 목적",
        "## 현행 분석 요약",
        "## 자산 정체",
        "## 핵심 객체",
        "## 검토 순서",
    ]
    assert [line for line in diagnosis_md.splitlines() if line.startswith("## ")] == [
        "## 현행 요약",
        "## 문제 정의",
        "## 영향 분석",
        "## 리스크",
    ]
    assert [line for line in decision_md.splitlines() if line.startswith("## ")] == [
        "## 비교 목적",
        "## 선택지 요약",
        "## 비교 기준",
        "## 추천 근거",
        "## 도입 단계",
    ]

    assert "추천안" not in structure_md
    assert "선택지" not in structure_md
    assert "불일치 가능성" not in structure_md
    assert "추천안" not in diagnosis_md
    assert "선택지" not in diagnosis_md
    assert "옵션" not in diagnosis_md
    assert "검토안" not in diagnosis_md
    assert "구조 개선" not in diagnosis_md
    assert "조치" not in diagnosis_md
    assert "개선" not in diagnosis_md
    assert "설계" not in diagnosis_md
    assert "후속" not in diagnosis_md
    assert "주차" not in diagnosis_md
    assert "단계" not in diagnosis_md
    assert "추진" not in diagnosis_md
    assert "해야" not in diagnosis_md
    assert "분리 구조" not in decision_md
    assert "핵심 객체" not in decision_md
    assert "불일치 가능성" not in decision_md
    assert "입금 lot 원장과 출금 lot 소진 흐름" not in decision_md

    def normalized_content_lines(markdown: str) -> set[str]:
        lines = set()
        for raw_line in markdown.splitlines():
            line = raw_line.strip().removeprefix("- ").strip()
            if not line or line.startswith("#") or line.startswith("Role:") or line.startswith("참조:"):
                continue
            if len(line) < 12:
                continue
            lines.add(line)
        return lines

    structure_lines = normalized_content_lines(structure_md)
    diagnosis_lines = normalized_content_lines(diagnosis_md)
    decision_lines = normalized_content_lines(decision_md)
    assert not (structure_lines & diagnosis_lines)
    assert not (structure_lines & decision_lines)
    assert not (diagnosis_lines & decision_lines)

    external_view = ExplanationPresenter().present(
        project_id="proj_fx_fifo_diagnosis",
        result_package=diagnosis_pkg,
        audience="manager",
        surface_mode="external",
    )
    assert [(section.section_key, section.title) for section in external_view.section_views] == [
        ("report_purpose", "현행 요약"),
        ("executive_summary_v2", "문제 정의"),
        ("primary_judgment_reason", "영향 분석"),
        ("risks", "리스크"),
    ]
    external_text = " ".join(section.text for section in external_view.section_views)
    assert "진단 순서" not in external_text
    assert "1단계" not in external_text
    assert "2단계" not in external_text
    assert "추천안" not in external_text
    assert "선택지" not in external_text


def test_journal_linkage_secondary_operational_uses_diagnosis_markdown_registry():
    goal = "이 SQL/프로시저가 전표 생성 기준과 GL 연결, 거래 키 기준에서 어디가 어긋날 수 있는지 진단해줘."
    _, result = _fx_fifo_result(goal=goal)
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_fx_fifo_secondary_diagnosis"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )
    family_payload = {
        "family": "document_consulting",
        "confidence": 0.81,
        "decision_basis": ["문서형 표면 입력이 감지됨"],
        "secondary_signals": ["operational_source", "redesign_review"],
        "display_strategy": "문서 구조화 우선",
        "internal_strategy": "문서 구조화",
    }
    pkg["family_classification"] = dict(family_payload)
    pkg.setdefault("authoritative_payload", {})["family_classification"] = dict(family_payload)

    filtered_pkg = _surface_filtered_result_package(pkg, surface_mode="internal")
    markdown = _result_package_markdown(filtered_pkg, surface_mode="internal")

    assert filtered_pkg["consulting_deck"]["information_role"] == "diagnosis"
    assert [line for line in markdown.splitlines() if line.startswith("## ")] == [
        "## 현행 요약",
        "## 문제 정의",
        "## 영향 분석",
        "## 리스크",
    ]
    forbidden = (
        "조치",
        "옵션",
        "다음 단계",
        "단계별 추진 흐름",
        "컨설팅 설계",
        "적용 방향",
        "검토안",
        "후속",
        "주차",
        "해야",
    )
    assert not any(term in markdown for term in forbidden)


def test_fx_fifo_surface_labels_and_polish_titles_follow_analysis_first_naming():
    _, result = _fx_fifo_result()
    service = RebuildAssistantService()
    polish_bundle = service.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_fx_fifo_surface_labels"},
        result,
        assets=[],
        polish_bundle=polish_bundle,
        app_version="0.1.0",
    )

    titles = {
        str(section.get("section_key") or ""): str(section.get("title") or "")
        for section in polish_bundle.get("polished_sections") or []
        if isinstance(section, dict)
    }
    surface_wording = (((pkg.get("extensions") or {}).get("decision_governance") or {}).get("surface_wording") or {})

    assert pkg["question_axis"] == result.question_axis
    assert surface_wording.get("display_strategy") == "현행 분석 우선"
    assert pkg["display"]["hero"]["label"] == "자산 정체"
    assert pkg["display"]["sections"]["executive"]["action_label"] == "검토 순서"
    assert titles["report_purpose"] == "분석 목적"
    assert titles["one_line_conclusion"] == "자산 정체"
    assert titles["recommended_option"] == "후속 확인 항목"
    assert titles["execution_plan"] == "검토 순서"


def test_business_order_anchor_survives_amount_limit_sql_without_order_by_false_positive():
    case = load_sample_case("04. amount_limit", fallback_goal="금액 한도형 샘플")
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )

    assert "order" in prepared.signals.concepts
    assert service._primary_concept(prepared) == "order"
