from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MaskingLevel(str, Enum):
    """Representation level for anonymized artifacts."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    FULL_MASKED = "FULL_MASKED"


class ExportVisibilityPolicy(BaseModel):
    """Public download visibility separated from masking level semantics."""

    allow_full_download: bool = False
    allow_partial_download: bool = True
    allow_full_masked_download: bool = True


class IdentifierToken(BaseModel):
    kind: str
    value: str


class AnonymizationAsset(BaseModel):
    """Internal asset contract. Raw bytes/text are excluded from serialization."""

    asset_id: str
    name: str
    temp_file_id: str
    size: int = 0
    kind_hint: str = ""
    language: str = ""
    content_text: str = Field(default="", exclude=True, repr=False)
    original_bytes: bytes = Field(default=b"", exclude=True, repr=False)

    @field_validator("asset_id", "name", "temp_file_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("asset fields cannot be blank")
        return stripped


class CanonicalAnonymizedSource(BaseModel):
    asset_id: str
    level: MaskingLevel = MaskingLevel.FULL
    language: str = ""
    source_type: str = "canonical_anonymized"
    content: str = ""
    replacement_stats: dict[str, int] = Field(default_factory=dict)


class StructureNode(BaseModel):
    kind: str
    id: str


class StructureEdge(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    type: str

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)


class StructureArtifact(BaseModel):
    asset_id: str
    level: MaskingLevel = MaskingLevel.FULL
    extracted_from: str = "canonical"
    nodes: list[StructureNode] = Field(default_factory=list)
    edges: list[StructureEdge] = Field(default_factory=list)


class SafeBundleGuard(BaseModel):
    contains_original: bool = False
    contains_mapping: bool = False
    canonical_only: bool = True
    structure_extracted_from_canonical: bool = True


class BundleAssetSummary(BaseModel):
    asset_id: str
    name: str
    temp_file_id: str
    size: int = 0
    kind_hint: str = ""
    language: str = ""


class SafeAnalysisBundle(BaseModel):
    bundle_id: str
    project_id: str
    masking_level: MaskingLevel = MaskingLevel.FULL
    asset_summary: list[BundleAssetSummary] = Field(default_factory=list)
    sources: list[CanonicalAnonymizedSource] = Field(default_factory=list)
    structures: list[StructureArtifact] = Field(default_factory=list)
    guard: SafeBundleGuard = Field(default_factory=SafeBundleGuard)


class AnonymizationRunRequest(BaseModel):
    project_id: str
    upload_session_id: str = ""
    masking_level: MaskingLevel = MaskingLevel.FULL
    assets: list[AnonymizationAsset] = Field(default_factory=list)
    export_visibility_policy: ExportVisibilityPolicy = Field(default_factory=ExportVisibilityPolicy)


class ReviewRoleTokenSummary(BaseModel):
    role_kind: str
    token_prefix: str
    label: str
    generated_count: int = 0


class ReviewDetectedType(BaseModel):
    type_key: str
    label: str
    count: int = 0
    source: Literal["document_role_token"] = "document_role_token"


class ReviewEntityCandidate(BaseModel):
    severity: Literal["risk", "warning"]
    entity_type_guess: str
    label: str
    asset_id: str
    asset_name: str = ""
    locator: str
    reason: str
    masked_preview: str


class ReviewDebugCandidateEvidence(BaseModel):
    severity: Literal["risk", "warning"]
    entity_type_guess: str
    asset_id: str
    asset_name: str = ""
    locator: str
    reason: str
    raw_value: str = Field(default="", exclude=True, repr=False)
    source_line: str = Field(default="", exclude=True, repr=False)


class ReviewStructureCheck(BaseModel):
    severity: Literal["ok", "warning", "risk"]
    code: str
    message: str
    asset_id: str = ""
    asset_name: str = ""


class ReviewAssetPreview(BaseModel):
    asset_id: str
    asset_name: str = ""
    preview_text: str
    role_token_count: int = 0
    risk_count: int = 0
    warning_count: int = 0


class AnonymizationReviewReport(BaseModel):
    applied: bool = False
    status: Literal["ready", "review_required", "blocked"] = "ready"
    llm_send_allowed: bool = True
    masking_level: MaskingLevel = MaskingLevel.FULL
    target_asset_count: int = 0
    role_token_summary: list[ReviewRoleTokenSummary] = Field(default_factory=list)
    detected_original_types: list[ReviewDetectedType] = Field(default_factory=list)
    label_less_risks: list[ReviewEntityCandidate] = Field(default_factory=list)
    label_less_warnings: list[ReviewEntityCandidate] = Field(default_factory=list)
    structure_checks: list[ReviewStructureCheck] = Field(default_factory=list)
    asset_previews: list[ReviewAssetPreview] = Field(default_factory=list)
    preview_quality_status: Literal["pass", "warning", "fail"] = "pass"
    replacement_ratio: float = 0.0
    candidate_density: float = 0.0
    hidden_line_ratio: float = 0.0
    overredaction_warnings: list[str] = Field(default_factory=list)
    low_conf_replacements_blocked: int = 0
    debug_candidate_evidence: list[ReviewDebugCandidateEvidence] = Field(default_factory=list, exclude=True, repr=False)


class AnonymizationRunResult(BaseModel):
    project_id: str
    bundle_id: str
    masking_level: MaskingLevel = MaskingLevel.FULL
    status: str = "completed"
    safe_bundle: SafeAnalysisBundle
    available_export_levels: list[MaskingLevel] = Field(default_factory=list)
    canonical_source_count: int = 0
    structure_count: int = 0
    review_report: AnonymizationReviewReport | None = None


class PublicExportSource(BaseModel):
    """The only externally shareable source schema for anonymization exports."""

    asset_id: str
    level: MaskingLevel
    language: str = ""
    source_type: str
    content: str = ""
    replacement_stats: dict[str, int] = Field(default_factory=dict)


class PublicExportStructure(BaseModel):
    """The only externally shareable structure schema for anonymization exports."""

    asset_id: str
    level: MaskingLevel
    extracted_from: str = "canonical"
    nodes: list[StructureNode] = Field(default_factory=list)
    edges: list[StructureEdge] = Field(default_factory=list)


class PublicExportBundle(BaseModel):
    """The only externally shareable export bundle schema for API/file responses."""

    level: MaskingLevel
    sources: list[PublicExportSource] = Field(default_factory=list)
    structures: list[PublicExportStructure] = Field(default_factory=list)
