from __future__ import annotations

from typing import Any

from .runtime_contracts import StageControlViolation, assert_stage_action
from .schemas import (
    DecisionConflict,
    DecisionValidationIssue,
    DecisionValidationResult,
)


class ValidationEngine:
    def coerce_result(self, payload: Any) -> DecisionValidationResult:
        return DecisionValidationResult.coerce(payload)

    def validate_decision(
        self,
        *,
        prepared: Any,
        diagnosis,
        decisions,
        stage_control: dict[str, object] | None,
    ) -> DecisionValidationResult:
        issues: list[DecisionValidationIssue] = []
        conflicts: list[DecisionConflict] = []
        missing_evidence: list[str] = []
        try:
            assert_stage_action(
                stage_control or getattr(prepared, "stage_control", None),
                expected_stage="decision",
                action="validate_decision_output",
                goal=str(getattr(prepared, "goal", "") or ""),
            )
        except StageControlViolation as exc:
            issues.append(
                DecisionValidationIssue(
                    issue_code="stage_control_violation",
                    severity="blocking",
                    message=str(exc) or "stage_control mismatch detected",
                )
            )

        evidence_index = list(getattr(diagnosis, "evidence_index", []) or [])
        evidence_ids = {
            str(getattr(item, "evidence_id", "") or "")
            for item in evidence_index
            if str(getattr(item, "evidence_id", "") or "").strip()
        }
        decision_records = list(getattr(getattr(decisions, "decision_summary", None), "decisions", []) or [])
        if decision_records:
            if not evidence_ids:
                missing_evidence.append("diagnosis_evidence_index_empty")
            elif any(not list(getattr(item, "evidence_ids", []) or []) for item in decision_records):
                missing_evidence.append("decision_missing_evidence_refs")
            elif any(
                any(str(evidence_id or "") not in evidence_ids for evidence_id in list(getattr(item, "evidence_ids", []) or []))
                for item in decision_records
            ):
                missing_evidence.append("decision_evidence_ref_out_of_index")
        if missing_evidence:
            issues.append(
                DecisionValidationIssue(
                    issue_code="evidence_insufficient",
                    severity="blocking",
                    message="decision evidence is insufficient or detached from diagnosis evidence_index",
                    decision_ids=[str(getattr(item, "decision_id", "") or "") for item in decision_records],
                    evidence_ids=sorted(evidence_ids),
                )
            )

        issue_decision_types: dict[str, set[str]] = {}
        for item in decision_records:
            decision_type = str(getattr(item, "decision_type", "") or "")
            for issue_id in list(getattr(item, "issue_ids", []) or []):
                normalized_issue_id = str(issue_id or "").strip()
                if not normalized_issue_id:
                    continue
                issue_decision_types.setdefault(normalized_issue_id, set()).add(decision_type)
        recommended_strategy = str(getattr(getattr(decisions, "decision_summary", None), "recommended_strategy", "") or "").strip()
        if any(len(decision_types) > 1 for decision_types in issue_decision_types.values()):
            conflicts.append(
                DecisionConflict(
                    conflict_id="validation-issue-type-conflict",
                    conflict_type="judgment_conflict",
                    severity="blocking",
                    summary="single issue is linked to multiple decision types",
                    issue_ids=[issue_id for issue_id, decision_types in issue_decision_types.items() if len(decision_types) > 1],
                    resolution_hint="dedupe conflicting issue decisions and keep the strongest evidence-backed decision only",
                )
            )
        elif "마이그레이션" in recommended_strategy and not any(
            str(getattr(item, "decision_type", "") or "") == "migration_consideration"
            for item in decision_records
        ):
            conflicts.append(
                DecisionConflict(
                    conflict_id="validation-strategy-record-mismatch",
                    conflict_type="judgment_conflict",
                    severity="blocking",
                    summary="recommended strategy says migration but supporting decision record is missing",
                    decision_ids=[str(getattr(item, "decision_id", "") or "") for item in decision_records],
                    resolution_hint="align recommended strategy with evidence-backed decision records",
                )
            )

        provided_conflicts = list(getattr(decisions, "conflicts", []) or [])
        for item in provided_conflicts:
            if isinstance(item, DecisionConflict):
                conflicts.append(item)
            else:
                conflicts.append(DecisionConflict.model_validate(item))

        blocked_types = {
            str(item or "").strip()
            for item in list(getattr(prepared, "decision_constraint_filters", []) or [])
            if str(item or "").strip()
        }
        if any(str(getattr(item, "decision_type", "") or "") in blocked_types for item in decision_records):
            issues.append(
                DecisionValidationIssue(
                    issue_code="forbidden_condition_violation",
                    severity="blocking",
                    message="blocked decision type leaked into final decision set",
                    decision_ids=[
                        str(getattr(item, "decision_id", "") or "")
                        for item in decision_records
                        if str(getattr(item, "decision_type", "") or "") in blocked_types
                    ],
                )
            )

        for item in conflicts:
            if item.severity in {"blocking", "review_required"}:
                issues.append(
                    DecisionValidationIssue(
                        issue_code=item.conflict_type,
                        severity=item.severity,
                        message=item.summary,
                        issue_ids=list(item.issue_ids or []),
                        decision_ids=list(item.decision_ids or []),
                        evidence_ids=list(item.evidence_ids or []),
                    )
                )

        failure_types = list(
            dict.fromkeys(
                item.issue_code
                for item in issues
                if item.severity == "blocking" and str(item.issue_code or "").strip()
            )
        )
        passed = not failure_types
        blocking_reason = next((item.message for item in issues if item.severity == "blocking" and item.message), None)
        retry_recommended = any(
            item.severity == "blocking"
            and item.issue_code in {
                "stage_control_violation",
                "forbidden_condition_violation",
                "judgment_conflict",
                "evidence_insufficient",
            }
            for item in issues
        )
        deduped_conflicts: list[DecisionConflict] = []
        seen_conflict_ids: set[str] = set()
        for item in conflicts:
            conflict_key = str(item.conflict_id or "").strip() or item.model_dump_json()
            if conflict_key in seen_conflict_ids:
                continue
            seen_conflict_ids.add(conflict_key)
            deduped_conflicts.append(item)
        return DecisionValidationResult(
            passed=passed,
            issues=issues,
            conflicts=deduped_conflicts,
            missing_evidence=list(dict.fromkeys(missing_evidence)),
            retry_recommended=retry_recommended,
            blocking_reason=blocking_reason if not passed else None,
            status="pass" if passed else "fail",
            failure_types=failure_types,
            retry_hint=self._retry_hint(failure_types),
        )

    def _retry_hint(self, failure_types: list[str]) -> str:
        if not failure_types:
            return ""
        if "stage_control_violation" in failure_types:
            return "stage_control mismatch detected; rerun only in decision stage."
        if "forbidden_condition_violation" in failure_types:
            return "forbidden condition detected; filter blocked decision types and rerun."
        if "judgment_conflict" in failure_types:
            return "judgment conflict detected; dedupe conflicting issue decisions and rerun."
        if "evidence_insufficient" in failure_types:
            return "evidence is insufficient; keep only evidence-grounded decisions and rerun."
        return "validation failed; rerun decision engine once."
