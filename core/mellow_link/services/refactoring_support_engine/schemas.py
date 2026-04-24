from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from mellow_link.modules.rebuild_assistant.schemas import (
    AppliedJudgmentTemplate,
    AssetPresenceSummary,
    DesignOption,
    DecisionItem,
    ExtractedRulesEnvelope,
    ExecutionPlanWeek,
    GroundedBusinessRule,
    InputFamilyClassification,
    LayeredListResult,
    MissingContextItem,
    PatternCandidate,
    PrioritySplitItem,
    RebuildAssetsPayload,
    RecommendedOption,
    RetainedContract,
    VerificationItem,
)
from mellow_link.services.anonymization.schemas import SafeAnalysisBundle, StructureArtifact


def stable_hash(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def make_stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{stable_hash(prefix, *parts)[:10].upper()}"


def normalize_fingerprint_text(text: str) -> str:
    normalized = (text or "").lower()
    normalized = re.sub(r'"(?:\\.|[^"])*"', '"STR"', normalized)
    normalized = re.sub(r"'(?:\\.|[^'])*'", "'STR'", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "NUM", normalized)
    normalized = re.sub(r"\s*([=!<>]+|\(|\)|,|\+|-|\*|/)\s*", r" \1 ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


@dataclass
class FeatureSignals:
    concepts: list[str] = field(default_factory=list)
    status_permissions: list[str] = field(default_factory=list)
    search_filters: list[str] = field(default_factory=list)
    save_validation: list[str] = field(default_factory=list)
    technical: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    primary_feature_mode: str = "general"
    secondary_feature_mode: str | None = None


class IntentInput(BaseModel):
    goal: str
    constraints: list[str] = Field(default_factory=list)
    scenario: str = ""
    sources: dict[str, str] = Field(default_factory=dict)


class AnalysisContextProject(BaseModel):
    project_id: str
    project_name: str = ""
    client_name: str = ""
    template_key: str = ""


class AnalysisContextAsset(BaseModel):
    asset_id: str
    name: str
    asset_type: str
    language: str = ""
    size: int = 0
    content_fingerprint: str
    masking_level: str = "FULL"


class AnalysisContextSourceBlock(BaseModel):
    block_id: str
    asset_id: str
    asset_name: str = ""
    asset_type: str = ""
    locator: str = ""
    excerpt: str = ""
    fingerprint: str = ""
    content: str = ""

    @field_validator("fingerprint", mode="before")
    @classmethod
    def default_fingerprint(cls, value: str, info) -> str:
        if value:
            return value
        content = ""
        if isinstance(info.data, dict):
            content = str(info.data.get("content") or info.data.get("excerpt") or "")
        return stable_hash(normalize_fingerprint_text(content))


class AnalysisContextEvidenceItem(BaseModel):
    evidence_id: str
    source_block_id: str
    asset_id: str
    locator: str = ""
    excerpt: str = ""
    claim: str = ""
    claim_type: Literal["observed", "inferred", "mapped"] = "observed"


class AnalysisFrame(BaseModel):
    family: str = ""
    family_confidence: float = 0.0
    question_axis: str = ""
    question_axis_confidence: float = 0.0
    primary_feature_mode: str = "general"
    primary_feature_mode_confidence: float = 0.0
    concept_signals: list[str] = Field(default_factory=list)
    scope_limited: bool = False


class AnalysisTrust(BaseModel):
    safe_bundle_id: str = ""
    masking_level: str = "FULL"
    missing_context: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisRun(BaseModel):
    run_id: str = ""
    input_fingerprint: str = ""
    policy_versions: dict[str, str] = Field(default_factory=dict)


class AnalysisContextBundle(BaseModel):
    context_id: str
    schema_version: str = "analysis_context_v1"
    project: AnalysisContextProject
    intent: IntentInput
    assets: list[AnalysisContextAsset] = Field(default_factory=list)
    source_blocks: list[AnalysisContextSourceBlock] = Field(default_factory=list)
    analysis_frame: AnalysisFrame = Field(default_factory=AnalysisFrame)
    evidence_index: list[AnalysisContextEvidenceItem] = Field(default_factory=list)
    trust: AnalysisTrust = Field(default_factory=AnalysisTrust)
    run: AnalysisRun = Field(default_factory=AnalysisRun)
    seed_structures: list[StructureArtifact] = Field(default_factory=list)


@dataclass
class PreparedRebuildInput:
    goal: str
    assets: RebuildAssetsPayload
    constraints: list[str]
    intent: IntentInput = field(default_factory=lambda: IntentInput(goal=""))
    asset_presence: AssetPresenceSummary = field(default_factory=AssetPresenceSummary)
    analysis_context: AnalysisContextBundle | None = None
    safe_bundle: SafeAnalysisBundle | None = None
    temp_context: str = ""
    supporting_docs: str = ""
    legacy_bundle: str = ""
    scope_limited: bool = False
    missing_context: list[str] | None = None
    signals: FeatureSignals = field(default_factory=FeatureSignals)
    selected_primary_judgment: str = ""
    selected_primary_judgment_reason: str = ""
    selected_narrative_judgment: str = ""
    question_axis: str = ""
    pattern_candidates: list[PatternCandidate] = field(default_factory=list)
    family_classification: InputFamilyClassification | None = None
    accounting_input: Any | None = None
    accounting_asset_name: str = ""
    accounting_input_error: str = ""

    def __post_init__(self) -> None:
        if not (self.intent.goal or self.intent.constraints or self.intent.scenario):
            self.intent = IntentInput(
                goal=self.goal,
                constraints=list(self.constraints or []),
                scenario=self.temp_context,
            )
        else:
            self.goal = self.intent.goal
            self.constraints = list(self.intent.constraints)
            self.temp_context = self.intent.scenario
        if self.missing_context is None:
            self.missing_context = []


class AssetInventoryItem(BaseModel):
    asset_id: str
    name: str
    asset_type: str
    size: int = 0
    language: str = ""
    kind_hint: str = ""


class SourceBlock(BaseModel):
    block_id: str
    asset_id: str
    asset_name: str
    asset_type: str
    locator: str = ""
    excerpt: str = ""
    content: str
    fingerprint: str = ""

    @field_validator("fingerprint", mode="before")
    @classmethod
    def default_fingerprint(cls, value: str, info) -> str:
        if value:
            return value
        content = ""
        if isinstance(info.data, dict):
            content = str(info.data.get("content") or "")
        return stable_hash(normalize_fingerprint_text(content))


class RefactoringAnalysisInput(BaseModel):
    analysis_scope: Literal["feature_slice"] = "feature_slice"
    goal: str
    constraints: list[str] = Field(default_factory=list)
    intent: IntentInput = Field(default_factory=lambda: IntentInput(goal=""))
    safe_bundle_id: str = ""
    safe_bundle: SafeAnalysisBundle | None = None
    asset_inventory: list[AssetInventoryItem] = Field(default_factory=list)
    source_blocks: list[SourceBlock] = Field(default_factory=list)
    seed_structures: list[StructureArtifact] = Field(default_factory=list)
    missing_context: list[MissingContextItem] = Field(default_factory=list)
    input_fingerprint: str = ""

    @field_validator("input_fingerprint", mode="before")
    @classmethod
    def build_fingerprint(cls, value: str, info) -> str:
        if value:
            return value
        if not isinstance(info.data, dict):
            return ""
        return stable_hash(
            [
                {
                    "asset_id": item.asset_id,
                    "name": item.name,
                    "asset_type": item.asset_type,
                    "fingerprint": stable_hash(item.name, item.asset_type),
                }
                for item in info.data.get("asset_inventory", [])
            ],
            [item.fingerprint for item in info.data.get("source_blocks", [])],
            [
                {
                    "asset_id": item.asset_id,
                    "node_count": len(item.nodes),
                    "edge_count": len(item.edges),
                }
                for item in info.data.get("seed_structures", [])
            ],
        )


class ComponentNode(BaseModel):
    component_id: str
    name: str
    component_type: str
    layer: str
    asset_ids: list[str] = Field(default_factory=list)
    responsibility_families: list[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    from_component: str
    to_component: str
    dependency_type: str


class LayerAssignment(BaseModel):
    component_id: str
    layer: str


class StructuralHotspot(BaseModel):
    component_id: str
    reasons: list[str] = Field(default_factory=list)
    score: int = 0


class CoverageSummary(BaseModel):
    asset_count: int = 0
    source_block_count: int = 0
    component_count: int = 0
    slice_count: int = 0
    missing_context_count: int = 0


class FunctionSlice(BaseModel):
    slice_id: str
    name: str
    entry_points: list[str] = Field(default_factory=list)
    related_components: list[str] = Field(default_factory=list)
    related_tables: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class StructureSnapshot(BaseModel):
    feature_slices: list[FunctionSlice] = Field(default_factory=list)
    components: list[ComponentNode] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    hotspots: list[StructuralHotspot] = Field(default_factory=list)
    layer_map: list[LayerAssignment] = Field(default_factory=list)
    coverage_summary: CoverageSummary = Field(default_factory=CoverageSummary)


class StructureAnalysisResult(BaseModel):
    analysis_input: RefactoringAnalysisInput
    structure_snapshot: StructureSnapshot
    seed_structures: list[StructureArtifact] = Field(default_factory=list)
    component_text_map: dict[str, str] = Field(default_factory=dict)
    component_asset_map: dict[str, str] = Field(default_factory=dict)
    component_layer_map: dict[str, str] = Field(default_factory=dict)
    component_responsibility_map: dict[str, list[str]] = Field(default_factory=dict)
    component_name_map: dict[str, str] = Field(default_factory=dict)
    slice_component_map: dict[str, list[str]] = Field(default_factory=dict)
    table_usage_map: dict[str, list[str]] = Field(default_factory=dict)


class EvidenceLink(BaseModel):
    evidence_id: str
    asset_id: str
    asset_name: str
    asset_type: str
    locator: str
    excerpt: str
    fingerprint: str


class StructuralIssue(BaseModel):
    issue_id: str
    detector_id: str
    category: str
    severity: int
    blast_radius: int
    effort: int
    summary: str
    affected_component_ids: list[str] = Field(default_factory=list)
    affected_slice_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class DetectorStat(BaseModel):
    detector_id: str
    issue_count: int = 0
    evidence_count: int = 0


class DiagnosisReport(BaseModel):
    issues: list[StructuralIssue] = Field(default_factory=list)
    coverage_summary: CoverageSummary = Field(default_factory=CoverageSummary)
    detector_stats: list[DetectorStat] = Field(default_factory=list)


class DiagnosisArtifacts(BaseModel):
    diagnosis_report: DiagnosisReport = Field(default_factory=DiagnosisReport)
    evidence_index: list[EvidenceLink] = Field(default_factory=list)
    extracted_rules: ExtractedRulesEnvelope = Field(default_factory=ExtractedRulesEnvelope)
    missing_context_details: list[MissingContextItem] = Field(default_factory=list)
    core_business_rules: list[str] = Field(default_factory=list)
    grounded_business_rules: list[GroundedBusinessRule] = Field(default_factory=list)
    retained_contracts: list[RetainedContract] = Field(default_factory=list)
    analysis_summary: list[str] = Field(default_factory=list)


class DecisionExplainability(BaseModel):
    decision_rule: str = ""
    score_formula: str = ""
    score_summary: str = ""
    evidence_count: int = 0
    affected_slice_count: int = 0


class DecisionRecord(BaseModel):
    decision_id: str
    issue_ids: list[str] = Field(default_factory=list)
    decision_type: Literal["refactor", "redesign", "migration_consideration"]
    target_component_ids: list[str] = Field(default_factory=list)
    priority_score: int = 0
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    explainability: DecisionExplainability = Field(default_factory=DecisionExplainability)
    rationale: str
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)


class DecisionSummary(BaseModel):
    decisions: list[DecisionRecord] = Field(default_factory=list)
    recommended_strategy: str = ""
    priority_queue: list[str] = Field(default_factory=list)


class DecisionArtifacts(BaseModel):
    decision_summary: DecisionSummary = Field(default_factory=DecisionSummary)
    applied_templates: list[AppliedJudgmentTemplate] = Field(default_factory=list)
    pattern_candidates: list[PatternCandidate] = Field(default_factory=list)
    family_classification: InputFamilyClassification = Field(default_factory=InputFamilyClassification)
    primary_judgment: str = ""
    template_judgment: str = ""
    structural_judgment: str = ""
    narrative_axis: str = ""
    feature_signal_mode: str = ""
    primary_judgment_reason: str = ""
    selected_narrative_judgment: str = ""
    decision_items: list[DecisionItem] = Field(default_factory=list)
    synthetic_signal_detected: bool = False


class RiskCheckpoint(BaseModel):
    checkpoint_id: str
    title: str
    description: str
    decision_ids: list[str] = Field(default_factory=list)


class ExecutionStage(BaseModel):
    stage_id: str
    title: str
    tasks: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    verification_checkpoint_ids: list[str] = Field(default_factory=list)
    risk_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class ImprovementPlanBundle(BaseModel):
    design_options: list[dict[str, Any]] = Field(default_factory=list)
    recommended_option: dict[str, Any] | None = None
    execution_stages: list[ExecutionStage] = Field(default_factory=list)
    risk_checkpoints: list[RiskCheckpoint] = Field(default_factory=list)


class ImprovementArtifacts(BaseModel):
    improvement_plan_bundle: ImprovementPlanBundle = Field(default_factory=ImprovementPlanBundle)
    priority_split_items: list[PrioritySplitItem] = Field(default_factory=list)
    verification_checkpoints: list[VerificationItem] = Field(default_factory=list)
    design_options: list[DesignOption] = Field(default_factory=list)
    recommended_option: RecommendedOption | None = None
    execution_plan: list[ExecutionPlanWeek] = Field(default_factory=list)
    rebuild_strategy: list[str] = Field(default_factory=list)
    layer_reconstruction: LayeredListResult = Field(default_factory=LayeredListResult)
    recomposition_draft: LayeredListResult = Field(default_factory=LayeredListResult)
    risks: list[str] = Field(default_factory=list)
    recommended_directions: list[str] = Field(default_factory=list)


class StructuredRefactoringResult(BaseModel):
    structure_snapshot: StructureSnapshot = Field(default_factory=StructureSnapshot)
    diagnosis_report: DiagnosisReport = Field(default_factory=DiagnosisReport)
    decision_summary: DecisionSummary = Field(default_factory=DecisionSummary)
    improvement_plan_bundle: ImprovementPlanBundle = Field(default_factory=ImprovementPlanBundle)
    appendix: dict[str, Any] = Field(default_factory=dict)
