from __future__ import annotations

from enum import Enum

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


class AnonymizationRunResult(BaseModel):
    project_id: str
    bundle_id: str
    masking_level: MaskingLevel = MaskingLevel.FULL
    status: str = "completed"
    safe_bundle: SafeAnalysisBundle
    available_export_levels: list[MaskingLevel] = Field(default_factory=list)
    canonical_source_count: int = 0
    structure_count: int = 0


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
