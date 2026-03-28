from build_generated_skill_transform import (
    build_generated_skill_transform_show_output,
    main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_review_decision,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
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
                "transaction_id": "txn-transform-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def _prepare_packet(tmp_path):
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
    return skill_id, reference


def test_transform_template_is_created_under_runtime_data(tmp_path):
    skill_id, reference = _prepare_packet(tmp_path)

    saved = save_generated_skill_transform_template(skill_id, reference=reference)
    loaded = load_generated_skill_transform_template(skill_id, reference=reference)

    assert saved["saved"] is True
    assert "runtime-data" in saved["path"]
    assert "generated_skill_transforms" in saved["path"]
    assert loaded["skill_id"] == skill_id


def test_generated_draft_runtime_fields_are_removed_from_template(tmp_path):
    skill_id, reference = _prepare_packet(tmp_path)

    saved = save_generated_skill_transform_template(skill_id, reference=reference)
    template = saved["template"]

    assert "sandbox_only" not in template["proposed_production"]
    assert "promotion_required" not in template["proposed_production"]
    assert "sandbox_only" in template["transform_notes"]["removed_fields"]
    assert "promotion_required" in template["transform_notes"]["removed_fields"]


def test_required_manual_edits_are_included(tmp_path):
    skill_id, reference = _prepare_packet(tmp_path)

    saved = save_generated_skill_transform_template(skill_id, reference=reference)
    edits = saved["template"]["transform_notes"]["required_manual_edits"]

    assert "choose a production-safe target_name" in edits
    assert "replace the placeholder target_path" in edits
    assert "confirm allowed capabilities for production candidate" in edits


def test_overwrite_risk_and_naming_collision_are_reflected(tmp_path):
    skill_id, reference = _prepare_packet(tmp_path)
    collision_path = tmp_path / "skills" / "runtime_state_summarizer"
    collision_path.mkdir(parents=True, exist_ok=True)
    save_generated_skill_promotion_packet(skill_id, reference=reference)

    saved = save_generated_skill_transform_template(skill_id, reference=reference)
    risk_checks = saved["template"]["risk_checks"]

    assert risk_checks["overwrite_risk"] == "high"
    assert risk_checks["naming_collision"] is True
    assert risk_checks["core_skill_conflict"] is True


def test_show_output_uses_block_sections(tmp_path, capsys):
    skill_id, reference = _prepare_packet(tmp_path)
    main(["build", skill_id, "--reference", str(reference)])
    capsys.readouterr()

    exit_code = main(["show", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Source]" in output
    assert "[Proposed Production]" in output
    assert "[Transform Notes]" in output
    assert "[Risk Checks]" in output
    assert "[Promotion Preconditions]" in output


def test_build_without_packet_fails_gracefully(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)

    exit_code = main(["build", skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert output.strip() == f"generated skill promotion packet not found: {skill_id}"


def test_template_can_include_build_warnings_from_packet_blockers(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_promotion_packet(skill_id, reference=reference)

    saved = save_generated_skill_transform_template(skill_id, reference=reference)

    assert saved["template"]["build_warnings"]
    assert "review decision missing" in saved["template"]["build_warnings"][0]


def test_transform_build_does_not_modify_packet_draft_or_review(tmp_path):
    skill_id, reference = _prepare_packet(tmp_path)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)

    save_generated_skill_transform_template(skill_id, reference=reference)

    packet_after = load_generated_skill_promotion_packet(skill_id, reference=reference)
    draft_after = load_generated_skill_draft(skill_id, reference=reference)
    review_after = load_generated_skill_review_decision(skill_id, reference=reference)

    assert packet_after == packet_before
    assert draft_after == draft_before
    assert review_after == review_before


def test_missing_transform_show_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    output = build_generated_skill_transform_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill transform template not found: missing-skill"
