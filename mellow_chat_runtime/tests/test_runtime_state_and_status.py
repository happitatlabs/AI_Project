from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mellow_chat_runtime import app_state
from mellow_chat_runtime.runtime.engine_backed_adapter import EngineBackedAdapter
from mellow_chat_runtime.runtime.llm_only import LLMOnlyAdapter
from mellow_chat_runtime.runtime.schemas import TurnRequest, TurnRequestContext, TurnRequestInput, TurnRequestUser


class _FakeLLM:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt: str, mode: str):
        self.calls.append({"prompt": prompt, "mode": mode})
        return SimpleNamespace(content=f"reply:{mode}:{prompt}")


class _FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def run_agent(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(answer="engine-reply")

    def get_state(self):
        return SimpleNamespace(value="IDLE")


class _FakeLedgerDb:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def record_ledger_entry(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FailingLedgerDb:
    def record_ledger_entry(self, **kwargs):
        raise RuntimeError("ledger unavailable")


def test_state_version_increments_only_on_success_per_session():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        llm = _FakeLLM()
        adapter = LLMOnlyAdapter(llm_service=llm)
        req = TurnRequest(session_id="sess_a", user=TurnRequestUser(id="u1"), input=TurnRequestInput(text="hello"))

        first = await adapter.turn(req, trace_id="trc_one")
        second = await adapter.turn(req, trace_id="trc_two")
        third = await adapter.turn(
            TurnRequest(session_id="sess_b", user=TurnRequestUser(id="u1"), input=TurnRequestInput(text="hello")),
            trace_id="trc_three",
        )
        return first, second, third

    first, second, third = asyncio.run(run())
    assert first.state.state_version == 1
    assert second.state.state_version == 2
    assert third.state.state_version == 1


def test_model_tier_effective_pro_uses_thinking_mode():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        llm = _FakeLLM()
        adapter = LLMOnlyAdapter(llm_service=llm)
        req = TurnRequest(
            session_id="sess_pro",
            user=TurnRequestUser(id="u1"),
            input=TurnRequestInput(text="hello"),
            context=TurnRequestContext(model_tier_requested="pro"),
        )
        resp = await adapter.turn(req, trace_id="trc_pro")
        return resp, llm.calls

    resp, calls = asyncio.run(run())
    assert resp.state.model_tier_effective == "pro"
    assert calls[-1]["mode"] == "thinking"


def test_model_tier_effective_auto_falls_back_to_free():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        orch = _FakeOrchestrator()
        adapter = EngineBackedAdapter(orchestrator=orch)
        req = TurnRequest(
            session_id="sess_auto",
            user=TurnRequestUser(id="u1"),
            input=TurnRequestInput(text="hello"),
            context=TurnRequestContext(model_tier_requested="auto"),
        )
        resp = await adapter.turn(req, trace_id="trc_auto")
        return resp, orch.calls

    resp, calls = asyncio.run(run())
    assert resp.state.model_tier_effective == "free"
    assert calls[-1]["mode"] == "fast"


def test_runtime_status_returns_minimum_operational_fields():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        adapter = LLMOnlyAdapter(llm_service=None)
        await app_state.record_runtime_error("SERVICE_UNAVAILABLE: adapter unavailable", "trc_20260318_deadbeef")
        return await adapter.status()

    status = asyncio.run(run())
    dumped = status.model_dump()
    assert dumped["runtime"]["impl"] == "llm-only"
    assert "uptime_sec" in dumped["runtime"]
    assert dumped["health"]["system_state"] == "IDLE"
    assert dumped["health"]["degraded"] is True
    assert re.match(r"^SERVICE_UNAVAILABLE: adapter unavailable \(trace_id=trc_\d{8}_[0-9a-f]{8}\)$", dumped["health"]["last_error"])


class _FailOnceLLM:
    def __init__(self):
        self.calls = 0

    async def generate(self, prompt: str, mode: str):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return SimpleNamespace(content=f"reply:{mode}:{prompt}")


def test_state_version_does_not_increment_when_turn_fails():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        llm = _FailOnceLLM()
        adapter = LLMOnlyAdapter(llm_service=llm)
        req = TurnRequest(session_id="sess_fail", user=TurnRequestUser(id="u1"), input=TurnRequestInput(text="hello"))

        try:
            await adapter.turn(req, trace_id="trc_fail")
        except RuntimeError:
            pass
        success = await adapter.turn(req, trace_id="trc_success")
        return success

    success = asyncio.run(run())
    assert success.state.state_version == 1


def test_state_version_remains_unique_under_consecutive_calls():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        llm = _FakeLLM()
        adapter = LLMOnlyAdapter(llm_service=llm)
        req = TurnRequest(session_id="sess_concurrent", user=TurnRequestUser(id="u1"), input=TurnRequestInput(text="hello"))
        results = await asyncio.gather(*[adapter.turn(req, trace_id=f"trc_{index}") for index in range(5)])
        return [resp.state.state_version for resp in results]

    versions = asyncio.run(run())
    assert sorted(versions) == [1, 2, 3, 4, 5]
    assert len(set(versions)) == 5


def test_runtime_status_recovers_from_degraded_after_success():
    async def run():
        await app_state.reset_runtime_state_for_tests()
        adapter = LLMOnlyAdapter(llm_service=_FakeLLM())
        await app_state.record_runtime_error("SERVICE_UNAVAILABLE: adapter unavailable", "trc_20260318_deadbeef")
        degraded = await adapter.status()
        req = TurnRequest(session_id="sess_recover", user=TurnRequestUser(id="u1"), input=TurnRequestInput(text="hello"))
        await adapter.turn(req, trace_id="trc_recover")
        recovered = await adapter.status()
        return degraded, recovered

    degraded, recovered = asyncio.run(run())
    assert degraded.health.degraded is True
    assert degraded.health.last_error is not None
    assert recovered.health.degraded is False
    assert recovered.health.last_error is None


def test_runtime_impl_switch_changes_turn_and_status_behavior(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    llm_turn = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_llm",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )
    llm_status = client.get("/runtime/status")

    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="engine-backed"))
    engine_turn = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_engine",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )
    engine_status = client.get("/runtime/status")

    assert llm_turn.status_code == 200, llm_turn.text
    assert llm_turn.json()["meta"]["runtime_impl"] == "llm-only"
    assert llm_status.status_code == 200, llm_status.text
    assert llm_status.json()["runtime"]["impl"] == "llm-only"

    assert engine_turn.status_code == 200, engine_turn.text
    assert engine_turn.json()["meta"]["runtime_impl"] == "engine-backed"
    assert engine_turn.json()["turn"]["speech"] == "engine-reply"
    assert engine_status.status_code == 200, engine_status.text
    assert engine_status.json()["runtime"]["impl"] == "engine-backed"


def test_runtime_status_degraded_after_api_failure_and_clears_on_success(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "orchestrator", None)
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="engine-backed"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    fail_res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_fail_status",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )
    degraded_status = client.get("/runtime/status")

    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))
    success_res = client.post(
        "/runtime/turn",
        json={
            "session_id": "sess_ok_status",
            "user": {"id": "user_001"},
            "input": {"text": "hello"},
        },
    )
    recovered_status = client.get("/runtime/status")

    assert fail_res.status_code == 503, fail_res.text
    assert fail_res.json()["error"]["trace_id"]
    assert degraded_status.status_code == 200, degraded_status.text
    assert degraded_status.json()["health"]["degraded"] is True
    assert "trace_id=" in degraded_status.json()["health"]["last_error"]

    assert success_res.status_code == 200, success_res.text
    assert success_res.json()["meta"]["runtime_impl"] == "llm-only"
    assert recovered_status.status_code == 200, recovered_status.text
    assert recovered_status.json()["health"]["degraded"] is False
    assert recovered_status.json()["health"]["last_error"] is None



def test_runtime_turn_logs_minimum_operational_fields(monkeypatch, caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with caplog.at_level(logging.INFO):
        res = client.post(
            "/runtime/turn",
            json={
                "session_id": "sess_log_turn",
                "user": {"id": "user_001"},
                "input": {"text": "hello"},
                "context": {"model_tier_requested": "pro"},
            },
        )

    assert res.status_code == 200, res.text
    log_text = caplog.text
    assert "runtime_turn trace_id=trc_" in log_text
    assert "session_id=sess_log_turn" in log_text
    assert "state_version=1" in log_text
    assert "model_tier_requested=pro" in log_text
    assert "model_tier_effective=pro" in log_text
    assert "runtime_impl=llm-only" in log_text
    assert "success=true" in log_text
    assert "duration_ms=" in log_text


def test_runtime_error_and_degraded_transition_logs(monkeypatch, caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "orchestrator", None)
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="engine-backed"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with caplog.at_level(logging.INFO):
        fail_res = client.post(
            "/runtime/turn",
            json={
                "session_id": "sess_log_fail",
                "user": {"id": "user_001"},
                "input": {"text": "hello"},
            },
        )
        monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))
        success_res = client.post(
            "/runtime/turn",
            json={
                "session_id": "sess_log_recover",
                "user": {"id": "user_001"},
                "input": {"text": "hello"},
            },
        )

    assert fail_res.status_code == 503, fail_res.text
    assert success_res.status_code == 200, success_res.text
    log_text = caplog.text
    assert "runtime_error trace_id=trc_" in log_text
    assert "error_code=SERVICE_UNAVAILABLE" in log_text
    assert "message=orchestrator unavailable" in log_text
    assert "runtime_impl=engine-backed" in log_text
    assert "path=/runtime/turn" in log_text
    assert "status_code=503" in log_text
    assert "runtime_status_transition degraded=true error_code=SERVICE_UNAVAILABLE" in log_text
    assert "runtime_status_transition degraded=false runtime_impl=llm-only" in log_text



def test_runtime_success_schedules_memory_ledger_bridge(monkeypatch):
    import unittest.mock as mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    ledger_db = _FakeLedgerDb(result=True)
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with mock.patch("mellow_link.infra.memory_database.get_memory_db", return_value=ledger_db):
        res = client.post(
            "/runtime/turn",
            json={
                "session_id": "sess_bridge_ok",
                "user": {"id": "user_001"},
                "input": {"text": "hello runtime bridge"},
            },
        )
        asyncio.run(app_state.drain_runtime_background_tasks())

    assert res.status_code == 200, res.text
    assert len(ledger_db.calls) == 1
    call = ledger_db.calls[0]
    assert call["is_success"] == 1
    assert call["used_tools"] == []
    assert call["error_message"] is None
    assert call["intent_type"] == "hello runtime bridge"


def test_runtime_memory_ledger_failure_does_not_pollute_status(monkeypatch):
    import unittest.mock as mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with mock.patch("mellow_link.infra.memory_database.get_memory_db", return_value=_FailingLedgerDb()):
        res = client.post(
            "/runtime/turn",
            json={
                "session_id": "sess_bridge_fail",
                "user": {"id": "user_001"},
                "input": {"text": "hello"},
            },
        )
        asyncio.run(app_state.drain_runtime_background_tasks())
        status = client.get("/runtime/status")

    assert res.status_code == 200, res.text
    assert status.status_code == 200, status.text
    assert status.json()["health"]["degraded"] is False
    assert status.json()["health"]["last_error"] is None


def test_runtime_memory_ledger_logs_success(monkeypatch, caplog):
    import unittest.mock as mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    ledger_db = _FakeLedgerDb(result=True)
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with mock.patch("mellow_link.infra.memory_database.get_memory_db", return_value=ledger_db):
        with caplog.at_level(logging.INFO):
            res = client.post(
                "/runtime/turn",
                json={
                    "session_id": "sess_bridge_log_ok",
                    "user": {"id": "user_001"},
                    "input": {"text": "hello"},
                },
            )
            asyncio.run(app_state.drain_runtime_background_tasks())

    assert res.status_code == 200, res.text
    assert "runtime_memory_bridge_scheduled trace_id=trc_" in caplog.text
    assert "runtime_memory_ledger_recorded trace_id=trc_" in caplog.text


def test_runtime_memory_ledger_logs_failure_without_runtime_error(monkeypatch, caplog):
    import unittest.mock as mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mellow_chat_runtime.routers import runtime as runtime_router

    asyncio.run(app_state.reset_runtime_state_for_tests())
    monkeypatch.setattr(app_state, "llm_service", _FakeLLM())
    monkeypatch.setattr(app_state, "orchestrator", _FakeOrchestrator())
    monkeypatch.setattr(app_state, "settings", SimpleNamespace(runtime_impl="llm-only"))

    app = FastAPI()
    runtime_router.install_runtime_exception_handlers(app)
    app.include_router(runtime_router.router)
    client = TestClient(app)

    with mock.patch("mellow_link.infra.memory_database.get_memory_db", return_value=_FailingLedgerDb()):
        with caplog.at_level(logging.INFO):
            res = client.post(
                "/runtime/turn",
                json={
                    "session_id": "sess_bridge_log_fail",
                    "user": {"id": "user_001"},
                    "input": {"text": "hello"},
                },
            )
            asyncio.run(app_state.drain_runtime_background_tasks())

    assert res.status_code == 200, res.text
    assert "runtime_memory_bridge_scheduled trace_id=trc_" in caplog.text
    assert "runtime_memory_ledger_failed trace_id=trc_" in caplog.text
    assert "runtime_error trace_id=" not in caplog.text
