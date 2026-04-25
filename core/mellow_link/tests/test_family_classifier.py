from __future__ import annotations

import pytest

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.family_classifier import FamilyClassifier

from .family_classifier_golden_samples import FAMILY_CLASSIFIER_GOLDEN_EXPECTATIONS
from .refactoring_support_test_utils import build_safe_bundle, load_sample_case


def _prepare(goal: str, asset_specs: list[dict[str, str]], constraints: list[str] | None = None):
    service = RebuildAssistantService()
    return service.prepare_safe_bundle_input(
        goal=goal,
        safe_bundle=build_safe_bundle(asset_specs),
        constraints=constraints or [],
    )


def test_family_classifier_prefers_redesign_review_when_explicit_structure_goal_overrides_code_asset_type():
    prepared = _prepare(
        "현재 구조 문제와 책임 분리 방향을 판단해줘",
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
            {
                "name": "order_query.sql",
                "content": "SELECT * FROM orders WHERE status = 'READY' AND amount > 1000",
            },
        ],
    )

    classification = FamilyClassifier().classify(prepared)

    assert classification.family == "redesign_review"
    assert "operational_source" in classification.secondary_signals
    assert classification.display_strategy == "구조 문제 우선"
    assert classification.internal_strategy == "재설계 우선"


def test_family_classifier_prefers_document_consulting_without_comparison_question():
    prepared = _prepare(
        "이 문서를 구조화해서 핵심 내용을 설명해줘",
        [
            {
                "name": "meeting_notes.md",
                "content": """
# Migration Review

- Current scope is legacy approval workflow.
- This document should be summarized and restructured for a steering committee.
                """,
            }
        ],
    )

    classification = FamilyClassifier().classify(prepared)

    assert classification.family == "document_consulting"
    assert classification.secondary_signals == []
    assert classification.display_strategy == "문서 구조화 우선"
    assert classification.internal_strategy == "문서 구조화"


def test_family_classifier_fixed_schema_and_secondary_signal_do_not_override_primary():
    case = load_sample_case("12_operational_redesign_boundary")
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )

    classification = FamilyClassifier().classify(prepared)

    assert set(classification.model_dump().keys()) == {
        "family",
        "confidence",
        "decision_basis",
        "secondary_signals",
        "display_strategy",
        "internal_strategy",
    }
    assert classification.family == "operational_source"
    assert "redesign_review" in classification.secondary_signals
    assert classification.internal_strategy == "리팩터링 우선"


def test_family_classifier_treats_operational_flow_reconstruction_as_operational_source():
    prepared = _prepare(
        "외화 입출금 FIFO 처리 흐름을 재구성해줘",
        [
            {
                "name": "TN_FORINS.sql",
                "content": """
CREATE TABLE TN_FORINS (
    ACCT_SEQ VARCHAR2(50),
    TR_DATE VARCHAR2(8),
    TR_DATE_SEQ NUMBER,
    RMN_FAMT NUMBER,
    RMN_AMT NUMBER,
    EXCH_RATE NUMBER
);
                """,
            },
            {
                "name": "P_FOROUT.prc",
                "content": """
CREATE OR REPLACE procedure P_FOROUT IS
BEGIN
    FOR clr IN (SELECT ACCT_SEQ, TR_DATE, TR_DATE_SEQ, RMN_FAMT, RMN_AMT, EXCH_RATE FROM TN_FORINS ORDER BY TR_DATE, TR_DATE_SEQ) LOOP
        INSERT INTO TN_FOROUD (OUTF_AMT, OUT_AMT0, GAP_AMT) VALUES (10, 1000, 50);
    END LOOP;
END;
                """,
            },
            {
                "name": "GL_INTERFACE.sql",
                "content": """
CREATE TABLE GL_INTERFACE (
    REFERENCE4 VARCHAR2(50),
    USER_JE_CATEGORY_NAME VARCHAR2(25),
    CURRENCY_CODE VARCHAR2(5)
);
                """,
            },
        ],
        constraints=[
            "승인(order) 도메인으로 해석하지 마라",
            "워크플로우/승인/권한 모델로 확장하지 마라",
            "외화 입금, 출금, FIFO lot, 환차손익, 전표, GL 흐름만 다뤄라",
        ],
    )

    classification = FamilyClassifier().classify(prepared)

    assert classification.family == "operational_source"
    assert "redesign_review" in classification.secondary_signals
    assert classification.display_strategy == "현행 분석 우선"
    assert classification.decision_basis


@pytest.mark.parametrize(
    "expectation",
    FAMILY_CLASSIFIER_GOLDEN_EXPECTATIONS,
    ids=[item.sample_name for item in FAMILY_CLASSIFIER_GOLDEN_EXPECTATIONS],
)
def test_family_classifier_golden_boundary_samples(expectation):
    case = load_sample_case(expectation.sample_name)
    service = RebuildAssistantService()
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )

    classification = FamilyClassifier().classify(prepared)

    assert classification.family == expectation.expected_family
    assert tuple(classification.secondary_signals) == expectation.expected_secondary_signals
    assert classification.display_strategy == expectation.expected_display_strategy
    assert classification.internal_strategy == expectation.expected_internal_strategy
    assert classification.decision_basis
