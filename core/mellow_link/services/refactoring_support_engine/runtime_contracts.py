from __future__ import annotations

from copy import deepcopy


class StageControlViolation(ValueError):
    """Raised when an engine produces output outside its declared stage."""


_STAGE_ACTIONS: dict[str, list[str]] = {
    "analysis": [
        "assemble_analysis_input",
        "generate_structure_snapshot",
    ],
    "diagnosis": [
        "generate_diagnosis_report",
    ],
    "decision": [
        "generate_decision_summary",
        "validate_decision_output",
        "retry_decision_output",
    ],
    "planning": [
        "generate_improvement_plan",
        "package_result",
        "augment_narrative",
    ],
}
_ALL_ACTIONS = sorted({action for actions in _STAGE_ACTIONS.values() for action in actions})


def build_stage_control(goal: str, current_stage: str = "analysis") -> dict[str, object]:
    control = {
        "current_stage": "analysis",
        "goal": str(goal or ""),
        "allowed_actions": [],
        "forbidden_actions": [],
    }
    return enter_stage(control, current_stage)


def coerce_stage_control(
    stage_control: dict[str, object] | None,
    *,
    goal: str = "",
    default_stage: str = "analysis",
) -> dict[str, object]:
    if isinstance(stage_control, dict):
        normalized = deepcopy(stage_control)
        normalized["goal"] = str(normalized.get("goal") or goal or "")
        return enter_stage(
            normalized,
            str(normalized.get("current_stage") or default_stage or "analysis"),
        )
    return build_stage_control(goal, current_stage=default_stage)


def enter_stage(stage_control: dict[str, object], stage: str) -> dict[str, object]:
    normalized_stage = str(stage or "").strip().lower() or "analysis"
    if normalized_stage not in _STAGE_ACTIONS:
        raise StageControlViolation(f"unsupported stage: {normalized_stage}")
    allowed_actions = list(_STAGE_ACTIONS[normalized_stage])
    forbidden_actions = [action for action in _ALL_ACTIONS if action not in allowed_actions]
    stage_control["current_stage"] = normalized_stage
    stage_control["allowed_actions"] = allowed_actions
    stage_control["forbidden_actions"] = forbidden_actions
    stage_control["goal"] = str(stage_control.get("goal") or "")
    return stage_control


def assert_stage_action(
    stage_control: dict[str, object] | None,
    *,
    expected_stage: str,
    action: str,
    goal: str = "",
) -> dict[str, object]:
    control = coerce_stage_control(stage_control, goal=goal, default_stage=expected_stage)
    current_stage = str(control.get("current_stage") or "")
    if current_stage != expected_stage:
        raise StageControlViolation(
            f"stage_control violation: action '{action}' requires stage '{expected_stage}', current '{current_stage}'"
        )
    allowed_actions = {str(item or "") for item in list(control.get("allowed_actions") or [])}
    forbidden_actions = {str(item or "") for item in list(control.get("forbidden_actions") or [])}
    if action in forbidden_actions or (allowed_actions and action not in allowed_actions):
        raise StageControlViolation(
            f"stage_control violation: action '{action}' is not allowed in stage '{current_stage}'"
        )
    return control


def snapshot_stage_control(stage_control: dict[str, object] | None, *, goal: str = "") -> dict[str, object]:
    control = coerce_stage_control(stage_control, goal=goal)
    return {
        "current_stage": str(control.get("current_stage") or ""),
        "goal": str(control.get("goal") or ""),
        "allowed_actions": list(control.get("allowed_actions") or []),
        "forbidden_actions": list(control.get("forbidden_actions") or []),
    }
