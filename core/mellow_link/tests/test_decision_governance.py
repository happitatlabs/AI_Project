from __future__ import annotations

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.decision_engine import DecisionEngine
from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine
from mellow_link.services.refactoring_support_engine.improvement_planner import ImprovementPlanner
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.services.refactoring_support_engine.schemas import (
    DecisionArtifacts,
    DecisionExplainability,
    DecisionRecord,
    DiagnosisArtifacts,
    DiagnosisReport,
    StructuralIssue,
)
from mellow_link.services.refactoring_support_engine.structure_analyzer import StructureAnalyzer

from .refactoring_support_test_utils import build_safe_bundle, load_expansion_sample_case


def _run_decision_engine(asset_specs, goal: str, constraints: list[str] | None = None):
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=goal,
        safe_bundle=build_safe_bundle(asset_specs),
        constraints=constraints or [],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    return service, prepared, structure, diagnosis, decisions


def _fx_fifo_boundary_asset_specs():
    return [
        {
            "name": "fx_fifo_page.jsp",
            "content": """
<%@ page import="FxFifoRepository" %>
<%
FxFifoRepository repo = new FxFifoRepository();
repo.findLots();
if (outAmt > 0) {
    repo.saveGl();
}
%>
            """,
        },
        {
            "name": "fx_fifo_repository.java",
            "content": """
class FxFifoRepository {
    String findLots() {
        return "SELECT ACCT_SEQ, RMN_FAMT FROM TN_FORINS ORDER BY TR_DATE, TR_DATE_SEQ";
    }

    void saveGl() {
        String sql = "INSERT INTO GL_INTERFACE (REFERENCE4, REFERENCE6, USER_JE_CATEGORY_NAME, CURRENCY_CODE) VALUES (?, ?, ?, ?)";
    }
}
            """,
        },
        {
            "name": "TN_FORINS.sql",
            "content": """
CREATE TABLE TN_FORINS (
    ACCT_SEQ VARCHAR2(50),
    TR_DATE VARCHAR2(8),
    TR_DATE_SEQ NUMBER,
    RMN_FAMT NUMBER,
    RMN_AMT NUMBER,
    EXCH_RATE NUMBER,
    MNEY_UNIT VARCHAR2(5)
);
            """,
        },
        {
            "name": "P_FOROUT.prc",
            "content": """
CREATE OR REPLACE procedure P_FOROUT IS
BEGIN
    IF out_amt > 0 THEN
        FOR clr IN (
            SELECT ACCT_SEQ, TR_DATE, TR_DATE_SEQ, RMN_FAMT, RMN_AMT, EXCH_RATE
            FROM TN_FORINS
            ORDER BY TR_DATE, TR_DATE_SEQ
        ) LOOP
            INSERT INTO TN_FOROUD (OUTF_AMT, OUT_AMT0, GAP_AMT) VALUES (10, 1000, 50);
        END LOOP;
    END IF;
END;
            """,
        },
        {
            "name": "TRG_FOROUT.sql",
            "content": """
CREATE OR REPLACE TRIGGER TRG_FOROUT
BEFORE INSERT ON TN_FOROUT
FOR EACH ROW
BEGIN
    IF :NEW.OUT_AMT > 0 THEN
        INSERT INTO TN_FOROUD (OUTF_AMT, OUT_AMT0, GAP_AMT)
        VALUES (:NEW.OUT_FAMT, :NEW.OUT_AMT, :NEW.OUT_AMT - 100);
    END IF;
END;
            """,
        },
        {
            "name": "P_BKCHNO.prc",
            "content": """
CREATE OR REPLACE procedure P_BKCHNO IS
BEGIN
    IF out_amt > 0 THEN
        INSERT INTO TN_BKCHIT (OCCR_PART, MNEY_UNIT) VALUES ('exchange p/l', 'USD');
        INSERT INTO GL_INTERFACE (REFERENCE4, REFERENCE6, USER_JE_CATEGORY_NAME, CURRENCY_CODE)
        VALUES ('CHK-20260418', '1', 'deposit', 'USD');
    END IF;
END;
            """,
        },
        {
            "name": "GL_INTERFACE.sql",
            "content": """
CREATE TABLE GL_INTERFACE (
    REFERENCE4 VARCHAR2(50),
    REFERENCE6 VARCHAR2(50),
    USER_JE_CATEGORY_NAME VARCHAR2(25),
    CURRENCY_CODE VARCHAR2(5),
    ENTERED_DR NUMBER,
    ENTERED_CR NUMBER
);
            """,
        },
    ]


def test_goal_only_migration_signal_is_blocked_and_downgrades_to_observation_only():
    case = load_expansion_sample_case("01_crud_simple")
    _, _, _, diagnosis, decisions = _run_decision_engine(
        case["asset_specs"],
        goal="reports CRUD 구조를 점검하고 전환 초안을 작성하라.",
    )

    assert diagnosis.diagnosis_report.issues == []
    assert decisions.synthetic_signal_detected is True
    assert decisions.structural_judgment == "observation_only"
    assert decisions.decision_summary.decisions == []
    assert decisions.decision_summary.recommended_strategy == "리팩터링 우선"
    assert not any(item.decision_type == "migration_consideration" for item in decisions.decision_summary.decisions)


def test_asset_absent_migration_decision_is_downgraded_to_refactor_by_hard_guard():
    engine = DecisionEngine()
    blocking_issue = StructuralIssue(
        issue_id="ISSUE-BOUNDARY",
        detector_id="duplicate_logic_candidate",
        category="duplication",
        severity=3,
        blast_radius=2,
        effort=2,
        summary="Repeated predicate sample",
        affected_component_ids=["cmp-a"],
        affected_slice_ids=["slice-a"],
        evidence_ids=["ev-1"],
        confidence=0.81,
    )
    rogue_migration = DecisionRecord(
        decision_id="DEC-ROGUE-MIGRATION",
        issue_ids=[],
        decision_type="migration_consideration",
        target_component_ids=["cmp-a"],
        priority_score=7,
        score_breakdown={"final_score": 7},
        explainability=DecisionExplainability(
            decision_rule="migration signal -> migration_consideration",
            score_formula="baseline",
            score_summary="migration_consideration final_score=7",
            evidence_count=0,
            affected_slice_count=0,
        ),
        rationale="전환 필요성을 검토한다.",
        confidence=0.72,
        evidence_ids=[],
    )

    guarded, synthetic_signal_detected = engine._apply_migration_hard_guard(
        [rogue_migration],
        DiagnosisArtifacts(diagnosis_report=DiagnosisReport(issues=[blocking_issue])),
    )

    assert synthetic_signal_detected is True
    assert len(guarded) == 1
    assert guarded[0].decision_type == "refactor"
    assert guarded[0].issue_ids == []
    assert guarded[0].evidence_ids == []
    assert "hard guard" in guarded[0].explainability.decision_rule


def test_legitimate_migration_is_preserved_when_asset_and_issue_support_exist():
    _, _, _, diagnosis, decisions = _run_decision_engine(
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
# migration target: spring boot rest api + react admin
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
            {
                "name": "pom.xml",
                "content": """
<project>
  <artifactId>legacy-order</artifactId>
  <dependencies>
    <dependency>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
                """,
            },
        ],
        goal="legacy order approval flow migration plan",
    )

    migration_decisions = [item for item in decisions.decision_summary.decisions if item.decision_type == "migration_consideration"]

    assert diagnosis.diagnosis_report.issues
    assert any(item.detector_id in {"boundary_mismatch", "ui_data_access_coupling"} for item in diagnosis.diagnosis_report.issues)
    assert decisions.synthetic_signal_detected is False
    assert migration_decisions
    assert all(item.issue_ids for item in migration_decisions)
    assert all(item.evidence_ids for item in migration_decisions)


def test_goal_wording_alone_does_not_upgrade_issue_bearing_sample_to_migration():
    case = load_expansion_sample_case("04_db_heavy_query_filter")
    _, _, _, diagnosis, decisions = _run_decision_engine(
        case["asset_specs"],
        goal="요청 검색 구조를 점검하고 전환 초안을 제시하라.",
    )

    assert diagnosis.diagnosis_report.issues
    assert decisions.synthetic_signal_detected is True
    assert decisions.structural_judgment == "refactor"
    assert decisions.decision_summary.decisions
    assert decisions.decision_summary.decisions[0].decision_type == "refactor"
    assert not any(item.decision_type == "migration_consideration" for item in decisions.decision_summary.decisions)
    assert all(item.issue_ids for item in decisions.decision_summary.decisions)
    assert all(item.evidence_ids for item in decisions.decision_summary.decisions)


def test_result_packager_exposes_governance_metadata_and_rechecks_rogue_migration():
    case = load_expansion_sample_case("04_db_heavy_query_filter")
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal="reports CRUD 구조를 점검하고 전환 초안을 작성하라.",
        safe_bundle=case["safe_bundle"],
        constraints=[],
    )
    structure = StructureAnalyzer().analyze(InputAssembler().assemble(prepared))
    diagnosis = DiagnosisEngine().run(prepared, structure, service)
    decisions = DecisionEngine().run(prepared, structure, diagnosis, service)
    rogue_migration = DecisionRecord(
        decision_id="DEC-ROGUE-MIGRATION",
        issue_ids=[],
        decision_type="migration_consideration",
        target_component_ids=["cmp-a"],
        priority_score=7,
        score_breakdown={"final_score": 7},
        explainability=DecisionExplainability(
            decision_rule="migration signal -> migration_consideration",
            score_formula="baseline",
            score_summary="migration_consideration final_score=7",
            evidence_count=0,
            affected_slice_count=0,
        ),
        rationale="전환 필요성을 검토한다.",
        confidence=0.72,
        evidence_ids=[],
    )
    decisions = DecisionArtifacts(
        decision_summary=decisions.decision_summary.model_copy(
            update={
                "decisions": [rogue_migration],
                "recommended_strategy": "마이그레이션 고려",
                "priority_queue": [rogue_migration.decision_id],
            }
        ),
        applied_templates=decisions.applied_templates,
        pattern_candidates=decisions.pattern_candidates,
        primary_judgment=decisions.primary_judgment,
        template_judgment=decisions.template_judgment,
        structural_judgment="migration_consideration",
        narrative_axis=decisions.narrative_axis,
        feature_signal_mode=decisions.feature_signal_mode,
        primary_judgment_reason=decisions.primary_judgment_reason,
        selected_narrative_judgment=decisions.selected_narrative_judgment,
        decision_items=decisions.decision_items,
        synthetic_signal_detected=False,
    )
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)

    result = ResultPackager().package(prepared, structure, diagnosis, decisions, improvement, service)

    assert result.structural_judgment == "refactor"
    assert result.decision_summary["decisions"]
    assert all(item["decision_type"] == "refactor" for item in result.decision_summary["decisions"])
    assert result.extensions["decision_governance"]["synthetic_signal_detected"] is True
    assert result.extensions["decision_governance"]["packager_guard_applied"] is True


def test_operational_sql_bundle_keeps_operational_analysis_when_boundary_mismatch_exists():
    service, prepared, structure, diagnosis, decisions = _run_decision_engine(
        _fx_fifo_boundary_asset_specs(),
        goal="외화 입출금 FIFO 처리 흐름을 검토해줘",
    )
    improvement = ImprovementPlanner().run(prepared, structure, diagnosis, decisions, service)
    result = ResultPackager().package(prepared, structure, diagnosis, decisions, improvement, service)

    assert any(item.detector_id == "boundary_mismatch" for item in diagnosis.diagnosis_report.issues)
    assert decisions.decision_summary.decisions
    assert decisions.decision_summary.decisions[0].decision_type == "refactor"
    assert "운영 소스 분석 우선 게이트" in decisions.decision_summary.decisions[0].explainability.decision_rule
    assert decisions.decision_summary.recommended_strategy == "리팩터링 우선"
    assert decisions.family_classification.family == "operational_source"
    assert "redesign_review" in decisions.family_classification.secondary_signals
    assert decisions.structural_judgment == "refactor"
    assert result.one_line_conclusion.startswith("본 자산은")
    assert "분리 구조" not in result.one_line_conclusion
    assert result.executive_summary_v2[0].startswith("현행 분석:")
    assert "현행 분석 우선" == result.extensions["decision_governance"]["document_outline"]["recommended_strategy"]
    assert result.family_classification.family == "operational_source"
    assert len(result.execution_plan) == 3
    assert all("주차" not in item.week_label for item in result.execution_plan)
    assert all("로드맵" not in item.goal for item in result.execution_plan)
