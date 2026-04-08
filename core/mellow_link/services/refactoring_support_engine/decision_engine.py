from __future__ import annotations

from typing import Any

from .judgment_synthesizer import JudgmentSynthesizer
from .narrative_axis import NarrativeAxisResolver
from .policies import get_detector_policy, load_engine_policy_bundle
from .schemas import (
    DecisionArtifacts,
    DecisionExplainability,
    DecisionRecord,
    DecisionSummary,
    DiagnosisArtifacts,
    StructureAnalysisResult,
    make_stable_id,
)


class DecisionEngine:
    MIGRATION_SIGNAL_KEYWORDS = (
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
    MIGRATION_ASSET_KEYWORDS = (
        "migration",
        "migrate",
        "react",
        "spring",
        "rewrite",
        "replatform",
        "microservice",
        "service split",
        "service separation",
        "service decomposition",
        "api gateway",
        "마이그레이션",
        "전환",
        "재플랫폼",
        "서비스 분리",
        "서비스 분해",
    )
    MIGRATION_BLOCK_KEYWORDS = (
        "migration 금지",
        "no migration",
        "without migration",
        "마이그레이션 금지",
        "마이그레이션 제외",
        "전환 금지",
        "전환 제외",
        "재플랫폼 금지",
        "재플랫폼 제외",
        "rewrite 금지",
        "rewrite 제외",
        "재작성 금지",
        "재작성 제외",
    )

    def __init__(self, policy_bundle=None) -> None:
        self.policy_bundle = policy_bundle or load_engine_policy_bundle()
        self.narrative_axis_resolver = NarrativeAxisResolver()
        self.judgment_synthesizer: JudgmentSynthesizer | None = None

    def run(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        legacy_service: Any | None = None,
    ) -> DecisionArtifacts:
        judgment_synthesizer = self.judgment_synthesizer or JudgmentSynthesizer()
        applied_templates = judgment_synthesizer.build_applied_templates(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
        )
        pattern_candidates = judgment_synthesizer.collect_pattern_candidates(prepared, applied_templates)
        primary_judgment, primary_judgment_reason, pattern_candidates = judgment_synthesizer.select_primary_judgment(prepared, pattern_candidates)
        prepared.selected_primary_judgment = primary_judgment
        prepared.selected_primary_judgment_reason = primary_judgment_reason
        prepared.pattern_candidates = list(pattern_candidates)
        selected_narrative_judgment = self.narrative_axis_resolver.select_axis(
            prepared,
            diagnosis.grounded_business_rules,
            diagnosis.retained_contracts,
            primary_judgment,
        )
        prepared.selected_narrative_judgment = selected_narrative_judgment
        decision_items = judgment_synthesizer.build_decision_items(
            prepared,
            diagnosis.grounded_business_rules,
            applied_templates,
            decision_count_hint=len(diagnosis.diagnosis_report.issues),
        )
        setattr(prepared, "decision_constraint_filters", self._blocked_recommendation_types(prepared))
        decisions, synthetic_signal_detected = self._build_decisions(prepared, structure, diagnosis, decision_items)
        decision_summary = self._build_summary(prepared, decisions)
        structural_judgment = self._structural_judgment(decision_summary)
        return DecisionArtifacts(
            decision_summary=decision_summary,
            applied_templates=applied_templates,
            pattern_candidates=pattern_candidates,
            primary_judgment=primary_judgment,
            template_judgment=primary_judgment,
            structural_judgment=structural_judgment,
            narrative_axis=selected_narrative_judgment,
            feature_signal_mode=str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""),
            primary_judgment_reason=primary_judgment_reason,
            selected_narrative_judgment=selected_narrative_judgment,
            decision_items=decision_items,
            synthetic_signal_detected=synthetic_signal_detected,
        )

    def _build_decisions(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        decision_items,
    ) -> tuple[list[DecisionRecord], bool]:
        decisions: list[DecisionRecord] = []
        synthetic_signal_detected = False
        rationale_fallback = decision_items[0].rationale if decision_items else "구조적 문제를 우선 분리하는 편이 적절합니다."
        hotspot_scores = {item.component_id: item.score for item in structure.structure_snapshot.hotspots}
        scoring_policy = self.policy_bundle.scoring_policy
        goal_prefers_migration = self._goal_prefers_migration(prepared)
        asset_migration_support = self._has_asset_migration_support(prepared)
        decision_breakdowns: dict[str, dict[str, int]] = {}
        decision_explainability: dict[str, DecisionExplainability] = {}
        for issue in diagnosis.diagnosis_report.issues:
            decision_type = self._decision_type_for_issue(prepared, issue, asset_migration_support=asset_migration_support)
            score_breakdown = self._score_breakdown(issue, decision_type, hotspot_scores, scoring_policy)
            priority_score = score_breakdown["final_score"]
            rationale = self._rationale_for_issue(issue, decision_type, rationale_fallback)
            decision_breakdowns[issue.issue_id] = score_breakdown
            decision_explainability[issue.issue_id] = self._build_explainability(issue, decision_type, score_breakdown, scoring_policy)
            decisions.append(
                DecisionRecord(
                    decision_id=make_stable_id("DEC", issue.issue_id, decision_type),
                    issue_ids=[issue.issue_id],
                    decision_type=decision_type,
                    target_component_ids=list(issue.affected_component_ids),
                    priority_score=priority_score,
                    score_breakdown=score_breakdown,
                    explainability=decision_explainability[issue.issue_id],
                    rationale=rationale,
                    confidence=round(min(0.95, issue.confidence + 0.02), 2),
                    evidence_ids=list(issue.evidence_ids),
                )
            )
        if goal_prefers_migration and not asset_migration_support:
            synthetic_signal_detected = True
        decisions, guard_triggered = self._apply_migration_hard_guard(decisions, diagnosis)
        synthetic_signal_detected = synthetic_signal_detected or guard_triggered
        decisions.sort(
            key=lambda item: (
                -(item.priority_score + self._goal_sort_bias(item, goal_prefers_migration)),
                -item.confidence,
                item.decision_id,
            )
        )
        return decisions, synthetic_signal_detected

    def _decision_type_for_issue(self, prepared: Any, issue, *, asset_migration_support: bool | None = None) -> str:
        del prepared
        if (asset_migration_support if asset_migration_support is not None else False) and self._issue_supports_migration(issue):
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

    def _build_explainability(self, issue, decision_type: str, score_breakdown: dict[str, int], scoring_policy) -> DecisionExplainability:
        return DecisionExplainability(
            decision_rule=self._decision_rule_text(issue, decision_type),
            score_formula=self._score_formula_text(scoring_policy),
            score_summary=self._score_summary_text(issue, score_breakdown, scoring_policy),
            evidence_count=len(issue.evidence_ids),
            affected_slice_count=len({slice_id for slice_id in issue.affected_slice_ids if slice_id and slice_id != "global"}),
        )

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

    def _migration_explainability(
        self,
        issue_ids: list[str],
        decision_explainability: dict[str, DecisionExplainability],
        final_score: int,
    ) -> DecisionExplainability:
        for issue_id in issue_ids:
            explainability = decision_explainability.get(issue_id)
            if explainability is None:
                continue
            return explainability.model_copy(
                update={
                    "decision_rule": f"migration signal + top structural issue({issue_id}) -> migration_consideration",
                    "score_summary": f"{explainability.score_summary}; migration_consideration final_score={final_score}",
                }
            )
        return DecisionExplainability(
            decision_rule="migration signal -> migration_consideration",
            score_formula="reuse top structural issue score as migration consideration baseline",
            score_summary=f"migration_consideration final_score={final_score}",
            evidence_count=0,
            affected_slice_count=0,
        )

    def _goal_prefers_migration(self, prepared: Any) -> bool:
        goal = str(getattr(getattr(prepared, "intent", None), "goal", "") or getattr(prepared, "goal", "") or "").lower()
        return any(keyword in goal for keyword in self.MIGRATION_SIGNAL_KEYWORDS)

    def _has_asset_migration_support(self, prepared: Any) -> bool:
        assets = getattr(prepared, "assets", None)
        combined = "\n".join(
            str(part or "")
            for part in (
                getattr(assets, "source_code", ""),
                getattr(assets, "database_schema", ""),
                getattr(assets, "sql_queries", ""),
                getattr(assets, "ui_template", ""),
                getattr(assets, "framework_info", ""),
            )
        ).lower()
        return any(keyword in combined for keyword in self.MIGRATION_ASSET_KEYWORDS)

    def _blocked_recommendation_types(self, prepared: Any) -> list[str]:
        constraints = list(getattr(getattr(prepared, "intent", None), "constraints", []) or getattr(prepared, "constraints", []) or [])
        blocked: list[str] = []
        lowered = [str(item or "").lower() for item in constraints]
        if any(
            any(keyword in text for keyword in self.MIGRATION_BLOCK_KEYWORDS)
            or (
                ("migration" in text or "마이그레이션" in text or "전환" in text or "재플랫폼" in text or "rewrite" in text)
                and any(token in text for token in ("금지", "제외", "without", "no ", "exclude"))
            )
            for text in lowered
        ):
            blocked.append("migration_consideration")
        return blocked

    def _goal_sort_bias(self, item: DecisionRecord, goal_prefers_migration: bool) -> float:
        if goal_prefers_migration and item.decision_type == "migration_consideration":
            return 0.25
        return 0.0

    def _issue_supports_migration(self, issue) -> bool:
        return issue.detector_id in {"boundary_mismatch", "ui_data_access_coupling"} and issue.severity >= 4

    def _apply_migration_hard_guard(
        self,
        decisions: list[DecisionRecord],
        diagnosis: DiagnosisArtifacts,
    ) -> tuple[list[DecisionRecord], bool]:
        guarded: list[DecisionRecord] = []
        guard_triggered = False
        has_structural_issues = bool(diagnosis.diagnosis_report.issues)
        for item in decisions:
            if item.decision_type != "migration_consideration":
                guarded.append(item)
                continue
            if item.issue_ids or item.evidence_ids:
                guarded.append(item)
                continue
            guard_triggered = True
            if not has_structural_issues:
                continue
            guarded.append(
                item.model_copy(
                    update={
                        "decision_type": "refactor",
                        "rationale": "전환 신호가 있었지만 구조 근거가 부족해 일반 리팩터링 후보로 낮춰 검토하는 편이 적절합니다.",
                        "explainability": item.explainability.model_copy(
                            update={
                                "decision_rule": "migration hard guard -> refactor (asset-absent decision blocked)",
                                "score_summary": f"{item.explainability.score_summary}; synthetic migration downgraded to refactor",
                            }
                        ),
                    }
                )
            )
        return guarded, guard_triggered

    def _rationale_for_issue(self, issue, decision_type: str, fallback: str) -> str:
        if decision_type == "redesign":
            return f"{issue.summary}. 현재 경계를 바로 고정하기보다 다시 정의하는 쪽을 우선 검토하는 편이 안전합니다."
        if decision_type == "migration_consideration":
            return f"{issue.summary}. 구조 개선과 별도로 단계적 전환 필요성을 함께 검토하는 편이 적절합니다."
        return f"{issue.summary}. 데이터 계약 변경 없이 책임 분리 후보로 다루는 편이 적절합니다."

    def _decision_rule_text(self, issue, decision_type: str) -> str:
        if decision_type == "migration_consideration":
            return f"detector_id={issue.detector_id}와 asset-derived migration support를 함께 확인해 migration_consideration으로 분기했습니다."
        if issue.detector_id == "boundary_mismatch":
            return "detector_id=boundary_mismatch 기준으로 redesign으로 분기했습니다."
        if issue.detector_id in {"rule_scatter", "state_transition_leak", "validation_guard_leak"} and (
            issue.blast_radius >= 4 or len(issue.affected_component_ids) >= 3
        ):
            return f"detector_id={issue.detector_id} 기준으로 다중 컴포넌트/광범위 영향 조건을 확인해 redesign으로 분기했습니다."
        if issue.detector_id == "ui_data_access_coupling" and issue.severity >= 5 and issue.blast_radius >= 4:
            return "detector_id=ui_data_access_coupling 기준으로 고위험 경계 침범 조건을 확인해 redesign으로 분기했습니다."
        return f"detector_id={issue.detector_id} 기준으로 기본 refactor 규칙에 분기했습니다."

    def _score_formula_text(self, scoring_policy) -> str:
        return (
            f"severity*{scoring_policy.severity_multiplier} + "
            f"blast_radius*{scoring_policy.blast_radius_multiplier} - "
            f"effort*{scoring_policy.effort_multiplier} + confidence_bonus + "
            "detector_weight + hotspot_bonus + multi_slice_bonus + redesign_bonus"
        )

    def _score_summary_text(self, issue, score_breakdown: dict[str, int], scoring_policy) -> str:
        return (
            f"severity({issue.severity}x{scoring_policy.severity_multiplier})={score_breakdown['severity_component']}, "
            f"blast_radius({issue.blast_radius}x{scoring_policy.blast_radius_multiplier})={score_breakdown['blast_radius_component']}, "
            f"effort({issue.effort}x{scoring_policy.effort_multiplier})={score_breakdown['effort_component']}, "
            f"confidence_bonus={score_breakdown['confidence_bonus']}, "
            f"detector_weight={score_breakdown['detector_weight']}, "
            f"hotspot_bonus={score_breakdown['hotspot_bonus']}, "
            f"multi_slice_bonus={score_breakdown['multi_slice_bonus']}, "
            f"redesign_bonus={score_breakdown['redesign_bonus']}, "
            f"final_score={score_breakdown['final_score']}"
        )

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

    def _structural_judgment(self, decision_summary: DecisionSummary) -> str:
        decisions = list(decision_summary.decisions or [])
        strategy = str(decision_summary.recommended_strategy or "").strip()
        if not decisions:
            return "observation_only"
        if strategy == "마이그레이션 고려" or decisions[0].decision_type == "migration_consideration":
            return "migration_consideration"
        if strategy == "재설계 우선" or decisions[0].decision_type == "redesign":
            return "redesign"
        return "refactor"
