from promote_generated_skill import main as promote_main

from agent.generated_skill_sandbox import (
    build_generated_skill_manual_promotion_preview,
    build_generated_skill_promotion_record_report,
    build_generated_skill_payload,
    execute_generated_skill_manual_promotion,
    load_generated_skill_approval_record,
    load_generated_skill_candidate,
    load_generated_skill_candidate_checklist,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_promotion_record,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
    save_generated_skill_approval_record,
    save_generated_skill_candidate_checklist,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
    save_generated_skill_transform_template,
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
        purpose="compact repeated review notes for manual review",
        generated_by="agent.self_authoring",
        skill_kind="review_note_compactor",
    )
    save_generated_skill_draft(payload, reference=reference)
    run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "review_notes": [
                "Needs tighter validation around sandbox-only metadata.",
                "Needs tighter validation around sandbox-only metadata.",
                "Promotion must remain manual-only.",
            ]
        },
    )
    return payload["skill_id"], reference


def _prepare_ready_for_manual_promotion(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox validation passed and low-risk formatting skill",
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
        final_target_name="review_note_compactor_v1",
        final_target_path="skills/review_note_compactor_v1.json",
        rollback_reference="manual-rollback-required",
        reference=reference,
    )
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
        target_name="review_note_compactor_v1",
        target_path="skills/review_note_compactor_v1.json",
        notes=["candidate ready for manual promotion execution"],
        reference=reference,
    )
    return skill_id, reference


def test_manual_promotion_execute_blocks_when_conditions_are_missing(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    preview = build_generated_skill_manual_promotion_preview(skill_id, reference=reference)

    assert preview["can_execute"] is False
    assert "approval record missing" in preview["blockers"]

    try:
        execute_generated_skill_manual_promotion(
            skill_id,
            operator="mellow",
            confirm_promotion=True,
            reference=reference,
        )
    except ValueError as exc:
        assert "approval record missing" in str(exc)
    else:
        raise AssertionError("expected manual promotion execution to be blocked")


def test_manual_promotion_execute_creates_candidate_and_promotion_record(tmp_path):
    skill_id, reference = _prepare_ready_for_manual_promotion(tmp_path)

    result = execute_generated_skill_manual_promotion(
        skill_id,
        operator="mellow",
        confirm_promotion=True,
        notes=["executed from test"],
        reference=reference,
    )

    candidate = load_generated_skill_candidate(skill_id, reference=reference)
    promotion = load_generated_skill_promotion_record(skill_id, reference=reference)

    assert result["executed"] is True
    assert "generated_skill_candidates" in result["candidate"]["path"]
    assert "generated_skill_reviews" in result["promotion"]["path"]
    assert candidate["target_name"] == "review_note_compactor_v1"
    assert candidate["target_path"] == "skills/review_note_compactor_v1.json"
    assert "sandbox_only" not in candidate
    assert promotion["decision"] == "executed"
    assert promotion["final_target_name"] == "review_note_compactor_v1"


def test_manual_promotion_execute_does_not_modify_existing_artifacts(tmp_path):
    skill_id, reference = _prepare_ready_for_manual_promotion(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)
    checklist_before = load_generated_skill_candidate_checklist(skill_id, reference=reference)

    execute_generated_skill_manual_promotion(
        skill_id,
        operator="mellow",
        confirm_promotion=True,
        reference=reference,
    )

    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before
    assert load_generated_skill_candidate_checklist(skill_id, reference=reference) == checklist_before


def test_manual_promotion_execute_respects_allow_replace_policy(tmp_path):
    skill_id, reference = _prepare_ready_for_manual_promotion(tmp_path)
    execute_generated_skill_manual_promotion(
        skill_id,
        operator="mellow",
        confirm_promotion=True,
        reference=reference,
    )

    try:
        execute_generated_skill_manual_promotion(
            skill_id,
            operator="mellow",
            confirm_promotion=True,
            reference=reference,
        )
    except ValueError as exc:
        assert "generated skill candidate artifact already exists" in str(exc)
    else:
        raise AssertionError("expected existing candidate artifact to block execute without allow_replace")

    result = execute_generated_skill_manual_promotion(
        skill_id,
        operator="mellow",
        confirm_promotion=True,
        allow_replace=True,
        reference=reference,
    )
    assert result["executed"] is True


def test_manual_promotion_cli_preview_execute_and_show(tmp_path, capsys):
    skill_id, reference = _prepare_ready_for_manual_promotion(tmp_path)

    preview_exit = promote_main(["preview", skill_id, "--reference", str(reference)])
    preview_output = capsys.readouterr().out
    assert preview_exit == 0
    assert "[Promotion Readiness]" in preview_output
    assert "[Candidate Preview]" in preview_output

    blocked_exit = promote_main(
        [
            "execute",
            skill_id,
            "--operator",
            "mellow",
            "--reference",
            str(reference),
        ]
    )
    blocked_output = capsys.readouterr().out
    assert blocked_exit == 1
    assert "requires --confirm-promotion" in blocked_output

    execute_exit = promote_main(
        [
            "execute",
            skill_id,
            "--operator",
            "mellow",
            "--confirm-promotion",
            "--reference",
            str(reference),
        ]
    )
    execute_output = capsys.readouterr().out
    assert execute_exit == 0
    assert "generated skill manual promotion executed" in execute_output

    show_exit = promote_main(["show", skill_id, "--reference", str(reference)])
    show_output = capsys.readouterr().out
    assert show_exit == 0
    assert "[Promotion]" in show_output
    assert "source_candidate_artifact" in show_output


def test_manual_promotion_show_handles_missing_record(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_promotion_record_report("missing-skill", reference=reference)

    assert output == "generated skill promotion record not found: missing-skill"
