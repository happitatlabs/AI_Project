from agent.generated_skill_sandbox import (
    build_generated_skill_payload,
    load_generated_skill_approval_record,
    load_generated_skill_candidate,
    load_generated_skill_candidate_checklist,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_promotion_record,
    load_generated_skill_queue_record,
    load_generated_skill_review_decision,
    load_generated_skill_rollback_record,
    load_generated_skill_transform_template,
    run_generated_skill_in_sandbox,
    save_generated_skill_draft,
    save_generated_skill_promotion_packet,
    save_generated_skill_review_decision,
    save_generated_skill_transform_template,
)
from local_reviewer_dashboard import (
    build_reviewer_dashboard_detail,
    build_reviewer_dashboard_html,
    build_reviewer_dashboard_queue_items,
    save_reviewer_dashboard_approval,
    save_reviewer_dashboard_checklist,
    execute_reviewer_dashboard_manual_promotion,
    save_reviewer_dashboard_rollback,
    save_reviewer_dashboard_review_decision,
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
                "transaction_id": "txn-dashboard-1",
                "execution_mode": "experimental_sandbox",
                "state": "apply_succeeded",
                "terminal_marker": "apply_succeeded",
                "markers": [{"marker": "apply_succeeded"}],
            }
        },
    )
    return payload["skill_id"], reference


def _prepare_full_candidate(tmp_path):
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
    save_reviewer_dashboard_approval(
        skill_id,
        {
            "approval_type": "transform_approval",
            "decision": "approved",
            "approver": "mellow",
            "rationale": "manual transform reviewed",
            "followup_required": False,
            "notes": ["candidate only"],
            "final_target_name": "runtime_state_summarizer_v1",
            "final_target_path": "skills/runtime_state_summarizer_v1.json",
        },
        reference=str(reference),
    )
    return skill_id, reference


def _prepare_promotion_ready_candidate(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)
    save_reviewer_dashboard_checklist(
        skill_id,
        {
            "operator": "mellow",
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
            "direct_move_not_used": True,
            "target_name": "runtime_state_summarizer_v1",
            "target_path": "skills/runtime_state_summarizer_v1.json",
            "notes": ["promotion ready from dashboard fixture"],
        },
        reference=str(reference),
    )
    return skill_id, reference


def test_queue_list_reads_generated_skill_queue(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    items = build_reviewer_dashboard_queue_items(reference=str(reference))

    assert len(items) == 1
    assert items[0]["skill_id"] == skill_id
    assert items[0]["promotion_status"] == "pending_manual_review"
    assert items[0]["auto_suggestion_available"] is True
    assert items[0]["risk_level"] == "low"
    assert items[0]["recommended_path"] == ["sandbox", "review", "promotion"]


def test_detail_view_includes_validation_sandbox_review_packet_transform_and_approval(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)

    detail = build_reviewer_dashboard_detail(skill_id, reference=str(reference))

    assert detail["skill"]["skill_id"] == skill_id
    assert detail["validation"]["validation_summary"].startswith("validated:")
    assert detail["sandbox"]["execution_mode"] == "experimental_sandbox"
    assert detail["review_decision"]["decision"] == "approve_for_consideration"
    assert detail["promotion_packet"]["summary"]["criteria_check_passed"] is True
    assert "required_manual_edits" in detail["transform_template"]["summary"]
    assert "transform_approval" in detail["approval"]["records"]
    assert detail["candidate_checklist"]["available"] is False
    assert detail["rollback"]["available"] is False
    assert detail["auto_suggestion"]["available"] is False
    assert detail["risk_summary"]["risk_level"] == "low"
    assert detail["risk_summary"]["recommended_path"] == ["sandbox", "review", "promotion"]
    assert detail["flow"]["current_stage"] == "review"
    assert detail["flow"]["selected_skill"] == skill_id
    assert detail["flow"]["sandbox_result"] == "passed"
    assert detail["manual_promotion"]["readiness"]["can_execute"] is False


def test_review_decision_form_save_only_updates_review_record(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)

    saved = save_reviewer_dashboard_review_decision(
        skill_id,
        {
            "decision": "approve_for_consideration",
            "reviewer": "mellow",
            "rationale": "dashboard write",
            "followup_required": False,
            "notes": ["written from dashboard"],
        },
        reference=str(reference),
    )

    assert saved["saved"] is True
    assert load_generated_skill_review_decision(skill_id, reference=reference)["rationale"] == "dashboard write"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before


def test_approval_form_save_only_updates_approval_record(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)

    saved = save_reviewer_dashboard_approval(
        skill_id,
        {
            "approval_type": "promotion_approval",
            "decision": "needs_followup",
            "approver": "mellow",
            "rationale": "rollback reference still missing",
            "followup_required": True,
            "notes": ["follow up before final approval"],
        },
        reference=str(reference),
    )

    assert saved["saved"] is True
    approval = load_generated_skill_approval_record(skill_id, reference=reference)
    assert approval["records"]["promotion_approval"]["decision"] == "needs_followup"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before


def test_detail_view_handles_missing_artifacts_gracefully(tmp_path):
    skill_id, reference = _queue_skill(tmp_path)

    detail = build_reviewer_dashboard_detail(skill_id, reference=str(reference))

    assert detail["review_decision"]["available"] is False
    assert detail["promotion_packet"]["available"] is False
    assert detail["transform_template"]["available"] is False
    assert detail["approval"]["available"] is False
    assert detail["candidate_checklist"]["available"] is False
    assert detail["rollback"]["available"] is False
    assert detail["auto_suggestion"]["available"] is True
    assert detail["flow"]["current_stage"] == "waiting_review"


def test_checklist_form_save_only_updates_checklist_record(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)

    saved = save_reviewer_dashboard_checklist(
        skill_id,
        {
            "operator": "mellow",
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
            "direct_move_not_used": True,
            "target_name": "runtime_state_summarizer_v1",
            "target_path": "skills/runtime_state_summarizer_v1.json",
            "notes": ["written from dashboard"],
        },
        reference=str(reference),
    )

    assert saved["saved"] is True
    assert load_generated_skill_candidate_checklist(skill_id, reference=reference)["target_name"] == "runtime_state_summarizer_v1"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before


def test_rollback_form_save_only_updates_rollback_record(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)

    saved = save_reviewer_dashboard_rollback(
        skill_id,
        {
            "operator": "mellow",
            "reason": "candidate withdrawn after manual review",
            "production_artifact_ref": "skills/runtime_state_summarizer_v1.json",
            "candidate_artifact_ref": "runtime_state_summarizer_v1.candidate",
            "notes": ["written from dashboard"],
        },
        reference=str(reference),
    )

    assert saved["saved"] is True
    assert load_generated_skill_rollback_record(skill_id, reference=reference)["reason"] == "candidate withdrawn after manual review"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before


def test_dashboard_html_includes_queue_detail_write_forms_and_flow_visualization():
    html = build_reviewer_dashboard_html()

    assert "검토 대시보드 v0" in html
    assert "검토 판단" in html
    assert "최종 검토 기록" in html
    assert "승격 전 점검표" in html
    assert "철회 기록" in html
    assert "1단계" in html
    assert "2단계" in html
    assert "3단계" in html
    assert "예외 처리: 철회 기록" in html
    assert "기본 확인" in html
    assert "운영 후보 정리" in html
    assert "안전성 확인" in html
    assert "기존 기록 덮어쓰기" in html
    assert "이 skill이 하는 일" in html
    assert "이 skill이 하려는 일" in html
    assert "자동 추천" in html
    assert "자동 추천 가능" in html
    assert "위험도 / 추천 경로" in html
    assert "위험도:" in html
    assert "추천 경로:" in html
    assert "기술 ID 보기" in html
    assert "런타임 상태 요약 skill" in html
    assert "<option value=\"false\">아니오</option>" in html
    assert "<option value=\"true\">예</option>" in html
    assert "에이전트 오피스" in html
    assert "에이전트 브레인" in html
    assert "샌드박스" in html
    assert "사람 검토" in html
    assert "자동 재생" in html
    assert "초기화" in html
    assert "검토 판단이란?" in html
    assert "기록 유형이란?" in html
    assert "최종 검토 판단이란?" in html
    assert "후속 조치 필요란?" in html
    assert "최종 후보 이름이란?" in html
    assert "최종 후보 경로란?" in html
    assert "자동 승격, sandbox 재실행은 일어나지 않습니다." in html
    assert "approval-prereq-note" in html
    assert "checklist-prereq-note" in html
    assert "review-existing-note" in html
    assert "approval-existing-note" in html
    assert "checklist-existing-note" in html
    assert "rollback-existing-note" in html
    assert "수동 승격 실행" in html
    assert "promotion-modal" in html
    assert "PROMOTE " in html
    assert "/api/promotions/" in html
    assert "review-form-message" in html
    assert "approval-form-message" in html
    assert "checklist-form-message" in html
    assert "rollback-form-message" in html
    assert "/api/queue" in html
    assert "/api/review-decisions/" in html
    assert "/api/approvals/" in html
    assert "/api/checklists/" in html
    assert "/api/rollbacks/" in html


def test_manual_promotion_readiness_shows_missing_reasons_until_checklist_complete(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)

    detail = build_reviewer_dashboard_detail(skill_id, reference=str(reference))

    assert detail["manual_promotion"]["readiness"]["can_execute"] is False
    assert "candidate checklist missing" in detail["manual_promotion"]["readiness"]["blockers"]


def test_manual_promotion_lists_incomplete_checklist_items(tmp_path):
    skill_id, reference = _prepare_full_candidate(tmp_path)
    save_reviewer_dashboard_checklist(
        skill_id,
        {
            "operator": "mellow",
            "review_decision_exists": True,
            "approval_record_exists": True,
            "validation_passed": True,
            "sandbox_passed": True,
            "sandbox_only_confirmed": True,
            "promotion_required_confirmed": True,
            "generated_only_fields_removed": False,
            "target_name_manually_chosen": False,
            "naming_collision_resolved": False,
            "core_skill_overwrite_absent": True,
            "rollback_reference_prepared": False,
            "direct_move_not_used": True,
            "target_name": "runtime_state_summarizer_v1",
            "target_path": "skills/runtime_state_summarizer_v1.json",
            "notes": ["partial checklist for UI visibility test"],
        },
        reference=str(reference),
    )

    detail = build_reviewer_dashboard_detail(skill_id, reference=str(reference))

    assert detail["manual_promotion"]["readiness"]["can_execute"] is False
    assert "초안 전용 항목을 정리했다" in detail["manual_promotion"]["readiness"]["checklist_missing_items"]
    assert "운영 후보 이름을 직접 정했다" in detail["manual_promotion"]["readiness"]["checklist_missing_items"]
    assert "이름 겹침 문제를 확인했다" in detail["manual_promotion"]["readiness"]["checklist_missing_items"]
    assert "문제 시 되돌릴 기준을 적어뒀다" in detail["manual_promotion"]["readiness"]["checklist_missing_items"]


def test_manual_promotion_execute_creates_candidate_and_promotion_record_without_modifying_sources(tmp_path):
    skill_id, reference = _prepare_promotion_ready_candidate(tmp_path)
    queue_before = load_generated_skill_queue_record(skill_id, reference=reference)
    draft_before = load_generated_skill_draft(skill_id, reference=reference)
    review_before = load_generated_skill_review_decision(skill_id, reference=reference)
    packet_before = load_generated_skill_promotion_packet(skill_id, reference=reference)
    transform_before = load_generated_skill_transform_template(skill_id, reference=reference)
    approval_before = load_generated_skill_approval_record(skill_id, reference=reference)
    checklist_before = load_generated_skill_candidate_checklist(skill_id, reference=reference)

    result = execute_reviewer_dashboard_manual_promotion(
        skill_id,
        {
            "operator": "admin",
            "confirm_phrase": f"PROMOTE {skill_id}",
            "notes": ["executed from dashboard test"],
        },
        reference=str(reference),
    )

    assert result["executed"] is True
    assert load_generated_skill_candidate(skill_id, reference=reference)["target_name"] == "runtime_state_summarizer_v1"
    assert load_generated_skill_promotion_record(skill_id, reference=reference)["final_target_name"] == "runtime_state_summarizer_v1"
    assert load_generated_skill_queue_record(skill_id, reference=reference) == queue_before
    assert load_generated_skill_draft(skill_id, reference=reference) == draft_before
    assert load_generated_skill_review_decision(skill_id, reference=reference) == review_before
    assert load_generated_skill_promotion_packet(skill_id, reference=reference) == packet_before
    assert load_generated_skill_transform_template(skill_id, reference=reference) == transform_before
    assert load_generated_skill_approval_record(skill_id, reference=reference) == approval_before
    assert load_generated_skill_candidate_checklist(skill_id, reference=reference) == checklist_before

    refreshed = build_reviewer_dashboard_detail(skill_id, reference=str(reference))
    assert refreshed["manual_promotion"]["candidate"]["available"] is True
    assert refreshed["manual_promotion"]["promotion_record"]["available"] is True
    assert refreshed["manual_promotion"]["promotion_record"]["final_target_path"] == "skills/runtime_state_summarizer_v1.json"


def test_manual_promotion_requires_exact_confirm_phrase(tmp_path):
    skill_id, reference = _prepare_promotion_ready_candidate(tmp_path)

    try:
        execute_reviewer_dashboard_manual_promotion(
            skill_id,
            {
                "operator": "admin",
                "confirm_phrase": f"PROMOTE {skill_id} ",
                "notes": [],
            },
            reference=str(reference),
        )
    except ValueError as exc:
        assert "exactly match" in str(exc)
    else:
        raise AssertionError("expected manual promotion confirmation mismatch to fail")
