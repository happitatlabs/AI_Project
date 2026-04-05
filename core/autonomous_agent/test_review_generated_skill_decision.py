from review_generated_skill_decision import (
    build_generated_skill_review_decision_show_output,
    main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_review_decision,
    validate_generated_skill_review_decision,
)


def _reference(tmp_path):
    return tmp_path / "pending_approvals.json"


def _experimental_flags():
    return {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def _queue_skill(tmp_path):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir(exist_ok=True)
    payload = build_generated_skill_payload(
        purpose="summarize runtime state for review",
        generated_by="agent.self_authoring",
        skill_kind="runtime_state_summarizer",
    )
    save_generated_skill_draft(payload, reference=reference)
    run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-review-record-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def test_review_decision_record_is_saved_under_runtime_data(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    saved = save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox validation passed and low-risk summary skill",
        notes=["manual transform required before production candidate"],
        reference=reference,
    )
    loaded = load_generated_skill_review_decision(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_reviews" in saved["path"]
    assert loaded["skill_id"] == skill_id
    assert loaded["decision"] == "approve_for_consideration"
    assert loaded["reviewer"] == "mellow"
    assert loaded["followup_required"] is False


def test_review_decision_does_not_modify_queue_or_draft_originals(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)

    save_generated_skill_review_decision(
        skill_id,
        decision="needs_followup",
        reviewer="mellow",
        rationale="needs human transform plan before consideration",
        reference=reference,
    )

    queue_after = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_after = load_generated_skill_draft(skill_id, reference=reference)

    assert queue_after == queue_before
    assert draft_after == draft_before


def test_invalid_decision_enum_is_rejected(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    report = validate_generated_skill_review_decision(
        {
            "skill_id": skill_id,
            "decision": "approved",
            "reviewed_at": "2026-03-23T12:00:00+09:00",
            "reviewer": "mellow",
            "rationale": "invalid enum",
            "followup_required": False,
            "notes": [],
        }
    )

    assert report["validation_passed"] is False
    assert "decision must be one of" in report["validation_errors"][0]


def test_missing_reviewer_or_rationale_fails_validation(tmp_path):
    skill_id, _reference_path = _queue_skill(tmp_path)

    report = validate_generated_skill_review_decision(
        {
            "skill_id": skill_id,
            "decision": "rejected",
            "reviewed_at": "2026-03-23T12:00:00+09:00",
            "reviewer": "",
            "rationale": "",
            "followup_required": False,
            "notes": [],
        }
    )

    assert report["validation_passed"] is False
    assert "reviewer is required" in report["validation_errors"]
    assert "rationale is required" in report["validation_errors"]


def test_show_command_reads_review_record(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="low-risk summary skill",
        notes=["manual transform required before production candidate"],
        reference=reference,
    )

    exit_code = main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Review Decision]" in output
    assert "- decision: approve_for_consideration" in output
    assert "- reviewer: mellow" in output


def test_missing_skill_id_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_review_decision_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill review decision not found: missing-skill"


def test_cli_write_validates_required_fields(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)

    exit_code = main(
        [
            "write",
            skill_id,
            "--decision",
            "approve_for_consideration",
            "--reviewer",
            "",
            "--rationale",
            "low-risk summary skill",
            "--reference",
            str(reference),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "reviewer is required" in output


def test_needs_followup_defaults_followup_required_true(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    saved = save_generated_skill_review_decision(
        skill_id,
        decision="needs_followup",
        reviewer="mellow",
        rationale="requires transform checklist",
        reference=reference,
    )

    assert saved["review"]["followup_required"] is True
