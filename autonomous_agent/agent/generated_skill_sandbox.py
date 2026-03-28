import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .execution_mode import build_experimental_sandbox_gate
from .workspace_metrics import resolve_runtime_data_root

GENERATED_SKILLS_DIRNAME = "generated_skills"
GENERATED_SKILL_RESULTS_DIRNAME = "generated_skill_results"
GENERATED_SKILL_QUEUE_DIRNAME = "generated_skill_queue"
GENERATED_SKILL_REVIEWS_DIRNAME = "generated_skill_reviews"
GENERATED_SKILL_PACKETS_DIRNAME = "generated_skill_packets"
GENERATED_SKILL_TRANSFORMS_DIRNAME = "generated_skill_transforms"
GENERATED_SKILL_CANDIDATES_DIRNAME = "generated_skill_candidates"

GENERATED_SKILL_ALLOWED_KINDS = {
    "runtime_state_summarizer": {
        "allowed_inputs": ["runtime_state"],
        "allowed_outputs": ["summary_lines", "summary_text"],
        "default_name": "runtime_state_summarizer",
        "default_steps": ["summarize_runtime_state"],
    },
    "proposal_summary_formatter": {
        "allowed_inputs": ["proposal"],
        "allowed_outputs": ["summary_text"],
        "default_name": "proposal_summary_formatter",
        "default_steps": ["format_proposal_summary"],
    },
    "review_note_compactor": {
        "allowed_inputs": ["review_notes"],
        "allowed_outputs": ["compacted_notes", "summary_text"],
        "default_name": "review_note_compactor",
        "default_steps": ["compact_review_notes"],
    },
    "diff_hint_reformatter": {
        "allowed_inputs": ["diff_hints"],
        "allowed_outputs": ["normalized_diff_hints", "summary_text"],
        "default_name": "diff_hint_reformatter",
        "default_steps": ["reformat_diff_hints"],
    },
}

GENERATED_SKILL_ALLOWED_CAPABILITIES = {"read_only", "summary", "formatting"}
GENERATED_SKILL_FORBIDDEN_CAPABILITIES = {
    "file_write",
    "file_delete",
    "file_modify",
    "network",
    "subprocess",
    "shell",
    "daemon",
    "apply",
    "rollback",
    "backup",
    "core_overwrite",
    "production_registration",
}
GENERATED_SKILL_FORBIDDEN_TEXT_PATTERNS = (
    r"\bsubprocess\b",
    r"\bos\.system\b",
    r"\brequests\b",
    r"\burllib\b",
    r"\bsocket\b",
    r"\bhttp\b",
    r"\bhttps\b",
    r"\bimport\b",
    r"\bfrom\b",
    r"\bshell\b",
    r"\bnetwork\b",
    r"\bdaemon\b",
    r"\bapply\b",
    r"\brollback\b",
    r"\bbackup\b",
    r"\boverwrite\b",
    r"\bdelete\b",
    r"\bwrite file\b",
)
GENERATED_SKILL_STATUSES = {
    "draft",
    "validation_failed",
    "validated",
    "sandbox_failed",
    "sandbox_passed",
    "queued_for_manual_promotion",
    "promoted",
}
GENERATED_SKILL_REVIEW_DECISIONS = {
    "approve_for_consideration",
    "rejected",
    "needs_followup",
}
GENERATED_SKILL_APPROVAL_TYPES = {
    "promotion_approval",
    "transform_approval",
}
GENERATED_SKILL_APPROVAL_DECISIONS = {
    "approved",
    "rejected",
    "needs_followup",
}
GENERATED_SKILL_CHECKLIST_BOOL_FIELDS = (
    "review_decision_exists",
    "approval_record_exists",
    "validation_passed",
    "sandbox_passed",
    "sandbox_only_confirmed",
    "promotion_required_confirmed",
    "generated_only_fields_removed",
    "target_name_manually_chosen",
    "naming_collision_resolved",
    "core_skill_overwrite_absent",
    "rollback_reference_prepared",
    "direct_move_not_used",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generated_skill_directories(reference: str | Path | None = None) -> dict[str, Path]:
    runtime_root = resolve_runtime_data_root(reference)
    return {
        "runtime_root": runtime_root,
        "generated_skills": runtime_root / GENERATED_SKILLS_DIRNAME,
        "generated_skill_results": runtime_root / GENERATED_SKILL_RESULTS_DIRNAME,
        "generated_skill_queue": runtime_root / GENERATED_SKILL_QUEUE_DIRNAME,
        "generated_skill_reviews": runtime_root / GENERATED_SKILL_REVIEWS_DIRNAME,
        "generated_skill_packets": runtime_root / GENERATED_SKILL_PACKETS_DIRNAME,
        "generated_skill_transforms": runtime_root / GENERATED_SKILL_TRANSFORMS_DIRNAME,
        "generated_skill_candidates": runtime_root / GENERATED_SKILL_CANDIDATES_DIRNAME,
    }


def _ensure_generated_skill_directories(reference: str | Path | None = None) -> dict[str, Path]:
    directories = _generated_skill_directories(reference)
    for key in (
        "generated_skills",
        "generated_skill_results",
        "generated_skill_queue",
        "generated_skill_reviews",
        "generated_skill_packets",
        "generated_skill_transforms",
        "generated_skill_candidates",
    ):
        directories[key].mkdir(parents=True, exist_ok=True)
    return directories


def _generated_skill_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skills"] / f"{skill_id}.json"


def _generated_skill_result_path(run_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_results"] / f"{run_id}.json"


def _generated_skill_queue_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_queue"] / f"{skill_id}.json"


def _generated_skill_review_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_reviews"] / f"{skill_id}.review.json"


def _generated_skill_packet_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_packets"] / f"{skill_id}.packet.json"


def _generated_skill_transform_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_transforms"] / f"{skill_id}.transform.json"


def _generated_skill_approval_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_reviews"] / f"{skill_id}.approval.json"


def _generated_skill_checklist_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_reviews"] / f"{skill_id}.checklist.json"


def _generated_skill_rollback_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_reviews"] / f"{skill_id}.rollback.json"


def _generated_skill_candidate_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_candidates"] / f"{skill_id}.candidate.json"


def _generated_skill_promotion_path(skill_id: str, *, reference: str | Path | None = None) -> Path:
    return _generated_skill_directories(reference)["generated_skill_reviews"] / f"{skill_id}.promotion.json"


def _write_json(path: Path, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_generated_skill_id(skill_kind: str, purpose: str) -> str:
    kind_slug = re.sub(r"[^a-z0-9_]+", "_", skill_kind.lower()).strip("_") or "generated_skill"
    purpose_slug = re.sub(r"[^a-z0-9_]+", "_", purpose.lower()).strip("_")[:24] or "draft"
    return f"{kind_slug}_{purpose_slug}_{uuid4().hex[:10]}"


def _default_skill_fields(skill_kind: str) -> dict:
    allowed = GENERATED_SKILL_ALLOWED_KINDS[skill_kind]
    return {
        "name": allowed["default_name"],
        "description": f"{skill_kind} generated sandbox-only draft",
        "when_to_use": f"Use when a sandbox-only {skill_kind} summary is needed",
        "input": ", ".join(allowed["allowed_inputs"]),
        "output": ", ".join(allowed["allowed_outputs"]),
        "steps": list(allowed["default_steps"]),
        "risk_level": "safe",
        "behavior_class": "report",
        "skill_kind": skill_kind,
        "capabilities": ["read_only", "summary", "formatting"],
    }


def build_generated_skill_payload(
    *,
    purpose: str,
    generated_by: str,
    skill_kind: str,
    name: str | None = None,
    description: str | None = None,
    when_to_use: str | None = None,
    allowed_inputs: list[str] | None = None,
    allowed_outputs: list[str] | None = None,
    steps: list[str] | None = None,
) -> dict:
    if skill_kind not in GENERATED_SKILL_ALLOWED_KINDS:
        raise ValueError(f"unsupported generated skill kind: {skill_kind}")

    default_fields = _default_skill_fields(skill_kind)
    skill_id = _build_generated_skill_id(skill_kind, purpose)
    skill_definition = {
        **default_fields,
        "name": name or default_fields["name"],
        "description": description or default_fields["description"],
        "when_to_use": when_to_use or default_fields["when_to_use"],
        "steps": list(steps or default_fields["steps"]),
    }
    allowed = GENERATED_SKILL_ALLOWED_KINDS[skill_kind]
    return {
        "skill_id": skill_id,
        "created_at": _timestamp(),
        "generated_by": generated_by,
        "purpose": purpose,
        "status": "draft",
        "sandbox_only": True,
        "promotion_required": True,
        "allowed_inputs": list(allowed_inputs or allowed["allowed_inputs"]),
        "allowed_outputs": list(allowed_outputs or allowed["allowed_outputs"]),
        "validation_summary": "not_validated",
        "sandbox_result_summary": "not_run",
        "skill_definition": skill_definition,
    }


def save_generated_skill_draft(
    payload: dict,
    *,
    reference: str | Path | None = None,
) -> dict:
    _ensure_generated_skill_directories(reference)
    path = _generated_skill_path(payload["skill_id"], reference=reference)
    record = dict(payload)
    record["status"] = record.get("status", "draft")
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "skill": record,
    }


def load_generated_skill_draft(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_path(skill_id, reference=reference))


def load_generated_skill_result(
    run_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_result_path(run_id, reference=reference))


def _persist_generated_skill_record(
    payload: dict,
    *,
    reference: str | Path | None = None,
) -> dict:
    _write_json(_generated_skill_path(payload["skill_id"], reference=reference), payload)
    return payload


def _collect_textual_fields(payload: dict) -> str:
    skill_definition = payload.get("skill_definition") or {}
    parts = [
        str(payload.get("purpose", "")),
        str(skill_definition.get("name", "")),
        str(skill_definition.get("description", "")),
        str(skill_definition.get("when_to_use", "")),
        str(skill_definition.get("input", "")),
        str(skill_definition.get("output", "")),
    ]
    for step in skill_definition.get("steps", []):
        parts.append(str(step))
    for capability in skill_definition.get("capabilities", []):
        parts.append(str(capability))
    return "\n".join(parts).lower()


def build_generated_skill_validation_report(payload: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    required_fields = [
        "skill_id",
        "created_at",
        "generated_by",
        "purpose",
        "status",
        "sandbox_only",
        "promotion_required",
        "allowed_inputs",
        "allowed_outputs",
        "validation_summary",
        "sandbox_result_summary",
        "skill_definition",
    ]
    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        errors.append(f"missing required fields: {', '.join(missing_fields)}")

    if payload.get("sandbox_only") is not True:
        errors.append("sandbox_only must be true")
    if payload.get("promotion_required") is not True:
        errors.append("promotion_required must be true")
    if payload.get("status") not in GENERATED_SKILL_STATUSES:
        errors.append(f"unsupported generated skill status: {payload.get('status')}")

    skill_definition = payload.get("skill_definition")
    if not isinstance(skill_definition, dict):
        errors.append("skill_definition must be a dict")
        skill_definition = {}

    definition_required = [
        "name",
        "description",
        "when_to_use",
        "input",
        "output",
        "steps",
        "risk_level",
        "behavior_class",
        "skill_kind",
        "capabilities",
    ]
    missing_definition = [
        field for field in definition_required if field not in skill_definition
    ]
    if missing_definition:
        errors.append(f"missing skill_definition fields: {', '.join(missing_definition)}")

    skill_kind = skill_definition.get("skill_kind")
    if skill_kind not in GENERATED_SKILL_ALLOWED_KINDS:
        errors.append(f"unsupported generated skill kind: {skill_kind}")
    else:
        allowed = GENERATED_SKILL_ALLOWED_KINDS[skill_kind]
        if payload.get("allowed_inputs") != allowed["allowed_inputs"]:
            errors.append("allowed_inputs must match the sandbox-only skill kind contract")
        if payload.get("allowed_outputs") != allowed["allowed_outputs"]:
            errors.append("allowed_outputs must match the sandbox-only skill kind contract")

    if skill_definition.get("risk_level") != "safe":
        errors.append("generated skills must remain risk_level='safe'")
    if skill_definition.get("behavior_class") not in {"report", "observe"}:
        errors.append("generated skills must remain behavior_class='report' or 'observe'")

    steps = skill_definition.get("steps", [])
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
    else:
        non_string_steps = [step for step in steps if not isinstance(step, str) or not step.strip()]
        if non_string_steps:
            errors.append("steps must contain non-empty strings only")

    capabilities = skill_definition.get("capabilities", [])
    if not isinstance(capabilities, list) or not capabilities:
        errors.append("capabilities must be a non-empty list")
        capabilities = []
    forbidden_capabilities = sorted(
        capability for capability in capabilities
        if str(capability).strip().lower() in GENERATED_SKILL_FORBIDDEN_CAPABILITIES
    )
    if forbidden_capabilities:
        errors.append(
            f"forbidden capabilities detected: {', '.join(forbidden_capabilities)}"
        )
    unknown_capabilities = sorted(
        capability for capability in capabilities
        if str(capability).strip().lower() not in GENERATED_SKILL_ALLOWED_CAPABILITIES
        and str(capability).strip().lower() not in GENERATED_SKILL_FORBIDDEN_CAPABILITIES
    )
    if unknown_capabilities:
        warnings.append(
            f"unknown capabilities ignored: {', '.join(str(item) for item in unknown_capabilities)}"
        )

    joined_text = _collect_textual_fields(payload)
    for pattern in GENERATED_SKILL_FORBIDDEN_TEXT_PATTERNS:
        if re.search(pattern, joined_text):
            errors.append(f"forbidden sandbox text pattern detected: {pattern}")
            break

    if any(field in payload for field in ("python_code", "source_code", "implementation_code")):
        errors.append("embedded code fields are not allowed for generated skills")

    validation_passed = not errors
    validation_summary = (
        f"validated: {len(warnings)} warning(s)"
        if validation_passed
        else f"validation_failed: {len(errors)} error(s)"
    )
    return {
        "skill_id": payload.get("skill_id"),
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "validation_summary": validation_summary,
    }


def validate_generated_skill(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    payload = load_generated_skill_draft(skill_id, reference=reference)
    if payload is None:
        return {
            "skill_id": skill_id,
            "validation_passed": False,
            "validation_errors": ["generated skill draft not found"],
            "validation_warnings": [],
            "validation_summary": "validation_failed: draft_missing",
            "skill": None,
        }

    report = build_generated_skill_validation_report(payload)
    payload["validation_summary"] = report["validation_summary"]
    payload["last_validation_report"] = {
        "validated_at": _timestamp(),
        "validation_passed": report["validation_passed"],
        "validation_errors": report["validation_errors"],
        "validation_warnings": report["validation_warnings"],
    }
    payload["status"] = "validated" if report["validation_passed"] else "validation_failed"
    _persist_generated_skill_record(payload, reference=reference)
    return {
        **report,
        "skill": payload,
    }


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _scan_for_external_paths(value, sandbox_root: Path, problems: list[str], key_hint: str = "value") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan_for_external_paths(item, sandbox_root, problems, key_hint=str(key))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _scan_for_external_paths(item, sandbox_root, problems, key_hint=f"{key_hint}[{index}]")
        return
    if isinstance(value, Path):
        resolved = value.resolve()
        if not _is_relative_to(resolved, sandbox_root):
            problems.append(f"mock input path escapes sandbox: {key_hint}={resolved}")
        return
    if isinstance(value, str) and "path" in key_hint.lower():
        candidate = Path(value)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if not _is_relative_to(resolved, sandbox_root):
                problems.append(f"mock input path escapes sandbox: {key_hint}={resolved}")


def build_generated_skill_sandbox_context(
    *,
    sandbox_root: str | Path,
    execution_flags: dict | None = None,
    mock_inputs: dict | None = None,
) -> dict:
    gate = build_experimental_sandbox_gate(sandbox_root, flags=execution_flags)
    resolved_root = Path(gate["sandbox_root"])
    input_problems: list[str] = []
    _scan_for_external_paths(mock_inputs or {}, resolved_root, input_problems)
    return {
        "execution_mode": gate["execution_mode"],
        "experimental_gate": gate,
        "sandbox_root": str(resolved_root),
        "mock_inputs": mock_inputs or {},
        "mock_inputs_allowed": not input_problems,
        "mock_input_errors": input_problems,
    }


def _run_runtime_state_summarizer(mock_inputs: dict) -> dict:
    runtime_state = mock_inputs.get("runtime_state")
    if not isinstance(runtime_state, dict):
        raise ValueError("runtime_state input is required")
    markers = runtime_state.get("markers", [])
    lines = [
        f"transaction_id: {runtime_state.get('transaction_id', 'unknown')}",
        f"proposal_id: {runtime_state.get('proposal_id', 'none')}",
        f"execution_mode: {runtime_state.get('execution_mode', 'operational')}",
        f"state: {runtime_state.get('state', 'unknown')}",
        f"marker_count: {len(markers)}",
        f"terminal_marker: {runtime_state.get('terminal_marker') or 'none'}",
    ]
    return {
        "summary_lines": lines,
        "summary_text": "\n".join(lines),
        "output_summary": f"runtime state summarized with {len(markers)} marker(s)",
    }


def _run_proposal_summary_formatter(mock_inputs: dict) -> dict:
    proposal = mock_inputs.get("proposal")
    if not isinstance(proposal, dict):
        raise ValueError("proposal input is required")
    summary_text = (
        f"proposal_id={proposal.get('proposal_id', 'unknown')} "
        f"status={proposal.get('status', 'unknown')} "
        f"targets={len(proposal.get('target_paths', []))} "
        f"change_type={proposal.get('change_type', 'unknown')}"
    )
    return {
        "summary_text": summary_text,
        "output_summary": "proposal summary formatted",
    }


def _run_review_note_compactor(mock_inputs: dict) -> dict:
    notes = mock_inputs.get("review_notes")
    if not isinstance(notes, list):
        raise ValueError("review_notes input is required")
    compacted = []
    seen = set()
    for note in notes:
        normalized = " ".join(str(note).split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            compacted.append(normalized)
    return {
        "compacted_notes": compacted,
        "summary_text": " | ".join(compacted[:5]),
        "output_summary": f"review notes compacted from {len(notes)} to {len(compacted)}",
    }


def _run_diff_hint_reformatter(mock_inputs: dict) -> dict:
    diff_hints = mock_inputs.get("diff_hints")
    if not isinstance(diff_hints, list):
        raise ValueError("diff_hints input is required")
    normalized = []
    for item in diff_hints:
        if isinstance(item, dict):
            text = item.get("text") or item.get("path") or str(item)
        else:
            text = str(item)
        formatted = " ".join(text.split())
        if formatted:
            normalized.append(formatted)
    return {
        "normalized_diff_hints": normalized,
        "summary_text": "; ".join(normalized[:5]),
        "output_summary": f"diff hints reformatted: {len(normalized)} item(s)",
    }


GENERATED_SKILL_RUNNERS = {
    "runtime_state_summarizer": _run_runtime_state_summarizer,
    "proposal_summary_formatter": _run_proposal_summary_formatter,
    "review_note_compactor": _run_review_note_compactor,
    "diff_hint_reformatter": _run_diff_hint_reformatter,
}


def _save_generated_skill_result(result_payload: dict, *, reference: str | Path | None = None) -> dict:
    _ensure_generated_skill_directories(reference)
    path = _generated_skill_result_path(result_payload["run_id"], reference=reference)
    _write_json(path, result_payload)
    result_payload["path"] = str(path)
    return result_payload


def enqueue_generated_skill_for_manual_promotion(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    payload = load_generated_skill_draft(skill_id, reference=reference)
    if payload is None:
        return {
            "queued": False,
            "reason": "draft_missing",
            "queue_entry": None,
        }

    validation_report = payload.get("last_validation_report") or {}
    sandbox_report = payload.get("last_sandbox_result") or {}
    blockers = []
    if not validation_report.get("validation_passed"):
        blockers.append("validation_passed required")
    if sandbox_report.get("sandbox_result") != "passed":
        blockers.append("sandbox_passed required")
    if payload.get("sandbox_only") is not True:
        blockers.append("sandbox_only must remain true")
    if payload.get("promotion_required") is not True:
        blockers.append("promotion_required must remain true")

    if blockers:
        return {
            "queued": False,
            "reason": "queue_blocked",
            "queue_entry": None,
            "blockers": blockers,
        }

    queue_entry = {
        "skill_id": skill_id,
        "queued_at": _timestamp(),
        "purpose": payload.get("purpose", ""),
        "validation_summary": payload.get("validation_summary", "unknown"),
        "sandbox_result_summary": payload.get("sandbox_result_summary", "unknown"),
        "promotion_status": "pending_manual_review",
        "sandbox_only": True,
        "promotion_required": True,
        "promoted": False,
    }
    queue_path = _generated_skill_queue_path(skill_id, reference=reference)
    _write_json(queue_path, queue_entry)

    payload["status"] = "queued_for_manual_promotion"
    payload["last_queue_entry"] = {
        "queued_at": queue_entry["queued_at"],
        "promotion_status": queue_entry["promotion_status"],
        "promoted": False,
    }
    _persist_generated_skill_record(payload, reference=reference)
    return {
        "queued": True,
        "reason": "queued_for_manual_promotion",
        "queue_entry": {
            **queue_entry,
            "path": str(queue_path),
        },
        "skill": payload,
    }


def load_generated_skill_promotion_queue(
    *,
    reference: str | Path | None = None,
) -> list[dict]:
    queue_dir = _generated_skill_directories(reference)["generated_skill_queue"]
    if not queue_dir.exists():
        return []
    entries = []
    for path in sorted(queue_dir.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        payload["path"] = str(path)
        entries.append(payload)
    return entries


def list_generated_skill_queue(
    *,
    reference: str | Path | None = None,
) -> list[dict]:
    entries = load_generated_skill_promotion_queue(reference=reference)

    def _sort_key(item: dict) -> tuple[str, str]:
        return (
            str(item.get("queued_at") or item.get("created_at") or ""),
            str(item.get("skill_id") or ""),
        )

    return sorted(entries, key=_sort_key, reverse=True)


def load_generated_skill_queue_record(
    target: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    target = str(target).strip()
    if not target:
        return None

    for entry in list_generated_skill_queue(reference=reference):
        queue_path = Path(entry.get("path", ""))
        if target in {
            str(entry.get("skill_id", "")),
            queue_path.stem,
            queue_path.name,
        }:
            return entry
    return None


def build_generated_skill_queue_summary(
    record: dict,
    *,
    index: int | None = None,
) -> str:
    prefix = f"[{index}] " if index is not None else ""
    status = record.get("promotion_status", "unknown")
    skill_id = str(record.get("skill_id", "unknown"))
    skill_label = skill_id.rsplit("_", 1)[0] if "_" in skill_id else skill_id
    validation_summary = record.get("validation_summary", "unknown")
    sandbox_summary = record.get("sandbox_result_summary", "unknown")
    validation_label = "ok" if validation_summary.startswith("validated") else validation_summary
    sandbox_label = "passed" if sandbox_summary and sandbox_summary != "unknown" else "unknown"
    return (
        f"{prefix}{status} | {skill_label} | "
        f"validation: {validation_label} | sandbox: {sandbox_label}"
    )


def build_generated_skill_queue_report(
    target: str,
    *,
    reference: str | Path | None = None,
) -> str:
    record = load_generated_skill_queue_record(target, reference=reference)
    if record is None:
        return f"generated skill queue record not found: {target}"

    skill = load_generated_skill_draft(str(record.get("skill_id", "")), reference=reference) or {}
    validation = skill.get("last_validation_report") or {}
    sandbox = skill.get("last_sandbox_result") or {}
    sandbox_result = load_generated_skill_result(str(sandbox.get("run_id", "")), reference=reference) if sandbox.get("run_id") else None
    skill_definition = skill.get("skill_definition") or {}

    lines = [
        "[Skill]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- purpose: {record.get('purpose') or skill.get('purpose') or 'none'}",
        f"- status: {skill.get('status', 'unknown')}",
        f"- promotion_status: {record.get('promotion_status', 'unknown')}",
        "",
        "[Validation]",
        f"- validation_summary: {record.get('validation_summary') or skill.get('validation_summary') or 'unknown'}",
    ]

    errors = validation.get("validation_errors", [])
    warnings = validation.get("validation_warnings", [])
    if errors:
        lines.append(f"- validation_errors: {', '.join(str(item) for item in errors)}")
    if warnings:
        lines.append(f"- validation_warnings: {', '.join(str(item) for item in warnings)}")
    if not errors and not warnings:
        lines.append("- validation_notes: none")

    lines.extend(
        [
            "",
            "[Sandbox]",
            f"- sandbox_result_summary: {record.get('sandbox_result_summary') or skill.get('sandbox_result_summary') or 'unknown'}",
            f"- run_id: {sandbox.get('run_id') or 'none'}",
            f"- sandbox_result: {sandbox.get('sandbox_result') or 'unknown'}",
            f"- execution_mode: {(sandbox_result or {}).get('execution_mode') or sandbox.get('execution_mode') or 'unknown'}",
            "",
            "[Promotion Queue]",
            f"- queued_at: {record.get('queued_at') or 'unknown'}",
            f"- sandbox_only: {record.get('sandbox_only', skill.get('sandbox_only', False))}",
            f"- promotion_required: {record.get('promotion_required', skill.get('promotion_required', False))}",
            f"- promoted: {record.get('promoted', False)}",
        ]
    )

    notes = []
    if skill.get("generated_by"):
        notes.append(f"generated_by={skill.get('generated_by')}")
    if skill_definition.get("skill_kind"):
        notes.append(f"skill_kind={skill_definition.get('skill_kind')}")
    if skill_definition.get("capabilities"):
        notes.append("capabilities=" + ",".join(str(item) for item in skill_definition.get("capabilities", [])))
    queue_note = skill.get("last_queue_entry")
    if queue_note:
        notes.append(f"last_queue_status={queue_note.get('promotion_status', 'unknown')}")

    if notes:
        lines.extend(["", "[Notes]"])
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def validate_generated_skill_review_decision(payload: dict) -> dict:
    errors: list[str] = []
    normalized = dict(payload)

    skill_id = str(normalized.get("skill_id") or "").strip()
    if not skill_id:
        errors.append("skill_id is required")
    normalized["skill_id"] = skill_id

    decision = str(normalized.get("decision") or "").strip()
    if decision not in GENERATED_SKILL_REVIEW_DECISIONS:
        errors.append(
            "decision must be one of: approve_for_consideration, rejected, needs_followup"
        )
    normalized["decision"] = decision

    reviewer = str(normalized.get("reviewer") or "").strip()
    if not reviewer:
        errors.append("reviewer is required")
    normalized["reviewer"] = reviewer

    rationale = str(normalized.get("rationale") or "").strip()
    if not rationale:
        errors.append("rationale is required")
    normalized["rationale"] = rationale

    reviewed_at = str(normalized.get("reviewed_at") or "").strip()
    if not reviewed_at:
        errors.append("reviewed_at is required")
    normalized["reviewed_at"] = reviewed_at

    followup_required = normalized.get("followup_required")
    if not isinstance(followup_required, bool):
        errors.append("followup_required must be a bool")
    normalized["followup_required"] = bool(followup_required)

    notes = normalized.get("notes", [])
    if notes is None:
        notes = []
    if not isinstance(notes, list):
        errors.append("notes must be a list")
        notes = []
    normalized["notes"] = [str(note) for note in notes]

    validation_passed = not errors
    return {
        "skill_id": skill_id,
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_summary": (
            "review_decision_validated"
            if validation_passed
            else f"review_decision_failed: {len(errors)} error(s)"
        ),
        "normalized_payload": normalized,
    }


def save_generated_skill_review_decision(
    skill_id: str,
    *,
    decision: str,
    reviewer: str,
    rationale: str,
    followup_required: bool | None = None,
    notes: list[str] | None = None,
    reviewed_at: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    if load_generated_skill_draft(skill_id, reference=reference) is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    _ensure_generated_skill_directories(reference)
    path = _generated_skill_review_path(skill_id, reference=reference)
    if path.exists() and not allow_replace:
        raise ValueError(
            f"generated skill review decision already exists: {skill_id}; pass allow_replace=True to replace it"
        )

    if followup_required is None:
        followup_required = decision == "needs_followup"

    payload = {
        "skill_id": skill_id,
        "decision": decision,
        "reviewed_at": reviewed_at or _timestamp(),
        "reviewer": reviewer,
        "rationale": rationale,
        "followup_required": followup_required,
        "notes": list(notes or []),
    }
    report = validate_generated_skill_review_decision(payload)
    if not report["validation_passed"]:
        raise ValueError("; ".join(report["validation_errors"]))

    record = report["normalized_payload"]
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "review": record,
    }


def load_generated_skill_review_decision(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_review_path(skill_id, reference=reference))


def build_generated_skill_review_decision_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    record = load_generated_skill_review_decision(skill_id, reference=reference)
    if record is None:
        return f"generated skill review decision not found: {skill_id}"

    lines = [
        "[Review Decision]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- decision: {record.get('decision', 'unknown')}",
        f"- reviewed_at: {record.get('reviewed_at', 'unknown')}",
        f"- reviewer: {record.get('reviewer', 'unknown')}",
        f"- rationale: {record.get('rationale', 'none')}",
        f"- followup_required: {record.get('followup_required', False)}",
    ]

    notes = record.get("notes") or []
    lines.extend(["", "[Notes]"])
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _generated_skill_overwrite_risk(
    draft: dict,
    *,
    reference: str | Path | None = None,
) -> str:
    skill_definition = draft.get("skill_definition") or {}
    skill_name = str(skill_definition.get("name") or "").strip()
    if not skill_name:
        return "none"

    project_root = _generated_skill_directories(reference)["runtime_root"].parent
    production_skill_path = project_root / "skills" / skill_name
    return "high" if production_skill_path.exists() else "none"


def _build_generated_skill_promotion_assessment(
    *,
    draft: dict,
    queue_record: dict | None,
    review_decision: dict | None,
    overwrite_risk: str,
) -> dict:
    blockers: list[str] = []
    warnings: list[str] = []

    validation_report = draft.get("last_validation_report") or {}
    sandbox_result = draft.get("last_sandbox_result") or {}

    if draft.get("sandbox_only") is not True:
        blockers.append("sandbox_only must remain true")
    if draft.get("promotion_required") is not True:
        blockers.append("promotion_required must remain true")
    if queue_record is None:
        blockers.append("queue record missing")
    if not validation_report:
        blockers.append("validation report missing")
    elif not validation_report.get("validation_passed"):
        blockers.append("validation_passed required")
    if validation_report.get("validation_warnings"):
        warnings.extend(str(item) for item in validation_report.get("validation_warnings", []))
    if not sandbox_result.get("run_id"):
        blockers.append("sandbox result missing")
    elif sandbox_result.get("sandbox_result") != "passed":
        blockers.append("sandbox_passed required")
    if review_decision is None:
        blockers.append("review decision missing")
    else:
        if review_decision.get("decision") == "rejected":
            blockers.append("review decision rejected")
        elif review_decision.get("decision") == "needs_followup":
            blockers.append("review decision requires follow-up")
        elif review_decision.get("followup_required"):
            blockers.append("review follow-up still required")

    if overwrite_risk == "high":
        blockers.append("production skill name collision detected")

    return {
        "criteria_check_passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "overwrite_risk": overwrite_risk,
        "requires_manual_transform": True,
    }


def build_generated_skill_promotion_packet(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    draft = load_generated_skill_draft(skill_id, reference=reference)
    if draft is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    queue_record = load_generated_skill_queue_record(skill_id, reference=reference)
    review_decision = load_generated_skill_review_decision(skill_id, reference=reference)
    validation_report = draft.get("last_validation_report") or {}
    sandbox_snapshot = draft.get("last_sandbox_result") or {}
    sandbox_result = (
        load_generated_skill_result(str(sandbox_snapshot.get("run_id")), reference=reference)
        if sandbox_snapshot.get("run_id")
        else None
    )
    skill_definition = draft.get("skill_definition") or {}
    overwrite_risk = _generated_skill_overwrite_risk(draft, reference=reference)

    packet = {
        "skill_id": skill_id,
        "created_at": _timestamp(),
        "draft": {
            "purpose": draft.get("purpose", ""),
            "skill_kind": skill_definition.get("skill_kind", "unknown"),
            "capabilities": list(skill_definition.get("capabilities", [])),
            "sandbox_only": draft.get("sandbox_only", False),
            "promotion_required": draft.get("promotion_required", False),
        },
        "queue_record": {
            "status": draft.get("status", "unknown"),
            "promotion_status": (queue_record or {}).get("promotion_status", "missing"),
            "queued_at": (queue_record or {}).get("queued_at", "missing"),
        },
        "validation": {
            "summary": draft.get("validation_summary", "unknown"),
            "errors": list(validation_report.get("validation_errors", [])),
            "warnings": list(validation_report.get("validation_warnings", [])),
        },
        "sandbox": {
            "result": sandbox_snapshot.get("sandbox_result", "missing"),
            "summary": draft.get("sandbox_result_summary", "unknown"),
            "run_id": sandbox_snapshot.get("run_id", "missing"),
            "execution_mode": (sandbox_result or {}).get(
                "execution_mode",
                sandbox_snapshot.get("execution_mode", "unknown"),
            ),
        },
        "review_decision": {
            "decision": (review_decision or {}).get("decision", "missing"),
            "reviewer": (review_decision or {}).get("reviewer", "missing"),
            "reviewed_at": (review_decision or {}).get("reviewed_at", "missing"),
            "rationale": (review_decision or {}).get("rationale", "missing"),
            "followup_required": (review_decision or {}).get("followup_required", False),
            "notes": list((review_decision or {}).get("notes", [])),
        },
    }
    packet["promotion_assessment"] = _build_generated_skill_promotion_assessment(
        draft=draft,
        queue_record=queue_record,
        review_decision=review_decision,
        overwrite_risk=overwrite_risk,
    )
    return packet


def save_generated_skill_promotion_packet(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    _ensure_generated_skill_directories(reference)
    packet = build_generated_skill_promotion_packet(skill_id, reference=reference)
    path = _generated_skill_packet_path(skill_id, reference=reference)
    _write_json(path, packet)
    return {
        "saved": True,
        "path": str(path),
        "packet": packet,
    }


def load_generated_skill_promotion_packet(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_packet_path(skill_id, reference=reference))


def build_generated_skill_promotion_packet_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    packet = load_generated_skill_promotion_packet(skill_id, reference=reference)
    if packet is None:
        return f"generated skill promotion packet not found: {skill_id}"

    lines = [
        "[Skill]",
        f"- skill_id: {packet.get('skill_id', 'unknown')}",
        f"- purpose: {packet.get('draft', {}).get('purpose', 'unknown')}",
        f"- skill_kind: {packet.get('draft', {}).get('skill_kind', 'unknown')}",
        f"- capabilities: {', '.join(str(item) for item in packet.get('draft', {}).get('capabilities', [])) or 'none'}",
        f"- sandbox_only: {packet.get('draft', {}).get('sandbox_only', False)}",
        f"- promotion_required: {packet.get('draft', {}).get('promotion_required', False)}",
        "",
        "[Validation]",
        f"- summary: {packet.get('validation', {}).get('summary', 'unknown')}",
    ]

    validation_errors = packet.get("validation", {}).get("errors", [])
    validation_warnings = packet.get("validation", {}).get("warnings", [])
    lines.append(
        "- errors: "
        + (", ".join(str(item) for item in validation_errors) if validation_errors else "none")
    )
    lines.append(
        "- warnings: "
        + (", ".join(str(item) for item in validation_warnings) if validation_warnings else "none")
    )

    lines.extend(
        [
            "",
            "[Sandbox]",
            f"- result: {packet.get('sandbox', {}).get('result', 'unknown')}",
            f"- summary: {packet.get('sandbox', {}).get('summary', 'unknown')}",
            f"- run_id: {packet.get('sandbox', {}).get('run_id', 'unknown')}",
            f"- execution_mode: {packet.get('sandbox', {}).get('execution_mode', 'unknown')}",
            "",
            "[Review Decision]",
            f"- decision: {packet.get('review_decision', {}).get('decision', 'unknown')}",
            f"- reviewer: {packet.get('review_decision', {}).get('reviewer', 'unknown')}",
            f"- reviewed_at: {packet.get('review_decision', {}).get('reviewed_at', 'unknown')}",
            f"- rationale: {packet.get('review_decision', {}).get('rationale', 'unknown')}",
            f"- followup_required: {packet.get('review_decision', {}).get('followup_required', False)}",
            "",
            "[Promotion Assessment]",
            f"- criteria_check_passed: {packet.get('promotion_assessment', {}).get('criteria_check_passed', False)}",
            "- blockers: "
            + (
                ", ".join(str(item) for item in packet.get("promotion_assessment", {}).get("blockers", []))
                if packet.get("promotion_assessment", {}).get("blockers")
                else "none"
            ),
            "- warnings: "
            + (
                ", ".join(str(item) for item in packet.get("promotion_assessment", {}).get("warnings", []))
                if packet.get("promotion_assessment", {}).get("warnings")
                else "none"
            ),
            f"- overwrite_risk: {packet.get('promotion_assessment', {}).get('overwrite_risk', 'unknown')}",
            f"- requires_manual_transform: {packet.get('promotion_assessment', {}).get('requires_manual_transform', True)}",
        ]
    )
    return "\n".join(lines)


def build_generated_skill_transform_template(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    packet = load_generated_skill_promotion_packet(skill_id, reference=reference)
    if packet is None:
        raise ValueError(f"generated skill promotion packet not found: {skill_id}")

    draft = load_generated_skill_draft(skill_id, reference=reference)
    if draft is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    review_decision = load_generated_skill_review_decision(skill_id, reference=reference) or {}
    assessment = packet.get("promotion_assessment") or {}
    draft_section = packet.get("draft") or {}
    skill_definition = draft.get("skill_definition") or {}
    overwrite_risk = assessment.get("overwrite_risk", "unknown")
    naming_collision = overwrite_risk in {"low", "high"}
    build_warnings = []

    blockers = assessment.get("blockers", [])
    if blockers:
        build_warnings.append(
            "promotion packet blockers remain unresolved: " + ", ".join(str(item) for item in blockers)
        )
    if packet.get("review_decision", {}).get("decision") in {"missing", "rejected", "needs_followup"}:
        build_warnings.append("manual review decision is not promotion-candidate ready")
    if packet.get("validation", {}).get("summary", "").startswith("validation_failed"):
        build_warnings.append("validation must pass before manual transform can proceed")
    if packet.get("sandbox", {}).get("result") != "passed":
        build_warnings.append("sandbox result must be passed before manual transform can proceed")

    template = {
        "skill_id": skill_id,
        "created_at": _timestamp(),
        "source": {
            "generated_skill_id": skill_id,
            "packet_id": packet.get("skill_id", skill_id),
            "sandbox_validated": packet.get("sandbox", {}).get("result") == "passed",
        },
        "proposed_production": {
            "target_name": "",
            "target_path": "skills/<manual_target_name>.json",
            "skill_kind": draft_section.get("skill_kind", "unknown"),
            "capabilities": list(draft_section.get("capabilities", [])),
            "description": skill_definition.get("description", ""),
            "inputs": list(draft.get("allowed_inputs", [])),
            "outputs": list(draft.get("allowed_outputs", [])),
        },
        "transform_notes": {
            "required_manual_edits": [
                "choose a production-safe target_name",
                "replace the placeholder target_path",
                "refine the production description",
                "confirm allowed capabilities for production candidate",
                "review inputs and outputs for production contract",
            ],
            "removed_fields": [
                "sandbox_only",
                "promotion_required",
                "validation_summary",
                "sandbox_result_summary",
                "last_validation_report",
                "last_sandbox_result",
                "last_queue_entry",
            ],
            "adjusted_fields": [
                "target_name left blank for manual decision",
                "target_path uses a manual placeholder",
                "description copied from generated draft and requires human revision",
                "capabilities copied from sandbox draft and require confirmation",
                "inputs and outputs copied from sandbox draft and require normalization",
            ],
            "naming_decision": (
                "manual naming decision required"
                + ("; possible collision with an existing production skill" if naming_collision else "")
            ),
            "capability_review": "required before any production candidate is proposed",
            "security_review": "required",
        },
        "risk_checks": {
            "overwrite_risk": overwrite_risk,
            "naming_collision": naming_collision,
            "core_skill_conflict": overwrite_risk == "high",
        },
        "promotion_preconditions": {
            "review_decision_required": True,
            "manual_confirmation_required": True,
            "rollback_plan_required": True,
        },
        "build_warnings": build_warnings,
        "review_context": {
            "decision": review_decision.get("decision", "missing"),
            "reviewer": review_decision.get("reviewer", "missing"),
            "reviewed_at": review_decision.get("reviewed_at", "missing"),
        },
    }
    return template


def save_generated_skill_transform_template(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    _ensure_generated_skill_directories(reference)
    template = build_generated_skill_transform_template(skill_id, reference=reference)
    path = _generated_skill_transform_path(skill_id, reference=reference)
    _write_json(path, template)
    return {
        "saved": True,
        "path": str(path),
        "template": template,
    }


def load_generated_skill_transform_template(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_transform_path(skill_id, reference=reference))


def build_generated_skill_transform_template_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    template = load_generated_skill_transform_template(skill_id, reference=reference)
    if template is None:
        return f"generated skill transform template not found: {skill_id}"

    lines = [
        "[Source]",
        f"- generated_skill_id: {template.get('source', {}).get('generated_skill_id', 'unknown')}",
        f"- packet_id: {template.get('source', {}).get('packet_id', 'unknown')}",
        f"- sandbox_validated: {template.get('source', {}).get('sandbox_validated', False)}",
        "",
        "[Proposed Production]",
        f"- target_name: {template.get('proposed_production', {}).get('target_name', '') or '<manual>'}",
        f"- target_path: {template.get('proposed_production', {}).get('target_path', 'unknown')}",
        f"- skill_kind: {template.get('proposed_production', {}).get('skill_kind', 'unknown')}",
        f"- capabilities: {', '.join(str(item) for item in template.get('proposed_production', {}).get('capabilities', [])) or 'none'}",
        f"- description: {template.get('proposed_production', {}).get('description', 'none')}",
        f"- inputs: {', '.join(str(item) for item in template.get('proposed_production', {}).get('inputs', [])) or 'none'}",
        f"- outputs: {', '.join(str(item) for item in template.get('proposed_production', {}).get('outputs', [])) or 'none'}",
        "",
        "[Transform Notes]",
        "- required_manual_edits: "
        + ", ".join(str(item) for item in template.get("transform_notes", {}).get("required_manual_edits", [])),
        "- removed_fields: "
        + ", ".join(str(item) for item in template.get("transform_notes", {}).get("removed_fields", [])),
        "- adjusted_fields: "
        + ", ".join(str(item) for item in template.get("transform_notes", {}).get("adjusted_fields", [])),
        f"- naming_decision: {template.get('transform_notes', {}).get('naming_decision', 'unknown')}",
        f"- capability_review: {template.get('transform_notes', {}).get('capability_review', 'unknown')}",
        f"- security_review: {template.get('transform_notes', {}).get('security_review', 'unknown')}",
        "",
        "[Risk Checks]",
        f"- overwrite_risk: {template.get('risk_checks', {}).get('overwrite_risk', 'unknown')}",
        f"- naming_collision: {template.get('risk_checks', {}).get('naming_collision', False)}",
        f"- core_skill_conflict: {template.get('risk_checks', {}).get('core_skill_conflict', False)}",
        "",
        "[Promotion Preconditions]",
        f"- review_decision_required: {template.get('promotion_preconditions', {}).get('review_decision_required', False)}",
        f"- manual_confirmation_required: {template.get('promotion_preconditions', {}).get('manual_confirmation_required', False)}",
        f"- rollback_plan_required: {template.get('promotion_preconditions', {}).get('rollback_plan_required', False)}",
    ]

    build_warnings = template.get("build_warnings", [])
    if build_warnings:
        lines.extend(["", "[Build Warnings]"])
        for warning in build_warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines)


def validate_generated_skill_approval_record(payload: dict) -> dict:
    errors: list[str] = []
    normalized = dict(payload)

    skill_id = str(normalized.get("skill_id") or "").strip()
    if not skill_id:
        errors.append("skill_id is required")
    normalized["skill_id"] = skill_id

    approval_type = str(normalized.get("approval_type") or "").strip()
    if approval_type not in GENERATED_SKILL_APPROVAL_TYPES:
        errors.append("approval_type must be one of: promotion_approval, transform_approval")
    normalized["approval_type"] = approval_type

    decision = str(normalized.get("decision") or "").strip()
    if decision not in GENERATED_SKILL_APPROVAL_DECISIONS:
        errors.append("decision must be one of: approved, rejected, needs_followup")
    normalized["decision"] = decision

    approved_at = str(normalized.get("approved_at") or "").strip()
    if not approved_at:
        errors.append("approved_at is required")
    normalized["approved_at"] = approved_at

    approver = str(normalized.get("approver") or "").strip()
    if not approver:
        errors.append("approver is required")
    normalized["approver"] = approver

    rationale = str(normalized.get("rationale") or "").strip()
    if not rationale:
        errors.append("rationale is required")
    normalized["rationale"] = rationale

    followup_required = normalized.get("followup_required")
    if not isinstance(followup_required, bool):
        errors.append("followup_required must be a bool")
    normalized["followup_required"] = bool(followup_required)

    notes = normalized.get("notes", [])
    if notes is None:
        notes = []
    if not isinstance(notes, list):
        errors.append("notes must be a list")
        notes = []
    normalized["notes"] = [str(note) for note in notes]

    source_review_decision = str(normalized.get("source_review_decision") or "").strip()
    if not source_review_decision:
        errors.append("source_review_decision is required")
    normalized["source_review_decision"] = source_review_decision

    source_packet_id = str(normalized.get("source_packet_id") or "").strip()
    if not source_packet_id:
        errors.append("source_packet_id is required")
    normalized["source_packet_id"] = source_packet_id

    source_transform_template = normalized.get("source_transform_template")
    if source_transform_template is None:
        source_transform_template = None
    elif str(source_transform_template).strip():
        source_transform_template = str(source_transform_template).strip()
    else:
        source_transform_template = None
    if approval_type == "transform_approval" and not source_transform_template:
        errors.append("source_transform_template is required for transform_approval")
    normalized["source_transform_template"] = source_transform_template

    final_target_name = normalized.get("final_target_name")
    if final_target_name is None:
        final_target_name = None
    elif str(final_target_name).strip():
        final_target_name = str(final_target_name).strip()
    else:
        final_target_name = None
    normalized["final_target_name"] = final_target_name

    final_target_path = normalized.get("final_target_path")
    if final_target_path is None:
        final_target_path = None
    elif str(final_target_path).strip():
        final_target_path = str(final_target_path).strip()
    else:
        final_target_path = None
    normalized["final_target_path"] = final_target_path

    if decision == "approved":
        if not final_target_name:
            errors.append("final_target_name is required when decision=approved")
        if not final_target_path:
            errors.append("final_target_path is required when decision=approved")

    rollback_reference = normalized.get("rollback_reference")
    if rollback_reference is None:
        rollback_reference = None
    elif str(rollback_reference).strip():
        rollback_reference = str(rollback_reference).strip()
    else:
        rollback_reference = None
    normalized["rollback_reference"] = rollback_reference

    validation_passed = not errors
    return {
        "skill_id": skill_id,
        "approval_type": approval_type,
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_summary": (
            "approval_record_validated"
            if validation_passed
            else f"approval_record_failed: {len(errors)} error(s)"
        ),
        "normalized_payload": normalized,
    }


def save_generated_skill_approval_record(
    skill_id: str,
    *,
    approval_type: str,
    decision: str,
    approver: str,
    rationale: str,
    followup_required: bool | None = None,
    notes: list[str] | None = None,
    approved_at: str | None = None,
    final_target_name: str | None = None,
    final_target_path: str | None = None,
    rollback_reference: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    if load_generated_skill_draft(skill_id, reference=reference) is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    review_decision = load_generated_skill_review_decision(skill_id, reference=reference)
    if review_decision is None:
        raise ValueError(f"generated skill review decision not found: {skill_id}")

    packet = load_generated_skill_promotion_packet(skill_id, reference=reference)
    if packet is None:
        raise ValueError(f"generated skill promotion packet not found: {skill_id}")

    transform_template = load_generated_skill_transform_template(skill_id, reference=reference)
    if approval_type == "transform_approval" and transform_template is None:
        raise ValueError(f"generated skill transform template not found: {skill_id}")

    _ensure_generated_skill_directories(reference)
    path = _generated_skill_approval_path(skill_id, reference=reference)
    existing = _read_json(path) or {"skill_id": skill_id, "records": {}}
    records = dict(existing.get("records") or {})
    if approval_type in records and not allow_replace:
        raise ValueError(
            f"generated skill approval record already exists for {approval_type}: {skill_id}; pass allow_replace=True to replace it"
        )

    if followup_required is None:
        followup_required = decision == "needs_followup"

    payload = {
        "skill_id": skill_id,
        "approval_type": approval_type,
        "decision": decision,
        "approved_at": approved_at or _timestamp(),
        "approver": approver,
        "rationale": rationale,
        "followup_required": followup_required,
        "notes": list(notes or []),
        "source_review_decision": review_decision.get("decision"),
        "source_packet_id": f"{packet.get('skill_id', skill_id)}.packet",
        "source_transform_template": (
            f"{transform_template.get('skill_id', skill_id)}.transform"
            if transform_template is not None
            else None
        ),
        "final_target_name": final_target_name,
        "final_target_path": final_target_path,
        "rollback_reference": rollback_reference,
    }
    report = validate_generated_skill_approval_record(payload)
    if not report["validation_passed"]:
        raise ValueError("; ".join(report["validation_errors"]))

    record = report["normalized_payload"]
    records[approval_type] = record
    file_payload = {
        "skill_id": skill_id,
        "updated_at": _timestamp(),
        "records": records,
    }
    _write_json(path, file_payload)
    return {
        "saved": True,
        "path": str(path),
        "approval": record,
        "approval_file": file_payload,
    }


def load_generated_skill_approval_record(
    skill_id: str,
    *,
    approval_type: str | None = None,
    reference: str | Path | None = None,
) -> dict | None:
    payload = _read_json(_generated_skill_approval_path(skill_id, reference=reference))
    if payload is None:
        return None
    if approval_type is None:
        return payload
    return (payload.get("records") or {}).get(approval_type)


def _build_generated_skill_approval_entry_report(record: dict) -> str:
    lines = [
        "[Approval]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- approval_type: {record.get('approval_type', 'unknown')}",
        f"- decision: {record.get('decision', 'unknown')}",
        f"- approved_at: {record.get('approved_at', 'unknown')}",
        f"- approver: {record.get('approver', 'unknown')}",
        "",
        "[Source]",
        f"- source_review_decision: {record.get('source_review_decision') or 'none'}",
        f"- source_packet_id: {record.get('source_packet_id') or 'none'}",
        f"- source_transform_template: {record.get('source_transform_template') or 'none'}",
        "",
        "[Target]",
        f"- final_target_name: {record.get('final_target_name') or 'none'}",
        f"- final_target_path: {record.get('final_target_path') or 'none'}",
        "",
        "[Rationale]",
        f"- rationale: {record.get('rationale') or 'none'}",
        f"- followup_required: {record.get('followup_required', False)}",
        "- notes: "
        + (
            ", ".join(str(item) for item in record.get("notes", []))
            if record.get("notes")
            else "none"
        ),
        "",
        "[Rollback]",
        f"- rollback_reference: {record.get('rollback_reference') or 'none'}",
    ]
    return "\n".join(lines)


def build_generated_skill_approval_report(
    skill_id: str,
    *,
    approval_type: str | None = None,
    reference: str | Path | None = None,
) -> str:
    payload = load_generated_skill_approval_record(skill_id, reference=reference)
    if payload is None:
        return f"generated skill approval record not found: {skill_id}"

    if approval_type is not None:
        record = (payload.get("records") or {}).get(approval_type)
        if record is None:
            return f"generated skill approval record not found: {skill_id}"
        return _build_generated_skill_approval_entry_report(record)

    records = payload.get("records") or {}
    if not records:
        return f"generated skill approval record not found: {skill_id}"
    return "\n\n".join(
        _build_generated_skill_approval_entry_report(records[key])
        for key in sorted(records)
    )


def validate_generated_skill_candidate_checklist(payload: dict) -> dict:
    errors: list[str] = []
    normalized = dict(payload)

    skill_id = str(normalized.get("skill_id") or "").strip()
    if not skill_id:
        errors.append("skill_id is required")
    normalized["skill_id"] = skill_id

    checked_at = str(normalized.get("checked_at") or "").strip()
    if not checked_at:
        errors.append("checked_at is required")
    normalized["checked_at"] = checked_at

    operator = str(normalized.get("operator") or "").strip()
    if not operator:
        errors.append("operator is required")
    normalized["operator"] = operator

    for field in GENERATED_SKILL_CHECKLIST_BOOL_FIELDS:
        value = normalized.get(field)
        if not isinstance(value, bool):
            errors.append(f"{field} must be a bool")
        normalized[field] = bool(value)

    source_review_record = str(normalized.get("source_review_record") or "").strip()
    if not source_review_record:
        errors.append("source_review_record is required")
    normalized["source_review_record"] = source_review_record

    source_approval_record = str(normalized.get("source_approval_record") or "").strip()
    if not source_approval_record:
        errors.append("source_approval_record is required")
    normalized["source_approval_record"] = source_approval_record

    source_transform_template = str(normalized.get("source_transform_template") or "").strip()
    if not source_transform_template:
        errors.append("source_transform_template is required")
    normalized["source_transform_template"] = source_transform_template

    target_name = str(normalized.get("target_name") or "").strip()
    if not target_name:
        errors.append("target_name is required")
    normalized["target_name"] = target_name

    target_path = str(normalized.get("target_path") or "").strip()
    if not target_path:
        errors.append("target_path is required")
    normalized["target_path"] = target_path

    notes = normalized.get("notes", [])
    if notes is None:
        notes = []
    if not isinstance(notes, list):
        errors.append("notes must be a list")
        notes = []
    normalized["notes"] = [str(note) for note in notes]

    expected_all_checks_passed = all(bool(normalized.get(field)) for field in GENERATED_SKILL_CHECKLIST_BOOL_FIELDS)
    normalized["all_checks_passed"] = expected_all_checks_passed

    validation_passed = not errors
    return {
        "skill_id": skill_id,
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_summary": (
            "candidate_checklist_validated"
            if validation_passed
            else f"candidate_checklist_failed: {len(errors)} error(s)"
        ),
        "normalized_payload": normalized,
    }


def save_generated_skill_candidate_checklist(
    skill_id: str,
    *,
    operator: str,
    review_decision_exists: bool,
    approval_record_exists: bool,
    validation_passed: bool,
    sandbox_passed: bool,
    sandbox_only_confirmed: bool,
    promotion_required_confirmed: bool,
    generated_only_fields_removed: bool,
    target_name_manually_chosen: bool,
    naming_collision_resolved: bool,
    core_skill_overwrite_absent: bool,
    rollback_reference_prepared: bool,
    direct_move_not_used: bool,
    target_name: str,
    target_path: str,
    notes: list[str] | None = None,
    checked_at: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    if load_generated_skill_draft(skill_id, reference=reference) is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    review_record = load_generated_skill_review_decision(skill_id, reference=reference)
    if review_record is None:
        raise ValueError(f"generated skill review decision not found: {skill_id}")

    approval_record = load_generated_skill_approval_record(skill_id, reference=reference)
    if approval_record is None:
        raise ValueError(f"generated skill approval record not found: {skill_id}")

    transform_template = load_generated_skill_transform_template(skill_id, reference=reference)
    if transform_template is None:
        raise ValueError(f"generated skill transform template not found: {skill_id}")

    _ensure_generated_skill_directories(reference)
    path = _generated_skill_checklist_path(skill_id, reference=reference)
    if path.exists() and not allow_replace:
        raise ValueError(
            f"generated skill candidate checklist already exists: {skill_id}; pass allow_replace=True to replace it"
        )

    bool_values = {
        "review_decision_exists": review_decision_exists,
        "approval_record_exists": approval_record_exists,
        "validation_passed": validation_passed,
        "sandbox_passed": sandbox_passed,
        "sandbox_only_confirmed": sandbox_only_confirmed,
        "promotion_required_confirmed": promotion_required_confirmed,
        "generated_only_fields_removed": generated_only_fields_removed,
        "target_name_manually_chosen": target_name_manually_chosen,
        "naming_collision_resolved": naming_collision_resolved,
        "core_skill_overwrite_absent": core_skill_overwrite_absent,
        "rollback_reference_prepared": rollback_reference_prepared,
        "direct_move_not_used": direct_move_not_used,
    }
    payload = {
        "skill_id": skill_id,
        "checked_at": checked_at or _timestamp(),
        "operator": operator,
        **bool_values,
        "source_review_record": f"{review_record.get('skill_id', skill_id)}.review",
        "source_approval_record": f"{skill_id}.approval",
        "source_transform_template": f"{transform_template.get('skill_id', skill_id)}.transform",
        "target_name": target_name,
        "target_path": target_path,
        "notes": list(notes or []),
        "all_checks_passed": all(bool_values.values()),
    }
    report = validate_generated_skill_candidate_checklist(payload)
    if not report["validation_passed"]:
        raise ValueError("; ".join(report["validation_errors"]))

    record = report["normalized_payload"]
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "checklist": record,
    }


def load_generated_skill_candidate_checklist(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_checklist_path(skill_id, reference=reference))


def build_generated_skill_candidate_checklist_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    record = load_generated_skill_candidate_checklist(skill_id, reference=reference)
    if record is None:
        return f"generated skill candidate checklist not found: {skill_id}"

    lines = [
        "[Checklist]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- checked_at: {record.get('checked_at', 'unknown')}",
        f"- operator: {record.get('operator', 'unknown')}",
        f"- all_checks_passed: {record.get('all_checks_passed', False)}",
        "",
        "[Checks]",
    ]
    for field in GENERATED_SKILL_CHECKLIST_BOOL_FIELDS:
        lines.append(f"- {field}: {record.get(field, False)}")
    lines.extend(
        [
            "",
            "[Target]",
            f"- target_name: {record.get('target_name', 'none')}",
            f"- target_path: {record.get('target_path', 'none')}",
            "",
            "[Sources]",
            f"- source_review_record: {record.get('source_review_record') or 'none'}",
            f"- source_approval_record: {record.get('source_approval_record') or 'none'}",
            f"- source_transform_template: {record.get('source_transform_template') or 'none'}",
            "",
            "[Notes]",
        ]
    )
    notes = record.get("notes") or []
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def validate_generated_skill_rollback_record(payload: dict) -> dict:
    errors: list[str] = []
    normalized = dict(payload)

    skill_id = str(normalized.get("skill_id") or "").strip()
    if not skill_id:
        errors.append("skill_id is required")
    normalized["skill_id"] = skill_id

    rolled_back_at = str(normalized.get("rolled_back_at") or "").strip()
    if not rolled_back_at:
        errors.append("rolled_back_at is required")
    normalized["rolled_back_at"] = rolled_back_at

    operator = str(normalized.get("operator") or "").strip()
    if not operator:
        errors.append("operator is required")
    normalized["operator"] = operator

    reason = str(normalized.get("reason") or "").strip()
    if not reason:
        errors.append("reason is required")
    normalized["reason"] = reason

    production_artifact_ref = str(normalized.get("production_artifact_ref") or "").strip()
    if not production_artifact_ref:
        errors.append("production_artifact_ref is required")
    normalized["production_artifact_ref"] = production_artifact_ref

    review_record_ref = str(normalized.get("review_record_ref") or "").strip()
    if not review_record_ref:
        errors.append("review_record_ref is required")
    normalized["review_record_ref"] = review_record_ref

    approval_record_ref = str(normalized.get("approval_record_ref") or "").strip()
    if not approval_record_ref:
        errors.append("approval_record_ref is required")
    normalized["approval_record_ref"] = approval_record_ref

    transform_template_ref = str(normalized.get("transform_template_ref") or "").strip()
    if not transform_template_ref:
        errors.append("transform_template_ref is required")
    normalized["transform_template_ref"] = transform_template_ref

    candidate_artifact_ref = str(normalized.get("candidate_artifact_ref") or "").strip()
    if not candidate_artifact_ref:
        errors.append("candidate_artifact_ref is required")
    normalized["candidate_artifact_ref"] = candidate_artifact_ref

    normalized["rollback_reference"] = _normalize_optional_text(normalized.get("rollback_reference"))

    notes = normalized.get("notes", [])
    if notes is None:
        notes = []
    if not isinstance(notes, list):
        errors.append("notes must be a list")
        notes = []
    normalized["notes"] = [str(note) for note in notes]

    validation_passed = not errors
    return {
        "skill_id": skill_id,
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_summary": (
            "rollback_record_validated"
            if validation_passed
            else f"rollback_record_failed: {len(errors)} error(s)"
        ),
        "normalized_payload": normalized,
    }


def save_generated_skill_rollback_record(
    skill_id: str,
    *,
    operator: str,
    reason: str,
    production_artifact_ref: str,
    candidate_artifact_ref: str,
    rollback_reference: str | None = None,
    notes: list[str] | None = None,
    rolled_back_at: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    if load_generated_skill_draft(skill_id, reference=reference) is None:
        raise ValueError(f"generated skill draft not found: {skill_id}")

    review_record = load_generated_skill_review_decision(skill_id, reference=reference)
    if review_record is None:
        raise ValueError(f"generated skill review decision not found: {skill_id}")

    approval_record = load_generated_skill_approval_record(skill_id, reference=reference)
    if approval_record is None:
        raise ValueError(f"generated skill approval record not found: {skill_id}")

    transform_template = load_generated_skill_transform_template(skill_id, reference=reference)
    if transform_template is None:
        raise ValueError(f"generated skill transform template not found: {skill_id}")

    _ensure_generated_skill_directories(reference)
    path = _generated_skill_rollback_path(skill_id, reference=reference)
    if path.exists() and not allow_replace:
        raise ValueError(
            f"generated skill rollback record already exists: {skill_id}; pass allow_replace=True to replace it"
        )

    payload = {
        "skill_id": skill_id,
        "rolled_back_at": rolled_back_at or _timestamp(),
        "operator": operator,
        "reason": reason,
        "production_artifact_ref": production_artifact_ref,
        "review_record_ref": f"{review_record.get('skill_id', skill_id)}.review",
        "approval_record_ref": f"{skill_id}.approval",
        "transform_template_ref": f"{transform_template.get('skill_id', skill_id)}.transform",
        "candidate_artifact_ref": candidate_artifact_ref,
        "rollback_reference": rollback_reference,
        "notes": list(notes or []),
    }
    report = validate_generated_skill_rollback_record(payload)
    if not report["validation_passed"]:
        raise ValueError("; ".join(report["validation_errors"]))

    record = report["normalized_payload"]
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "rollback": record,
    }


def load_generated_skill_rollback_record(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_rollback_path(skill_id, reference=reference))


def build_generated_skill_rollback_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    record = load_generated_skill_rollback_record(skill_id, reference=reference)
    if record is None:
        return f"generated skill rollback record not found: {skill_id}"

    lines = [
        "[Rollback]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- rolled_back_at: {record.get('rolled_back_at', 'unknown')}",
        f"- operator: {record.get('operator', 'unknown')}",
        f"- reason: {record.get('reason', 'none')}",
        f"- rollback_reference: {record.get('rollback_reference') or 'none'}",
        "",
        "[Source]",
        f"- review_record_ref: {record.get('review_record_ref') or 'none'}",
        f"- approval_record_ref: {record.get('approval_record_ref') or 'none'}",
        f"- transform_template_ref: {record.get('transform_template_ref') or 'none'}",
        f"- candidate_artifact_ref: {record.get('candidate_artifact_ref') or 'none'}",
        "",
        "[Production Artifact]",
        f"- production_artifact_ref: {record.get('production_artifact_ref') or 'none'}",
        "",
        "[Notes]",
    ]
    notes = record.get("notes") or []
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _select_generated_skill_approval_entry(approval_payload: dict | None) -> dict | None:
    records = (approval_payload or {}).get("records") or {}
    for approval_type in ("transform_approval", "promotion_approval"):
        record = records.get(approval_type)
        if record:
            return record
    for record in records.values():
        return record
    return None


def build_generated_skill_manual_promotion_readiness(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    draft = load_generated_skill_draft(skill_id, reference=reference)
    review_record = load_generated_skill_review_decision(skill_id, reference=reference)
    approval_payload = load_generated_skill_approval_record(skill_id, reference=reference)
    approval_record = _select_generated_skill_approval_entry(approval_payload)
    checklist = load_generated_skill_candidate_checklist(skill_id, reference=reference)
    transform_template = load_generated_skill_transform_template(skill_id, reference=reference)

    blockers: list[str] = []
    warnings: list[str] = []

    if draft is None:
        blockers.append("generated skill draft not found")
    if review_record is None:
        blockers.append("review decision missing")
    if approval_payload is None or approval_record is None:
        blockers.append("approval record missing")
    elif approval_record.get("decision") != "approved":
        blockers.append("approved approval record required")
    if checklist is None:
        blockers.append("candidate checklist missing")
    else:
        if checklist.get("all_checks_passed") is not True:
            blockers.append("checklist.all_checks_passed must be true")
        if not checklist.get("target_name"):
            blockers.append("target_name is required")
        if not checklist.get("target_path"):
            blockers.append("target_path is required")
        if checklist.get("naming_collision_resolved") is not True:
            blockers.append("naming_collision_resolved must be true")
        if checklist.get("direct_move_not_used") is not True:
            blockers.append("direct_move_not_used must be true")
        if checklist.get("rollback_reference_prepared") is not True:
            blockers.append("rollback_reference_prepared must be true")
    if transform_template is None:
        blockers.append("transform template missing")
    else:
        if transform_template.get("build_warnings"):
            warnings.extend(str(item) for item in transform_template.get("build_warnings", []))

    if approval_record and approval_record.get("followup_required"):
        warnings.append("approval record still indicates follow-up required")
    if review_record and review_record.get("followup_required"):
        warnings.append("review decision still indicates follow-up required")

    return {
        "skill_id": skill_id,
        "can_execute": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "review_record": review_record,
        "approval_payload": approval_payload,
        "approval_record": approval_record,
        "checklist": checklist,
        "transform_template": transform_template,
    }


def _build_generated_skill_candidate_payload(
    skill_id: str,
    *,
    transform_template: dict,
    approval_record: dict,
    checklist: dict,
    operator: str,
    generated_at: str,
    extra_notes: list[str] | None = None,
) -> dict:
    proposed = transform_template.get("proposed_production") or {}
    notes = []
    notes.extend(str(item) for item in checklist.get("notes", []))
    notes.extend(str(item) for item in approval_record.get("notes", []))
    notes.extend(str(item) for item in (extra_notes or []))

    unique_notes: list[str] = []
    seen_notes: set[str] = set()
    for note in notes:
        if note in seen_notes:
            continue
        seen_notes.add(note)
        unique_notes.append(note)

    return {
        "skill_id": skill_id,
        "target_name": checklist.get("target_name"),
        "target_path": checklist.get("target_path"),
        "reviewed_description": proposed.get("description", ""),
        "reviewed_capabilities": list(proposed.get("capabilities", [])),
        "reviewed_inputs": list(proposed.get("inputs", [])),
        "reviewed_outputs": list(proposed.get("outputs", [])),
        "source_packet_id": approval_record.get("source_packet_id") or f"{skill_id}.packet",
        "source_transform_template": approval_record.get("source_transform_template") or f"{skill_id}.transform",
        "source_approval_record": f"{skill_id}.approval",
        "manual_transform_completed_by": operator,
        "manual_transform_completed_at": generated_at,
        "overwrite_risk": (transform_template.get("risk_checks") or {}).get("overwrite_risk", "unknown"),
        "rollback_reference": approval_record.get("rollback_reference") or None,
        "notes": unique_notes,
    }


def build_generated_skill_candidate(
    skill_id: str,
    *,
    operator: str,
    notes: list[str] | None = None,
    generated_at: str | None = None,
    reference: str | Path | None = None,
) -> dict:
    readiness = build_generated_skill_manual_promotion_readiness(skill_id, reference=reference)
    if not readiness["can_execute"]:
        raise ValueError("; ".join(readiness["blockers"]))

    return _build_generated_skill_candidate_payload(
        skill_id,
        transform_template=readiness["transform_template"],
        approval_record=readiness["approval_record"],
        checklist=readiness["checklist"],
        operator=operator,
        generated_at=generated_at or _timestamp(),
        extra_notes=notes,
    )


def save_generated_skill_candidate(
    skill_id: str,
    *,
    operator: str,
    notes: list[str] | None = None,
    generated_at: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    _ensure_generated_skill_directories(reference)
    path = _generated_skill_candidate_path(skill_id, reference=reference)
    if path.exists() and not allow_replace:
        raise ValueError(
            f"generated skill candidate artifact already exists: {skill_id}; pass allow_replace=True to replace it"
        )

    candidate = build_generated_skill_candidate(
        skill_id,
        operator=operator,
        notes=notes,
        generated_at=generated_at,
        reference=reference,
    )
    _write_json(path, candidate)
    return {
        "saved": True,
        "path": str(path),
        "candidate": candidate,
    }


def load_generated_skill_candidate(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_candidate_path(skill_id, reference=reference))


def validate_generated_skill_promotion_record(payload: dict) -> dict:
    errors: list[str] = []
    normalized = dict(payload)

    skill_id = str(normalized.get("skill_id") or "").strip()
    if not skill_id:
        errors.append("skill_id is required")
    normalized["skill_id"] = skill_id

    promoted_at = str(normalized.get("promoted_at") or "").strip()
    if not promoted_at:
        errors.append("promoted_at is required")
    normalized["promoted_at"] = promoted_at

    operator = str(normalized.get("operator") or "").strip()
    if not operator:
        errors.append("operator is required")
    normalized["operator"] = operator

    decision = str(normalized.get("decision") or "").strip()
    if decision != "executed":
        errors.append("decision must be executed")
    normalized["decision"] = decision

    for field in (
        "source_review_record",
        "source_approval_record",
        "source_checklist_record",
        "source_transform_template",
        "source_candidate_artifact",
        "final_target_name",
        "final_target_path",
    ):
        value = str(normalized.get(field) or "").strip()
        if not value:
            errors.append(f"{field} is required")
        normalized[field] = value

    notes = normalized.get("notes", [])
    if notes is None:
        notes = []
    if not isinstance(notes, list):
        errors.append("notes must be a list")
        notes = []
    normalized["notes"] = [str(note) for note in notes]

    validation_passed = not errors
    return {
        "skill_id": skill_id,
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_summary": (
            "promotion_record_validated"
            if validation_passed
            else f"promotion_record_failed: {len(errors)} error(s)"
        ),
        "normalized_payload": normalized,
    }


def save_generated_skill_promotion_record(
    skill_id: str,
    *,
    operator: str,
    source_candidate_artifact: str,
    final_target_name: str,
    final_target_path: str,
    notes: list[str] | None = None,
    promoted_at: str | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    review_record = load_generated_skill_review_decision(skill_id, reference=reference)
    if review_record is None:
        raise ValueError(f"generated skill review decision not found: {skill_id}")

    approval_payload = load_generated_skill_approval_record(skill_id, reference=reference)
    if approval_payload is None:
        raise ValueError(f"generated skill approval record not found: {skill_id}")

    checklist = load_generated_skill_candidate_checklist(skill_id, reference=reference)
    if checklist is None:
        raise ValueError(f"generated skill candidate checklist not found: {skill_id}")

    transform_template = load_generated_skill_transform_template(skill_id, reference=reference)
    if transform_template is None:
        raise ValueError(f"generated skill transform template not found: {skill_id}")

    _ensure_generated_skill_directories(reference)
    path = _generated_skill_promotion_path(skill_id, reference=reference)
    if path.exists() and not allow_replace:
        raise ValueError(
            f"generated skill promotion record already exists: {skill_id}; pass allow_replace=True to replace it"
        )

    payload = {
        "skill_id": skill_id,
        "promoted_at": promoted_at or _timestamp(),
        "operator": operator,
        "decision": "executed",
        "source_review_record": f"{review_record.get('skill_id', skill_id)}.review",
        "source_approval_record": f"{skill_id}.approval",
        "source_checklist_record": f"{skill_id}.checklist",
        "source_transform_template": f"{transform_template.get('skill_id', skill_id)}.transform",
        "source_candidate_artifact": source_candidate_artifact,
        "final_target_name": final_target_name,
        "final_target_path": final_target_path,
        "notes": list(notes or []),
    }
    report = validate_generated_skill_promotion_record(payload)
    if not report["validation_passed"]:
        raise ValueError("; ".join(report["validation_errors"]))

    record = report["normalized_payload"]
    _write_json(path, record)
    return {
        "saved": True,
        "path": str(path),
        "promotion": record,
    }


def load_generated_skill_promotion_record(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return _read_json(_generated_skill_promotion_path(skill_id, reference=reference))


def build_generated_skill_manual_promotion_preview(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> dict:
    readiness = build_generated_skill_manual_promotion_readiness(skill_id, reference=reference)
    candidate_preview = None
    if (
        readiness["transform_template"] is not None
        and readiness["approval_record"] is not None
        and readiness["checklist"] is not None
    ):
        candidate_preview = _build_generated_skill_candidate_payload(
            skill_id,
            transform_template=readiness["transform_template"],
            approval_record=readiness["approval_record"],
            checklist=readiness["checklist"],
            operator=(readiness["approval_record"].get("approver") or readiness["checklist"].get("operator") or "preview"),
            generated_at=_timestamp(),
            extra_notes=[],
        )

    return {
        "skill_id": skill_id,
        "can_execute": readiness["can_execute"],
        "blockers": list(readiness["blockers"]),
        "warnings": list(readiness["warnings"]),
        "candidate_preview": candidate_preview,
    }


def build_generated_skill_manual_promotion_preview_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    preview = build_generated_skill_manual_promotion_preview(skill_id, reference=reference)
    lines = [
        "[Promotion Readiness]",
        f"- skill_id: {preview['skill_id']}",
        f"- can_execute: {preview['can_execute']}",
        "- blockers: " + (", ".join(preview["blockers"]) if preview["blockers"] else "none"),
        "- warnings: " + (", ".join(preview["warnings"]) if preview["warnings"] else "none"),
        "",
        "[Candidate Preview]",
    ]
    candidate = preview.get("candidate_preview")
    if candidate is None:
        lines.append("- status: not available")
    else:
        lines.extend(
            [
                f"- target_name: {candidate.get('target_name', 'none')}",
                f"- target_path: {candidate.get('target_path', 'none')}",
                f"- reviewed_description: {candidate.get('reviewed_description', 'none') or 'none'}",
                f"- reviewed_capabilities: {', '.join(str(item) for item in candidate.get('reviewed_capabilities', [])) or 'none'}",
                f"- reviewed_inputs: {', '.join(str(item) for item in candidate.get('reviewed_inputs', [])) or 'none'}",
                f"- reviewed_outputs: {', '.join(str(item) for item in candidate.get('reviewed_outputs', [])) or 'none'}",
                f"- overwrite_risk: {candidate.get('overwrite_risk', 'unknown')}",
                f"- rollback_reference: {candidate.get('rollback_reference') or 'none'}",
            ]
        )
    return "\n".join(lines)


def build_generated_skill_promotion_record_report(
    skill_id: str,
    *,
    reference: str | Path | None = None,
) -> str:
    record = load_generated_skill_promotion_record(skill_id, reference=reference)
    if record is None:
        return f"generated skill promotion record not found: {skill_id}"

    lines = [
        "[Promotion]",
        f"- skill_id: {record.get('skill_id', 'unknown')}",
        f"- promoted_at: {record.get('promoted_at', 'unknown')}",
        f"- operator: {record.get('operator', 'unknown')}",
        f"- decision: {record.get('decision', 'unknown')}",
        "",
        "[Sources]",
        f"- source_review_record: {record.get('source_review_record', 'none')}",
        f"- source_approval_record: {record.get('source_approval_record', 'none')}",
        f"- source_checklist_record: {record.get('source_checklist_record', 'none')}",
        f"- source_transform_template: {record.get('source_transform_template', 'none')}",
        f"- source_candidate_artifact: {record.get('source_candidate_artifact', 'none')}",
        "",
        "[Target]",
        f"- final_target_name: {record.get('final_target_name', 'none')}",
        f"- final_target_path: {record.get('final_target_path', 'none')}",
        "",
        "[Notes]",
    ]
    notes = record.get("notes") or []
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def execute_generated_skill_manual_promotion(
    skill_id: str,
    *,
    operator: str,
    confirm_promotion: bool = False,
    notes: list[str] | None = None,
    allow_replace: bool = False,
    reference: str | Path | None = None,
) -> dict:
    if not confirm_promotion:
        raise ValueError("confirm_promotion must be true to execute manual promotion")

    readiness = build_generated_skill_manual_promotion_readiness(skill_id, reference=reference)
    if not readiness["can_execute"]:
        raise ValueError("; ".join(readiness["blockers"]))

    candidate_result = save_generated_skill_candidate(
        skill_id,
        operator=operator,
        notes=notes,
        allow_replace=allow_replace,
        reference=reference,
    )
    candidate = candidate_result["candidate"]
    promotion_result = save_generated_skill_promotion_record(
        skill_id,
        operator=operator,
        source_candidate_artifact=f"{skill_id}.candidate",
        final_target_name=str(candidate.get("target_name") or ""),
        final_target_path=str(candidate.get("target_path") or ""),
        notes=notes,
        allow_replace=allow_replace,
        reference=reference,
    )
    return {
        "executed": True,
        "skill_id": skill_id,
        "candidate": candidate_result,
        "promotion": promotion_result,
    }


def run_generated_skill_in_sandbox(
    skill_id: str,
    *,
    sandbox_root: str | Path,
    reference: str | Path | None = None,
    execution_flags: dict | None = None,
    mock_inputs: dict | None = None,
) -> dict:
    payload = load_generated_skill_draft(skill_id, reference=reference)
    if payload is None:
        return {
            "skill_id": skill_id,
            "run_id": None,
            "execution_mode": "operational",
            "sandbox_result": "failed",
            "success": False,
            "blocked": True,
            "reason": "draft_missing",
            "output_summary": "generated skill draft not found",
            "runtime_notes": ["draft_missing"],
        }

    validation = validate_generated_skill(skill_id, reference=reference)
    if not validation["validation_passed"]:
        return {
            "skill_id": skill_id,
            "run_id": None,
            "execution_mode": "operational",
            "sandbox_result": "failed",
            "success": False,
            "blocked": True,
            "reason": "validation_failed",
            "output_summary": validation["validation_summary"],
            "runtime_notes": list(validation["validation_errors"]),
        }
    payload = validation["skill"]

    context = build_generated_skill_sandbox_context(
        sandbox_root=sandbox_root,
        execution_flags=execution_flags,
        mock_inputs=mock_inputs,
    )
    gate = context["experimental_gate"]
    if not gate["experimental_sandbox_enabled"]:
        return {
            "skill_id": skill_id,
            "run_id": None,
            "execution_mode": gate["execution_mode"],
            "sandbox_result": "failed",
            "success": False,
            "blocked": True,
            "reason": "generated_skill_sandbox_requires_experimental_mode",
            "output_summary": "generated skill sandbox execution blocked",
            "runtime_notes": list(gate["enable_blockers"]),
            "experimental_gate": gate,
        }

    run_id = f"generated_skill_run_{uuid4().hex[:12]}"
    runtime_notes = []
    if not context["mock_inputs_allowed"]:
        runtime_notes.extend(context["mock_input_errors"])
        result_payload = _save_generated_skill_result(
            {
                "skill_id": skill_id,
                "run_id": run_id,
                "execution_mode": gate["execution_mode"],
                "sandbox_result": "failed",
                "output_summary": "mock inputs escaped sandbox policy",
                "runtime_notes": runtime_notes,
                "generated_at": _timestamp(),
            },
            reference=reference,
        )
        payload["status"] = "sandbox_failed"
        payload["sandbox_result_summary"] = result_payload["output_summary"]
        payload["last_sandbox_result"] = {
            "run_id": run_id,
            "sandbox_result": "failed",
            "output_summary": result_payload["output_summary"],
            "runtime_notes": runtime_notes,
        }
        _persist_generated_skill_record(payload, reference=reference)
        return {
            **result_payload,
            "success": False,
            "blocked": False,
            "experimental_gate": gate,
        }

    skill_kind = payload["skill_definition"]["skill_kind"]
    runner = GENERATED_SKILL_RUNNERS[skill_kind]
    try:
        output = runner(context["mock_inputs"])
        result_payload = _save_generated_skill_result(
            {
                "skill_id": skill_id,
                "run_id": run_id,
                "execution_mode": gate["execution_mode"],
                "sandbox_result": "passed",
                "output_summary": output["output_summary"],
                "runtime_notes": runtime_notes,
                "generated_at": _timestamp(),
                "output": output,
            },
            reference=reference,
        )
        payload["status"] = "sandbox_passed"
        payload["sandbox_result_summary"] = result_payload["output_summary"]
        payload["last_sandbox_result"] = {
            "run_id": run_id,
            "sandbox_result": "passed",
            "output_summary": result_payload["output_summary"],
            "runtime_notes": runtime_notes,
        }
        _persist_generated_skill_record(payload, reference=reference)
        queued = enqueue_generated_skill_for_manual_promotion(skill_id, reference=reference)
        return {
            **result_payload,
            "success": True,
            "blocked": False,
            "experimental_gate": gate,
            "queue": queued,
        }
    except Exception as exc:
        runtime_notes.append(str(exc))
        result_payload = _save_generated_skill_result(
            {
                "skill_id": skill_id,
                "run_id": run_id,
                "execution_mode": gate["execution_mode"],
                "sandbox_result": "failed",
                "output_summary": f"sandbox execution failed: {exc}",
                "runtime_notes": runtime_notes,
                "generated_at": _timestamp(),
            },
            reference=reference,
        )
        payload["status"] = "sandbox_failed"
        payload["sandbox_result_summary"] = result_payload["output_summary"]
        payload["last_sandbox_result"] = {
            "run_id": run_id,
            "sandbox_result": "failed",
            "output_summary": result_payload["output_summary"],
            "runtime_notes": runtime_notes,
        }
        _persist_generated_skill_record(payload, reference=reference)
        return {
            **result_payload,
            "success": False,
            "blocked": False,
            "experimental_gate": gate,
        }
