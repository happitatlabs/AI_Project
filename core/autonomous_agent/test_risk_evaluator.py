from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_queue_record,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
)
from agent.risk_evaluator import build_risk_report, evaluate_skill_risk
from evaluate_skill_risk import main as evaluate_skill_risk_main


def _reference(tmp_path):
    return tmp_path / "pending_approvals.json"


def _experimental_flags():
    return {
        "experimental_sandbox": True,
        "confirm_experimental": True,
    }


def _queue_skill(tmp_path, *, skill_kind="runtime_state_summarizer"):
    reference = _reference(tmp_path)
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir(exist_ok=True)
    payload = build_generated_skill_payload(
        purpose="summarize runtime state for manual review",
        generated_by="agent.self_authoring",
        skill_kind=skill_kind,
    )
    save_generated_skill_draft(payload, reference=reference)
    run_generated_skill_in_sandbox(
        payload["skill_id"],
        sandbox_root=sandbox_root,
        reference=reference,
        execution_flags=_experimental_flags(),
        mock_inputs={
            "runtime_state": {
                "transaction_id": "txn-risk-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    save_generated_skill_promotion_packet(payload["skill_id"], reference=reference)
    return payload["skill_id"], reference


def test_low_risk_skill_is_classified_as_low(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    report = evaluate_skill_risk(skill_id, reference=reference)

    assert report["risk_level"] == "low"
    assert report["allowed_skips"] == ["validation", "approval", "checklist"]
    assert report["recommended_path"] == ["sandbox", "review", "promotion"]


def test_high_risk_condition_is_classified_as_high(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    draft = load_generated_skill_draft(skill_id, reference=reference)
    draft["skill_definition"]["capabilities"] = ["read_only", "summary", "network"]

    report = evaluate_skill_risk(skill_id, draft=draft, reference=reference)

    assert report["risk_level"] == "high"
    assert report["allowed_skips"] == []
    assert report["recommended_path"] == ["validation", "sandbox", "review", "approval", "checklist", "promotion"]


def test_medium_risk_condition_is_classified_as_medium(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    draft = load_generated_skill_draft(skill_id, reference=reference)
    draft["skill_definition"]["skill_kind"] = "custom_read_only_formatter"

    report = evaluate_skill_risk(skill_id, draft=draft, reference=reference)

    assert report["risk_level"] == "medium"
    assert report["allowed_skips"] == ["checklist"]
    assert report["recommended_path"] == ["validation", "sandbox", "review", "approval", "promotion"]


def test_output_keeps_required_json_shape(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    report = evaluate_skill_risk(skill_id, reference=reference)

    assert set(report) == {
        "skill_id",
        "risk_level",
        "allowed_skips",
        "required_stages",
        "recommended_path",
        "reason",
        "confidence",
    }


def test_risk_evaluation_does_not_modify_existing_pipeline_artifacts(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)

    report = evaluate_skill_risk(skill_id, reference=reference)

    assert report["risk_level"] == "low"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before


def test_cli_prints_risk_report(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)

    exit_code = evaluate_skill_risk_main([skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Risk Evaluation]" in output
    assert "recommended_path" in output
    assert build_risk_report(skill_id, reference=reference) in output
