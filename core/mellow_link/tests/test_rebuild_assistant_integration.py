import json
from types import SimpleNamespace

from mellow_link import app_state
from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
from mellow_link.modules.rebuild_assistant import runner as rebuild_runner
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)

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
    assert result.template_judgment == result.primary_judgment
    assert result.structural_judgment in {"refactor", "redesign", "migration_consideration", "observation_only"}
    assert result.narrative_axis == result.extensions["narrative"]["axis"]
    assert result.feature_signal_mode
    assert set(result.decision_summary["decisions"][0]["explainability"].keys()) >= {
        "decision_rule",
        "score_formula",
        "score_summary",
        "evidence_count",
        "affected_slice_count",
    }
    assert result.extensions["narrative"]["source"] == "deterministic_fallback"
    assert result.extensions["narrative"]["axis"]


def test_rebuild_assistant_narrative_augmentation_rewrites_only_allowed_top_fields():
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
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    result = service.build_result(prepared)
    authoritative_before = {
        "structure_snapshot": result.structure_snapshot,
        "diagnosis_report": result.diagnosis_report,
        "decision_summary": result.decision_summary,
        "improvement_plan_bundle": result.improvement_plan_bundle,
        "appendix": result.appendix,
    }

    class FakeLLM:
        def get_model_for_mode(self, mode):
            return "qwen3.5:9b"

        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": "주문 처리 구조와 책임 경계를 설명하기 위한 보고서입니다.",
                        "primary_judgment_reason": "상위 구조 이슈를 기준으로 우선 분리 방향을 설명합니다.",
                        "one_line_conclusion": "주문 처리 기능은 책임 경계를 분리하는 편이 적절합니다.",
                        "executive_summary_v2": [
                            "주문 처리 기능은 구조적 책임을 먼저 정리하는 편이 적절합니다.",
                            "상위 decision과 evidence를 기준으로 설명을 단순화했습니다.",
                        ],
                    },
                    ensure_ascii=False,
                ),
                model="qwen3.5:9b",
            )

    augmented = NarrativeAugmentationService().augment_sync(
        prepared=prepared,
        result=result,
        llm_service=FakeLLM(),
    )

    assert augmented.report_purpose == "주문 처리 구조와 책임 경계를 설명하기 위한 보고서입니다."
    assert augmented.one_line_conclusion == "주문 처리 기능은 책임 경계를 분리하는 편이 적절합니다."
    assert augmented.extensions["narrative"]["source"] == "ai"
    assert augmented.extensions["narrative"]["axis"] == result.narrative_axis
    assert set(augmented.extensions["narrative"]["fields_rewritten"]) == {
        "report_purpose",
        "primary_judgment_reason",
        "one_line_conclusion",
        "executive_summary_v2",
    }
    assert augmented.structure_snapshot == authoritative_before["structure_snapshot"]
    assert augmented.diagnosis_report == authoritative_before["diagnosis_report"]
    assert augmented.decision_summary == authoritative_before["decision_summary"]
    assert augmented.improvement_plan_bundle == authoritative_before["improvement_plan_bundle"]
    assert augmented.appendix == authoritative_before["appendix"]
    assert augmented.recommended_option == result.recommended_option


def test_rebuild_assistant_narrative_augmentation_invalid_output_falls_back():
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
            }
        ]
    )
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order creation flow", safe_bundle=bundle, constraints=[])
    result = service.build_result(prepared)

    class BadLLM:
        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": "새로운 9999점 위험을 설명하는 보고서입니다.",
                        "unexpected_field": "should fail",
                    },
                    ensure_ascii=False,
                ),
                model="qwen3.5:9b",
            )

    augmented = NarrativeAugmentationService().augment_sync(
        prepared=prepared,
        result=result,
        llm_service=BadLLM(),
    )

    assert augmented.report_purpose == result.report_purpose
    assert augmented.one_line_conclusion == result.one_line_conclusion
    assert augmented.extensions["narrative"]["source"] == "deterministic_fallback"
    assert augmented.extensions["narrative"]["axis"] == result.narrative_axis
    assert augmented.extensions["narrative"]["validation_passed"] is False
    assert augmented.extensions["narrative"]["failure_reason"]


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


def test_rebuild_assistant_runner_applies_ai_narrative_only_to_top_fields(monkeypatch):
    events = []

    class InlineThread:
        def __init__(self, target=None, daemon=None, *args, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    class FakeLLM:
        def get_model_for_mode(self, mode):
            return "qwen3.5:9b"

        async def generate(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "report_purpose": "주문 조회 구조와 책임 경계를 설명하기 위한 보고서입니다.",
                        "primary_judgment_reason": "상위 이슈와 evidence를 기준으로 사용자 설명을 단순화했습니다.",
                        "one_line_conclusion": "주문 조회 기능은 조회 책임을 분리하는 편이 적절합니다.",
                        "executive_summary_v2": [
                            "주문 조회 기능은 조회 책임과 데이터 접근 경계를 먼저 정리하는 편이 적절합니다.",
                            "deterministic decision과 evidence를 그대로 유지한 채 설명만 재작성했습니다.",
                        ],
                    },
                    ensure_ascii=False,
                ),
                model="qwen3.5:9b",
            )

    def fake_emit(run_id_arg, event_type, payload, **kwargs):
        events.append({"run_id": run_id_arg, "type": event_type, "payload": payload})

    monkeypatch.setattr(rebuild_runner.threading, "Thread", InlineThread)
    monkeypatch.setattr(rebuild_runner, "emit_event", fake_emit)
    monkeypatch.setattr(app_state, "llm_service", FakeLLM(), raising=False)
    monkeypatch.setattr(app_state, "TEMP_CONTEXT_STORE", {"rebuild-temp": "<% String sql = \"SELECT * FROM orders\"; %>"}, raising=False)

    getattr(rebuild_compat, "start_rebuild_assistant_run_compat")(
        run_id="run_rebuild_ai_narrative",
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
    structured = payload["structured_result"]
    assert structured["extensions"]["narrative"]["source"] == "ai"
    assert structured["extensions"]["narrative"]["axis"] == structured["narrative_axis"]
    assert structured["report_purpose"] == "주문 조회 구조와 책임 경계를 설명하기 위한 보고서입니다."
    assert structured["structure_snapshot"] == payload["authoritative_payload"]["structure_snapshot"]
    assert structured["diagnosis_report"] == payload["authoritative_payload"]["diagnosis_report"]
    assert structured["decision_summary"] == payload["authoritative_payload"]["decision_summary"]
    assert structured["improvement_plan_bundle"] == payload["authoritative_payload"]["improvement_plan_bundle"]
    assert structured["appendix"] == payload["authoritative_payload"]["appendix"]


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
