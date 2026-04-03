from mellow_link import app_state
from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
from mellow_link.modules.rebuild_assistant import runner as rebuild_runner
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

from .refactoring_support_test_utils import build_safe_bundle


def test_rebuild_assistant_result_contains_authoritative_blocks():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        repo.save(order)
        return approve(order)
                """,
            },
            {"name": "order_page.html", "content": '<button onclick="submitOrder()">submit</button>'},
        ]
    )
    service = RebuildAssistantService()
    result = service.build_result(service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[]))

    assert set(result.structure_snapshot.keys()) >= {"feature_slices", "components", "dependencies", "hotspots", "layer_map"}
    assert set(result.diagnosis_report.keys()) >= {"issues", "coverage_summary", "detector_stats"}
    assert set(result.decision_summary.keys()) >= {"decisions", "recommended_strategy", "priority_queue"}
    assert set(result.improvement_plan_bundle.keys()) >= {"design_options", "recommended_option", "execution_stages", "risk_checkpoints"}
    assert "evidence_index" in result.appendix
    assert result.decision_summary["decisions"][0]["score_breakdown"]["final_score"] == result.decision_summary["decisions"][0]["priority_score"]


def test_rebuild_assistant_runner_emits_authoritative_payload(monkeypatch):
    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {"rebuild-temp": "<% String sql = \"SELECT * FROM orders\"; %>"}, raising=False)

    getattr(rebuild_compat, "start_rebuild_assistant_run_compat")(
        run_id="run_rebuild_authoritative",
        session_id="session-test",
        goal="이 JSP 주문 조회 화면을 React + REST API로 재구성해줘",
        assets=rebuild_compat.RebuildAssetsPayload(
            source_code="<% String sql = \"SELECT * FROM orders\"; %>",
            sql_queries="SELECT * FROM orders WHERE status = 'READY'",
        ),
        constraints=["기존 DB 호환 유지"],
        temp_session_id="rebuild-temp",
    )

    finished = [event for event in events if event["type"] == "run_finished"]
    assert len(finished) == 1
    payload = finished[0]["payload"]
    assert set(payload["authoritative_payload"].keys()) == {
        "structure_snapshot",
        "diagnosis_report",
        "decision_summary",
        "improvement_plan_bundle",
        "appendix",
    }


def test_rebuild_assistant_softens_supporting_result_sentences():
    bundle = build_safe_bundle(
        [
            {
                "name": "order_service.py",
                "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY":
            repo.save(order)
            return approve(order)
                """,
            },
            {"name": "order_page.html", "content": '<button onclick="submitOrder()">submit</button>'},
        ]
    )
    service = RebuildAssistantService()
    result = service.build_result(service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[]))

    assert result.primary_judgment_reason
    assert "확정" not in " ".join(result.executive_summary_v2[1:]) if len(result.executive_summary_v2) > 1 else True
    assert result.recommended_option is None or ("적절" in result.recommended_option.selection_reason or "안전" in result.recommended_option.selection_reason)
