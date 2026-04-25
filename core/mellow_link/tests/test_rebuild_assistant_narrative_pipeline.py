import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from mellow_link import app_state
from mellow_link.infra import ModernizationProject
from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
from mellow_link.modules.rebuild_assistant import runner as rebuild_runner
from mellow_link.modules.rebuild_assistant.schemas import (
    CanonicalRebuildPayload,
    DeterministicExplanationBlock,
    DesignOption,
    NarrativeCriticalFact,
    NarrativeDecisionDrivingEvidence,
    NarrativeLockedFields,
    RecommendedOption,
)
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import (
    _generate_result_package_docx,
    _result_package_markdown,
    _result_package_pptx_response,
    build_result_package,
)
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)

from .refactoring_support_test_utils import build_safe_bundle


def _sample_prepared_and_result():
    service = RebuildAssistantService()
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
VERY_PRIVATE_SOURCE_MARKER
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
                "name": "order_page.html",
                "content": '<button onclick="submitOrder()">submit</button>',
            },
            {
                "name": "order_query.sql",
                "content": "SELECT * FROM orders WHERE status = 'READY' ORDER BY created_at DESC /* FULL_SQL_MARKER */",
            },
        ]
    )
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=["기존 DB 계약 유지"])
    result = service.build_result(prepared)
    return prepared, result


def _sample_project() -> ModernizationProject:
    return ModernizationProject(
        id="proj_narrative_pipeline",
        user_id=1,
        session_id="sess_narrative_pipeline",
        run_id="run_narrative_pipeline",
        project_name="내러티브 파이프라인",
        client_name="OO생명",
        template_key="default_modernization_v1",
        template_mode="recommended",
        constraints_json='["기존 DB 계약 유지"]',
        upload_session_id="upload_narrative_pipeline",
        asset_manifest_json="[]",
        status="completed",
    )


def _build_valid_candidate(result, evidence_id: str) -> dict:
    return {
        "report_purpose": result.report_purpose,
        "executive_summary_v2": list(result.executive_summary_v2[:2]),
        "one_line_conclusion": result.one_line_conclusion,
        "primary_judgment_reason": result.primary_judgment_reason,
    }


def _first_evidence_id(result) -> str:
    for item in result.appendix.get("evidence_index") or []:
        evidence_id = str(item.get("evidence_id") or "").strip()
        if evidence_id:
            return evidence_id
    return ""


def _build_guard_block(
    *,
    block_id: str,
    deterministic_lines: list[str],
    critical_facts: list[str] | None = None,
    evidence_items: list[tuple[str, str]] | None = None,
    locked_fields: NarrativeLockedFields | None = None,
) -> DeterministicExplanationBlock:
    facts = critical_facts or deterministic_lines
    evidence_items = evidence_items or []
    return DeterministicExplanationBlock(
        block_id=block_id,
        field_type="list" if block_id in {"executive_summary_v2", "execution_plan", "risks"} else "text",
        deterministic_lines=list(deterministic_lines),
        resolved_lines=list(deterministic_lines),
        critical_facts=[
            NarrativeCriticalFact(fact_id=f"{block_id}:{index + 1}", text=text)
            for index, text in enumerate(facts)
        ],
        decision_driving_evidence=[
            NarrativeDecisionDrivingEvidence(
                evidence_id=evidence_id,
                summary=summary,
            )
            for evidence_id, summary in evidence_items
        ],
        locked_fields=locked_fields or NarrativeLockedFields(),
    )


def test_canonical_payload_is_frozen_from_deterministic_result():
    prepared, result = _sample_prepared_and_result()

    assert result.canonical_payload is not None
    assert result.canonical_payload.request_context.goal == prepared.goal
    assert result.canonical_payload.request_context.constraints == prepared.constraints
    assert result.canonical_payload.function_classification.primary_judgment == result.primary_judgment
    assert result.canonical_payload.function_classification.template_judgment == result.template_judgment
    assert result.canonical_payload.function_classification.structural_judgment == result.structural_judgment
    assert result.canonical_payload.decision_summary == result.decision_summary
    assert result.canonical_payload.analysis_summary == result.analysis_summary
    assert [item.model_dump() for item in result.canonical_payload.grounded_business_rules] == [
        item.model_dump() for item in result.grounded_business_rules
    ]
    assert [item.model_dump() for item in result.canonical_payload.execution_plan] == [
        item.model_dump() for item in result.execution_plan
    ]


def test_slim_payload_excludes_raw_assets_and_keeps_only_summary_inputs():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()

    slim_payload = service.build_slim_payload(
        canonical_payload=service.freeze_canonical_payload(prepared=prepared, result=result),
        result=result,
    )
    dumped = json.dumps(slim_payload.model_dump(), ensure_ascii=False)

    assert "source_code" not in dumped
    assert "sql_queries" not in dumped
    assert "ui_template" not in dumped
    assert "VERY_PRIVATE_SOURCE_MARKER" not in dumped
    assert "FULL_SQL_MARKER" not in dumped
    assert slim_payload.analysis_summary
    assert slim_payload.deterministic_narrative["one_line_conclusion"] == result.one_line_conclusion


def test_deterministic_explanation_blocks_include_recommended_option_mapping():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)

    blocks = service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
    recommended_block = next(block for block in blocks if block.block_id == "recommended_option")

    assert recommended_block.deterministic_lines
    recommended_text = recommended_block.deterministic_lines[0]
    assert result.recommended_option is not None
    assert result.recommended_option.name in recommended_text
    assert result.recommended_option.structure_summary in recommended_text
    assert result.recommended_option.selection_reason in recommended_text
    assert recommended_block.locked_fields.recommended_strategy == result.recommended_option.name


def test_deterministic_explanation_blocks_include_execution_plan_stage_mapping():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)

    blocks = service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
    execution_block = next(block for block in blocks if block.block_id == "execution_plan")
    execution_stages = result.improvement_plan_bundle.get("execution_stages") or []

    assert len(execution_block.deterministic_lines) == len(canonical.execution_plan)
    assert len(execution_block.critical_facts) == len(execution_stages)
    for index, stage in enumerate(execution_stages):
        assert execution_block.critical_facts[index].fact_id == stage["stage_id"]
        assert canonical.execution_plan[index].week_label in execution_block.deterministic_lines[index]
        assert stage["title"] in execution_block.deterministic_lines[index]


def test_deterministic_explanation_blocks_include_risk_mapping():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)

    blocks = service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
    risks_block = next(block for block in blocks if block.block_id == "risks")
    risk_checkpoints = result.improvement_plan_bundle.get("risk_checkpoints") or []

    assert len(risks_block.deterministic_lines) == len(canonical.risks)
    assert len(risks_block.critical_facts) == len(canonical.risks)
    assert len(risks_block.decision_driving_evidence) == len(canonical.risks)
    for index, risk_text in enumerate(canonical.risks):
        assert risks_block.deterministic_lines[index] == risk_text
        assert risks_block.critical_facts[index].text == risk_text
        if index < len(risk_checkpoints):
            assert risks_block.critical_facts[index].fact_id == risk_checkpoints[index]["checkpoint_id"]


def test_narrative_schema_validation_accepts_valid_layer_and_rejects_invalid_field():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    evidence_id = _first_evidence_id(result)

    valid_candidate = _build_valid_candidate(result, evidence_id)
    layer, failure_reason = service.validate_candidate(
        candidate=valid_candidate,
        canonical_payload=canonical,
        slim_payload=slim,
        result=result,
    )
    assert layer is not None
    assert failure_reason == ""

    invalid_layer, invalid_failure = service.validate_candidate(
        candidate={**valid_candidate, "unexpected_field": "boom"},
        canonical_payload=canonical,
        slim_payload=slim,
        result=result,
    )
    assert invalid_layer is None
    assert invalid_failure == "schema_validation_error"


@pytest.mark.parametrize(
    ("candidate_builder", "expected_failure"),
    [
        (
            lambda result, evidence_id: {
                **_build_valid_candidate(result, evidence_id),
                "primary_judgment_reason": "workflow 분류로 재해석합니다.",
            },
            "classification_mutation",
        ),
        (
            lambda result, evidence_id: {
                **_build_valid_candidate(
                    result.model_copy(
                        update={
                            "design_options": [
                                DesignOption(name="옵션 A", structure_summary="A"),
                                DesignOption(name="옵션 B", structure_summary="B"),
                            ],
                            "recommended_option": RecommendedOption(
                                name="옵션 A",
                                structure_summary="A",
                                selection_reason="A 유지",
                            ),
                        }
                    ),
                    evidence_id,
                ),
                "one_line_conclusion": "옵션 B를 선택해야 합니다.",
            },
            "recommended_option_mutation",
        ),
        (
            lambda result, evidence_id: {
                **_build_valid_candidate(result, evidence_id),
                "primary_judgment_reason": "imaginary_detector_candidate 기준으로 재조정합니다.",
            },
            "diagnosis_mutation",
        ),
        (
            lambda result, evidence_id: {
                **_build_valid_candidate(result, evidence_id),
                "executive_summary_v2": ["이 항목은 1순위로 올려야 합니다."],
            },
            "priority_mutation",
        ),
    ],
)
def test_validator_blocks_invariance_violations(candidate_builder, expected_failure):
    prepared, base_result = _sample_prepared_and_result()
    result = base_result
    service = NarrativeAugmentationService()
    evidence_id = _first_evidence_id(base_result)
    candidate = candidate_builder(result, evidence_id)
    if "옵션 B" in json.dumps(candidate, ensure_ascii=False):
        result = base_result.model_copy(
            update={
                "design_options": [
                    DesignOption(name="옵션 A", structure_summary="A"),
                    DesignOption(name="옵션 B", structure_summary="B"),
                ],
                "recommended_option": RecommendedOption(
                    name="옵션 A",
                    structure_summary="A",
                    selection_reason="A 유지",
                ),
                "canonical_payload": None,
            }
        )
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    layer, failure_reason = service.validate_candidate(
        candidate=candidate,
        canonical_payload=canonical,
        slim_payload=slim,
        result=result,
    )

    assert layer is None
    assert failure_reason == expected_failure


def test_validator_blocks_hallucinated_fact_and_rewrite_scope_violation():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)

    layer, failure_reason = service.validate_candidate(
        candidate={
            "report_purpose": "배송 보정 규칙과 신규 회수 정책을 설명합니다.",
            "primary_judgment_reason": "배송 보정 규칙을 새로 추가해야 합니다.",
        },
        canonical_payload=canonical,
        slim_payload=slim,
        result=result,
    )
    assert layer is None
    assert failure_reason in {"grounded_fact_mismatch", "forbidden_expression"}

    invalid_scope_layer, invalid_scope_reason = service.validate_candidate(
        candidate={
            **_build_valid_candidate(result, ""),
            "decision_narrative": [{"text": result.one_line_conclusion, "evidence_refs": ["ev_missing"]}],
        },
        canonical_payload=canonical,
        slim_payload=slim,
        result=result,
    )
    assert invalid_scope_layer is None
    assert invalid_scope_reason == "rewrite_scope_violation"


def test_block_validator_rejects_new_claim_generation():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="primary_judgment_reason",
        deterministic_lines=["주문 저장 시 validation과 save 책임이 결합되어 있습니다."],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["주문 저장 시 validation과 save 책임이 결합되어 있으며 승인 정책 누락도 핵심 원인입니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "unsupported_claim"
    assert validation.unsupported_claims


def test_block_validator_preserves_locked_fields():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="one_line_conclusion",
        deterministic_lines=["현재 구조는 refactor 방향으로 정리하는 것이 적합합니다."],
        locked_fields=NarrativeLockedFields(
            recommended_strategy="refactor",
            decision_type="refactor",
        ),
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["현재 구조는 redesign 방향으로 다시 잡는 것이 적합합니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "locked_field_mutation"
    assert set(validation.mutated_locked_fields) >= {"recommended_strategy", "decision_type"}


def test_block_validator_preserves_decision_evidence_coverage():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="executive_summary_v2",
        deterministic_lines=["validation과 save 경로를 먼저 분리해야 합니다."],
        evidence_items=[
            ("ev_validation", "required check 누락이 submit 분기에서 확인됨"),
            ("ev_save", "READY 상태 승인 예외가 분기 앞단에 걸려 있음"),
        ],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["validation과 save 경로를 먼저 분리해야 합니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "decision_evidence_coverage_missing"
    assert set(validation.missing_evidence_ids) == {"ev_validation", "ev_save"}


def test_block_validator_allows_decision_evidence_paraphrase_with_normalization():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="executive_summary_v2",
        deterministic_lines=["검증과 저장 흐름을 먼저 분리해야 합니다."],
        evidence_items=[
            ("ev_validation", "필수 검증 누락이 submit 분기에서 확인됨"),
        ],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["검증과 저장 흐름을 먼저 분리해야 합니다. 필수 확인 빠짐이 submit 조건 분기에서 드러납니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is True
    assert validation.failure_reason == ""
    assert validation.match_mode == "normalized"


def test_execution_plan_block_rejects_stage_order_mutation():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    execution_block = next(
        block
        for block in service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
        if block.block_id == "execution_plan"
    )

    reversed_lines = list(reversed(execution_block.deterministic_lines))
    validation = service.validate_explanation_block(
        block=execution_block,
        rewritten_lines=reversed_lines,
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "execution_stage_order_mutation"


def test_execution_plan_block_allows_task_synonym_paraphrase():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="execution_plan",
        deterministic_lines=["1주차: 검증 흐름 정리. 주요 작업은 검증 흐름 분리입니다."],
        evidence_items=[
            ("stage_1", "검증 흐름 분리"),
        ],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["1주차: 검증 흐름 정리. 주요 작업은 검사 플로우 격리입니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is True
    assert validation.failure_reason == ""
    assert validation.match_mode == "normalized"


def test_execution_plan_block_rejects_missing_primary_task_coverage():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    execution_block = next(
        block
        for block in service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
        if block.block_id == "execution_plan"
    )

    rewritten_lines = [
        re.sub(r"\. 주요 작업은 .+$", "", line).strip()
        for line in execution_block.deterministic_lines
    ]
    validation = service.validate_explanation_block(
        block=execution_block,
        rewritten_lines=rewritten_lines,
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "execution_stage_task_missing"


def test_recommended_option_block_allows_whitelisted_alias():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="recommended_option",
        deterministic_lines=["추천안은 책임 분리형 개선안이며, 저장 검증 경계를 재배치합니다."],
        locked_fields=NarrativeLockedFields(
            recommended_strategy="책임 분리형 개선안",
            recommended_option_aliases=["책임 분리형"],
        ),
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["추천안은 책임 분리형이며, 저장 검증 경계를 재배치합니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is True
    assert validation.failure_reason == ""
    assert validation.match_mode == "normalized"


def test_recommended_option_block_requires_exact_option_name():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    recommended_block = next(
        block
        for block in service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
        if block.block_id == "recommended_option"
    )

    option = result.recommended_option
    assert option is not None
    rewritten_line = f"{option.structure_summary}를 기준으로 {option.selection_reason}"
    validation = service.validate_explanation_block(
        block=recommended_block,
        rewritten_lines=[rewritten_line],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "recommended_option_name_missing"


def test_risks_block_rejects_item_count_mutation():
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    risks_block = next(
        block
        for block in service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
        if block.block_id == "risks"
    )

    validation = service.validate_explanation_block(
        block=risks_block,
        rewritten_lines=risks_block.deterministic_lines[:1],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "risk_item_count_mismatch"


def test_risks_block_allows_synonym_paraphrase_coverage():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload(
        risks=["승인 경계가 흐려질 수 있습니다."]
    )
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="risks",
        deterministic_lines=["승인 경계가 흐려질 수 있습니다."],
        evidence_items=[
            ("risk_checkpoint_1", "승인 경계가 흐려질 수 있습니다."),
        ],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["승인 경계가 불명확해질 수 있습니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is True
    assert validation.failure_reason == ""
    assert validation.match_mode == "normalized"


def test_block_validator_records_exact_match_mode_on_exact_pass():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload()
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="report_purpose",
        deterministic_lines=["주문 저장 흐름 현대화 판단을 위한 결과입니다."],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["주문 저장 흐름 현대화 판단을 위한 결과입니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is True
    assert validation.failure_reason == ""
    assert validation.match_mode == "exact"


def test_risks_block_rejects_missing_canonical_risk_coverage():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload(
        risks=["권한 분기가 저장 로직과 함께 처리되어 승인 경계가 흐려질 수 있습니다."]
    )
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="risks",
        deterministic_lines=["권한 분기가 저장 로직과 함께 처리되어 승인 경계가 흐려질 수 있습니다."],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["변경 영향이 있습니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "risk_coverage_missing"


def test_risks_block_rejects_severity_downgrade():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload(
        risks=["회귀 영향"]
    )
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="risks",
        deterministic_lines=["회귀 영향"],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["영향"],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason == "risk_severity_downgraded"


def test_risks_block_rejects_generalization_beyond_evidence():
    _, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = CanonicalRebuildPayload(
        risks=["READY 상태 승인 경로가 저장 로직과 결합되어 회귀 영향이 커질 수 있습니다."]
    )
    slim = service.build_slim_payload(canonical_payload=canonical, result=result)
    block = _build_guard_block(
        block_id="risks",
        deterministic_lines=["READY 상태 승인 경로가 저장 로직과 결합되어 회귀 영향이 커질 수 있습니다."],
        evidence_items=[
            ("risk_checkpoint_1", "READY 상태 승인 경로가 저장 로직과 결합되어 회귀 영향이 커질 수 있습니다."),
        ],
    )

    validation = service.validate_explanation_block(
        block=block,
        rewritten_lines=["전체 시스템에 치명적 장애를 일으킬 가능성이 매우 높습니다."],
        canonical_payload=canonical,
        slim_payload=slim,
    )

    assert validation.validation_passed is False
    assert validation.failure_reason in {"risk_generalization_beyond_evidence", "unsupported_claim"}


@pytest.mark.parametrize(
    ("llm_double", "expected_reason"),
    [
        (
            SimpleNamespace(generate=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timeout"))),
            "llm_generate_failed:TimeoutError",
        ),
        (
            SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(content="not-json")),
            "invalid_json_response",
        ),
    ],
)
def test_llm_failure_or_invalid_payload_falls_back(llm_double, expected_reason):
    prepared, result = _sample_prepared_and_result()

    class AsyncWrapper:
        async def generate(self, *args, **kwargs):
            output = llm_double.generate(*args, **kwargs)
            return output

    augmented = NarrativeAugmentationService().augment_sync(
        prepared=prepared,
        result=result,
        llm_service=AsyncWrapper(),
    )

    assert augmented.report_purpose == result.report_purpose
    assert augmented.one_line_conclusion == result.one_line_conclusion
    assert augmented.narrative_layer is None
    assert augmented.narrative_metadata is not None
    assert augmented.narrative_metadata.failure_reason == expected_reason
    assert augmented.narrative_metadata.fallback_used is True
    assert augmented.narrative_metadata.match_mode == "failed"
    assert all(item.match_mode == "failed" for item in augmented.narrative_metadata.block_results)
    assert all(item.match_mode == "failed" for item in augmented.narrative_metadata.block_rewrite_metadata)
    assert augmented.validated_explanation_blocks
    assert augmented.narrative_guard_metadata is not None
    assert augmented.extensions["narrative"]["source"] == "deterministic_fallback"
    assert augmented.extensions["narrative"]["match_mode"] == "failed"


@pytest.mark.asyncio
async def test_result_package_and_exports_use_validated_narrative_layer_when_present(tmp_path, monkeypatch):
    prepared, result = _sample_prepared_and_result()
    evidence_id = _first_evidence_id(result)

    class FakeLLM:
        def get_model_for_mode(self, mode):
            return "qwen3.5:9b"

        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(_build_valid_candidate(result, evidence_id), ensure_ascii=False),
                model="qwen3.5:9b",
            )

    narrative_service = NarrativeAugmentationService()
    augmentation = await narrative_service.augment(
        prepared=prepared,
        result=result,
        llm_service=FakeLLM(),
    )
    augmented = narrative_service.apply(result, augmentation)
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_narrative_pipeline"},
        augmented,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    assert pkg["canonical_payload"] is not None
    assert pkg["validated_narrative_layer"] is not None
    assert pkg["validated_explanation_blocks"]
    assert pkg["fallback_narrative_metadata"]["source"] == "ai"
    assert pkg["fallback_narrative_metadata"]["match_mode"] == "mixed"
    assert pkg["narrative_guard_metadata"]["source"] == "ai"
    assert pkg["narrative_guard_metadata"]["match_mode"] == "mixed"
    assert pkg["guard_match_mode"] == "mixed"
    assert isinstance(pkg["guard_block_match_modes"], dict)
    assert pkg["validated_narrative_layer"]["one_line_conclusion"] == augmented.one_line_conclusion
    markdown = _result_package_markdown(pkg, surface_mode="internal")
    assert _sample_project().project_name in markdown

    class FakeDocService:
        def is_available(self):
            return True

        async def generate(self, request):
            suffix = ".docx" if str(request.output_type).endswith("DOCX") else ".pptx"
            output_path = tmp_path / f"generated{suffix}"
            output_path.write_bytes(request.content.encode("utf-8"))
            return SimpleNamespace(output_path=str(output_path))

    monkeypatch.setattr(app_state, "doc_service", FakeDocService(), raising=False)
    docx_path, _ = await _generate_result_package_docx(_sample_project(), pkg)
    pptx_response = await _result_package_pptx_response(_sample_project(), pkg)

    assert Path(docx_path).exists()
    assert Path(pptx_response.path).exists()


def test_runner_emits_canonical_and_narrative_payloads(monkeypatch):
    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)
    monkeypatch.setattr(app_state, "narrative_llm_service", None, raising=False)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {"rebuild-temp": "<% String sql = \"SELECT * FROM orders\"; %>"}, raising=False)

    start_compat_run = rebuild_compat.start_rebuild_assistant_run_compat
    start_compat_run(
        run_id="run_rebuild_narrative_pipeline",
        session_id="session-test",
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        assets=rebuild_compat.RebuildAssetsPayload(
            source_code="<% String sql = \"SELECT * FROM orders\"; %>",
            sql_queries="SELECT * FROM orders WHERE status = 'READY'",
        ),
        constraints=["기존 DB 호환 유지"],
        temp_session_id="rebuild-temp",
    )

    finished = [event for event in events if event["type"] == "run_finished"]
    assert len(finished) == 1
    payload = finished[0]["payload"]
    assert payload["canonical_payload"] is not None
    assert payload["validated_narrative_layer"] is None
    assert payload["validated_explanation_blocks"]
    assert payload["fallback_narrative_metadata"]["source"] == "deterministic_fallback"
    assert payload["fallback_narrative_metadata"]["match_mode"] == "failed"
    assert payload["narrative_guard_metadata"]["source"] == "deterministic_fallback"
    assert payload["narrative_guard_metadata"]["match_mode"] == "failed"
    assert payload["guard_match_mode"] == "failed"
    assert isinstance(payload["guard_block_match_modes"], dict)


def test_resolve_explanation_blocks_logs_rule_and_match_mode(caplog):
    prepared, result = _sample_prepared_and_result()
    service = NarrativeAugmentationService()
    canonical = service.freeze_canonical_payload(prepared=prepared, result=result)
    blocks = service.build_deterministic_explanation_blocks(canonical_payload=canonical, result=result)
    slim = service.build_slim_payload(canonical_payload=canonical, result=result, explanation_blocks=blocks)
    candidate = service.materialize_narrative_layer(blocks).model_dump()
    candidate["execution_plan"] = [
        line.replace("검증", "검사").replace("분리", "격리")
        for line in candidate["execution_plan"]
    ]

    with caplog.at_level("INFO"):
        _, block_results, _ = service.resolve_explanation_blocks(
            candidate=candidate,
            canonical_payload=canonical,
            slim_payload=slim,
        )

    execution_result = next(item for item in block_results if item.block_id == "execution_plan")
    assert execution_result.validation_passed is True
    assert execution_result.match_mode == "normalized"
    assert any(
        "block=execution_plan" in record.message
        and "rule=normalized_synonym_match" in record.message
        and "match_mode=normalized" in record.message
        for record in caplog.records
    )
