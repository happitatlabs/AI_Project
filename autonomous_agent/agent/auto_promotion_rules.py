import json
from pathlib import Path

from .generated_skill_sandbox import (
    GENERATED_SKILL_FORBIDDEN_CAPABILITIES,
    load_generated_skill_candidate_checklist,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
    load_generated_skill_review_decision,
)
from .workspace_metrics import resolve_runtime_data_root


AUTO_PROMOTION_ALLOWED_KINDS = {
    "runtime_state_summarizer",
    "proposal_summary_formatter",
    "review_note_compactor",
    "diff_hint_reformatter",
}
AUTO_PROMOTION_ALLOWED_CAPABILITIES = {"read_only", "summary", "formatting"}
AUTO_CHECKLIST_SUGGESTION_FIELDS = {
    "validation_passed": True,
    "sandbox_passed": True,
    "sandbox_only_confirmed": True,
    "promotion_required_confirmed": True,
}


def _load_auto_promotion_input(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    existing_review: dict | None = None,
    existing_checklist: dict | None = None,
    reference: str | Path | None = None,
) -> dict:
    loaded_draft = draft or load_generated_skill_draft(skill_id, reference=reference) or {}
    loaded_validation = validation or loaded_draft.get("last_validation_report") or {}
    loaded_sandbox = sandbox or loaded_draft.get("last_sandbox_result") or {}
    loaded_packet = packet or load_generated_skill_promotion_packet(skill_id, reference=reference) or {}
    loaded_review = existing_review or load_generated_skill_review_decision(skill_id, reference=reference) or {}
    loaded_checklist = (
        existing_checklist
        or load_generated_skill_candidate_checklist(skill_id, reference=reference)
        or {}
    )
    return {
        "skill_id": skill_id,
        "draft": loaded_draft,
        "validation": loaded_validation,
        "sandbox": loaded_sandbox,
        "packet": loaded_packet,
        "existing_review": loaded_review,
        "existing_checklist": loaded_checklist,
    }


def build_auto_review_decision(
    *,
    reason: str = "low-risk read-only skill with successful sandbox validation",
) -> dict:
    return {
        "decision": "approve_for_consideration",
        "source": "auto_rule_engine",
        "confidence": "high",
        "reason": reason,
    }


def build_auto_checklist_suggestions() -> dict:
    return {
        **AUTO_CHECKLIST_SUGGESTION_FIELDS,
        "source": "auto_rule_engine",
        "note": "auto-filled readiness hints only; manual checklist completion is still required",
    }


def _auto_overwrite_risk(
    draft: dict,
    *,
    reference: str | Path | None = None,
) -> str:
    skill_definition = draft.get("skill_definition") or {}
    skill_name = str(skill_definition.get("name") or "").strip()
    if not skill_name:
        return "none"
    project_root = resolve_runtime_data_root(reference).parent
    production_skill_path = project_root / "skills" / skill_name
    return "high" if production_skill_path.exists() else "none"


def evaluate_auto_promotion_rules(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    existing_review: dict | None = None,
    existing_checklist: dict | None = None,
    reference: str | Path | None = None,
) -> dict:
    payload = _load_auto_promotion_input(
        skill_id,
        draft=draft,
        validation=validation,
        sandbox=sandbox,
        packet=packet,
        existing_review=existing_review,
        existing_checklist=existing_checklist,
        reference=reference,
    )
    draft_payload = payload["draft"]
    validation_payload = payload["validation"]
    sandbox_payload = payload["sandbox"]
    packet_payload = payload["packet"]
    review_payload = payload["existing_review"]
    checklist_payload = payload["existing_checklist"]
    skill_definition = draft_payload.get("skill_definition") or {}
    capabilities = {
        str(item).strip().lower()
        for item in skill_definition.get("capabilities", [])
        if str(item).strip()
    }
    packet_assessment = packet_payload.get("promotion_assessment") or {}
    skill_kind = str(skill_definition.get("skill_kind") or "")
    overwrite_risk = packet_assessment.get("overwrite_risk")
    if overwrite_risk is None:
        overwrite_risk = _auto_overwrite_risk(draft_payload, reference=reference)

    blocked_reasons: list[str] = []

    if not draft_payload:
        blocked_reasons.append("generated skill draft is missing")
    if skill_kind not in AUTO_PROMOTION_ALLOWED_KINDS:
        blocked_reasons.append("skill kind is outside the low-risk auto-review allowlist")
    if capabilities - AUTO_PROMOTION_ALLOWED_CAPABILITIES:
        blocked_reasons.append("capabilities exceed the low-risk read-only allowlist")
    forbidden_present = capabilities & GENERATED_SKILL_FORBIDDEN_CAPABILITIES
    if forbidden_present:
        blocked_reasons.append(
            "forbidden capabilities detected: " + ", ".join(sorted(forbidden_present))
        )
    if validation_payload.get("validation_passed") is not True:
        blocked_reasons.append("validation did not pass")
    if sandbox_payload.get("sandbox_result") != "passed":
        blocked_reasons.append("sandbox result is not passed")
    if draft_payload.get("sandbox_only") is not True:
        blocked_reasons.append("sandbox_only must remain true")
    if draft_payload.get("promotion_required") is not True:
        blocked_reasons.append("promotion_required must remain true")
    if overwrite_risk != "none":
        blocked_reasons.append("overwrite risk must be none")
    if overwrite_risk != "none":
        blocked_reasons.append("naming collision risk must be false")
    if review_payload:
        blocked_reasons.append("existing human review decision already exists")
    if checklist_payload:
        blocked_reasons.append("existing checklist record already exists")

    auto_applicable = not blocked_reasons
    auto_review_decision = build_auto_review_decision() if auto_applicable else None
    auto_checklist_suggestions = (
        build_auto_checklist_suggestions() if auto_applicable else {}
    )
    return {
        "auto_applicable": auto_applicable,
        "auto_review_decision": auto_review_decision,
        "auto_checklist_suggestions": auto_checklist_suggestions,
        "blocked_reason": blocked_reasons[0] if blocked_reasons else "",
        "confidence": "high" if auto_applicable else "low",
    }


def build_auto_promotion_report(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    existing_review: dict | None = None,
    existing_checklist: dict | None = None,
    reference: str | Path | None = None,
) -> str:
    result = evaluate_auto_promotion_rules(
        skill_id,
        draft=draft,
        validation=validation,
        sandbox=sandbox,
        packet=packet,
        existing_review=existing_review,
        existing_checklist=existing_checklist,
        reference=reference,
    )
    lines = [
        "[Auto Promotion Suggestion]",
        f"- skill_id: {skill_id}",
        f"- auto_applicable: {result['auto_applicable']}",
        f"- confidence: {result['confidence']}",
        f"- blocked_reason: {result['blocked_reason'] or 'none'}",
        "",
        "[Auto Review Decision]",
    ]
    if result["auto_review_decision"]:
        for key, value in result["auto_review_decision"].items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "[Auto Checklist Suggestions]"])
    if result["auto_checklist_suggestions"]:
        for key, value in result["auto_checklist_suggestions"].items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def build_auto_promotion_json(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    return json.dumps(
        evaluate_auto_promotion_rules(skill_id, reference=reference),
        ensure_ascii=False,
        indent=2,
    )
