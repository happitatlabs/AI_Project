from __future__ import annotations

import threading
from typing import Callable

from mellow_link import app_state
from mellow_link.infra.run_events import (
    EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT,
    EVENT_TYPE_LOG,
    EVENT_TYPE_PLAN_CREATED,
    EVENT_TYPE_RUN_FINISHED,
    EVENT_TYPE_RUN_STARTED,
    EVENT_TYPE_TODO_DONE,
    EVENT_TYPE_TODO_STARTED,
    emit_event,
)
from mellow_link.services.anonymization import build_debug_anonymization_report_from_bundle
from mellow_link.services.anonymization.schemas import SafeAnalysisBundle
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)
from mellow_link.services.refactoring_support_engine.runtime_contracts import (
    build_stage_control,
    snapshot_stage_control,
)
from mellow_link.services.refactoring_support_engine.schemas import AnalysisContextBundle
from mellow_link.services.refactoring_support_engine.template_support import TemplateSupport

from .service import RebuildAssistantService


def _context_linkage(prepared: object, result: object | None = None) -> dict:
    context = getattr(prepared, "analysis_context", None)
    if context is None:
        return {
            "context_id": getattr(result, "context_id", "") if result is not None else "",
            "input_fingerprint": getattr(result, "input_fingerprint", "") if result is not None else "",
            "safe_bundle_id": getattr(result, "safe_bundle_id", "") if result is not None else "",
            "evidence_refs": list(getattr(result, "evidence_refs", []) or []) if result is not None else [],
        }
    result_refs = list(getattr(result, "evidence_refs", []) or []) if result is not None else []
    if not result_refs:
        result_refs = [item.evidence_id for item in context.evidence_index]
    return {
        "context_id": context.context_id,
        "input_fingerprint": context.run.input_fingerprint,
        "safe_bundle_id": context.trust.safe_bundle_id,
        "evidence_refs": result_refs,
    }


def _apply_context_linkage(result: object, linkage: dict) -> None:
    for key in ("context_id", "input_fingerprint", "safe_bundle_id", "evidence_refs"):
        if hasattr(result, key):
            setattr(result, key, linkage.get(key, [] if key == "evidence_refs" else ""))


def _rebuild_todos() -> list[dict[str, str]]:
    return [
        {"todo_id": "B1", "title": "입력 정규화", "status": "pending"},
        {"todo_id": "B2", "title": "구조 분석", "status": "pending"},
        {"todo_id": "B3", "title": "진단 및 판단", "status": "pending"},
        {"todo_id": "B4", "title": "개선안 생성", "status": "pending"},
        {"todo_id": "B5", "title": "결과 패키징", "status": "pending"},
    ]


def _spawn_rebuild_run(
    *,
    run_id: str,
    session_id: str | None,
    goal: str,
    prepare_input: Callable[[RebuildAssistantService], object],
    run_meta: dict,
    safe_bundle: SafeAnalysisBundle | None = None,
) -> None:
    todos = _rebuild_todos()
    narrative_augmentation = NarrativeAugmentationService()
    stage_control = build_stage_control(goal)

    def _run() -> None:
        service = RebuildAssistantService()
        template_support = TemplateSupport()
        anonymization_summary = None
        try:
            emit_event(
                run_id,
                EVENT_TYPE_RUN_STARTED,
                {
                    "user_input": goal[:200],
                    "mode": "module",
                    "session_id": session_id,
                    **run_meta,
                },
            )
            emit_event(run_id, EVENT_TYPE_PLAN_CREATED, {"todos": todos})
            emit_event(
                run_id,
                EVENT_TYPE_LOG,
                {
                    "level": "info",
                    "message": "stage control initialized",
                    "stage_control": snapshot_stage_control(stage_control, goal=goal),
                },
            )

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[0])
            prepared = prepare_input(service)
            prepared.stage_control = stage_control
            if safe_bundle is not None:
                debug_report = build_debug_anonymization_report_from_bundle(safe_bundle)
                anonymization_summary = debug_report["report_summary"]
                emit_event(run_id, EVENT_TYPE_DEBUG_ANONYMIZATION_REPORT, debug_report)
                emit_event(
                    run_id,
                    EVENT_TYPE_LOG,
                    {
                        "level": "info",
                        "message": "anonymization bundle ready",
                        "policy_version": debug_report["policy_version"],
                        "masking_level": anonymization_summary["masking_level"],
                        "applied": anonymization_summary["applied"],
                        "total_replacements": anonymization_summary["total_replacements"],
                        "validation_passed": anonymization_summary["validation_passed"],
                    },
                )
            emit_event(
                run_id,
                EVENT_TYPE_LOG,
                {
                    "level": "info",
                    "message": "rebuild input prepared",
                    "scope_limited": prepared.scope_limited,
                    "missing_context_count": len(prepared.missing_context),
                    **_context_linkage(prepared),
                },
            )
            question_guard_summary = getattr(prepared, "question_guard_summary", None)
            if question_guard_summary is not None:
                emit_event(
                    run_id,
                    EVENT_TYPE_LOG,
                    {
                        "level": "info",
                        "message": "source question guard applied",
                        "question_guard_summary": (
                            question_guard_summary.model_dump()
                            if hasattr(question_guard_summary, "model_dump")
                            else {}
                        ),
                    },
                )
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[0], "detail": "입력 검증, 업로드 문맥 수집, 범위 제한 여부를 확인했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[1])
            analysis_summary = service.analyze_assets(prepared)
            emit_event(run_id, EVENT_TYPE_LOG, {"level": "info", "message": "legacy analysis complete", "findings": analysis_summary[:3]})
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[1], "detail": "레거시 구조와 기능 슬라이스 후보를 분석했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[2])
            strategy = template_support.infer_target_architecture(prepared)
            emit_event(run_id, EVENT_TYPE_LOG, {"level": "info", "message": "rebuild design complete", "strategy": strategy[:3]})
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[2], "detail": "구조 진단과 의사결정 방향을 확정했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[3])
            draft = template_support.build_recomposition_draft(prepared)
            emit_event(
                run_id,
                EVENT_TYPE_LOG,
                {
                    "level": "info",
                    "message": "recomposition draft prepared",
                    "draft_layers": {"database": len(draft.database), "backend": len(draft.backend), "frontend": len(draft.frontend)},
                },
            )
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[3], "detail": "설계 옵션과 단계별 개선안을 생성했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[4])
            result = service.build_result(prepared)
            result = narrative_augmentation.augment_sync(
                prepared=prepared,
                result=result,
                llm_service=getattr(app_state, "narrative_llm_service", None),
                stage_control=stage_control,
            )
            result = service._sanitize_structured_result(result)
            context_linkage = _context_linkage(prepared, result)
            _apply_context_linkage(result, context_linkage)
            polish_bundle = service.build_polish_bundle(
                result,
                audience="manager",
                delivery_mode="client_report",
                use_ai_rewrite=False,
            )
            primary_template_id = result.primary_judgment or ""
            emit_event(
                run_id,
                EVENT_TYPE_LOG,
                {
                    "level": "info",
                    "message": "primary judgment selected",
                    "primary_judgment": primary_template_id,
                    "template_judgment": result.template_judgment,
                    "structural_judgment": result.structural_judgment,
                    "narrative_axis": result.narrative_axis,
                    "feature_signal_mode": result.feature_signal_mode,
                    "primary_judgment_reason": result.primary_judgment_reason,
                    "pattern_candidates": [item.model_dump() for item in result.pattern_candidates],
                    "narrative": result.extensions.get("narrative", {}) if isinstance(result.extensions, dict) else {},
                },
            )
            needs_more_input = bool(result.missing_context or result.confidence < 0.45)
            summary = service.format_user_summary(result, scope_limited=prepared.scope_limited, needs_more_input=needs_more_input)
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[4], "detail": "구조화 결과와 사용자 요약을 정리했습니다."})
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {
                    "success": True,
                    **context_linkage,
                    "summary": summary[:4000],
                    "structured_result": result.model_dump(),
                    "authoritative_payload": {
                        "family_classification": result.family_classification.model_dump(),
                        "structure_snapshot": result.structure_snapshot,
                        "diagnosis_report": result.diagnosis_report,
                        "decision_summary": result.decision_summary,
                        "improvement_plan_bundle": result.improvement_plan_bundle,
                        "appendix": result.appendix,
                    },
                    "canonical_payload": result.canonical_payload.model_dump() if result.canonical_payload else None,
                    "validated_narrative_layer": result.narrative_layer.model_dump() if result.narrative_layer else None,
                    "validated_explanation_blocks": [
                        item.model_dump() for item in (result.validated_explanation_blocks or [])
                    ],
                    "fallback_narrative_metadata": result.narrative_metadata.model_dump() if result.narrative_metadata else None,
                    "narrative_guard_metadata": (
                        result.narrative_guard_metadata.model_dump()
                        if result.narrative_guard_metadata
                        else None
                    ),
                    "guard_match_mode": (
                        result.narrative_guard_metadata.match_mode
                        if result.narrative_guard_metadata
                        else "failed"
                    ),
                    "guard_block_match_modes": (
                        dict(result.narrative_guard_metadata.block_match_modes)
                        if result.narrative_guard_metadata
                        else {}
                    ),
                    "source_question_candidates": [
                        item.model_dump() for item in (getattr(prepared, "source_question_candidates", []) or [])
                    ],
                    "blocked_user_questions": [
                        item.model_dump() for item in (getattr(prepared, "blocked_user_questions", []) or [])
                    ],
                    "review_user_questions": [
                        item.model_dump() for item in (getattr(prepared, "review_user_questions", []) or [])
                    ],
                    "question_guard_summary": (
                        prepared.question_guard_summary.model_dump()
                        if hasattr(getattr(prepared, "question_guard_summary", None), "model_dump")
                        else None
                    ),
                    "judgment_canvas": result.judgment_canvas,
                    "stage_control": result.stage_control,
                    "validation_result": result.validation_result,
                    "polish_bundle": polish_bundle.model_dump(),
                    "primary_feature_mode": prepared.signals.primary_feature_mode,
                    "secondary_feature_mode": prepared.signals.secondary_feature_mode,
                    "confidence": result.confidence,
                    "needs_more_input": needs_more_input,
                    "scope_limited": prepared.scope_limited,
                    "module_id": "rebuild_assistant",
                    "run_kind": "rebuild_plan",
                    "primary_judgment": primary_template_id,
                    "template_judgment": result.template_judgment,
                    "structural_judgment": result.structural_judgment,
                    "narrative_axis": result.narrative_axis,
                    "feature_signal_mode": result.feature_signal_mode,
                    "judgment_template_key": primary_template_id,
                    "anonymization_summary": anonymization_summary,
                },
            )
        except Exception as e:
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {
                    "success": False,
                    "summary": f"Rebuild assistant failed: {str(e)[:300]}",
                    "module_id": "rebuild_assistant",
                    "run_kind": "rebuild_plan",
                    "anonymization_summary": anonymization_summary,
                },
            )

    threading.Thread(target=_run, daemon=True).start()

def start_rebuild_assistant_safe_bundle_run(
    run_id: str,
    session_id: str | None,
    *,
    goal: str,
    safe_bundle: SafeAnalysisBundle,
    constraints: list[str] | None = None,
    analysis_context: AnalysisContextBundle | None = None,
) -> None:
    if analysis_context is None:
        analysis_context = AnalysisContextBuilder().build(
            project_id=safe_bundle.project_id,
            run_id=run_id,
            safe_bundle=safe_bundle,
            goal=goal,
            constraints=constraints or [],
        )

    def _prepare(service: RebuildAssistantService):
        prepared = service.prepare_analysis_context_input(analysis_context=analysis_context)
        prepared.safe_bundle = safe_bundle
        return prepared

    _spawn_rebuild_run(
        run_id=run_id,
        session_id=session_id,
        goal=goal,
        prepare_input=_prepare,
        run_meta={
            "safe_bundle_id": safe_bundle.bundle_id,
            "context_id": analysis_context.context_id,
            "input_fingerprint": analysis_context.run.input_fingerprint,
        },
        safe_bundle=safe_bundle,
    )
