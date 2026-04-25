from __future__ import annotations

from .bundle_builder import SafeBundleBuilder
from .document_tokenizer import DocumentEntityTokenizer
from .export_service import ExportService
from .mapper import IdentifierMapper
from .masking_policy import MaskingPolicyApplier
from .review_report import build_anonymization_review_artifacts
from .schemas import AnonymizationRunRequest, AnonymizationRunResult
from .storage import AnonymizationStorage
from .structure_extractor import CanonicalStructureExtractor
from .tokenizer import IdentifierTokenizer


class AnonymizationService:
    """Facade that orchestrates anonymization components without owning their logic."""

    def __init__(
        self,
        *,
        storage: AnonymizationStorage | None = None,
        tokenizer: IdentifierTokenizer | None = None,
        document_tokenizer: DocumentEntityTokenizer | None = None,
        mapper: IdentifierMapper | None = None,
        structure_extractor: CanonicalStructureExtractor | None = None,
        masking_policy: MaskingPolicyApplier | None = None,
        bundle_builder: SafeBundleBuilder | None = None,
        export_service: ExportService | None = None,
    ) -> None:
        self.storage = storage or AnonymizationStorage()
        self.tokenizer = tokenizer or IdentifierTokenizer()
        self.document_tokenizer = document_tokenizer or DocumentEntityTokenizer()
        self.mapper = mapper or IdentifierMapper()
        self.structure_extractor = structure_extractor or CanonicalStructureExtractor()
        self.masking_policy = masking_policy or MaskingPolicyApplier()
        self.bundle_builder = bundle_builder or SafeBundleBuilder()
        self.export_service = export_service or ExportService()

    def run_anonymization_pipeline(self, request: AnonymizationRunRequest) -> AnonymizationRunResult:
        canonical_sources = []
        structures = []
        tokens_by_asset: dict[str, list] = {}
        for asset in request.assets:
            self.storage.store_original(project_id=request.project_id, asset=asset, content=asset.original_bytes)
            tokens = self._merge_tokens(
                self.document_tokenizer.tokenize(asset),
                self.tokenizer.tokenize(asset),
            )
            tokens_by_asset[asset.asset_id] = list(tokens)
            mapping = self.mapper.build_mapping(asset, tokens)
            canonical = self.mapper.apply_mapping(asset=asset, mapping=mapping)
            self.storage.store_mapping_internal(project_id=request.project_id, asset_id=asset.asset_id, mapping=mapping)
            self.storage.store_canonical(project_id=request.project_id, canonical=canonical)
            structure = self.structure_extractor.extract(canonical)
            self.storage.store_structure(project_id=request.project_id, structure=structure)
            canonical_sources.append(canonical)
            structures.append(structure)

        review_artifacts = build_anonymization_review_artifacts(
            assets=request.assets,
            safe_bundle=self.bundle_builder.build(
                project_id=request.project_id,
                masking_level=request.masking_level,
                assets=request.assets,
                canonical_sources=canonical_sources,
                structures=structures,
            ),
            canonical_sources=canonical_sources,
            tokens_by_asset=tokens_by_asset,
            document_tokenizer=self.document_tokenizer,
        )
        safe_bundle = self.bundle_builder.build(
            project_id=request.project_id,
            masking_level=request.masking_level,
            assets=request.assets,
            canonical_sources=review_artifacts.llm_safe_sources,
            structures=structures,
        )
        public_exports = self.export_service.build_public_exports(
            canonical_sources=canonical_sources,
            structures=structures,
            visibility_policy=request.export_visibility_policy,
            masking_policy=self.masking_policy,
        )
        for level, payload in public_exports.items():
            self.storage.store_export(project_id=request.project_id, level=level, payload=payload.model_dump(by_alias=True))

        return AnonymizationRunResult(
            project_id=request.project_id,
            bundle_id=safe_bundle.bundle_id,
            masking_level=request.masking_level,
            safe_bundle=safe_bundle,
            available_export_levels=list(public_exports.keys()),
            canonical_source_count=len(canonical_sources),
            structure_count=len(structures),
            review_report=review_artifacts.review_report,
        )

    @staticmethod
    def _merge_tokens(*token_groups: list) -> list:
        merged = []
        seen_values: set[str] = set()
        for token_group in token_groups:
            for token in token_group:
                value = str(getattr(token, "value", "") or "").strip()
                if not value or value in seen_values:
                    continue
                seen_values.add(value)
                merged.append(token)
        return merged
