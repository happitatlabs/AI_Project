import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .execution_mode import resolve_execution_mode
from .risk_evaluator import evaluate_skill_risk
from .skill_selection import (
    build_skill_selection_input,
    build_skill_selection_report,
    collect_available_skills,
    select_skill_for_task,
)
from .workspace_metrics import resolve_runtime_data_root


BRAIN_PROPOSALS_DIRNAME = "brain_proposals"
LLM_SELECTOR_ALLOWED_KEYS = {
    "selected_skill",
    "reason",
    "confidence",
    "alternative_candidates",
}
LLM_SELECTOR_FORBIDDEN_KEYS = {
    "action",
    "command",
    "execute",
    "next_step",
    "plan",
    "tool",
    "tool_call",
}
LLM_SELECTOR_ALLOWED_CONFIDENCE = {"low", "medium", "high"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brain_directories(reference: str | Path | None = None) -> dict[str, Path]:
    runtime_root = resolve_runtime_data_root(reference)
    return {
        "runtime_root": runtime_root,
        "brain_proposals": runtime_root / BRAIN_PROPOSALS_DIRNAME,
    }


def _ensure_brain_directories(reference: str | Path | None = None) -> dict[str, Path]:
    directories = _brain_directories(reference)
    directories["brain_proposals"].mkdir(parents=True, exist_ok=True)
    return directories


def _brain_proposal_path(run_id: str, *, reference: str | Path | None = None) -> Path:
    return _brain_directories(reference)["brain_proposals"] / f"{run_id}.json"


def _write_json(path: Path, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_id() -> str:
    return f"brain_run_{uuid4().hex[:12]}"


def build_recent_runtime_state_summary(current_state: dict | None) -> dict:
    current_state = current_state or {}
    gate_view = current_state.get("operational_gate_view") or {}
    return {
        "total_files": current_state.get("total_files", 0),
        "decision_total_files": current_state.get("decision_total_files", 0),
        "total_dirs": current_state.get("total_dirs", 0),
        "changed_paths": len(current_state.get("state_diff", {}).get("added_paths", []))
        + len(current_state.get("state_diff", {}).get("removed_paths", [])),
        "operational_gate_mode": gate_view.get("gate_mode"),
        "operational_gate_action": gate_view.get("recommended_action"),
        "operational_gate_target": gate_view.get("target"),
    }


def build_past_skill_memory_from_recent_actions(recent_actions: list[dict] | None) -> dict[str, dict]:
    memory: dict[str, dict] = {}
    for entry in recent_actions or []:
        skill_id = str(entry.get("skill") or entry.get("skill_id") or "").strip()
        if not skill_id:
            continue
        bucket = memory.setdefault(skill_id, {"success": 0, "failure": 0})
        outcome = str(entry.get("outcome") or "success").strip().lower()
        if outcome in {"failed", "failure", "error"}:
            bucket["failure"] += 1
        else:
            bucket["success"] += 1
    return memory


def build_llm_skill_selector_input(
    *,
    task_description: str,
    available_skills: list[dict],
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
) -> dict:
    return build_skill_selection_input(
        task_description=task_description,
        available_skills=available_skills,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
    )


def validate_llm_skill_selector_output(
    payload,
    *,
    available_skills: list[dict],
) -> dict:
    errors: list[str] = []
    normalized_output = {
        "selected_skill": None,
        "reason": "",
        "confidence": "low",
        "alternative_candidates": [],
    }

    if not isinstance(payload, dict):
        errors.append("llm selector output must be a JSON object")
        return {
            "valid": False,
            "errors": errors,
            "normalized_output": normalized_output,
        }

    keys = set(payload)
    if keys - LLM_SELECTOR_ALLOWED_KEYS:
        errors.append("llm selector output contains unsupported keys")
    if keys & LLM_SELECTOR_FORBIDDEN_KEYS:
        errors.append("llm selector output contains execution-oriented keys")

    selected_skill = str(payload.get("selected_skill") or "").strip()
    available_ids = {
        str(candidate.get("skill_id") or "")
        for candidate in available_skills
    }
    if not selected_skill:
        errors.append("selected_skill is required")
    elif selected_skill not in available_ids:
        errors.append("selected_skill must reference an available skill candidate")
    normalized_output["selected_skill"] = selected_skill or None

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        errors.append("reason is required")
    normalized_output["reason"] = reason

    confidence = str(payload.get("confidence") or "").strip().lower()
    if confidence not in LLM_SELECTOR_ALLOWED_CONFIDENCE:
        errors.append("confidence must be one of: low, medium, high")
        confidence = "low"
    normalized_output["confidence"] = confidence

    alternatives = payload.get("alternative_candidates", [])
    if alternatives is None:
        alternatives = []
    if not isinstance(alternatives, list):
        errors.append("alternative_candidates must be a list")
        alternatives = []
    normalized_output["alternative_candidates"] = [
        str(candidate).strip()
        for candidate in alternatives
        if str(candidate).strip()
    ][:3]

    return {
        "valid": not errors,
        "errors": errors,
        "normalized_output": normalized_output,
    }


def build_agent_brain_input(
    *,
    task_description: str,
    reference: str | Path | None = None,
    skills_dir: str | Path | None = None,
    available_skills: list[dict] | None = None,
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
) -> dict:
    candidates = available_skills or collect_available_skills(
        reference=reference,
        skills_dir=skills_dir,
    )
    return build_llm_skill_selector_input(
        task_description=task_description,
        available_skills=candidates,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
    )


def _wrap_llm_selector(llm_selector, available_skills: list[dict]):
    if llm_selector is None:
        return None

    def _validated_selector(selection_input: dict):
        try:
            raw_output = llm_selector(selection_input)
        except Exception:
            return None
        report = validate_llm_skill_selector_output(
            raw_output,
            available_skills=available_skills,
        )
        if not report["valid"]:
            return None
        return report["normalized_output"]

    return _validated_selector


def run_agent_brain_selection(
    *,
    task_description: str,
    reference: str | Path | None = None,
    skills_dir: str | Path | None = None,
    available_skills: list[dict] | None = None,
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
    execution_flags: dict | None = None,
    llm_selector=None,
) -> dict:
    candidates = available_skills or collect_available_skills(
        reference=reference,
        skills_dir=skills_dir,
    )
    selection_input = build_agent_brain_input(
        task_description=task_description,
        reference=reference,
        skills_dir=skills_dir,
        available_skills=candidates,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
    )
    selection = select_skill_for_task(
        task_description=task_description,
        available_skills=candidates,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
        reference=reference,
        skills_dir=skills_dir,
        llm_selector=_wrap_llm_selector(llm_selector, candidates),
    )
    selected_skill_id = selection.get("selected_skill")
    selected_candidate = next(
        (candidate for candidate in candidates if candidate.get("skill_id") == selected_skill_id),
        None,
    )
    risk_summary = None
    risk_warnings: list[str] = []
    if selected_skill_id:
        try:
            risk_summary = evaluate_skill_risk(
                str(selected_skill_id),
                reference=reference,
            )
        except Exception as exc:
            risk_warnings.append(f"risk summary unavailable: {exc}")
    return {
        "run_id": _run_id(),
        "task_description": task_description,
        "selection": build_skill_selection_report(selection),
        "risk_summary": risk_summary,
        "risk_warnings": risk_warnings,
        "selection_input": selection_input,
        "selected_candidate": selected_candidate,
        "execution_mode": resolve_execution_mode(execution_flags).value,
        "created_at": _timestamp(),
        "proposal_status": "selected" if selected_candidate else "no_candidate",
    }


def save_agent_brain_proposal(
    proposal: dict,
    *,
    reference: str | Path | None = None,
) -> dict:
    _ensure_brain_directories(reference)
    path = _brain_proposal_path(proposal["run_id"], reference=reference)
    saved = dict(proposal)
    _write_json(path, saved)
    return {
        "saved": True,
        "path": str(path),
        "proposal": saved,
    }


def load_agent_brain_proposal(
    run_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_brain_proposal_path(run_id, reference=reference))


def build_agent_brain_proposal_report(
    proposal_or_run_id,
    *,
    reference: str | Path | None = None,
) -> str:
    proposal = proposal_or_run_id
    if not isinstance(proposal, dict):
        proposal = load_agent_brain_proposal(str(proposal_or_run_id), reference=reference)
    if proposal is None:
        return f"brain proposal not found: {proposal_or_run_id}"

    selection = proposal.get("selection") or {}
    risk_summary = proposal.get("risk_summary") or {}
    lines = [
        "[Selection]",
        f"- selected_skill: {selection.get('selected_skill', 'none')}",
        f"- selection_reason: {selection.get('reason', 'none')}",
        f"- selection_confidence: {selection.get('confidence', 'low')}",
        "",
        "[Risk Summary]",
    ]
    if risk_summary:
        lines.extend(
            [
                f"- risk_level: {risk_summary.get('risk_level', 'unknown')}",
                f"- recommended_path: {' -> '.join(str(item) for item in risk_summary.get('recommended_path', [])) or 'none'}",
                f"- allowed_skips: {', '.join(str(item) for item in risk_summary.get('allowed_skips', [])) or 'none'}",
                f"- required_stages: {', '.join(str(item) for item in risk_summary.get('required_stages', [])) or 'none'}",
                f"- risk_reason: {risk_summary.get('reason', 'none')}",
                f"- risk_confidence: {risk_summary.get('confidence', 'low')}",
            ]
        )
    else:
        lines.append("- status: unavailable")
    warnings = proposal.get("risk_warnings") or []
    if warnings:
        lines.extend(["", "[Warnings]"])
        for item in warnings:
            lines.append(f"- {item}")
    return "\n".join(lines)
