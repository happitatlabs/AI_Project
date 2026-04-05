from review_generated_skills import (
    build_generated_skill_queue_list_output,
    build_generated_skill_queue_show_output,
    main,
)

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    build_generated_skill_queue_summary,
    list_generated_skill_queue,
    load_generated_skill_queue_record,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
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
                "transaction_id": "txn-review-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def test_queue_record_appears_in_list(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    queue = list_generated_skill_queue(reference=reference)

    assert len(queue) == 1
    assert queue[0]["skill_id"] == skill_id


def test_list_output_is_compact_single_line(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    queue = list_generated_skill_queue(reference=reference)
    line = build_generated_skill_queue_summary(queue[0], index=0)
    output = build_generated_skill_queue_list_output(reference=str(reference))

    assert line.startswith("[0] pending_manual_review |")
    assert "validation: ok" in line
    assert "sandbox: passed" in line
    assert output.splitlines()[0].startswith(line)
    assert "auto: 추천 가능" in output.splitlines()[0]
    assert skill_id.rsplit("_", 1)[0] in line


def test_show_output_uses_block_sections(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    output = build_generated_skill_queue_show_output(skill_id, reference=str(reference))

    assert "[Skill]" in output
    assert "[Validation]" in output
    assert "[Sandbox]" in output
    assert "[Promotion Queue]" in output
    assert "[Auto Promotion Suggestion]" in output
    assert "- skill_id: " in output
    assert "- purpose: " in output


def test_show_output_includes_validation_sandbox_and_promotion_fields(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    output = build_generated_skill_queue_show_output(skill_id, reference=str(reference))

    assert "- validation_summary: validated:" in output
    assert "- sandbox_result_summary: runtime state summarized" in output
    assert "- promotion_status: pending_manual_review" in output
    assert "- queued_at: " in output
    assert "- sandbox_only: True" in output
    assert "- promotion_required: True" in output
    assert "- execution_mode: experimental_sandbox" in output


def test_missing_skill_id_is_handled_gracefully(tmp_path):
    reference = _reference(tmp_path)

    assert load_generated_skill_queue_record("missing-skill", reference=reference) is None
    output = build_generated_skill_queue_show_output("missing-skill", reference=str(reference))

    assert output == "generated skill queue record not found: missing-skill"


def test_cli_list_and_show_outputs(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)

    exit_code = main(["list", "--reference", str(reference)])
    list_output = capsys.readouterr().out

    assert exit_code == 0
    assert "pending_manual_review" in list_output
    assert "auto: 추천 가능" in list_output

    exit_code = main(["show", skill_id, "--reference", str(reference)])
    show_output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Skill]" in show_output
    assert "- promotion_status: pending_manual_review" in show_output
    assert "[Auto Promotion Suggestion]" in show_output
