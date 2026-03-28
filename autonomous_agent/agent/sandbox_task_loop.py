import json
from datetime import datetime, timezone
from pathlib import Path

from .agent_brain import (
    load_agent_brain_proposal,
    run_agent_brain_selection,
    save_agent_brain_proposal,
)
from .execution_mode import build_experimental_sandbox_gate
from .generated_skill_sandbox import (
    load_generated_skill_draft,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
)
from .workspace_metrics import resolve_runtime_data_root


TASK_HISTORY_DIRNAME = "task_history"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_loop_directories(reference: str | Path | None = None) -> dict[str, Path]:
    runtime_root = resolve_runtime_data_root(reference)
    return {
        "runtime_root": runtime_root,
        "task_history": runtime_root / TASK_HISTORY_DIRNAME,
    }


def _ensure_task_loop_directories(reference: str | Path | None = None) -> dict[str, Path]:
    directories = _task_loop_directories(reference)
    directories["task_history"].mkdir(parents=True, exist_ok=True)
    return directories


def _task_history_path(run_id: str, *, reference: str | Path | None = None) -> Path:
    return _task_loop_directories(reference)["task_history"] / f"{run_id}.json"


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


def save_sandbox_task_result(
    payload: dict,
    *,
    reference: str | Path | None = None,
) -> dict:
    _ensure_task_loop_directories(reference)
    path = _task_history_path(payload["run_id"], reference=reference)
    record = dict(payload)
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "task_result": record,
    }


def load_sandbox_task_result(
    run_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_task_history_path(run_id, reference=reference))


def build_task_history_memory(
    *,
    reference: str | Path | None = None,
) -> dict[str, dict]:
    history_dir = _task_loop_directories(reference)["task_history"]
    memory: dict[str, dict] = {}
    if not history_dir.exists():
        return memory

    for path in sorted(history_dir.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        skill_id = str(payload.get("selected_skill") or "").strip()
        if not skill_id:
            continue
        if payload.get("blocked"):
            continue
        bucket = memory.setdefault(skill_id, {"success": 0, "failure": 0})
        if payload.get("sandbox_result") == "passed":
            bucket["success"] += 1
        elif payload.get("sandbox_result") == "failed":
            bucket["failure"] += 1
    return memory


def _clone_generated_skill_to_isolated_runtime(
    skill_id: str,
    *,
    sandbox_root: str | Path,
    reference: str | Path | None = None,
    run_id: str,
) -> dict:
    original_draft = load_generated_skill_draft(skill_id, reference=reference)
    if original_draft is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    isolated_reference = Path(sandbox_root) / f"{run_id}_reference" / "pending_approvals.json"
    cloned_payload = json.loads(json.dumps(original_draft))
    saved = save_generated_skill_draft(cloned_payload, reference=isolated_reference)
    return {
        "reference": isolated_reference,
        "draft_path": saved["path"],
    }


def _build_blocked_task_result(
    proposal: dict,
    *,
    execution_mode: str,
    result_summary: str,
    reason: str,
    runtime_references: list[str] | None = None,
) -> dict:
    selection = proposal.get("selection") or {}
    return {
        "run_id": proposal.get("run_id"),
        "task_description": proposal.get("task_description", ""),
        "selected_skill": selection.get("selected_skill"),
        "execution_mode": execution_mode,
        "sandbox_result": "failed",
        "blocked": True,
        "result_summary": result_summary,
        "runtime_references": list(runtime_references or []),
        "recorded_at": _timestamp(),
        "reason": reason,
    }


def run_sandbox_single_step(
    proposal_or_run_id,
    *,
    sandbox_root: str | Path,
    reference: str | Path | None = None,
    execution_flags: dict | None = None,
    mock_inputs: dict | None = None,
) -> dict:
    proposal = proposal_or_run_id
    if not isinstance(proposal, dict):
        proposal = load_agent_brain_proposal(str(proposal_or_run_id), reference=reference)
    if proposal is None:
        raise ValueError(f"brain proposal not found: {proposal_or_run_id}")

    gate = build_experimental_sandbox_gate(sandbox_root, flags=execution_flags)
    proposal_path = (
        resolve_runtime_data_root(reference) / "brain_proposals" / f"{proposal.get('run_id')}.json"
    )

    if not gate["experimental_sandbox_enabled"]:
        blocked = _build_blocked_task_result(
            proposal,
            execution_mode=gate["execution_mode"],
            result_summary="sandbox single-run blocked by execution mode gate",
            reason="sandbox_single_run_requires_experimental_mode",
            runtime_references=[str(proposal_path)],
        )
        return save_sandbox_task_result(blocked, reference=reference)

    selected_candidate = proposal.get("selected_candidate") or {}
    if not selected_candidate:
        blocked = _build_blocked_task_result(
            proposal,
            execution_mode=gate["execution_mode"],
            result_summary="brain proposal does not contain a selected skill candidate",
            reason="selected_candidate_missing",
            runtime_references=[str(proposal_path)],
        )
        return save_sandbox_task_result(blocked, reference=reference)

    if selected_candidate.get("source") != "generated":
        blocked = _build_blocked_task_result(
            proposal,
            execution_mode=gate["execution_mode"],
            result_summary="selected skill is not runnable by sandbox single-run v0",
            reason="builtin_skill_execution_not_enabled_in_sandbox_single_run_v0",
            runtime_references=[str(proposal_path)],
        )
        return save_sandbox_task_result(blocked, reference=reference)

    isolated = _clone_generated_skill_to_isolated_runtime(
        str(selected_candidate.get("skill_id") or ""),
        sandbox_root=sandbox_root,
        reference=reference,
        run_id=str(proposal.get("run_id")),
    )
    isolated_sandbox_root = Path(sandbox_root) / f"{proposal.get('run_id')}_sandbox"
    isolated_sandbox_root.mkdir(parents=True, exist_ok=True)
    execution = run_generated_skill_in_sandbox(
        str(selected_candidate.get("skill_id") or ""),
        sandbox_root=isolated_sandbox_root,
        reference=isolated["reference"],
        execution_flags=execution_flags,
        mock_inputs=mock_inputs,
    )

    runtime_references = [str(proposal_path), str(isolated["draft_path"])]
    if execution.get("path"):
        runtime_references.append(str(execution["path"]))
    queue_entry = (execution.get("queue") or {}).get("queue_entry") or {}
    if queue_entry.get("path"):
        runtime_references.append(str(queue_entry["path"]))

    result_payload = {
        "run_id": proposal.get("run_id"),
        "task_description": proposal.get("task_description", ""),
        "selected_skill": selected_candidate.get("skill_id"),
        "execution_mode": execution.get("execution_mode", gate["execution_mode"]),
        "sandbox_result": execution.get("sandbox_result", "failed"),
        "blocked": bool(execution.get("blocked")),
        "result_summary": execution.get("output_summary", "sandbox single-run finished"),
        "runtime_references": runtime_references,
        "recorded_at": _timestamp(),
        "reason": execution.get("reason"),
    }
    return save_sandbox_task_result(result_payload, reference=reference)


def run_sandbox_task_once(
    *,
    task_description: str,
    sandbox_root: str | Path,
    reference: str | Path | None = None,
    skills_dir: str | Path | None = None,
    execution_flags: dict | None = None,
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
    llm_selector=None,
    mock_inputs: dict | None = None,
) -> dict:
    if past_skill_memory is None:
        past_skill_memory = build_task_history_memory(reference=reference)

    proposal = run_agent_brain_selection(
        task_description=task_description,
        reference=reference,
        skills_dir=skills_dir,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
        execution_flags=execution_flags,
        llm_selector=llm_selector,
    )
    saved_proposal = save_agent_brain_proposal(proposal, reference=reference)
    task_result = run_sandbox_single_step(
        saved_proposal["proposal"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=execution_flags,
        mock_inputs=mock_inputs,
    )
    return {
        "proposal": saved_proposal,
        "task_result": task_result,
    }
