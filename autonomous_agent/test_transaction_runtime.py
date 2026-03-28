from agent.marker_recorder import record_transaction_marker
from agent.transaction_runtime import (
    get_transaction_runtime_state_path,
    initialize_transaction_runtime_state,
    load_runtime_transaction_state_for_debug,
    summarize_runtime_transaction_state,
    update_transaction_runtime_state,
)


def test_initialize_transaction_runtime_state_creates_expected_metadata(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    state = initialize_transaction_runtime_state(
        "123e4567-e89b-12d3-a456-426614174000",
        "proposal_test",
        reference=reference,
    )

    path = get_transaction_runtime_state_path("123e4567-e89b-12d3-a456-426614174000", reference=reference)
    assert path.exists()
    assert state["transaction_id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert state["proposal_id"] == "proposal_test"
    assert state["execution_mode"] == "operational"
    assert state["state"] == "prechecked"
    assert state["markers"] == []
    assert state["terminal_marker"] is None
    assert state["idempotency_mode"] == "strict"


def test_repeated_initialize_is_safe_reload(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    first = initialize_transaction_runtime_state("txn-1", "proposal_test", reference=reference)
    second = initialize_transaction_runtime_state("txn-1", "proposal_other", reference=reference)

    assert first == second
    assert second["proposal_id"] == "proposal_test"


def test_update_transaction_runtime_state_before_terminal(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state("txn-2", "proposal_test", reference=reference)

    result = update_transaction_runtime_state(
        "txn-2",
        {"state": "transaction_ready"},
        reference=reference,
        note="mock transition",
    )

    assert result["updated"] is True
    assert result["runtime_state"]["state"] == "transaction_ready"
    assert "mock transition" in result["runtime_state"]["runtime_notes"]


def test_initialize_transaction_runtime_state_preserves_execution_mode(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    state = initialize_transaction_runtime_state(
        "txn-experimental",
        "proposal_test",
        reference=reference,
        metadata={"execution_mode": "experimental_sandbox"},
    )

    assert state["execution_mode"] == "experimental_sandbox"


def test_record_marker_appends_and_updates_state(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-3",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )

    result = record_transaction_marker("txn-3", "apply_started", reference=reference, details={"source": "test"})

    assert result["recorded"] is True
    assert result["runtime_state"]["state"] == "apply_started"
    assert result["runtime_state"]["markers"][0]["marker"] == "apply_started"


def test_duplicate_marker_is_rejected_without_duplication(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-4",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )
    first = record_transaction_marker("txn-4", "apply_started", reference=reference)
    second = record_transaction_marker("txn-4", "apply_started", reference=reference)

    assert first["recorded"] is True
    assert second["recorded"] is False
    assert second["reason"] == "duplicate_marker"
    assert len(second["runtime_state"]["markers"]) == 1


def test_terminal_marker_blocks_further_mutation(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-5",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )
    record_transaction_marker("txn-5", "apply_started", reference=reference)
    record_transaction_marker("txn-5", "apply_succeeded", reference=reference)

    update_result = update_transaction_runtime_state("txn-5", {"state": "apply_failed"}, reference=reference)
    marker_result = record_transaction_marker("txn-5", "apply_failed", reference=reference)

    assert update_result["updated"] is False
    assert update_result["reason"] == "terminal_marker_recorded"
    assert marker_result["recorded"] is False
    assert marker_result["reason"] == "terminal_marker_already_recorded"


def test_invalid_marker_order_halts_for_manual_review(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state("txn-6", "proposal_test", reference=reference, initial_state="prechecked")

    result = record_transaction_marker("txn-6", "apply_succeeded", reference=reference)

    assert result["recorded"] is False
    assert result["reason"] == "success_requires_validation_passed"
    assert result["runtime_state"]["state"] == "halted_for_manual_review"
    assert any("marker_rejected:apply_succeeded:success_requires_validation_passed" in note for note in result["runtime_state"]["runtime_notes"])


def test_runtime_state_summary_and_debug_loader(tmp_path):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-7",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )
    record_transaction_marker("txn-7", "apply_started", reference=reference)

    summary = summarize_runtime_transaction_state("txn-7", reference=reference)
    debug_state = load_runtime_transaction_state_for_debug("txn-7", reference=reference)

    assert summary["state"] == "apply_started"
    assert summary["execution_mode"] == "operational"
    assert summary["marker_count"] == 1
    assert summary["last_marker"] == "apply_started"
    assert debug_state["transaction_id"] == "txn-7"
