import json

from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_queue_record,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
)
from agent.skill_selection import (
    build_skill_selection_report,
    collect_available_skills,
    rank_skill_candidates,
    select_skill_for_task,
)
from select_skill import main


def _reference(tmp_path):
    return tmp_path / "pending_approvals.json"


def _experimental_flags():
    return {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def _write_skill(skill_dir, *, name, description, when_to_use, behavior_class="report"):
    target = skill_dir / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        "\n".join(
            [
                f"# SKILL: {name}",
                "",
                "## name",
                name,
                "",
                "## description",
                description,
                "",
                "## when_to_use",
                when_to_use,
                "",
                "## steps",
                "1. first_step: do the thing",
                "",
                "## risk_level",
                "safe",
                "",
                "## behavior_class",
                behavior_class,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _skills_dir(tmp_path):
    skill_dir = tmp_path / "skills"
    _write_skill(
        skill_dir,
        name="workspace_reporter",
        description="Create a workspace summary report",
        when_to_use="Use for workspace summary and status reporting",
        behavior_class="report",
    )
    _write_skill(
        skill_dir,
        name="code_reviewer",
        description="Review code changes for bugs and regressions",
        when_to_use="Use for code review and regression checks",
        behavior_class="review",
    )
    return skill_dir


def _queue_generated_skill(tmp_path, *, skill_kind, purpose, mock_inputs):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir(exist_ok=True)
    payload = build_generated_skill_payload(
        purpose=purpose,
        generated_by="agent.self_authoring",
        skill_kind=skill_kind,
    )
    save_generated_skill_draft(payload, reference=reference)
    run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs=mock_inputs,
    )
    return payload["skill_id"]


def _prepare_candidates(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _queue_generated_skill(
        tmp_path,
        skill_kind="runtime_state_summarizer",
        purpose="summarize runtime state",
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-select-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    proposal_skill = _queue_generated_skill(
        tmp_path,
        skill_kind="proposal_summary_formatter",
        purpose="format proposal summary",
        mock_inputs={
            "proposal": {
                "proposal_id": "proposal-1",
                "status": "approved",
                "target_paths": ["src/app.py"],
                "change_type": "config_change",
            }
        },
    )
    return skills_dir, runtime_skill, proposal_skill


def test_generated_and_builtin_skills_are_collected(tmp_path):
    skills_dir, runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)

    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)
    skill_ids = {candidate["skill_id"] for candidate in candidates}

    assert "workspace_reporter" in skill_ids
    assert "code_reviewer" in skill_ids
    assert runtime_skill in skill_ids
    assert any(candidate["source"] == "generated" for candidate in candidates)
    assert any(candidate["source"] == "builtin" for candidate in candidates)


def test_task_drives_different_skill_selection(tmp_path):
    skills_dir, runtime_skill, proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)

    runtime_selection = select_skill_for_task(
        task_description="summarize runtime state and marker flow",
        available_skills=candidates,
    )
    proposal_selection = select_skill_for_task(
        task_description="format proposal summary for manual review",
        available_skills=candidates,
    )
    review_selection = select_skill_for_task(
        task_description="review code changes for regressions",
        available_skills=candidates,
    )

    assert runtime_selection["selected_skill"] == runtime_skill
    assert proposal_selection["selected_skill"] == proposal_skill
    assert review_selection["selected_skill"] == "code_reviewer"


def test_invalid_task_uses_deterministic_fallback(tmp_path):
    skills_dir, _runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)

    selection = select_skill_for_task(
        task_description="",
        available_skills=candidates,
    )

    assert selection["selected_skill"] == "workspace_reporter"
    assert selection["confidence"] == "low"
    assert "deterministic fallback" in selection["reason"]


def test_ambiguous_task_uses_deterministic_fallback(tmp_path):
    skills_dir, _runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)

    selection = select_skill_for_task(
        task_description="misc",
        available_skills=candidates,
    )

    assert selection["selected_skill"] == "workspace_reporter"
    assert selection["confidence"] == "low"
    assert "ambiguous" in selection["reason"]


def test_success_failure_memory_affects_ranking(tmp_path):
    skills_dir, runtime_skill, proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)

    ranked = rank_skill_candidates(
        candidates,
        task_description="format proposal summary for manual review",
        past_skill_memory={
            runtime_skill: {"success": 0, "failure": 2},
            proposal_skill: {"success": 3, "failure": 0},
        },
    )
    selection = select_skill_for_task(
        task_description="format proposal summary for manual review",
        available_skills=candidates,
        past_skill_memory={
            runtime_skill: {"success": 0, "failure": 2},
            proposal_skill: {"success": 3, "failure": 0},
        },
    )

    assert ranked[0]["skill_id"] == proposal_skill
    assert selection["selected_skill"] == proposal_skill
    assert "prior success memory" in selection["reason"]


def test_selection_output_keeps_required_json_shape(tmp_path, capsys):
    skills_dir, _runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)

    exit_code = main(
        [
            "--task",
            "summarize runtime state for the latest transaction",
            "--reference",
            str(reference),
            "--skills-dir",
            str(skills_dir),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert set(output) == {"selected_skill", "reason", "confidence", "alternative_candidates"}
    assert isinstance(output["alternative_candidates"], list)
    assert output["selected_skill"]


def test_selection_does_not_modify_existing_artifacts(tmp_path):
    skills_dir, runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    queue_before = load_generated_skill_queue_record(runtime_skill, reference=reference)
    draft_before = load_generated_skill_draft(runtime_skill, reference=reference)

    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)
    selection = select_skill_for_task(
        task_description="summarize runtime state and marker flow",
        available_skills=candidates,
        past_skill_memory=[{"skill_id": runtime_skill, "outcome": "success"}],
    )
    report = build_skill_selection_report(selection)

    assert report["selected_skill"] == runtime_skill
    assert load_generated_skill_queue_record(runtime_skill, reference=reference) == queue_before
    assert load_generated_skill_draft(runtime_skill, reference=reference) == draft_before


def test_generated_candidate_requires_pending_manual_review_when_present(tmp_path):
    skills_dir, runtime_skill, _proposal_skill = _prepare_candidates(tmp_path)
    reference = _reference(tmp_path)
    queue_path = tmp_path / "runtime-data" / "generated_skill_queue" / f"{runtime_skill}.json"
    queue_record = json.loads(queue_path.read_text(encoding="utf-8"))
    queue_record["promotion_status"] = "reviewed"
    queue_path.write_text(json.dumps(queue_record, ensure_ascii=False, indent=2), encoding="utf-8")

    candidates = collect_available_skills(reference=reference, skills_dir=skills_dir)
    skill_ids = {candidate["skill_id"] for candidate in candidates}

    assert runtime_skill not in skill_ids
