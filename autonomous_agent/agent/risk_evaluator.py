import json
from pathlib import Path

from .generated_skill_sandbox import (
    GENERATED_SKILL_FORBIDDEN_CAPABILITIES,
    load_generated_skill_draft,
    load_generated_skill_promotion_packet,
)
from .workspace_metrics import resolve_runtime_data_root


LOW_RISK_ALLOWED_KINDS = {
    "runtime_state_summarizer",
    "proposal_summary_formatter",
    "review_note_compactor",
    "diff_hint_reformatter",
}
LOW_RISK_ALLOWED_CAPABILITIES = {"read_only", "summary", "formatting"}


def _load_risk_inputs(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    reference: str | Path | None = None,
) -> dict:
    loaded_draft = draft or load_generated_skill_draft(skill_id, reference=reference) or {}
    return {
        "skill_id": skill_id,
        "draft": loaded_draft,
        "validation": validation or loaded_draft.get("last_validation_report") or {},
        "sandbox": sandbox or loaded_draft.get("last_sandbox_result") or {},
        "packet": packet or load_generated_skill_promotion_packet(skill_id, reference=reference) or {},
    }


def _overwrite_risk_from_draft(
    draft: dict,
    *,
    reference: str | Path | None = None,
) -> str:
    skill_definition = draft.get("skill_definition") or {}
    skill_name = str(skill_definition.get("name") or "").strip()
    if not skill_name:
        return "unknown"
    project_root = resolve_runtime_data_root(reference).parent
    production_skill_path = project_root / "skills" / skill_name
    return "high" if production_skill_path.exists() else "none"


def _classify_risk(inputs: dict, *, reference: str | Path | None = None) -> dict:
    draft = inputs["draft"]
    validation = inputs["validation"]
    sandbox = inputs["sandbox"]
    packet = inputs["packet"]
    skill_definition = draft.get("skill_definition") or {}
    capabilities = {
        str(item).strip().lower()
        for item in skill_definition.get("capabilities", [])
        if str(item).strip()
    }
    skill_kind = str(skill_definition.get("skill_kind") or "")
    packet_assessment = packet.get("promotion_assessment") or {}
    overwrite_risk = packet_assessment.get("overwrite_risk")
    if overwrite_risk is None:
        overwrite_risk = _overwrite_risk_from_draft(draft, reference=reference)
    naming_collision = bool(
        (packet.get("risk_checks") or {}).get("naming_collision")
        or overwrite_risk in {"low", "high"}
    )

    high_reasons: list[str] = []
    medium_reasons: list[str] = []

    if not draft:
        high_reasons.append("generated skill draft is missing")
    if capabilities & GENERATED_SKILL_FORBIDDEN_CAPABILITIES:
        high_reasons.append("forbidden capability present")
    if draft.get("sandbox_only") is not True:
        high_reasons.append("sandbox_only invariant is broken")
    if draft.get("promotion_required") is not True:
        high_reasons.append("promotion_required invariant is broken")
    if overwrite_risk in {"low", "high"}:
        high_reasons.append("overwrite risk exists")
    if naming_collision:
        high_reasons.append("naming collision remains unresolved")
    if skill_definition.get("risk_level") not in {None, "", "safe"}:
        high_reasons.append("skill risk_level is outside safe")

    if not high_reasons:
        if validation.get("validation_passed") is not True:
            medium_reasons.append("validation is not fully confirmed")
        if sandbox.get("sandbox_result") != "passed":
            medium_reasons.append("sandbox pass is not fully confirmed")
        if skill_kind not in LOW_RISK_ALLOWED_KINDS:
            medium_reasons.append("skill kind is outside the low-risk fast path allowlist")
        if capabilities - LOW_RISK_ALLOWED_CAPABILITIES:
            medium_reasons.append("capabilities extend beyond read_only/summary/formatting")
        if overwrite_risk == "unknown":
            medium_reasons.append("overwrite risk is still unknown")

    if high_reasons:
        return {
            "risk_level": "high",
            "reason": "; ".join(high_reasons),
            "confidence": "high",
            "overwrite_risk": overwrite_risk,
        }
    if medium_reasons:
        return {
            "risk_level": "medium",
            "reason": "; ".join(medium_reasons),
            "confidence": "medium",
            "overwrite_risk": overwrite_risk,
        }
    return {
        "risk_level": "low",
        "reason": "low-risk read-only skill with successful validation and sandbox results",
        "confidence": "high",
        "overwrite_risk": overwrite_risk,
    }


def decide_stage_path(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    reference: str | Path | None = None,
) -> dict:
    inputs = _load_risk_inputs(
        skill_id,
        draft=draft,
        validation=validation,
        sandbox=sandbox,
        packet=packet,
        reference=reference,
    )
    risk = _classify_risk(inputs, reference=reference)
    risk_level = risk["risk_level"]
    if risk_level == "low":
        return {
            "skill_id": skill_id,
            "risk_level": "low",
            "allowed_skips": ["validation", "approval", "checklist"],
            "required_stages": ["sandbox", "review", "promotion"],
            "recommended_path": ["sandbox", "review", "promotion"],
            "reason": risk["reason"],
            "confidence": risk["confidence"],
        }
    if risk_level == "medium":
        return {
            "skill_id": skill_id,
            "risk_level": "medium",
            "allowed_skips": ["checklist"],
            "required_stages": ["validation", "sandbox", "review", "approval", "promotion"],
            "recommended_path": ["validation", "sandbox", "review", "approval", "promotion"],
            "reason": risk["reason"],
            "confidence": risk["confidence"],
        }
    return {
        "skill_id": skill_id,
        "risk_level": "high",
        "allowed_skips": [],
        "required_stages": ["validation", "sandbox", "review", "approval", "checklist", "promotion"],
        "recommended_path": ["validation", "sandbox", "review", "approval", "checklist", "promotion"],
        "reason": risk["reason"],
        "confidence": risk["confidence"],
    }


def evaluate_skill_risk(
    skill_id: str,
    *,
    draft: dict | None = None,
    validation: dict | None = None,
    sandbox: dict | None = None,
    packet: dict | None = None,
    reference: str | Path | None = None,
) -> dict:
    return decide_stage_path(
        skill_id,
        draft=draft,
        validation=validation,
        sandbox=sandbox,
        packet=packet,
        reference=reference,
    )


def build_risk_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    report = evaluate_skill_risk(skill_id, reference=reference)
    lines = [
        "[Risk Evaluation]",
        f"- skill_id: {report['skill_id']}",
        f"- risk_level: {report['risk_level']}",
        f"- allowed_skips: {', '.join(report['allowed_skips']) if report['allowed_skips'] else 'none'}",
        f"- required_stages: {', '.join(report['required_stages'])}",
        f"- recommended_path: {' -> '.join(report['recommended_path'])}",
        f"- confidence: {report['confidence']}",
        f"- reason: {report['reason']}",
    ]
    return "\n".join(lines)


def build_risk_json(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    return json.dumps(
        evaluate_skill_risk(skill_id, reference=reference),
        ensure_ascii=False,
        indent=2,
    )
