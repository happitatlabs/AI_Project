from __future__ import annotations

import asyncio
import threading

from mellow_link import app_state
from mellow_link.infra.run_events import (
    EVENT_TYPE_PLAN_CREATED,
    EVENT_TYPE_RUN_FINISHED,
    EVENT_TYPE_RUN_STARTED,
    EVENT_TYPE_TODO_DONE,
    EVENT_TYPE_TODO_STARTED,
    emit_event,
)

from .service import ResearchAssistantService


def start_research_run(
    run_id: str,
    session_id: str | None,
    question: str,
    context_note: str = "",
    temp_session_id: str | None = None,
) -> None:
    todos = [
        {"todo_id": "R1", "title": "질문 정리", "status": "pending"},
        {"todo_id": "R2", "title": "문서 문맥 수집", "status": "pending"},
        {"todo_id": "R3", "title": "문서 기반 분석", "status": "pending"},
        {"todo_id": "R4", "title": "결과 요약", "status": "pending"},
    ]

    async def _run_async() -> None:
        svc = ResearchAssistantService()
        try:
            document_context = ""
            if temp_session_id:
                document_context = str(app_state.TEMP_CONTEXT_STORE.get(temp_session_id, "") or "")
            emit_event(
                run_id,
                EVENT_TYPE_RUN_STARTED,
                {
                    "user_input": question[:200],
                    "mode": "research",
                    "session_id": session_id,
                    "temp_session_id": temp_session_id,
                    "has_document_context": bool(document_context),
                },
            )
            emit_event(run_id, EVENT_TYPE_PLAN_CREATED, {"todos": todos})
            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[0])
            emit_event(
                run_id,
                EVENT_TYPE_TODO_DONE,
                {
                    **todos[0],
                    "detail": "질문과 요청 형식을 분석했습니다.",
                },
            )

            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[1])
            context_detail = "업로드된 문서가 없어 일반 리서치 문맥으로 진행합니다."
            if document_context:
                context_detail = f"업로드 문서 문맥 {min(len(document_context), svc.MAX_DOCUMENT_CHARS)}자를 분석 입력으로 반영했습니다."
            emit_event(
                run_id,
                EVENT_TYPE_TODO_DONE,
                {
                    **todos[1],
                    "detail": context_detail,
                },
            )

            orch = getattr(app_state, "orchestrator", None)
            if not orch:
                raise RuntimeError("Orchestrator not initialized")
            prompt = svc.build_prompt(question, context_note, document_context=document_context)
            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[2])
            result = await orch.run_agent(
                prompt,
                history=[],
                is_admin=False,
                mode="research",
                session_id=session_id,
                session_state={
                    "run_id": run_id,
                    "module_id": "research_assistant",
                    "temp_session_id": temp_session_id,
                },
            )
            raw_summary = getattr(result, "text", None) or getattr(result, "summary", None) or ""
            summary = str(raw_summary).strip() or "문서 기반 리서치 실행이 완료되었습니다."
            emit_event(
                run_id,
                EVENT_TYPE_TODO_DONE,
                {
                    **todos[2],
                    "detail": "문서와 질문을 기준으로 분석 응답을 생성했습니다.",
                },
            )
            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[3])
            emit_event(
                run_id,
                EVENT_TYPE_TODO_DONE,
                {
                    **todos[3],
                    "detail": "사용자 콘솔에 표시할 요약 결과를 정리했습니다.",
                },
            )
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {
                    "success": True,
                    "summary": str(summary)[:4000],
                    "module_id": "research_assistant",
                    "run_kind": "research_run",
                },
            )
        except Exception as e:
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {
                    "success": False,
                    "summary": f"Research run failed: {str(e)[:300]}",
                    "module_id": "research_assistant",
                    "run_kind": "research_run",
                },
            )

    def _run_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_async())
        finally:
            loop.close()

    threading.Thread(target=_run_thread, daemon=True).start()
