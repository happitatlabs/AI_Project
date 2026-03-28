import json
import tempfile
from pathlib import Path

from agent.agent_brain import (
    build_agent_brain_proposal_report,
    load_agent_brain_proposal,
    run_agent_brain_selection,
    save_agent_brain_proposal,
    validate_llm_skill_selector_output,
)
from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
    save_generated_skill_transform_template,
)
from agent.sandbox_task_loop import (
    build_task_history_memory,
    load_sandbox_task_result,
    run_sandbox_single_step,
    run_sandbox_task_once,
)
from local_reviewer_dashboard import build_reviewer_dashboard_detail
from run_sandbox_task import main


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
    sandbox_root = tmp_path / "prepare-sandbox"
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


def _prepare_generated_runtime_skill(tmp_path):
    skill_id = _queue_generated_skill(
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
    return skill_id


def _prepare_review_packet_transform(tmp_path, skill_id):
    reference = _reference(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="sandbox passed and low-risk summary skill",
        reference=reference,
    )
    save_generated_skill_promotion_packet(skill_id, reference=reference)
    save_generated_skill_transform_template(skill_id, reference=reference)


def test_agent_brain_saves_selection_proposal_artifact(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
    )
    saved = save_agent_brain_proposal(proposal, reference=reference)
    loaded = load_agent_brain_proposal(proposal["run_id"], reference=reference)

    assert saved["path"].endswith(f"runtime-data\\brain_proposals\\{proposal['run_id']}.json")
    assert loaded["selection"]["selected_skill"] == runtime_skill
    assert loaded["execution_mode"] == "experimental_sandbox"
    assert loaded["risk_summary"]["risk_level"] == "low"
    assert loaded["risk_summary"]["recommended_path"] == ["sandbox", "review", "promotion"]


def test_agent_brain_report_includes_selection_and_risk_summary(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
    )

    report = build_agent_brain_proposal_report(proposal, reference=reference)

    assert "[Selection]" in report
    assert "[Risk Summary]" in report
    assert "selection_confidence" in report
    assert "recommended_path" in report


def test_agent_brain_proposal_is_saved_even_if_risk_evaluator_fails(tmp_path, monkeypatch):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    def _broken_risk(*args, **kwargs):
        raise RuntimeError("risk evaluator unavailable")

    monkeypatch.setattr("agent.agent_brain.evaluate_skill_risk", _broken_risk)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
    )
    saved = save_agent_brain_proposal(proposal, reference=reference)
    loaded = load_agent_brain_proposal(proposal["run_id"], reference=reference)

    assert proposal["selection"]["selected_skill"] == runtime_skill
    assert proposal["risk_summary"] is None
    assert proposal["risk_warnings"]
    assert saved["saved"] is True
    assert loaded["risk_summary"] is None


def test_dashboard_flow_uses_latest_brain_proposal_risk_summary(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
    )
    save_agent_brain_proposal(proposal, reference=reference)

    detail = build_reviewer_dashboard_detail(runtime_skill, reference=str(reference))

    assert detail["flow"]["proposal_risk_level"] == "low"
    assert detail["flow"]["proposal_recommended_path"] == ["sandbox", "review", "promotion"]


def test_llm_selector_output_validation_rejects_execution_shaped_payload(tmp_path):
    skill_id = _prepare_generated_runtime_skill(tmp_path)
    report = validate_llm_skill_selector_output(
        {
            "selected_skill": skill_id,
            "reason": "do it",
            "confidence": "high",
            "alternative_candidates": [],
            "command": "run-now",
        },
        available_skills=[{"skill_id": skill_id}],
    )

    assert report["valid"] is False
    assert any("unsupported keys" in error or "execution-oriented" in error for error in report["errors"])


def test_invalid_llm_selector_falls_back_to_deterministic_rules(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        llm_selector=lambda _payload: {
            "selected_skill": "not-a-real-skill",
            "reason": "bad selector output",
            "confidence": "high",
            "alternative_candidates": [],
            "command": "execute",
        },
    )

    assert proposal["selection"]["selected_skill"] == runtime_skill
    assert "rule ranking" in proposal["selection"]["reason"]


def test_operational_mode_blocks_single_run_and_saves_history(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    _prepare_review_packet_transform(tmp_path, runtime_skill)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags={},
    )
    saved = save_agent_brain_proposal(proposal, reference=reference)
    temp_sandbox_root = Path(tempfile.mkdtemp()) / "single-run-operational"
    temp_sandbox_root.mkdir(parents=True, exist_ok=True)

    queue_before = load_generated_skill_queue_record(runtime_skill, reference=reference)
    draft_before = load_generated_skill_draft(runtime_skill, reference=reference)
    review_before = load_generated_skill_review_decision(runtime_skill, reference=reference)
    packet_before = load_generated_skill_promotion_packet(runtime_skill, reference=reference)
    transform_before = load_generated_skill_transform_template(runtime_skill, reference=reference)

    result = run_sandbox_single_step(
        saved["proposal"],
        sandbox_root=temp_sandbox_root,
        reference=reference,
        execution_flags={},
        mock_inputs={},
    )

    assert result["task_result"]["blocked"] is True
    assert result["task_result"]["execution_mode"] == "operational"
    assert load_generated_skill_queue_record(runtime_skill, reference=reference) == queue_before
    assert load_generated_skill_draft(runtime_skill, reference=reference) == draft_before
    assert load_generated_skill_review_decision(runtime_skill, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(runtime_skill, reference=reference) == packet_before
    assert load_generated_skill_transform_template(runtime_skill, reference=reference) == transform_before


def test_non_temp_sandbox_root_is_blocked(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)

    proposal = run_agent_brain_selection(
        task_description="summarize runtime state for manual review",
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
    )
    saved = save_agent_brain_proposal(proposal, reference=reference)

    result = run_sandbox_single_step(
        saved["proposal"],
        sandbox_root=Path.cwd() / "non_temp_sandbox_root_should_block",
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={},
    )

    assert result["task_result"]["blocked"] is True
    assert result["task_result"]["reason"] == "sandbox_single_run_requires_experimental_mode"


def test_experimental_single_run_uses_isolated_execution_and_preserves_original_artifacts(tmp_path):
    skills_dir = _skills_dir(tmp_path)
    runtime_skill = _prepare_generated_runtime_skill(tmp_path)
    _prepare_review_packet_transform(tmp_path, runtime_skill)
    reference = _reference(tmp_path)
    temp_sandbox_root = Path(tempfile.mkdtemp()) / "single-run-experimental"
    temp_sandbox_root.mkdir(parents=True, exist_ok=True)

    queue_before = load_generated_skill_queue_record(runtime_skill, reference=reference)
    draft_before = load_generated_skill_draft(runtime_skill, reference=reference)
    review_before = load_generated_skill_review_decision(runtime_skill, reference=reference)
    packet_before = load_generated_skill_promotion_packet(runtime_skill, reference=reference)
    transform_before = load_generated_skill_transform_template(runtime_skill, reference=reference)

    result = run_sandbox_task_once(
        task_description="summarize runtime state for manual review",
        sandbox_root=temp_sandbox_root,
        reference=reference,
        skills_dir=skills_dir,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-single-run-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [
                    {"marker": "apply_started"},
                    {"marker": "apply_succeeded"},
                ],
            }
        },
    )
    run_id = result["proposal"]["proposal"]["run_id"]
    saved_history = load_sandbox_task_result(run_id, reference=reference)
    memory = build_task_history_memory(reference=reference)

    assert result["task_result"]["task_result"]["sandbox_result"] == "passed"
    assert saved_history["selected_skill"] == runtime_skill
    assert memory[runtime_skill]["success"] >= 1
    assert load_generated_skill_queue_record(runtime_skill, reference=reference) == queue_before
    assert load_generated_skill_draft(runtime_skill, reference=reference) == draft_before
    assert load_generated_skill_review_decision(runtime_skill, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(runtime_skill, reference=reference) == packet_before
    assert load_generated_skill_transform_template(runtime_skill, reference=reference) == transform_before


def test_single_run_cli_outputs_summary(tmp_path, capsys):
    skills_dir = _skills_dir(tmp_path)
    _prepare_generated_runtime_skill(tmp_path)
    reference = _reference(tmp_path)
    temp_sandbox_root = Path(tempfile.mkdtemp()) / "single-run-cli"
    temp_sandbox_root.mkdir(parents=True, exist_ok=True)
    mock_file = tmp_path / "mock_inputs.json"
    mock_file.write_text(json.dumps({
        "runtime_state": {
            "transaction_id": "txn-cli-1",
            "execution_mode": "experimental_sandbox",
            "state": "apply_succeeded",
            "terminal_marker": "apply_succeeded",
            "markers": [{"marker": "apply_succeeded"}],
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(
        [
            "--task",
            "summarize runtime state for manual review",
            "--reference",
            str(reference),
            "--skills-dir",
            str(skills_dir),
            "--sandbox-root",
            str(temp_sandbox_root),
            "--mock-input-file",
            str(mock_file),
            "--experimental-sandbox",
            "--confirm-experimental",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert set(output) == {
        "run_id",
        "selected_skill",
        "selection_confidence",
        "risk_level",
        "recommended_path",
        "risk_confidence",
        "sandbox_result",
        "result_summary",
        "proposal_path",
        "task_history_path",
    }
    assert output["run_id"]
    assert output["risk_level"] == "low"
    assert output["recommended_path"] == ["sandbox", "review", "promotion"]
