from inspect_transaction_runtime import main

from agent.marker_recorder import record_transaction_marker
from agent.transaction_runtime import initialize_transaction_runtime_state


def test_cli_prints_runtime_transaction_state_from_temp_runtime_dir(tmp_path, capsys):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-cli-1",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )
    record_transaction_marker("txn-cli-1", "apply_started", reference=reference)
    record_transaction_marker("txn-cli-1", "apply_failed", reference=reference)

    exit_code = main(["--transaction-id", "txn-cli-1", "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Transaction Runtime State]" in output
    assert "- transaction_id: txn-cli-1" in output
    assert "- execution_mode: operational" in output
    assert "[Markers]" in output
    assert "- apply_started @" in output
    assert "- apply_failed @" in output
    assert "[Summary]" in output
    assert "- marker_count: 2" in output


def test_cli_handles_missing_transaction_gracefully(tmp_path, capsys):
    reference = tmp_path / "pending_approvals.json"

    exit_code = main(["--transaction-id", "missing-txn", "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "transaction runtime state not found: missing-txn" in output


def test_cli_includes_summary_and_preserves_marker_order(tmp_path, capsys):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-cli-2",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
    )
    record_transaction_marker("txn-cli-2", "apply_started", reference=reference)
    record_transaction_marker("txn-cli-2", "apply_failed", reference=reference)

    main(["txn-cli-2", "--reference", str(reference)])
    output = capsys.readouterr().out

    assert output.index("- apply_started @") < output.index("- apply_failed @")
    assert "- execution_mode: operational" in output
    assert "- last_marker: apply_failed" in output


def test_cli_prints_notes_when_present(tmp_path, capsys):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state("txn-cli-3", "proposal_test", reference=reference, initial_state="prechecked")
    record_transaction_marker("txn-cli-3", "apply_succeeded", reference=reference)

    main(["txn-cli-3", "--reference", str(reference)])
    output = capsys.readouterr().out

    assert "[Notes]" in output
    assert "marker_rejected:apply_succeeded:success_requires_validation_passed" in output


def test_cli_prints_experimental_execution_mode_when_present(tmp_path, capsys):
    reference = tmp_path / "pending_approvals.json"
    initialize_transaction_runtime_state(
        "txn-cli-4",
        "proposal_test",
        reference=reference,
        initial_state="validation_passed",
        metadata={"execution_mode": "experimental_sandbox"},
    )

    main(["txn-cli-4", "--reference", str(reference)])
    output = capsys.readouterr().out

    assert "- execution_mode: experimental_sandbox" in output
