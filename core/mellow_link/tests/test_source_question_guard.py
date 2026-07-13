from __future__ import annotations

from mellow_link.services.anonymization import (
    AnonymizationAsset,
    AnonymizationRunRequest,
    AnonymizationService,
)
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder
from mellow_link.services.refactoring_support_engine.source_question_guard import SourceQuestionGuardService


def _cost_safe_bundle():
    sml = "\n".join(
        [
            "[SML v1]",
            "presentation_file: cost_consulting_deck.pptx",
            "slide_count: 2",
            "",
            "[SLIDE 1]",
            "title: [CLIENT] 원가 컨설팅 개요",
            "texts:",
            "- 현행 원가체계 분석",
            "- 원가분석 및 원가계산 개선 방향",
            "- 재료비, 노무비, 제조경비 배부기준 검토",
            "- 손익분석 확장 검토",
            "",
            "[SLIDE 2]",
            "title: 배부기준 재정의",
            "texts:",
            "- 배부기준 조정",
            "- 재료비 배부 기준",
            "- 노무비 배부 기준",
            "- 제조경비 배부 기준",
        ]
    )
    return AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_question_guard_cost",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_cost_001",
                    name="cost_consulting_deck.pptx",
                    temp_file_id="temp_cost_001",
                    kind_hint="presentation",
                    content_text=sml,
                    original_bytes=b"pptx-binary",
                )
            ],
        )
    ).safe_bundle


def _build_context(*, safe_bundle, goal: str = "", constraints: list[str] | None = None):
    return AnalysisContextBuilder().build(
        project_id="proj_question_guard_cost",
        run_id="run_question_guard",
        safe_bundle=safe_bundle,
        goal=goal,
        constraints=constraints or [],
    )


def test_cost_sml_extracts_source_grounded_questions():
    safe_bundle = _cost_safe_bundle()
    context = _build_context(safe_bundle=safe_bundle)

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal="",
        raw_constraints=[],
    )

    questions = [item.question for item in result.source_question_candidates]
    snippets = [item.evidence_snippet for item in result.source_question_candidates]

    assert "현행 원가체계의 한계는 무엇인가?" in questions
    assert "문서가 제안하는 원가계산 개선 방향은 무엇인가?" in questions
    assert "재료비, 노무비, 제조경비 배부 기준은 어떻게 달라지는가?" in questions
    assert "원가계산 결과를 손익분석까지 확장할 근거가 있는가?" in questions
    assert result.question_guard_summary.preferred_question_axis == "processing_flow"
    assert any("원가" in snippet for snippet in snippets)
    assert any("[CLIENT]" in snippet for snippet in snippets)


def test_question_guard_blocks_product_validation_domain_mismatch():
    safe_bundle = _cost_safe_bundle()
    context = _build_context(
        safe_bundle=safe_bundle,
        goal="제품 저장 전 검증 로직을 어떻게 강화할 것인가?",
        constraints=["SQL 파라미터 검증을 어떻게 설계할 것인가?"],
    )

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal=context.intent.goal,
        raw_constraints=context.intent.constraints,
    )

    blocked = {(item.question, item.blocked_reason) for item in result.blocked_user_questions}

    assert (
        "제품 저장 전 검증 로직을 어떻게 강화할 것인가?",
        "source_domain_mismatch",
    ) in blocked
    assert (
        "SQL 파라미터 검증을 어떻게 설계할 것인가?",
        "source_domain_mismatch",
    ) in blocked
    assert result.effective_goal == "현행 원가체계의 한계는 무엇인가?"


def test_question_guard_marks_forced_rebuild_as_review():
    safe_bundle = _cost_safe_bundle()
    context = _build_context(
        safe_bundle=safe_bundle,
        goal="전면 재구축해야 하는가?",
        constraints=["무조건 TO-BE 시스템으로 전환해야 하는가?"],
    )

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal=context.intent.goal,
        raw_constraints=context.intent.constraints,
    )

    review = {(item.question, item.blocked_reason) for item in result.review_user_questions}
    assert ("전면 재구축해야 하는가?", "conclusion_forcing") in review
    assert ("무조건 TO-BE 시스템으로 전환해야 하는가?", "conclusion_forcing") in review
    assert result.question_guard_summary.needs_review is True


def test_question_guard_evidence_snippet_stays_safe():
    safe_bundle = _cost_safe_bundle()
    context = _build_context(safe_bundle=safe_bundle)

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal="",
        raw_constraints=[],
    )

    dump = " ".join(item.evidence_snippet for item in result.source_question_candidates)
    assert "[CLIENT]" in dump
    assert "OO우유" not in dump
    assert "홍길동" not in dump


def test_question_guard_reports_shortage_when_source_is_too_thin():
    safe_bundle = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_question_guard_short",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_short_001",
                    name="short.txt",
                    temp_file_id="temp_short_001",
                    kind_hint="doc",
                    content_text="짧은 메모",
                    original_bytes=b"memo",
                )
            ],
        )
    ).safe_bundle
    context = AnalysisContextBuilder().build(
        project_id="proj_question_guard_short",
        run_id="run_question_guard_short",
        safe_bundle=safe_bundle,
        goal="",
        constraints=[],
    )

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal="",
        raw_constraints=[],
    )

    assert result.source_question_candidates == []
    assert result.question_guard_summary.needs_review is True
    assert result.question_guard_summary.source_question_shortage is True
    assert result.question_guard_summary.guard_input_source_count == 1
    assert "insufficient_source_text" in result.question_guard_summary.no_candidate_reasons


def test_question_guard_builds_generic_fallback_for_non_domain_document():
    safe_bundle = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id="proj_question_guard_generic",
            assets=[
                AnonymizationAsset(
                    asset_id="asset_generic_001",
                    name="generic_doc.txt",
                    temp_file_id="temp_generic_001",
                    kind_hint="doc",
                    content_text="\n".join(
                        [
                            "[SML v1]",
                            "presentation_file: generic_strategy_deck.pptx",
                            "slide_count: 1",
                            "",
                            "[SLIDE 1]",
                            "title: 개선 전략 검토",
                            "texts:",
                            "- 현행 프로세스의 한계",
                            "- 개선 방향 검토",
                            "- 추가 확인이 필요한 항목",
                            "- 판단 기준 정리",
                        ]
                    ),
                    original_bytes=b"generic",
                )
            ],
        )
    ).safe_bundle
    context = AnalysisContextBuilder().build(
        project_id="proj_question_guard_generic",
        run_id="run_question_guard_generic",
        safe_bundle=safe_bundle,
        goal="",
        constraints=[],
    )

    result = SourceQuestionGuardService().evaluate(
        analysis_context=context,
        raw_goal="",
        raw_constraints=[],
    )

    questions = [item.question for item in result.source_question_candidates]
    assert "이 문서는 어떤 문제를 해결하려는가?" in questions
    assert "현행 구조의 한계는 무엇인가?" in questions
    assert result.question_guard_summary.guard_input_total_chars >= 120
    assert "no_domain_terms_detected" in result.question_guard_summary.no_candidate_reasons
