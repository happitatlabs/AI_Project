from __future__ import annotations

from typing import Any

from .policies import get_detector_policy, load_engine_policy_bundle
from .schemas import (
    DecisionArtifacts,
    DecisionRecord,
    DecisionSummary,
    DiagnosisArtifacts,
    StructureAnalysisResult,
    make_stable_id,
)


class DecisionEngine:
    def __init__(self, policy_bundle=None) -> None:
        self.policy_bundle = policy_bundle or load_engine_policy_bundle()

    def run(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        legacy_service: Any,
    ) -> DecisionArtifacts:
        applied_templates = legacy_service.build_applied_templates(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
        )
        pattern_candidates = legacy_service.collect_pattern_candidates(prepared, applied_templates)
        primary_judgment, primary_judgment_reason, pattern_candidates = legacy_service.select_primary_judgment(prepared, pattern_candidates)
        prepared.selected_primary_judgment = primary_judgment
        prepared.selected_primary_judgment_reason = primary_judgment_reason
        prepared.pattern_candidates = list(pattern_candidates)
        selected_narrative_judgment = legacy_service._resolve_narrative_judgment(
            prepared,
            diagnosis.grounded_business_rules,
            applied_templates,
        )
        prepared.selected_narrative_judgment = selected_narrative_judgment
        decision_items = legacy_service.build_decision_items(
            prepared,
            diagnosis.grounded_business_rules,
            applied_templates,
        )
        decisions = self._build_decisions(prepared, structure, diagnosis, decision_items)
        decision_summary = self._build_summary(prepared, decisions)
        return DecisionArtifacts(
            decision_summary=decision_summary,
            applied_templates=applied_templates,
            pattern_candidates=pattern_candidates,
            primary_judgment=primary_judgment,
            primary_judgment_reason=primary_judgment_reason,
            selected_narrative_judgment=selected_narrative_judgment,
            decision_items=decision_items,
        )

    def _build_decisions(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decision_items,
    ) -> list[DecisionRecord]:
        decisions: list[DecisionRecord] = []
        rationale_fallback = decision_items[0].rationale if decision_items else "구조적 문제를 우선 분리하는 편이 적절합니다."
        hotspot_scores = {item.component_id: item.score for item in structure.structure_snapshot.hotspots}
        scoring_policy = self.policy_bundle.scoring_policy
        decision_breakdowns: dict[str, dict[str, int]] = {}
        for issue in diagnosis.diagnosis_report.issues:
            decision_type = self._decision_type_for_issue(prepared, issue)
            score_breakdown = self._score_breakdown(issue, decision_type, hotspot_scores, scoring_policy)
            priority_score = score_breakdown["final_score"]
            rationale = self._rationale_for_issue(issue, decision_type, rationale_fallback)
            decision_breakdowns[issue.issue_id] = score_breakdown
            decisions.append(
                DecisionRecord(
                    decision_id=make_stable_id("DEC", issue.issue_id, decision_type),
                    issue_ids=[issue.issue_id],
                    decision_type=decision_type,
                    target_component_ids=list(issue.affected_component_ids),
                    priority_score=priority_score,
                    score_breakdown=score_breakdown,
                    rationale=rationale,
                    confidence=round(min(0.95, issue.confidence + 0.02), 2),
                    evidence_ids=list(issue.evidence_ids),
                )
            )
        if self._has_migration_signal(prepared):
            top_issue_ids = [item.issue_id for item in diagnosis.diagnosis_report.issues[:2]]
            evidence_ids = [evidence_id for item in diagnosis.diagnosis_report.issues[:2] for evidence_id in item.evidence_ids]
            decisions.append(
                DecisionRecord(
                    decision_id=make_stable_id("DEC", prepared.goal, "migration_consideration"),
                    issue_ids=top_issue_ids,
                    decision_type="migration_consideration",
                    target_component_ids=[component.component_id for component in structure.structure_snapshot.components if component.layer in {"api", "service"}][:3],
                    priority_score=max([item.priority_score for item in decisions], default=7),
                    score_breakdown=self._migration_score_breakdown(top_issue_ids, decision_breakdowns, max([item.priority_score for item in decisions], default=7)),
                    rationale="스택 또는 전환 요구가 명시되어 있어 후속 마이그레이션 필요성을 함께 검토하는 편이 적절합니다.",
                    confidence=0.72,
                    evidence_ids=list(dict.fromkeys(evidence_ids)),
                )
            )
        decisions.sort(key=lambda item: (-item.priority_score, -item.confidence, item.decision_id))
        return decisions

    def _decision_type_for_issue(self, prepared: Any, issue) -> str:
        if self._has_migration_signal(prepared) and issue.detector_id in {"boundary_mismatch", "ui_data_access_coupling"} and issue.severity >= 4:
            return "migration_consideration"
        if issue.detector_id == "boundary_mismatch":
            return "redesign"
        if issue.detector_id in {"rule_scatter", "state_transition_leak", "validation_guard_leak"} and (
            issue.blast_radius >= 4 or len(issue.affected_component_ids) >= 3
        ):
            return "redesign"
        if issue.detector_id == "ui_data_access_coupling" and issue.severity >= 5 and issue.blast_radius >= 4:
            return "redesign"
        return "refactor"

    def _score_breakdown(self, issue, decision_type: str, hotspot_scores: dict[str, int], scoring_policy) -> dict[str, int]:
        detector_policy = self._policy_for(issue.detector_id)
        severity_component = issue.severity * scoring_policy.severity_multiplier
        blast_radius_component = issue.blast_radius * scoring_policy.blast_radius_multiplier
        effort_component = issue.effort * scoring_policy.effort_multiplier
        confidence_bonus = scoring_policy.confidence_bonus_value if issue.confidence >= scoring_policy.confidence_bonus_threshold else 0
        detector_bonus = detector_policy.detector_weight
        hotspot_bonus = 0
        if detector_policy.allow_hotspot_bonus and any(hotspot_scores.get(component_id, 0) >= 2 for component_id in issue.affected_component_ids):
            hotspot_bonus = scoring_policy.hotspot_bonus
        slice_ids = [slice_id for slice_id in issue.affected_slice_ids if slice_id != "global"]
        multi_slice_bonus = scoring_policy.multi_slice_bonus if len(set(slice_ids)) >= 2 else 0
        redesign_bonus = scoring_policy.redesign_bonus if decision_type == "redesign" else 0
        final_score = max(
            1,
            severity_component
            + blast_radius_component
            - effort_component
            + confidence_bonus
            + detector_bonus
            + hotspot_bonus
            + multi_slice_bonus
            + redesign_bonus,
        )
        return {
            "severity_component": severity_component,
            "blast_radius_component": blast_radius_component,
            "effort_component": effort_component,
            "confidence_bonus": confidence_bonus,
            "detector_weight": detector_bonus,
            "hotspot_bonus": hotspot_bonus,
            "multi_slice_bonus": multi_slice_bonus,
            "redesign_bonus": redesign_bonus,
            "final_score": final_score,
        }

    def _priority_score(self, issue, decision_type: str, hotspot_scores: dict[str, int], scoring_policy) -> int:
        return self._score_breakdown(issue, decision_type, hotspot_scores, scoring_policy)["final_score"]

    def _migration_score_breakdown(
        self,
        issue_ids: list[str],
        decision_breakdowns: dict[str, dict[str, int]],
        final_score: int,
    ) -> dict[str, int]:
        for issue_id in issue_ids:
            breakdown = decision_breakdowns.get(issue_id)
            if breakdown:
                return dict(breakdown, final_score=final_score)
        return {
            "severity_component": 0,
            "blast_radius_component": 0,
            "effort_component": 0,
            "confidence_bonus": 0,
            "detector_weight": 0,
            "hotspot_bonus": 0,
            "multi_slice_bonus": 0,
            "redesign_bonus": 0,
            "final_score": final_score,
        }

    def _has_migration_signal(self, prepared: Any) -> bool:
        combined = " ".join([str(getattr(prepared, "goal", "") or "")] + list(getattr(prepared, "constraints", []) or [])).lower()
        keywords = (
            "migration",
            "migrate",
            "react",
            "spring",
            "rewrite",
            "rest api",
            "microservice",
            "마이그레이션",
            "전환",
            "재플랫폼",
        )
        return any(keyword in combined for keyword in keywords)

    def _rationale_for_issue(self, issue, decision_type: str, fallback: str) -> str:
        if decision_type == "redesign":
            return f"{issue.summary}. 현재 경계를 바로 고정하기보다 다시 정의하는 쪽을 우선 검토하는 편이 안전합니다."
        if decision_type == "migration_consideration":
            return f"{issue.summary}. 구조 개선과 별도로 단계적 전환 필요성을 함께 검토하는 편이 적절합니다."
        return f"{issue.summary}. 데이터 계약 변경 없이 책임 분리 후보로 다루는 편이 적절합니다."

    def _policy_for(self, detector_id: str):
        return get_detector_policy(detector_id, self.policy_bundle)

    def _build_summary(self, prepared: Any, decisions: list[DecisionRecord]) -> DecisionSummary:
        if not decisions:
            return DecisionSummary(recommended_strategy="리팩터링 우선", priority_queue=[])
        redesign_count = sum(1 for item in decisions if item.decision_type == "redesign")
        migration_count = sum(1 for item in decisions if item.decision_type == "migration_consideration")
        if migration_count and decisions[0].decision_type == "migration_consideration":
            strategy = "마이그레이션 고려"
        elif redesign_count:
            strategy = "재설계 우선"
        else:
            strategy = "리팩터링 우선"
        return DecisionSummary(
            decisions=decisions,
            recommended_strategy=strategy,
            priority_queue=[item.decision_id for item in decisions],
        )
