import json
from datetime import datetime, timezone
from pathlib import Path

from agent.workspace_metrics import resolve_runtime_data_root

RUNTIME_STATE_DIRNAME = "runtime"
RUNTIME_STATE_VERSION = "v1"
IMMUTABLE_RUNTIME_FIELDS = {
    "transaction_id",
    "proposal_id",
    "markers",
    "terminal_marker",
    "state_machine_version",
    "executor_spec_version",
    "idempotency_mode",
    "execution_mode",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_transaction_runtime_state_path(transaction_id: str, *, reference: str | Path | None = None) -> Path:
    runtime_root = resolve_runtime_data_root(reference)
    return runtime_root / RUNTIME_STATE_DIRNAME / f"{transaction_id}.json"


def _ensure_runtime_state_dir(reference: str | Path | None = None) -> Path:
    path = get_transaction_runtime_state_path("placeholder", reference=reference).parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_transaction_runtime_state(payload: dict, *, reference: str | Path | None = None) -> dict:
    path = get_transaction_runtime_state_path(payload["transaction_id"], reference=reference)
    _ensure_runtime_state_dir(reference)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def initialize_transaction_runtime_state(
    transaction_id: str,
    proposal_id: str | None,
    *,
    reference: str | Path | None = None,
    initial_state: str = "prechecked",
    metadata: dict | None = None,
) -> dict:
    existing = load_transaction_runtime_state(transaction_id, reference=reference)
    if existing is not None:
        return existing

    metadata = metadata or {}
    payload = {
        "transaction_id": transaction_id,
        "proposal_id": proposal_id,
        "state": initial_state,
        "markers": [],
        "last_updated_at": _timestamp(),
        "terminal_marker": None,
        "runtime_notes": [],
        "state_machine_version": metadata.get("state_machine_version", RUNTIME_STATE_VERSION),
        "executor_spec_version": metadata.get("executor_spec_version", RUNTIME_STATE_VERSION),
        "idempotency_mode": metadata.get("idempotency_mode", "strict"),
        "execution_mode": metadata.get("execution_mode", "operational"),
    }
    return _write_transaction_runtime_state(payload, reference=reference)


def load_transaction_runtime_state(
    transaction_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    path = get_transaction_runtime_state_path(transaction_id, reference=reference)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def update_transaction_runtime_state(
    transaction_id: str,
    patch: dict,
    *,
    reference: str | Path | None = None,
    note: str | None = None,
) -> dict:
    current = load_transaction_runtime_state(transaction_id, reference=reference)
    if current is None:
        return {"updated": False, "reason": "runtime_state_missing", "runtime_state": None}
    if current.get("terminal_marker"):
        return {"updated": False, "reason": "terminal_marker_recorded", "runtime_state": current}
    if current.get("state") == "halted_for_manual_review":
        return {"updated": False, "reason": "halted_for_manual_review", "runtime_state": current}

    forbidden = IMMUTABLE_RUNTIME_FIELDS.intersection(patch.keys())
    if forbidden:
        return {
            "updated": False,
            "reason": f"immutable_fields: {', '.join(sorted(forbidden))}",
            "runtime_state": current,
        }

    current.update(patch)
    if note:
        current.setdefault("runtime_notes", []).append(note)
    current["last_updated_at"] = _timestamp()
    _write_transaction_runtime_state(current, reference=reference)
    return {"updated": True, "reason": "updated", "runtime_state": current}


def summarize_runtime_transaction_state(
    transaction_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    current = load_transaction_runtime_state(transaction_id, reference=reference)
    if current is None:
        return None
    markers = current.get("markers", [])
    return {
        "transaction_id": current.get("transaction_id"),
        "proposal_id": current.get("proposal_id"),
        "execution_mode": current.get("execution_mode", "operational"),
        "state": current.get("state"),
        "marker_count": len(markers),
        "terminal_marker": current.get("terminal_marker"),
        "last_marker": markers[-1]["marker"] if markers else None,
        "last_updated_at": current.get("last_updated_at"),
        "note_count": len(current.get("runtime_notes", [])),
    }


def load_runtime_transaction_state_for_debug(
    transaction_id: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    return load_transaction_runtime_state(transaction_id, reference=reference)
