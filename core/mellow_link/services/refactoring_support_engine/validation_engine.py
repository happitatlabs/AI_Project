from __future__ import annotations

from typing import Any

from .runtime_contracts import StageControlViolation, assert_stage_action


class ValidationEngine:
    def validate_decision(
        self,
        *,
        prepared: Any,
        diagnosis,
        decisions,
        stage_control: dict[str, object] | None,
    ) -> dict[str, Any]:
        failure_types: list[str] = []
        try:
            assert_stage_action(
                stage_control or getattr(prepared, "stage_control", None),
                expected_stage="decision",
                action="validate_decision_output",
                goal=str(getattr(prepared, "goal", "") or ""),
            )
        except StageControlViolation:
            failure_types.append("stage_control_violation")

        evidence_index = list(getattr(diagnosis, "evidence_index", []) or [])
        evidence_ids = {
            str(getattr(item, "evidence_id", "") or "")
            for item in evidence_index
            if str(getattr(item, "evidence_id", "") or "").strip()
        }
        decision_records = list(getattr(getattr(decisions, "decision_summary", None), "decisions", []) or [])
        if decision_records:
            if not evidence_ids:
                failure_types.append("evidence_insufficient")
            elif any(not list(getattr(item, "evidence_ids", []) or []) for item in decision_records):
                failure_types.append("evidence_insufficient")
            elif any(
                any(str(evidence_id or "") not in evidence_ids for evidence_id in list(getattr(item, "evidence_ids", []) or []))
                for item in decision_records
            ):
                failure_types.append("evidence_insufficient")

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
            failure_types.append("judgment_conflict")
        elif "마이그레이션" in recommended_strategy and not any(
            str(getattr(item, "decision_type", "") or "") == "migration_consideration"
            for item in decision_records
        ):
            failure_types.append("judgment_conflict")

        blocked_types = {
            str(item or "").strip()
            for item in list(getattr(prepared, "decision_constraint_filters", []) or [])
            if str(item or "").strip()
        }
        if any(str(getattr(item, "decision_type", "") or "") in blocked_types for item in decision_records):
            failure_types.append("forbidden_condition_violation")

        deduped_failures = list(dict.fromkeys(failure_types))
        return {
            "status": "fail" if deduped_failures else "pass",
            "failure_types": deduped_failures,
            "retry_hint": self._retry_hint(deduped_failures),
        }

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
