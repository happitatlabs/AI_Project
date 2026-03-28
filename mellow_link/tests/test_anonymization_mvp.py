from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.anonymization.bundle_builder import SafeBundleBuilder
from mellow_link.services.anonymization.export_service import ExportService
from mellow_link.services.anonymization.masking_levels import default_export_visibility_policy, is_publicly_visible
from mellow_link.services.anonymization.masking_policy import MaskingPolicyApplier
from mellow_link.services.anonymization.schemas import (
    AnonymizationAsset,
    CanonicalAnonymizedSource,
    MaskingLevel,
    PublicExportBundle,
    StructureArtifact,
)
from mellow_link.services.anonymization.structure_extractor import CanonicalStructureExtractor


def test_structure_extractor_requires_canonical_source_only():
    extractor = CanonicalStructureExtractor()

    try:
        extractor.extract("raw-source")  # type: ignore[arg-type]
    except TypeError as exc:
        assert "CanonicalAnonymizedSource" in str(exc)
    else:
        raise AssertionError("raw source input must be rejected")


def test_rebuild_assistant_safe_bundle_path_uses_safe_bundle_only():
    service = RebuildAssistantService()
    bundle = SafeBundleBuilder().build(
        project_id="proj_safe_only",
        masking_level=MaskingLevel.FULL,
        assets=[
            AnonymizationAsset(
                asset_id="asset_001",
                name="legacy.jsp",
                temp_file_id="temp_001",
                size=12,
            )
        ],
        canonical_sources=[
            CanonicalAnonymizedSource(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                content="class CLS_001 { function FUNC_001() {} }",
            )
        ],
        structures=[
            StructureArtifact(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                extracted_from="canonical",
                nodes=[],
                edges=[],
            )
        ],
    )

    prepared = service.prepare_safe_bundle_input(
        goal="legacy modernized screen",
        safe_bundle=bundle,
        constraints=["safe_bundle_only"],
    )
    assert "safe_bundle_id=" in prepared.constraints[1]
    assert "CLS_001" in (prepared.assets.source_code + prepared.assets.ui_template)
    assert prepared.temp_context == ""


def test_safe_bundle_excludes_original_and_mapping_fields():
    bundle = SafeBundleBuilder().build(
        project_id="proj_bundle_guard",
        masking_level=MaskingLevel.FULL,
        assets=[
            AnonymizationAsset(
                asset_id="asset_001",
                name="legacy.sql",
                temp_file_id="temp_001",
                size=100,
                content_text="SELECT * FROM orders",
                original_bytes=b"SELECT * FROM orders",
            )
        ],
        canonical_sources=[
            CanonicalAnonymizedSource(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                content="SELECT * FROM TBL_001",
            )
        ],
        structures=[],
    )

    dumped = bundle.model_dump()
    assert bundle.guard.contains_original is False
    assert bundle.guard.contains_mapping is False
    assert "original_bytes" not in str(dumped)
    assert "mapping.json" not in str(dumped)
    assert "OrderController" not in str(dumped)


def test_bundle_asset_summary_has_no_raw_fields():
    bundle = SafeBundleBuilder().build(
        project_id="proj_bundle_summary",
        masking_level=MaskingLevel.FULL,
        assets=[
            AnonymizationAsset(
                asset_id="asset_001",
                name="legacy.sql",
                temp_file_id="temp_001",
                size=100,
                content_text="SELECT * FROM orders",
                original_bytes=b"SELECT * FROM orders",
            )
        ],
        canonical_sources=[],
        structures=[],
    )

    summary = bundle.model_dump()["asset_summary"][0]
    assert set(summary.keys()) == {"asset_id", "name", "temp_file_id", "size", "kind_hint", "language"}
    assert "content_text" not in summary
    assert "original_bytes" not in summary


def test_full_export_is_not_public_by_default():
    policy = default_export_visibility_policy()

    assert is_publicly_visible(MaskingLevel.FULL, policy) is False
    assert is_publicly_visible(MaskingLevel.PARTIAL, policy) is True
    assert is_publicly_visible(MaskingLevel.FULL_MASKED, policy) is True


def test_public_export_strips_forbidden_fields():
    exports = ExportService().build_public_exports(
        canonical_sources=[
            CanonicalAnonymizedSource(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                content="SELECT * FROM TBL_001",
                replacement_stats={"table": 1},
            )
        ],
        structures=[
            StructureArtifact(
                asset_id="asset_001",
                level=MaskingLevel.FULL,
                extracted_from="canonical",
                nodes=[],
                edges=[],
            )
        ],
        visibility_policy=default_export_visibility_policy(),
        masking_policy=MaskingPolicyApplier(),
    )

    assert all(isinstance(bundle, PublicExportBundle) for bundle in exports.values())
    for payload in exports.values():
        dumped = str(payload.model_dump())
        assert "original_bytes" not in dumped
        assert "content_text" not in dumped
        assert "mapping_path" not in dumped
        assert "original_path" not in dumped
