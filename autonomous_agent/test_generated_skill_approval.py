from approve_generated_skill import (
    build_generated_skill_approval_show_output,
    main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_approval_record,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
    save_generated_skill_approval_record,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
    save_generated_skill_transform_template,
    validate_generated_skill_approval_record,
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
                "transaction_id": "txn-approval-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def _prepare_transform_candidate(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox validation passed and low-risk summary skill",
        notes=["manual transform required before production candidate"],
        reference=reference,
    )
    save_generated_skill_promotion_packet(skill_id, reference=reference)
    save_generated_skill_transform_template(skill_id, reference=reference)
    return skill_id, reference


def test_approval_record_is_saved_under_runtime_data(tmp_path):
    skill_id, reference = _prepare_transform_candidate(tmp_path)

    saved = save_generated_skill_approval_record(
        skill_id,
        approval_type="transform_approval",
        decision="approved",
        approver="mellow",
        rationale="manual transform reviewed",
        final_target_name="runtime_state_summarizer_v1",
        final_target_path="skills/runtime_state_summarizer_v1.json",
        notes=["production candidate still requires manual registration"],
        reference=reference,
    )
    loaded = load_generated_skill_approval_record(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_reviews" in saved["path"]
    assert loaded["records"]["transform_approval"]["decision"] == "approved"


def test_approval_save_does_not_modify_existing_artifacts(tmp_path):
    skill_id, reference = _prepare_transform_candidate(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)

    save_generated_skill_approval_record(
        skill_id,
        approval_type="transform_approval",
        decision="approved",
        approver="mellow",
        rationale="manual transform reviewed",
        final_target_name="runtime_state_summarizer_v1",
        final_target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before


def test_invalid_enums_are_rejected(tmp_path):
    skill_id, _reference_path = _prepare_transform_candidate(tmp_path)

    report = validate_generated_skill_approval_record(
        {
            "skill_id": skill_id,
            "approval_type": "promotion",
            "decision": "approve",
            "approved_at": "2026-03-23T12:00:00+09:00",
            "approver": "mellow",
            "rationale": "invalid enums",
            "followup_required": False,
            "notes": [],
            "source_review_decision": "approve_for_consideration",
            "source_packet_id": f"{skill_id}.packet",
            "source_transform_template": f"{skill_id}.transform",
            "final_target_name": None,
            "final_target_path": None,
            "rollback_reference": None,
        }
    )

    assert report["validation_passed"] is False
    assert "approval_type must be one of" in report["validation_errors"][0]


def test_missing_required_fields_fail_validation(tmp_path):
    skill_id, _reference_path = _prepare_transform_candidate(tmp_path)

    report = validate_generated_skill_approval_record(
        {
            "skill_id": skill_id,
            "approval_type": "transform_approval",
            "decision": "approved",
            "approved_at": "2026-03-23T12:00:00+09:00",
            "approver": "",
            "rationale": "",
            "followup_required": False,
            "notes": [],
            "source_review_decision": "",
            "source_packet_id": "",
            "source_transform_template": "",
            "final_target_name": None,
            "final_target_path": None,
            "rollback_reference": None,
        }
    )

    assert report["validation_passed"] is False
    assert "approver is required" in report["validation_errors"]
    assert "rationale is required" in report["validation_errors"]
    assert "source_review_decision is required" in report["validation_errors"]
    assert "source_packet_id is required" in report["validation_errors"]
    assert "source_transform_template is required for transform_approval" in report["validation_errors"]


def test_show_command_reads_approval_record(tmp_path, capsys):
    skill_id, reference = _prepare_transform_candidate(tmp_path)
    save_generated_skill_approval_record(
        skill_id,
        approval_type="transform_approval",
        decision="approved",
        approver="mellow",
        rationale="manual transform reviewed",
        final_target_name="runtime_state_summarizer_v1",
        final_target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    exit_code = main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Approval]" in output
    assert "- approval_type: transform_approval" in output
    assert "- decision: approved" in output


def test_missing_skill_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_approval_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill approval record not found: missing-skill"


def test_needs_followup_defaults_followup_required_true(tmp_path):
    skill_id, reference = _prepare_transform_candidate(tmp_path)

    saved = save_generated_skill_approval_record(
        skill_id,
        approval_type="promotion_approval",
        decision="needs_followup",
        approver="mellow",
        rationale="rollback reference must be added before final approval",
        reference=reference,
    )

    assert saved["approval"]["followup_required"] is True


def test_approved_record_does_not_register_production_skill(tmp_path):
    skill_id, reference = _prepare_transform_candidate(tmp_path)

    save_generated_skill_approval_record(
        skill_id,
        approval_type="transform_approval",
        decision="approved",
        approver="mellow",
        rationale="manual transform reviewed",
        final_target_name="runtime_state_summarizer_v1",
        final_target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    assert not (tmp_path / "skills" / "runtime_state_summarizer_v1.json").exists()


def test_cli_write_validates_required_approved_target_fields(tmp_path, capsys):
    skill_id, reference = _prepare_transform_candidate(tmp_path)

    exit_code = main(
        [
            "write",
            skill_id,
            "--approval-type",
            "transform_approval",
            "--decision",
            "approved",
            "--approver",
            "mellow",
            "--rationale",
            "manual transform reviewed",
            "--reference",
            str(reference),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "final_target_name is required when decision=approved" in output
