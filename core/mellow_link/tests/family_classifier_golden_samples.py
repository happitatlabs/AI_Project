from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyClassifierGoldenExpectation:
    sample_name: str
    expected_family: str
    expected_secondary_signals: tuple[str, ...]
    expected_display_strategy: str
    expected_internal_strategy: str


FAMILY_CLASSIFIER_GOLDEN_EXPECTATIONS: tuple[FamilyClassifierGoldenExpectation, ...] = (
    FamilyClassifierGoldenExpectation(
        sample_name="12_operational_redesign_boundary",
        expected_family="operational_source",
        expected_secondary_signals=("redesign_review",),
        expected_display_strategy="현행 분석 우선",
        expected_internal_strategy="리팩터링 우선",
    ),
    FamilyClassifierGoldenExpectation(
        sample_name="13_document_option_boundary",
        expected_family="option_comparison",
        expected_secondary_signals=("document_consulting",),
        expected_display_strategy="비교 기준 우선",
        expected_internal_strategy="옵션 비교",
    ),
)
