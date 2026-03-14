from __future__ import annotations

import asyncio
import threading

from mellow_link.infra.run_events import (
    EVENT_TYPE_PLAN_CREATED,
    EVENT_TYPE_RUN_FINISHED,
    EVENT_TYPE_RUN_STARTED,
    emit_event,
)

from .service import ResearchAssistantService


def start_research_run(run_id: str, session_id: str | None, question: str, context_note: str = "") -> None:
    todos = [
        {"todo_id": "R1", "title": "질문 분석", "status": "pending"},
        {"todo_id": "R2", "title": "문맥 수집", "status": "pending"},
        {"todo_id": "R3", "title": "요약 생성", "status": "pending"},
    ]

    async def _run_async() -> None:
        from mellow_link import app_state

        svc = ResearchAssistantService()
        try:
            emit_event(run_id, EVENT_TYPE_RUN_STARTED, {"user_input": question[:200], "mode": "research", "session_id": session_id})
            emit_event(run_id, EVENT_TYPE_PLAN_CREATED, {"todos": todos})
            orch = getattr(app_state, "orchestrator", None)
            if not orch:
                raise RuntimeError("Orchestrator not initialized")
            prompt = svc.build_prompt(question, context_note)
            result = await orch.run_agent(
                prompt,
                history=[],
                is_admin=False,
                mode="research",
                session_id=session_id,
                session_state={"run_id": run_id, "module_id": "research_assistant"},
            )
            summary = getattr(result, "text", None) or getattr(result, "summary", None) or "Research run completed"
            emit_event(run_id, EVENT_TYPE_RUN_FINISHED, {"success": True, "summary": str(summary)[:1000], "module_id": "research_assistant", "run_kind": "research_run"})
        except Exception as e:
            emit_event(run_id, EVENT_TYPE_RUN_FINISHED, {"success": False, "summary": f"Research run failed: {str(e)[:300]}", "module_id": "research_assistant", "run_kind": "research_run"})

    def _run_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_async())
        finally:
            loop.close()

    threading.Thread(target=_run_thread, daemon=True).start()
