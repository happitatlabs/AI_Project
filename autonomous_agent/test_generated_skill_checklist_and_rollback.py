from record_generated_skill_checklist import (
    build_generated_skill_checklist_show_output,
    main as checklist_main,
)
from record_generated_skill_rollback import (
    build_generated_skill_rollback_show_output,
    main as rollback_main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_approval_record,
    load_generated_skill_candidate_checklist,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    load_generated_skill_rollback_record,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
    save_generated_skill_approval_record,
    save_generated_skill_candidate_checklist,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
    save_generated_skill_rollback_record,
    save_generated_skill_transform_template,
    validate_generated_skill_candidate_checklist,
    validate_generated_skill_rollback_record,
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
                "transaction_id": "txn-checklist-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def _prepare_candidate_ready_skill(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox validation passed and low-risk summary skill",
        reference=reference,
    )
    save_generated_skill_promotion_packet(skill_id, reference=reference)
    save_generated_skill_transform_template(skill_id, reference=reference)
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
    return skill_id, reference


def test_candidate_checklist_is_saved_under_runtime_data(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)

    saved = save_generated_skill_candidate_checklist(
        skill_id,
        operator="mellow",
        review_decision_exists=True,
        approval_record_exists=True,
        validation_passed=True,
        sandbox_passed=True,
        sandbox_only_confirmed=True,
        promotion_required_confirmed=True,
        generated_only_fields_removed=True,
        target_name_manually_chosen=True,
        naming_collision_resolved=True,
        core_skill_overwrite_absent=True,
        rollback_reference_prepared=True,
        direct_move_not_used=True,
        target_name="runtime_state_summarizer_v1",
        target_path="skills/runtime_state_summarizer_v1.json",
        notes=["candidate ready for manual registration review"],
        reference=reference,
    )
    loaded = load_generated_skill_candidate_checklist(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_reviews" in saved["path"]
    assert loaded["all_checks_passed"] is True


def test_candidate_checklist_all_checks_passed_is_derived(tmp_path):
    skill_id, _reference_path = _prepare_candidate_ready_skill(tmp_path)

    report = validate_generated_skill_candidate_checklist(
        {
            "skill_id": skill_id,
            "checked_at": "2026-03-23T12:00:00+09:00",
            "operator": "mellow",
            "review_decision_exists": True,
            "approval_record_exists": True,
            "validation_passed": True,
            "sandbox_passed": True,
            "sandbox_only_confirmed": True,
            "promotion_required_confirmed": True,
            "generated_only_fields_removed": True,
            "target_name_manually_chosen": True,
            "naming_collision_resolved": False,
            "core_skill_overwrite_absent": True,
            "rollback_reference_prepared": True,
            "direct_move_not_used": True,
            "source_review_record": f"{skill_id}.review",
            "source_approval_record": f"{skill_id}.approval",
            "source_transform_template": f"{skill_id}.transform",
            "target_name": "runtime_state_summarizer_v1",
            "target_path": "skills/runtime_state_summarizer_v1.json",
            "notes": [],
        }
    )

    assert report["validation_passed"] is True
    assert report["normalized_payload"]["all_checks_passed"] is False


def test_partial_candidate_checklist_fails_validation(tmp_path):
    skill_id, _reference_path = _prepare_candidate_ready_skill(tmp_path)

    report = validate_generated_skill_candidate_checklist(
        {
            "skill_id": skill_id,
            "checked_at": "2026-03-23T12:00:00+09:00",
            "operator": "",
            "review_decision_exists": True,
            "approval_record_exists": True,
            "validation_passed": True,
            "sandbox_passed": True,
            "sandbox_only_confirmed": True,
            "promotion_required_confirmed": True,
            "generated_only_fields_removed": True,
            "target_name_manually_chosen": True,
            "naming_collision_resolved": True,
            "core_skill_overwrite_absent": True,
            "rollback_reference_prepared": True,
            "source_review_record": "",
            "source_approval_record": "",
            "source_transform_template": "",
            "target_name": "",
            "target_path": "",
            "notes": [],
            "all_checks_passed": True,
        }
    )

    assert report["validation_passed"] is False
    assert "operator is required" in report["validation_errors"]
    assert "direct_move_not_used must be a bool" in report["validation_errors"]
    assert "source_review_record is required" in report["validation_errors"]
    assert "target_name is required" in report["validation_errors"]


def test_candidate_checklist_save_does_not_modify_existing_artifacts(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)

    save_generated_skill_candidate_checklist(
        skill_id,
        operator="mellow",
        review_decision_exists=True,
        approval_record_exists=True,
        validation_passed=True,
        sandbox_passed=True,
        sandbox_only_confirmed=True,
        promotion_required_confirmed=True,
        generated_only_fields_removed=True,
        target_name_manually_chosen=True,
        naming_collision_resolved=True,
        core_skill_overwrite_absent=True,
        rollback_reference_prepared=True,
        direct_move_not_used=True,
        target_name="runtime_state_summarizer_v1",
        target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before


def test_candidate_checklist_show_command_uses_block_report(tmp_path, capsys):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    save_generated_skill_candidate_checklist(
        skill_id,
        operator="mellow",
        review_decision_exists=True,
        approval_record_exists=True,
        validation_passed=True,
        sandbox_passed=True,
        sandbox_only_confirmed=True,
        promotion_required_confirmed=True,
        generated_only_fields_removed=True,
        target_name_manually_chosen=True,
        naming_collision_resolved=True,
        core_skill_overwrite_absent=True,
        rollback_reference_prepared=True,
        direct_move_not_used=True,
        target_name="runtime_state_summarizer_v1",
        target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    exit_code = checklist_main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Checklist]" in output
    assert "[Checks]" in output
    assert "[Target]" in output
    assert "[Sources]" in output


def test_candidate_checklist_cli_write_saves_record(tmp_path, capsys):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)

    exit_code = checklist_main(
        [
            "write",
            skill_id,
            "--operator",
            "mellow",
            "--review-decision-exists",
            "yes",
            "--approval-record-exists",
            "yes",
            "--validation-passed",
            "yes",
            "--sandbox-passed",
            "yes",
            "--sandbox-only-confirmed",
            "yes",
            "--promotion-required-confirmed",
            "yes",
            "--generated-only-fields-removed",
            "yes",
            "--target-name-manually-chosen",
            "yes",
            "--naming-collision-resolved",
            "yes",
            "--core-skill-overwrite-absent",
            "yes",
            "--rollback-reference-prepared",
            "yes",
            "--direct-move-not-used",
            "yes",
            "--target-name",
            "runtime_state_summarizer_v1",
            "--target-path",
            "skills/runtime_state_summarizer_v1.json",
            "--reference",
            str(reference),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "generated skill candidate checklist saved" in output
    assert load_generated_skill_candidate_checklist(skill_id, reference=reference)["all_checks_passed"] is True


def test_missing_candidate_checklist_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_checklist_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill candidate checklist not found: missing-skill"


def test_rollback_record_is_saved_under_runtime_data(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    save_generated_skill_candidate_checklist(
        skill_id,
        operator="mellow",
        review_decision_exists=True,
        approval_record_exists=True,
        validation_passed=True,
        sandbox_passed=True,
        sandbox_only_confirmed=True,
        promotion_required_confirmed=True,
        generated_only_fields_removed=True,
        target_name_manually_chosen=True,
        naming_collision_resolved=True,
        core_skill_overwrite_absent=True,
        rollback_reference_prepared=True,
        direct_move_not_used=True,
        target_name="runtime_state_summarizer_v1",
        target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )

    saved = save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="candidate withdrawn after manual review",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        rollback_reference="runtime_state_summarizer_v1.rollback",
        notes=["manual revert only"],
        reference=reference,
    )
    loaded = load_generated_skill_rollback_record(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_reviews" in saved["path"]
    assert loaded["production_artifact_ref"] == "skills/runtime_state_summarizer_v1.json"


def test_invalid_rollback_record_fields_fail_validation(tmp_path):
    skill_id, _reference_path = _prepare_candidate_ready_skill(tmp_path)

    report = validate_generated_skill_rollback_record(
        {
            "skill_id": skill_id,
            "rolled_back_at": "2026-03-23T12:00:00+09:00",
            "operator": "",
            "reason": "",
            "production_artifact_ref": "",
            "review_record_ref": "",
            "approval_record_ref": "",
            "transform_template_ref": "",
            "candidate_artifact_ref": "",
            "rollback_reference": None,
            "notes": {},
        }
    )

    assert report["validation_passed"] is False
    assert "operator is required" in report["validation_errors"]
    assert "reason is required" in report["validation_errors"]
    assert "production_artifact_ref is required" in report["validation_errors"]
    assert "notes must be a list" in report["validation_errors"]


def test_rollback_latest_only_replace_policy(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)

    save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="candidate withdrawn after manual review",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        reference=reference,
    )

    try:
        save_generated_skill_rollback_record(
            skill_id,
            operator="mellow",
            reason="second rollback attempt",
            production_artifact_ref="skills/runtime_state_summarizer_v1.json",
            candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
            reference=reference,
        )
        raised = False
    except ValueError as exc:
        raised = True
        message = str(exc)

    assert raised is True
    assert "generated skill rollback record already exists" in message


def test_rollback_allow_replace_updates_latest_record(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="first rollback reason",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        reference=reference,
    )

    saved = save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="updated rollback reason",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        allow_replace=True,
        reference=reference,
    )

    assert saved["rollback"]["reason"] == "updated rollback reason"


def test_rollback_save_does_not_modify_existing_artifacts(tmp_path):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    save_generated_skill_candidate_checklist(
        skill_id,
        operator="mellow",
        review_decision_exists=True,
        approval_record_exists=True,
        validation_passed=True,
        sandbox_passed=True,
        sandbox_only_confirmed=True,
        promotion_required_confirmed=True,
        generated_only_fields_removed=True,
        target_name_manually_chosen=True,
        naming_collision_resolved=True,
        core_skill_overwrite_absent=True,
        rollback_reference_prepared=True,
        direct_move_not_used=True,
        target_name="runtime_state_summarizer_v1",
        target_path="skills/runtime_state_summarizer_v1.json",
        reference=reference,
    )
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)
    checklist_before = load_generated_skill_candidate_checklist(skill_id, reference=reference)

    save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="candidate withdrawn after manual review",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        reference=reference,
    )

    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before
    assert load_generated_skill_candidate_checklist(skill_id, reference=reference) == checklist_before


def test_rollback_show_command_uses_block_report(tmp_path, capsys):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)
    save_generated_skill_rollback_record(
        skill_id,
        operator="mellow",
        reason="candidate withdrawn after manual review",
        production_artifact_ref="skills/runtime_state_summarizer_v1.json",
        candidate_artifact_ref="runtime_state_summarizer_v1.candidate",
        reference=reference,
    )

    exit_code = rollback_main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Rollback]" in output
    assert "[Source]" in output
    assert "[Production Artifact]" in output
    assert "[Notes]" in output


def test_rollback_cli_write_saves_record(tmp_path, capsys):
    skill_id, reference = _prepare_candidate_ready_skill(tmp_path)

    exit_code = rollback_main(
        [
            "write",
            skill_id,
            "--operator",
            "mellow",
            "--reason",
            "candidate withdrawn after manual review",
            "--production-artifact-ref",
            "skills/runtime_state_summarizer_v1.json",
            "--candidate-artifact-ref",
            "runtime_state_summarizer_v1.candidate",
            "--reference",
            str(reference),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "generated skill rollback record saved" in output
    assert load_generated_skill_rollback_record(skill_id, reference=reference)["reason"] == "candidate withdrawn after manual review"


def test_missing_rollback_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_rollback_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill rollback record not found: missing-skill"
