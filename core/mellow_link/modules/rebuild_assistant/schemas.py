from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mellow_link.services.anonymization.schemas import SafeAnalysisBundle


class RebuildAssetsPayload(BaseModel):
    source_code: str = ""
    database_schema: str = ""
    sql_queries: str = ""
    ui_template: str = ""
    framework_info: str = ""

    def has_any_content(self) -> bool:
        return any(
            bool((value or "").strip())
            for value in (
                self.source_code,
                self.database_schema,
                self.sql_queries,
                self.ui_template,
                self.framework_info,
            )
        )


class AssetPresenceSummary(BaseModel):
    has_source_code: bool = False
    has_ui_asset: bool = False
    has_schema_asset: bool = False
    has_sql_asset: bool = False
    has_framework_hint: bool = False
    has_docs: bool = False
    framework_runtime_hints: list[str] = Field(default_factory=list)
    source_asset_names: list[str] = Field(default_factory=list)
    ui_asset_names: list[str] = Field(default_factory=list)
    schema_asset_names: list[str] = Field(default_factory=list)
    sql_asset_names: list[str] = Field(default_factory=list)
    framework_asset_names: list[str] = Field(default_factory=list)
    doc_asset_names: list[str] = Field(default_factory=list)


class LayeredListResult(BaseModel):
    database: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)


class StatusPermissionsRules(BaseModel):
    entities: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    role_action_matrix: list[dict] = Field(default_factory=list)
    status_action_matrix: list[dict] = Field(default_factory=list)
    transition_rules: list[dict] = Field(default_factory=list)
    ui_visibility_rules: list[str] = Field(default_factory=list)
    policy_hints: list[str] = Field(default_factory=list)


class SearchFilterRules(BaseModel):
    entities: list[str] = Field(default_factory=list)
    filter_fields: list[dict] = Field(default_factory=list)
    query_params: list[str] = Field(default_factory=list)
    sort_rules: list[dict] = Field(default_factory=list)
    paging_rules: list[dict] = Field(default_factory=list)
    query_binding_rules: list[str] = Field(default_factory=list)
    default_filters: list[str] = Field(default_factory=list)
    result_shape_hints: list[str] = Field(default_factory=list)


class SaveValidationRules(BaseModel):
    entities: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    field_validation_rules: list[str] = Field(default_factory=list)
    duplicate_check_rules: list[str] = Field(default_factory=list)
    save_guard_rules: list[str] = Field(default_factory=list)
    exception_rules: list[str] = Field(default_factory=list)
    command_boundary_hints: list[str] = Field(default_factory=list)


class ExtractedRulesEnvelope(BaseModel):
    status_permissions: StatusPermissionsRules = Field(default_factory=StatusPermissionsRules)
    search_filters: SearchFilterRules = Field(default_factory=SearchFilterRules)
    save_validation: SaveValidationRules = Field(default_factory=SaveValidationRules)


class MissingContextItem(BaseModel):
    required_material: str
    reason: str


class CompanyRuleProfile(BaseModel):
    profile_name: str = "default_placeholder"
    enabled: bool = False
    rule_sources: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    asset_name: str
    asset_type: str
    locator: str
    excerpt: str
    evidence_kind: str


class GroundedBusinessRule(BaseModel):
    title: str
    description: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    design_targets: list[str] = Field(default_factory=list)
    confidence: str = "가정"
    confidence_reason: str = ""
    needs_verification: bool = True


class DecisionItem(BaseModel):
    statement: str
    rationale: str
    linked_evidence: list[EvidenceRef] = Field(default_factory=list)
    linked_risks: list[str] = Field(default_factory=list)


class RetainedContract(BaseModel):
    item: str
    basis: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AppliedJudgmentTemplate(BaseModel):
    template_id: str
    score: float = 0.0
    matched_signal_types: list[str] = Field(default_factory=list)
    matched_rule_titles: list[str] = Field(default_factory=list)
    matched_contract_items: list[str] = Field(default_factory=list)
    core_questions: list[str] = Field(default_factory=list)


class PatternCandidate(BaseModel):
    name: str
    matched: bool = False
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    rejected_reason: str = ""


class PrioritySplitItem(BaseModel):
    priority: int
    item: str = ""
    title: str
    reason: str
    impact_scope: str
    prerequisite: str
    linked_rules: list[str] = Field(default_factory=list)
    linked_contracts: list[str] = Field(default_factory=list)


class VerificationItem(BaseModel):
    item: str
    reason: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class DesignOption(BaseModel):
    name: str
    structure_summary: str
    advantages: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    difficulty: str = "MEDIUM"
    duration_weeks: int = 0
    recommended: bool = False
    selection_reason: str = ""


class RecommendedOption(BaseModel):
    name: str
    structure_summary: str
    selection_reason: str
    expected_outcomes: list[str] = Field(default_factory=list)


class ExecutionPlanWeek(BaseModel):
    week_label: str
    goal: str
    tasks: list[str] = Field(default_factory=list)
    related_rules: list[str] = Field(default_factory=list)
    related_contracts: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    duration_weeks: int = 1
    deliverables: list[str] = Field(default_factory=list)


class CanonicalRequestContext(BaseModel):
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    scope_limited: bool = False


class CanonicalFunctionClassification(BaseModel):
    primary_judgment: str = ""
    template_judgment: str = ""
    structural_judgment: str = ""
    narrative_axis: str = ""
    feature_signal_mode: str = ""
    pattern_candidates: list[PatternCandidate] = Field(default_factory=list)


class CanonicalRebuildPayload(BaseModel):
    request_context: CanonicalRequestContext = Field(default_factory=CanonicalRequestContext)
    function_classification: CanonicalFunctionClassification = Field(default_factory=CanonicalFunctionClassification)
    structure_snapshot: dict[str, Any] = Field(default_factory=dict)
    diagnosis_report: dict[str, Any] = Field(default_factory=dict)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    analysis_summary: list[str] = Field(default_factory=list)
    core_business_rules: list[str] = Field(default_factory=list)
    grounded_business_rules: list[GroundedBusinessRule] = Field(default_factory=list)
    decision_items: list[DecisionItem] = Field(default_factory=list)
    retained_contracts: list[RetainedContract] = Field(default_factory=list)
    design_options: list[DesignOption] = Field(default_factory=list)
    recommended_option: RecommendedOption | None = None
    execution_plan: list[ExecutionPlanWeek] = Field(default_factory=list)
    recommended_directions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_context_details: list[MissingContextItem] = Field(default_factory=list)
    appendix: dict[str, Any] = Field(default_factory=dict)


class InputFamilyClassification(BaseModel):
    family: str = ""
    confidence: float = 0.0
    decision_basis: list[str] = Field(default_factory=list)
    secondary_signals: list[str] = Field(default_factory=list)
    display_strategy: str = ""
    internal_strategy: str = ""

    @field_validator("family")
    @classmethod
    def validate_family(cls, value: str) -> str:
        normalized = (value or "").strip()
        allowed = {
            "",
            "operational_source",
            "redesign_review",
            "migration_transition",
            "document_consulting",
            "option_comparison",
        }
        if normalized not in allowed:
            raise ValueError("unsupported family")
        return normalized

    @field_validator("secondary_signals")
    @classmethod
    def validate_secondary_signals(cls, value: list[str]) -> list[str]:
        allowed = {
            "operational_source",
            "redesign_review",
            "migration_transition",
            "document_consulting",
            "option_comparison",
        }
        normalized: list[str] = []
        for item in value or []:
            candidate = str(item or "").strip()
            if not candidate:
                continue
            if candidate not in allowed:
                raise ValueError("unsupported secondary family")
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = 0.0
        return max(0.0, min(1.0, numeric))


class StructuredRebuildResult(BaseModel):
    context_id: str = ""
    input_fingerprint: str = ""
    safe_bundle_id: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    primary_judgment: str = ""
    template_judgment: str = ""
    structural_judgment: str = ""
    narrative_axis: str = ""
    feature_signal_mode: str = ""
    primary_judgment_reason: str = ""
    pattern_candidates: list[PatternCandidate] = Field(default_factory=list)
    report_purpose: str = ""
    report_scope: list[str] = Field(default_factory=list)
    report_questions: list[str] = Field(default_factory=list)
    one_line_conclusion: str = ""
    core_business_rules: list[str] = Field(default_factory=list)
    executive_summary_v2: list[str] = Field(default_factory=list)
    grounded_business_rules: list[GroundedBusinessRule] = Field(default_factory=list)
    decision_items: list[DecisionItem] = Field(default_factory=list)
    retained_contracts: list[RetainedContract] = Field(default_factory=list)
    priority_split_items: list[PrioritySplitItem] = Field(default_factory=list)
    verification_checkpoints: list[VerificationItem] = Field(default_factory=list)
    design_options: list[DesignOption] = Field(default_factory=list)
    recommended_option: RecommendedOption | None = None
    execution_plan: list[ExecutionPlanWeek] = Field(default_factory=list)
    analysis_summary: list[str] = Field(default_factory=list)
    rebuild_strategy: list[str] = Field(default_factory=list)
    layer_reconstruction: LayeredListResult = Field(default_factory=LayeredListResult)
    recomposition_draft: LayeredListResult = Field(default_factory=LayeredListResult)
    risks: list[str] = Field(default_factory=list)
    extracted_rules: ExtractedRulesEnvelope = Field(default_factory=ExtractedRulesEnvelope)
    recommended_directions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    missing_context: list[str] = Field(default_factory=list)
    missing_context_details: list[MissingContextItem] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)
    structure_snapshot: dict[str, Any] = Field(default_factory=dict)
    diagnosis_report: dict[str, Any] = Field(default_factory=dict)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    improvement_plan_bundle: dict[str, Any] = Field(default_factory=dict)
    appendix: dict[str, Any] = Field(default_factory=dict)
    canonical_payload: CanonicalRebuildPayload | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = 0.0
        return max(0.0, min(1.0, numeric))


class RebuildAssistantStartResponse(BaseModel):
    run_id: str
    session_id: str
    module_id: str = "rebuild_assistant"
    run_kind: str = "rebuild_plan"


class RebuildAssistantBundleRequest(BaseModel):
    goal: str = Field(..., description="Single feature/page legacy reconstruction goal")
    safe_bundle: SafeAnalysisBundle
    constraints: list[str] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        stripped = (value or "").strip()
        if len(stripped) < 8:
            raise ValueError("goal must be at least 8 characters after trimming")
        return stripped


class ProjectAssetItem(BaseModel):
    name: str
    temp_file_id: str
    size: int = 0
    category_hint: str = ""

    @field_validator("name", "temp_file_id")
    @classmethod
    def validate_asset_strings(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("asset field cannot be blank")
        return stripped


class ProjectStartRequest(BaseModel):
    project_name: str = Field(..., description="Commercial modernization project name")
    client_name: str = Field(..., description="Customer or account name")
    upload_session_id: str = Field(..., description="Temp upload session ID")
    asset_manifest: list[ProjectAssetItem] = Field(default_factory=list)
    template_key: str = Field("default_modernization_v1")
    constraints: list[str] = Field(default_factory=list)

    @field_validator("project_name", "client_name", "upload_session_id", "template_key")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("required field cannot be blank")
        return stripped

    @field_validator("constraints")
    @classmethod
    def normalize_constraints(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in (value or []) if (item or "").strip()]


class ProjectStartResponse(BaseModel):
    project_id: str
    run_id: str
    session_id: str
    status: str = "running"
    warnings: list[str] = Field(default_factory=list)


class ProjectReanalysisRequest(BaseModel):
    new_asset_manifest: list[ProjectAssetItem] = Field(default_factory=list)


class ProjectReanalysisResponse(BaseModel):
    project_id: str
    run_id: str
    session_id: str
    status: str = "running"
    promoted_asset_count: int = 0
    latest_asset_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ResultCitation(BaseModel):
    decision_id: str | None = None
    issue_id: str | None = None
    evidence_id: str | None = None
    stage_id: str | None = None
    locator: str = ""
    excerpt: str = ""


class ResultExplanationSummaryCard(BaseModel):
    card_key: str
    title: str
    body: str
    citations: list[ResultCitation] = Field(default_factory=list)


class ResultExplanationSectionView(BaseModel):
    section_key: str
    title: str
    audience: Literal["developer", "manager", "client"] = "manager"
    text: str
    citations: list[ResultCitation] = Field(default_factory=list)


class ResultExplanationCoreJudgmentView(BaseModel):
    structural_judgment: str = ""
    recommended_strategy: str = ""
    top_decision_type: str = ""


class ResultExplanationEvidenceView(BaseModel):
    top_priority_score: int | None = None
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    explainability: dict[str, Any] = Field(default_factory=dict)
    citations: list[ResultCitation] = Field(default_factory=list)


class ResultExplanationContextView(BaseModel):
    narrative_axis: str = ""


class ResultExplanationTaxonomyView(BaseModel):
    core_judgment: ResultExplanationCoreJudgmentView = Field(default_factory=ResultExplanationCoreJudgmentView)
    evidence_view: ResultExplanationEvidenceView = Field(default_factory=ResultExplanationEvidenceView)
    explanation_context: ResultExplanationContextView = Field(default_factory=ResultExplanationContextView)


class ResultExplanationReviewDiffPreview(BaseModel):
    available: bool = False
    structural_signals: list[str] = Field(default_factory=list)
    evidence_signals: list[str] = Field(default_factory=list)
    blocked_decisions: list[str] = Field(default_factory=list)
    synthetic_signal_detected: bool = False
    decision_engine_guard_applied: bool = False
    result_packager_guard_applied: bool = False


class ResultExplanationResponse(BaseModel):
    project_id: str
    audience: Literal["developer", "manager", "client"] = "manager"
    surface_mode: Literal["internal", "external"] = "internal"
    taxonomy_view: ResultExplanationTaxonomyView = Field(default_factory=ResultExplanationTaxonomyView)
    review_diff_preview: ResultExplanationReviewDiffPreview = Field(default_factory=ResultExplanationReviewDiffPreview)
    summary_cards: list[ResultExplanationSummaryCard] = Field(default_factory=list)
    section_views: list[ResultExplanationSectionView] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ResultQARequest(BaseModel):
    question: str
    audience: Literal["developer", "manager", "client"] = "manager"

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped


class ResultQAResponse(BaseModel):
    answer: str
    answer_mode: Literal["deterministic", "ai_grounded"] = "deterministic"
    citations: list[ResultCitation] = Field(default_factory=list)
    referenced_sections: list[str] = Field(default_factory=list)
    insufficient_grounding: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)
