import argparse
from pathlib import Path

from agent.apply_executor_v0 import run_isolated_apply_v0
from agent.execution_mode import add_experimental_sandbox_flags, build_experimental_sandbox_gate
from agent.transaction_runtime import load_transaction_runtime_state


def _proposal(paths: list[str]) -> dict:
    return {
        "proposal_id": "proposal_temp_apply",
        "target_paths": paths,
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    }


def _experimental_flags() -> dict:
    return {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def test_explicit_flags_enable_experimental_sandbox_mode(tmp_path):
    parser = argparse.ArgumentParser()
    add_experimental_sandbox_flags(parser)
    args = parser.parse_args(["--experimental-sandbox", "--confirm-experimental"])

    gate = build_experimental_sandbox_gate(tmp_path, flags=args)

    assert gate["experimental_sandbox_enabled"] is True
    assert gate["execution_mode"] == "experimental_sandbox"
    assert gate["required_flags"] == {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def test_opt_in_required_blocks_apply_in_operational_mode(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    target = sandbox_root / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/prod.yaml": "mode: canary\n"},
        reference=reference,
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)

    assert result["success"] is False
    assert result["aborted"] is True
    assert result["reason"] == "experimental_sandbox_not_enabled"
    assert result["execution_mode"] == "operational"
    assert result["experimental_gate"]["experimental_sandbox_enabled"] is False
    assert target.read_text(encoding="utf-8") == "mode: prod\n"
    assert runtime_state["execution_mode"] == "operational"
    assert runtime_state["state"] == "halted_for_manual_review"
    assert runtime_state["markers"] == []


def test_temp_dir_only_apply_success(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    target = sandbox_root / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/prod.yaml": "mode: canary\n"},
        reference=reference,
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)
    backup_path = Path(result["backup_result"]["artifacts"][0]["backup_path"])

    assert result["success"] is True
    assert result["execution_mode"] == "experimental_sandbox"
    assert target.read_text(encoding="utf-8") == "mode: canary\n"
    assert backup_path.read_text(encoding="utf-8") == "mode: prod\n"
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert [m["marker"] for m in runtime_state["markers"]] == ["apply_started", "apply_succeeded"]
    assert runtime_state["terminal_marker"] == "apply_succeeded"


def test_backup_missing_aborts_before_apply(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/missing.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/missing.yaml": "mode: canary\n"},
        reference=reference,
        execution_flags=_experimental_flags(),
    )

    assert result["success"] is False
    assert result["aborted"] is True
    assert result["reason"] == "backup_missing"
    assert result["execution_mode"] == "experimental_sandbox"
    assert result["runtime_state"]["state"] == "halted_for_manual_review"
    assert result["runtime_state"]["markers"] == []


def test_temp_write_failure_triggers_full_rollback(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    target = sandbox_root / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/prod.yaml": "mode: canary\n"},
        reference=reference,
        failure_injection={"temp_write_failure_for": ["config/prod.yaml"]},
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)

    assert result["success"] is False
    assert result["reason"] == "temp_write_failed"
    assert target.read_text(encoding="utf-8") == "mode: prod\n"
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert [m["marker"] for m in runtime_state["markers"]] == [
        "apply_started",
        "apply_failed",
        "rollback_started",
        "rollback_completed",
    ]
    assert runtime_state["terminal_marker"] == "rollback_completed"


def test_rename_failure_restores_all_targets(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    first = sandbox_root / "config" / "prod.yaml"
    second = sandbox_root / "docs" / "guide.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("mode: prod\n", encoding="utf-8")
    second.write_text("guide: old\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml", "docs/guide.md"]),
        sandbox_root=sandbox_root,
        content_map={
            "config/prod.yaml": "mode: canary\n",
            "docs/guide.md": "guide: new\n",
        },
        reference=reference,
        failure_injection={"rename_failure_for": ["docs/guide.md"]},
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)

    assert result["success"] is False
    assert result["reason"] == "rename_failed"
    assert first.read_text(encoding="utf-8") == "mode: prod\n"
    assert second.read_text(encoding="utf-8") == "guide: old\n"
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert runtime_state["terminal_marker"] == "rollback_completed"


def test_post_apply_validation_failure_triggers_failed_and_rollback_started(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    target = sandbox_root / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/prod.yaml": "mode: canary\n"},
        reference=reference,
        failure_injection={"post_validation_failure": True},
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)
    markers = [m["marker"] for m in runtime_state["markers"]]

    assert result["success"] is False
    assert result["reason"] == "post_apply_validation_failed"
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert "apply_failed" in markers
    assert "rollback_started" in markers
    assert runtime_state["terminal_marker"] == "rollback_completed"
    assert target.read_text(encoding="utf-8") == "mode: prod\n"


def test_rollback_restore_failure_halts_for_manual_review(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    first = sandbox_root / "config" / "prod.yaml"
    second = sandbox_root / "docs" / "guide.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("mode: prod\n", encoding="utf-8")
    second.write_text("guide: old\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml", "docs/guide.md"]),
        sandbox_root=sandbox_root,
        content_map={
            "config/prod.yaml": "mode: canary\n",
            "docs/guide.md": "guide: new\n",
        },
        reference=reference,
        failure_injection={
            "rename_failure_for": ["docs/guide.md"],
            "rollback_restore_failure_for": ["config/prod.yaml"],
        },
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)

    assert result["success"] is False
    assert result["rollback_result"]["reason"] == "rollback_restore_failed"
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert runtime_state["state"] == "halted_for_manual_review"
    assert runtime_state["terminal_marker"] is None


def test_marker_ordering_and_terminal_marker_accuracy(tmp_path):
    sandbox_root = tmp_path / "sandbox"
    target = sandbox_root / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    reference = tmp_path / "pending_approvals.json"

    result = run_isolated_apply_v0(
        _proposal(["config/prod.yaml"]),
        sandbox_root=sandbox_root,
        content_map={"config/prod.yaml": "mode: canary\n"},
        reference=reference,
        execution_flags=_experimental_flags(),
    )

    runtime_state = load_transaction_runtime_state(result["transaction_id"], reference=reference)

    assert [m["marker"] for m in runtime_state["markers"]] == ["apply_started", "apply_succeeded"]
    assert runtime_state["execution_mode"] == "experimental_sandbox"
    assert runtime_state["terminal_marker"] == "apply_succeeded"


def test_real_workspace_like_root_is_rejected(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    non_temp_root = Path.cwd()

    try:
        run_isolated_apply_v0(
            _proposal(["config/prod.yaml"]),
            sandbox_root=non_temp_root,
            content_map={"config/prod.yaml": "mode: canary\n"},
            reference=reference,
            execution_flags=_experimental_flags(),
        )
    except ValueError as exc:
        assert "system temp directory" in str(exc)
    else:
        raise AssertionError("expected non-temp sandbox root to be rejected")
