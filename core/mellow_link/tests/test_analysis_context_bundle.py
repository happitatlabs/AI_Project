from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from mellow_link.infra.database import AnalysisContext, Base, ModernizationProject
from mellow_link.modules.rebuild_assistant.schemas import GroundedBusinessRule
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.services.refactoring_support_engine.schemas import DiagnosisArtifacts

from .refactoring_support_test_utils import build_safe_bundle


def _bundle():
    return build_safe_bundle(
        [
            {"name": "goal.txt", "content": "Modernize order save flow"},
            {"name": "constraints.txt", "content": "Keep audit trail"},
            {
                "name": "OrderService.java",
                "content": "class OrderService { void save(Order order) { repository.save(order); } }",
            },
            {
                "name": "schema.sql",
                "content": "CREATE TABLE orders (id BIGINT PRIMARY KEY, status VARCHAR(20));",
            },
        ]
    )


def _context(run_id: str = "run-ctx-001"):
    return AnalysisContextBuilder().build(
        project_id="proj_ctx_001",
        run_id=run_id,
        safe_bundle=_bundle(),
        goal="Modernize order save flow",
        constraints=["Keep audit trail"],
        project_name="Order Modernization",
        client_name="ACME",
        template_key="default_modernization_v1",
    )


def test_analysis_context_builder_is_deterministic_and_excludes_intent_assets():
    bundle = _bundle()
    context = _context()
    reordered_context = AnalysisContextBuilder().build(
        project_id="proj_ctx_001",
        run_id="run-ctx-001",
        safe_bundle=bundle.model_copy(
            update={
                "asset_summary": list(reversed(bundle.asset_summary)),
                "sources": list(reversed(bundle.sources)),
            }
        ),
        goal="Modernize order save flow",
        constraints=["Keep audit trail"],
        project_name="Order Modernization",
        client_name="ACME",
        template_key="default_modernization_v1",
    )

    assert context.context_id == "ctx_proj_ctx_001_run-ctx-001"
    assert context.run.input_fingerprint == reordered_context.run.input_fingerprint
    assert {asset.name for asset in context.assets}.isdisjoint({"goal.txt", "constraints.txt", "scenario.md"})
    assert {block.asset_name for block in context.source_blocks}.isdisjoint({"goal.txt", "constraints.txt", "scenario.md"})
    assert context.intent.sources["goal"] == "inline|goal.txt"
    assert context.intent.sources["constraints"] == "inline|constraints.txt"
    assert any(block.content.startswith("class OrderService") for block in context.source_blocks)


def test_input_assembler_prefers_analysis_context_over_legacy_bundle():
    service = RebuildAssistantService()
    context = _context()
    prepared = service.prepare_analysis_context_input(analysis_context=context)
    prepared.legacy_bundle = "WRONG_LEGACY_TEXT"
    analysis_input = InputAssembler().assemble(prepared)

    assert prepared.analysis_context is context
    assert analysis_input.safe_bundle_id == context.trust.safe_bundle_id
    assert analysis_input.input_fingerprint == context.run.input_fingerprint
    assert not any("WRONG_LEGACY_TEXT" in block.content for block in analysis_input.source_blocks)
    assert any(block.asset_name == "OrderService.java" for block in analysis_input.source_blocks)


def test_analysis_contexts_table_persists_payload_and_enforces_run_uniqueness():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    context = _context()
    db.add(
        ModernizationProject(
            id=context.project.project_id,
            user_id=1,
            session_id="session-1",
            run_id="project-run",
            project_name=context.project.project_name,
            client_name=context.project.client_name,
            goal_text=context.intent.goal,
            template_key=context.project.template_key,
            constraints_json=json.dumps(context.intent.constraints, ensure_ascii=False),
            upload_session_id="upload-1",
            asset_manifest_json="[]",
        )
    )
    db.add(
        AnalysisContext(
            context_id=context.context_id,
            project_id=context.project.project_id,
            run_id=context.run.run_id,
            safe_bundle_id=context.trust.safe_bundle_id,
            input_fingerprint=context.run.input_fingerprint,
            schema_version=context.schema_version,
            payload_json=json.dumps(context.model_dump(mode="json"), ensure_ascii=False),
        )
    )
    db.commit()

    row = db.query(AnalysisContext).filter(AnalysisContext.run_id == context.run.run_id).one()
    assert json.loads(row.payload_json)["context_id"] == context.context_id

    db.add(
        AnalysisContext(
            context_id="ctx_duplicate",
            project_id=context.project.project_id,
            run_id=context.run.run_id,
            safe_bundle_id=context.trust.safe_bundle_id,
            input_fingerprint=context.run.input_fingerprint,
            schema_version=context.schema_version,
            payload_json="{}",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_result_payloads_include_context_linkage_and_allow_empty_evidence_refs():
    service = RebuildAssistantService()
    context = _context()
    prepared = service.prepare_analysis_context_input(analysis_context=context)
    prepared.safe_bundle = _bundle()

    result = service.build_result(prepared)

    assert result.context_id == context.context_id
    assert result.input_fingerprint == context.run.input_fingerprint
    assert result.safe_bundle_id == context.trust.safe_bundle_id
    assert result.evidence_refs == [item.evidence_id for item in context.evidence_index]
    assert result.canonical_payload is not None
    assert result.canonical_payload.appendix["context_linkage"] == {
        "context_id": result.context_id,
        "input_fingerprint": result.input_fingerprint,
        "safe_bundle_id": result.safe_bundle_id,
        "evidence_refs": result.evidence_refs,
    }


def test_evidence_missing_confirmed_claims_are_degraded_without_run_failure():
    diagnosis = DiagnosisArtifacts(
        grounded_business_rules=[
            GroundedBusinessRule(
                title="Confirmed without evidence",
                description="This should be downgraded at item level.",
                confidence="확정",
                needs_verification=False,
            )
        ]
    )

    degraded = ResultPackager()._degrade_unverified_claims(diagnosis)

    assert degraded.grounded_business_rules[0].confidence == "가정"
    assert degraded.grounded_business_rules[0].needs_verification is True
    assert degraded.missing_context_details[0].reason == "missing_decision_driving_evidence"
