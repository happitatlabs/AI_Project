from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mellow_chat_runtime.routers import runtime as runtime_router
from mellow_chat_runtime.runtime.schemas import StatusHealth, StatusResponse, StatusRuntime, TurnMeta, TurnPayload, TurnResponse, TurnState


class _SuccessAdapter:
    async def turn(self, req, trace_id=None):
        return TurnResponse(
            turn=TurnPayload(
                id="turn_test_001",
                speech=f"echo:{req.input.text}",
                passage="passage",
                ooc=None,
                clarify=None,
            ),
            state=TurnState(
                session_id=req.session_id,
                state_version=1,
                system_state="IDLE",
                model_tier_effective="free",
            ),
            meta=TurnMeta(
                trace_id=trace_id or "missing",
                runtime_impl="engine-backed",
                latency_ms=1.23,
            ),
        )

    async def status(self):
        return StatusResponse(
            runtime=StatusRuntime(impl="engine-backed", version="0.1", uptime_sec=5.0),
            health=StatusHealth(system_state="IDLE", last_error=None, degraded=False),
        )


class _FailingAdapter:
    async def turn(self, req, trace_id=None):
        raise RuntimeError("adapter unavailable")

    async def status(self):
        return StatusResponse(
            runtime=StatusRuntime(impl="engine-backed", version="0.1", uptime_sec=0.0),
            health=StatusHealth(system_state="IDLE", last_error=None, degraded=False),
        )


def _make_client(monkeypatch, adapter):
    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    monkeypatch.setattr(runtime_router, "_get_adapter", lambda: adapter)
    return TestClient(app)


def test_runtime_turn_success_contract(monkeypatch):
    client = _make_client(monkeypatch, _SuccessAdapter())

    res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_001",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
            "context": {
                "character_id": "default",
                "model_tier_requested": "free",
                "client_turn_id": "web_1",
            },
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["turn"]["speech"] == "echo:hello"
    assert body["turn"]["passage"] == "passage"
    assert "ooc" in body["turn"]
    assert "clarify" in body["turn"]
    assert body["turn"]["ooc"] is None
    assert body["turn"]["clarify"] is None
    assert body["state"]["session_id"] == "sess_001"
    assert body["state"]["state_version"] == 1
    assert body["state"]["model_tier_effective"] == "free"
    assert body["meta"]["runtime_impl"] == "engine-backed"
    assert re.match(r"^trc_\d{8}_[0-9a-f]{8}$", body["meta"]["trace_id"])


def test_runtime_turn_validation_error_uses_common_error_body(monkeypatch):
    client = _make_client(monkeypatch, _SuccessAdapter())

    res = client.post(
        "/runtime/turn",
        json={
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )

    assert res.status_code == 400, res.text
    body = res.json()
    assert body["error"]["code"] == "BAD_REQUEST"
    assert body["error"]["message"] == "Invalid runtime request."
    assert re.match(r"^trc_\d{8}_[0-9a-f]{8}$", body["error"]["trace_id"])


def test_runtime_turn_failure_includes_trace_id(monkeypatch):
    client = _make_client(monkeypatch, _FailingAdapter())

    res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_001",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )

    assert res.status_code == 503, res.text
    body = res.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["message"] == "adapter unavailable"
    assert re.match(r"^trc_\d{8}_[0-9a-f]{8}$", body["error"]["trace_id"])


def test_runtime_turn_blank_input_uses_common_error_body(monkeypatch):
    client = _make_client(monkeypatch, _SuccessAdapter())

    res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_blank",
            "user": {"id": "user_001"},
            "input": {"text": "   "},
        },
    )

    assert res.status_code == 400, res.text
    body = res.json()
    assert body["error"]["code"] == "BAD_REQUEST"
    assert body["error"]["message"] == "Invalid runtime request."
    assert re.match(r"^trc_\d{8}_[0-9a-f]{8}$", body["error"]["trace_id"])


def test_runtime_turn_long_input_succeeds_with_trace_id(monkeypatch):
    client = _make_client(monkeypatch, _SuccessAdapter())
    long_text = "x" * 20000

    res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_long",
            "user": {"id": "user_001"},
            "input": {"text": long_text},
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["turn"]["speech"] == f"echo:{long_text}"
    assert re.match(r"^trc_\d{8}_[0-9a-f]{8}$", body["meta"]["trace_id"])
