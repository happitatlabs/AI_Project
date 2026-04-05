#!/usr/bin/env python3
"""
local_reviewer_dashboard.py -- local-only generated skill reviewer dashboard v0
"""

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from agent.auto_promotion_rules import evaluate_auto_promotion_rules
from agent.generated_skill_sandbox import (
    build_generated_skill_manual_promotion_readiness,
    execute_generated_skill_manual_promotion,
    list_generated_skill_queue,
    load_generated_skill_approval_record,
    load_generated_skill_candidate,
    load_generated_skill_candidate_checklist,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_promotion_record,
    load_generated_skill_queue_record,
    load_generated_skill_result,
    load_generated_skill_review_decision,
    load_generated_skill_rollback_record,
    load_generated_skill_transform_template,
    save_generated_skill_approval_record,
    save_generated_skill_candidate_checklist,
    save_generated_skill_review_decision,
    save_generated_skill_rollback_record,
)
from agent.risk_evaluator import evaluate_skill_risk
from agent.workspace_metrics import resolve_runtime_data_root


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def _detail_none(message: str) -> dict:
    return {
        "available": False,
        "message": message,
    }


CHECKLIST_FIELD_LABELS = {
    "review_decision_exists": "검토 판단을 이미 남겼다",
    "approval_record_exists": "최종 검토 기록을 이미 남겼다",
    "validation_passed": "자동 검증을 통과했다",
    "sandbox_passed": "샌드박스 실행을 통과했다",
    "sandbox_only_confirmed": "샌드박스 전용 원칙을 다시 확인했다",
    "promotion_required_confirmed": "사람 승인 전에는 운영 반영하지 않음을 확인했다",
    "generated_only_fields_removed": "초안 전용 항목을 정리했다",
    "target_name_manually_chosen": "운영 후보 이름을 직접 정했다",
    "naming_collision_resolved": "이름 겹침 문제를 확인했다",
    "core_skill_overwrite_absent": "기존 핵심 skill을 덮어쓰지 않는다",
    "rollback_reference_prepared": "문제 시 되돌릴 기준을 적어뒀다",
    "direct_move_not_used": "초안 파일을 그대로 옮기지 않는다",
}


def _read_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_runtime_artifact(
    dirname: str,
    *,
    reference: str | None = None,
    matcher=None,
) -> dict | None:
    artifact_dir = resolve_runtime_data_root(reference or DEFAULT_REFERENCE) / dirname
    if not artifact_dir.exists():
        return None

    matches: list[dict] = []
    for path in sorted(artifact_dir.glob("*.json")):
        payload = _read_json_file(path)
        if payload is None:
            continue
        if matcher is not None and not matcher(payload):
            continue
        payload = dict(payload)
        payload["_path"] = str(path)
        matches.append(payload)

    if not matches:
        return None

    matches.sort(
        key=lambda payload: (
            str(payload.get("recorded_at") or ""),
            str(payload.get("created_at") or ""),
            str(payload.get("queued_at") or ""),
            str(payload.get("run_id") or ""),
        ),
        reverse=True,
    )
    return matches[0]


def _build_visual_flow_state(
    *,
    skill_id: str,
    queue_record: dict | None,
    draft: dict,
    sandbox_snapshot: dict,
    review_decision: dict | None,
    approval_record: dict | None,
    candidate_checklist: dict | None,
    rollback_record: dict | None,
    reference: str | None = None,
) -> dict:
    latest_proposal = _latest_runtime_artifact(
        "brain_proposals",
        reference=reference,
        matcher=lambda payload: (
            str((payload.get("selection") or {}).get("selected_skill") or "") == skill_id
            or str(((payload.get("selected_candidate") or {}).get("skill_id") or "")) == skill_id
        ),
    )
    latest_task_history = _latest_runtime_artifact(
        "task_history",
        reference=reference,
        matcher=lambda payload: str(payload.get("selected_skill") or "") == skill_id,
    )

    sandbox_result = str(sandbox_snapshot.get("sandbox_result") or "unknown")
    promotion_status = str((queue_record or {}).get("promotion_status") or "none")
    approval_records = (approval_record or {}).get("records") or {}
    transform_approval = approval_records.get("transform_approval") or {}
    has_approval = bool(approval_records)
    has_checklist = bool(candidate_checklist)
    has_rollback = bool(rollback_record)
    has_review = bool(review_decision)
    has_sandbox = bool(sandbox_snapshot or draft.get("sandbox_result_summary"))

    stage = "office"
    stage_title = "오피스 대기"
    stage_description = "아직 선택된 실행 흐름이 없습니다."
    station = "office"

    if latest_proposal:
        stage = "brain"
        stage_title = "브레인 선택 완료"
        stage_description = "에이전트가 현재 작업에 맞는 skill 후보를 골랐습니다."
        station = "brain"

    if has_sandbox and sandbox_result == "failed":
        stage = "failed"
        stage_title = "샌드박스 실패"
        stage_description = "샌드박스 1회 실행이 실패했습니다."
        station = "sandbox"
    elif has_sandbox and sandbox_result == "passed":
        stage = "sandbox"
        stage_title = "샌드박스 통과"
        stage_description = "선택된 skill이 experimental sandbox에서 1회 검증을 통과했습니다."
        station = "sandbox"

    if promotion_status == "pending_manual_review" or has_review or has_checklist or has_approval:
        stage = "review"
        stage_title = "리뷰 진행 중"
        stage_description = "사람 검토와 승인 기록이 이어지는 단계입니다."
        station = "review"

    if has_sandbox and sandbox_result == "passed" and not has_review:
        stage = "waiting_review"
        stage_title = "리뷰 대기"
        stage_description = "샌드박스를 통과했고, 이제 사람 검토를 기다립니다."
        station = "review"

    if has_checklist and has_approval and not has_rollback:
        stage = "success"
        stage_title = "리뷰 준비 완료"
        stage_description = "체크리스트와 승인 기록이 존재하며, 수동 승격 전 검토 입력이 모였습니다."
        station = "review"

    if has_rollback:
        stage = "failed"
        stage_title = "롤백 기록됨"
        stage_description = "이 후보는 롤백 또는 철회 기록이 남아 있는 상태입니다."
        station = "review"

    task_description = (
        str((latest_task_history or {}).get("task_description") or "").strip()
        or str((latest_proposal or {}).get("task_description") or "").strip()
        or str((queue_record or {}).get("purpose") or draft.get("purpose") or "").strip()
        or "none"
    )
    run_id = (
        str((latest_task_history or {}).get("run_id") or "").strip()
        or str((latest_proposal or {}).get("run_id") or "").strip()
        or str(sandbox_snapshot.get("run_id") or "").strip()
        or "none"
    )
    confidence = str(((latest_proposal or {}).get("selection") or {}).get("confidence") or "none")
    proposal_risk = (latest_proposal or {}).get("risk_summary") or {}
    sequence_map = {
        "office": ["office"],
        "brain": ["office", "brain"],
        "sandbox": ["office", "brain", "sandbox"],
        "waiting_review": ["office", "brain", "sandbox", "review"],
        "review": ["office", "brain", "sandbox", "review"],
        "success": ["office", "brain", "sandbox", "review"],
        "failed": ["office", "brain", "sandbox", station],
    }

    return {
        "current_stage": stage,
        "current_station": station,
        "stage_title": stage_title,
        "stage_description": stage_description,
        "selected_skill": skill_id,
        "task_description": task_description,
        "run_id": run_id,
        "confidence": confidence,
        "proposal_risk_level": proposal_risk.get("risk_level") or "none",
        "proposal_recommended_path": proposal_risk.get("recommended_path") or [],
        "sandbox_result": sandbox_result,
        "review_status": promotion_status,
        "review_decision": (review_decision or {}).get("decision") or "none",
        "approval_present": has_approval,
        "checklist_present": has_checklist,
        "rollback_present": has_rollback,
        "sequence": sequence_map.get(stage, ["office"]),
        "proposal_path": (latest_proposal or {}).get("_path"),
        "task_history_path": (latest_task_history or {}).get("_path"),
        "final_target_name": transform_approval.get("final_target_name") or (candidate_checklist or {}).get("target_name") or "none",
    }


def build_reviewer_dashboard_queue_items(
    *,
    reference: str | None = None,
) -> list[dict]:
    resolved_reference = reference or DEFAULT_REFERENCE
    items = []
    for entry in list_generated_skill_queue(reference=resolved_reference):
        skill_id = str(entry.get("skill_id", ""))
        draft = load_generated_skill_draft(skill_id, reference=resolved_reference) or {}
        skill_definition = draft.get("skill_definition") or {}
        review_decision = load_generated_skill_review_decision(skill_id, reference=resolved_reference)
        candidate_checklist = load_generated_skill_candidate_checklist(skill_id, reference=resolved_reference)
        auto = evaluate_auto_promotion_rules(
            skill_id,
            draft=draft,
            validation=draft.get("last_validation_report") or {},
            sandbox=draft.get("last_sandbox_result") or {},
            existing_review=review_decision,
            existing_checklist=candidate_checklist,
            reference=resolved_reference,
        )
        risk = evaluate_skill_risk(
            skill_id,
            draft=draft,
            validation=draft.get("last_validation_report") or {},
            sandbox=draft.get("last_sandbox_result") or {},
            reference=resolved_reference,
        )
        items.append(
            {
                "skill_id": skill_id,
                "purpose": entry.get("purpose") or draft.get("purpose") or "none",
                "skill_kind": skill_definition.get("skill_kind", "unknown"),
                "promotion_status": entry.get("promotion_status", "unknown"),
                "validation_summary": entry.get("validation_summary") or draft.get("validation_summary") or "unknown",
                "sandbox_result_summary": entry.get("sandbox_result_summary") or draft.get("sandbox_result_summary") or "unknown",
                "queued_at": entry.get("queued_at", "unknown"),
                "auto_suggestion_available": auto["auto_applicable"],
                "auto_suggestion_reason": auto["auto_review_decision"]["reason"] if auto["auto_review_decision"] else auto["blocked_reason"],
                "risk_level": risk["risk_level"],
                "recommended_path": risk["recommended_path"],
            }
        )
    return items


def build_reviewer_dashboard_detail(
    skill_id: str,
    *,
    reference: str | None = None,
) -> dict:
    resolved_reference = reference or DEFAULT_REFERENCE
    queue_record = load_generated_skill_queue_record(skill_id, reference=resolved_reference)
    draft = load_generated_skill_draft(skill_id, reference=resolved_reference)
    if draft is None and queue_record is None:
        return {
            "skill_id": skill_id,
            "not_found": True,
            "message": f"generated skill not found: {skill_id}",
        }

    draft = draft or {}
    skill_definition = draft.get("skill_definition") or {}
    validation_report = draft.get("last_validation_report") or {}
    sandbox_snapshot = draft.get("last_sandbox_result") or {}
    sandbox_result = (
        load_generated_skill_result(str(sandbox_snapshot.get("run_id")), reference=resolved_reference)
        if sandbox_snapshot.get("run_id")
        else None
    )
    review_decision = load_generated_skill_review_decision(skill_id, reference=resolved_reference)
    promotion_packet = load_generated_skill_promotion_packet(skill_id, reference=resolved_reference)
    transform_template = load_generated_skill_transform_template(skill_id, reference=resolved_reference)
    approval_record = load_generated_skill_approval_record(skill_id, reference=resolved_reference)
    candidate_checklist = load_generated_skill_candidate_checklist(skill_id, reference=resolved_reference)
    rollback_record = load_generated_skill_rollback_record(skill_id, reference=resolved_reference)
    candidate_artifact = load_generated_skill_candidate(skill_id, reference=resolved_reference)
    promotion_record = load_generated_skill_promotion_record(skill_id, reference=resolved_reference)
    manual_promotion_readiness = build_generated_skill_manual_promotion_readiness(
        skill_id,
        reference=resolved_reference,
    )
    auto_suggestion = evaluate_auto_promotion_rules(
        skill_id,
        draft=draft,
        validation=validation_report,
        sandbox=sandbox_snapshot,
        packet=promotion_packet,
        existing_review=review_decision,
        existing_checklist=candidate_checklist,
        reference=resolved_reference,
    )
    risk_summary = evaluate_skill_risk(
        skill_id,
        draft=draft,
        validation=validation_report,
        sandbox=sandbox_snapshot,
        packet=promotion_packet,
        reference=resolved_reference,
    )
    approval_records = (approval_record or {}).get("records") or {}
    transform_approval = approval_records.get("transform_approval") or {}
    flow = _build_visual_flow_state(
        skill_id=skill_id,
        queue_record=queue_record,
        draft=draft,
        sandbox_snapshot=sandbox_snapshot,
        review_decision=review_decision,
        approval_record=approval_record,
        candidate_checklist=candidate_checklist,
        rollback_record=rollback_record,
        reference=resolved_reference,
    )

    candidate_path = (
        str(resolve_runtime_data_root(resolved_reference) / "generated_skill_candidates" / f"{skill_id}.candidate.json")
        if candidate_artifact
        else None
    )
    promotion_path = (
        str(resolve_runtime_data_root(resolved_reference) / "generated_skill_reviews" / f"{skill_id}.promotion.json")
        if promotion_record
        else None
    )
    ui_promotion_blockers = list(manual_promotion_readiness.get("blockers", []))
    if candidate_artifact:
        ui_promotion_blockers.append("candidate artifact already exists")
    if promotion_record:
        ui_promotion_blockers.append("promotion record already exists")
    ui_can_execute = not ui_promotion_blockers
    checklist_missing_items = []
    if candidate_checklist:
        for field, label in CHECKLIST_FIELD_LABELS.items():
            if not bool(candidate_checklist.get(field, False)):
                checklist_missing_items.append(label)
    return {
        "skill_id": skill_id,
        "not_found": False,
        "flow": flow,
        "skill": {
            "skill_id": skill_id,
            "purpose": (queue_record or {}).get("purpose") or draft.get("purpose") or "none",
            "status": draft.get("status", "unknown"),
            "promotion_status": (queue_record or {}).get("promotion_status", "none"),
            "capabilities": list(skill_definition.get("capabilities", [])),
            "generated_by": draft.get("generated_by", "unknown"),
            "skill_kind": skill_definition.get("skill_kind", "unknown"),
        },
        "validation": {
            "available": bool(validation_report or draft.get("validation_summary")),
            "validation_summary": draft.get("validation_summary", "unknown"),
            "validation_errors": list(validation_report.get("validation_errors", [])),
            "validation_warnings": list(validation_report.get("validation_warnings", [])),
        },
        "sandbox": {
            "available": bool(sandbox_snapshot or draft.get("sandbox_result_summary")),
            "sandbox_result_summary": draft.get("sandbox_result_summary", "unknown"),
            "sandbox_result": sandbox_snapshot.get("sandbox_result", "unknown"),
            "run_id": sandbox_snapshot.get("run_id", "none"),
            "execution_mode": (sandbox_result or {}).get(
                "execution_mode",
                sandbox_snapshot.get("execution_mode", "unknown"),
            ),
        },
        "review_decision": (
            {
                "available": True,
                **review_decision,
            }
            if review_decision
            else _detail_none("none")
        ),
        "promotion_packet": (
            {
                "available": True,
                "summary": {
                    "criteria_check_passed": promotion_packet.get("promotion_assessment", {}).get("criteria_check_passed", False),
                    "overwrite_risk": promotion_packet.get("promotion_assessment", {}).get("overwrite_risk", "unknown"),
                    "blockers": list(promotion_packet.get("promotion_assessment", {}).get("blockers", [])),
                    "warnings": list(promotion_packet.get("promotion_assessment", {}).get("warnings", [])),
                },
                "raw": promotion_packet,
            }
            if promotion_packet
            else _detail_none("not available")
        ),
        "transform_template": (
            {
                "available": True,
                "summary": {
                    "target_name": transform_template.get("proposed_production", {}).get("target_name", ""),
                    "target_path": transform_template.get("proposed_production", {}).get("target_path", "none"),
                    "required_manual_edits": list(transform_template.get("transform_notes", {}).get("required_manual_edits", [])),
                    "removed_fields": list(transform_template.get("transform_notes", {}).get("removed_fields", [])),
                    "risk_checks": dict(transform_template.get("risk_checks", {})),
                },
                "raw": transform_template,
            }
            if transform_template
            else _detail_none("not available")
        ),
        "candidate_checklist": (
            {
                "available": True,
                **candidate_checklist,
            }
            if candidate_checklist
            else _detail_none("none")
        ),
        "approval": (
            {
                "available": True,
                **approval_record,
            }
            if approval_record
            else _detail_none("none")
        ),
        "rollback": (
            {
                "available": True,
                **rollback_record,
            }
            if rollback_record
            else _detail_none("none")
        ),
        "manual_promotion": {
            "readiness": {
                **manual_promotion_readiness,
                "can_execute": ui_can_execute,
                "blockers": ui_promotion_blockers,
                "approval_exists": bool(approval_record),
                "review_exists": bool(review_decision),
                "checklist_exists": bool(candidate_checklist),
                "transform_exists": bool(transform_template),
                "checklist_all_checks_passed": bool((candidate_checklist or {}).get("all_checks_passed")),
                "target_name": (candidate_checklist or {}).get("target_name") or transform_approval.get("final_target_name") or "",
                "target_path": (candidate_checklist or {}).get("target_path") or transform_approval.get("final_target_path") or "",
                "naming_collision_resolved": bool((candidate_checklist or {}).get("naming_collision_resolved", False)),
                "direct_move_not_used": bool((candidate_checklist or {}).get("direct_move_not_used", False)),
                "rollback_reference_prepared": bool((candidate_checklist or {}).get("rollback_reference_prepared", False)),
                "overwrite_risk": (
                    (transform_template or {}).get("risk_checks", {}) or {}
                ).get("overwrite_risk", "unknown"),
                "rollback_reference": transform_approval.get("rollback_reference") or (rollback_record or {}).get("rollback_reference") or "none",
                "checklist_missing_items": checklist_missing_items,
            },
            "candidate": (
                {
                    "available": True,
                    "_path": candidate_path,
                    **candidate_artifact,
                }
                if candidate_artifact
                else _detail_none("none")
            ),
            "promotion_record": (
                {
                    "available": True,
                    "_path": promotion_path,
                    **promotion_record,
                }
                if promotion_record
                else _detail_none("none")
            ),
            "confirm_phrase": f"PROMOTE {skill_id}",
        },
        "auto_suggestion": {
            "available": auto_suggestion["auto_applicable"],
            "summary": auto_suggestion,
        },
        "risk_summary": risk_summary,
        "review_form_defaults": {
            "decision": (review_decision or {}).get("decision") or "approve_for_consideration",
            "reviewer": (review_decision or {}).get("reviewer") or "",
            "rationale": (review_decision or {}).get("rationale") or "",
            "followup_required": bool((review_decision or {}).get("followup_required", False)),
            "notes": list((review_decision or {}).get("notes", [])),
        },
        "checklist_form_defaults": {
            "operator": (candidate_checklist or {}).get("operator") or "",
            "review_decision_exists": bool((candidate_checklist or {}).get("review_decision_exists", bool(review_decision))),
            "approval_record_exists": bool((candidate_checklist or {}).get("approval_record_exists", bool(approval_record))),
            "validation_passed": bool((candidate_checklist or {}).get("validation_passed", validation_report.get("validation_passed", False))),
            "sandbox_passed": bool((candidate_checklist or {}).get("sandbox_passed", sandbox_snapshot.get("sandbox_result") == "passed")),
            "sandbox_only_confirmed": bool((candidate_checklist or {}).get("sandbox_only_confirmed", draft.get("sandbox_only", False))),
            "promotion_required_confirmed": bool((candidate_checklist or {}).get("promotion_required_confirmed", draft.get("promotion_required", False))),
            "generated_only_fields_removed": bool((candidate_checklist or {}).get("generated_only_fields_removed", False)),
            "target_name_manually_chosen": bool((candidate_checklist or {}).get("target_name_manually_chosen", False)),
            "naming_collision_resolved": bool((candidate_checklist or {}).get("naming_collision_resolved", False)),
            "core_skill_overwrite_absent": bool((candidate_checklist or {}).get("core_skill_overwrite_absent", False)),
            "rollback_reference_prepared": bool((candidate_checklist or {}).get("rollback_reference_prepared", False)),
            "direct_move_not_used": bool((candidate_checklist or {}).get("direct_move_not_used", False)),
            "target_name": (candidate_checklist or {}).get("target_name") or transform_approval.get("final_target_name") or "",
            "target_path": (candidate_checklist or {}).get("target_path") or transform_approval.get("final_target_path") or "",
            "notes": list((candidate_checklist or {}).get("notes", [])),
        },
        "approval_form_defaults": {
            "approval_type": "transform_approval",
            "decision": transform_approval.get("decision") or "needs_followup",
            "approver": transform_approval.get("approver") or "",
            "rationale": transform_approval.get("rationale") or "",
            "followup_required": bool(transform_approval.get("followup_required", False)),
            "notes": list(transform_approval.get("notes", [])),
            "source_review_decision": (review_decision or {}).get("decision") or "none",
            "source_packet_id": f"{skill_id}.packet" if promotion_packet else "none",
            "source_transform_template": f"{skill_id}.transform" if transform_template else "none",
            "final_target_name": transform_approval.get("final_target_name") or "",
            "final_target_path": transform_approval.get("final_target_path") or "",
            "rollback_reference": transform_approval.get("rollback_reference") or "",
        },
        "rollback_form_defaults": {
            "operator": (rollback_record or {}).get("operator") or "",
            "reason": (rollback_record or {}).get("reason") or "",
            "production_artifact_ref": (rollback_record or {}).get("production_artifact_ref") or transform_approval.get("final_target_path") or "",
            "candidate_artifact_ref": (rollback_record or {}).get("candidate_artifact_ref") or "",
            "rollback_reference": (rollback_record or {}).get("rollback_reference") or "",
            "notes": list((rollback_record or {}).get("notes", [])),
        },
        "manual_promotion_defaults": {
            "operator": (promotion_record or {}).get("operator") or transform_approval.get("approver") or "",
            "notes": list((promotion_record or {}).get("notes", [])),
        },
    }


def save_reviewer_dashboard_review_decision(
    skill_id: str,
    payload: dict,
    *,
    reference: str | None = None,
) -> dict:
    return save_generated_skill_review_decision(
        skill_id,
        decision=str(payload.get("decision") or ""),
        reviewer=str(payload.get("reviewer") or ""),
        rationale=str(payload.get("rationale") or ""),
        followup_required=bool(payload.get("followup_required", False)),
        notes=list(payload.get("notes") or []),
        allow_replace=bool(payload.get("allow_replace", False)),
        reference=reference or DEFAULT_REFERENCE,
    )


def save_reviewer_dashboard_approval(
    skill_id: str,
    payload: dict,
    *,
    reference: str | None = None,
) -> dict:
    return save_generated_skill_approval_record(
        skill_id,
        approval_type=str(payload.get("approval_type") or ""),
        decision=str(payload.get("decision") or ""),
        approver=str(payload.get("approver") or ""),
        rationale=str(payload.get("rationale") or ""),
        followup_required=bool(payload.get("followup_required", False)),
        notes=list(payload.get("notes") or []),
        final_target_name=payload.get("final_target_name") or None,
        final_target_path=payload.get("final_target_path") or None,
        rollback_reference=payload.get("rollback_reference") or None,
        allow_replace=bool(payload.get("allow_replace", False)),
        reference=reference or DEFAULT_REFERENCE,
    )


def save_reviewer_dashboard_checklist(
    skill_id: str,
    payload: dict,
    *,
    reference: str | None = None,
) -> dict:
    return save_generated_skill_candidate_checklist(
        skill_id,
        operator=str(payload.get("operator") or ""),
        review_decision_exists=bool(payload.get("review_decision_exists", False)),
        approval_record_exists=bool(payload.get("approval_record_exists", False)),
        validation_passed=bool(payload.get("validation_passed", False)),
        sandbox_passed=bool(payload.get("sandbox_passed", False)),
        sandbox_only_confirmed=bool(payload.get("sandbox_only_confirmed", False)),
        promotion_required_confirmed=bool(payload.get("promotion_required_confirmed", False)),
        generated_only_fields_removed=bool(payload.get("generated_only_fields_removed", False)),
        target_name_manually_chosen=bool(payload.get("target_name_manually_chosen", False)),
        naming_collision_resolved=bool(payload.get("naming_collision_resolved", False)),
        core_skill_overwrite_absent=bool(payload.get("core_skill_overwrite_absent", False)),
        rollback_reference_prepared=bool(payload.get("rollback_reference_prepared", False)),
        direct_move_not_used=bool(payload.get("direct_move_not_used", False)),
        target_name=str(payload.get("target_name") or ""),
        target_path=str(payload.get("target_path") or ""),
        notes=list(payload.get("notes") or []),
        allow_replace=bool(payload.get("allow_replace", False)),
        reference=reference or DEFAULT_REFERENCE,
    )


def save_reviewer_dashboard_rollback(
    skill_id: str,
    payload: dict,
    *,
    reference: str | None = None,
) -> dict:
    return save_generated_skill_rollback_record(
        skill_id,
        operator=str(payload.get("operator") or ""),
        reason=str(payload.get("reason") or ""),
        production_artifact_ref=str(payload.get("production_artifact_ref") or ""),
        candidate_artifact_ref=str(payload.get("candidate_artifact_ref") or ""),
        rollback_reference=payload.get("rollback_reference") or None,
        notes=list(payload.get("notes") or []),
        allow_replace=bool(payload.get("allow_replace", False)),
        reference=reference or DEFAULT_REFERENCE,
    )


def execute_reviewer_dashboard_manual_promotion(
    skill_id: str,
    payload: dict,
    *,
    reference: str | None = None,
) -> dict:
    operator = str(payload.get("operator") or "").strip()
    confirm_phrase = str(payload.get("confirm_phrase") or "")
    expected_phrase = f"PROMOTE {skill_id}"
    if confirm_phrase != expected_phrase:
        raise ValueError(f"manual promotion confirmation must exactly match: {expected_phrase}")
    result = execute_generated_skill_manual_promotion(
        skill_id,
        operator=operator,
        confirm_promotion=True,
        notes=list(payload.get("notes") or []),
        allow_replace=bool(payload.get("allow_replace", False)),
        reference=reference or DEFAULT_REFERENCE,
    )
    return result


def build_reviewer_dashboard_html() -> str:
    return """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Generated Skill 검토 대시보드 v0</title>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: #fbf8f2;
      --line: #d7cdb8;
      --text: #1f2430;
      --muted: #5a6472;
      --accent: #a04f2d;
      --accent-2: #234b63;
      --warn: #8a5a00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, #fff4db 0, transparent 32%),
        linear-gradient(135deg, #f4efe4, #ebe1cd);
    }
    .shell {
      display: grid;
      grid-template-columns: 360px 1fr;
      min-height: 100vh;
    }
    .sidebar {
      border-right: 1px solid var(--line);
      background: rgba(251, 248, 242, 0.92);
      padding: 24px;
      overflow: auto;
    }
    .main {
      padding: 24px;
      overflow: auto;
    }
    h1, h2, h3 { margin: 0 0 10px; }
    h1 { font-size: 28px; }
    h2 {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }
    .queue-item, .section, form {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 14px;
      padding: 14px 16px;
      margin-bottom: 12px;
      box-shadow: 0 10px 30px rgba(70, 58, 33, 0.05);
      min-width: 0;
      overflow: hidden;
    }
    .queue-item { cursor: pointer; }
    .queue-item.active { border-color: var(--accent); box-shadow: 0 10px 32px rgba(160, 79, 45, 0.16); }
    .queue-item strong {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .queue-title {
      font-size: 18px;
      line-height: 1.35;
    }
    .queue-purpose {
      margin: 6px 0 8px;
      color: var(--text);
      font-size: 13px;
      line-height: 1.45;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .queue-tech {
      margin-top: 8px;
      border-top: 1px dashed rgba(215, 205, 184, 0.95);
      padding-top: 8px;
    }
    .queue-tech summary {
      cursor: pointer;
      color: var(--accent-2);
      font-size: 12px;
      user-select: none;
    }
    .queue-tech .meta {
      margin-top: 6px;
    }
    .meta, .empty, .status {
      color: var(--muted);
      font-size: 13px;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }
    .visualization-shell {
      display: grid;
      grid-template-columns: minmax(280px, 340px) 1fr minmax(240px, 320px);
      gap: 12px;
      margin-bottom: 16px;
      align-items: stretch;
    }
    .flow-panel {
      position: relative;
      min-height: 360px;
      padding: 18px;
    }
    .flow-layout {
      position: relative;
      min-height: 320px;
      border-radius: 16px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(245, 238, 223, 0.92)),
        linear-gradient(135deg, #efe4cf, #f8f2e7);
      border: 1px solid var(--line);
      overflow: hidden;
    }
    .office-zone {
      position: absolute;
      top: 18px;
      left: 50%;
      width: min(360px, calc(100% - 36px));
      transform: translateX(-50%);
      border: 1px solid #cab995;
      border-radius: 16px;
      background: rgba(255, 249, 236, 0.92);
      padding: 16px 18px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.5);
      text-align: center;
    }
    .office-zone h3, .station h3, .summary-card h3 { margin: 0 0 8px; font-size: 20px; }
    .office-zone p, .station p, .summary-card p { margin: 0; color: var(--muted); font-size: 13px; }
    .stations {
      position: absolute;
      left: 18px;
      right: 18px;
      bottom: 18px;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .station {
      min-height: 120px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(251, 248, 242, 0.96);
      padding: 14px;
    }
    .station.active, .office-zone.active {
      border-color: var(--accent);
      box-shadow: 0 12px 30px rgba(160, 79, 45, 0.16);
    }
    .station .badge, .office-zone .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(160, 79, 45, 0.08);
      color: var(--accent);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .flow-path {
      position: absolute;
      left: 16%;
      right: 16%;
      top: 112px;
      bottom: 116px;
      pointer-events: none;
    }
    .flow-path::before {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 34px;
      height: 2px;
      background: linear-gradient(90deg, rgba(160,79,45,0.12), rgba(160,79,45,0.55), rgba(35,75,99,0.35));
    }
    .agent-token {
      position: absolute;
      left: var(--agent-left, 50%);
      top: var(--agent-top, 46px);
      width: 58px;
      height: 58px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-size: 30px;
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid rgba(160, 79, 45, 0.25);
      box-shadow: 0 12px 28px rgba(44, 36, 17, 0.14);
      transform: translate(-50%, -50%);
      transition: left 700ms cubic-bezier(0.2, 0.8, 0.2, 1), top 700ms cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 250ms ease;
      z-index: 3;
    }
    .flow-controls {
      display: flex;
      gap: 8px;
      margin-top: 12px;
      flex-wrap: wrap;
    }
    .flow-controls button {
      padding: 8px 12px;
      font-size: 13px;
    }
    .summary-card .headline {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .summary-card .stage-emoji {
      font-size: 22px;
    }
    .skill-explainer {
      margin-top: 12px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(215, 205, 184, 0.95);
      background: rgba(255, 253, 248, 0.92);
    }
    .skill-explainer h4 {
      margin: 0 0 6px;
      font-size: 18px;
    }
    .skill-explainer p {
      margin: 0 0 8px;
      color: var(--text);
      line-height: 1.55;
    }
    .skill-explainer .meta {
      font-size: 12px;
    }
    .kv { margin: 0; }
    .kv div {
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 10px;
      padding: 4px 0;
      border-bottom: 1px dashed rgba(215, 205, 184, 0.8);
    }
    .kv div:last-child { border-bottom: 0; }
    .kv dt { color: var(--muted); }
    .kv dt, .kv dd {
      margin: 0;
      min-width: 0;
      word-break: break-word;
      overflow-wrap: anywhere;
      white-space: normal;
    }
    .list {
      margin: 0;
      padding-left: 18px;
      min-width: 0;
    }
    .list li {
      margin-bottom: 4px;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .forms {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      margin-top: 16px;
    }
    .workflow-banner {
      display: none;
      margin-top: 16px;
      margin-bottom: 12px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(135deg, rgba(255,248,236,0.98), rgba(250,243,231,0.98));
      box-shadow: 0 10px 30px rgba(70, 58, 33, 0.05);
    }
    .workflow-banner.active {
      display: block;
    }
    .workflow-banner h3 {
      margin: 0 0 6px;
      font-size: 24px;
    }
    .workflow-banner p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }
    .workflow-tags {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .workflow-tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(160, 79, 45, 0.08);
      color: var(--accent);
      font-size: 12px;
    }
    .stage-card {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 16px;
      padding: 16px 18px;
      box-shadow: 0 10px 30px rgba(70, 58, 33, 0.05);
    }
    .stage-card.active {
      border-color: var(--accent);
      box-shadow: 0 12px 32px rgba(160, 79, 45, 0.16);
    }
    .stage-card.muted {
      opacity: 0.78;
    }
    #stage-review-card { order: 1; }
    #stage-approval-card { order: 2; }
    #stage-checklist-card { order: 3; }
    #rollback-panel { order: 4; }
    .stage-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .stage-kicker {
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .stage-header h3 {
      margin: 0;
      font-size: 24px;
    }
    .stage-header p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .stage-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 86px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(35, 75, 99, 0.1);
      color: var(--accent-2);
      font-size: 12px;
      text-align: center;
      flex-shrink: 0;
    }
    .optional-panel {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(251, 248, 242, 0.96);
      box-shadow: 0 10px 30px rgba(70, 58, 33, 0.05);
      overflow: hidden;
    }
    .optional-panel > summary {
      list-style: none;
      cursor: pointer;
      padding: 16px 18px;
      font-size: 22px;
      font-weight: 700;
    }
    .optional-panel > summary::-webkit-details-marker {
      display: none;
    }
    .optional-panel-body {
      padding: 0 18px 18px;
    }
    .optional-panel .meta {
      margin-bottom: 14px;
    }
    .checklist-group {
      margin-bottom: 12px;
      padding: 12px 12px 4px;
      border: 1px dashed rgba(215, 205, 184, 0.95);
      border-radius: 12px;
      background: rgba(255, 253, 248, 0.78);
    }
    .checklist-group h4 {
      margin: 0 0 8px;
      font-size: 14px;
      color: var(--text);
    }
    .checklist-group p {
      margin: 0 0 10px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .label-with-help {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 4px;
    }
    .label-with-help span {
      color: var(--muted);
      font-size: 12px;
    }
    .inline-help {
      position: relative;
      display: inline-block;
    }
    .inline-help summary {
      list-style: none;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      cursor: pointer;
      border: 1px solid var(--line);
      background: white;
      color: var(--accent-2);
      font-size: 12px;
      font-weight: 700;
      user-select: none;
    }
    .inline-help summary::-webkit-details-marker {
      display: none;
    }
    .inline-help[open] summary {
      border-color: var(--accent);
      color: var(--accent);
    }
    .help-popover {
      position: absolute;
      top: 28px;
      left: 0;
      width: min(320px, 72vw);
      z-index: 6;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 252, 245, 0.98);
      box-shadow: 0 14px 30px rgba(44, 36, 17, 0.14);
      color: var(--text);
    }
    .help-popover strong {
      display: block;
      margin-bottom: 8px;
      font-size: 13px;
    }
    .help-popover ul {
      margin: 0;
      padding-left: 18px;
    }
    .help-popover li {
      margin-bottom: 6px;
      line-height: 1.45;
      color: var(--muted);
    }
    input, select, textarea {
      width: 100%;
      margin-top: 4px;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: white;
      color: var(--text);
      font: inherit;
    }
    textarea { min-height: 92px; resize: vertical; }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      min-width: 0;
    }
    .row > * {
      min-width: 0;
    }
    .checkbox {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text);
      margin: 0 0 12px;
    }
    .checkbox input { width: auto; margin: 0; }
    button {
      padding: 10px 14px;
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      font: inherit;
    }
    .secondary { background: var(--accent-2); }
    .message {
      margin: 0 0 12px;
      padding: 10px 12px;
      border-radius: 10px;
      background: #fff2d7;
      color: var(--warn);
      display: none;
    }
    .inline-message {
      margin-top: 12px;
      margin-bottom: 0;
    }
    .prereq-note {
      display: none;
      margin: 0 0 12px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #fff6df;
      color: var(--warn);
      border: 1px solid #efd7a3;
      font-size: 13px;
      line-height: 1.5;
    }
    .prereq-note.active {
      display: block;
    }
    .prereq-note.ready {
      display: block;
      background: #ebf8ef;
      color: #1f6b3b;
      border: 1px solid #b9e1c5;
    }
    .existing-note {
      display: none;
      margin: 0 0 12px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #eef6ff;
      color: var(--accent-2);
      border: 1px solid #c8ddef;
      font-size: 13px;
      line-height: 1.5;
    }
    .existing-note.active {
      display: block;
    }
    button[disabled] {
      opacity: 0.45;
      cursor: not-allowed;
    }
    .manual-promotion-section {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 14px;
      padding: 16px;
      margin-top: 12px;
      box-shadow: 0 10px 30px rgba(70, 58, 33, 0.05);
    }
    .manual-promotion-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(31, 36, 48, 0.52);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 30;
      padding: 20px;
    }
    .modal-backdrop.active {
      display: flex;
    }
    .modal-card {
      width: min(720px, 100%);
      max-height: 90vh;
      overflow: auto;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
      box-shadow: 0 24px 60px rgba(31, 36, 48, 0.3);
    }
    .modal-card h3 {
      margin-bottom: 8px;
    }
    .modal-actions {
      display: flex;
      gap: 10px;
      justify-content: flex-end;
      margin-top: 14px;
      flex-wrap: wrap;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
      font-family: Consolas, monospace;
      font-size: 12px;
    }
    @media (max-width: 900px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
      .visualization-shell { grid-template-columns: 1fr; }
      .stations { grid-template-columns: 1fr; position: static; margin: 130px 18px 18px; }
      .office-zone {
        position: static;
        transform: none;
        width: auto;
        margin: 18px 18px 0;
      }
      .flow-layout {
        padding-bottom: 18px;
      }
      .flow-path {
        display: none;
      }
      .agent-token {
        top: var(--agent-top, 76px);
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h2>대기열</h2>
      <h1>검토 대시보드 v0</h1>
      <p class="meta">생성된 skill 후보의 검토 자료를 로컬에서 확인하고 기록하는 대시보드입니다.</p>
      <div id="queue-message" class="message"></div>
      <div id="queue-list"></div>
    </aside>
    <main class="main">
      <div id="page-message" class="message"></div>
      <div id="visualization-root" class="visualization-shell" style="display:none;"></div>
      <div id="detail-root" class="empty">왼쪽 대기열에서 generated skill을 선택하세요.</div>
      <div id="workflow-root" class="workflow-banner"></div>
      <div class="forms" id="forms-root" style="display:none;">
        <section class="stage-card" id="stage-review-card" data-stage-card="review">
          <div class="stage-header">
            <div>
              <div class="stage-kicker">1단계</div>
              <h3>검토 판단</h3>
              <p>이 후보를 계속 검토할지, 멈출지, 추가 확인이 필요한지 먼저 남깁니다.</p>
            </div>
            <div class="stage-badge" id="stage-review-badge">먼저 확인</div>
          </div>
          <form id="review-form">
            <div id="review-existing-note" class="existing-note"></div>
            <label>
              <div class="label-with-help">
                <span>판단</span>
                <details class="inline-help">
                  <summary>?</summary>
                  <div class="help-popover">
                    <strong>검토 판단이란?</strong>
                    <ul>
                      <li><b>검토 계속 진행</b>: 이 후보를 계속 검토 대상으로 둡니다.</li>
                      <li><b>거절</b>: 이 후보를 더 이상 진행하지 않습니다.</li>
                      <li><b>추가 확인 필요</b>: 바로 거절하지는 않지만, 정보가 더 필요합니다.</li>
                    </ul>
                  </div>
                </details>
              </div>
              <select name="decision">
                <option value="approve_for_consideration">검토 계속 진행</option>
                <option value="rejected">거절</option>
                <option value="needs_followup">추가 확인 필요</option>
              </select>
            </label>
              <div class="row">
              <label>검토자
                <input name="reviewer" required />
              </label>
              <label>기존 기록 덮어쓰기
                <select name="allow_replace">
                  <option value="false">아니오</option>
                  <option value="true">예</option>
                </select>
              </label>
            </div>
            <label>사유
              <textarea name="rationale" required></textarea>
            </label>
            <div class="label-with-help" style="margin-bottom:8px;">
              <label class="checkbox" style="margin:0;"><input type="checkbox" name="followup_required" />후속 조치 필요</label>
              <details class="inline-help">
                <summary>?</summary>
                <div class="help-popover">
                  <strong>후속 조치 필요란?</strong>
                  <ul>
                    <li>이 후보를 바로 다음 단계로 넘기지 않고, 추가 확인이 남아 있다고 기록합니다.</li>
                    <li>자동 실행, 자동 승격, sandbox 재실행은 일어나지 않습니다.</li>
                    <li>즉시 거절은 아니지만, 아직 검토가 끝나지 않았다는 뜻입니다.</li>
                  </ul>
                </div>
              </details>
            </div>
            <label>메모 (줄바꿈 구분)
              <textarea name="notes"></textarea>
            </label>
            <button type="submit">검토 판단 저장</button>
            <div id="review-form-message" class="message inline-message"></div>
          </form>
        </section>

        <section class="stage-card" id="stage-checklist-card" data-stage-card="checklist">
          <div class="stage-header">
            <div>
              <div class="stage-kicker">3단계</div>
              <h3>승격 전 점검표</h3>
              <p>현재 구현에서는 최종 검토 기록이 먼저 있어야 저장할 수 있습니다. 그 뒤에 수동 승격 전 운영 점검 항목을 확인합니다.</p>
            </div>
            <div class="stage-badge" id="stage-checklist-badge">마지막 점검</div>
          </div>
          <form id="checklist-form">
            <div id="checklist-prereq-note" class="prereq-note"></div>
            <div id="checklist-existing-note" class="existing-note"></div>
            <div class="row">
              <label>작업자
                <input name="operator" required />
              </label>
              <label>기존 기록 덮어쓰기
                <select name="allow_replace">
                  <option value="false">아니오</option>
                  <option value="true">예</option>
                </select>
              </label>
            </div>
            <div class="checklist-group">
              <h4>기본 확인</h4>
              <p>이 후보가 검토 가능한 상태인지 확인합니다.</p>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="review_decision_exists" />검토 판단을 이미 남겼다</label>
                <label class="checkbox"><input type="checkbox" name="approval_record_exists" />최종 검토 기록을 이미 남겼다</label>
              </div>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="validation_passed" />자동 검증을 통과했다</label>
                <label class="checkbox"><input type="checkbox" name="sandbox_passed" />샌드박스 실행을 통과했다</label>
              </div>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="sandbox_only_confirmed" />샌드박스 전용 원칙을 다시 확인했다</label>
                <label class="checkbox"><input type="checkbox" name="promotion_required_confirmed" />사람 승인 전에는 운영 반영하지 않음을 확인했다</label>
              </div>
            </div>
            <div class="checklist-group">
              <h4>운영 후보 정리</h4>
              <p>이름과 초안 정리 상태를 확인합니다.</p>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="generated_only_fields_removed" />초안 전용 항목을 정리했다</label>
                <label class="checkbox"><input type="checkbox" name="target_name_manually_chosen" />운영 후보 이름을 직접 정했다</label>
              </div>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="naming_collision_resolved" />이름 겹침 문제를 확인했다</label>
                <label class="checkbox"><input type="checkbox" name="direct_move_not_used" />초안 파일을 그대로 옮기지 않는다</label>
              </div>
            </div>
            <div class="checklist-group">
              <h4>안전성 확인</h4>
              <p>운영 위험과 되돌리기 준비 여부를 확인합니다.</p>
              <div class="row">
                <label class="checkbox"><input type="checkbox" name="core_skill_overwrite_absent" />기존 핵심 skill을 덮어쓰지 않는다</label>
                <label class="checkbox"><input type="checkbox" name="rollback_reference_prepared" />문제 시 되돌릴 기준을 적어뒀다</label>
              </div>
            </div>
            <div class="row">
              <label>운영 후보 이름
                <input name="target_name" />
              </label>
              <label>운영 후보 경로
                <input name="target_path" />
              </label>
            </div>
            <label>메모 (줄바꿈 구분)
              <textarea name="notes"></textarea>
            </label>
            <button type="submit">점검표 저장</button>
            <div id="checklist-form-message" class="message inline-message"></div>
          </form>
        </section>

        <section class="stage-card" id="stage-approval-card" data-stage-card="approval">
          <div class="stage-header">
            <div>
              <div class="stage-kicker">2단계</div>
              <h3>최종 검토 기록</h3>
              <p>현재 구현 기준으로는 점검표보다 이 기록이 먼저 필요합니다. 승인으로 저장하려면 최종 후보 이름과 경로도 같이 입력해야 합니다.</p>
            </div>
            <div class="stage-badge" id="stage-approval-badge">다음 단계</div>
          </div>
          <form id="approval-form">
            <div id="approval-prereq-note" class="prereq-note"></div>
            <div id="approval-existing-note" class="existing-note"></div>
            <div class="row">
              <label>
                <div class="label-with-help">
                  <span>기록 유형</span>
                  <details class="inline-help">
                    <summary>?</summary>
                    <div class="help-popover">
                      <strong>기록 유형이란?</strong>
                      <ul>
                        <li><b>변환 검토 승인</b>: generated skill을 운영 후보 형태로 정리한 결과를 검토하는 기록입니다.</li>
                        <li><b>승격 검토 승인</b>: 나중에 실제 승격 대상으로 볼지 판단하는 기록 슬롯입니다.</li>
                      </ul>
                    </div>
                  </details>
                </div>
                <select name="approval_type">
                  <option value="transform_approval">변환 검토 승인</option>
                  <option value="promotion_approval">승격 검토 승인</option>
                </select>
              </label>
              <label>
                <div class="label-with-help">
                  <span>판단</span>
                  <details class="inline-help">
                    <summary>?</summary>
                    <div class="help-popover">
                      <strong>최종 검토 판단이란?</strong>
                      <ul>
                        <li><b>승인</b>: 현재 기준으로 다음 수동 절차로 넘길 수 있다고 기록합니다.</li>
                        <li><b>거절</b>: 이 상태로는 진행하지 않겠다고 기록합니다.</li>
                        <li><b>추가 확인 필요</b>: 아직 보완이나 확인이 더 필요합니다.</li>
                      </ul>
                    </div>
                  </details>
                </div>
                <select name="decision">
                  <option value="approved">승인</option>
                  <option value="rejected">거절</option>
                  <option value="needs_followup">추가 확인 필요</option>
                </select>
              </label>
            </div>
            <div class="row">
              <label>승인자
                <input name="approver" required />
              </label>
              <label>기존 기록 덮어쓰기
                <select name="allow_replace">
                  <option value="false">아니오</option>
                  <option value="true">예</option>
                </select>
              </label>
            </div>
            <label>사유
              <textarea name="rationale" required></textarea>
            </label>
            <div class="label-with-help" style="margin-bottom:8px;">
              <label class="checkbox" style="margin:0;"><input type="checkbox" name="followup_required" />후속 조치 필요</label>
              <details class="inline-help">
                <summary>?</summary>
                <div class="help-popover">
                  <strong>후속 조치 필요란?</strong>
                  <ul>
                    <li>최종 검토를 아직 닫지 않고, 보완이나 추가 확인이 필요하다고 기록합니다.</li>
                    <li>체크해도 운영 반영이나 승격은 자동으로 진행되지 않습니다.</li>
                    <li>다음 사람이 다시 확인해야 한다는 운영 표시로 보면 됩니다.</li>
                  </ul>
                </div>
              </details>
            </div>
            <div class="meta">`승인`으로 저장할 때는 아래의 `최종 후보 이름`과 `최종 후보 경로`도 꼭 입력해야 합니다.</div>
            <label>메모 (줄바꿈 구분)
              <textarea name="notes"></textarea>
            </label>
            <div class="row">
              <label>참고 검토 판단
                <input name="source_review_decision" readonly />
              </label>
              <label>참고 패킷 ID
                <input name="source_packet_id" readonly />
              </label>
            </div>
            <label>참고 변환 템플릿
              <input name="source_transform_template" readonly />
            </label>
            <div class="row">
              <label>
                <div class="label-with-help">
                  <span>최종 후보 이름</span>
                  <details class="inline-help">
                    <summary>?</summary>
                    <div class="help-popover">
                      <strong>최종 후보 이름이란?</strong>
                      <ul>
                        <li>이 generated skill을 나중에 운영 후보로 정리한다면 어떤 이름으로 부를지 적는 칸입니다.</li>
                        <li>실제 파일을 만드는 값이 아니라, 검토 기록에 남기는 후보 이름입니다.</li>
                        <li>예: <code>review_note_compactor_v1</code></li>
                      </ul>
                    </div>
                  </details>
                </div>
                <input name="final_target_name" />
              </label>
              <label>
                <div class="label-with-help">
                  <span>최종 후보 경로</span>
                  <details class="inline-help">
                    <summary>?</summary>
                    <div class="help-popover">
                      <strong>최종 후보 경로란?</strong>
                      <ul>
                        <li>이 후보를 운영 후보 artifact로 본다면 어떤 경로를 쓸지 기록하는 칸입니다.</li>
                        <li>실제 등록이나 파일 생성은 하지 않고, 예정 경로만 남깁니다.</li>
                        <li>예: <code>skills/review_note_compactor_v1.json</code></li>
                      </ul>
                    </div>
                  </details>
                </div>
                <input name="final_target_path" />
              </label>
            </div>
            <label>롤백 참조
              <input name="rollback_reference" />
            </label>
            <button type="submit" class="secondary">최종 검토 기록 저장</button>
            <div id="approval-form-message" class="message inline-message"></div>
          </form>
        </section>

        <section class="manual-promotion-section">
          <div class="stage-header">
            <div>
              <div class="stage-kicker">4단계</div>
              <h3>수동 승격 실행</h3>
              <p>모든 선행 조건이 충족된 경우에만, 사람이 명시적으로 확인한 뒤 production candidate artifact를 생성합니다.</p>
            </div>
          </div>
          <div id="manual-promotion-banner" class="prereq-note"></div>
          <div id="manual-promotion-existing-note" class="existing-note"></div>
          <div id="manual-promotion-summary" class="detail-grid"></div>
          <div class="manual-promotion-actions">
            <button type="button" id="manual-promotion-button" class="secondary" disabled title="선행 조건이 아직 충족되지 않았습니다.">수동 승격 실행</button>
            <div id="manual-promotion-message" class="message inline-message"></div>
          </div>
        </section>

        <details class="optional-panel" id="rollback-panel">
          <summary>예외 처리: 철회 기록</summary>
          <div class="optional-panel-body">
            <div class="meta">후보를 철회하거나 되돌려야 할 때만 작성합니다. 평소에는 비워 둬도 됩니다.</div>
            <form id="rollback-form">
              <div id="rollback-existing-note" class="existing-note"></div>
              <div class="row">
                <label>작업자
                  <input name="operator" required />
                </label>
              <label>기존 기록 덮어쓰기
                <select name="allow_replace">
                  <option value="false">아니오</option>
                  <option value="true">예</option>
                </select>
              </label>
              </div>
              <label>사유
                <textarea name="reason" required></textarea>
              </label>
              <div class="row">
                <label>운영 반영물 참조
                  <input name="production_artifact_ref" />
                </label>
                <label>후보 반영물 참조
                  <input name="candidate_artifact_ref" />
                </label>
              </div>
              <label>롤백 참조
                <input name="rollback_reference" />
              </label>
              <label>메모 (줄바꿈 구분)
                <textarea name="notes"></textarea>
              </label>
              <button type="submit" class="secondary">철회 기록 저장</button>
              <div id="rollback-form-message" class="message inline-message"></div>
            </form>
          </div>
        </details>
      </div>
      <div id="promotion-modal" class="modal-backdrop" aria-hidden="true">
        <div class="modal-card">
          <h3>수동 승격 확인</h3>
          <p class="meta">자동 승격이 아닙니다. 아래 정보를 다시 확인한 뒤, 정확한 확인 문구를 입력해야만 실행됩니다.</p>
          <div id="promotion-modal-summary" class="detail-grid"></div>
          <label style="margin-top: 12px; display:block;">승격 실행자
            <input id="promotion-modal-operator" />
          </label>
          <label style="margin-top: 12px; display:block;">확인 문구 입력
            <input id="promotion-modal-confirm" />
          </label>
          <div class="meta" id="promotion-modal-confirm-label" style="margin-top:8px;">예: PROMOTE &lt;skill_id&gt;</div>
          <label style="margin-top: 12px; display:block;">메모 (줄바꿈 구분)
            <textarea id="promotion-modal-notes"></textarea>
          </label>
          <div id="promotion-modal-message" class="message inline-message"></div>
          <div class="modal-actions">
            <button type="button" id="promotion-modal-cancel">취소</button>
            <button type="button" id="promotion-modal-execute" class="secondary" disabled>수동 승격 실행</button>
          </div>
        </div>
      </div>
    </main>
  </div>
  <script>
    let selectedSkillId = null;
    let currentDetail = null;

    function setMessage(id, text) {
      const el = document.getElementById(id);
      if (!text) {
        el.style.display = "none";
        el.textContent = "";
        return;
      }
      el.textContent = text;
      el.style.display = "block";
    }

    function setInlineFormMessage(formName, text) {
      setMessage(`${formName}-form-message`, text);
    }

    function setPrereqNote(id, text) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!text) {
        el.classList.remove("active");
        el.textContent = "";
        return;
      }
      el.textContent = text;
      el.classList.add("active");
    }

    function setExistingNote(id, text) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!text) {
        el.classList.remove("active");
        el.textContent = "";
        return;
      }
      el.textContent = text;
      el.classList.add("active");
    }

    function formatValue(value) {
      const labelMap = {
        none: "없음",
        approve_for_consideration: "검토 계속 진행",
        rejected: "거절",
        needs_followup: "추가 확인 필요",
        approved: "승인",
        pending_manual_review: "사람 검토 대기",
        passed: "통과",
        failed: "실패",
        operational: "운영 모드",
        experimental_sandbox: "실험 샌드박스",
        queued_for_manual_promotion: "수동 승격 대기",
      };
      if (value === null || value === undefined || value === "") return "없음";
      if (typeof value === "boolean") return value ? "예" : "아니오";
      if (Array.isArray(value)) return value.length ? value.map((item) => formatValue(item)).join(", ") : "없음";
      if (typeof value === "string") {
        return labelMap[value] || value;
      }
      if (typeof value === "object") return JSON.stringify(value, null, 2);
      return String(value);
    }

    function fieldLabel(label) {
      const labels = {
        skill_id: "skill ID",
        purpose: "목적",
        status: "상태",
        promotion_status: "승격 상태",
        skill_kind: "skill 종류",
        capabilities: "기능 성격",
        generated_by: "생성 주체",
        validation_summary: "검증 요약",
        validation_errors: "검증 오류",
        validation_warnings: "검증 경고",
        sandbox_result_summary: "sandbox 결과 요약",
        sandbox_result: "sandbox 결과",
        run_id: "실행 ID",
        execution_mode: "실행 모드",
        decision: "결정",
        reviewer: "검토자",
        reviewed_at: "검토 시각",
        rationale: "사유",
        followup_required: "후속 조치 필요",
        notes: "메모",
        criteria_check_passed: "기준 충족 여부",
        overwrite_risk: "덮어쓰기 위험",
        blockers: "진행 차단 요소",
        warnings: "주의 사항",
        auto_applicable: "자동 추천 가능 여부",
        auto_review_decision: "자동 검토 판단 제안",
        auto_checklist_suggestions: "자동 점검표 힌트",
        reason: "사유",
        confidence: "신뢰도",
        risk_level: "위험도",
        allowed_skips: "생략 가능 단계",
        required_stages: "필수 단계",
        recommended_path: "추천 경로",
        can_execute: "실행 가능 여부",
        approval_exists: "최종 검토 기록 존재",
        review_exists: "검토 판단 존재",
        checklist_exists: "점검표 존재",
        transform_exists: "수동 변환 양식 존재",
        checklist_all_checks_passed: "점검표 전체 통과",
        naming_collision_resolved: "이름 겹침 해결 여부",
        direct_move_not_used: "직접 이동 금지 확인",
        rollback_reference_prepared: "철회 기준 준비 여부",
        rollback_reference: "철회 참조",
        checklist_missing_items: "미완료 점검 항목",
        promoted_at: "승격 실행 시각",
        final_target_name: "최종 후보 이름",
        final_target_path: "최종 후보 경로",
        source_candidate_artifact: "후보 artifact 참조",
        candidate_artifact_path: "후보 artifact 경로",
        promotion_record_path: "승격 기록 경로",
        target_name: "대상 이름",
        target_path: "대상 경로",
        required_manual_edits: "필수 수동 보완",
        removed_fields: "제거 필드",
        risk_checks: "위험 점검",
        operator: "작업자",
        checked_at: "체크 시각",
        all_checks_passed: "전체 통과",
        record_types: "기록 유형",
        rolled_back_at: "철회 시각",
        reason: "사유",
        production_artifact_ref: "운영 반영물 참조",
        candidate_artifact_ref: "후보 반영물 참조",
        rollback_reference: "철회 참조",
      };
      return labels[label] || label;
    }

    function explainSkill(entity) {
      const skillView = entity.skill || entity;
      const kind = skillView.skill_kind;
      const purpose = skillView.purpose || "없음";
      const capabilityText = formatValue(skillView.capabilities || []);
      const map = {
        runtime_state_summarizer: {
          title: "런타임 상태 요약 skill",
          body: "runtime 상태와 marker 흐름을 짧게 요약해서 사람이 검토하기 쉽게 만드는 skill입니다.",
          input: "runtime state",
          output: "요약 문자열",
        },
        proposal_summary_formatter: {
          title: "제안서 요약 정리 skill",
          body: "proposal 내용을 사람이 읽기 좋은 짧은 요약으로 정리하는 skill입니다.",
          input: "proposal",
          output: "proposal 요약",
        },
        review_note_compactor: {
          title: "리뷰 메모 정리 skill",
          body: "반복되거나 긴 review note를 더 짧고 읽기 쉽게 압축하는 skill입니다.",
          input: "review notes",
          output: "정리된 review note",
        },
        diff_hint_reformatter: {
          title: "변경 힌트 정리 skill",
          body: "diff hint나 변경 힌트를 사람이 검토하기 좋은 형태로 다시 정리하는 skill입니다.",
          input: "diff hints",
          output: "정리된 변경 힌트",
        },
      };
      const explanation = map[kind] || {
        title: "생성된 skill",
        body: "생성된 skill의 목적과 기능을 기준으로 사람이 검토하기 위한 후보입니다.",
        input: "정의된 입력",
        output: "정의된 출력",
      };
      return {
        ...explanation,
        purpose,
        capabilityText,
        kind,
      };
    }

    function section(title, pairs, extras) {
      const rows = pairs.map(([label, value]) => `
        <div><dt>${fieldLabel(label)}</dt><dd>${typeof value === "string" ? value : formatValue(value)}</dd></div>
      `).join("");
      return `
        <section class="section">
          <h2>${title}</h2>
          <dl class="kv">${rows}</dl>
          ${extras || ""}
        </section>
      `;
    }

    function listBlock(title, items) {
      const content = items && items.length
        ? `<ul class="list">${items.map((item) => `<li>${formatValue(item)}</li>`).join("")}</ul>`
        : `<div class="meta">none</div>`;
      return `<div><strong>${title}</strong>${content}</div>`;
    }

    function stageEmoji(stage) {
      const emojis = {
        office: "🤖",
        brain: "🧠",
        sandbox: "🧪",
        review: "🧐",
        waiting_review: "⏳",
        success: "✅",
        failed: "❌",
      };
      return emojis[stage] || "🤖";
    }

    function stagePosition(stage, compact) {
      if (compact) {
        const compactMap = {
          office: { left: "50%", top: "76px" },
          brain: { left: "50%", top: "150px" },
          sandbox: { left: "50%", top: "242px" },
          review: { left: "50%", top: "334px" },
          waiting_review: { left: "50%", top: "334px" },
          success: { left: "50%", top: "334px" },
          failed: { left: "50%", top: "242px" },
        };
        return compactMap[stage] || compactMap.office;
      }
      const fullMap = {
        office: { left: "50%", top: "96px" },
        brain: { left: "16.5%", top: "238px" },
        sandbox: { left: "50%", top: "238px" },
        review: { left: "83.5%", top: "238px" },
        waiting_review: { left: "83.5%", top: "238px" },
        success: { left: "83.5%", top: "238px" },
        failed: { left: "50%", top: "238px" },
      };
      return fullMap[stage] || fullMap.office;
    }

    function renderVisualization(detail) {
      const root = document.getElementById("visualization-root");
      if (detail.not_found) {
        root.style.display = "none";
        root.innerHTML = "";
        return;
      }

      const flow = detail.flow || {};
      const skillExplanation = explainSkill(detail);
      const compact = window.innerWidth <= 900;
      const pos = stagePosition(flow.current_stage, compact);
      const isOffice = flow.current_station === "office";
      const isBrain = flow.current_station === "brain";
      const isSandbox = flow.current_station === "sandbox";
      const isReview = flow.current_station === "review";

      root.style.display = "grid";
      root.innerHTML = `
        <section class="section summary-card">
          <div class="headline">
            <span class="stage-emoji">${stageEmoji(flow.current_stage)}</span>
            <div>
              <h3>현재 흐름 요약</h3>
              <p>${flow.stage_title || "대기 중"}</p>
            </div>
          </div>
          <dl class="kv">
            <div><dt>현재 작업</dt><dd>${formatValue(flow.task_description)}</dd></div>
            <div><dt>실행 ID</dt><dd>${formatValue(flow.run_id)}</dd></div>
            <div><dt>선택된 skill</dt><dd>${formatValue(flow.selected_skill)}</dd></div>
            <div><dt>선택 신뢰도</dt><dd>${formatValue(flow.confidence)}</dd></div>
            <div><dt>제안 위험도</dt><dd>${formatValue(flow.proposal_risk_level)}</dd></div>
            <div><dt>추천 경로</dt><dd>${formatValue(flow.proposal_recommended_path)}</dd></div>
          </dl>
          <div class="skill-explainer">
            <h4>${skillExplanation.title}</h4>
            <p>${skillExplanation.body}</p>
            <div class="meta">이 skill이 하려는 일: ${formatValue(skillExplanation.purpose)}</div>
            <div class="meta">주요 입력: ${formatValue(skillExplanation.input)} | 결과 형태: ${formatValue(skillExplanation.output)}</div>
            <div class="meta">기능 성격: ${formatValue(skillExplanation.capabilityText)}</div>
          </div>
        </section>
        <section class="section flow-panel">
          <div class="flow-layout">
            <div class="office-zone ${isOffice ? "active" : ""}">
              <div class="badge">출발점</div>
              <h3>에이전트 오피스</h3>
              <p>에이전트가 대기하거나 작업을 시작하는 사무실 영역입니다.</p>
            </div>
            <div class="flow-path"></div>
            <div class="agent-token" id="agent-token" style="--agent-left:${pos.left}; --agent-top:${pos.top};">${stageEmoji(flow.current_stage)}</div>
            <div class="stations">
              <article class="station ${isBrain ? "active" : ""}">
                <div class="badge">선택</div>
                <h3>에이전트 브레인</h3>
                <p>현재 작업과 기록을 보고 어떤 skill이 맞는지 고르는 단계입니다.</p>
              </article>
              <article class="station ${isSandbox ? "active" : ""}">
                <div class="badge">검증</div>
                <h3>샌드박스</h3>
                <p>선택된 skill을 experimental sandbox에서 1회 실행해 확인합니다.</p>
              </article>
              <article class="station ${isReview ? "active" : ""}">
                <div class="badge">사람 검토</div>
                <h3>사람 검토</h3>
                <p>검토 판단, 점검표, 최종 검토 기록, 철회 기록이 모이는 단계입니다.</p>
              </article>
            </div>
          </div>
          <div class="flow-controls">
            <button type="button" id="flow-autoplay">자동 재생</button>
            <button type="button" class="secondary" id="flow-reset">초기화</button>
          </div>
        </section>
        <section class="section summary-card">
          <h3>현재 단계 설명</h3>
          <p>${formatValue(flow.stage_description)}</p>
          <dl class="kv" style="margin-top:12px;">
            <div><dt>sandbox 결과</dt><dd>${formatValue(flow.sandbox_result)}</dd></div>
            <div><dt>검토 상태</dt><dd>${formatValue(flow.review_status)}</dd></div>
            <div><dt>검토 판단</dt><dd>${formatValue(flow.review_decision)}</dd></div>
            <div><dt>점검표</dt><dd>${flow.checklist_present ? "있음" : "없음"}</dd></div>
            <div><dt>최종 검토 기록</dt><dd>${flow.approval_present ? "있음" : "없음"}</dd></div>
            <div><dt>철회 기록</dt><dd>${flow.rollback_present ? "있음" : "없음"}</dd></div>
          </dl>
        </section>
      `;

      const token = document.getElementById("agent-token");
      document.getElementById("flow-reset").addEventListener("click", () => {
        const resetPos = stagePosition("office", window.innerWidth <= 900);
        token.style.setProperty("--agent-left", resetPos.left);
        token.style.setProperty("--agent-top", resetPos.top);
        token.textContent = stageEmoji("office");
      });
      document.getElementById("flow-autoplay").addEventListener("click", async () => {
        const sequence = flow.sequence || ["office"];
        for (const stage of sequence) {
          const stepPos = stagePosition(stage, window.innerWidth <= 900);
          token.style.setProperty("--agent-left", stepPos.left);
          token.style.setProperty("--agent-top", stepPos.top);
          token.textContent = stageEmoji(stage);
          await new Promise((resolve) => window.setTimeout(resolve, 520));
        }
      });
    }

    function buildOperatorWorkflow(detail) {
      const review = detail.review_decision;
      const checklist = detail.candidate_checklist;
      const approval = detail.approval;
      const rollback = detail.rollback;
      const approvalRecords = approval.available ? (approval.records || {}) : {};
      const hasTransformApproval = Boolean(approvalRecords.transform_approval);
      const checklistPassed = Boolean(checklist.available && checklist.all_checks_passed);
      const reviewReady = review.available;

      let currentStep = "review";
      let title = "지금 할 일: 검토 판단부터 작성";
      let description = "이 후보를 계속 검토할지 먼저 결정하세요. 대부분의 경우 여기서 시작합니다.";

      if (rollback.available) {
        currentStep = "rollback";
        title = "예외 상황: 철회 기록 확인";
        description = "이 후보는 이미 철회 기록이 있습니다. 추가 조치가 필요한 경우에만 예외 섹션을 열어 확인하세요.";
      } else if (!reviewReady) {
        currentStep = "review";
        title = "지금 할 일: 검토 판단 작성";
        description = "검토 계속 진행 / 거절 / 추가 확인 필요 중 하나를 먼저 남기세요.";
      } else if (!hasTransformApproval) {
        currentStep = "approval";
        title = "마지막 할 일: 최종 검토 기록 남기기";
        description = "현재 구현에서는 점검표보다 최종 검토 기록이 먼저 필요합니다. 승인으로 저장하려면 최종 후보 이름과 경로도 함께 입력하세요.";
      } else if (!checklist.available || !checklistPassed) {
        currentStep = "checklist";
        title = "다음 할 일: 승격 전 점검표 채우기";
        description = "최종 검토 기록이 있으면 운영 점검 항목을 채우고 저장하세요.";
      } else {
        currentStep = "complete";
        title = "검토 입력이 모두 모였습니다";
        description = "검토 판단, 점검표, 최종 검토 기록이 존재합니다. 이제 별도 수동 절차만 남았습니다.";
      }

      return {
        currentStep,
        title,
        description,
        tags: [
          reviewReady ? "검토 판단 있음" : "검토 판단 필요",
          hasTransformApproval ? "최종 검토 기록 있음" : "최종 검토 기록 필요",
          checklistPassed ? "점검표 완료" : "점검표 진행 필요",
          rollback.available ? "철회 기록 있음" : "철회 기록 없음",
        ],
      };
    }

    function applyOperatorWorkflow(detail) {
      const workflow = buildOperatorWorkflow(detail);
      const root = document.getElementById("workflow-root");
      root.classList.add("active");
      root.innerHTML = `
        <h3>${workflow.title}</h3>
        <p>${workflow.description}</p>
        <div class="workflow-tags">
          ${workflow.tags.map((tag) => `<span class="workflow-tag">${tag}</span>`).join("")}
        </div>
      `;

      const steps = {
        review: document.getElementById("stage-review-card"),
        checklist: document.getElementById("stage-checklist-card"),
        approval: document.getElementById("stage-approval-card"),
      };
      Object.entries(steps).forEach(([key, node]) => {
        if (!node) return;
        node.classList.remove("active", "muted");
        if (workflow.currentStep === "complete") {
          return;
        }
        if (workflow.currentStep === key) {
          node.classList.add("active");
          return;
        }
        node.classList.add("muted");
      });

      const badges = {
        review: document.getElementById("stage-review-badge"),
        checklist: document.getElementById("stage-checklist-badge"),
        approval: document.getElementById("stage-approval-badge"),
      };
      if (badges.review) badges.review.textContent = workflow.currentStep === "review" ? "지금 할 일" : "선행 단계";
      if (badges.checklist) badges.checklist.textContent = workflow.currentStep === "checklist" ? "지금 할 일" : "다음 단계";
      if (badges.approval) badges.approval.textContent = workflow.currentStep === "approval" ? "지금 할 일" : "마지막 단계";
      if (workflow.currentStep === "complete") {
        if (badges.review) badges.review.textContent = "완료";
        if (badges.checklist) badges.checklist.textContent = "완료";
        if (badges.approval) badges.approval.textContent = "완료";
      }

      const rollbackPanel = document.getElementById("rollback-panel");
      if (rollbackPanel) {
        rollbackPanel.open = workflow.currentStep === "rollback";
      }
    }

    function renderDetail(detail) {
      currentDetail = detail;
      if (detail.not_found) {
        renderVisualization(detail);
        document.getElementById("workflow-root").classList.remove("active");
        document.getElementById("workflow-root").innerHTML = "";
        document.getElementById("detail-root").innerHTML = `<div class="empty">${detail.message}</div>`;
        document.getElementById("forms-root").style.display = "none";
        return;
      }

      const review = detail.review_decision;
      const packet = detail.promotion_packet;
      const transform = detail.transform_template;
      const checklist = detail.candidate_checklist;
      const approval = detail.approval;
      const rollback = detail.rollback;
      const manualPromotion = detail.manual_promotion;
      const autoSuggestion = detail.auto_suggestion;
      const riskSummary = detail.risk_summary;
      const skillExplanation = explainSkill(detail);
      const approvalExtras = approval.available && approval.records
        ? `<pre>${JSON.stringify(approval.records, null, 2)}</pre>`
        : `<div class="meta">${approval.message || "none"}</div>`;

      renderVisualization(detail);

      document.getElementById("detail-root").innerHTML = `
        <div class="detail-grid">
          ${section("이 skill이 하는 일", [
            ["purpose", skillExplanation.purpose],
            ["skill_kind", skillExplanation.title],
            ["capabilities", skillExplanation.capabilityText],
          ], `<p class="meta">${skillExplanation.body}</p>`)}
          ${section("기본 정보", [
            ["skill_id", detail.skill.skill_id],
            ["purpose", detail.skill.purpose],
            ["status", detail.skill.status],
            ["promotion_status", detail.skill.promotion_status],
            ["skill_kind", detail.skill.skill_kind],
            ["capabilities", detail.skill.capabilities],
            ["generated_by", detail.skill.generated_by],
          ])}
          ${section("자동 검증", [
            ["validation_summary", detail.validation.validation_summary],
          ], `
            ${listBlock("검증 오류", detail.validation.validation_errors)}
            ${listBlock("검증 경고", detail.validation.validation_warnings)}
          `)}
          ${section("위험도 / 추천 경로", [
            ["risk_level", riskSummary.risk_level],
            ["recommended_path", riskSummary.recommended_path],
            ["allowed_skips", riskSummary.allowed_skips],
            ["required_stages", riskSummary.required_stages],
            ["confidence", riskSummary.confidence],
            ["reason", riskSummary.reason],
          ])}
          ${section("Sandbox 실행", [
            ["sandbox_result_summary", detail.sandbox.sandbox_result_summary],
            ["sandbox_result", detail.sandbox.sandbox_result],
            ["run_id", detail.sandbox.run_id],
            ["execution_mode", detail.sandbox.execution_mode],
          ])}
          ${section("자동 추천", autoSuggestion.available ? [
            ["auto_applicable", autoSuggestion.summary.auto_applicable],
            ["confidence", autoSuggestion.summary.confidence],
            ["auto_review_decision", (autoSuggestion.summary.auto_review_decision || {}).decision || "none"],
            ["reason", (autoSuggestion.summary.auto_review_decision || {}).reason || autoSuggestion.summary.blocked_reason || "none"],
            ["auto_checklist_suggestions", Object.keys(autoSuggestion.summary.auto_checklist_suggestions || {})],
          ] : [
            ["status", autoSuggestion.summary.blocked_reason || "자동 추천 조건을 아직 충족하지 않았습니다."]
          ])}
          ${section("검토 판단", review.available ? [
            ["decision", review.decision],
            ["reviewer", review.reviewer],
            ["reviewed_at", review.reviewed_at],
            ["rationale", review.rationale],
            ["followup_required", review.followup_required],
            ["notes", review.notes],
          ] : [["status", review.message]])}
          ${section("승격 검토 묶음", packet.available ? [
            ["criteria_check_passed", packet.summary.criteria_check_passed],
            ["overwrite_risk", packet.summary.overwrite_risk],
            ["blockers", packet.summary.blockers],
            ["warnings", packet.summary.warnings],
          ] : [["status", packet.message]])}
          ${section("수동 변환 양식", transform.available ? [
            ["target_name", transform.summary.target_name || "<직접 입력>"],
            ["target_path", transform.summary.target_path],
            ["required_manual_edits", transform.summary.required_manual_edits],
            ["removed_fields", transform.summary.removed_fields],
            ["risk_checks", transform.summary.risk_checks],
          ] : [["status", transform.message]])}
          ${section("승격 전 점검표", checklist.available ? [
            ["operator", checklist.operator],
            ["checked_at", checklist.checked_at],
            ["all_checks_passed", checklist.all_checks_passed],
            ["target_name", checklist.target_name],
            ["target_path", checklist.target_path],
            ["notes", checklist.notes],
          ] : [["status", checklist.message]])}
          ${section("최종 검토 기록", approval.available ? [
            ["record_types", Object.keys(approval.records || {})],
          ] : [["status", approval.message]], approval.available ? approvalExtras : "")}
          ${section("수동 승격 상태", [
            ["can_execute", manualPromotion.readiness.can_execute],
            ["review_exists", manualPromotion.readiness.review_exists],
            ["approval_exists", manualPromotion.readiness.approval_exists],
            ["checklist_exists", manualPromotion.readiness.checklist_exists],
            ["checklist_all_checks_passed", manualPromotion.readiness.checklist_all_checks_passed],
            ["transform_exists", manualPromotion.readiness.transform_exists],
            ["naming_collision_resolved", manualPromotion.readiness.naming_collision_resolved],
            ["direct_move_not_used", manualPromotion.readiness.direct_move_not_used],
            ["rollback_reference_prepared", manualPromotion.readiness.rollback_reference_prepared],
            ["overwrite_risk", manualPromotion.readiness.overwrite_risk],
          ], `
            ${listBlock("실행 차단 요소", manualPromotion.readiness.blockers)}
            ${listBlock("주의 사항", manualPromotion.readiness.warnings)}
          `)}
          ${section("승격 실행 기록", manualPromotion.promotion_record.available ? [
            ["promoted_at", manualPromotion.promotion_record.promoted_at],
            ["operator", manualPromotion.promotion_record.operator],
            ["final_target_name", manualPromotion.promotion_record.final_target_name],
            ["final_target_path", manualPromotion.promotion_record.final_target_path],
            ["source_candidate_artifact", manualPromotion.promotion_record.source_candidate_artifact],
            ["candidate_artifact_path", manualPromotion.candidate._path || "none"],
            ["promotion_record_path", manualPromotion.promotion_record._path || "none"],
          ] : [["status", manualPromotion.promotion_record.message]])}
          ${section("철회 기록", rollback.available ? [
            ["operator", rollback.operator],
            ["rolled_back_at", rollback.rolled_back_at],
            ["reason", rollback.reason],
            ["production_artifact_ref", rollback.production_artifact_ref],
            ["candidate_artifact_ref", rollback.candidate_artifact_ref],
            ["rollback_reference", rollback.rollback_reference],
            ["notes", rollback.notes],
          ] : [["status", rollback.message]])}
        </div>
      `;
      document.getElementById("forms-root").style.display = "grid";
      hydrateForms(detail);
      applyOperatorWorkflow(detail);
      hydrateManualPromotion(detail);
    }

    function hydrateForms(detail) {
      setInlineFormMessage("review", "");
      setInlineFormMessage("approval", "");
      setInlineFormMessage("checklist", "");
      setInlineFormMessage("rollback", "");
      setExistingNote("review-existing-note", "");
      setExistingNote("approval-existing-note", "");
      setExistingNote("checklist-existing-note", "");
      setExistingNote("rollback-existing-note", "");

      const reviewForm = document.getElementById("review-form");
      reviewForm.elements.decision.value = detail.review_form_defaults.decision;
      reviewForm.elements.reviewer.value = detail.review_form_defaults.reviewer;
      reviewForm.elements.rationale.value = detail.review_form_defaults.rationale;
      reviewForm.elements.followup_required.checked = Boolean(detail.review_form_defaults.followup_required);
      reviewForm.elements.notes.value = (detail.review_form_defaults.notes || []).join("\\n");
      reviewForm.querySelector("button[type='submit']").textContent = detail.review_decision.available ? "검토 판단 수정 저장" : "검토 판단 저장";
      setExistingNote(
        "review-existing-note",
        detail.review_decision.available
          ? `현재 저장본: ${detail.review_decision.reviewer || "unknown"} / ${detail.review_decision.reviewed_at || "unknown"} / ${detail.review_decision.decision || "unknown"} | 내용을 바꾸려면 '기존 기록 덮어쓰기'를 true로 바꾸고 다시 저장하세요.`
          : ""
      );

      const approvalForm = document.getElementById("approval-form");
      const defaults = detail.approval_form_defaults;
      const approvalRecords = (detail.approval.available ? (detail.approval.records || {}) : {});
      const activeApprovalRecord = approvalRecords[defaults.approval_type] || approvalRecords.transform_approval || approvalRecords.promotion_approval || null;
      approvalForm.elements.approval_type.value = defaults.approval_type;
      approvalForm.elements.decision.value = defaults.decision;
      approvalForm.elements.approver.value = defaults.approver;
      approvalForm.elements.rationale.value = defaults.rationale;
      approvalForm.elements.followup_required.checked = Boolean(defaults.followup_required);
      approvalForm.elements.notes.value = (defaults.notes || []).join("\\n");
      approvalForm.elements.source_review_decision.value = defaults.source_review_decision === "none" ? "아직 생성 안 됨" : defaults.source_review_decision;
      approvalForm.elements.source_packet_id.value = defaults.source_packet_id === "none" ? "아직 생성 안 됨" : defaults.source_packet_id;
      approvalForm.elements.source_transform_template.value = defaults.source_transform_template === "none" ? "아직 생성 안 됨" : defaults.source_transform_template;
      approvalForm.elements.final_target_name.value = defaults.final_target_name;
      approvalForm.elements.final_target_path.value = defaults.final_target_path;
      approvalForm.elements.rollback_reference.value = defaults.rollback_reference;
      approvalForm.querySelector("button[type='submit']").textContent = detail.approval.available ? "최종 검토 기록 수정 저장" : "최종 검토 기록 저장";
      setExistingNote(
        "approval-existing-note",
        detail.approval.available
          ? `현재 저장본: ${(activeApprovalRecord || {}).approver || "unknown"} / ${(activeApprovalRecord || {}).approved_at || "unknown"} / ${(activeApprovalRecord || {}).decision || "unknown"} | 수정하려면 '기존 기록 덮어쓰기'를 true로 바꾸고 다시 저장하세요.`
          : ""
      );

      const approvalBlockedReasons = [];
      if (!detail.review_decision.available) {
        approvalBlockedReasons.push("먼저 검토 판단을 저장해야 합니다.");
      }
      if (!detail.promotion_packet.available) {
        approvalBlockedReasons.push("먼저 승격 검토 묶음(packet)을 생성해야 합니다.");
      }
      if (!detail.transform_template.available) {
        approvalBlockedReasons.push("먼저 수동 변환 양식(transform template)을 생성해야 합니다.");
      }
      const approvalSubmitButton = approvalForm.querySelector("button[type='submit']");
      const approvalBlocked = approvalBlockedReasons.length > 0;
      approvalSubmitButton.disabled = approvalBlocked;
      setPrereqNote("approval-prereq-note", approvalBlocked ? approvalBlockedReasons.join(" ") : "");

      const checklistForm = document.getElementById("checklist-form");
      const checklistDefaults = detail.checklist_form_defaults;
      checklistForm.elements.operator.value = checklistDefaults.operator;
      checklistForm.elements.review_decision_exists.checked = Boolean(checklistDefaults.review_decision_exists);
      checklistForm.elements.approval_record_exists.checked = Boolean(checklistDefaults.approval_record_exists);
      checklistForm.elements.validation_passed.checked = Boolean(checklistDefaults.validation_passed);
      checklistForm.elements.sandbox_passed.checked = Boolean(checklistDefaults.sandbox_passed);
      checklistForm.elements.sandbox_only_confirmed.checked = Boolean(checklistDefaults.sandbox_only_confirmed);
      checklistForm.elements.promotion_required_confirmed.checked = Boolean(checklistDefaults.promotion_required_confirmed);
      checklistForm.elements.generated_only_fields_removed.checked = Boolean(checklistDefaults.generated_only_fields_removed);
      checklistForm.elements.target_name_manually_chosen.checked = Boolean(checklistDefaults.target_name_manually_chosen);
      checklistForm.elements.naming_collision_resolved.checked = Boolean(checklistDefaults.naming_collision_resolved);
      checklistForm.elements.core_skill_overwrite_absent.checked = Boolean(checklistDefaults.core_skill_overwrite_absent);
      checklistForm.elements.rollback_reference_prepared.checked = Boolean(checklistDefaults.rollback_reference_prepared);
      checklistForm.elements.direct_move_not_used.checked = Boolean(checklistDefaults.direct_move_not_used);
      checklistForm.elements.target_name.value = checklistDefaults.target_name;
      checklistForm.elements.target_path.value = checklistDefaults.target_path;
      checklistForm.elements.notes.value = (checklistDefaults.notes || []).join("\\n");
      checklistForm.querySelector("button[type='submit']").textContent = detail.candidate_checklist.available ? "점검표 수정 저장" : "점검표 저장";
      setExistingNote(
        "checklist-existing-note",
        detail.candidate_checklist.available
          ? `현재 저장본: ${detail.candidate_checklist.operator || "unknown"} / ${detail.candidate_checklist.checked_at || "unknown"} / 전체 통과=${detail.candidate_checklist.all_checks_passed ? "예" : "아니오"} | 수정하려면 '기존 기록 덮어쓰기'를 true로 바꾸고 다시 저장하세요.`
          : ""
      );

      const checklistBlockedReasons = [];
      if (!detail.review_decision.available) {
        checklistBlockedReasons.push("먼저 검토 판단을 저장해야 합니다.");
      }
      if (!detail.approval.available) {
        checklistBlockedReasons.push("현재 구현에서는 최종 검토 기록이 먼저 필요합니다.");
      }
      if (!detail.transform_template.available) {
        checklistBlockedReasons.push("먼저 수동 변환 양식(transform template)을 생성해야 합니다.");
      }
      const checklistSubmitButton = checklistForm.querySelector("button[type='submit']");
      const checklistBlocked = checklistBlockedReasons.length > 0;
      checklistSubmitButton.disabled = checklistBlocked;
      setPrereqNote("checklist-prereq-note", checklistBlocked ? checklistBlockedReasons.join(" ") : "");

      const rollbackForm = document.getElementById("rollback-form");
      const rollbackDefaults = detail.rollback_form_defaults;
      rollbackForm.elements.operator.value = rollbackDefaults.operator;
      rollbackForm.elements.reason.value = rollbackDefaults.reason;
      rollbackForm.elements.production_artifact_ref.value = rollbackDefaults.production_artifact_ref;
      rollbackForm.elements.candidate_artifact_ref.value = rollbackDefaults.candidate_artifact_ref;
      rollbackForm.elements.rollback_reference.value = rollbackDefaults.rollback_reference;
      rollbackForm.elements.notes.value = (rollbackDefaults.notes || []).join("\\n");
      rollbackForm.querySelector("button[type='submit']").textContent = detail.rollback.available ? "철회 기록 수정 저장" : "철회 기록 저장";
      setExistingNote(
        "rollback-existing-note",
        detail.rollback.available
          ? `현재 저장본: ${detail.rollback.operator || "unknown"} / ${detail.rollback.rolled_back_at || "unknown"} / ${detail.rollback.reason || "none"} | 수정하려면 '기존 기록 덮어쓰기'를 true로 바꾸고 다시 저장하세요.`
          : ""
      );
    }

    function renderPairs(pairs) {
      return pairs.map(([label, value]) => `
        <section class="section">
          <h2>${label}</h2>
          <div class="meta">${formatValue(value)}</div>
        </section>
      `).join("");
    }

    function hydrateManualPromotion(detail) {
      const manual = detail.manual_promotion;
      const readiness = manual.readiness;
      const banner = document.getElementById("manual-promotion-banner");
      const existing = document.getElementById("manual-promotion-existing-note");
      const button = document.getElementById("manual-promotion-button");
      const summary = document.getElementById("manual-promotion-summary");
      const message = document.getElementById("manual-promotion-message");
      setMessage("manual-promotion-message", "");

      const missingChecklistSummary = (readiness.checklist_missing_items || []).slice(0, 3).join(", ");
      const bannerText = readiness.can_execute
        ? "Ready for manual promotion"
        : (
          missingChecklistSummary
            ? `승격 실행 불가: 미완료 점검 항목 - ${missingChecklistSummary}`
            : (
              readiness.blockers[0]
                ? `승격 실행 불가: ${readiness.blockers[0]}`
                : "승격 실행 조건이 아직 충족되지 않았습니다."
            )
        );
      banner.textContent = bannerText;
      banner.classList.add("active");
      banner.classList.toggle("ready", Boolean(readiness.can_execute));

      summary.innerHTML = renderPairs([
        ["candidate readiness", readiness.can_execute ? "ready" : "blocked"],
        ["checklist all_checks_passed", readiness.checklist_all_checks_passed],
        ["approval 존재 여부", readiness.approval_exists],
        ["transform template 존재 여부", readiness.transform_exists],
        ["naming collision resolved 여부", readiness.naming_collision_resolved],
        ["rollback reference prepared 여부", readiness.rollback_reference_prepared],
        ["미완료 점검 항목", (readiness.checklist_missing_items || []).length ? readiness.checklist_missing_items : "없음"],
      ]);

      button.disabled = !readiness.can_execute;
      button.title = readiness.can_execute
        ? "명시적 확인 후 수동 승격 실행"
        : (readiness.blockers[0] || "선행 조건이 아직 충족되지 않았습니다.");

      setExistingNote(
        "manual-promotion-existing-note",
        manual.promotion_record.available
          ? `현재 저장본: ${manual.promotion_record.operator || "unknown"} / ${manual.promotion_record.promoted_at || "unknown"} / ${manual.promotion_record.final_target_name || "none"} -> ${manual.promotion_record.final_target_path || "none"}`
          : ""
      );

      message.style.display = "none";
    }

    function closePromotionModal() {
      const modal = document.getElementById("promotion-modal");
      modal.classList.remove("active");
      modal.setAttribute("aria-hidden", "true");
      document.getElementById("promotion-modal-message").style.display = "none";
    }

    function openPromotionModal() {
      if (!currentDetail || !selectedSkillId) return;
      const manual = currentDetail.manual_promotion;
      if (!manual.readiness.can_execute) {
        setMessage("manual-promotion-message", manual.readiness.blockers[0] || "선행 조건이 아직 충족되지 않았습니다.");
        return;
      }
      const modal = document.getElementById("promotion-modal");
      const confirmPhrase = manual.confirm_phrase;
      document.getElementById("promotion-modal-summary").innerHTML = renderPairs([
        ["skill_id", selectedSkillId],
        ["target_name", manual.readiness.target_name || "없음"],
        ["target_path", manual.readiness.target_path || "없음"],
        ["approval decision", (((currentDetail.approval || {}).records || {}).transform_approval || ((currentDetail.approval || {}).records || {}).promotion_approval || {}).decision || "없음"],
        ["checklist all_checks_passed", manual.readiness.checklist_all_checks_passed],
        ["overwrite risk", manual.readiness.overwrite_risk],
        ["rollback reference", manual.readiness.rollback_reference],
      ]);
      document.getElementById("promotion-modal-operator").value = currentDetail.manual_promotion_defaults.operator || "";
      document.getElementById("promotion-modal-notes").value = (currentDetail.manual_promotion_defaults.notes || []).join("\\n");
      document.getElementById("promotion-modal-confirm").value = "";
      document.getElementById("promotion-modal-confirm-label").textContent = `정확히 입력: ${confirmPhrase}`;
      const executeButton = document.getElementById("promotion-modal-execute");
      executeButton.disabled = true;
      setMessage("promotion-modal-message", "");
      modal.classList.add("active");
      modal.setAttribute("aria-hidden", "false");
    }

    async function loadQueue() {
      setMessage("queue-message", "");
      const response = await fetch("/api/queue");
      const payload = await response.json();
      const list = document.getElementById("queue-list");
      if (!payload.items.length) {
        list.innerHTML = `<div class="empty">generated skill 수동 검토 대기열이 비어 있습니다.</div>`;
        return;
      }
      list.innerHTML = payload.items.map((item) => {
        const explanation = explainSkill(item);
        return `
        <div class="queue-item ${selectedSkillId === item.skill_id ? "active" : ""}" data-skill-id="${item.skill_id}">
          <strong class="queue-title">${explanation.title}</strong>
          <div class="queue-purpose">${formatValue(item.purpose)}</div>
          <div class="status">${formatValue(item.promotion_status)}</div>
          <div class="meta">위험도: ${formatValue(item.risk_level)}</div>
          <div class="meta">추천 경로: ${formatValue(item.recommended_path)}</div>
          <div class="meta">${formatValue(item.validation_summary)}</div>
          <div class="meta">${formatValue(item.sandbox_result_summary)}</div>
          <div class="meta">${item.auto_suggestion_available ? "자동 추천 가능" : "자동 추천 없음"}</div>
          <details class="queue-tech">
            <summary>기술 ID 보기</summary>
            <div class="meta">skill_id: ${item.skill_id}</div>
            <div class="meta">skill_kind: ${formatValue(item.skill_kind)}</div>
            <div class="meta">auto: ${formatValue(item.auto_suggestion_reason || "none")}</div>
          </details>
        </div>
      `;
      }).join("");
      document.querySelectorAll(".queue-item").forEach((node) => {
        node.addEventListener("click", () => selectSkill(node.dataset.skillId));
      });
    }

    async function selectSkill(skillId) {
      selectedSkillId = skillId;
      await loadQueue();
      const response = await fetch(`/api/skills/${encodeURIComponent(skillId)}`);
      const detail = await response.json();
      renderDetail(detail);
    }

    async function submitJson(url, payload) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "request failed");
      }
      return data;
    }

    document.getElementById("review-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedSkillId) return;
      const form = event.target;
      try {
        setInlineFormMessage("review", "");
        await submitJson(`/api/review-decisions/${encodeURIComponent(selectedSkillId)}`, {
          decision: form.elements.decision.value,
          reviewer: form.elements.reviewer.value,
          rationale: form.elements.rationale.value,
          followup_required: form.elements.followup_required.checked,
          notes: form.elements.notes.value ? form.elements.notes.value.split("\\n").filter(Boolean) : [],
          allow_replace: form.elements.allow_replace.value === "true",
        });
        setMessage("page-message", "검토 판단이 저장되었습니다.");
        setInlineFormMessage("review", "검토 판단이 저장되었습니다.");
        await selectSkill(selectedSkillId);
      } catch (error) {
        setMessage("page-message", error.message);
        setInlineFormMessage("review", error.message);
        document.getElementById("review-form-message").scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    document.getElementById("approval-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedSkillId) return;
      const form = event.target;
      if (form.querySelector("button[type='submit']").disabled) {
        const text = document.getElementById("approval-prereq-note")?.textContent || "선행 조건이 아직 충족되지 않았습니다.";
        setInlineFormMessage("approval", text);
        return;
      }
      try {
        setInlineFormMessage("approval", "");
        await submitJson(`/api/approvals/${encodeURIComponent(selectedSkillId)}`, {
          approval_type: form.elements.approval_type.value,
          decision: form.elements.decision.value,
          approver: form.elements.approver.value,
          rationale: form.elements.rationale.value,
          followup_required: form.elements.followup_required.checked,
          notes: form.elements.notes.value ? form.elements.notes.value.split("\\n").filter(Boolean) : [],
          source_review_decision: form.elements.source_review_decision.value,
          source_packet_id: form.elements.source_packet_id.value,
          source_transform_template: form.elements.source_transform_template.value,
          final_target_name: form.elements.final_target_name.value,
          final_target_path: form.elements.final_target_path.value,
          rollback_reference: form.elements.rollback_reference.value,
          allow_replace: form.elements.allow_replace.value === "true",
        });
        setMessage("page-message", "최종 검토 기록이 저장되었습니다.");
        setInlineFormMessage("approval", "최종 검토 기록이 저장되었습니다.");
        await selectSkill(selectedSkillId);
      } catch (error) {
        setMessage("page-message", error.message);
        setInlineFormMessage("approval", error.message);
        document.getElementById("approval-form-message").scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    document.getElementById("checklist-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedSkillId) return;
      const form = event.target;
      if (form.querySelector("button[type='submit']").disabled) {
        const text = document.getElementById("checklist-prereq-note")?.textContent || "선행 조건이 아직 충족되지 않았습니다.";
        setInlineFormMessage("checklist", text);
        return;
      }
      try {
        setInlineFormMessage("checklist", "");
        await submitJson(`/api/checklists/${encodeURIComponent(selectedSkillId)}`, {
          operator: form.elements.operator.value,
          review_decision_exists: form.elements.review_decision_exists.checked,
          approval_record_exists: form.elements.approval_record_exists.checked,
          validation_passed: form.elements.validation_passed.checked,
          sandbox_passed: form.elements.sandbox_passed.checked,
          sandbox_only_confirmed: form.elements.sandbox_only_confirmed.checked,
          promotion_required_confirmed: form.elements.promotion_required_confirmed.checked,
          generated_only_fields_removed: form.elements.generated_only_fields_removed.checked,
          target_name_manually_chosen: form.elements.target_name_manually_chosen.checked,
          naming_collision_resolved: form.elements.naming_collision_resolved.checked,
          core_skill_overwrite_absent: form.elements.core_skill_overwrite_absent.checked,
          rollback_reference_prepared: form.elements.rollback_reference_prepared.checked,
          direct_move_not_used: form.elements.direct_move_not_used.checked,
          target_name: form.elements.target_name.value,
          target_path: form.elements.target_path.value,
          notes: form.elements.notes.value ? form.elements.notes.value.split("\\n").filter(Boolean) : [],
          allow_replace: form.elements.allow_replace.value === "true",
        });
        setMessage("page-message", "승격 전 점검표가 저장되었습니다.");
        setInlineFormMessage("checklist", "승격 전 점검표가 저장되었습니다.");
        await selectSkill(selectedSkillId);
      } catch (error) {
        setMessage("page-message", error.message);
        setInlineFormMessage("checklist", error.message);
        document.getElementById("checklist-form-message").scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    document.getElementById("rollback-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedSkillId) return;
      const form = event.target;
      try {
        setInlineFormMessage("rollback", "");
        await submitJson(`/api/rollbacks/${encodeURIComponent(selectedSkillId)}`, {
          operator: form.elements.operator.value,
          reason: form.elements.reason.value,
          production_artifact_ref: form.elements.production_artifact_ref.value,
          candidate_artifact_ref: form.elements.candidate_artifact_ref.value,
          rollback_reference: form.elements.rollback_reference.value,
          notes: form.elements.notes.value ? form.elements.notes.value.split("\\n").filter(Boolean) : [],
          allow_replace: form.elements.allow_replace.value === "true",
        });
        setMessage("page-message", "철회 기록이 저장되었습니다.");
        setInlineFormMessage("rollback", "철회 기록이 저장되었습니다.");
        await selectSkill(selectedSkillId);
      } catch (error) {
        setMessage("page-message", error.message);
        setInlineFormMessage("rollback", error.message);
        document.getElementById("rollback-form-message").scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    document.getElementById("manual-promotion-button").addEventListener("click", () => {
      openPromotionModal();
    });

    document.getElementById("promotion-modal-cancel").addEventListener("click", () => {
      closePromotionModal();
    });

    document.getElementById("promotion-modal-confirm").addEventListener("input", (event) => {
      const expected = currentDetail?.manual_promotion?.confirm_phrase || "";
      document.getElementById("promotion-modal-execute").disabled = event.target.value !== expected;
    });

    document.getElementById("promotion-modal-execute").addEventListener("click", async () => {
      if (!selectedSkillId || !currentDetail) return;
      const operator = document.getElementById("promotion-modal-operator").value;
      const confirmPhrase = document.getElementById("promotion-modal-confirm").value;
      const notesValue = document.getElementById("promotion-modal-notes").value;
      try {
        setMessage("promotion-modal-message", "");
        const result = await submitJson(`/api/promotions/${encodeURIComponent(selectedSkillId)}`, {
          operator,
          confirm_phrase: confirmPhrase,
          notes: notesValue ? notesValue.split("\\n").filter(Boolean) : [],
        });
        closePromotionModal();
        setMessage("page-message", `수동 승격 실행이 완료되었습니다. candidate=${result.candidate.path} promotion=${result.promotion.path}`);
        setMessage("manual-promotion-message", "수동 승격 실행이 완료되었습니다.");
        await selectSkill(selectedSkillId);
      } catch (error) {
        setMessage("promotion-modal-message", error.message);
      }
    });

    loadQueue()
      .then(async () => {
        const first = document.querySelector(".queue-item");
        if (first) {
          await selectSkill(first.dataset.skillId);
        }
      })
      .catch((error) => setMessage("queue-message", error.message));

    window.addEventListener("resize", () => {
      if (currentDetail) {
        renderVisualization(currentDetail);
      }
    });

    document.getElementById("promotion-modal").addEventListener("click", (event) => {
      if (event.target.id === "promotion-modal") {
        closePromotionModal();
      }
    });
  </script>
</body>
</html>"""


class ReviewerDashboardHandler(BaseHTTPRequestHandler):
    reference_path = DEFAULT_REFERENCE

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json body: {exc}") from exc

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(build_reviewer_dashboard_html())
            return
        if parsed.path == "/api/queue":
            self._send_json({"items": build_reviewer_dashboard_queue_items(reference=self.reference_path)})
            return
        if parsed.path.startswith("/api/skills/"):
            skill_id = parsed.path.rsplit("/", 1)[-1]
            self._send_json(build_reviewer_dashboard_detail(skill_id, reference=self.reference_path))
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json_body()
            if parsed.path.startswith("/api/review-decisions/"):
                skill_id = parsed.path.rsplit("/", 1)[-1]
                result = save_reviewer_dashboard_review_decision(skill_id, payload, reference=self.reference_path)
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/approvals/"):
                skill_id = parsed.path.rsplit("/", 1)[-1]
                result = save_reviewer_dashboard_approval(skill_id, payload, reference=self.reference_path)
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/checklists/"):
                skill_id = parsed.path.rsplit("/", 1)[-1]
                result = save_reviewer_dashboard_checklist(skill_id, payload, reference=self.reference_path)
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/rollbacks/"):
                skill_id = parsed.path.rsplit("/", 1)[-1]
                result = save_reviewer_dashboard_rollback(skill_id, payload, reference=self.reference_path)
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/promotions/"):
                skill_id = parsed.path.rsplit("/", 1)[-1]
                result = execute_reviewer_dashboard_manual_promotion(skill_id, payload, reference=self.reference_path)
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args) -> None:
        return


def run_local_reviewer_dashboard(
    *,
    host: str,
    port: int,
    reference: str | None = None,
) -> ThreadingHTTPServer:
    reference_path = reference or DEFAULT_REFERENCE

    class _ConfiguredHandler(ReviewerDashboardHandler):
        pass

    _ConfiguredHandler.reference_path = reference_path
    return ThreadingHTTPServer((host, port), _ConfiguredHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local generated skill reviewer dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="local bind host")
    parser.add_argument("--port", type=int, default=8765, help="local bind port")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE, help="reference path used to resolve runtime-data root")
    args = parser.parse_args(argv)

    server = run_local_reviewer_dashboard(host=args.host, port=args.port, reference=args.reference)
    print(f"local reviewer dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
