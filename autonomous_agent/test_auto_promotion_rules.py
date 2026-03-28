from agent.auto_promotion_rules import evaluate_auto_promotion_rules
from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_draft,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
)
from suggest_auto_promotion import main as suggest_auto_promotion_main


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
                "transaction_id": "txn-auto-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    save_generated_skill_promotion_packet(payload["skill_id"], reference=reference)
    return payload["skill_id"], reference


def test_auto_promotion_rules_apply_for_low_risk_generated_skill(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    result = evaluate_auto_promotion_rules(skill_id, reference=reference)

    assert result["auto_applicable"] is True
    assert result["auto_review_decision"]["decision"] == "approve_for_consideration"
    assert result["auto_checklist_suggestions"]["validation_passed"] is True
    assert result["confidence"] == "high"


def test_auto_promotion_rules_block_for_forbidden_capability(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    draft = load_generated_skill_draft(skill_id, reference=reference)
    draft["skill_definition"]["capabilities"] = ["read_only", "summary", "network"]

    result = evaluate_auto_promotion_rules(skill_id, draft=draft, reference=reference)

    assert result["auto_applicable"] is False
    assert "allowlist" in result["blocked_reason"] or "forbidden capabilities" in result["blocked_reason"]


def test_auto_promotion_rules_block_when_validation_failed(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    draft = load_generated_skill_draft(skill_id, reference=reference)
    validation = {"validation_passed": False}

    result = evaluate_auto_promotion_rules(
        skill_id,
        draft=draft,
        validation=validation,
        reference=reference,
    )

    assert result["auto_applicable"] is False
    assert result["blocked_reason"] == "validation did not pass"


def test_auto_promotion_rules_block_when_sandbox_failed(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    draft = load_generated_skill_draft(skill_id, reference=reference)
    sandbox = {"sandbox_result": "failed"}

    result = evaluate_auto_promotion_rules(
        skill_id,
        draft=draft,
        sandbox=sandbox,
        reference=reference,
    )

    assert result["auto_applicable"] is False
    assert result["blocked_reason"] == "sandbox result is not passed"


def test_auto_promotion_rules_block_when_human_review_exists(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    save_generated_skill_review_decision(
        skill_id,
        decision="approve_for_consideration",
        reviewer="mellow",
        rationale="human already reviewed it",
        reference=reference,
    )

    result = evaluate_auto_promotion_rules(skill_id, reference=reference)

    assert result["auto_applicable"] is False
    assert result["blocked_reason"] == "existing human review decision already exists"
    assert load_generated_skill_review_decision(skill_id, reference=reference)["reviewer"] == "mellow"


def test_auto_promotion_output_keeps_required_json_shape(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    result = evaluate_auto_promotion_rules(skill_id, reference=reference)

    assert set(result) == {
        "auto_applicable",
        "auto_review_decision",
        "auto_checklist_suggestions",
        "blocked_reason",
        "confidence",
    }


def test_auto_promotion_rules_do_not_modify_existing_artifacts(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)

    result = evaluate_auto_promotion_rules(skill_id, reference=reference)

    assert result["auto_applicable"] is True
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before


def test_auto_promotion_cli_prints_report(tmp_path, capsys):
    skill_id, reference = _queue_skill(tmp_path)

    exit_code = suggest_auto_promotion_main([skill_id, "--reference", str(reference)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[Auto Promotion Suggestion]" in output
    assert "approve_for_consideration" in output
