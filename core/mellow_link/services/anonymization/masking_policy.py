from __future__ import annotations

import re

from .schemas import CanonicalAnonymizedSource, MaskingLevel, StructureArtifact, StructureEdge, StructureNode


class MaskingPolicyApplier:
    """Applies derived masking views to canonical anonymized artifacts."""

    def apply_source(self, canonical: CanonicalAnonymizedSource, level: MaskingLevel) -> CanonicalAnonymizedSource:
        if level == MaskingLevel.FULL:
            return canonical.model_copy(deep=True)
        if level == MaskingLevel.PARTIAL:
            return canonical.model_copy(update={"level": level, "source_type": "partial_anonymized"})
        masked = re.sub(r"\b(?:CLS|FUNC|TBL|COL|API)_\d{3}\b", "MASKED_NODE", canonical.content or "")
        return canonical.model_copy(update={"level": level, "source_type": "fully_masked", "content": masked})

    def apply_structure(self, structure: StructureArtifact, level: MaskingLevel) -> StructureArtifact:
        if level == MaskingLevel.FULL:
            return structure.model_copy(deep=True)
        if level == MaskingLevel.PARTIAL:
            return structure.model_copy(update={"level": level})

        remapped_nodes = [
            StructureNode(kind=node.kind, id=f"{node.kind.upper()}_{index + 1:03d}")
            for index, node in enumerate(structure.nodes)
        ]
        index_map = {node.id: remapped_nodes[idx].id for idx, node in enumerate(structure.nodes)}
        remapped_edges = [
            StructureEdge(
                **{
                    "from": index_map.get(edge.from_id, edge.from_id),
                    "to": index_map.get(edge.to_id, edge.to_id),
                    "type": edge.type,
                }
            )
            for edge in structure.edges
        ]
        return structure.model_copy(update={"level": level, "nodes": remapped_nodes, "edges": remapped_edges})
