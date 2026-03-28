from datetime import datetime, timezone

from agent.transaction_runtime import (
    _write_transaction_runtime_state,
    load_transaction_runtime_state,
)
from agent.workspace_metrics import build_apply_state_machine, build_transaction_markers

VALID_MARKERS = set(build_transaction_markers().get("markers", []))
TERMINAL_MARKERS = {"apply_succeeded", "rollback_completed"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_terminal_marker(marker: str) -> bool:
    return marker in TERMINAL_MARKERS


def derive_state_from_marker(marker: str) -> str:
    mapping = {
        "apply_started": "apply_started",
        "apply_failed": "apply_failed",
        "apply_succeeded": "apply_succeeded",
        "rollback_started": "rollback_required",
        "rollback_completed": "rollback_completed",
    }
    return mapping.get(marker, "halted_for_manual_review")


def validate_marker_transition(
    current_state: str,
    marker: str,
    runtime_state: dict,
    executor_spec: dict | None = None,
) -> dict:
    del executor_spec
    if marker not in VALID_MARKERS:
        return {"valid": False, "reason": "invalid_marker"}
    if runtime_state.get("terminal_marker"):
        return {"valid": False, "reason": "terminal_marker_already_recorded"}
    if runtime_state.get("state") == "halted_for_manual_review":
        return {"valid": False, "reason": "halted_for_manual_review"}
    existing_markers = {entry.get("marker") for entry in runtime_state.get("markers", [])}
    if marker in existing_markers:
        return {"valid": False, "reason": "duplicate_marker"}

    if marker == "apply_started" and current_state != "validation_passed":
        return {"valid": False, "reason": "apply_started_requires_validation_passed", "halt": True}
    if marker == "apply_succeeded" and current_state not in {"validation_passed", "apply_started"}:
        return {"valid": False, "reason": "success_requires_validation_passed", "halt": True}
    if marker == "apply_failed" and current_state not in {"apply_started", "validation_passed"}:
        return {"valid": False, "reason": "failure_requires_started_or_validated", "halt": True}
    if marker == "rollback_started" and current_state not in {"apply_failed", "rollback_required"}:
        return {"valid": False, "reason": "rollback_start_requires_failure_state", "halt": True}
    if marker == "rollback_completed" and current_state != "rollback_required":
        return {"valid": False, "reason": "rollback_complete_requires_rollback_required", "halt": True}

    allowed_transitions = build_apply_state_machine().get("allowed_transitions", {})
    derived_state = derive_state_from_marker(marker)
    if current_state in allowed_transitions and derived_state not in allowed_transitions[current_state] and marker != "rollback_started":
        return {"valid": False, "reason": "marker_state_transition_not_allowed", "halt": True}

    return {"valid": True, "reason": "valid", "derived_state": derived_state}


def can_record_marker(runtime_state: dict, marker: str) -> dict:
    return validate_marker_transition(runtime_state.get("state", "unknown"), marker, runtime_state)


def record_transaction_marker(
    transaction_id: str,
    marker: str,
    *,
    details: dict | None = None,
    reference=None,
    executor_spec: dict | None = None,
) -> dict:
    runtime_state = load_transaction_runtime_state(transaction_id, reference=reference)
    if runtime_state is None:
        return {"recorded": False, "reason": "runtime_state_missing", "runtime_state": None}

    validation = validate_marker_transition(
        runtime_state.get("state", "unknown"),
        marker,
        runtime_state,
        executor_spec=executor_spec,
    )
    if not validation.get("valid"):
        if validation.get("reason") in {"duplicate_marker", "terminal_marker_already_recorded", "halted_for_manual_review"}:
            return {"recorded": False, "reason": validation["reason"], "runtime_state": runtime_state}
        runtime_state["state"] = "halted_for_manual_review"
        runtime_state.setdefault("runtime_notes", []).append(
            f"marker_rejected:{marker}:{validation.get('reason', 'invalid_transition')}"
        )
        runtime_state["last_updated_at"] = _timestamp()
        _write_transaction_runtime_state(runtime_state, reference=reference)
        return {"recorded": False, "reason": validation["reason"], "runtime_state": runtime_state}

    runtime_state.setdefault("markers", []).append(
        {
            "marker": marker,
            "recorded_at": _timestamp(),
            "details": details or {},
        }
    )
    runtime_state["state"] = validation.get("derived_state", derive_state_from_marker(marker))
    if is_terminal_marker(marker):
        runtime_state["terminal_marker"] = marker
    runtime_state["last_updated_at"] = _timestamp()
    _write_transaction_runtime_state(runtime_state, reference=reference)
    return {"recorded": True, "reason": "recorded", "runtime_state": runtime_state}
