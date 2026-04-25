from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PolishedSection(BaseModel):
    section_key: str
    title: str
    original_text: str
    polished_text: str
    audience_variants: dict[str, str] = Field(default_factory=dict)
    delivery_variants: dict[str, str] = Field(default_factory=dict)


class StructuredResultPolishBundle(BaseModel):
    primary_judgment: str
    template_judgment: str = ""
    structural_judgment: str = ""
    narrative_axis: str = ""
    feature_signal_mode: str = ""
    audience: str = "manager"
    delivery_mode: str = "client_report"
    use_ai_rewrite: bool = False
    original_result: dict[str, Any]
    polished_sections: list[PolishedSection] = Field(default_factory=list)
    preserved_facts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConsultingMinContract(BaseModel):
    as_is: list[str] = Field(default_factory=list)
    process_flow: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    gap: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    problem_definition: list[str] = Field(default_factory=list)
    decision_question: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    decision_criteria: list[str] = Field(default_factory=list)
    conclusion: list[str] = Field(default_factory=list)
    key_reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class ConsultingDeckSection(BaseModel):
    section_key: str
    title: str
    items: list[str] = Field(default_factory=list)
    uses_placeholder: bool = False


class ConsultingDeckChapter(BaseModel):
    chapter_key: str
    title: str
    sections: list[ConsultingDeckSection] = Field(default_factory=list)


class ConsultingDeck(BaseModel):
    project_name: str = ""
    client_name: str = ""
    surface_mode: Literal["internal", "external"] = "internal"
    information_role: str = ""
    role_label: str = ""
    role_description: str = ""
    role_header: str = ""
    chapters: list[ConsultingDeckChapter] = Field(default_factory=list)


class SlideStep(BaseModel):
    step_label: str
    step_text: str


class SlideRuleCard(BaseModel):
    title: str
    body: str


class SlideSchema(BaseModel):
    slide_id: str
    slide_type: Literal["overview", "as_is_gap", "flow", "design", "vision"]
    chapter_key: Literal["overview", "approach", "implementation", "design", "vision"]
    title: str
    headline: str = ""
    source_refs: list[str] = Field(default_factory=list)
    layout_hint: str = ""
    sequence: int = 1
    is_continuation: bool = False
    continuation_of: str = ""
    continuation_reason: str = ""
    continuation_value: Literal["not_applicable", "retain", "absorb_candidate"] = "not_applicable"
    continuation_value_score: int = 0
    absorbed_summary_text: str = ""
    density_tier: Literal["light", "balanced", "dense"] = "balanced"
    max_text_objects: int = 6
    context_bullets: list[str] = Field(default_factory=list)
    scope_bullets: list[str] = Field(default_factory=list)
    constraint_bullets: list[str] = Field(default_factory=list)
    tagline: str = ""
    as_is_bullets: list[str] = Field(default_factory=list)
    gap_bullets: list[str] = Field(default_factory=list)
    to_be_bullets: list[str] = Field(default_factory=list)
    risk_bullets: list[str] = Field(default_factory=list)
    decision_message: str = ""
    steps: list[SlideStep] = Field(default_factory=list)
    action_bullets: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    footer_note: str = ""
    rule_cards: list[SlideRuleCard] = Field(default_factory=list)
    flow_bullets: list[str] = Field(default_factory=list)
    entity_blocks: list[str] = Field(default_factory=list)
    interface_points: list[str] = Field(default_factory=list)
    future_state_bullets: list[str] = Field(default_factory=list)
    effect_bullets: list[str] = Field(default_factory=list)
    closing_statement: str = ""


class SlideSchemaDeck(BaseModel):
    schema_version: str = "slide_schema.v1"
    project_name: str = ""
    client_name: str = ""
    surface_mode: Literal["internal", "external"] = "internal"
    slides: list[SlideSchema] = Field(default_factory=list)
