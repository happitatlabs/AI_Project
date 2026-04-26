from __future__ import annotations

import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import AssumptionItem

from .family_classifier import FamilyClassifier
from .judgment_synthesizer import JudgmentSynthesizer
from .narrative_axis import NarrativeAxisResolver
from .policies import get_detector_policy, load_engine_policy_bundle
from .runtime_contracts import assert_stage_action
from .template_support import TemplateSupport
from .schemas import (
    DecisionBasis,
    DecisionArtifacts,
    DecisionConflict,
    DecisionExplainability,
    DecisionRecord,
    DecisionSummary,
    DiagnosisArtifacts,
    JudgmentCriteria,
    StructureAnalysisResult,
    make_stable_id,
    max_recommendation_strength,
    normalize_unit_interval,
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
    GOAL_FORCING_KEYWORDS = (
        "재구축",
        "전환",
        "마이그레이션",
        "재설계",
        "to-be",
        "무조건",
        "전면",
    )
    _ASSUMPTION_ALLOWED_MARKERS = {"가정", "전제", "조건부", "if_clause"}
    _ASSUMPTION_EXCLUDED_PREFIXES = ("가능하다면", "일반적으로", "통상적으로", "보통")
    _ASSUMPTION_EXCLUDED_PHRASES = ("추가 확인이 필요",)
    _ASSUMPTION_EXCLUDED_ACTION_PATTERNS = (
        re.compile(r".*해야\s+합니다[.]?$"),
        re.compile(r".*해야\s+한다[.]?$"),
    )

    def __init__(self, policy_bundle=None) -> None:
        self.policy_bundle = policy_bundle or load_engine_policy_bundle()
        self.narrative_axis_resolver = NarrativeAxisResolver()
        self.judgment_synthesizer: JudgmentSynthesizer | None = None
        self.template_support = TemplateSupport()
        self.family_classifier = FamilyClassifier(self.template_support)

    def run(
        self,
        prepared: Any,
        structure: StructureAnalysisResult,
        diagnosis: DiagnosisArtifacts,
        legacy_service: Any | None = None,
        *,
        stage_control: dict[str, object] | None = None,
        retry_hint: str = "",
    ) -> DecisionArtifacts:
        assert_stage_action(
            stage_control or getattr(prepared, "stage_control", None),
            expected_stage="decision",
            action="generate_decision_summary",
            goal=str(getattr(prepared, "goal", "") or ""),
        )
        family_classification = self.family_classifier.classify(
            prepared,
            structure=structure,
            diagnosis=diagnosis,
        )
        setattr(prepared, "family_classification", family_classification)
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
        if self._can_use_operational_analysis_profile(prepared):
            profile = self.template_support.operational_analysis_profile(prepared)
            if bool(profile.get("active")):
                domain = str(profile.get("domain") or "").strip()
                if domain in {"fx_fifo", "interface_linkage", "settlement_journal"}:
                    selected_narrative_judgment = domain
        prepared.selected_narrative_judgment = selected_narrative_judgment
        decision_items = judgment_synthesizer.build_decision_items(
            prepared,
            diagnosis.grounded_business_rules,
            applied_templates,
            decision_count_hint=len(diagnosis.diagnosis_report.issues),
        )
        assumptions = self._gatekeep_assumptions(prepared)
        setattr(prepared, "decision_constraint_filters", self._blocked_recommendation_types(prepared))
        decisions, synthetic_signal_detected = self._build_decisions(prepared, structure, diagnosis, decision_items)
        decisions = self._apply_retry_hint(
            decisions,
            diagnosis=diagnosis,
            prepared=prepared,
            retry_hint=retry_hint,
        )
        decision_basis = self._build_decision_basis(
            prepared,
            diagnosis=diagnosis,
            decisions=decisions,
        )
        conflicts = self._detect_decision_conflicts(
            prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            decision_basis=decision_basis,
        )
        decision_basis = self._apply_conflict_strength_adjustments(decision_basis, conflicts)
        decision_summary = self._build_summary(prepared, decisions, conflicts=conflicts)
        structural_judgment = self._structural_judgment(decision_summary)
        return DecisionArtifacts(
            decision_summary=decision_summary,
            applied_templates=applied_templates,
            pattern_candidates=pattern_candidates,
            family_classification=family_classification,
            primary_judgment=primary_judgment,
            template_judgment=primary_judgment,
            structural_judgment=structural_judgment,
            narrative_axis=selected_narrative_judgment,
            feature_signal_mode=str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""),
            primary_judgment_reason=primary_judgment_reason,
            selected_narrative_judgment=selected_narrative_judgment,
            decision_items=decision_items,
            assumptions=assumptions,
            synthetic_signal_detected=synthetic_signal_detected,
            decision_basis=decision_basis,
            conflicts=conflicts,
        )

    def _apply_retry_hint(
        self,
        decisions: list[DecisionRecord],
        *,
        diagnosis: DiagnosisArtifacts,
        prepared: Any,
        retry_hint: str,
    ) -> list[DecisionRecord]:
        hint = str(retry_hint or "").strip().lower()
        if not hint:
            return decisions
        filtered = list(decisions)
        if "evidence" in hint:
            filtered = [item for item in filtered if item.evidence_ids]
        blocked = {str(item or "").strip() for item in list(getattr(prepared, "decision_constraint_filters", []) or []) if str(item or "").strip()}
        if "forbidden" in hint or "constraint" in hint:
            filtered = [item for item in filtered if item.decision_type not in blocked]
        if "conflict" in hint:
            deduped: dict[str, DecisionRecord] = {}
            for item in filtered:
                issue_key = ",".join(sorted(item.issue_ids))
                if not issue_key:
                    issue_key = item.decision_id
                current = deduped.get(issue_key)
                if current is None or item.priority_score > current.priority_score:
                    deduped[issue_key] = item
            filtered = list(deduped.values())
        if "stage" in hint:
            filtered = [item.model_copy(deep=True) for item in filtered]
        if filtered == decisions:
            return filtered
        evidence_ids = {item.evidence_id for item in diagnosis.evidence_index}
        sanitized: list[DecisionRecord] = []
        for item in filtered:
            valid_refs = [evidence_id for evidence_id in item.evidence_ids if evidence_id in evidence_ids]
            sanitized.append(item.model_copy(update={"evidence_ids": valid_refs or list(item.evidence_ids)}))
        sanitized.sort(key=lambda item: (-item.priority_score, -item.confidence, item.decision_id))
        return sanitized

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
        raw_goal_prefers_migration = self._raw_goal_prefers_migration(prepared)
        asset_migration_support = self._has_asset_migration_support(prepared)
        decision_breakdowns: dict[str, dict[str, int]] = {}
        decision_explainability: dict[str, DecisionExplainability] = {}
        for issue in diagnosis.diagnosis_report.issues:
            decision_type = self._decision_type_for_issue(prepared, issue, asset_migration_support=asset_migration_support)
            score_breakdown = self._score_breakdown(issue, decision_type, hotspot_scores, scoring_policy)
            priority_score = score_breakdown["final_score"]
            rationale = self._rationale_for_issue(prepared, issue, decision_type, rationale_fallback)
            decision_breakdowns[issue.issue_id] = score_breakdown
            decision_explainability[issue.issue_id] = self._build_explainability(issue, decision_type, score_breakdown, scoring_policy, prepared=prepared)
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
        if (goal_prefers_migration or raw_goal_prefers_migration) and not asset_migration_support:
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
        if self._should_prioritize_operational_analysis(prepared):
            return "refactor"
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

    def _gatekeep_assumptions(self, prepared: Any) -> list[AssumptionItem]:
        output: list[AssumptionItem] = []
        seen: set[tuple[str, str]] = set()
        for raw_item in list(getattr(prepared, "assumption_candidates", []) or []):
            try:
                item = raw_item if isinstance(raw_item, AssumptionItem) else AssumptionItem.model_validate(raw_item)
            except Exception:
                continue
            marker = str(item.explicit_marker or "").strip()
            statement = " ".join(str(item.statement or "").split()).strip()
            if not statement or marker not in self._ASSUMPTION_ALLOWED_MARKERS:
                continue
            if self._is_excluded_assumption_statement(statement):
                continue
            key = (re.sub(r"\s+", " ", statement).lower(), marker)
            if key in seen:
                continue
            seen.add(key)
            output.append(
                item.model_copy(
                    update={
                        "statement": statement,
                        "applies_to": list(item.applies_to or []),
                    }
                )
            )
        return output

    def _is_excluded_assumption_statement(self, statement: str) -> bool:
        normalized = " ".join(str(statement or "").split()).strip()
        if not normalized:
            return True
        if normalized.startswith(self._ASSUMPTION_EXCLUDED_PREFIXES):
            return True
        if any(phrase in normalized for phrase in self._ASSUMPTION_EXCLUDED_PHRASES):
            return True
        return any(pattern.match(normalized) for pattern in self._ASSUMPTION_EXCLUDED_ACTION_PATTERNS)

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

    def _build_explainability(self, issue, decision_type: str, score_breakdown: dict[str, int], scoring_policy, *, prepared: Any | None = None) -> DecisionExplainability:
        return DecisionExplainability(
            decision_rule=self._decision_rule_text(issue, decision_type, prepared=prepared),
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
        goal = self._effective_goal_text(prepared).lower()
        return any(keyword in goal for keyword in self.MIGRATION_SIGNAL_KEYWORDS)

    def _raw_goal_prefers_migration(self, prepared: Any) -> bool:
        goal = self._raw_goal_text(prepared).lower()
        return any(keyword in goal for keyword in self.MIGRATION_SIGNAL_KEYWORDS)

    def _raw_goal_forces_direction(self, prepared: Any) -> bool:
        goal = self._raw_goal_text(prepared).lower()
        return any(keyword in goal for keyword in self.GOAL_FORCING_KEYWORDS)

    def _effective_goal_text(self, prepared: Any) -> str:
        guarded = getattr(prepared, "guarded_decision_input", None)
        if guarded is not None:
            goal = str(getattr(guarded, "effective_goal", "") or "").strip()
            if goal:
                return goal
        return str(getattr(getattr(prepared, "intent", None), "goal", "") or getattr(prepared, "goal", "") or "").strip()

    def _raw_goal_text(self, prepared: Any) -> str:
        guarded = getattr(prepared, "guarded_decision_input", None)
        if guarded is not None:
            goal = str(getattr(guarded, "raw_goal", "") or "").strip()
            if goal:
                return goal
        return str(getattr(prepared, "raw_goal", "") or getattr(getattr(prepared, "intent", None), "goal", "") or getattr(prepared, "goal", "") or "").strip()

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
        guarded = getattr(prepared, "guarded_decision_input", None)
        constraints = list(
            getattr(guarded, "raw_constraints", []) or getattr(prepared, "raw_constraints", []) or getattr(getattr(prepared, "intent", None), "constraints", []) or []
        )
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

    def _rationale_for_issue(self, prepared: Any, issue, decision_type: str, fallback: str) -> str:
        del fallback
        if self._should_prioritize_operational_analysis(prepared) and decision_type == "refactor" and issue.detector_id in {
            "boundary_mismatch",
            "rule_scatter",
            "state_transition_leak",
            "validation_guard_leak",
            "ui_data_access_coupling",
        }:
            return f"{issue.summary}. 현재 단계에서는 현행 운영 규칙과 처리 흐름을 복원하는 기준으로 점검하는 편이 적절합니다."
        if decision_type == "redesign":
            return f"{issue.summary}. 현재 경계를 바로 고정하기보다 다시 정의하는 쪽을 우선 검토하는 편이 안전합니다."
        if decision_type == "migration_consideration":
            return f"{issue.summary}. 구조 개선과 별도로 단계적 전환 필요성을 함께 검토하는 편이 적절합니다."
        return f"{issue.summary}. 데이터 계약 변경 없이 책임 분리 후보로 다루는 편이 적절합니다."

    def _decision_rule_text(self, issue, decision_type: str, *, prepared: Any | None = None) -> str:
        if decision_type == "migration_consideration":
            return f"detector_id={issue.detector_id}와 asset-derived migration support를 함께 확인해 migration_consideration으로 분기했습니다."
        if self._should_prioritize_operational_analysis(prepared) and decision_type == "refactor" and issue.detector_id in {
            "boundary_mismatch",
            "rule_scatter",
            "state_transition_leak",
            "validation_guard_leak",
            "ui_data_access_coupling",
        }:
            return f"detector_id={issue.detector_id} 감지는 있었지만 운영 소스 분석 우선 게이트에 따라 refactor로 유지했습니다."
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

    def _build_decision_basis(
        self,
        prepared: Any,
        *,
        diagnosis: DiagnosisArtifacts,
        decisions: list[DecisionRecord],
    ) -> list[DecisionBasis]:
        issue_map = {item.issue_id: item for item in list(diagnosis.diagnosis_report.issues or [])}
        missing_context_count = len(list(diagnosis.missing_context_details or []))
        blocked_types = {
            str(item or "").strip()
            for item in list(getattr(prepared, "decision_constraint_filters", []) or [])
            if str(item or "").strip()
        }
        raw_goal_signal_detected = self._raw_goal_prefers_migration(prepared)
        goal_signal_applied = self._goal_prefers_migration(prepared)
        asset_signal_detected = self._has_asset_migration_support(prepared)
        raw_goal_text = self._raw_goal_text(prepared)
        effective_goal_text = self._effective_goal_text(prepared)
        bases: list[DecisionBasis] = []
        for item in decisions:
            issue = issue_map.get(item.issue_ids[0], None) if item.issue_ids else None
            severity = max(0, int(getattr(issue, "severity", 0) or 0))
            blast_radius = max(0, int(getattr(issue, "blast_radius", 0) or 0))
            effort = max(0, int(getattr(issue, "effort", 0) or 0))
            issue_confidence = normalize_unit_interval(getattr(issue, "confidence", 0.0) or 0.0)
            evidence_ref_count = len(list(item.evidence_ids or []))
            evidence_coverage = normalize_unit_interval(evidence_ref_count / 2.0)
            evidence_strength = normalize_unit_interval(
                (evidence_coverage * 0.45)
                + (issue_confidence * 0.3)
                + (0.25 if bool(item.issue_ids and item.evidence_ids) else 0.0)
            )
            input_sufficiency = normalize_unit_interval(1.0 - (min(missing_context_count, 3) / 3.0))
            change_cost = normalize_unit_interval(effort / 5.0)
            delivery_speed = normalize_unit_interval(1.0 - change_cost)
            maintainability_gain = normalize_unit_interval((severity + blast_radius) / 10.0)
            if item.decision_type == "refactor":
                contract_stability = 0.9
            elif item.decision_type == "redesign":
                contract_stability = 0.65
            else:
                contract_stability = 0.5
            contract_stability = normalize_unit_interval(contract_stability)
            notes: list[str] = []
            scoring_reasons: list[str] = []
            if raw_goal_signal_detected and not goal_signal_applied:
                notes.append("raw_goal_signal_dropped_by_source_guard")
                scoring_reasons.append("raw_goal_signal_dropped_by_source_guard")
            if self._raw_goal_forces_direction(prepared) and raw_goal_text.strip() != effective_goal_text.strip():
                notes.append("raw_goal_direction_softened_by_source_guard")
                scoring_reasons.append("raw_goal_direction_softened_by_source_guard")
            if item.decision_type in blocked_types:
                notes.append("user_constraint_blocks_decision_type")
                scoring_reasons.append("blocked_by_constraint")
            if not item.evidence_ids:
                notes.append("missing_issue_evidence")
                scoring_reasons.append("missing_issue_evidence")
            if item.issue_ids and item.evidence_ids:
                scoring_reasons.append("source_grounded_decision")
            if missing_context_count:
                scoring_reasons.append("missing_context_penalty")
            risk_score = normalize_unit_interval((severity / 5.0) * 0.55 + (blast_radius / 5.0) * 0.45)
            urgency_score = normalize_unit_interval((severity / 5.0) * 0.45 + (blast_radius / 5.0) * 0.35 + (evidence_strength * 0.2))
            maintainability_score = normalize_unit_interval(
                (maintainability_gain * 0.5)
                + (contract_stability * 0.25)
                + (input_sufficiency * 0.25)
            )
            confidence_penalty = 0.0
            if not item.evidence_ids:
                confidence_penalty += 0.25
            if item.decision_type in blocked_types:
                confidence_penalty += 0.2
            if missing_context_count >= 2:
                confidence_penalty += 0.1
            elif missing_context_count == 1:
                confidence_penalty += 0.05
            if raw_goal_signal_detected and not goal_signal_applied:
                confidence_penalty += 0.05
            confidence_score = normalize_unit_interval(
                (evidence_strength * 0.4)
                + (input_sufficiency * 0.2)
                + (issue_confidence * 0.2)
                + (contract_stability * 0.2)
                - confidence_penalty
            )
            recommendation_strength = self._recommendation_strength_for_basis(
                confidence_score=confidence_score,
                evidence_strength_score=evidence_strength,
                input_sufficiency=input_sufficiency,
                blocked=bool(item.decision_type in blocked_types),
                has_evidence=bool(item.evidence_ids),
            )
            bases.append(
                DecisionBasis(
                    decision_id=item.decision_id,
                    issue_ids=list(item.issue_ids or []),
                    decision_type=item.decision_type,
                    criteria=JudgmentCriteria(
                        evidence_strength=evidence_strength,
                        input_sufficiency=round(input_sufficiency, 2),
                        change_cost=change_cost,
                        delivery_speed=delivery_speed,
                        maintainability_gain=maintainability_gain,
                        contract_stability=contract_stability,
                        notes=notes,
                    ),
                    evidence_ids=list(item.evidence_ids or []),
                    source_grounded=bool(item.issue_ids and item.evidence_ids),
                    goal_signal_detected=raw_goal_signal_detected,
                    goal_signal_applied=goal_signal_applied,
                    asset_signal_detected=asset_signal_detected,
                    blocked_recommendation_types=sorted(blocked_types),
                    evidence_strength_score=evidence_strength,
                    risk_score=risk_score,
                    urgency_score=urgency_score,
                    maintainability_score=maintainability_score,
                    confidence_score=confidence_score,
                    recommendation_strength=recommendation_strength,
                    scoring_reasons=scoring_reasons,
                    summary=(
                        f"{item.decision_type} 판단은 issue={','.join(item.issue_ids) or '-'} "
                        f"evidence={len(item.evidence_ids)} priority={item.priority_score} "
                        f"strength={recommendation_strength}"
                    ),
                )
            )
        return bases

    def _recommendation_strength_for_basis(
        self,
        *,
        confidence_score: float,
        evidence_strength_score: float,
        input_sufficiency: float,
        blocked: bool,
        has_evidence: bool,
    ) -> str:
        if blocked or not has_evidence:
            return "blocked"
        if confidence_score >= 0.7 and evidence_strength_score >= 0.65 and input_sufficiency >= 0.6:
            return "assertive"
        if confidence_score >= 0.5 and evidence_strength_score >= 0.45:
            return "conditional"
        return "review_required"

    def _detect_decision_conflicts(
        self,
        prepared: Any,
        *,
        diagnosis: DiagnosisArtifacts,
        decisions: list[DecisionRecord],
        decision_basis: list[DecisionBasis],
    ) -> list[DecisionConflict]:
        del diagnosis
        conflicts: list[DecisionConflict] = []
        guarded = getattr(prepared, "guarded_decision_input", None)
        raw_goal = self._raw_goal_text(prepared)
        effective_goal = self._effective_goal_text(prepared)
        source_guard_applied = bool(
            guarded is not None
            and getattr(guarded, "applied_question_source", "uninitialized") != "uninitialized"
            and list(getattr(guarded, "selected_questions", []) or [])
        )
        raw_goal_signal_detected = self._raw_goal_prefers_migration(prepared)
        goal_signal_applied = self._goal_prefers_migration(prepared)
        asset_signal_detected = self._has_asset_migration_support(prepared)
        if (
            source_guard_applied
            and self._raw_goal_forces_direction(prepared)
            and raw_goal.strip()
            and effective_goal.strip()
            and raw_goal.strip() != effective_goal.strip()
            and (
                (raw_goal_signal_detected and not goal_signal_applied and not asset_signal_detected)
                or not raw_goal_signal_detected
            )
        ):
            conflicts.append(
                DecisionConflict(
                    conflict_id=make_stable_id("DCF", "goal_source_mismatch", raw_goal, effective_goal),
                    conflict_type="goal_source_mismatch",
                    severity="review_required",
                    summary="사용자 질문의 방향 강제 신호가 있었지만 source evidence가 약하거나 불충분해 판단 축에는 직접 반영하지 않았습니다.",
                    issue_ids=[],
                    decision_ids=[],
                    evidence_ids=[],
                    resolution_hint="source-derived question axis와 evidence를 기준으로만 전략을 확정해야 합니다.",
                )
            )
        top_decisions = list(decisions[:2])
        if len(top_decisions) >= 2:
            leading_types = {item.decision_type for item in top_decisions}
            score_gap = abs(top_decisions[0].priority_score - top_decisions[1].priority_score)
            if (
                len(leading_types) >= 2
                and score_gap <= 2
                and "migration_consideration" in leading_types
                and (raw_goal_signal_detected or goal_signal_applied)
            ):
                evidence_ids: list[str] = []
                for basis in decision_basis:
                    if basis.decision_id in {top_decisions[0].decision_id, top_decisions[1].decision_id}:
                        evidence_ids.extend(list(basis.evidence_ids or []))
                conflicts.append(
                    DecisionConflict(
                        conflict_id=make_stable_id("DCF", "strategy_tradeoff", *(item.decision_id for item in top_decisions)),
                        conflict_type="strategy_tradeoff",
                        severity="review_required",
                        summary="상위 전략 후보의 점수가 근접해 refactor/redesign 또는 migration 판단을 단정하기 어렵습니다.",
                        issue_ids=[issue_id for item in top_decisions for issue_id in list(item.issue_ids or [])],
                        decision_ids=[item.decision_id for item in top_decisions],
                        evidence_ids=list(dict.fromkeys(item for item in evidence_ids if item)),
                        resolution_hint="상위 후보 간 추가 evidence 또는 제약 확인 전까지 조건부 판단으로 유지해야 합니다.",
                    )
                )
        return conflicts

    def _apply_conflict_strength_adjustments(
        self,
        decision_basis: list[DecisionBasis],
        conflicts: list[DecisionConflict],
    ) -> list[DecisionBasis]:
        if not decision_basis or not conflicts:
            return decision_basis
        conflict_index: dict[str, list[DecisionConflict]] = {}
        global_conflicts: list[DecisionConflict] = []
        for item in conflicts:
            if item.decision_ids:
                for decision_id in item.decision_ids:
                    normalized = str(decision_id or "").strip()
                    if normalized:
                        conflict_index.setdefault(normalized, []).append(item)
            else:
                global_conflicts.append(item)
        updated: list[DecisionBasis] = []
        for basis in decision_basis:
            related_conflicts = list(conflict_index.get(basis.decision_id, []))
            if global_conflicts:
                related_conflicts.extend(global_conflicts)
            recommendation_strength = basis.recommendation_strength
            if any(item.severity == "blocking" for item in related_conflicts):
                recommendation_strength = "blocked"
            elif any(item.severity == "review_required" for item in related_conflicts):
                recommendation_strength = max_recommendation_strength(recommendation_strength, "review_required")
            elif any(item.severity == "warning" for item in related_conflicts):
                recommendation_strength = max_recommendation_strength(recommendation_strength, "conditional")
            scoring_reasons = list(basis.scoring_reasons or [])
            for item in related_conflicts:
                marker = f"conflict:{item.conflict_type}"
                if marker not in scoring_reasons:
                    scoring_reasons.append(marker)
            updated.append(
                basis.model_copy(
                    update={
                        "recommendation_strength": recommendation_strength,
                        "scoring_reasons": scoring_reasons,
                    }
                )
            )
        return updated

    def _build_summary(self, prepared: Any, decisions: list[DecisionRecord], *, conflicts: list[DecisionConflict] | None = None) -> DecisionSummary:
        if not decisions:
            return DecisionSummary(
                recommended_strategy="리팩터링 우선",
                priority_queue=[],
                conditional=bool(conflicts),
                review_required=any(item.severity in {"review_required", "blocking"} for item in list(conflicts or [])),
                conflict_ids=[item.conflict_id for item in list(conflicts or [])],
            )
        redesign_count = sum(1 for item in decisions if item.decision_type == "redesign")
        migration_count = sum(1 for item in decisions if item.decision_type == "migration_consideration")
        if self._should_prioritize_operational_analysis(prepared):
            strategy = "리팩터링 우선"
        elif migration_count and decisions[0].decision_type == "migration_consideration":
            strategy = "마이그레이션 고려"
        elif redesign_count:
            strategy = "재설계 우선"
        else:
            strategy = "리팩터링 우선"
        return DecisionSummary(
            decisions=decisions,
            recommended_strategy=strategy,
            priority_queue=[item.decision_id for item in decisions],
            conditional=bool(conflicts),
            review_required=any(item.severity in {"review_required", "blocking"} for item in list(conflicts or [])),
            conflict_ids=[item.conflict_id for item in list(conflicts or [])],
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

    def _can_use_operational_analysis_profile(self, prepared: Any) -> bool:
        return hasattr(prepared, "assets") and hasattr(prepared, "asset_presence")

    def _should_prioritize_operational_analysis(self, prepared: Any) -> bool:
        family_classification = getattr(prepared, "family_classification", None)
        if str(getattr(family_classification, "family", "") or "").strip() == "operational_source":
            return True
        if not self._can_use_operational_analysis_profile(prepared):
            return False
        return bool(self.template_support._has_operational_source_analysis_priority(prepared))
