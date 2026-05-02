import json
from types import SimpleNamespace

from mellow_link import app_state
from mellow_link.modules.rebuild_assistant import compat as rebuild_compat
from mellow_link.modules.rebuild_assistant import runner as rebuild_runner
from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)
from mellow_link.services.refactoring_support_engine.schemas import FeatureSignals, PreparedRebuildInput
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer
from mellow_link.services.refactoring_support_engine.template_support import TemplateSupport

from .refactoring_support_test_utils import build_safe_bundle


def _build_validation_bundle_result(*, grounded: bool = False):
    service = RebuildAssistantService()
    if grounded:
        prepared = service.prepare_input(
            goal="modernize order flow",
            assets=RebuildAssetsPayload(
                source_code="""
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY" and order.amount > 1000:
            repo.save(order)
            return approve(order)
                """,
                ui_template='<button onclick="submitOrder()">submit</button>',
                sql_queries="SELECT * FROM orders WHERE status = ? AND amount > ? ORDER BY created_at DESC",
                database_schema="CREATE TABLE orders (id bigint primary key, status varchar(20), amount numeric(12,2));",
                framework_info="JSP + Spring MVC + MyBatis",
            ),
            constraints=[],
        )
    else:
        prepared = service.prepare_safe_bundle_input(
            goal="modernize order flow",
            safe_bundle=build_safe_bundle(
                [
                    {
                        "name": "order_service.py",
                        "content": """
class OrderService:
    def submit(self, order, repo):
        if not order.amount:
            raise ValueError("required")
        if order.status == "READY" and order.amount > 1000:
            repo.save(order)
            return approve(order)
                        """,
                    },
                    {"name": "order_page.jsp", "content": '<button onclick="submitOrder()">submit</button>'},
                    {"name": "order_query.sql", "content": "SELECT * FROM orders WHERE status = 'READY' AND amount > 1000"},
                ]
            ),
            constraints=[],
        )
    return service.build_result(prepared)


def test_rebuild_assistant_safe_bundle_readme_only_keeps_source_and_framework_missing_context():
    bundle = build_safe_bundle(
        [
            {
                "name": "README.md",
                "content": """
# Order Flow
이 문서는 주문 승인 흐름과 저장 검증 규칙을 설명합니다.
                """,
            }
        ]
    )
    service = RebuildAssistantService()

    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])

    assert "레거시 화면 또는 서버 코드" in prepared.missing_context
    assert "기존 프레임워크/런타임 정보" in prepared.missing_context
    assert prepared.asset_presence.has_source_code is False
    assert prepared.asset_presence.has_framework_hint is False
    assert prepared.assets.source_code == ""
    assert prepared.assets.framework_info == ""
    assert prepared.supporting_docs


def test_rebuild_assistant_safe_bundle_ddl_dump_marks_schema_asset():
    bundle = build_safe_bundle(
        [
            {
                "name": "orders_tables.sql",
                "content": """
CREATE TABLE orders (
    id bigint primary key,
    status varchar(20)
);
ALTER TABLE orders
    ADD CONSTRAINT fk_orders_customer FOREIGN KEY (id) REFERENCES customers(id);
                """,
            }
        ]
    )
    service = RebuildAssistantService()

    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])

    assert prepared.asset_presence.has_schema_asset is True
    assert "orders_tables.sql" in prepared.asset_presence.schema_asset_names
    assert prepared.assets.database_schema.startswith("[SAFE SOURCE:")
    assert prepared.assets.sql_queries == ""
    assert "DB 스키마" not in prepared.missing_context
    assert "핵심 SQL" in prepared.missing_context


def test_rebuild_assistant_safe_bundle_scenario_only_keeps_missing_context_and_intent_separate():
    bundle = build_safe_bundle(
        [
            {
                "name": "scenario.md",
                "content": """
# 업무 시나리오
승인 화면과 저장 흐름을 나중에 React와 API로 나누고 싶다.
                """,
            }
        ]
    )
    service = RebuildAssistantService()

    prepared = service.prepare_safe_bundle_input(goal="", safe_bundle=bundle, constraints=[])
    analysis_input = InputAssembler().assemble(prepared)

    assert prepared.intent.goal == ""
    assert prepared.intent.scenario.startswith("# 업무 시나리오")
    assert prepared.assets.source_code == ""
    assert prepared.assets.framework_info == ""
    assert prepared.supporting_docs == ""
    assert prepared.asset_presence.doc_asset_names == []
    assert analysis_input.asset_inventory == []
    assert analysis_input.source_blocks == []
    assert "레거시 화면 또는 서버 코드" in prepared.missing_context
    assert "기존 프레임워크/런타임 정보" in prepared.missing_context


def test_rebuild_assistant_goal_only_keeps_analysis_possible_but_low_confidence():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="reports CRUD 구조를 점검하고 전환 초안을 작성하라.",
        assets=RebuildAssetsPayload(),
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)

    assert diagnosis.analysis_summary
    assert service.estimate_confidence(prepared) < 0.2
    assert "레거시 화면 또는 서버 코드" in prepared.missing_context
    assert "기존 프레임워크/런타임 정보" in prepared.missing_context
    assert not diagnosis.grounded_business_rules or all(
        rule.confidence != "확정" and rule.needs_verification for rule in diagnosis.grounded_business_rules
    )


def test_rebuild_assistant_constraints_only_do_not_become_rule_evidence():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="",
        assets=RebuildAssetsPayload(),
        constraints=[
            "VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.",
            "VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.",
        ],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)

    assert prepared.intent.constraints == ["VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다."]
    assert diagnosis.core_business_rules == []
    assert not diagnosis.grounded_business_rules or all(not rule.evidence for rule in diagnosis.grounded_business_rules)
    assert "레거시 화면 또는 서버 코드" in prepared.missing_context


def test_rebuild_assistant_intent_inputs_do_not_change_structure_snapshot():
    base_assets = [
        {
            "name": "order_service.py",
            "content": """
class OrderService:
    def submit(self, order, repo):
        if order.status == "READY":
            repo.save(order)
        return order
            """,
        },
        {
            "name": "order_page.html",
            "content": '<button onclick="submitOrder()">submit</button>',
        },
    ]
    bundle_without_intent = build_safe_bundle(base_assets)
    bundle_with_intent = build_safe_bundle(
        base_assets
        + [
            {"name": "goal.txt", "content": "주문 저장 흐름을 점검한다."},
            {"name": "constraints.txt", "content": "기존 DB 계약 유지\n기존 DB 계약 유지"},
            {"name": "scenario.md", "content": "업무 시나리오: 승인 이후 저장 흐름을 설명한다."},
        ]
    )
    service = RebuildAssistantService()

    prepared_without_intent = service.prepare_safe_bundle_input(
        goal="legacy order flow",
        safe_bundle=bundle_without_intent,
        constraints=["keep db contract"],
    )
    prepared_with_intent = service.prepare_safe_bundle_input(
        goal="",
        safe_bundle=bundle_with_intent,
        constraints=[],
    )
    assembled_with_intent = InputAssembler().assemble(prepared_with_intent)
    structure_without_intent = StructureAnalyzer().analyze(InputAssembler().assemble(prepared_without_intent))
    structure_with_intent = StructureAnalyzer().analyze(assembled_with_intent)
    diagnosis_without_intent = DiagnosisEngine().run(prepared_without_intent, structure_without_intent, service)
    diagnosis_with_intent = DiagnosisEngine().run(prepared_with_intent, structure_with_intent, service)

    assert prepared_with_intent.intent.goal == "주문 저장 흐름을 점검한다."
    assert prepared_with_intent.intent.constraints == ["기존 DB 계약 유지"]
    assert prepared_with_intent.intent.scenario == "업무 시나리오: 승인 이후 저장 흐름을 설명한다."
    assert [item.name for item in assembled_with_intent.asset_inventory] == ["order_service.py", "order_page.html"]
    assert [item.asset_name for item in assembled_with_intent.source_blocks] == ["order_service.py", "order_page.html"]
    assert structure_without_intent.structure_snapshot.model_dump() == structure_with_intent.structure_snapshot.model_dump()
    assert diagnosis_without_intent.diagnosis_report.model_dump() == diagnosis_with_intent.diagnosis_report.model_dump()


def test_rebuild_assistant_strong_scenario_keeps_recommendation_as_insufficient_grounding():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="",
        assets=RebuildAssetsPayload(),
        constraints=[],
        temp_context="반드시 React와 Spring Boot로 전면 전환해야 하고 승인 구조도 새로 설계해야 한다.",
    )

    result = service.build_result(prepared)
    grounding = result.extensions["decision_governance"]["recommendation_grounding"]

    assert grounding["insufficient_grounding"] is True
    assert grounding["level"] == "insufficient"
    assert result.recommended_option is None
    assert result.confidence == 0.0
    assert "구조 근거가 부족" in result.one_line_conclusion
    assert [line.split(":", 1)[0] for line in result.executive_summary_v2[:4]] == ["문제", "영향", "조치", "다음 단계"]
    assert "검토용 초안" in result.executive_summary_v2[2]


def test_rebuild_assistant_explicit_goal_is_preserved_as_canonical_request_context():
    service = RebuildAssistantService()
    goal = "이 SQL/프로시저가 실제로 어떤 처리 흐름과 계산 규칙으로 동작하는지 분석해줘."
    bundle = build_safe_bundle(
        [
            {
                "name": "fx_fifo_proc.sql",
                "content": """
CREATE OR REPLACE PROCEDURE p_fx_fifo IS
BEGIN
    INSERT INTO tn_forout_hist(amount_krw)
    SELECT SUM(out_amt0) FROM tn_forins WHERE status_cd = 'READY';
END;
                """,
            },
            {
                "name": "fx_fifo_tables.sql",
                "content": """
CREATE TABLE tn_forins (
    txn_no varchar(30),
    in_amt numeric(18,2),
    out_amt0 numeric(18,2),
    status_cd varchar(20)
);
                """,
            },
        ]
    )

    prepared = service.prepare_safe_bundle_input(goal=goal, safe_bundle=bundle, constraints=[])
    result = service.build_result(prepared)

    assert prepared.goal == goal
    assert result.canonical_payload is not None
    assert result.canonical_payload.request_context.goal == goal
    assert result.canonical_payload.request_context.question_axis == "processing_flow"
    assert result.question_axis == "processing_flow"
    assert result.family_classification.family == "operational_source"
    assert "보고서" in result.report_purpose
    assert "1차 목적은 현행 운영 로직과 처리 흐름" in result.one_line_conclusion
    assert result.extensions["decision_governance"]["document_outline"]["next_step"]


def test_rebuild_assistant_constraints_affect_recommendation_filter_metadata_only():
    bundle = build_safe_bundle(
        [
            {
                "name": "legacy_order_page.jsp",
                "content": """
<% String sql = "SELECT * FROM orders WHERE status = 'READY'"; %>
<button onclick="submitOrder()">submit</button>
                """,
            },
            {
                "name": "order_service.py",
                "content": """
# migration target: react + spring boot
class OrderService:
    def submit(self, order):
        if order.status == "READY" and order.amount > 1000:
            return repo.save(order)
                """,
            },
            {
                "name": "approval_service.py",
                "content": """
class ApprovalService:
    def approve(self, order):
        if order.status == "READY" and order.amount > 1000:
            return repo.save(order)
                """,
            },
        ]
    )
    service = RebuildAssistantService()

    result_without_constraint = service.build_result(
        service.prepare_safe_bundle_input(
            goal="legacy order approval flow migration plan",
            safe_bundle=bundle,
            constraints=[],
        )
    )
    result_with_constraint = service.build_result(
        service.prepare_safe_bundle_input(
            goal="legacy order approval flow migration plan",
            safe_bundle=bundle,
            constraints=["마이그레이션은 이번 범위에서 제외"],
        )
    )

    assert result_without_constraint.structure_snapshot == result_with_constraint.structure_snapshot
    assert result_without_constraint.diagnosis_report == result_with_constraint.diagnosis_report
    assert result_without_constraint.extensions["decision_governance"]["constraint_filters_applied"] == []
    assert result_with_constraint.extensions["decision_governance"]["constraint_filters_applied"] == [
        {
            "decision_type": "migration_consideration",
            "effect": "exclude_from_recommendation",
            "source_constraint": "마이그레이션은 이번 범위에서 제외",
        }
    ]


def test_rebuild_assistant_confidence_does_not_increase_with_strong_intent_inputs():
    service = RebuildAssistantService()
    base_assets = RebuildAssetsPayload(
        source_code="class OrderService:\n    pass",
        ui_template="<button>submit</button>",
    )
    plain = service.prepare_input(goal="", assets=base_assets, constraints=[])
    intent_heavy = service.prepare_input(
        goal="반드시 React와 Spring Boot로 전환한다.",
        assets=base_assets,
        constraints=["마이그레이션 계획은 별도 문서로 만든다."],
        temp_context="업무 시나리오: 구조를 전면 재설계해야 한다.",
    )

    assert service.estimate_confidence(plain) == service.estimate_confidence(intent_heavy)


def test_rebuild_assistant_same_input_keeps_polished_narrative_deterministic():
    first = _build_validation_bundle_result(grounded=False)
    second = _build_validation_bundle_result(grounded=False)

    assert first.one_line_conclusion == second.one_line_conclusion
    assert first.executive_summary_v2 == second.executive_summary_v2
    assert first.recommended_option.model_dump() == second.recommended_option.model_dump()
    assert first.extensions["decision_governance"]["document_outline"] == second.extensions["decision_governance"]["document_outline"]


def test_rebuild_assistant_limited_grounding_uses_conditional_recommendation_wording():
    result = _build_validation_bundle_result(grounded=False)
    outline = result.extensions["decision_governance"]["document_outline"]
    grounding = result.extensions["decision_governance"]["recommendation_grounding"]

    assert grounding["level"] == "limited"
    assert result.one_line_conclusion.endswith("우선 검토해야 합니다.")
    assert [line.split(":", 1)[0] for line in result.executive_summary_v2[:4]] == ["문제", "영향", "조치", "다음 단계"]
    assert "우선 검토안" in result.executive_summary_v2[2]
    assert result.recommended_option is not None
    assert "우선 검토안" in result.recommended_option.selection_reason
    assert "판단 근거는" in outline["rationale"]
    assert outline["risk"] == "차단 조건과 저장 전 검증이 다시 섞이면 예외 누락과 저장 경로 재작업 위험이 커집니다."


def test_rebuild_assistant_grounded_recommendation_stays_assertive_and_evidence_linked():
    result = _build_validation_bundle_result(grounded=True)
    outline = result.extensions["decision_governance"]["document_outline"]
    grounding = result.extensions["decision_governance"]["recommendation_grounding"]

    assert grounding["level"] == "grounded"
    assert result.one_line_conclusion.endswith("분리해야 합니다.")
    assert "우선안" in result.executive_summary_v2[2]
    assert result.recommended_option is not None
    assert "검토안" not in result.recommended_option.selection_reason
    assert "초안" not in result.recommended_option.selection_reason
    assert "판단 근거는" in outline["rationale"]
    assert "screen.html" in outline["rationale"] or "order_page" in outline["rationale"]


def test_rebuild_assistant_same_validation_pattern_uses_consistent_risk_and_conclusion_shape():
    service = RebuildAssistantService()
    first = service.build_result(
        service.prepare_safe_bundle_input(
            goal="modernize order validation flow",
            safe_bundle=build_safe_bundle(
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
                        """,
                    },
                    {"name": "order_page.jsp", "content": '<button onclick="submitOrder()">submit</button>'},
                    {"name": "order_query.sql", "content": "SELECT * FROM orders WHERE status = 'READY'"},
                ]
            ),
            constraints=[],
        )
    )
    second = service.build_result(
        service.prepare_safe_bundle_input(
            goal="modernize claim validation flow",
            safe_bundle=build_safe_bundle(
                [
                    {
                        "name": "claim_service.py",
                        "content": """
class ClaimService:
    def submit(self, claim, repo):
        if not claim.amount:
            raise ValueError("required")
        if claim.status == "READY":
            repo.save(claim)
                        """,
                    },
                    {"name": "claim_page.jsp", "content": '<button onclick="submitClaim()">submit</button>'},
                    {"name": "claim_query.sql", "content": "SELECT * FROM claims WHERE status = 'READY'"},
                ]
            ),
            constraints=[],
        )
    )

    assert "차단 조건, 검증 순서, 저장 전 검증을 검증 계층과 처리 흐름으로" in first.one_line_conclusion
    assert "차단 조건, 검증 순서, 저장 전 검증을 검증 계층과 처리 흐름으로" in second.one_line_conclusion
    assert first.extensions["decision_governance"]["document_outline"]["risk"] == second.extensions["decision_governance"]["document_outline"]["risk"]


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
        "family_classification",
        "structure_snapshot",
        "diagnosis_report",
        "decision_summary",
        "improvement_plan_bundle",
        "judgment_canvas",
        "stage_control",
        "validation_result",
        "appendix",
    }
    structured = payload["structured_result"]
    assert structured["judgment_canvas"] == payload["authoritative_payload"]["judgment_canvas"]
    assert structured["stage_control"] == payload["authoritative_payload"]["stage_control"]
    assert structured["validation_result"] == payload["authoritative_payload"]["validation_result"]


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
    monkeypatch.setattr(app_state, "narrative_llm_service", FakeLLM(), raising=False)
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


def test_rebuild_assistant_service_prepare_safe_bundle_input_uses_engine_input_assembler(monkeypatch):
    bundle = build_safe_bundle([{"name": "order_service.py", "content": "class OrderService: pass"}])
    expected = PreparedRebuildInput(
        goal="modernize order flow",
        assets=RebuildAssetsPayload(),
        constraints=[],
        signals=FeatureSignals(),
        missing_context=[],
    )

    def fake_prepare_safe_bundle_input(self, legacy_service, **kwargs):
        assert isinstance(legacy_service, RebuildAssistantService)
        assert kwargs["safe_bundle"] == bundle
        return expected

    monkeypatch.setattr(InputAssembler, "prepare_safe_bundle_input", fake_prepare_safe_bundle_input)

    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])

    assert prepared is expected


def test_rebuild_assistant_service_planning_wrappers_delegate_to_engine_support(monkeypatch):
    bundle = build_safe_bundle([{"name": "order_service.py", "content": "class OrderService: pass"}])
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(goal="modernize order flow", safe_bundle=bundle, constraints=[])

    calls = []

    def fake_infer(self, arg):
        calls.append(("infer", arg.goal))
        return ["engine strategy"]

    def fake_recompose(self, arg, applied_templates=None):
        calls.append(("recompose", arg.goal, tuple(applied_templates or [])))
        return SimpleNamespace(database=["db"], backend=["api"], frontend=["ui"])

    monkeypatch.setattr(TemplateSupport, "infer_target_architecture", fake_infer)
    monkeypatch.setattr(TemplateSupport, "build_recomposition_draft", fake_recompose)

    assert service.infer_target_architecture(prepared) == ["engine strategy"]
    draft = service.build_recomposition_draft(prepared)

    assert draft.database == ["db"]
    assert draft.backend == ["api"]
    assert draft.frontend == ["ui"]
    assert calls == [
        ("infer", "modernize order flow"),
        ("recompose", "modernize order flow", ()),
    ]
