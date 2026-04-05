from build_generated_skill_packet import (
    build_generated_skill_packet_show_output,
    main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
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
                "transaction_id": "txn-packet-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def _prepare_reviewed_skill(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox validation passed and low-risk summary skill",
        notes=["manual transform required before production candidate"],
        reference=reference,
    )
    return skill_id, reference


def test_packet_is_created_under_runtime_data(tmp_path):
    skill_id, reference = _prepare_reviewed_skill(tmp_path)

    saved = save_generated_skill_promotion_packet(skill_id, reference=reference)
    loaded = load_generated_skill_promotion_packet(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_packets" in saved["path"]
    assert loaded["skill_id"] == skill_id


def test_packet_build_does_not_modify_queue_draft_or_review_originals(tmp_path):
    skill_id, reference = _prepare_reviewed_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)

    save_generated_skill_promotion_packet(skill_id, reference=reference)

    queue_after = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_after = load_generated_skill_draft(skill_id, reference=reference)
    review_after = load_generated_skill_review_decision(skill_id, reference=reference)

    assert queue_after == queue_before
    assert draft_after == draft_before
    assert review_after == review_before


def test_packet_includes_validation_sandbox_and_review_details(tmp_path):
    skill_id, reference = _prepare_reviewed_skill(tmp_path)

    saved = save_generated_skill_promotion_packet(skill_id, reference=reference)
    packet = saved["packet"]

    assert packet["validation"]["summary"].startswith("validated:")
    assert packet["sandbox"]["result"] == "passed"
    assert packet["sandbox"]["execution_mode"] == "experimental_sandbox"
    assert packet["review_decision"]["decision"] == "approve_for_consideration"
    assert packet["review_decision"]["reviewer"] == "mellow"


def test_packet_handles_missing_review_decision(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    saved = save_generated_skill_promotion_packet(skill_id, reference=reference)
    assessment = saved["packet"]["promotion_assessment"]

    assert assessment["criteria_check_passed"] is False
    assert "review decision missing" in assessment["blockers"]
    assert saved["packet"]["review_decision"]["decision"] == "missing"


def test_criteria_check_passed_is_true_for_reviewed_sandbox_passed_skill(tmp_path):
    skill_id, reference = _prepare_reviewed_skill(tmp_path)

    saved = save_generated_skill_promotion_packet(skill_id, reference=reference)
    assessment = saved["packet"]["promotion_assessment"]

    assert assessment["criteria_check_passed"] is True
    assert assessment["blockers"] == []
    assert assessment["overwrite_risk"] == "none"
    assert assessment["requires_manual_transform"] is True


def test_show_output_uses_block_sections(tmp_path, capsys):
    skill_id, reference = _prepare_reviewed_skill(tmp_path)
    main(["build", skill_id, "--reference", str(reference)])
    capsys.readouterr()

    exit_code = main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Skill]" in output
    assert "[Validation]" in output
    assert "[Sandbox]" in output
    assert "[Review Decision]" in output
    assert "[Promotion Assessment]" in output


def test_missing_packet_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_packet_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill promotion packet not found: missing-skill"
