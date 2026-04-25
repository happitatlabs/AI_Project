from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import InputFamilyClassification

from .template_support import TemplateSupport


@dataclass
class _StageDecision:
    primary: str = ""
    secondary: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)


class FamilyClassifier:
    FAMILIES = (
        "operational_source",
        "redesign_review",
        "migration_transition",
        "document_consulting",
        "option_comparison",
    )
    FAMILY_ORDER = {family: index for index, family in enumerate(FAMILIES)}
    DISPLAY_STRATEGY_BY_FAMILY = {
        "redesign_review": "구조 문제 우선",
        "migration_transition": "전환 계획 우선",
        "document_consulting": "문서 구조화 우선",
        "option_comparison": "비교 기준 우선",
    }
    INTERNAL_STRATEGY_BY_FAMILY = {
        "operational_source": "리팩터링 우선",
        "redesign_review": "재설계 우선",
        "migration_transition": "마이그레이션 고려",
        "document_consulting": "문서 구조화",
        "option_comparison": "옵션 비교",
    }
    OPERATIONAL_ANALYSIS_TERMS = (
        "무엇을 하는",
        "무슨 프로그램",
        "어떻게 흐르",
        "처리 흐름",
        "데이터 흐름",
        "운영 로직",
        "현행 운영 로직",
        "회계 흐름",
        "흐름 복원",
        "로직 복원",
        "업무 규칙",
        "계산 규칙",
        "현행 동작",
        "운영 리스크",
        "정합성",
        "what does",
        "actual behavior",
        "data flow",
        "processing flow",
        "business rule",
        "calculation rule",
    )
    REDESIGN_TERMS = (
        "구조 문제",
        "책임 분리",
        "책임을 분리",
        "분리 방향",
        "분리해줘",
        "분리하라",
        "경계 재설정",
        "구조 개선",
        "재설계",
        "재구성",
        "새로 설계",
        "다시 설계",
        "서비스 구조",
        "현대적인 서비스 구조",
        "레이어",
        "모듈 분리",
        "유지보수",
        "responsibility",
        "boundary",
        "redesign",
        "re-architect",
        "module split",
        "maintainability",
    )
    STRONG_REDESIGN_TERMS = (
        "재설계",
        "책임 분리",
        "책임을 분리",
        "분리 방향",
        "분리해줘",
        "분리하라",
        "경계 재설정",
        "구조 개선",
        "서비스 구조",
        "현대적인 서비스 구조",
        "어떻게 나누",
        "왜 유지보수",
        "redesign",
        "re-architect",
        "how to split",
    )
    MIGRATION_TERMS = (
        "전환",
        "이관",
        "마이그레이션",
        "to-be",
        "as-is",
        "migrate",
        "migration",
        "transition",
        "cutover",
        "cloud",
    )
    OPTION_TERMS = (
        "비교",
        "선택",
        "추천",
        "어떤 안",
        "어떤게",
        "더 좋은",
        "장단점",
        "비교 기준",
        "compare",
        "tradeoff",
        "pros and cons",
        "which option",
    )
    DOCUMENT_TERMS = (
        "문서",
        "요약",
        "정리",
        "구조화",
        "설명",
        "제안서",
        "회의록",
        "설명서",
        "문서화",
        "summarize",
        "summary",
        "document",
        "explain",
    )
    MIXED_REVIEW_TERMS = ("같이", "함께", "also", "as well", "along with")
    MIGRATION_REQUEST_PATTERNS = (
        r"전환\s*(계획|전략|순서|단계|리스크)",
        r"전면\s*전환",
        r"\S+\s*로\s*전환",
        r"\S+\s*으로\s*전환",
        r"이관\s*(계획|전략|순서|단계|리스크)",
        r"마이그레이션\s*(계획|전략|순서|단계|리스크)",
        r"(as-is|asis)\s*/?\s*(to-be|tobe)",
        r"무엇을\s+어디로\s+옮기",
        r"어디로\s+옮기",
        r"migration\s*(plan|strategy|sequence|risk)",
        r"transition\s*(plan|strategy|sequence|risk)",
        r"what\s+to\s+migrate",
        r"cutover",
    )
    REDESIGN_DEPRIORITIZED_PATTERNS = (
        r"재설계[^.]{0,20}(보다|후순위|나중|아님)",
        r"redesign[^.]{0,20}(after|later|not first)",
    )

    def __init__(self, helper: TemplateSupport | None = None) -> None:
        self.helper = helper or TemplateSupport()

    def classify(
        self,
        prepared: Any,
        *,
        structure: Any | None = None,
        diagnosis: Any | None = None,
    ) -> InputFamilyClassification:
        del structure
        goal_decision = self._classify_explicit_goal(prepared)
        asset_decision = self._classify_asset_type(prepared)
        question_decision = self._classify_question_axis(prepared)
        evidence_decision = self._classify_dominant_evidence(prepared, diagnosis=diagnosis)
        ordered_stages = (
            ("goal", goal_decision),
            ("asset", asset_decision),
            ("question", question_decision),
            ("evidence", evidence_decision),
        )

        selected_stage = "conservative"
        selected_decision = _StageDecision()
        for stage_name, decision in ordered_stages:
            if decision.primary:
                selected_stage = stage_name
                selected_decision = decision
                break
        if not selected_decision.primary:
            fallback_family, fallback_basis = self._conservative_choice(
                prepared,
                asset_decision=asset_decision,
                question_decision=question_decision,
                evidence_decision=evidence_decision,
            )
            selected_decision = _StageDecision(primary=fallback_family, basis=fallback_basis)

        secondary_signals = self._collect_secondary_signals(
            selected_decision.primary,
            ordered_stages=ordered_stages,
        )
        decision_basis = self._dedupe_list(
            selected_decision.basis
            + self._supporting_basis(
                selected_decision.primary,
                ordered_stages=ordered_stages,
                selected_stage=selected_stage,
            )
        )[:4]
        confidence = self._confidence(
            selected_decision.primary,
            ordered_stages=ordered_stages,
            selected_stage=selected_stage,
        )
        return InputFamilyClassification(
            family=selected_decision.primary,
            confidence=confidence,
            decision_basis=decision_basis,
            secondary_signals=secondary_signals,
            display_strategy=self._display_strategy(selected_decision.primary, prepared),
            internal_strategy=self._internal_strategy(selected_decision.primary),
        )

    def _classify_explicit_goal(self, prepared: Any) -> _StageDecision:
        text = self._goal_text(prepared)
        if not text:
            return _StageDecision()
        operational_assets = self._operational_assets_dominant(prepared)
        operational_goal = self._has_any(text, self.OPERATIONAL_ANALYSIS_TERMS)
        redesign_goal = self._has_any(text, self.REDESIGN_TERMS)
        migration_goal = self._is_migration_request(text)
        option_goal = self._has_any(text, self.OPTION_TERMS)
        document_goal = self._has_any(text, self.DOCUMENT_TERMS)
        mixed_review = self._has_any(text, self.MIXED_REVIEW_TERMS)
        redesign_deprioritized = self._is_redesign_deprioritized(text)
        if option_goal:
            secondary = ["document_consulting"] if document_goal or self._document_assets_present(prepared) else []
            return _StageDecision(
                primary="option_comparison",
                secondary=secondary,
                basis=["사용자 목표가 선택지 비교와 추천안 판단에 맞춰져 있습니다."],
            )
        if migration_goal:
            if operational_assets and (operational_goal or mixed_review):
                return _StageDecision(
                    secondary=["migration_transition"],
                    basis=["전환 요청이 있으나 운영 소스 자산에서는 현행 복원이 선행될 수 있습니다."],
                )
            return _StageDecision(
                primary="migration_transition",
                basis=["사용자 목표가 전환 대상과 순서, 리스크 계획 수립에 맞춰져 있습니다."],
            )
        if redesign_goal and operational_assets and self._is_operational_reconstruction_request(text):
            return _StageDecision(
                primary="operational_source",
                secondary=["redesign_review"],
                basis=["사용자 목표의 재구성은 구조 재배치보다 현행 처리 흐름과 계산 규칙 복원 의미가 더 강합니다."],
            )
        if redesign_goal:
            if operational_assets and redesign_deprioritized:
                return _StageDecision(
                    primary="operational_source",
                    secondary=["redesign_review"],
                    basis=["재설계 언급이 있으나 사용자 목표가 현행 운영 로직 복원을 우선하도록 명시합니다."],
                )
            if operational_assets and mixed_review:
                return _StageDecision(
                    secondary=["redesign_review"],
                    basis=["구조 개선 요청이 있으나 운영 소스 자산에서는 현행 복원이 선행될 수 있습니다."],
                )
            return _StageDecision(
                primary="redesign_review",
                secondary=["operational_source"] if operational_assets else [],
                basis=["사용자 목표가 구조 문제와 책임 분리 판단에 맞춰져 있습니다."],
            )
        if document_goal and not self._has_any(text, self.OPTION_TERMS):
            return _StageDecision(
                primary="document_consulting",
                basis=["사용자 목표가 문서 요약과 구조화 설명에 맞춰져 있습니다."],
            )
        if operational_goal:
            secondary = ["redesign_review"] if redesign_goal else []
            return _StageDecision(
                primary="operational_source",
                secondary=secondary,
                basis=["사용자 목표가 현행 동작, 흐름, 규칙 복원에 맞춰져 있습니다."],
            )
        return _StageDecision()

    def _classify_asset_type(self, prepared: Any) -> _StageDecision:
        profile = self.helper.operational_analysis_profile(prepared)
        if bool(profile.get("dominant_operational_assets")) and (
            bool(profile.get("active"))
            or int(profile.get("sql_object_count") or 0) >= 2
            or int(profile.get("domain_keyword_count") or 0) >= 4
        ):
            basis = ["SQL/trigger/procedure 중심 자산이 우세합니다."]
            domain = str(profile.get("domain") or "").strip()
            if domain == "fx_fifo":
                basis.append("FIFO, 환차손익, 전표/GL 흐름이 반복적으로 확인됩니다.")
            elif domain == "interface_linkage":
                basis.append("staging, ACK, retry, downstream 연계 객체가 반복적으로 확인됩니다.")
            elif domain == "settlement_journal":
                basis.append("정산, 전표, GL, 취소 역처리 객체가 반복적으로 확인됩니다.")
            return _StageDecision(primary="operational_source", basis=basis)
        if self._document_assets_present(prepared):
            if self._document_option_density(prepared) >= 2:
                return _StageDecision(
                    primary="option_comparison",
                    secondary=["document_consulting"],
                    basis=["옵션 A/B 또는 장단점이 포함된 문서 자산이 중심입니다."],
                )
            if self._document_only(prepared):
                return _StageDecision(
                    primary="document_consulting",
                    basis=["코드보다 문서형 자산이 중심입니다."],
                )
        if self._to_be_document_density(prepared) >= 2:
            return _StageDecision(
                primary="migration_transition",
                basis=["AS-IS/TO-BE 또는 전환 계획 문서 자산이 확인됩니다."],
            )
        return _StageDecision()

    def _classify_question_axis(self, prepared: Any) -> _StageDecision:
        text = self._question_axis_text(prepared)
        if not text:
            return _StageDecision()
        if self._has_any(text, self.OPTION_TERMS):
            return _StageDecision(
                primary="option_comparison",
                secondary=["document_consulting"] if self._document_assets_present(prepared) else [],
                basis=["질문 축이 비교 기준과 추천안 판단에 집중돼 있습니다."],
            )
        if self._is_migration_request(text):
            return _StageDecision(
                primary="migration_transition",
                basis=["질문 축이 전환 대상, 순서, 리스크 계획에 집중돼 있습니다."],
            )
        if self._operational_assets_dominant(prepared) and self._is_redesign_deprioritized(text):
            return _StageDecision(
                primary="operational_source",
                secondary=["redesign_review"],
                basis=["질문 축에서 재설계 언급은 보조 신호이고 현행 흐름 복원이 선행 과제입니다."],
            )
        if self._operational_assets_dominant(prepared) and self._is_operational_reconstruction_request(text):
            return _StageDecision(
                primary="operational_source",
                secondary=["redesign_review"],
                basis=["질문 축의 재구성 요청은 구조 재배치보다 현행 객체와 처리 흐름 복원에 가깝습니다."],
            )
        if self._has_any(text, self.REDESIGN_TERMS):
            return _StageDecision(
                primary="redesign_review",
                secondary=["operational_source"] if self._operational_assets_dominant(prepared) else [],
                basis=["질문 축이 책임 배치와 경계 결함 판단에 집중돼 있습니다."],
            )
        if self._has_any(text, self.OPERATIONAL_ANALYSIS_TERMS):
            return _StageDecision(
                primary="operational_source",
                basis=["질문 축이 현행 객체, 흐름, 계산 규칙 복원에 집중돼 있습니다."],
            )
        if self._has_any(text, self.DOCUMENT_TERMS):
            return _StageDecision(
                primary="document_consulting",
                basis=["질문 축이 문서 설명과 구조화에 집중돼 있습니다."],
            )
        return _StageDecision()

    def _classify_dominant_evidence(self, prepared: Any, *, diagnosis: Any | None) -> _StageDecision:
        profile = self.helper.operational_analysis_profile(prepared)
        evidence_text = self._combined_text(prepared)
        redesign_score = 0
        if diagnosis is not None:
            for issue in list(getattr(getattr(diagnosis, "diagnosis_report", None), "issues", []) or []):
                detector_id = str(getattr(issue, "detector_id", "") or "").strip()
                if detector_id in {
                    "boundary_mismatch",
                    "ui_data_access_coupling",
                    "mixed_responsibility",
                    "rule_scatter",
                    "state_transition_leak",
                    "validation_guard_leak",
                }:
                    redesign_score += 2
                elif detector_id in {"duplicate_logic_candidate", "query_filter_leak"}:
                    redesign_score += 1
        operational_score = int(profile.get("sql_object_count") or 0) + min(int(profile.get("domain_keyword_count") or 0), 5)
        if bool(profile.get("dominant_operational_assets")):
            operational_score += 2
        migration_score = self._term_hits(evidence_text, self.MIGRATION_TERMS)
        option_score = self._document_option_density(prepared)
        document_score = 2 if self._document_assets_present(prepared) else 0
        if option_score >= max(document_score + 1, 2):
            return _StageDecision(
                primary="option_comparison",
                secondary=["document_consulting"] if document_score else [],
                basis=["문서 증거에서 옵션 비교와 추천 신호가 반복적으로 확인됩니다."],
            )
        if operational_score >= max(redesign_score + 1, 5):
            basis = ["테이블/프로시저/트리거 객체와 업무 키워드가 운영 흐름 중심으로 반복됩니다."]
            if not self._has_any(self._goal_text(prepared), self.STRONG_REDESIGN_TERMS):
                basis.append("명시적 구조 재설계 우선 요구는 강하지 않습니다.")
            return _StageDecision(primary="operational_source", basis=basis)
        if redesign_score >= 4:
            return _StageDecision(
                primary="redesign_review",
                secondary=["operational_source"] if operational_score >= 4 else [],
                basis=["경계 누수, 책임 혼합, 규칙 산재 같은 구조 결함 증거가 우세합니다."],
            )
        if migration_score >= 2 and self._to_be_document_density(prepared) >= 1:
            return _StageDecision(
                primary="migration_transition",
                basis=["AS-IS/TO-BE 또는 migration 증거가 반복적으로 확인됩니다."],
            )
        if document_score and not operational_score:
            return _StageDecision(
                primary="document_consulting",
                basis=["문서 증거가 중심이고 코드 구조 판단 신호는 약합니다."],
            )
        return _StageDecision()

    def _collect_secondary_signals(
        self,
        primary: str,
        *,
        ordered_stages: tuple[tuple[str, _StageDecision], ...],
    ) -> list[str]:
        counts: dict[str, int] = {}
        for _, decision in ordered_stages:
            if decision.primary and decision.primary != primary:
                counts[decision.primary] = counts.get(decision.primary, 0) + 2
            for secondary in decision.secondary:
                if secondary and secondary != primary:
                    counts[secondary] = counts.get(secondary, 0) + 1
        ordered = sorted(
            counts.items(),
            key=lambda item: (-item[1], self.FAMILY_ORDER.get(item[0], 99)),
        )
        return [family for family, _ in ordered[:2]]

    def _supporting_basis(
        self,
        primary: str,
        *,
        ordered_stages: tuple[tuple[str, _StageDecision], ...],
        selected_stage: str,
    ) -> list[str]:
        output: list[str] = []
        for stage_name, decision in ordered_stages:
            if stage_name == selected_stage:
                continue
            if decision.primary == primary or primary in decision.secondary:
                output.extend(decision.basis)
        return output[:2]

    def _confidence(
        self,
        primary: str,
        *,
        ordered_stages: tuple[tuple[str, _StageDecision], ...],
        selected_stage: str,
    ) -> float:
        base_by_stage = {
            "goal": 0.84,
            "asset": 0.78,
            "question": 0.71,
            "evidence": 0.66,
            "conservative": 0.58,
        }
        aligned = 0
        conflicts = 0
        for _, decision in ordered_stages:
            if decision.primary == primary or primary in decision.secondary:
                aligned += 1
            elif decision.primary and decision.primary != primary:
                conflicts += 1
        confidence = base_by_stage.get(selected_stage, 0.58) + (0.05 * max(0, aligned - 1)) - (0.04 * conflicts)
        return round(max(0.55, min(0.96, confidence)), 2)

    def _conservative_choice(
        self,
        prepared: Any,
        *,
        asset_decision: _StageDecision,
        question_decision: _StageDecision,
        evidence_decision: _StageDecision,
    ) -> tuple[str, list[str]]:
        comparison_present = self._has_any(self._question_axis_text(prepared), self.OPTION_TERMS) or self._document_option_density(prepared) >= 2
        candidates = [
            family
            for family in (
                asset_decision.primary,
                question_decision.primary,
                evidence_decision.primary,
            )
            if family
        ]
        if "operational_source" in candidates and "redesign_review" in candidates:
            return "operational_source", ["동률 구간에서는 보수 선택 원칙에 따라 operational_source를 우선합니다."]
        if comparison_present and "option_comparison" in candidates:
            return "option_comparison", ["비교 질문이 확인돼 document_consulting보다 option_comparison을 우선합니다."]
        if self._document_assets_present(prepared):
            return "document_consulting", ["명시 목표가 부족해 문서 자산 기준의 보수 선택을 적용했습니다."]
        return "operational_source", ["명시 목표가 부족해 운영 자산 분석을 우선하는 보수 선택을 적용했습니다."]

    def _display_strategy(self, family: str, prepared: Any) -> str:
        if family == "operational_source":
            profile = self.helper.operational_analysis_profile(prepared)
            if str(profile.get("domain") or "").strip() == "fx_fifo":
                return "현행 분석 우선"
            return "운영 로직 검토 우선"
        return self.DISPLAY_STRATEGY_BY_FAMILY.get(family, "")

    def _internal_strategy(self, family: str) -> str:
        return self.INTERNAL_STRATEGY_BY_FAMILY.get(family, "")

    def _goal_text(self, prepared: Any) -> str:
        intent = getattr(prepared, "intent", None)
        goal = str(getattr(intent, "goal", "") or getattr(prepared, "goal", "") or "")
        constraints = " ".join(list(getattr(intent, "constraints", []) or getattr(prepared, "constraints", []) or []))
        scenario = str(getattr(intent, "scenario", "") or "")
        parts = [part for part in (goal, constraints) if part]
        if not parts and scenario:
            parts.append(scenario)
        return self._normalize_text(" ".join(parts))

    def _question_axis_text(self, prepared: Any) -> str:
        parts = [
            self._goal_text(prepared),
            str(getattr(prepared, "supporting_docs", "") or ""),
        ]
        return self._normalize_text(" ".join(part for part in parts if part))

    def _combined_text(self, prepared: Any) -> str:
        return self._normalize_text(
            " ".join(
                part
                for part in (
                    self._goal_text(prepared),
                    str(getattr(prepared, "supporting_docs", "") or ""),
                    str(getattr(prepared, "legacy_bundle", "") or ""),
                    str(getattr(getattr(prepared, "assets", None), "framework_info", "") or ""),
                )
                if part
            )
        )

    def _document_assets_present(self, prepared: Any) -> bool:
        asset_presence = getattr(prepared, "asset_presence", None)
        return bool(getattr(asset_presence, "has_docs", False) or str(getattr(prepared, "supporting_docs", "") or "").strip())

    def _document_only(self, prepared: Any) -> bool:
        asset_presence = getattr(prepared, "asset_presence", None)
        if not self._document_assets_present(prepared):
            return False
        return not any(
            bool(getattr(asset_presence, field, False))
            for field in ("has_source_code", "has_ui_asset", "has_schema_asset", "has_sql_asset", "has_framework_hint")
        )

    def _operational_assets_dominant(self, prepared: Any) -> bool:
        profile = self.helper.operational_analysis_profile(prepared)
        return bool(profile.get("dominant_operational_assets"))

    def _document_option_density(self, prepared: Any) -> int:
        text = self._normalize_text(
            " ".join(
                part
                for part in (
                    str(getattr(prepared, "supporting_docs", "") or ""),
                    self._goal_text(prepared),
                )
                if part
            )
        )
        hits = self._term_hits(text, self.OPTION_TERMS)
        if re.search(r"(option|옵션)\s*[abc123]", text):
            hits += 2
        if re.search(r"장점.+단점|pros?.+cons?", text):
            hits += 1
        return hits

    def _to_be_document_density(self, prepared: Any) -> int:
        text = self._normalize_text(
            " ".join(
                part
                for part in (
                    str(getattr(prepared, "supporting_docs", "") or ""),
                    self._goal_text(prepared),
                    str(getattr(getattr(prepared, "assets", None), "framework_info", "") or ""),
                )
                if part
            )
        )
        hits = self._term_hits(text, self.MIGRATION_TERMS)
        if "as-is" in text and "to-be" in text:
            hits += 2
        return hits

    def _term_hits(self, text: str, terms: tuple[str, ...]) -> int:
        return sum(1 for term in terms if term in text)

    def _has_any(self, text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    def _normalize_text(self, text: str) -> str:
        lowered = (text or "").strip().lower()
        return re.sub(r"\s+", " ", lowered)

    def _dedupe_list(self, items: list[str]) -> list[str]:
        output: list[str] = []
        for item in items:
            normalized = str(item or "").strip()
            if normalized and normalized not in output:
                output.append(normalized)
        return output

    def _is_migration_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        if "as-is" in normalized and "to-be" in normalized:
            return True
        return any(re.search(pattern, normalized) for pattern in self.MIGRATION_REQUEST_PATTERNS)

    def _is_redesign_deprioritized(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        if "현행 운영 로직" in normalized and "우선" in normalized:
            return True
        if "현행 동작" in normalized and "우선" in normalized:
            return True
        return any(re.search(pattern, normalized) for pattern in self.REDESIGN_DEPRIORITIZED_PATTERNS)

    def _is_operational_reconstruction_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if "재구성" not in normalized:
            return False
        operational_anchors = (
            "처리 흐름",
            "데이터 흐름",
            "운영 로직",
            "현행 동작",
            "회계 흐름",
            "업무 규칙",
            "계산 규칙",
            "흐름 복원",
            "로직 복원",
            "fifo",
            "lot",
            "환차손익",
            "전표",
            "gl",
        )
        redesign_anchors = (
            "구조 문제",
            "책임 분리",
            "경계 재설정",
            "구조 개선",
            "모듈 분리",
            "레이어",
            "유지보수",
            "서비스 구조",
        )
        return any(anchor in normalized for anchor in operational_anchors) and not any(
            anchor in normalized for anchor in redesign_anchors
        )
