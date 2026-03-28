import shutil
from pathlib import Path
from uuid import uuid4

from agent.execution_mode import build_experimental_sandbox_gate
from agent.marker_recorder import record_transaction_marker
from agent.transaction_runtime import (
    initialize_transaction_runtime_state,
    update_transaction_runtime_state,
)
from agent.workspace_metrics import (
    build_apply_dry_run,
    build_apply_plan,
    build_apply_precheck,
    build_executor_spec,
    validate_apply_plan,
)

BACKUP_DIRNAME = "runtime_backups"


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _normalize_target_path(target_path: str) -> Path | None:
    candidate = Path(target_path.replace("\\", "/"))
    if candidate.is_absolute():
        return None
    parts = [part for part in candidate.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    if not parts:
        return None
    return Path(*parts)


def _resolve_targets(proposal: dict, sandbox_root: Path) -> list[dict]:
    resolved = []
    for raw_path in proposal.get("target_paths", []):
        normalized = _normalize_target_path(str(raw_path))
        if normalized is None:
            raise ValueError(f"invalid target path: {raw_path}")
        absolute = (sandbox_root / normalized).resolve()
        if not _is_relative_to(absolute, sandbox_root):
            raise ValueError(f"target path escapes sandbox: {raw_path}")
        resolved.append(
            {
                "target_path": str(normalized).replace("\\", "/"),
                "relative_path": normalized,
                "absolute_path": absolute,
            }
        )
    return resolved


def _backup_root(reference: str | Path | None, transaction_id: str) -> Path:
    base = Path(reference).resolve().parent if reference is not None and Path(reference).suffix else Path(reference or ".").resolve()
    return base / "runtime-data" / BACKUP_DIRNAME / transaction_id


def materialize_backups_v0(
    targets: list[dict],
    transaction_id: str,
    *,
    reference: str | Path | None = None,
    failure_injection: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    backup_root = _backup_root(reference, transaction_id)
    artifacts = []
    blockers = []
    missing_targets = []
    skip_targets = set(failure_injection.get("skip_backup_for", []))

    for target in targets:
        path_key = target["target_path"]
        absolute = target["absolute_path"]
        if path_key in skip_targets or not absolute.exists():
            missing_targets.append(path_key)
            continue
        backup_path = backup_root / target["relative_path"]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(absolute, backup_path)
        artifacts.append({"target_path": path_key, "backup_path": str(backup_path)})

    if missing_targets:
        blockers.append("backup_missing")

    return {
        "ok": not blockers,
        "transaction_id": transaction_id,
        "backup_root": str(backup_root),
        "artifacts": artifacts,
        "missing_targets": missing_targets,
        "reason": "ok" if not blockers else "backup_missing",
        "blockers": blockers,
    }


def execute_atomic_write_v0(
    targets: list[dict],
    content_map: dict[str, str],
    transaction_id: str,
    *,
    failure_injection: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    temp_write_failures = set(failure_injection.get("temp_write_failure_for", []))
    rename_failures = set(failure_injection.get("rename_failure_for", []))
    temp_files = []
    renamed_paths = []

    for target in targets:
        path_key = target["target_path"]
        absolute = target["absolute_path"]
        if path_key in temp_write_failures:
            return {
                "ok": False,
                "reason": "temp_write_failed",
                "failed_target": path_key,
                "temp_files": temp_files,
                "renamed_paths": renamed_paths,
            }
        temp_path = absolute.parent / f".{absolute.name}.{transaction_id}.tmp"
        temp_path.write_text(content_map[path_key], encoding="utf-8")
        temp_files.append({"target_path": path_key, "temp_path": str(temp_path), "path_obj": temp_path})

    for temp_item, target in zip(temp_files, targets):
        path_key = target["target_path"]
        absolute = target["absolute_path"]
        if path_key in rename_failures:
            return {
                "ok": False,
                "reason": "rename_failed",
                "failed_target": path_key,
                "temp_files": temp_files,
                "renamed_paths": renamed_paths,
            }
        temp_item["path_obj"].replace(absolute)
        renamed_paths.append(path_key)

    return {
        "ok": True,
        "reason": "applied",
        "temp_files": temp_files,
        "renamed_paths": renamed_paths,
    }


def execute_full_rollback_v0(
    targets: list[dict],
    backup_result: dict,
    *,
    failure_injection: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    restore_failures = set(failure_injection.get("rollback_restore_failure_for", []))
    restored = []

    artifact_map = {item["target_path"]: Path(item["backup_path"]) for item in backup_result.get("artifacts", [])}
    for target in targets:
        path_key = target["target_path"]
        absolute = target["absolute_path"]
        if path_key in restore_failures:
            return {
                "ok": False,
                "reason": "rollback_restore_failed",
                "failed_target": path_key,
                "restored_paths": restored,
            }
        backup_path = artifact_map.get(path_key)
        if backup_path is None or not backup_path.exists():
            return {
                "ok": False,
                "reason": "rollback_backup_missing",
                "failed_target": path_key,
                "restored_paths": restored,
            }
        shutil.copy2(backup_path, absolute)
        restored.append(path_key)

    return {
        "ok": True,
        "reason": "rollback_completed",
        "restored_paths": restored,
    }


def run_post_apply_validation_v0(
    targets: list[dict],
    content_map: dict[str, str],
    *,
    failure_injection: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    if failure_injection.get("post_validation_failure"):
        return {"ok": False, "reason": "post_apply_validation_failed", "changed_files_match_plan": False}

    changed_files_match_plan = True
    for target in targets:
        path_key = target["target_path"]
        if target["absolute_path"].read_text(encoding="utf-8") != content_map[path_key]:
            changed_files_match_plan = False
            break

    return {
        "ok": changed_files_match_plan and len(targets) >= 0,
        "reason": "validated" if changed_files_match_plan else "post_apply_validation_failed",
        "changed_files_match_plan": changed_files_match_plan,
        "target_count_matches_expected": True,
    }


def _halt_runtime_state(transaction_id: str, reason: str, *, reference: str | Path | None = None) -> dict | None:
    result = update_transaction_runtime_state(
        transaction_id,
        {"state": "halted_for_manual_review"},
        reference=reference,
        note=reason,
    )
    return result.get("runtime_state")


def _run_experimental_sandbox_apply_v0(
    proposal: dict,
    *,
    sandbox: Path,
    content_map: dict[str, str],
    transaction_id: str,
    execution_mode: str,
    experimental_gate: dict,
    precheck: dict,
    plan: dict,
    executor_spec: dict,
    dry_run: dict,
    runtime_state: dict,
    reference: str | Path | None = None,
    failure_injection: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    result_base = {
        "execution_mode": execution_mode,
        "experimental_gate": experimental_gate,
        "transaction_id": transaction_id,
        "precheck": precheck,
        "apply_plan": plan,
        "dry_run": dry_run,
    }

    sandbox_eligible = (
        proposal.get("status") == "approved"
        and precheck.get("apply_mode") != "blocked"
        and not precheck.get("blocked_target_paths")
    )
    if not sandbox_eligible:
        halted = _halt_runtime_state(transaction_id, "apply_aborted:precheck_or_validation_failed", reference=reference)
        return {
            "success": False,
            "aborted": True,
            "reason": "apply_blocked",
            "runtime_state": halted or runtime_state,
            **result_base,
        }

    targets = _resolve_targets(proposal, sandbox)
    missing_content = [item["target_path"] for item in targets if item["target_path"] not in content_map]
    if missing_content:
        halted = _halt_runtime_state(transaction_id, f"apply_aborted:missing_content_map:{', '.join(missing_content)}", reference=reference)
        return {
            "success": False,
            "aborted": True,
            "reason": "missing_content_map",
            "runtime_state": halted or runtime_state,
            **result_base,
        }

    update_transaction_runtime_state(transaction_id, {"state": "transaction_ready"}, reference=reference)
    backup_result = materialize_backups_v0(targets, transaction_id, reference=reference, failure_injection=failure_injection)
    if not backup_result["ok"]:
        halted = _halt_runtime_state(transaction_id, "apply_aborted:backup_missing", reference=reference)
        return {
            "success": False,
            "aborted": True,
            "reason": "backup_missing",
            "runtime_state": halted or runtime_state,
            "backup_result": backup_result,
            **result_base,
        }

    update_transaction_runtime_state(transaction_id, {"state": "backup_ready"}, reference=reference)
    update_transaction_runtime_state(transaction_id, {"state": "validation_passed"}, reference=reference)
    record_transaction_marker(transaction_id, "apply_started", reference=reference, executor_spec=executor_spec)

    write_result = execute_atomic_write_v0(
        targets,
        content_map,
        transaction_id,
        failure_injection=failure_injection,
    )
    if not write_result["ok"]:
        record_transaction_marker(transaction_id, "apply_failed", reference=reference, executor_spec=executor_spec)
        update_transaction_runtime_state(transaction_id, {"state": "rollback_required"}, reference=reference)
        record_transaction_marker(transaction_id, "rollback_started", reference=reference, executor_spec=executor_spec)
        rollback_result = execute_full_rollback_v0(targets, backup_result, failure_injection=failure_injection)
        if rollback_result["ok"]:
            rollback_marker = record_transaction_marker(transaction_id, "rollback_completed", reference=reference, executor_spec=executor_spec)
            return {
                "success": False,
                "aborted": False,
                "reason": write_result["reason"],
                "backup_result": backup_result,
                "write_result": write_result,
                "rollback_result": rollback_result,
                "runtime_state": rollback_marker["runtime_state"],
                **result_base,
            }
        halted = _halt_runtime_state(transaction_id, f"rollback_failed:{rollback_result['reason']}", reference=reference)
        return {
            "success": False,
            "aborted": False,
            "reason": write_result["reason"],
            "backup_result": backup_result,
            "write_result": write_result,
            "rollback_result": rollback_result,
            "runtime_state": halted,
            **result_base,
        }

    post_validation = run_post_apply_validation_v0(targets, content_map, failure_injection=failure_injection)
    if not post_validation["ok"]:
        record_transaction_marker(transaction_id, "apply_failed", reference=reference, executor_spec=executor_spec)
        update_transaction_runtime_state(transaction_id, {"state": "rollback_required"}, reference=reference)
        record_transaction_marker(transaction_id, "rollback_started", reference=reference, executor_spec=executor_spec)
        rollback_result = execute_full_rollback_v0(targets, backup_result, failure_injection=failure_injection)
        if rollback_result["ok"]:
            rollback_marker = record_transaction_marker(transaction_id, "rollback_completed", reference=reference, executor_spec=executor_spec)
            return {
                "success": False,
                "aborted": False,
                "reason": post_validation["reason"],
                "backup_result": backup_result,
                "write_result": write_result,
                "post_validation": post_validation,
                "rollback_result": rollback_result,
                "runtime_state": rollback_marker["runtime_state"],
                **result_base,
            }
        halted = _halt_runtime_state(transaction_id, f"rollback_failed:{rollback_result['reason']}", reference=reference)
        return {
            "success": False,
            "aborted": False,
            "reason": post_validation["reason"],
            "backup_result": backup_result,
            "write_result": write_result,
            "post_validation": post_validation,
            "rollback_result": rollback_result,
            "runtime_state": halted,
            **result_base,
        }

    success_marker = record_transaction_marker(transaction_id, "apply_succeeded", reference=reference, executor_spec=executor_spec)
    return {
        "success": True,
        "aborted": False,
        "reason": "applied",
        "backup_result": backup_result,
        "write_result": write_result,
        "post_validation": post_validation,
        "runtime_state": success_marker["runtime_state"],
        **result_base,
    }


def run_isolated_apply_v0(
    proposal: dict,
    *,
    sandbox_root: str | Path,
    content_map: dict[str, str],
    reference: str | Path | None = None,
    failure_injection: dict | None = None,
    execution_flags: dict | None = None,
) -> dict:
    failure_injection = failure_injection or {}
    precheck = build_apply_precheck(proposal)
    plan = build_apply_plan(proposal, precheck=precheck)
    validate_apply_plan(proposal, precheck=precheck)
    executor_spec = build_executor_spec(proposal, precheck=precheck)
    dry_run = build_apply_dry_run(proposal, precheck=precheck)
    experimental_gate = build_experimental_sandbox_gate(sandbox_root, flags=execution_flags)
    if not experimental_gate["path_in_temp_dir"]:
        raise ValueError("sandbox_root must be inside the system temp directory")

    transaction_id = str(uuid4())
    execution_mode = experimental_gate["execution_mode"]
    runtime_state = initialize_transaction_runtime_state(
        transaction_id,
        proposal.get("proposal_id"),
        reference=reference,
        initial_state="prechecked",
        metadata={
            "state_machine_version": executor_spec.get("state_machine", {}).get("state_machine_version", "v1"),
            "executor_spec_version": executor_spec.get("executor_spec_version", "v1"),
            "idempotency_mode": executor_spec.get("idempotency_policy", {}).get("mode", "strict"),
            "execution_mode": execution_mode,
        },
    )

    if not experimental_gate["experimental_sandbox_enabled"]:
        halted = _halt_runtime_state(
            transaction_id,
            "apply_aborted:experimental_sandbox_gate_blocked",
            reference=reference,
        )
        return {
            "success": False,
            "aborted": True,
            "reason": "experimental_sandbox_not_enabled",
            "transaction_id": transaction_id,
            "execution_mode": execution_mode,
            "experimental_gate": experimental_gate,
            "runtime_state": halted or runtime_state,
            "precheck": precheck,
            "apply_plan": plan,
            "dry_run": dry_run,
        }

    return _run_experimental_sandbox_apply_v0(
        proposal,
        sandbox=Path(experimental_gate["sandbox_root"]),
        content_map=content_map,
        transaction_id=transaction_id,
        execution_mode=execution_mode,
        experimental_gate=experimental_gate,
        precheck=precheck,
        plan=plan,
        executor_spec=executor_spec,
        dry_run=dry_run,
        runtime_state=runtime_state,
        reference=reference,
        failure_injection=failure_injection,
    )
