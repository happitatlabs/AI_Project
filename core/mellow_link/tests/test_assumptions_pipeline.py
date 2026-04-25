from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from mellow_link.modules.rebuild_assistant.postprocess.consulting_contract import (
    build_consulting_min_contract,
)
from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import build_result_package
from mellow_link.services.refactoring_support_engine import ExplanationPresenter

from .refactoring_support_test_utils import build_safe_bundle


def _sample_project(project_name: str = "assumptions_pipeline"):
    return SimpleNamespace(
        id=f"proj_{project_name}",
        project_name=project_name,
        client_name="ACME",
        template_key="rebuild_assistant",
        constraints_json="[]",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def _section_by_key(response, section_key: str):
    return next(section for section in response.section_views if section.section_key == section_key)


def test_input_assembler_collects_explicit_assumption_candidates_from_constraints_and_source_blocks():
    bundle = build_safe_bundle(
        [
            {
                "name": "legacy_rule.txt",
                "content": """
가정: 기존 데이터 정합성이 확보되어 있다.
외부 시스템 연계가 승인된 경우에 한해 적용한다.
가능하다면 데이터 정비를 먼저 한다.
                """,
            },
            {"name": "order_service.py", "content": "class OrderService: pass"},
        ]
    )
    service = RebuildAssistantService()

    prepared = service.prepare_safe_bundle_input(
        goal="주문 구조를 검토한다.",
        safe_bundle=bundle,
        constraints=["전제: 현업 담당자가 기준정보를 유지한다."],
    )

    statements = [item.statement for item in prepared.assumption_candidates]
    assert statements == [
        "기존 데이터 정합성이 확보되어 있다.",
        "외부 시스템 연계가 승인된 경우에 한해 적용한다.",
        "현업 담당자가 기준정보를 유지한다.",
    ]
    assert [item.explicit_marker for item in prepared.assumption_candidates] == [
        "가정",
        "조건부",
        "전제",
    ]
    assert any(item.source_field == "constraints[0]" for item in prepared.assumption_candidates)
    assert any(
        str(item.source_field).startswith("analysis_context.source_blocks[legacy_rule.txt]")
        for item in prepared.assumption_candidates
    )


def test_assumptions_remain_empty_without_explicit_source_in_completed_result():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="modernize order creation flow",
        assets=RebuildAssetsPayload(
            source_code="""
class OrderService:
    def submit(self, order, repo):
        if order.status == "READY":
            repo.save(order)
            return approve(order)
            """,
            ui_template='<button onclick="submitOrder()">submit</button>',
            sql_queries="SELECT * FROM orders WHERE status = 'READY'",
        ),
        constraints=[],
    )
    result = service.build_result(prepared)
    pkg = build_result_package(
        _sample_project("assumptions_absent"),
        {"status": "completed", "run_id": "run_assumptions_absent"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    assert result.assumptions == []
    assert pkg["assumptions"] == []
    assert pkg["consulting_min_contract"]["assumptions"] == []


def test_explicit_assumptions_flow_to_result_package_without_evidence_or_canonical_pollution():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="주문 저장 구조를 검토한다.",
        assets=RebuildAssetsPayload(source_code="class OrderService: pass"),
        constraints=[],
        temp_context="""
가정: 기존 데이터 정합성이 확보되어 있다.
전제: 현업 담당자가 기준정보를 유지한다.
외부 시스템 연계가 승인된 경우에 한해 적용한다.
        """,
    )
    result = service.build_result(prepared)
    pkg = build_result_package(
        _sample_project("assumptions_explicit"),
        {"status": "completed", "run_id": "run_assumptions_explicit"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    expected = [
        "기존 데이터 정합성이 확보되어 있다.",
        "현업 담당자가 기준정보를 유지한다.",
        "외부 시스템 연계가 승인된 경우에 한해 적용한다.",
    ]
    assert [item.statement for item in result.assumptions] == expected
    assert [item["statement"] for item in pkg["assumptions"]] == expected
    assert pkg["consulting_min_contract"]["assumptions"] == expected
    assert "assumptions" not in (pkg["canonical_payload"] or {})

    evidence_text = " ".join(pkg["consulting_min_contract"]["evidence"])
    analysis_text = " ".join(pkg["analysis_summary"])
    retained_contract_text = " ".join(
        f"{item.get('item', '')} {item.get('basis', '')}" for item in pkg["retained_contracts"]
    )
    grounded_rule_text = " ".join(
        f"{item.get('title', '')} {item.get('description', '')}" for item in pkg["grounded_business_rules"]
    )
    missing_information_text = " ".join(pkg["consulting_min_contract"]["missing_information"])
    for statement in expected:
        assert statement not in evidence_text
        assert statement not in analysis_text
        assert statement not in retained_contract_text
        assert statement not in grounded_rule_text
        assert statement not in missing_information_text


def test_decision_engine_filters_labeled_but_excluded_assumption_sentences():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="주문 저장 구조를 검토한다.",
        assets=RebuildAssetsPayload(source_code="class OrderService: pass"),
        constraints=[],
        temp_context="""
가정: 가능하다면 데이터 정비를 먼저 한다.
전제: 일반적으로 기준정보가 중요하다.
전제: 시스템을 재구축해야 한다.
전제: 추가 확인이 필요하다.
        """,
    )

    assert [item.statement for item in prepared.assumption_candidates] == [
        "가능하다면 데이터 정비를 먼저 한다.",
        "일반적으로 기준정보가 중요하다.",
        "시스템을 재구축해야 한다.",
        "추가 확인이 필요하다.",
    ]

    result = service.build_result(prepared)

    assert result.assumptions == []


def test_consulting_contract_prefers_structured_assumptions_over_legacy_token_fallback():
    contract = build_consulting_min_contract(
        {
            "assumptions": [
                {
                    "statement": "기존 데이터 정합성이 확보되어 있다.",
                    "source_stage": "input",
                    "source_field": "scenario",
                    "explicit_marker": "가정",
                    "applies_to": [],
                }
            ],
            "analysis_summary": ["가정: fallback summary should be ignored"],
            "primary_judgment_reason": "이 구조는 운영 정책을 전제로 합니다.",
            "risks": ["전제: fallback risk should be ignored"],
        }
    )

    assert contract.assumptions == ["기존 데이터 정합성이 확보되어 있다."]


def test_assumptions_surface_is_consistent_between_internal_and_external_generic_contract():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="modernize order creation flow",
        assets=RebuildAssetsPayload(
            source_code="""
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY":
            repo.save(order)
            return approve(order)
            """,
            ui_template='<button onclick="submitOrder()">submit</button>',
            sql_queries="SELECT * FROM orders WHERE status = 'READY' AND amount > 1000",
        ),
        constraints=[],
        temp_context="전제: 현업 담당자가 기준정보를 유지한다.",
    )
    result = service.build_result(prepared)
    pkg = build_result_package(
        _sample_project("assumptions_surface"),
        {"status": "completed", "run_id": "run_assumptions_surface"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    presenter = ExplanationPresenter()
    internal = presenter.present(
        project_id="proj_assumptions_surface",
        result_package=pkg,
        audience="manager",
        surface_mode="internal",
    )
    external = presenter.present(
        project_id="proj_assumptions_surface",
        result_package=pkg,
        audience="manager",
        surface_mode="external",
    )

    expected_statement = "현업 담당자가 기준정보를 유지한다."
    assert expected_statement in _section_by_key(internal, "risks").text
    assert expected_statement.rstrip(".") in _section_by_key(external, "risks").text
