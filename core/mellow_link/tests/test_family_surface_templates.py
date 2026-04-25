from __future__ import annotations

import re

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

from .refactoring_support_test_utils import build_safe_bundle, load_sample_case


def _build_result(goal: str, asset_specs: list[dict[str, str]], constraints: list[str] | None = None):
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=goal,
        safe_bundle=build_safe_bundle(asset_specs),
        constraints=constraints or [],
    )
    return service.build_result(prepared)


def _sample_result(sample_name: str):
    case = load_sample_case(sample_name)
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )
    return service.build_result(prepared)


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


def test_operational_source_templates_keep_analysis_first_summary_conclusion_and_execution():
    result = _sample_result("09_fx_fifo_operational_source")

    front_text = " ".join([result.report_purpose, result.one_line_conclusion, *list(result.executive_summary_v2[:2])])
    execution_text = " ".join(
        " ".join([item.week_label, item.goal, *list(item.tasks[:2])]).strip()
        for item in result.execution_plan
    )
    execution_support_text = " ".join(
        " ".join(item.related_contracts).strip() for item in result.execution_plan
    ) + " " + " ".join(result.recommended_directions)
    object_lines = list(result.analysis_summary[1:])

    assert result.family_classification.family == "operational_source"
    assert result.one_line_conclusion.startswith("본 자산은")
    assert result.executive_summary_v2[0].startswith("현행 분석:")
    assert result.analysis_summary[0].startswith("핵심 데이터 흐름은")
    assert len(result.execution_plan) == 3
    assert all("주차" not in item.week_label for item in result.execution_plan)
    assert all("로드맵" not in item.goal for item in result.execution_plan)
    assert all("재설계" not in line and "계층" not in line for line in [result.one_line_conclusion, *result.executive_summary_v2[:2]])
    assert "validation_guard_leak" not in front_text
    assert "boundary_mismatch" not in front_text
    assert "detector" not in front_text.lower()
    assert "현행 운영 로직" in result.one_line_conclusion
    assert "분리 구조" not in execution_text
    assert not _contains_sql_like_token(front_text)
    assert not _contains_sql_like_token(execution_text)
    assert not _contains_sql_like_token(execution_support_text)
    assert not _contains_operational_forbidden_surface(front_text)
    assert not _contains_operational_forbidden_surface(execution_text)
    assert not _contains_operational_forbidden_surface(execution_support_text)
    assert 3 <= len(object_lines) <= 5
    assert all(re.match(r"^[^:]+: .+$", line) for line in object_lines)
    assert all(not re.search(r"\b(?:table|procedure|trigger)\b", line, flags=re.IGNORECASE) for line in object_lines)
    assert all("TN_" not in line and "GL_INTERFACE" not in line for line in object_lines)


def test_redesign_review_templates_keep_structure_first_summary_conclusion_and_execution():
    result = _build_result(
        "현재 구조 문제와 책임 분리 방향을 판단해줘",
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY":
            repo.save(order)
            return approve(order)
                """,
            },
            {
                "name": "order_query.sql",
                "content": "SELECT * FROM orders WHERE status = 'READY' AND amount > 1000",
            },
        ],
    )

    assert result.family_classification.family == "redesign_review"
    assert not result.one_line_conclusion.startswith("본 자산은")
    assert result.executive_summary_v2[0].startswith("문제:")
    assert any(token in result.one_line_conclusion for token in ("분리", "구조", "계층"))
    assert any(token in result.execution_plan[0].goal for token in ("설계", "구조", "분리", "정책"))


def test_option_comparison_templates_keep_comparison_first_summary_conclusion_and_execution():
    result = _sample_result("13_document_option_boundary")

    execution_text = " ".join(
        f"{item.week_label} {item.goal} {' '.join(item.tasks[:1])}" for item in result.execution_plan
    )

    assert result.family_classification.family == "option_comparison"
    assert "복수 선택지" in result.report_purpose
    assert result.one_line_conclusion.startswith("우선 검토안은")
    assert result.executive_summary_v2[0].startswith("비교 관점:")
    assert "현행 분석:" not in " ".join(result.executive_summary_v2[:2])
    assert "본 자산은" not in result.one_line_conclusion
    assert "운영 소스" not in execution_text
