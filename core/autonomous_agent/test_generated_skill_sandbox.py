from pathlib import Path

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    enqueue_generated_skill_for_manual_promotion,
    load_generated_skill_draft,
    load_generated_skill_promotion_queue,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    validate_generated_skill,
)


def _reference(tmp_path):
    return tmp_path / "pending_approvals.json"


def _experimental_flags():
    return {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def _build_runtime_state_skill():
    return build_generated_skill_payload(
        purpose="summarize runtime state for review",
        generated_by="agent.self_authoring",
        skill_kind="runtime_state_summarizer",
    )


def test_generated_skill_draft_saved_under_runtime_data(tmp_path):
    reference = _reference(tmp_path)
    payload = _build_runtime_state_skill()

    saved = save_generated_skill_draft(payload, reference=reference)
    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)

    assert saved["saved"] is True
    assert Path(saved["path"]).exists()
    assert "runtime-data" in saved["path"]
    assert "generated_skills" in saved["path"]
    assert loaded["skill_id"] == payload["skill_id"]
    assert loaded["status"] == "draft"
    assert loaded["sandbox_only"] is True
    assert loaded["promotion_required"] is True


def test_generated_skill_validation_fails_for_forbidden_capability(tmp_path):
    reference = _reference(tmp_path)
    payload = _build_runtime_state_skill()
    payload["skill_definition"]["capabilities"].append("subprocess")
    save_generated_skill_draft(payload, reference=reference)

    report = validate_generated_skill(payload["skill_id"], reference=reference)
    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)

    assert report["validation_passed"] is False
    assert any("forbidden capabilities" in error for error in report["validation_errors"])
    assert loaded["status"] == "validation_failed"
    assert loaded["validation_summary"].startswith("validation_failed")


def test_operational_mode_blocks_generated_skill_sandbox_execution(tmp_path):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    payload = _build_runtime_state_skill()
    save_generated_skill_draft(payload, reference=reference)

    result = run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-1",
                "state": "apply_started",
                "markers": [{"marker": "apply_started"}],
            }
        },
    )

    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["reason"] == "generated_skill_sandbox_requires_experimental_mode"
    assert result["execution_mode"] == "operational"
    assert loaded["status"] == "validated"


def test_experimental_sandbox_execution_saves_result_and_queues_for_manual_promotion(tmp_path):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    payload = _build_runtime_state_skill()
    save_generated_skill_draft(payload, reference=reference)

    result = run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-1",
                "proposal_id": "proposal-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [
                    {"marker": "apply_started"},
                    {"marker": "apply_succeeded"},
                ],
            }
        },
    )

    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)
    queue_entries = load_generated_skill_promotion_queue(reference=reference)
    result_path = tmp_path / "runtime-data" / "generated_skill_results" / f"{result['run_id']}.json"
    queue_path = tmp_path / "runtime-data" / "generated_skill_queue" / f"{payload['skill_id']}.json"

    assert result["success"] is True
    assert result["blocked"] is False
    assert result["sandbox_result"] == "passed"
    assert result["execution_mode"] == "experimental_sandbox"
    assert result_path.exists()
    assert queue_path.exists()
    assert loaded["status"] == "queued_for_manual_promotion"
    assert loaded["sandbox_result_summary"] == result["output_summary"]
    assert result["queue"]["queued"] is True
    assert result["queue"]["queue_entry"]["promotion_status"] == "pending_manual_review"
    assert len(queue_entries) == 1
    assert queue_entries[0]["skill_id"] == payload["skill_id"]


def test_queue_record_is_not_treated_as_promotion(tmp_path):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    payload = _build_runtime_state_skill()
    save_generated_skill_draft(payload, reference=reference)

    result = run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-2",
                "state": "rollback_completed",
                "terminal_marker": "rollback_completed",
                "markers": [{"marker": "rollback_completed"}],
            }
        },
    )

    queue_entry = result["queue"]["queue_entry"]
    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)

    assert queue_entry["promotion_status"] == "pending_manual_review"
    assert queue_entry["promoted"] is False
    assert loaded["status"] == "queued_for_manual_promotion"
    assert loaded["status"] != "promoted"


def test_enqueue_is_blocked_without_sandbox_pass(tmp_path):
    reference = _reference(tmp_path)
    payload = _build_runtime_state_skill()
    save_generated_skill_draft(payload, reference=reference)
    validate_generated_skill(payload["skill_id"], reference=reference)

    queued = enqueue_generated_skill_for_manual_promotion(payload["skill_id"], reference=reference)

    assert queued["queued"] is False
    assert queued["reason"] == "queue_blocked"
    assert "sandbox_passed required" in queued["blockers"]


def test_sandbox_execution_rejects_mock_input_path_outside_sandbox(tmp_path):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    payload = build_generated_skill_payload(
        purpose="compact review notes",
        generated_by="agent.self_authoring",
        skill_kind="review_note_compactor",
    )
    save_generated_skill_draft(payload, reference=reference)

    result = run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "review_notes": ["keep this short"],
            "workspace_path": str(Path.cwd()),
        },
    )

    loaded = load_generated_skill_draft(payload["skill_id"], reference=reference)

    assert result["success"] is False
    assert result["blocked"] is False
    assert result["sandbox_result"] == "failed"
    assert "escapes sandbox" in result["runtime_notes"][0]
    assert loaded["status"] == "sandbox_failed"
