from __future__ import annotations

import logging
import time

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mellow_chat_runtime import app_state
from mellow_chat_runtime.runtime import ErrorBody, ErrorDetail, StatusResponse, TurnRequest, TurnResponse, get_runtime_adapter
from mellow_chat_runtime.runtime.runtime_memory_bridge import schedule_runtime_experience_ledger
from mellow_chat_runtime.runtime.engine_backed_adapter import _new_trace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["Runtime"])


def _get_runtime_impl() -> str:
    settings = getattr(app_state, "settings", None)
    impl = getattr(settings, "runtime_impl", None)
    if impl in {"engine-backed", "llm-only"}:
        return impl
    return "engine-backed"


def _get_adapter():
    return get_runtime_adapter(impl=_get_runtime_impl(), orchestrator=app_state.orchestrator, llm_service=app_state.llm_service)


def _log_runtime_turn_result(
    *,
    trace_id: str,
    session_id: str | None,
    state_version: int | None,
    model_tier_requested: str | None,
    model_tier_effective: str | None,
    runtime_impl: str,
    success: bool,
    duration_ms: float,
) -> None:
    logger.info(
        "runtime_turn trace_id=%s session_id=%s state_version=%s model_tier_requested=%s model_tier_effective=%s runtime_impl=%s success=%s duration_ms=%.2f",
        trace_id,
        session_id or "missing",
        state_version if state_version is not None else "null",
        model_tier_requested or "null",
        model_tier_effective or "null",
        runtime_impl,
        str(success).lower(),
        duration_ms,
    )


def _log_runtime_error(
    *,
    trace_id: str,
    error_code: str,
    message: str,
    runtime_impl: str,
    path: str,
    status_code: int,
) -> None:
    logger.warning(
        "runtime_error trace_id=%s error_code=%s message=%s runtime_impl=%s path=%s status_code=%s",
        trace_id,
        error_code,
        message,
        runtime_impl,
        path,
        status_code,
    )


def _error_response(status_code: int, code: str, message: str, trace_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorBody(
            error=ErrorDetail(code=code, message=message, trace_id=trace_id)
        ).model_dump(),
    )


def install_runtime_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError):
        trace_id = _new_trace_id()
        runtime_impl = _get_runtime_impl()
        logger.warning("runtime validation failed trace_id=%s errors=%s", trace_id, exc.errors())
        _log_runtime_error(
            trace_id=trace_id,
            error_code="BAD_REQUEST",
            message="Invalid runtime request.",
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=400,
        )
        await app_state.record_runtime_error(
            "BAD_REQUEST: Invalid runtime request.",
            trace_id,
            error_code="BAD_REQUEST",
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=400,
        )
        return _error_response(400, "BAD_REQUEST", "Invalid runtime request.", trace_id)

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException):
        trace_id = _new_trace_id()
        runtime_impl = _get_runtime_impl()
        detail = exc.detail if isinstance(exc.detail, str) else "Runtime request failed."
        _log_runtime_error(
            trace_id=trace_id,
            error_code="HTTP_ERROR",
            message=detail,
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=exc.status_code,
        )
        await app_state.record_runtime_error(
            f"HTTP_ERROR: {detail}",
            trace_id,
            error_code="HTTP_ERROR",
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=exc.status_code,
        )
        return _error_response(exc.status_code, "HTTP_ERROR", detail, trace_id)

    @app.exception_handler(Exception)
    async def _handle_runtime_exception(request: Request, exc: Exception):
        trace_id = _new_trace_id()
        runtime_impl = _get_runtime_impl()
        logger.exception("unhandled runtime exception trace_id=%s", trace_id, exc_info=exc)
        _log_runtime_error(
            trace_id=trace_id,
            error_code="INTERNAL_ERROR",
            message="Internal runtime error.",
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=500,
        )
        await app_state.record_runtime_error(
            "INTERNAL_ERROR: Internal runtime error.",
            trace_id,
            error_code="INTERNAL_ERROR",
            runtime_impl=runtime_impl,
            path=request.url.path,
            status_code=500,
        )
        return _error_response(500, "INTERNAL_ERROR", "Internal runtime error.", trace_id)


@router.post("/turn", response_model=TurnResponse)
async def runtime_turn(req: TurnRequest):
    trace_id = _new_trace_id()
    runtime_impl = _get_runtime_impl()
    adapter = _get_adapter()
    started = time.perf_counter()
    requested_tier = req.context.model_tier_requested if req.context else None
    try:
        response = await adapter.turn(req, trace_id=trace_id)
        duration_ms = (time.perf_counter() - started) * 1000
        _log_runtime_turn_result(
            trace_id=trace_id,
            session_id=req.session_id,
            state_version=response.state.state_version,
            model_tier_requested=requested_tier,
            model_tier_effective=response.state.model_tier_effective,
            runtime_impl=response.meta.runtime_impl,
            success=True,
            duration_ms=duration_ms,
        )
        await schedule_runtime_experience_ledger(req, response)
        return response
    except Exception as e:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.exception("runtime turn failed: %s", e)
        _log_runtime_turn_result(
            trace_id=trace_id,
            session_id=req.session_id,
            state_version=None,
            model_tier_requested=requested_tier,
            model_tier_effective=None,
            runtime_impl=runtime_impl,
            success=False,
            duration_ms=duration_ms,
        )
        _log_runtime_error(
            trace_id=trace_id,
            error_code="SERVICE_UNAVAILABLE",
            message=str(e),
            runtime_impl=runtime_impl,
            path="/runtime/turn",
            status_code=503,
        )
        await app_state.record_runtime_error(
            f"SERVICE_UNAVAILABLE: {str(e)}",
            trace_id,
            error_code="SERVICE_UNAVAILABLE",
            runtime_impl=runtime_impl,
            path="/runtime/turn",
            status_code=503,
        )
        return _error_response(503, "SERVICE_UNAVAILABLE", str(e), trace_id)


@router.get("/status", response_model=StatusResponse)
async def runtime_status():
    adapter = _get_adapter()
    return await adapter.status()
