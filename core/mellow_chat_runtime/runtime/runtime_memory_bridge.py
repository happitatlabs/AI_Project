from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from mellow_chat_runtime import app_state
from mellow_chat_runtime.runtime.schemas import TurnRequest, TurnResponse

logger = logging.getLogger(__name__)

_INTENT_MAX_CHARS = 2000


def _map_intent_type(text: str) -> str:
    return (text or 'chat').strip()[:_INTENT_MAX_CHARS] or 'chat'


async def record_runtime_experience_ledger(req: TurnRequest, response: TurnResponse) -> None:
    from mellow_link.infra.memory_database import get_memory_db

    trace_id = response.meta.trace_id
    session_id = response.state.session_id
    state_version = response.state.state_version
    runtime_impl = response.meta.runtime_impl
    intent_type = _map_intent_type(req.input.text)
    latency_ms = float(response.meta.latency_ms or 0.0)

    try:
        db = get_memory_db()
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(
            None,
            lambda: db.record_ledger_entry(
                timestamp=datetime.utcnow(),
                intent_type=intent_type,
                is_success=1,
                latency_ms=latency_ms,
                used_tools=[],
                error_message=None,
            ),
        )
        if ok:
            logger.info(
                'runtime_memory_ledger_recorded trace_id=%s session_id=%s state_version=%s runtime_impl=%s',
                trace_id,
                session_id,
                state_version,
                runtime_impl,
            )
        else:
            logger.warning(
                'runtime_memory_ledger_failed trace_id=%s session_id=%s state_version=%s runtime_impl=%s error=record_ledger_entry_returned_false',
                trace_id,
                session_id,
                state_version,
                runtime_impl,
            )
    except Exception as exc:
        logger.warning(
            'runtime_memory_ledger_failed trace_id=%s session_id=%s state_version=%s runtime_impl=%s error=%s',
            trace_id,
            session_id,
            state_version,
            runtime_impl,
            exc,
        )


async def schedule_runtime_experience_ledger(req: TurnRequest, response: TurnResponse) -> None:
    logger.info(
        'runtime_memory_bridge_scheduled trace_id=%s session_id=%s state_version=%s runtime_impl=%s',
        response.meta.trace_id,
        response.state.session_id,
        response.state.state_version,
        response.meta.runtime_impl,
    )
    task = asyncio.create_task(record_runtime_experience_ledger(req, response))
    await app_state.track_runtime_background_task(task)
