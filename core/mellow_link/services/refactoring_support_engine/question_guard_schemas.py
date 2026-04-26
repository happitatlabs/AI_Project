from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceQuestionCandidate(BaseModel):
    question: str
    source_asset_id: str | None = None
    source_stage: Literal["sml", "document", "code", "manual"] = "document"
    evidence_snippet: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    question_type: Literal[
        "problem_definition",
        "option_comparison",
        "decision_criteria",
        "implementation",
        "risk",
        "missing_information",
        "strategy",
        "scope",
    ] = "problem_definition"
    blocked_reason: str | None = None


class GuardedUserQuestion(BaseModel):
    question: str
    status: Literal["allowed", "blocked", "needs_review"] = "allowed"
    blocked_reason: str | None = None
    matched_source_question: str = ""
    evidence_snippet: str = ""


class QuestionGuardSummary(BaseModel):
    safe_question_count: int = 0
    blocked_question_count: int = 0
    review_question_count: int = 0
    candidate_count: int = 0
    source_question_candidate_count: int = 0
    allowed_user_question_count: int = 0
    needs_review: bool = False
    source_question_shortage: bool = False
    uploaded_asset_count: int = 0
    has_pptx_asset: bool = False
    has_safe_source_text: bool = False
    safe_source_count: int = 0
    guard_input_source_count: int = 0
    guard_input_total_chars: int = 0
    sml_text_length: int = 0
    no_candidate_reasons: list[str] = Field(default_factory=list)
    selected_questions: list[str] = Field(default_factory=list)
    selected_question_types: list[str] = Field(default_factory=list)
    source_domain_terms: list[str] = Field(default_factory=list)
    preferred_question_axis: str = ""
    applied_question_source: Literal["source_candidates", "mixed_with_user", "generic_fallback"] = "generic_fallback"


class GuardedDecisionInput(BaseModel):
    raw_goal: str = ""
    raw_constraints: list[str] = Field(default_factory=list)
    effective_goal: str = ""
    effective_constraints: list[str] = Field(default_factory=list)
    raw_question_axis: str = ""
    preferred_question_axis: str = ""
    selected_questions: list[str] = Field(default_factory=list)
    selected_question_types: list[str] = Field(default_factory=list)
    source_domain_terms: list[str] = Field(default_factory=list)
    applied_question_source: Literal["source_candidates", "mixed_with_user", "generic_fallback", "uninitialized"] = "uninitialized"
