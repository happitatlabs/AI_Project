from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

settings = None
orchestrator = None
llm_service = None

SESSION_BUSY = set()
SESSION_BUSY_LOCK = asyncio.Lock()
SESSION_STATE_VERSIONS: dict[str, int] = {}
SESSION_STATE_LOCK = asyncio.Lock()
RUNTIME_BACKGROUND_TASKS: set[asyncio.Task] = set()
RUNTIME_BACKGROUND_TASKS_LOCK = asyncio.Lock()
RUNTIME_LAST_ERROR: Optional[str] = None
RUNTIME_LAST_ERROR_TRACE_ID: Optional[str] = None
RUNTIME_LAST_ERROR_CODE: Optional[str] = None
RUNTIME_LAST_ERROR_RUNTIME_IMPL: Optional[str] = None
RUNTIME_LAST_ERROR_PATH: Optional[str] = None
RUNTIME_LAST_ERROR_STATUS_CODE: Optional[int] = None
RUNTIME_STATUS_LOCK = asyncio.Lock()


async def next_state_version(session_id: str) -> int:
    async with SESSION_STATE_LOCK:
        next_value = SESSION_STATE_VERSIONS.get(session_id, 0) + 1
        SESSION_STATE_VERSIONS[session_id] = next_value
        return next_value


async def record_runtime_success(runtime_impl: Optional[str] = None) -> None:
    global RUNTIME_LAST_ERROR, RUNTIME_LAST_ERROR_TRACE_ID, RUNTIME_LAST_ERROR_CODE, RUNTIME_LAST_ERROR_RUNTIME_IMPL, RUNTIME_LAST_ERROR_PATH, RUNTIME_LAST_ERROR_STATUS_CODE
    async with RUNTIME_STATUS_LOCK:
        if RUNTIME_LAST_ERROR is not None:
            logger.info(
                'runtime_status_transition degraded=false runtime_impl=%s previous_error_code=%s previous_status_code=%s previous_path=%s trace_id=%s',
                runtime_impl or RUNTIME_LAST_ERROR_RUNTIME_IMPL or 'unknown',
                RUNTIME_LAST_ERROR_CODE or 'unknown',
                RUNTIME_LAST_ERROR_STATUS_CODE or 0,
                RUNTIME_LAST_ERROR_PATH or 'unknown',
                RUNTIME_LAST_ERROR_TRACE_ID or 'missing',
            )
        RUNTIME_LAST_ERROR = None
        RUNTIME_LAST_ERROR_TRACE_ID = None
        RUNTIME_LAST_ERROR_CODE = None
        RUNTIME_LAST_ERROR_RUNTIME_IMPL = None
        RUNTIME_LAST_ERROR_PATH = None
        RUNTIME_LAST_ERROR_STATUS_CODE = None


async def record_runtime_error(
    message: str,
    trace_id: Optional[str] = None,
    *,
    error_code: Optional[str] = None,
    runtime_impl: Optional[str] = None,
    path: Optional[str] = None,
    status_code: Optional[int] = None,
) -> None:
    global RUNTIME_LAST_ERROR, RUNTIME_LAST_ERROR_TRACE_ID, RUNTIME_LAST_ERROR_CODE, RUNTIME_LAST_ERROR_RUNTIME_IMPL, RUNTIME_LAST_ERROR_PATH, RUNTIME_LAST_ERROR_STATUS_CODE
    async with RUNTIME_STATUS_LOCK:
        was_degraded = RUNTIME_LAST_ERROR is not None
        RUNTIME_LAST_ERROR = message
        RUNTIME_LAST_ERROR_TRACE_ID = trace_id
        RUNTIME_LAST_ERROR_CODE = error_code
        RUNTIME_LAST_ERROR_RUNTIME_IMPL = runtime_impl
        RUNTIME_LAST_ERROR_PATH = path
        RUNTIME_LAST_ERROR_STATUS_CODE = status_code
        if not was_degraded:
            logger.warning(
                'runtime_status_transition degraded=true error_code=%s message=%s runtime_impl=%s path=%s status_code=%s trace_id=%s',
                error_code or 'unknown',
                message,
                runtime_impl or 'unknown',
                path or 'unknown',
                status_code or 0,
                trace_id or 'missing',
            )


async def get_runtime_health_snapshot() -> dict[str, object]:
    async with RUNTIME_STATUS_LOCK:
        if RUNTIME_LAST_ERROR:
            trace_suffix = f' (trace_id={RUNTIME_LAST_ERROR_TRACE_ID})' if RUNTIME_LAST_ERROR_TRACE_ID else ''
            return {
                'last_error': f'{RUNTIME_LAST_ERROR}{trace_suffix}',
                'degraded': True,
            }
        return {
            'last_error': None,
            'degraded': False,
        }


def resolve_effective_tier(requested_tier: Optional[str]) -> str:
    requested = (requested_tier or 'free').strip().lower()
    if requested == 'pro':
        return 'pro'
    return 'free'


def tier_to_mode(effective_tier: str) -> str:
    return 'thinking' if effective_tier == 'pro' else 'fast'


async def track_runtime_background_task(task: asyncio.Task) -> None:
    async with RUNTIME_BACKGROUND_TASKS_LOCK:
        RUNTIME_BACKGROUND_TASKS.add(task)

    def _discard(done_task: asyncio.Task) -> None:
        try:
            RUNTIME_BACKGROUND_TASKS.discard(done_task)
        except Exception:
            pass

    task.add_done_callback(_discard)


async def drain_runtime_background_tasks() -> None:
    async with RUNTIME_BACKGROUND_TASKS_LOCK:
        pending = [task for task in list(RUNTIME_BACKGROUND_TASKS) if not task.done()]
    if not pending:
        return
    await asyncio.gather(*pending, return_exceptions=True)


async def reset_runtime_state_for_tests() -> None:
    global RUNTIME_LAST_ERROR, RUNTIME_LAST_ERROR_TRACE_ID, RUNTIME_LAST_ERROR_CODE, RUNTIME_LAST_ERROR_RUNTIME_IMPL, RUNTIME_LAST_ERROR_PATH, RUNTIME_LAST_ERROR_STATUS_CODE
    await drain_runtime_background_tasks()
    async with SESSION_STATE_LOCK:
        SESSION_STATE_VERSIONS.clear()
    async with RUNTIME_BACKGROUND_TASKS_LOCK:
        RUNTIME_BACKGROUND_TASKS.clear()
    async with RUNTIME_STATUS_LOCK:
        RUNTIME_LAST_ERROR = None
        RUNTIME_LAST_ERROR_TRACE_ID = None
        RUNTIME_LAST_ERROR_CODE = None
        RUNTIME_LAST_ERROR_RUNTIME_IMPL = None
        RUNTIME_LAST_ERROR_PATH = None
        RUNTIME_LAST_ERROR_STATUS_CODE = None
