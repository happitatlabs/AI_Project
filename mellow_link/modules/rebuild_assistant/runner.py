from __future__ import annotations

import threading
from typing import Callable

from mellow_link.infra.run_events import (
    EVENT_TYPE_LOG,
    EVENT_TYPE_PLAN_CREATED,
    EVENT_TYPE_RUN_FINISHED,
    EVENT_TYPE_RUN_STARTED,
    EVENT_TYPE_TODO_DONE,
    EVENT_TYPE_TODO_STARTED,
    emit_event,
)
from mellow_link.services.anonymization.schemas import SafeAnalysisBundle

from .service import RebuildAssistantService


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
) -> None:
    todos = _rebuild_todos()

    def _run() -> None:
        service = RebuildAssistantService()
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

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[0])
            prepared = prepare_input(service)
            emit_event(
                run_id,
                EVENT_TYPE_LOG,
                {
                    "level": "info",
                    "message": "rebuild input prepared",
                    "scope_limited": prepared.scope_limited,
                    "missing_context_count": len(prepared.missing_context),
                },
            )
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[0], "detail": "입력 검증, 업로드 문맥 수집, 범위 제한 여부를 확인했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[1])
            analysis_summary = service.analyze_assets(prepared)
            emit_event(run_id, EVENT_TYPE_LOG, {"level": "info", "message": "legacy analysis complete", "findings": analysis_summary[:3]})
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[1], "detail": "레거시 구조와 기능 슬라이스 후보를 분석했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[2])
            strategy = service.infer_target_architecture(prepared)
            emit_event(run_id, EVENT_TYPE_LOG, {"level": "info", "message": "rebuild design complete", "strategy": strategy[:3]})
            emit_event(run_id, EVENT_TYPE_TODO_DONE, {**todos[2], "detail": "구조 진단과 의사결정 방향을 확정했습니다."})

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[3])
            draft = service.build_recomposition_draft(prepared)
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
                    "primary_judgment_reason": result.primary_judgment_reason,
                    "pattern_candidates": [item.model_dump() for item in result.pattern_candidates],
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
                    "summary": summary[:4000],
                    "structured_result": result.model_dump(),
                    "authoritative_payload": {
                        "structure_snapshot": result.structure_snapshot,
                        "diagnosis_report": result.diagnosis_report,
                        "decision_summary": result.decision_summary,
                        "improvement_plan_bundle": result.improvement_plan_bundle,
                        "appendix": result.appendix,
                    },
                    "polish_bundle": polish_bundle.model_dump(),
                    "primary_feature_mode": prepared.signals.primary_feature_mode,
                    "secondary_feature_mode": prepared.signals.secondary_feature_mode,
                    "confidence": result.confidence,
                    "needs_more_input": needs_more_input,
                    "scope_limited": prepared.scope_limited,
                    "module_id": "rebuild_assistant",
                    "run_kind": "rebuild_plan",
                    "primary_judgment": primary_template_id,
                    "judgment_template_key": primary_template_id,
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
) -> None:
    _spawn_rebuild_run(
        run_id=run_id,
        session_id=session_id,
        goal=goal,
        prepare_input=lambda service: service.prepare_safe_bundle_input(
            goal=goal,
            safe_bundle=safe_bundle,
            constraints=constraints,
        ),
        run_meta={"safe_bundle_id": safe_bundle.bundle_id},
    )
