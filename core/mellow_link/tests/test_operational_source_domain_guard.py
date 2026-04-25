from __future__ import annotations

import json
import re
from types import SimpleNamespace

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)

from .refactoring_support_test_utils import load_sample_case


def _sample_result(sample_name: str):
    case = load_sample_case(sample_name)
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )
    return prepared, service.build_result(prepared)


def _contains_sql_like_token(text: str) -> bool:
    patterns = (
        r"\b(?:TN|TB|TR|IB|GL|P|PKG|PK|PROC|PRC|FN|FNC|SP|VW|IDX|SEQ)_[A-Z0-9_$#]+\b",
        r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:AMT|SEQ|ID|CD|CODE|YN|FLAG|STATUS|RATE|DATE|DT|NO|NUM|QTY|CNT|KEY|REF)[A-Z0-9$#]*\b",
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


def test_interface_linkage_sample_prefers_analysis_first_narrative_and_objects():
    _, result = _sample_result("10_interface_linkage_operational_source")

    front_text = " ".join(
        [
            result.report_purpose,
            result.one_line_conclusion,
            result.analysis_summary[0],
            result.executive_summary_v2[0],
            result.executive_summary_v2[1],
        ]
    )
    object_lines = list(result.analysis_summary[1:])

    assert result.narrative_axis == "interface_linkage"
    assert result.analysis_summary[0].startswith("핵심 데이터 흐름은")
    assert result.executive_summary_v2[0].startswith("현행 분석:")
    assert not _contains_sql_like_token(front_text)
    assert not _contains_operational_forbidden_surface(front_text)
    assert 3 <= len(object_lines) <= 5
    assert all(re.match(r"^[^:]+: .+$", line) for line in object_lines)
    assert all(not re.search(r"\b(?:table|procedure|trigger)\b", line, flags=re.IGNORECASE) for line in object_lines)
    assert all("IB_" not in line and "TN_" not in line for line in object_lines)
    assert "응답 확정" in front_text or "재처리" in front_text
    assert result.decision_summary["decisions"][0]["decision_type"] == "refactor"
    assert result.extensions["decision_governance"]["surface_wording"]["display_strategy"] == "운영 로직 검토 우선"
    assert all(term not in front_text for term in ("재설계", "분리 구조", "계층 분리", "서비스 분리"))


def test_settlement_journal_sample_prefers_analysis_first_narrative_and_objects():
    _, result = _sample_result("11_settlement_journal_operational_source")

    front_text = " ".join(
        [
            result.report_purpose,
            result.one_line_conclusion,
            result.analysis_summary[0],
            result.executive_summary_v2[0],
            result.executive_summary_v2[1],
        ]
    )
    object_lines = list(result.analysis_summary[1:])

    assert result.narrative_axis == "settlement_journal"
    assert result.analysis_summary[0].startswith("핵심 데이터 흐름은")
    assert result.executive_summary_v2[0].startswith("현행 분석:")
    assert not _contains_sql_like_token(front_text)
    assert not _contains_operational_forbidden_surface(front_text)
    assert 3 <= len(object_lines) <= 5
    assert all(re.match(r"^[^:]+: .+$", line) for line in object_lines)
    assert all(not re.search(r"\b(?:table|procedure|trigger)\b", line, flags=re.IGNORECASE) for line in object_lines)
    assert all("TN_" not in line and "GL_INTERFACE" not in line for line in object_lines)
    assert "전표" in front_text
    assert result.decision_summary["decisions"][0]["decision_type"] == "refactor"
    assert all(term not in front_text for term in ("재설계", "분리 구조", "계층 분리", "서비스 분리"))


def test_interface_linkage_ai_narrative_keeps_operational_objects_and_flow():
    prepared, result = _sample_result("10_interface_linkage_operational_source")

    class FakeLLM:
        async def generate(self, *args, **kwargs):
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "report_purpose": result.report_purpose,
                            "primary_judgment_reason": result.primary_judgment_reason,
                            "one_line_conclusion": result.one_line_conclusion,
                            "executive_summary_v2": list(result.executive_summary_v2),
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

    front_text = " ".join(
        [
            augmented.report_purpose,
            augmented.one_line_conclusion,
            *list(augmented.executive_summary_v2[:3]),
        ]
    )

    assert augmented.extensions["narrative"]["source"] == "ai"
    assert augmented.extensions["narrative"]["axis"] == "interface_linkage"
    assert augmented.executive_summary_v2[0].startswith("현행 분석:")
    assert augmented.one_line_conclusion.startswith("본 자산은")
    assert not _contains_sql_like_token(front_text)
    assert "후속 업무 연계" in front_text or "후속 업무 연결" in front_text
    assert "상태 확정" in front_text or "재처리" in front_text


def test_interface_linkage_ai_narrative_rejects_anchorless_generic_summary():
    prepared, result = _sample_result("10_interface_linkage_operational_source")

    class BadLLM:
        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": "운영 소스 분석 보고서입니다.",
                        "primary_judgment_reason": "현재는 재설계보다 운영 분석이 우선입니다.",
                        "one_line_conclusion": "본 자산은 인터페이스 운영 소스 묶음입니다.",
                        "executive_summary_v2": [
                            "현행 분석: 인터페이스 운영 소스 묶음입니다.",
                            "핵심 객체: 관련 테이블과 프로시저입니다.",
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

    assert augmented.extensions["narrative"]["source"] == "deterministic_fallback"
    assert augmented.extensions["narrative"]["validation_passed"] is False
    assert augmented.extensions["narrative"]["failure_reason"] in {
        "operational_governance_violation",
        "critical_fact_missing",
    }
