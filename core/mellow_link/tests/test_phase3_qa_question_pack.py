from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import build_result_package
from mellow_link.services.refactoring_support_engine import ResultQuestionAnsweringService

from .refactoring_support_golden_samples import GOLDEN_SAMPLE_EXPECTATIONS
from .refactoring_support_test_utils import load_sample_case


QUESTION_PACK_PATH = (
    Path(__file__).resolve().parents[1]
    / "modules"
    / "rebuild_assistant"
    / "samples"
    / "_templates"
    / "phase3_qa_question_pack.json"
)
QUESTION_PACK = json.loads(QUESTION_PACK_PATH.read_text(encoding="utf-8"))
FALLBACK_GOAL_MAP = {
    expectation.sample_name: expectation.fallback_goal
    for expectation in GOLDEN_SAMPLE_EXPECTATIONS
}


def _build_result_package_for_sample(sample_name: str) -> dict:
    service = RebuildAssistantService()
    case = load_sample_case(sample_name, fallback_goal=FALLBACK_GOAL_MAP.get(sample_name, ""))
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )
    result = service.build_result(prepared)
    polish_bundle = service.build_polish_bundle(result, audience="manager", delivery_mode="client_report").model_dump()
    project = ModernizationProject(
        id=f"proj_{re.sub(r'[^a-zA-Z0-9]+', '_', sample_name)}",
        user_id=1,
        session_id="sess_phase3_pack",
        run_id="run_phase3_pack",
        project_name=sample_name,
        client_name="OO",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json="[]",
        upload_session_id="upload_phase3_pack",
        asset_manifest_json="[]",
        status="completed",
    )
    return build_result_package(
        project,
        {"status": "completed", "run_id": project.run_id},
        result,
        assets=[],
        polish_bundle=polish_bundle,
        app_version="0.1.0",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sample_config", QUESTION_PACK["sample_question_sets"], ids=lambda item: item["sample_name"])
async def test_phase3_question_pack_sample_questions(sample_config):
    qa_service = ResultQuestionAnsweringService()
    result_package = _build_result_package_for_sample(sample_config["sample_name"])

    for question_spec in sample_config["questions"]:
        response = await qa_service.answer(
            project_id="proj_phase3_pack",
            result_package=result_package,
            question=question_spec["question"],
            audience=question_spec["audience"],
            llm_service=None,
        )

        assert response.referenced_sections == question_spec["expected_referenced_sections"]
        expected_insufficient = bool(question_spec.get("expect_insufficient_grounding", False))
        assert response.insufficient_grounding is expected_insufficient
        if expected_insufficient:
            assert response.answer_mode == "deterministic"
            continue
        if question_spec["expect_citations"]:
            assert response.citations
        else:
            assert response.citations == []


@pytest.mark.asyncio
async def test_phase3_question_pack_common_audience_invariance():
    qa_service = ResultQuestionAnsweringService()
    result_package = _build_result_package_for_sample("01. java_order_closure_case_01")
    top_decision = result_package["authoritative_payload"]["decision_summary"]["decisions"][0]
    top_stage = result_package["authoritative_payload"]["improvement_plan_bundle"]["execution_stages"][0]

    for check in QUESTION_PACK["common_audience_invariance_checks"]:
        responses = {}
        for audience in check["audiences"]:
            responses[audience] = await qa_service.answer(
                project_id="proj_phase3_pack",
                result_package=result_package,
                question=check["question"],
                audience=audience,
                llm_service=None,
            )

        developer = responses["developer"]
        manager = responses["manager"]
        client = responses["client"]

        assert [item.model_dump() for item in developer.citations] == [item.model_dump() for item in manager.citations]
        assert [item.model_dump() for item in manager.citations] == [item.model_dump() for item in client.citations]
        assert developer.referenced_sections == manager.referenced_sections == client.referenced_sections

        if check["id"] == "priority-invariance":
            expected_score = str(top_decision["priority_score"])
            assert expected_score in developer.answer
            assert expected_score in manager.answer
            assert expected_score in client.answer
        elif check["id"] == "execution-invariance":
            expected_title = top_stage["title"]
            assert expected_title in developer.answer
            assert expected_title in manager.answer
            assert expected_title in client.answer
