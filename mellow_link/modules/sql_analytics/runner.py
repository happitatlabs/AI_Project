from __future__ import annotations

import threading

from mellow_link.infra.run_events import (
    EVENT_TYPE_PLAN_CREATED,
    EVENT_TYPE_RUN_FINISHED,
    EVENT_TYPE_RUN_STARTED,
    EVENT_TYPE_TODO_DONE,
    EVENT_TYPE_TODO_STARTED,
    emit_event,
)

from .service import SQLAnalyticsService


def start_sql_analytics_run(run_id: str, session_id: str | None, question: str, input_type: str = "natural_language") -> None:
    todos = [
        {"todo_id": "S1", "title": "질문 정규화", "status": "pending"},
        {"todo_id": "S2", "title": "SQL 템플릿 선택", "status": "pending"},
        {"todo_id": "S3", "title": "SQL 실행", "status": "pending"},
        {"todo_id": "S4", "title": "결과 요약", "status": "pending"},
    ]

    def _run() -> None:
        service = SQLAnalyticsService()
        try:
            emit_event(run_id, EVENT_TYPE_RUN_STARTED, {"user_input": question[:200], "mode": "module", "session_id": session_id})
            emit_event(run_id, EVENT_TYPE_PLAN_CREATED, {"todos": todos})
            for todo in todos[:-1]:
                emit_event(run_id, EVENT_TYPE_TODO_STARTED, todo)
                emit_event(run_id, EVENT_TYPE_TODO_DONE, todo)
            emit_event(run_id, EVENT_TYPE_TODO_STARTED, todos[-1])
            result = service.analyze(question=question, input_type=input_type)
            summary = result.get("ai_interpretation") or result.get("decision") or "SQL analytics run completed"
            emit_event(run_id, EVENT_TYPE_TODO_DONE, todos[-1])
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {
                    "success": True,
                    "summary": str(summary)[:1000],
                    "module_id": "sql_analytics",
                    "run_kind": "sql_analysis",
                },
            )
        except Exception as e:
            emit_event(
                run_id,
                EVENT_TYPE_RUN_FINISHED,
                {"success": False, "summary": f"SQL analytics failed: {str(e)[:300]}", "module_id": "sql_analytics", "run_kind": "sql_analysis"},
            )

    threading.Thread(target=_run, daemon=True).start()
