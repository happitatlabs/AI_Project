import json
import logging
import fnmatch
import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger("workspace_metrics")

DEFAULT_EXCLUDED_DIRS = {"__pycache__"}
DEFAULT_EXCLUDED_FILE_PATTERNS = (
    "agent_memory_broken*",
    "*_broken*",
    "legacy_agent_memory*",
)
EXCLUDED_LARGE_FILE_BYTES = 1024 * 1024
SELF_ARTIFACT_DIRS = {"reports", "archive", "logs", "runtime-data"}
SELF_ARTIFACT_SUFFIXES = {".log", ".jsonl"}
BUILTIN_SELF_ARTIFACT_EXACT_NAMES = {
    "agent_state.json",
    "pending_approvals.json",
    "agent.pid",
}
BUILTIN_SELF_ARTIFACT_GLOB_PATTERNS = (
    "history/history_current.jsonl",
    "history/history_*.jsonl",
    "history/runtime_*.jsonl",
    "logs/agent_trace*",
    "logs/runtime_trace*",
    "runtime_trace*",
    "session_trace*",
    "agent_trace*",
    "*.pid.lock",
)
SELF_ARTIFACT_RULES_FILE = Path(__file__).resolve().parent.parent / "self_artifacts.json"
HIGH_RISK_EXACT_NAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env",
}
HIGH_RISK_PREFIXES = (
    "src/",
    "scripts/",
    "config/",
    "configs/",
)
HIGH_RISK_CODE_SUFFIXES = {".py", ".sh", ".ps1", ".bat"}
HIGH_RISK_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
HIGH_RISK_CONFIG_NAME_HINTS = ("config", "settings", "package", "manifest", "lock")
LOW_RISK_PREFIXES = (
    "docs/",
    "doc/",
    "notes/",
)
LOW_RISK_SUFFIXES = {
    ".md",
    ".rst",
    ".txt",
    ".tmp",
    ".tmpdata",
    ".trace",
    ".cache",
    ".bak",
    ".orig",
}
RISK_SCORES = {"IGNORE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
RISK_SNAPSHOT_DIR = "reports"
RISK_SNAPSHOT_BASENAME = "risk_snapshot"
RISK_SNAPSHOT_MAX_AGE_SECONDS = 24 * 60 * 60
MEDIUM_SURGE_THRESHOLD = 5
RISK_ACTION_REOPEN_WEIGHTS = {
    "REVIEW_REQUIRED": 3,
    "ALERT": 2,
    "REVIEW_RECOMMENDED": 1,
    "MONITOR": 1,
    "SAFE": 0,
    None: 0,
}
RISK_ACTION_SUGGESTION_PRIORITIES = {
    "REVIEW_REQUIRED": 90,
    "ALERT": 75,
    "REVIEW_RECOMMENDED": 55,
    "MONITOR": 35,
    "SAFE": 0,
    None: 0,
}
RISK_ACTION_SUGGESTION_SEVERITIES = {
    "REVIEW_REQUIRED": "critical",
    "ALERT": "high",
    "REVIEW_RECOMMENDED": "medium",
    "MONITOR": "low",
    "SAFE": "none",
    None: "none",
}
RISK_CERTAINTY_BONUS = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
RISK_BASELINE_PENALTY = {"fresh": 0, "stale": 1, "missing": 2}
RISK_BLOCKER_BASE_SCORES = {
    "REVIEW_REQUIRED": 90,
    "ALERT": 65,
    "REVIEW_RECOMMENDED": 45,
    "MONITOR": 20,
    "SAFE": 0,
    None: 0,
}
RISK_PATH_PRIORITY_HINTS = {
    "config/": "config",
    "configs/": "config",
    "src/core/": "runtime_core",
    "src/runtime/": "runtime_core",
    "runtime/": "runtime_core",
    "scripts/": "script",
}
RISK_CLUSTER_LABELS = {
    "config": "Config Risk Cluster",
    "runtime": "Runtime Risk Cluster",
    "core": "Core Source Risk Cluster",
    "docs": "Docs Risk Cluster",
    "temp": "Temp Noise Cluster",
    "mixed": "Mixed Risk Cluster",
}
RISK_CLUSTER_PRIORITY = {
    "config": 0,
    "runtime": 1,
    "core": 2,
    "mixed": 3,
    "docs": 4,
    "temp": 5,
}
REOPEN_TIE_BREAKER_DEFAULT = 1000
RUNTIME_DATA_ENV_VAR = "AUTONOMOUS_AGENT_RUNTIME_DIR"
PROPOSALS_DIRNAME = "proposals"
STAGING_DIRNAME = "staging"
REVIEW_DECISIONS_DIRNAME = "review_decisions"
SAFE_APPLY_ALLOWED_PREFIXES = ("config/", "configs/", "docs/", "doc/", "notes/")
REAL_APPLY_ALLOWED_PREFIXES = SAFE_APPLY_ALLOWED_PREFIXES
REAL_APPLY_BACKUP_ROOT_PATTERN = "runtime-data/live_backups/<transaction_id>/"
REAL_APPLY_AUDIT_FIELDS = [
    "transaction_id",
    "proposal_id",
    "operator",
    "timestamp",
    "target_paths",
    "apply_mode",
    "result",
    "rollback_invoked",
]


@dataclass
class StateDiff:
    full_changed: bool
    decision_changed: bool
    self_artifact_changed: bool
    external_changed: bool
    added_paths: list[str]
    removed_paths: list[str]
    added_self_artifacts: list[str]
    removed_self_artifacts: list[str]
    added_external_paths: list[str]
    removed_external_paths: list[str]


def _normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("./").lower()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_baseline_reason(baseline_status: str) -> str:
    return {
        "fresh": "fresh_snapshot",
        "stale": "stale_snapshot",
        "missing": "missing_snapshot",
    }.get(baseline_status, "missing_snapshot")


@lru_cache(maxsize=1)
def _load_self_artifact_rules() -> dict:
    if not SELF_ARTIFACT_RULES_FILE.exists():
        return {
            "exact_names": tuple(sorted(BUILTIN_SELF_ARTIFACT_EXACT_NAMES)),
            "glob_patterns": tuple(sorted(_normalize_path(pattern) for pattern in BUILTIN_SELF_ARTIFACT_GLOB_PATTERNS)),
        }
    with open(SELF_ARTIFACT_RULES_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    exact_names = {
        *(_normalize_path(name) for name in payload.get("exact_names", [])),
        *(_normalize_path(name) for name in BUILTIN_SELF_ARTIFACT_EXACT_NAMES),
    }
    glob_patterns = {
        *(_normalize_path(pattern) for pattern in payload.get("glob_patterns", [])),
        *(_normalize_path(pattern) for pattern in BUILTIN_SELF_ARTIFACT_GLOB_PATTERNS),
    }
    return {
        "exact_names": tuple(sorted(exact_names)),
        "glob_patterns": tuple(sorted(glob_patterns)),
    }


def is_self_artifact(path: str | Path) -> bool:
    candidate = Path(path)
    parts = {part.lower() for part in candidate.parts[:-1]}
    if parts & SELF_ARTIFACT_DIRS:
        return True

    normalized = _normalize_path(candidate)
    name = candidate.name.lower()
    rules = _load_self_artifact_rules()
    if name in rules["exact_names"]:
        return True

    suffix = candidate.suffix.lower()
    if suffix in SELF_ARTIFACT_SUFFIXES:
        return True

    return any(
        fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in rules["glob_patterns"]
    )


def classify_risk(path: str | Path, self_artifact: bool | None = None) -> str:
    if self_artifact is None:
        self_artifact = is_self_artifact(path)
    if self_artifact:
        return "IGNORE"

    candidate = Path(path)
    normalized = _normalize_path(candidate)
    suffix = candidate.suffix.lower()
    name = candidate.name.lower()

    if name in HIGH_RISK_EXACT_NAMES or normalized in HIGH_RISK_EXACT_NAMES:
        return "HIGH"
    if any(normalized.startswith(prefix) for prefix in HIGH_RISK_PREFIXES) and suffix in HIGH_RISK_CODE_SUFFIXES | HIGH_RISK_CONFIG_SUFFIXES:
        return "HIGH"
    if suffix == ".py":
        return "HIGH"
    if suffix in HIGH_RISK_CONFIG_SUFFIXES and any(hint in name for hint in HIGH_RISK_CONFIG_NAME_HINTS):
        return "HIGH"
    if suffix in {".sh", ".ps1", ".bat"}:
        return "HIGH"

    if any(normalized.startswith(prefix) for prefix in LOW_RISK_PREFIXES):
        return "LOW"
    if suffix in LOW_RISK_SUFFIXES:
        return "LOW"
    if name.endswith(".md"):
        return "LOW"

    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "MEDIUM"
    if suffix in {".py", ".sh", ".ps1", ".bat"}:
        return "MEDIUM"
    return "MEDIUM"


def annotate_changes(paths: list[str | Path]) -> list[dict]:
    annotated = []
    for path in paths:
        self_artifact = is_self_artifact(path)
        annotated.append({
            "path": str(path),
            "normalized_path": _normalize_path(path),
            "self_artifact": self_artifact,
            "risk": classify_risk(path, self_artifact=self_artifact),
            "severity": RISK_SCORES[classify_risk(path, self_artifact=self_artifact)],
        })
    return annotated


def summarize_risk_changes(changes: list[dict]) -> dict:
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "IGNORE": 0}
    external_changes = []
    for change in changes:
        risk = change.get("risk", "MEDIUM")
        counts[risk] = counts.get(risk, 0) + 1
        if not change.get("self_artifact") and risk != "IGNORE":
            external_changes.append(change)

    highest = max(external_changes, key=lambda item: item.get("severity", RISK_SCORES.get(item.get("risk", "MEDIUM"), 2)), default=None)
    return {
        "high_risk_count": counts["HIGH"],
        "medium_risk_count": counts["MEDIUM"],
        "low_risk_count": counts["LOW"],
        "ignored_count": counts["IGNORE"],
        "external_change_count": len(external_changes),
        "highest_risk": highest.get("risk") if highest else "IGNORE",
        "primary_risky_path": highest.get("normalized_path") if highest else None,
    }


def summarize_workspace_risks(paths: list[str | Path]) -> dict:
    return summarize_risk_changes(annotate_changes(list(paths)))


def _canonicalize_text_for_signature(raw_text: str, suffix: str) -> str:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    if suffix == ".json":
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _load_canonical_content(risk_item: dict, workspace: str | Path | None = None) -> dict | None:
    path_value = risk_item.get("normalized_path") or risk_item.get("path")
    if not path_value:
        return None

    candidate = Path(path_value)
    if workspace is not None and not candidate.is_absolute():
        candidate = Path(workspace) / candidate

    try:
        raw_bytes = candidate.read_bytes()
    except OSError:
        return None

    payload = {
        "path": str(candidate),
        "suffix": candidate.suffix.lower(),
    }
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        payload["canonical_bytes"] = raw_bytes
        payload["canonical_text"] = None
        payload["parsed_json"] = None
        return payload

    canonical_text = _canonicalize_text_for_signature(raw_text, candidate.suffix.lower())
    parsed_json = None
    if candidate.suffix.lower() == ".json":
        try:
            parsed_json = json.loads(canonical_text)
        except json.JSONDecodeError:
            parsed_json = None

    payload["canonical_text"] = canonical_text
    payload["canonical_bytes"] = canonical_text.encode("utf-8")
    payload["parsed_json"] = parsed_json
    return payload


def build_content_signature(risk_item: dict, workspace: str | Path | None = None) -> str | None:
    payload = _load_canonical_content(risk_item, workspace=workspace)
    if not payload:
        return None
    return hashlib.sha256(payload["canonical_bytes"]).hexdigest()


def build_content_metadata(risk_item: dict, workspace: str | Path | None = None) -> dict | None:
    payload = _load_canonical_content(risk_item, workspace=workspace)
    if not payload:
        return None

    canonical_text = payload.get("canonical_text")
    parsed_json = payload.get("parsed_json")
    metadata = {
        "content_kind": "binary" if canonical_text is None else "text",
    }
    if canonical_text is not None:
        metadata["line_count"] = len(canonical_text.splitlines()) if canonical_text else 0
    if isinstance(parsed_json, dict):
        metadata["content_kind"] = "json"
        metadata["json_keys"] = sorted(str(key) for key in parsed_json.keys())
    return metadata


def build_diff_hint(previous_item: dict, current_item: dict) -> dict:
    path = current_item.get("path") or previous_item.get("path") or "unknown"
    previous_meta = previous_item.get("content_meta") or {}
    current_meta = current_item.get("content_meta") or {}
    previous_kind = previous_meta.get("content_kind")
    current_kind = current_meta.get("content_kind")

    if previous_kind == current_kind == "json":
        previous_keys = previous_meta.get("json_keys", [])
        current_keys = current_meta.get("json_keys", [])
        if previous_keys != current_keys:
            return {
                "type": "json_keys_changed",
                "text": f"{path}: json keys changed",
            }
        if previous_meta.get("line_count") != current_meta.get("line_count"):
            return {
                "type": "line_count_changed",
                "text": f"{path}: line count changed",
            }
        return {
            "type": "value_changed",
            "text": f"{path}: values changed",
        }

    previous_line_count = previous_meta.get("line_count")
    current_line_count = current_meta.get("line_count")
    if previous_line_count is not None and current_line_count is not None and previous_line_count != current_line_count:
        return {
            "type": "line_count_changed",
            "text": f"{path}: line count changed",
        }

    return {
        "type": "text_modified",
        "text": f"{path}: text modified",
    }


def build_risk_snapshot(paths: list[str | Path], workspace: str | Path | None = None) -> dict:
    entries = []
    for change in annotate_changes(list(paths)):
        if change.get("self_artifact") or change.get("risk") == "IGNORE":
            continue
        item = {
            "path": change.get("normalized_path") or change.get("path"),
            "severity": change.get("risk"),
        }
        content_signature = build_content_signature(change, workspace=workspace)
        if content_signature:
            item["content_signature"] = content_signature
            content_meta = build_content_metadata(change, workspace=workspace)
            if content_meta:
                item["content_meta"] = content_meta
        entries.append(item)
    entries.sort(key=lambda item: item["path"])
    return {
        "created_at": _format_timestamp(_utc_now()),
        "source": "manual",
        "entries": entries,
    }


def _risk_snapshot_path(workspace: str | Path, target: str | Path | None = None) -> Path:
    workspace_path = Path(workspace)
    if target is None:
        return workspace_path / RISK_SNAPSHOT_DIR / f"{RISK_SNAPSHOT_BASENAME}.json"
    return workspace_path / target


def write_risk_snapshot(
    workspace: str | Path,
    paths: list[str | Path],
    target: str | Path | None = None,
    source: str = "inspect",
) -> dict:
    target_path = _risk_snapshot_path(workspace, target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path = target_path
    if actual_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        actual_path = actual_path.with_name(f"{actual_path.stem}_{timestamp}{actual_path.suffix}")

    payload = build_risk_snapshot(paths, workspace=workspace)
    payload["source"] = source
    actual_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "saved": True,
        "path": str(actual_path),
        "requested_path": str(target_path),
        "entries": len(payload["entries"]),
    }


def load_latest_risk_snapshot(workspace: str | Path) -> dict:
    reports_dir = Path(workspace) / RISK_SNAPSHOT_DIR
    if not reports_dir.exists():
        return {"created_at": None, "entries": [], "baseline_reason": "initial_scan"}
    candidates = sorted(reports_dir.glob(f"{RISK_SNAPSHOT_BASENAME}*.json"))
    if not candidates:
        return {"created_at": None, "entries": [], "baseline_reason": "initial_scan"}
    latest = max(candidates, key=lambda path: (path.stat().st_mtime, path.name))
    latest_mtime = latest.stat().st_mtime
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "created_at": None,
            "entries": [],
            "path": str(latest),
            "_loaded_mtime": latest_mtime,
            "baseline_reason": "missing_snapshot",
        }
    payload.setdefault("entries", [])
    payload.setdefault("source", "legacy")
    payload.setdefault("baseline_reason", "fresh_snapshot")
    payload["path"] = str(latest)
    payload["_loaded_mtime"] = latest_mtime
    return payload


def evaluate_snapshot_freshness(
    snapshot_meta: dict | None,
    now: datetime | None = None,
    max_age_seconds: int = RISK_SNAPSHOT_MAX_AGE_SECONDS,
) -> dict:
    now = now or _utc_now()
    snapshot_meta = snapshot_meta or {}
    if not snapshot_meta or (not snapshot_meta.get("entries") and not snapshot_meta.get("path")):
        return {
            "baseline_status": "missing",
            "baseline_created_at": None,
            "baseline_age_seconds": None,
            "baseline_stale": False,
            "baseline_reason": snapshot_meta.get("baseline_reason", "initial_scan") if snapshot_meta else "initial_scan",
        }

    created_at = _parse_timestamp(snapshot_meta.get("created_at"))
    if created_at is None and snapshot_meta.get("_loaded_mtime") is not None:
        created_at = datetime.fromtimestamp(snapshot_meta["_loaded_mtime"], tz=timezone.utc)
    if created_at is None:
        return {
            "baseline_status": "missing",
            "baseline_created_at": None,
            "baseline_age_seconds": None,
            "baseline_stale": False,
            "baseline_reason": snapshot_meta.get("baseline_reason", "missing_snapshot"),
        }

    age_seconds = max(0, int((now - created_at).total_seconds()))
    stale = age_seconds > max_age_seconds
    return {
        "baseline_status": "stale" if stale else "fresh",
        "baseline_created_at": _format_timestamp(created_at),
        "baseline_age_seconds": age_seconds,
        "baseline_stale": stale,
        "baseline_reason": "stale_snapshot" if stale else "fresh_snapshot",
    }


def compute_risk_delta(
    previous_snapshot: dict | None,
    current_snapshot: dict | None,
    baseline_meta: dict | None = None,
) -> dict:
    # 현재 risk delta의 기본 계약은 path + severity 비교다.
    # content-aware delta는 동일 path + severity 조건에서의 보강 정보만 추가한다.
    previous_items = {item["path"]: item for item in (previous_snapshot or {}).get("entries", []) if item.get("path")}
    current_items = {item["path"]: item for item in (current_snapshot or {}).get("entries", []) if item.get("path")}
    previous_entries = {path: item["severity"] for path, item in previous_items.items()}
    current_entries = {path: item["severity"] for path, item in current_items.items()}

    previous_high = {path for path, severity in previous_entries.items() if severity == "HIGH"}
    current_high = {path for path, severity in current_entries.items() if severity == "HIGH"}

    def _count(entries: dict[str, str], severity: str) -> int:
        return sum(1 for value in entries.values() if value == severity)

    delta = {
        "high_risk_delta": _count(current_entries, "HIGH") - _count(previous_entries, "HIGH"),
        "medium_risk_delta": _count(current_entries, "MEDIUM") - _count(previous_entries, "MEDIUM"),
        "low_risk_delta": _count(current_entries, "LOW") - _count(previous_entries, "LOW"),
        "new_high_risk_paths": sorted(current_high - previous_high),
        "resolved_high_risks": sorted(previous_high - current_high),
        "persistent_high_risks": sorted(previous_high & current_high),
    }

    has_content_signatures = any(
        item.get("content_signature")
        for item in [*previous_items.values(), *current_items.values()]
    )
    if has_content_signatures:
        shared_paths = sorted(set(previous_items) & set(current_items))
        persistent_same_paths = []
        persistent_content_changed_paths = []
        severity_changed_paths = []
        for path in shared_paths:
            previous_item = previous_items[path]
            current_item = current_items[path]
            if previous_item["severity"] != current_item["severity"]:
                severity_changed_paths.append(path)
                continue
            previous_signature = previous_item.get("content_signature")
            current_signature = current_item.get("content_signature")
            if previous_signature and current_signature and previous_signature != current_signature:
                persistent_content_changed_paths.append(path)
            else:
                persistent_same_paths.append(path)

        content_change_hints = {}
        content_change_hint_types = {}
        for path in persistent_content_changed_paths:
            hint = build_diff_hint(previous_items[path], current_items[path])
            content_change_hints[path] = hint["text"]
            content_change_hint_types[path] = hint["type"]

        delta.update({
            "content_changed": bool(persistent_content_changed_paths),
            "content_change_type": "modified" if persistent_content_changed_paths else "same",
            "comparison_basis": "path+severity+content",
            "content_changed_count": len(persistent_content_changed_paths),
            "content_changed_paths": persistent_content_changed_paths,
            "top_content_changed_path": persistent_content_changed_paths[0] if persistent_content_changed_paths else None,
            "content_change_hints": content_change_hints,
            "content_change_hint_types": content_change_hint_types,
            "top_content_change_hint": content_change_hints.get(persistent_content_changed_paths[0]) if persistent_content_changed_paths else None,
            "persistent_same_paths": persistent_same_paths,
            "persistent_content_changed_paths": persistent_content_changed_paths,
            "severity_changed_paths": severity_changed_paths,
        })

    if baseline_meta:
        delta.update({
            "baseline_status": baseline_meta.get("baseline_status", "missing"),
            "baseline_created_at": baseline_meta.get("baseline_created_at"),
            "baseline_age_seconds": baseline_meta.get("baseline_age_seconds"),
            "baseline_stale": baseline_meta.get("baseline_stale", False),
            "baseline_reason": baseline_meta.get(
                "baseline_reason",
                _default_baseline_reason(baseline_meta.get("baseline_status", "missing")),
            ),
        })
    return delta


def build_action_signal(risk_delta: dict, current_risk_summary: dict) -> dict:
    new_high_risks = risk_delta.get("new_high_risk_paths", [])
    persistent_high_risks = risk_delta.get("persistent_high_risks", [])
    baseline_status = risk_delta.get("baseline_status", "missing")
    primary_path = (
        new_high_risks[0] if new_high_risks
        else current_risk_summary.get("primary_risky_path")
        or (persistent_high_risks[0] if persistent_high_risks else None)
    )

    baseline_reason = risk_delta.get("baseline_reason", _default_baseline_reason(baseline_status))
    current_high_count = current_risk_summary.get("high_risk_count", 0)

    if new_high_risks and baseline_status != "missing":
        action = "REVIEW_REQUIRED"
        reason = "new HIGH risk detected"
    elif baseline_status == "missing" and current_high_count > 0:
        action = "REVIEW_REQUIRED"
        reason = "baseline missing; HIGH risk present in current snapshot"
    elif risk_delta.get("high_risk_delta", 0) > 0:
        action = "ALERT"
        reason = "HIGH risk count increased"
    elif persistent_high_risks or current_risk_summary.get("high_risk_count", 0) > 0:
        action = "MONITOR"
        reason = "HIGH risk persists"
    elif risk_delta.get("medium_risk_delta", 0) >= MEDIUM_SURGE_THRESHOLD:
        action = "REVIEW_RECOMMENDED"
        reason = "medium risk increased sharply"
    elif baseline_status == "missing":
        action = "MONITOR"
        reason = "baseline missing; monitor current risk state"
    else:
        action = "SAFE"
        reason = "no HIGH risk detected"

    if baseline_status == "fresh":
        certainty = "HIGH" if action in {"REVIEW_REQUIRED", "ALERT", "SAFE"} else "MEDIUM"
    elif baseline_status == "stale":
        certainty = "MEDIUM" if action in {"REVIEW_REQUIRED", "ALERT"} else "LOW"
    else:
        certainty = "LOW"

    if baseline_status == "stale":
        reason = f"baseline stale; {reason}"
    elif baseline_status == "missing":
        primary_path = primary_path or current_risk_summary.get("primary_risky_path")

    return {
        "action": action,
        "reason": reason,
        "primary_path": primary_path,
        "certainty": certainty,
        "baseline_reason": baseline_reason,
    }


def score_risk_decision_signal(risk_signal: dict | None) -> dict:
    risk_signal = risk_signal or {}
    action_signal = risk_signal.get("action_signal", risk_signal)
    action = action_signal.get("action")
    certainty = action_signal.get("certainty", "LOW")
    baseline_status = risk_signal.get("baseline_status", "missing")
    baseline_reason = risk_signal.get("baseline_reason", _default_baseline_reason(baseline_status))
    blocker_candidate = risk_signal.get("blocker_candidate")

    reopen_score = max(
        0,
        RISK_ACTION_REOPEN_WEIGHTS.get(action, 0)
        + RISK_CERTAINTY_BONUS.get(certainty, 0)
        - RISK_BASELINE_PENALTY.get(baseline_status, 0),
    )
    if action == "MONITOR" and certainty == "LOW":
        reopen_score = 0

    suggestion_priority = max(
        0,
        RISK_ACTION_SUGGESTION_PRIORITIES.get(action, 0)
        - (10 if certainty == "LOW" else 0),
    )
    blocker_score = max(
        0,
        RISK_BLOCKER_BASE_SCORES.get(action, 0)
        + (10 if certainty == "HIGH" else 5 if certainty == "MEDIUM" else 0)
        - (15 if baseline_status == "missing" else 10 if baseline_status == "stale" else 0),
    )
    blocker_promoted = bool(
        blocker_candidate
        and action == "REVIEW_REQUIRED"
        and certainty == "HIGH"
        and blocker_score >= 80
    )

    return {
        "reopen_score": reopen_score,
        "suggestion_priority": suggestion_priority,
        "suggestion_severity": RISK_ACTION_SUGGESTION_SEVERITIES.get(action, "none"),
        "blocker_candidate": blocker_candidate,
        "blocker_score": blocker_score,
        "blocker_promoted": blocker_promoted,
        "baseline_status": baseline_status,
        "baseline_reason": baseline_reason,
        "action": action,
        "certainty": certainty,
    }


def classify_risk_path_scope(path: str | None) -> str:
    normalized = _normalize_path(path or "")
    for prefix, scope in RISK_PATH_PRIORITY_HINTS.items():
        if normalized.startswith(prefix):
            return scope
    if normalized.endswith((".yaml", ".yml", ".json", ".toml", ".ini", ".cfg")):
        return "config"
    if normalized.endswith((".sh", ".ps1", ".bat")):
        return "script"
    if normalized.endswith(".py"):
        return "runtime_core"
    return "general"


def classify_risk_cluster(path: str | None, severity: str | None = None) -> str:
    normalized = _normalize_path(path or "")
    if normalized.startswith(("config/", "configs/")):
        return "config"
    if normalized.startswith(("src/runtime/", "runtime/", "scripts/")):
        return "runtime"
    if normalized.startswith(("src/core/", "src/")) or normalized.endswith(".py"):
        return "core"
    if normalized.startswith(("docs/", "doc/", "notes/")):
        return "docs"
    if normalized.endswith((".tmp", ".tmpdata", ".trace", ".cache", ".bak", ".orig")):
        return "temp"
    if severity == "LOW":
        return "temp"
    return "mixed"


def build_risk_clusters(
    current_snapshot: dict | None,
    risk_delta: dict | None,
    operational_signal: dict | None = None,
    skills: list[dict] | None = None,
) -> dict:
    current_snapshot = current_snapshot or {}
    risk_delta = risk_delta or {}
    operational_signal = operational_signal or {}
    entries = current_snapshot.get("entries", [])
    new_high_paths = set(risk_delta.get("new_high_risk_paths", []))
    persistent_high_paths = set(risk_delta.get("persistent_high_risks", []))
    baseline_status = risk_delta.get("baseline_status", operational_signal.get("baseline_status", "missing"))

    cluster_map: dict[str, dict] = {}
    for entry in entries:
        path = entry.get("path")
        severity = entry.get("severity", "MEDIUM")
        if not path or severity == "IGNORE":
            continue
        cluster_id = classify_risk_cluster(path, severity)
        cluster = cluster_map.setdefault(cluster_id, {
            "cluster_id": cluster_id,
            "label": RISK_CLUSTER_LABELS.get(cluster_id, "Mixed Risk Cluster"),
            "severity": severity,
            "path_count": 0,
            "new_high_count": 0,
            "persistent_high_count": 0,
            "top_paths": [],
            "paths": [],
        })
        if RISK_SCORES.get(severity, 0) > RISK_SCORES.get(cluster["severity"], 0):
            cluster["severity"] = severity
        cluster["path_count"] += 1
        cluster["paths"].append(path)
        if len(cluster["top_paths"]) < 3:
            cluster["top_paths"].append(path)
        if path in new_high_paths:
            cluster["new_high_count"] += 1
        if path in persistent_high_paths:
            cluster["persistent_high_count"] += 1

    clusters = []
    for cluster in cluster_map.values():
        severity_score = RISK_SCORES.get(cluster["severity"], 0)
        freshness_bonus = 2 if baseline_status == "fresh" else 1 if baseline_status == "stale" else 0
        cluster_sort_key = (
            -severity_score,
            -cluster["new_high_count"],
            -cluster["persistent_high_count"],
            -(freshness_bonus),
            RISK_CLUSTER_PRIORITY.get(cluster["cluster_id"], 99),
            -cluster["path_count"],
            cluster["cluster_id"],
        )
        if cluster["new_high_count"] > 0:
            summary_reason = f"new high-risk {cluster['cluster_id']} changes detected"
        elif cluster["persistent_high_count"] > 0:
            summary_reason = f"persistent high-risk {cluster['cluster_id']} paths remain"
        elif cluster["severity"] == "MEDIUM":
            summary_reason = f"medium-risk {cluster['cluster_id']} changes require grouped review"
        else:
            summary_reason = f"{cluster['cluster_id']} changes observed"
        cluster["summary_reason"] = summary_reason
        cluster["cluster_sort_key"] = cluster_sort_key
        cluster["cluster_rank_reason"] = (
            f"severity={cluster['severity']}, new_high={cluster['new_high_count']}, "
            f"persistent={cluster['persistent_high_count']}, baseline={baseline_status}"
        )
        clusters.append(cluster)

    high_medium_clusters = [cluster for cluster in clusters if cluster["severity"] in {"HIGH", "MEDIUM"}]
    if high_medium_clusters:
        clusters = high_medium_clusters
    clusters = sorted(clusters, key=lambda item: item["cluster_sort_key"])
    for idx, cluster in enumerate(clusters, start=1):
        cluster["cluster_rank"] = idx

    return {
        "clusters": clusters,
        "top_cluster_id": clusters[0]["cluster_id"] if clusters else None,
    }


def attach_content_summary_to_clusters(
    cluster_model: dict | None,
    risk_delta: dict | None,
) -> dict:
    cluster_model = cluster_model or {}
    risk_delta = risk_delta or {}
    content_changed_paths = set(risk_delta.get("content_changed_paths", []))
    content_change_hints = risk_delta.get("content_change_hints", {})
    clusters = []

    for cluster in cluster_model.get("clusters", []):
        cluster_copy = dict(cluster)
        cluster_paths = cluster_copy.get("paths", [])
        cluster_content_paths = [path for path in cluster_paths if path in content_changed_paths]
        cluster_copy["cluster_content_changed_count"] = len(cluster_content_paths)
        cluster_copy["cluster_content_changed_paths"] = cluster_content_paths
        cluster_copy["cluster_has_content_change"] = bool(cluster_content_paths)
        cluster_copy["top_content_changed_path_in_cluster"] = cluster_content_paths[0] if cluster_content_paths else None
        cluster_copy["top_content_change_hint_in_cluster"] = (
            content_change_hints.get(cluster_content_paths[0]) if cluster_content_paths else None
        )
        clusters.append(cluster_copy)

    return {
        "clusters": clusters,
        "top_cluster_id": cluster_model.get("top_cluster_id"),
    }


def select_guidance_wording(
    *,
    certainty: str,
    has_new_high: bool = False,
    has_content_change: bool = False,
    has_persistent_high: bool = False,
    suggestion_bias: str = "neutral",
) -> dict:
    if has_new_high:
        if certainty == "HIGH":
            lead = "review immediately"
        elif certainty == "MEDIUM":
            lead = "review recommended"
        else:
            lead = "monitor and verify"
    elif has_content_change:
        if certainty == "HIGH":
            lead = "review changed risk paths"
        elif certainty == "MEDIUM":
            lead = "verify recent changes"
        else:
            lead = "monitor and verify recent changes"
    elif has_persistent_high:
        lead = "monitor and verify" if certainty != "HIGH" else "review recommended"
    else:
        lead = "monitor and verify" if certainty == "LOW" else "review recommended"

    if suggestion_bias == "action" and has_new_high and certainty != "LOW":
        lead = "review immediately" if certainty == "HIGH" else "review recommended"
    elif suggestion_bias == "action" and has_content_change and certainty == "HIGH":
        lead = "review changed risk paths"
    elif suggestion_bias == "monitor":
        lead = "monitor and summarize" if not has_content_change and certainty != "LOW" else lead
    elif suggestion_bias == "explain":
        if has_content_change and certainty != "LOW":
            lead = "review changed paths and explain impact"
        elif certainty != "LOW":
            lead = "review and explain impact"

    return {"lead": lead}


def classify_guidance_mode(risk_signal: dict | None = None, cluster_guidance: dict | None = None) -> str:
    risk_signal = risk_signal or {}
    cluster_guidance = cluster_guidance or {}
    risk_delta = risk_signal.get("risk_delta", {})
    risk_action = (
        risk_signal.get("action_signal", {}).get("action")
        or cluster_guidance.get("risk_action")
    )
    if risk_delta.get("new_high_risk_paths"):
        return "new_high"
    if risk_action == "REVIEW_REQUIRED":
        return "new_high"
    if cluster_guidance.get("top_risk_cluster_has_content_change") or risk_delta.get("content_changed_paths"):
        return "content_changed"
    if risk_delta.get("persistent_high_risks"):
        return "persistent_same"
    if risk_action == "MONITOR":
        return "persistent_same"
    if risk_delta.get("medium_risk_delta", 0) >= MEDIUM_SURGE_THRESHOLD:
        return "medium_surge"
    return "steady"


def _format_cluster_descriptor(cluster_label: str | None, cluster_severity: str | None) -> str | None:
    if not cluster_label:
        return None
    severity_prefix = ""
    if cluster_severity and str(cluster_severity).lower() != "none":
        severity_prefix = f"{str(cluster_severity).title()}-risk "
    return f"{severity_prefix}{cluster_label}"


def build_summary_wording(
    *,
    primary_path: str | None,
    certainty: str,
    baseline_reason: str,
    cluster_label: str | None,
    cluster_severity: str | None,
    guidance_mode: str,
) -> dict:
    cluster_descriptor = _format_cluster_descriptor(cluster_label, cluster_severity)
    if guidance_mode == "new_high":
        lead = (
            "review immediately" if certainty == "HIGH"
            else "review recommended" if certainty == "MEDIUM"
            else "monitor and verify"
        )
    elif guidance_mode == "content_changed":
        lead = (
            "review changed risk paths" if certainty == "HIGH"
            else "verify recent changes" if certainty == "MEDIUM"
            else "monitor changed risk paths"
        )
    elif guidance_mode == "persistent_same":
        lead = (
            "review recommended for persistent risk" if certainty == "HIGH"
            else "monitor persistent risk paths" if certainty == "MEDIUM"
            else "confirm persistent risk if expected"
        )
    elif guidance_mode == "medium_surge":
        lead = "review recommended" if certainty != "LOW" else "monitor and verify"
    else:
        lead = "monitor and verify" if certainty == "LOW" else "review recommended"

    headline = f"{lead}: {primary_path}" if primary_path else lead
    if cluster_descriptor:
        headline = f"{headline} | {cluster_descriptor}"
    if baseline_reason == "stale_snapshot":
        headline = f"{headline} | verify against stale baseline"
    elif baseline_reason in {"initial_scan", "missing_snapshot"}:
        headline = f"{headline} | confirm baseline first"
    return {"summary_headline": headline}


def build_clustered_guidance(
    cluster_model: dict | None,
    risk_signal: dict | None = None,
) -> dict:
    cluster_model = cluster_model or {}
    risk_signal = risk_signal or {}
    top_cluster = (cluster_model.get("clusters") or [None])[0]
    if not top_cluster:
        return {
            "top_risk_cluster_label": None,
            "top_risk_cluster_severity": "none",
            "top_risk_cluster_path_count": 0,
            "top_risk_cluster_summary_reason": None,
            "top_risk_cluster_content_changed_count": 0,
            "top_risk_cluster_has_content_change": False,
            "top_risk_cluster_top_content_changed_path": None,
            "top_risk_cluster_top_content_change_hint": None,
            "cluster_recommended_next_step": "monitor current risk set before escalating",
            "cluster_recommended_review_scope": "none",
            "cluster_priority_bucket": "normal",
            "cluster_rank": 0,
            "cluster_rank_reason": None,
            "cluster_sort_key": None,
        }

    baseline_reason = risk_signal.get("baseline_reason", "missing_snapshot")
    certainty = risk_signal.get("action_signal", {}).get("certainty")
    if not certainty:
        certainty = "HIGH" if top_cluster["severity"] == "HIGH" else "MEDIUM"
    guidance_mode = classify_guidance_mode(risk_signal, {"top_risk_cluster_has_content_change": top_cluster.get("cluster_has_content_change", False)})
    cluster_id = top_cluster["cluster_id"]
    if cluster_id == "config" and top_cluster.get("new_high_count", 0) > 0:
        next_step = "review config risk cluster before reopen"
        scope = f"config files ({top_cluster['path_count']} paths, {top_cluster['new_high_count']} new high-risk)"
        bucket = "critical" if top_cluster["severity"] == "HIGH" else "high"
    elif cluster_id == "config" and top_cluster.get("cluster_has_content_change"):
        next_step = "review changed config risk paths before reopen" if certainty != "LOW" else "verify changed config risk paths before reopen"
        scope = f"changed config files ({top_cluster.get('cluster_content_changed_count', 0)} paths)"
        bucket = "high" if top_cluster["severity"] == "HIGH" else "elevated"
    elif cluster_id in {"runtime", "core"}:
        if top_cluster.get("cluster_has_content_change"):
            next_step = "verify recent runtime-sensitive changes before follow-up analysis"
            scope = f"changed {cluster_id} files ({top_cluster.get('cluster_content_changed_count', 0)} paths)"
        else:
            next_step = (
                "review runtime-sensitive cluster before follow-up analysis"
                if guidance_mode == "new_high" or certainty == "HIGH"
                else "monitor runtime-sensitive cluster before follow-up analysis"
            )
            scope = (
                f"{cluster_id} files ({top_cluster['path_count']} paths)"
                if guidance_mode != "persistent_same"
                else f"persistent {cluster_id} files ({top_cluster['path_count']} paths)"
            )
        bucket = "high" if top_cluster["severity"] == "HIGH" else "elevated"
    elif cluster_id == "docs":
        next_step = "monitor documentation-oriented risk cluster"
        scope = f"docs files ({top_cluster['path_count']} paths)"
        bucket = "watch"
    else:
        if top_cluster.get("cluster_has_content_change"):
            next_step = "inspect changed grouped risk cluster before broader review"
            scope = f"changed {cluster_id} files ({top_cluster.get('cluster_content_changed_count', 0)} paths)"
        else:
            next_step = (
                "inspect grouped risk cluster before broader review"
                if guidance_mode != "persistent_same"
                else "monitor grouped persistent risk cluster before broader review"
            )
            scope = (
                f"{cluster_id} files ({top_cluster['path_count']} paths)"
                if guidance_mode != "persistent_same"
                else f"persistent {cluster_id} files ({top_cluster['path_count']} paths)"
            )
        bucket = "elevated" if top_cluster["severity"] in {"HIGH", "MEDIUM"} else "watch"

    if baseline_reason == "stale_snapshot":
        next_step = f"{next_step} (verify stale baseline first)"
    elif baseline_reason in {"initial_scan", "missing_snapshot"}:
        next_step = f"{next_step} (confirm baseline first)"

    return {
        "top_risk_cluster_label": top_cluster["label"],
        "top_risk_cluster_severity": top_cluster["severity"],
        "top_risk_cluster_path_count": top_cluster["path_count"],
        "top_risk_cluster_summary_reason": top_cluster["summary_reason"],
        "top_risk_cluster_content_changed_count": top_cluster.get("cluster_content_changed_count", 0),
        "top_risk_cluster_has_content_change": top_cluster.get("cluster_has_content_change", False),
        "top_risk_cluster_top_content_changed_path": top_cluster.get("top_content_changed_path_in_cluster"),
        "top_risk_cluster_top_content_change_hint": top_cluster.get("top_content_change_hint_in_cluster"),
        "cluster_recommended_next_step": next_step,
        "cluster_recommended_review_scope": scope,
        "cluster_priority_bucket": bucket,
        "cluster_rank": top_cluster.get("cluster_rank", 1),
        "cluster_rank_reason": top_cluster.get("cluster_rank_reason"),
        "cluster_sort_key": top_cluster.get("cluster_sort_key"),
    }


def build_multi_cluster_compact_summary(
    cluster_model: dict | None,
    *,
    baseline_reason: str | None = None,
    max_lines: int = 2,
) -> dict:
    cluster_model = cluster_model or {}
    clusters = list(cluster_model.get("clusters") or [])
    if not clusters:
        return {
            "secondary_cluster_label": None,
            "secondary_cluster_severity": "none",
            "secondary_cluster_path_count": 0,
            "secondary_cluster_compact_line": None,
            "additional_cluster_note": None,
            "compact_cluster_lines": [],
        }

    top_cluster_id = cluster_model.get("top_cluster_id")
    secondary_candidates = [cluster for cluster in clusters if cluster.get("cluster_id") != top_cluster_id]
    secondary_clusters = secondary_candidates[:max_lines]
    compact_lines: list[str] = []

    for index, cluster in enumerate(secondary_clusters):
        prefix = "Secondary cluster" if index == 0 else "Additional cluster"
        line = f"{prefix}: {cluster['label']} ({cluster['severity']}, {cluster['path_count']} paths)"
        if cluster.get("cluster_has_content_change"):
            line = f"{line}, content changes detected"
        if baseline_reason == "stale_snapshot":
            line = f"{line} | verify against stale baseline"
        elif baseline_reason in {"initial_scan", "missing_snapshot"}:
            line = f"{line} | confirm against baseline"
        compact_lines.append(line)

    secondary_cluster = secondary_clusters[0] if secondary_clusters else {}
    additional_note = compact_lines[1] if len(compact_lines) > 1 else None
    return {
        "secondary_cluster_label": secondary_cluster.get("label"),
        "secondary_cluster_severity": secondary_cluster.get("severity", "none"),
        "secondary_cluster_path_count": secondary_cluster.get("path_count", 0),
        "secondary_cluster_compact_line": compact_lines[0] if compact_lines else None,
        "additional_cluster_note": additional_note,
        "compact_cluster_lines": compact_lines,
    }


def build_metadata_mismatch_hint(
    top_reopen_candidate: dict | None,
    cluster_guidance: dict | None,
) -> str | None:
    top_reopen_candidate = top_reopen_candidate or {}
    cluster_guidance = cluster_guidance or {}
    cluster_label = cluster_guidance.get("top_risk_cluster_label", "") or ""
    risk_profile = top_reopen_candidate.get("skill_risk_profile")
    if not cluster_label or not risk_profile:
        return None
    if "Runtime" in cluster_label and risk_profile == "monitoring":
        return "selected skill may not be ideal for runtime-sensitive cluster"
    if "Config" in cluster_label and risk_profile == "monitoring":
        return "selected skill may not fully cover config-sensitive cluster"
    return None


def rank_reopen_candidates(
    skills: list[dict],
    risk_signal: dict | None,
    priority_order: list[str] | None = None,
    last_skill_name: str | None = None,
) -> list[dict]:
    risk_signal = risk_signal or {}
    decision_weighting = risk_signal.get("decision_weighting") or score_risk_decision_signal(risk_signal)
    action_signal = risk_signal.get("action_signal", {})
    action = action_signal.get("action")
    certainty = action_signal.get("certainty", "LOW")
    baseline_status = risk_signal.get("baseline_status", "missing")
    risk_primary_path = action_signal.get("primary_path")
    risk_scope = classify_risk_path_scope(risk_primary_path)
    risk_delta = risk_signal.get("risk_delta", {})
    new_high_exists = bool(risk_delta.get("new_high_risk_paths", []))
    persistent_high_exists = bool(risk_delta.get("persistent_high_risks", []))
    priority_order = priority_order or []
    order_index = {name: idx for idx, name in enumerate(priority_order)}

    ranked = []
    for skill in skills:
        name = skill.get("name")
        if not name or name == last_skill_name:
            continue
        behavior_class = skill.get("behavior_class", "report")
        risk_profile = skill.get("risk_profile", "monitoring")
        handles_config_changes = bool(skill.get("handles_config_changes", False))
        handles_runtime_changes = bool(skill.get("handles_runtime_changes", False))
        prefers_reopen_on_high_risk = bool(skill.get("prefers_reopen_on_high_risk", False))
        review_cost = skill.get("review_cost", "low")
        score = decision_weighting.get("reopen_score", 0) * 10
        reasons = [f"risk_action={action}", f"certainty={certainty}", f"baseline={baseline_status}"]
        metadata_weight_applied = False

        if action == "REVIEW_REQUIRED":
            if behavior_class == "review":
                score += 30
                reasons.append("review_match")
            elif behavior_class in {"observe", "report"}:
                score += 14
                reasons.append("observe_match")
        elif action == "ALERT":
            if behavior_class == "review":
                score += 24
                reasons.append("review_alert")
            elif "classifier" in name:
                score += 14
                reasons.append("classifier_alert")
        elif action == "REVIEW_RECOMMENDED":
            if "classifier" in name:
                score += 22
                reasons.append("classifier_medium_surge")
            elif behavior_class in {"observe", "report"}:
                score += 12
                reasons.append("observe_medium_surge")
        elif action == "MONITOR" and "workspace" in name:
            score += 18
            reasons.append("workspace_monitor")

        if prefers_reopen_on_high_risk and action in {"REVIEW_REQUIRED", "ALERT"}:
            score += 8
            metadata_weight_applied = True
            reasons.append("prefers_reopen_on_high_risk")

        if risk_scope == "config" and handles_config_changes:
            score += 6
            metadata_weight_applied = True
            reasons.append("handles_config_changes")
        if risk_scope in {"runtime_core", "script"} and handles_runtime_changes:
            score += 6
            metadata_weight_applied = True
            reasons.append("handles_runtime_changes")

        if risk_profile == "monitoring" and action in {"REVIEW_REQUIRED", "ALERT"}:
            score -= 5
            metadata_weight_applied = True
            reasons.append("monitoring_penalty")
        elif risk_profile == "runtime_sensitive" and risk_scope in {"runtime_core", "script"}:
            score += 5
            metadata_weight_applied = True
            reasons.append("runtime_sensitive_bonus")

        if review_cost == "high" and certainty == "LOW":
            score -= 6
            metadata_weight_applied = True
            reasons.append("high_review_cost_low_certainty")

        if new_high_exists:
            score += 10
            reasons.append("new_high_risk")
        elif persistent_high_exists:
            score += 4
            reasons.append("persistent_high_risk")

        if certainty == "HIGH":
            score += 8
        elif certainty == "MEDIUM":
            score += 4

        if baseline_status == "fresh":
            score += 5
        elif baseline_status == "stale":
            score += 2

        if risk_scope == "config":
            if behavior_class == "review":
                score += 8
                reasons.append("config_priority")
            elif "classifier" in name:
                score += 5
                reasons.append("config_classifier")
        elif risk_scope in {"runtime_core", "script"}:
            if behavior_class == "review":
                score += 7
                reasons.append(f"{risk_scope}_review")
            elif "workspace" in name:
                score += 3
                reasons.append(f"{risk_scope}_workspace")

        tie_breaker = order_index.get(name, REOPEN_TIE_BREAKER_DEFAULT)
        sort_key = (-score, tie_breaker, name)
        ranked.append({
            "skill": name,
            "reopen_priority": score,
            "reopen_rank_reason": ", ".join(reasons),
            "reopen_sort_key": sort_key,
            "skill_risk_profile": risk_profile,
            "metadata_weight_applied": metadata_weight_applied,
            "suggestion_bias": skill.get("suggestion_bias", "explain"),
            "inferred_risk_metadata_used": skill.get("inferred_risk_metadata_used", False),
            "inferred_from": skill.get("inferred_from", "explicit"),
        })

    return sorted(ranked, key=lambda item: item["reopen_sort_key"])


def build_risk_suggestions(risk_signal: dict | None, ranked_candidates: list[dict] | None = None) -> list[dict]:
    risk_signal = risk_signal or {}
    action_signal = risk_signal.get("action_signal", {})
    decision_weighting = risk_signal.get("decision_weighting") or score_risk_decision_signal(risk_signal)
    action = action_signal.get("action")
    certainty = action_signal.get("certainty", "LOW")
    primary_path = action_signal.get("primary_path")
    baseline_status = risk_signal.get("baseline_status", "missing")
    baseline_reason = risk_signal.get("baseline_reason", _default_baseline_reason(baseline_status))
    top_candidate = ranked_candidates[0] if ranked_candidates else {}
    suggestion_bias = top_candidate.get("suggestion_bias", "neutral")
    risk_delta = risk_signal.get("risk_delta", {})
    has_new_high = bool(risk_delta.get("new_high_risk_paths", [])) or action == "REVIEW_REQUIRED"
    has_content_change = bool(risk_delta.get("content_changed_paths", []))
    has_persistent_high = bool(risk_delta.get("persistent_high_risks", []))

    if action in {None, "SAFE"}:
        return []

    lead = select_guidance_wording(
        certainty=certainty,
        has_new_high=has_new_high,
        has_content_change=has_content_change and not has_new_high,
        has_persistent_high=has_persistent_high,
        suggestion_bias=suggestion_bias,
    )["lead"]

    uncertainty_clause = ""
    if baseline_reason == "stale_snapshot":
        uncertainty_clause = " (stale baseline)"
    elif baseline_reason in {"initial_scan", "missing_snapshot"}:
        uncertainty_clause = " (baseline incomplete)"

    text = lead
    if primary_path:
        text = f"{lead}: {primary_path}"
    text = f"{text}{uncertainty_clause}"

    priority = decision_weighting.get("suggestion_priority", 0)
    if suggestion_bias == "action":
        priority += 8
    elif suggestion_bias == "monitor":
        priority -= 4
    priority = max(0, priority)

    return [{
        "priority": priority,
        "severity": decision_weighting.get("suggestion_severity", "none"),
        "certainty": certainty,
        "source": "risk_signal",
        "text": text,
        "action": action,
        "path": primary_path,
        "skill_risk_profile": top_candidate.get("skill_risk_profile"),
        "metadata_weight_applied": top_candidate.get("metadata_weight_applied", False),
    }]


def build_operator_guidance(risk_signal: dict | None) -> dict:
    risk_signal = risk_signal or {}
    action_signal = risk_signal.get("action_signal", {})
    action = action_signal.get("action", "SAFE")
    certainty = action_signal.get("certainty", "LOW")
    primary_path = action_signal.get("primary_path")
    scope = classify_risk_path_scope(primary_path)
    risk_delta = risk_signal.get("risk_delta", {})
    has_content_change = bool(risk_delta.get("content_changed_paths", []))
    has_persistent_high = bool(risk_delta.get("persistent_high_risks", []))
    baseline_reason = risk_signal.get("baseline_reason")

    if action == "REVIEW_REQUIRED" and scope == "config":
        next_step = "review config change before reopen"
        review_scope = "configuration boundary"
        bucket = "critical" if certainty == "HIGH" else "high"
    elif action == "MONITOR" and has_content_change and scope == "config":
        next_step = "review changed config risk paths before reopening broader analysis"
        review_scope = "changed config risk paths"
        bucket = "high" if certainty == "HIGH" else "elevated"
    elif action == "MONITOR" and has_content_change and scope in {"runtime_core", "script"}:
        next_step = "verify recent runtime changes before broader review"
        review_scope = "changed runtime execution path"
        bucket = "elevated"
    elif action in {"REVIEW_REQUIRED", "ALERT"} and scope in {"runtime_core", "script"}:
        next_step = "review execution path before follow-up analysis"
        review_scope = "runtime execution path"
        bucket = "high"
    elif action == "REVIEW_RECOMMENDED" and risk_delta.get("medium_risk_delta", 0) >= MEDIUM_SURGE_THRESHOLD:
        next_step = "inspect medium-risk file cluster"
        review_scope = "medium-risk cluster"
        bucket = "elevated"
    elif action == "MONITOR" and has_persistent_high:
        next_step = "monitor persistent risk paths before escalating" if certainty != "LOW" else "confirm persistent risk if expected"
        review_scope = "persistent risky files"
        bucket = "watch"
    elif action == "MONITOR":
        next_step = "monitor current risk set before escalating"
        review_scope = "current risky files"
        bucket = "watch"
    else:
        next_step = "no immediate review required"
        review_scope = "none"
        bucket = "normal"

    return {
        "recommended_next_step": next_step,
        "recommended_review_scope": review_scope,
        "priority_bucket": bucket,
    }


def build_review_summary_payload(
    operational_signal: dict | None = None,
    *,
    risk_signal: dict | None = None,
) -> dict:
    operational_signal = operational_signal or {}
    risk_signal = risk_signal or {}
    baseline_reason = operational_signal.get(
        "baseline_reason",
        risk_signal.get("baseline_reason", "missing_snapshot"),
    )
    certainty = (
        operational_signal.get("top_suggestion_certainty")
        or operational_signal.get("risk_certainty")
        or risk_signal.get("action_signal", {}).get("certainty")
        or "LOW"
    )
    primary_path = (
        operational_signal.get("risk_primary_path")
        or risk_signal.get("action_signal", {}).get("primary_path")
    )
    cluster_label = operational_signal.get("top_risk_cluster_label")
    cluster_severity = operational_signal.get("top_risk_cluster_severity")
    cluster_path_count = operational_signal.get("top_risk_cluster_path_count", 0)
    guidance_mode = classify_guidance_mode(risk_signal, operational_signal)
    compact_cluster_lines = operational_signal.get("compact_cluster_lines", [])
    headline = operational_signal.get("top_suggestion_text")
    if not headline:
        headline = build_summary_wording(
            primary_path=primary_path,
            certainty=certainty,
            baseline_reason=baseline_reason,
            cluster_label=cluster_label,
            cluster_severity=cluster_severity,
            guidance_mode=guidance_mode,
        )["summary_headline"]
    elif operational_signal.get("top_suggestion_text"):
        headline = build_summary_wording(
            primary_path=primary_path,
            certainty=certainty,
            baseline_reason=baseline_reason,
            cluster_label=cluster_label,
            cluster_severity=cluster_severity,
            guidance_mode=guidance_mode,
        )["summary_headline"]

    cluster_line = None
    if cluster_label:
        cluster_line = f"Top cluster: {cluster_label} ({cluster_path_count} paths, {cluster_severity})"
    cluster_content_line = None
    if operational_signal.get("top_risk_cluster_has_content_change"):
        cluster_content_target = (
            operational_signal.get("top_risk_cluster_top_content_changed_path")
            or f"{operational_signal.get('top_risk_cluster_content_changed_count', 0)} paths"
        )
        cluster_content_line = f"Content changes detected in top cluster: {cluster_content_target}"

    return {
        "summary_headline": headline,
        "summary_priority": operational_signal.get("top_suggestion_priority", operational_signal.get("risk_suggestion_priority", 0)),
        "summary_certainty": certainty,
        "summary_severity": operational_signal.get("top_suggestion_severity", operational_signal.get("risk_suggestion_severity", "none")),
        "summary_next_step": operational_signal.get("cluster_recommended_next_step") or operational_signal.get("recommended_next_step"),
        "summary_review_scope": operational_signal.get("cluster_recommended_review_scope") or operational_signal.get("recommended_review_scope"),
        "summary_cluster_line": cluster_line,
        "summary_secondary_cluster_line": compact_cluster_lines[0] if compact_cluster_lines else None,
        "summary_additional_cluster_note": compact_cluster_lines[1] if len(compact_cluster_lines) > 1 else None,
        "summary_cluster_content_line": cluster_content_line,
        "priority_bucket": operational_signal.get("priority_bucket", "normal"),
        "top_suggestion_text": operational_signal.get("top_suggestion_text"),
        "top_suggestion_priority": operational_signal.get("top_suggestion_priority", 0),
        "top_suggestion_severity": operational_signal.get("top_suggestion_severity", "none"),
        "top_suggestion_certainty": operational_signal.get("top_suggestion_certainty", "none"),
        "recommended_next_step": operational_signal.get("recommended_next_step"),
        "recommended_review_scope": operational_signal.get("recommended_review_scope"),
        "content_changed_count": operational_signal.get("content_changed_count", 0),
        "top_content_changed_path": operational_signal.get("top_content_changed_path"),
        "top_content_change_hint": operational_signal.get("top_content_change_hint"),
    }


def build_report_summary_payload(
    operational_signal: dict | None = None,
    *,
    risk_signal: dict | None = None,
) -> dict:
    return build_review_summary_payload(operational_signal, risk_signal=risk_signal)


def build_common_render_sections(render_payload: dict | None) -> list[dict]:
    render_payload = render_payload or {}
    sections = []

    headline = render_payload.get("summary_headline")
    if headline:
        sections.append({
            "title": "Headline",
            "lines": [headline],
        })

    action_lines = []
    next_step = (
        render_payload.get("summary_next_step")
        or render_payload.get("cluster_recommended_next_step")
        or render_payload.get("recommended_next_step")
    )
    review_scope = (
        render_payload.get("summary_review_scope")
        or render_payload.get("cluster_recommended_review_scope")
        or render_payload.get("recommended_review_scope")
    )
    if next_step:
        action_lines.append(f"next: {next_step}")
    if review_scope:
        action_lines.append(f"scope: {review_scope}")
    if action_lines:
        sections.append({"title": "Action", "lines": action_lines})

    priority_lines = []
    if render_payload.get("priority_bucket") is not None:
        priority_lines.append(f"bucket: {render_payload.get('priority_bucket')}")
    if render_payload.get("summary_priority") is not None:
        priority_lines.append(f"priority: {render_payload.get('summary_priority')}")
    if render_payload.get("summary_certainty") is not None:
        priority_lines.append(f"certainty: {render_payload.get('summary_certainty')}")
    if priority_lines:
        sections.append({"title": "Priority / Certainty", "lines": priority_lines})

    top_cluster_lines = []
    if render_payload.get("summary_cluster_line"):
        top_cluster_lines.append(render_payload["summary_cluster_line"])
    elif render_payload.get("top_risk_cluster_label"):
        cluster_label = render_payload.get("top_risk_cluster_label")
        cluster_severity = render_payload.get("top_risk_cluster_severity", "none")
        cluster_count = render_payload.get("top_risk_cluster_path_count", 0)
        top_cluster_lines.append(f"Top cluster: {cluster_label} ({cluster_count} paths, {cluster_severity})")
    if render_payload.get("summary_cluster_content_line"):
        top_cluster_lines.append(render_payload["summary_cluster_content_line"])
    elif render_payload.get("top_risk_cluster_has_content_change"):
        top_cluster_lines.append("Content changes detected in top cluster")
    elif render_payload.get("content_changed_count", 0):
        target = render_payload.get("top_content_changed_path") or f"{render_payload['content_changed_count']} paths"
        top_cluster_lines.append(f"Content changes detected in existing risk paths: {target}")
    if render_payload.get("top_risk_cluster_top_content_change_hint"):
        top_cluster_lines.append(f"Change hint: {render_payload.get('top_risk_cluster_top_content_change_hint')}")
    elif render_payload.get("top_content_change_hint"):
        top_cluster_lines.append(f"Change hint: {render_payload.get('top_content_change_hint')}")
    if top_cluster_lines:
        sections.append({"title": "Top Cluster", "lines": top_cluster_lines})

    secondary_lines = []
    if render_payload.get("summary_secondary_cluster_line"):
        secondary_lines.append(render_payload["summary_secondary_cluster_line"])
    elif render_payload.get("secondary_cluster_compact_line"):
        secondary_lines.append(render_payload["secondary_cluster_compact_line"])
    if render_payload.get("summary_additional_cluster_note"):
        secondary_lines.append(render_payload["summary_additional_cluster_note"])
    elif render_payload.get("additional_cluster_note"):
        secondary_lines.append(render_payload["additional_cluster_note"])
    if secondary_lines:
        sections.append({"title": "Secondary / Additional", "lines": secondary_lines})

    baseline_lines = []
    for value in (
        render_payload.get("summary_headline"),
        next_step,
        render_payload.get("cluster_recommended_next_step"),
        render_payload.get("recommended_next_step"),
    ):
        if not value:
            continue
        if "verify against stale baseline" in value:
            baseline_lines.append("verify against stale baseline")
            break
        if "confirm baseline first" in value or "confirm baseline before interpreting changes" in value:
            baseline_lines.append("confirm baseline first")
            break
    if baseline_lines:
        sections.append({"title": "Baseline Note", "lines": baseline_lines})

    metadata_lines = []
    if render_payload.get("metadata_mismatch_hint"):
        metadata_lines.append(render_payload["metadata_mismatch_hint"])
    if metadata_lines:
        sections.append({"title": "Metadata / Hints", "lines": metadata_lines})

    return sections


def build_review_summary_lines(summary_payload: dict | None) -> list[str]:
    sections = build_common_render_sections(summary_payload)
    if not sections:
        return []

    lines = []
    for section in sections:
        title = section.get("title")
        values = section.get("lines", [])
        if title == "Headline" and values:
            lines.append(f"- 운영 요약: {values[0]}")
        elif title == "Action":
            for value in values:
                if value.startswith("next: "):
                    lines.append(f"- 다음 단계: {value.replace('next: ', '', 1)}")
                elif value.startswith("scope: "):
                    lines.append(f"- 검토 범위: {value.replace('scope: ', '', 1)}")
        elif title == "Priority / Certainty":
            priority = summary_payload.get("summary_priority", 0)
            certainty = summary_payload.get("summary_certainty", "LOW")
            lines.append(f"- 우선순위: {priority} | 확실도: {certainty}")
        else:
            lines.extend(f"- {value}" for value in values)
    return lines


def build_operational_risk_signal(
    workspace: str | Path,
    paths: list[str | Path],
    now: datetime | None = None,
    max_age_seconds: int = RISK_SNAPSHOT_MAX_AGE_SECONDS,
) -> dict:
    current_snapshot = build_risk_snapshot(paths, workspace=workspace)
    baseline_snapshot = load_latest_risk_snapshot(workspace)
    baseline_meta = evaluate_snapshot_freshness(
        baseline_snapshot,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    risk_delta = compute_risk_delta(baseline_snapshot, current_snapshot, baseline_meta=baseline_meta)
    current_risk_summary = summarize_workspace_risks(paths)
    action_signal = build_action_signal(risk_delta, current_risk_summary)
    decision_weighting = score_risk_decision_signal({
        "action_signal": action_signal,
        "baseline_status": baseline_meta["baseline_status"],
        "baseline_reason": baseline_meta["baseline_reason"],
    })
    blocker_candidate = None
    if action_signal["action"] in {"REVIEW_REQUIRED", "ALERT", "REVIEW_RECOMMENDED"} and action_signal.get("primary_path"):
        blocker_candidate = f"risk:{action_signal['action']}({action_signal['primary_path']})"
    decision_weighting = score_risk_decision_signal({
        "action_signal": action_signal,
        "baseline_status": baseline_meta["baseline_status"],
        "baseline_reason": baseline_meta["baseline_reason"],
        "blocker_candidate": blocker_candidate,
    })

    return {
        "baseline_status": baseline_meta["baseline_status"],
        "baseline_created_at": baseline_meta["baseline_created_at"],
        "baseline_age_seconds": baseline_meta["baseline_age_seconds"],
        "baseline_stale": baseline_meta["baseline_stale"],
        "baseline_reason": baseline_meta["baseline_reason"],
        "current_snapshot": current_snapshot,
        "baseline_snapshot": baseline_snapshot,
        "risk_delta": risk_delta,
        "current_risk_summary": current_risk_summary,
        "action_signal": action_signal,
        "blocker_candidate": blocker_candidate,
        "decision_weighting": decision_weighting,
    }


def build_state_summary(changes: list[dict]) -> dict:
    external_changes = [change for change in changes if not change.get("self_artifact")]
    risky_changes = [change for change in external_changes if change.get("risk") == "HIGH"]
    return {
        "external_change": bool(external_changes),
        "risky_change": bool(risky_changes),
        "self_artifact_only": bool(changes) and not external_changes,
        "recommended_action": (
            "ignore"
            if not changes or not external_changes
            else "review_file"
            if risky_changes
            else "observe"
        ),
    }


def build_warning_signatures(changes: list[dict], state_summary: dict) -> list[str]:
    recommended_action = state_summary.get("recommended_action", "ignore")
    signatures = []
    for change in changes:
        if change.get("self_artifact") or change.get("risk") == "IGNORE":
            continue
        signatures.append(
            f"{change.get('normalized_path') or _normalize_path(change.get('path', ''))}|"
            f"{change.get('risk', 'MEDIUM')}|"
            f"{recommended_action}"
        )
    return sorted(set(signatures))


def should_suppress_warning(
    changes: list[dict],
    state_summary: dict,
    recent_signatures: list[str] | None = None,
) -> bool:
    recent_signatures = recent_signatures or []
    current_signatures = build_warning_signatures(changes, state_summary)
    if not current_signatures:
        return False
    recent_set = set(recent_signatures)
    return all(signature in recent_set for signature in current_signatures)


def collect_self_artifact_candidates(
    paths: list[str | Path],
    min_repetitions: int = 2,
) -> list[dict]:
    counts: dict[str, int] = {}
    original_paths: dict[str, str] = {}
    for path in paths:
        normalized = _normalize_path(path)
        original_paths.setdefault(normalized, str(path))
        counts[normalized] = counts.get(normalized, 0) + 1

    candidates = []
    for normalized, count in sorted(counts.items()):
        if count < min_repetitions:
            continue
        if is_self_artifact(normalized):
            continue
        risk = classify_risk(normalized, self_artifact=False)
        if risk != "MEDIUM":
            continue
        candidates.append({
            "path": original_paths[normalized],
            "normalized_path": normalized,
            "occurrences": count,
            "status": "review_needed",
            "reason": "repeated_unclassified_change",
        })
    return candidates


def build_operational_signal(
    changes: list[dict],
    recent_signatures: list[str] | None = None,
    recent_paths: list[str | Path] | None = None,
    approval_entries: list[dict] | None = None,
    risk_signal: dict | None = None,
    skills: list[dict] | None = None,
) -> dict:
    summary = build_state_summary(changes)
    suppressed = should_suppress_warning(changes, summary, recent_signatures=recent_signatures)
    warning_signatures = build_warning_signatures(changes, summary)
    approval_entries = approval_entries or []
    approval_status = "not_needed"
    operational_entries = [
        entry for entry in approval_entries
        if entry.get("type") == "operational_risk" or entry.get("source") == "operational_signal"
    ]
    if summary["recommended_action"] == "review_file" and not suppressed:
        existing_statuses = [
            entry.get("status", "pending")
            for entry in operational_entries
            if entry.get("signature") in warning_signatures
        ]
        if existing_statuses:
            if "pending" in existing_statuses:
                approval_status = "pending"
            elif "rejected" in existing_statuses:
                approval_status = "rejected"
            elif "approved" in existing_statuses:
                approval_status = "approved"
        else:
            approval_status = "review_needed"
    approval_required = (
        summary["recommended_action"] == "review_file"
        and not suppressed
        and approval_status in {"review_needed", "pending"}
    )
    candidate_paths = recent_paths if recent_paths is not None else [change.get("path", "") for change in changes]
    risk_signal = risk_signal or {}
    action_signal = risk_signal.get("action_signal", {})
    decision_weighting = risk_signal.get("decision_weighting") or score_risk_decision_signal(risk_signal)
    ranked_reopen_candidates = rank_reopen_candidates(skills or [], risk_signal, last_skill_name=None)
    top_reopen_candidate = ranked_reopen_candidates[0] if ranked_reopen_candidates else None
    risk_suggestions = build_risk_suggestions(risk_signal, ranked_candidates=ranked_reopen_candidates)
    cluster_model = build_risk_clusters(
        risk_signal.get("current_snapshot"),
        risk_signal.get("risk_delta"),
        operational_signal={"baseline_status": risk_signal.get("baseline_status", "missing")},
        skills=skills,
    )
    cluster_model = attach_content_summary_to_clusters(cluster_model, risk_signal.get("risk_delta"))
    cluster_guidance = build_clustered_guidance(cluster_model, risk_signal=risk_signal)
    compact_cluster_summary = build_multi_cluster_compact_summary(
        cluster_model,
        baseline_reason=risk_signal.get("baseline_reason"),
    )
    operator_guidance = build_operator_guidance(risk_signal)
    metadata_mismatch_hint = build_metadata_mismatch_hint(top_reopen_candidate, cluster_guidance)
    signal = {
        "summary": summary,
        "risk_summary": summarize_risk_changes(changes),
        "risk_action": action_signal.get("action"),
        "risk_reason": action_signal.get("reason"),
        "risk_primary_path": action_signal.get("primary_path"),
        "risk_certainty": action_signal.get("certainty"),
        "risk_suggestion_priority": decision_weighting.get("suggestion_priority", 0),
        "risk_suggestion_severity": decision_weighting.get("suggestion_severity", "none"),
        "risk_reopen_score": decision_weighting.get("reopen_score", 0),
        "baseline_status": risk_signal.get("baseline_status", "missing"),
        "baseline_reason": risk_signal.get(
            "baseline_reason",
            _default_baseline_reason(risk_signal.get("baseline_status", "missing")),
        ),
        "baseline_created_at": risk_signal.get("baseline_created_at"),
        "baseline_age_seconds": risk_signal.get("baseline_age_seconds"),
        "content_changed_count": risk_signal.get("risk_delta", {}).get("content_changed_count", 0),
        "content_changed_paths": risk_signal.get("risk_delta", {}).get("content_changed_paths", [])[:5],
        "top_content_changed_path": risk_signal.get("risk_delta", {}).get("top_content_changed_path"),
        "top_content_change_hint": risk_signal.get("risk_delta", {}).get("top_content_change_hint"),
        "blocker_candidate": risk_signal.get("blocker_candidate"),
        "risk_blocker_candidate": decision_weighting.get("blocker_candidate"),
        "risk_blocker_score": decision_weighting.get("blocker_score", 0),
        "risk_blocker_promoted": decision_weighting.get("blocker_promoted", False),
        "reopen_priority": top_reopen_candidate.get("reopen_priority", 0) if top_reopen_candidate else 0,
        "reopen_rank_reason": top_reopen_candidate.get("reopen_rank_reason") if top_reopen_candidate else None,
        "reopen_candidate": top_reopen_candidate.get("skill") if top_reopen_candidate else None,
        "skill_risk_profile": top_reopen_candidate.get("skill_risk_profile") if top_reopen_candidate else None,
        "metadata_weight_applied": top_reopen_candidate.get("metadata_weight_applied", False) if top_reopen_candidate else False,
        "inferred_risk_metadata_used": top_reopen_candidate.get("inferred_risk_metadata_used", False) if top_reopen_candidate else False,
        "inferred_from": top_reopen_candidate.get("inferred_from") if top_reopen_candidate else None,
        "prioritized_suggestions": risk_suggestions,
        "top_suggestion": risk_suggestions[0] if risk_suggestions else None,
        "top_suggestion_text": risk_suggestions[0]["text"] if risk_suggestions else None,
        "top_suggestion_priority": risk_suggestions[0]["priority"] if risk_suggestions else 0,
        "top_suggestion_severity": risk_suggestions[0]["severity"] if risk_suggestions else "none",
        "top_suggestion_certainty": risk_suggestions[0]["certainty"] if risk_suggestions else "none",
        "risk_clusters": cluster_model.get("clusters", []),
        "top_cluster_id": cluster_model.get("top_cluster_id"),
        **compact_cluster_summary,
        **cluster_guidance,
        **operator_guidance,
        "metadata_mismatch_hint": metadata_mismatch_hint,
        "suppressed": suppressed,
        "warning_signatures": warning_signatures,
        "approval": {
            "required": approval_required,
            "status": approval_status,
        },
        "self_artifact_candidates": collect_self_artifact_candidates(candidate_paths),
    }
    signal.update(build_review_summary_payload(signal, risk_signal=risk_signal))
    return signal


def resolve_operational_gate(signal: dict) -> dict:
    approval = signal.get("approval", {})
    summary = signal.get("summary", {})
    if summary.get("recommended_action") == "ignore":
        mode = "ignore"
    elif approval.get("status") == "approved":
        mode = "review_allowed"
    elif approval.get("status") == "rejected":
        mode = "blocked"
    elif approval.get("required") or approval.get("status") in {"review_needed", "pending"}:
        mode = "observe_only"
    else:
        mode = "observe_only" if summary.get("external_change") else "ignore"
    return {
        "mode": mode,
        "reason": approval.get("status", "not_needed"),
        "warning_signatures": signal.get("warning_signatures", []),
    }


def build_operational_gate_view(signal: dict, gate: dict) -> dict:
    approval = signal.get("approval", {})
    warning_signatures = signal.get("warning_signatures", [])
    signature = warning_signatures[0] if warning_signatures else None
    summary = signal.get("summary", {})
    target = None
    risk = None

    if signature:
        parts = signature.split("|")
        if parts:
            target = parts[0]
        if len(parts) >= 2:
            risk = parts[1]

    return {
        "gate_mode": gate.get("mode", "ignore"),
        "approval_status": approval.get("status", "not_needed"),
        "target": target,
        "signature": signature,
        "recommended_action": summary.get("recommended_action", "ignore"),
        "risk": risk,
    }


def build_operational_gate_view_from_approvals(approval_entries: list[dict] | None = None) -> dict:
    approval_entries = approval_entries or []
    operational_entries = [
        entry for entry in approval_entries
        if entry.get("type") == "operational_risk" or entry.get("source") == "operational_signal"
    ]
    if not operational_entries:
        return {
            "gate_mode": "ignore",
            "approval_status": "not_needed",
            "target": None,
            "signature": None,
            "recommended_action": "ignore",
            "risk": None,
        }

    latest = max(
        operational_entries,
        key=lambda entry: entry.get("created_at", ""),
    )
    status = latest.get("status", "pending")
    if status == "approved":
        gate_mode = "review_allowed"
    elif status == "rejected":
        gate_mode = "blocked"
    elif status == "pending":
        gate_mode = "observe_only"
    else:
        gate_mode = "observe_only"

    return {
        "gate_mode": gate_mode,
        "approval_status": status,
        "target": latest.get("target"),
        "signature": latest.get("signature"),
        "recommended_action": latest.get("recommended_action", "ignore"),
        "risk": latest.get("risk"),
    }


def summarize_operational_approvals(approval_entries: list[dict] | None = None) -> dict:
    approval_entries = approval_entries or []
    operational_entries = [
        entry for entry in approval_entries
        if entry.get("type") == "operational_risk" or entry.get("source") == "operational_signal"
    ]
    pending_count = sum(1 for entry in operational_entries if entry.get("status") == "pending")
    approved_count = sum(1 for entry in operational_entries if entry.get("status") == "approved")
    rejected_count = sum(1 for entry in operational_entries if entry.get("status") == "rejected")
    recent_targets: list[str] = []
    for entry in sorted(operational_entries, key=lambda item: item.get("created_at", ""), reverse=True):
        target = entry.get("target")
        if target and target not in recent_targets:
            recent_targets.append(target)
        if len(recent_targets) >= 5:
            break

    return {
        "total_operational_approvals_count": len(operational_entries),
        "pending_operational_approvals_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "recent_targets": recent_targets,
    }


def load_pending_approvals(approval_file: str | Path) -> list[dict]:
    approval_path = Path(approval_file)
    if not approval_path.exists():
        return []
    try:
        with open(approval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else [data]


def save_pending_approvals(approval_file: str | Path, entries: list[dict]) -> None:
    approval_path = Path(approval_file)
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    with open(approval_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def resolve_runtime_data_root(reference: str | Path | None = None) -> Path:
    runtime_root = os.getenv(RUNTIME_DATA_ENV_VAR)
    if runtime_root:
        return Path(runtime_root)

    reference_path = Path(reference) if reference is not None else Path.cwd()
    if reference_path.suffix:
        reference_path = reference_path.parent
    return reference_path / "runtime-data"


def _proposal_directories(reference: str | Path | None = None) -> dict[str, Path]:
    runtime_root = resolve_runtime_data_root(reference)
    return {
        "runtime_root": runtime_root,
        "proposals": runtime_root / PROPOSALS_DIRNAME,
        "staging": runtime_root / STAGING_DIRNAME,
        "review_decisions": runtime_root / REVIEW_DECISIONS_DIRNAME,
    }


def _ensure_proposal_directories(reference: str | Path | None = None) -> dict[str, Path]:
    directories = _proposal_directories(reference)
    for key in ("proposals", "staging", "review_decisions"):
        directories[key].mkdir(parents=True, exist_ok=True)
    return directories


def _build_proposal_id(source_review_id: str, target_paths: list[str] | None = None) -> str:
    target_paths = target_paths or []
    material = f"{source_review_id}|{'|'.join(target_paths)}"
    short_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]
    return f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{short_hash}"


def _infer_change_type(target_paths: list[str] | None = None) -> str:
    for path in target_paths or []:
        normalized = _normalize_path(path)
        suffix = Path(path).suffix.lower()
        if normalized.startswith(("config/", "configs/")):
            return "config_change"
        if normalized.startswith(("src/", "scripts/")) or suffix in HIGH_RISK_CODE_SUFFIXES:
            return "code_change"
    return "unknown"


def build_proposal_payload(
    review_entry: dict,
    *,
    proposal_id: str | None = None,
    created_at: datetime | None = None,
) -> dict:
    target_paths = []
    target = review_entry.get("target")
    if target:
        target_paths.append(target)
    elif review_entry.get("target_paths"):
        target_paths.extend(review_entry.get("target_paths", []))

    source_review_id = review_entry.get("signature") or review_entry.get("review_id") or "unknown"
    created_at = created_at or datetime.now()
    proposal_id = proposal_id or _build_proposal_id(source_review_id, target_paths)
    diff_hint = (
        review_entry.get("top_content_change_hint")
        or review_entry.get("top_risk_cluster_top_content_change_hint")
        or "none"
    )
    return {
        "proposal_id": proposal_id,
        "source_review_id": source_review_id,
        "created_at": created_at.isoformat(),
        "target_paths": target_paths,
        "summary": review_entry.get("summary_headline") or review_entry.get("top_suggestion") or review_entry.get("suggestion") or "none",
        "change_type": _infer_change_type(target_paths),
        "risk_context": {
            "top_cluster": review_entry.get("top_risk_cluster_label"),
            "severity": review_entry.get("top_risk_cluster_severity") or review_entry.get("risk"),
            "content_changed": bool(
                review_entry.get("top_risk_cluster_has_content_change")
                or review_entry.get("content_changed_count", 0)
                or review_entry.get("top_content_change_hint")
            ),
        },
        "diff_hint": diff_hint,
        "status": review_entry.get("status", "pending"),
    }


def save_proposal(proposal: dict, reference: str | Path | None = None) -> dict:
    directories = _ensure_proposal_directories(reference)
    proposal_path = directories["proposals"] / f"{proposal['proposal_id']}.json"
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "saved": True,
        "path": str(proposal_path),
        "proposal": proposal,
    }


def load_proposal(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    proposal_path = _proposal_directories(reference)["proposals"] / f"{proposal_id}.json"
    if not proposal_path.exists():
        return None
    try:
        return json.loads(proposal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_proposal_by_review_id(review_id: str, reference: str | Path | None = None) -> dict | None:
    proposals_dir = _proposal_directories(reference)["proposals"]
    if not proposals_dir.exists():
        return None
    for proposal_path in sorted(proposals_dir.glob("*.json")):
        try:
            payload = json.loads(proposal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("source_review_id") == review_id:
            return payload
    return None


def create_proposal(review_entry: dict, reference: str | Path | None = None) -> dict:
    existing = load_proposal_by_review_id(
        review_entry.get("signature") or review_entry.get("review_id") or "unknown",
        reference=reference,
    )
    if existing is not None:
        return {"created": False, "proposal": existing, "path": None}
    proposal = build_proposal_payload(review_entry)
    saved = save_proposal(proposal, reference=reference)
    return {"created": True, "proposal": saved["proposal"], "path": saved["path"]}


def _proposal_indicates_stale_or_missing_baseline(proposal: dict) -> str | None:
    for value in (
        proposal.get("summary"),
        proposal.get("diff_hint"),
    ):
        if not value:
            continue
        if "verify against stale baseline" in value:
            return "stale"
        if "confirm baseline first" in value or "confirm baseline before interpreting changes" in value:
            return "missing"
    return None


def build_apply_precheck(
    proposal: dict | None,
    *,
    allowed_prefixes: tuple[str, ...] = SAFE_APPLY_ALLOWED_PREFIXES,
) -> dict:
    proposal = proposal or {}
    target_paths = [str(path) for path in proposal.get("target_paths", [])]
    normalized_paths = [_normalize_path(path) for path in target_paths]
    allowed_target_paths = [
        path for path, normalized in zip(target_paths, normalized_paths)
        if any(normalized.startswith(prefix) for prefix in allowed_prefixes)
    ]
    blocked_target_paths = [path for path in target_paths if path not in allowed_target_paths]

    blockers: list[str] = ["workspace write not enabled"]
    warnings: list[str] = []
    operator_steps = [
        "review proposal content",
        "confirm apply remains manual-only",
    ]
    change_type = proposal.get("change_type", "unknown")
    baseline_state = _proposal_indicates_stale_or_missing_baseline(proposal)
    severity = (proposal.get("risk_context") or {}).get("severity")

    if change_type == "code_change":
        blockers.append("code_change requires manual operator validation")
    elif change_type == "unknown":
        blockers.append("unknown change_type remains blocked")
    elif change_type == "config_change":
        operator_steps.append("manually validate config semantics")
    else:
        blockers.append(f"{change_type} remains blocked")

    if blocked_target_paths:
        blockers.append("target path outside safe apply allowlist")

    if baseline_state == "stale":
        warnings.append("stale baseline verification recommended")
        blockers.append("baseline verification required before apply consideration")
        operator_steps.append("confirm baseline freshness")
    elif baseline_state == "missing":
        warnings.append("baseline confirmation recommended")
        blockers.append("baseline confirmation required before apply consideration")
        operator_steps.append("confirm baseline before interpreting changes")

    if severity == "HIGH":
        warnings.append("high-risk change requires manual operator review")

    risk_context = proposal.get("risk_context") or {}
    if risk_context.get("content_changed"):
        warnings.append("content-changed risk path should be reviewed manually")

    apply_mode = "blocked"
    apply_possible = False
    if (
        change_type == "config_change"
        and allowed_target_paths
        and not blocked_target_paths
        and baseline_state is None
    ):
        apply_mode = "dry_run_only"

    return {
        "apply_possible": apply_possible,
        "apply_mode": apply_mode,
        "apply_blockers": blockers,
        "apply_warnings": warnings,
        "allowed_target_paths": allowed_target_paths,
        "blocked_target_paths": blocked_target_paths,
        "path_policy_reason": "safe apply allowlist enforced",
        "operator_steps": operator_steps,
    }


def build_dry_run_payload(proposal: dict | None) -> dict:
    proposal = proposal or {}
    precheck = build_apply_precheck(proposal)
    return {
        "proposal_id": proposal.get("proposal_id"),
        "target_paths": proposal.get("target_paths", []),
        "apply_mode": precheck.get("apply_mode", "blocked"),
        "apply_blockers": precheck.get("apply_blockers", []),
        "apply_warnings": precheck.get("apply_warnings", []),
        "operator_steps": precheck.get("operator_steps", []),
    }


def build_rollback_plan(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    backup_targets = proposal.get("target_paths", [])
    return {
        "backup_required": bool(backup_targets),
        "backup_targets": backup_targets,
        "restore_strategy": "partial" if precheck.get("allowed_target_paths") else "full",
        "notes": "prepare manual restore path before any future apply step",
    }


def validate_apply_plan(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    checks = [
        {
            "name": "proposal approved",
            "passed": proposal.get("status") == "approved",
            "detail": f"status={proposal.get('status', 'unknown')}",
        },
        {
            "name": "apply mode not blocked",
            "passed": precheck.get("apply_mode") != "blocked",
            "detail": f"apply_mode={precheck.get('apply_mode', 'blocked')}",
        },
        {
            "name": "allowed target paths only",
            "passed": not precheck.get("blocked_target_paths"),
            "detail": ", ".join(precheck.get("blocked_target_paths", [])) or "ok",
        },
        {
            "name": "critical blockers absent",
            "passed": not precheck.get("apply_blockers"),
            "detail": ", ".join(precheck.get("apply_blockers", [])) or "ok",
        },
    ]
    return {
        "apply_ready": all(check["passed"] for check in checks),
        "checks": checks,
    }


def build_apply_plan(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    validation = validate_apply_plan(proposal, precheck=precheck)
    action = "modify"
    if proposal.get("change_type") == "unknown":
        action = "review"

    apply_plan_items = []
    if precheck.get("apply_mode") != "blocked":
        for path in proposal.get("target_paths", []):
            apply_plan_items.append({
                "target_path": path,
                "action": action,
                "summary": proposal.get("summary", "none"),
                "risk_level": (proposal.get("risk_context") or {}).get("severity", "unknown"),
            })

    return {
        "proposal_id": proposal.get("proposal_id"),
        "apply_mode": precheck.get("apply_mode", "blocked"),
        "apply_plan": apply_plan_items,
        "validation_checks": validation.get("checks", []),
        "rollback_plan": build_rollback_plan(proposal, precheck=precheck),
    }


def build_apply_dry_run(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    plan = build_apply_plan(proposal, precheck=precheck)
    affected_paths = [item["target_path"] for item in plan.get("apply_plan", [])]
    potential_conflicts = list(precheck.get("blocked_target_paths", []))
    return {
        "proposal_id": proposal.get("proposal_id"),
        "apply_mode": precheck.get("apply_mode", "blocked"),
        "dry_run_result": "no workspace changes performed",
        "affected_paths": affected_paths,
        "potential_conflicts": potential_conflicts,
        "change_count": len(affected_paths),
    }


def build_atomicity_policy(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    target_paths = proposal.get("target_paths", [])
    transaction_id = str(uuid4())
    blockers = []
    warnings = []

    if precheck.get("apply_mode") == "blocked":
        blockers.append("blocked apply mode cannot enter transaction")
    if precheck.get("blocked_target_paths"):
        blockers.append("transaction scope includes blocked target paths")
    if not target_paths:
        blockers.append("transaction scope requires at least one target path")

    if (proposal.get("risk_context") or {}).get("severity") == "HIGH":
        warnings.append("high-risk transaction requires manual verification")
    if (proposal.get("risk_context") or {}).get("content_changed"):
        warnings.append("content-changed targets should be validated before any future write")

    return {
        "transaction_id": transaction_id,
        "proposal_id": proposal.get("proposal_id"),
        "atomicity_mode": "all_or_nothing",
        "transaction_scope": {
            "target_paths": target_paths,
            "change_count": len(target_paths),
        },
        "atomicity_requirements": [
            "all backups available before apply",
            "all validation checks pass before first write",
            "rollback possible for all target paths",
        ],
        "atomicity_blockers": blockers,
        "atomicity_warnings": warnings,
    }


def build_rollback_triggers(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    triggers = [
        "pre_apply_validation_failed",
        "post_apply_validation_failed",
        "backup_missing",
        "partial_apply_detected",
        "target_mismatch_detected",
        "unexpected_target_count_mismatch",
    ]
    if precheck.get("apply_mode") == "blocked":
        triggers.insert(0, "blocked_apply_mode")
    return {
        "rollback_required": True,
        "rollback_triggers": triggers,
        "recovery_mode": "full_rollback_required",
    }


def build_backup_plan(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    backup_targets = proposal.get("target_paths", [])
    blockers = []
    if not backup_targets:
        blockers.append("no target paths available for backup scope")
    if precheck.get("blocked_target_paths"):
        blockers.append("backup scope contains blocked target paths")
    return {
        "backup_required": True,
        "backup_scope": "all_target_paths",
        "backup_targets": backup_targets,
        "backup_format": "copy_before_apply",
        "backup_preconditions": [
            "sufficient disk space not yet verified",
            "all target paths resolvable",
        ],
        "backup_blockers": blockers,
    }


def build_pre_apply_validation(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    backup_plan = build_backup_plan(proposal, precheck=precheck)
    rollback_plan = build_rollback_plan(proposal, precheck=precheck)
    checks = [
        {"name": "proposal approved", "passed": proposal.get("status") == "approved"},
        {"name": "apply mode not blocked", "passed": precheck.get("apply_mode") != "blocked"},
        {"name": "allowed target paths only", "passed": not precheck.get("blocked_target_paths")},
        {"name": "backup plan complete", "passed": not backup_plan.get("backup_blockers")},
        {"name": "rollback plan complete", "passed": bool(rollback_plan.get("backup_targets"))},
        {"name": "no critical blockers", "passed": not precheck.get("apply_blockers")},
    ]
    return {
        "checks": checks,
        "validation_ready": all(check["passed"] for check in checks),
    }


def build_post_apply_validation(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    expected_count = len(proposal.get("target_paths", []))
    checks = [
        {"name": "target count matches expected", "passed": expected_count >= 0},
        {"name": "no partial apply markers", "passed": False},
        {"name": "rollback remains available", "passed": bool(proposal.get("target_paths"))},
        {"name": "changed files match plan", "passed": False},
    ]
    return {
        "checks": checks,
        "validation_mode": "post_apply_placeholder",
    }


def build_failure_handling_policy(proposal: dict | None = None) -> dict:
    return {
        "partial_apply_policy": "forbidden",
        "on_partial_apply": "require_full_rollback",
        "on_unknown_state": "halt_and_require_manual_review",
        "failure_visibility": "must_record_transaction_state",
    }


def build_apply_transaction(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    return {
        "transaction_id": build_atomicity_policy(proposal, precheck=precheck)["transaction_id"],
        "proposal_id": proposal.get("proposal_id"),
        "atomicity_policy": build_atomicity_policy(proposal, precheck=precheck),
        "rollback_triggers": build_rollback_triggers(proposal, precheck=precheck),
        "backup_plan": build_backup_plan(proposal, precheck=precheck),
        "pre_apply_validation": build_pre_apply_validation(proposal, precheck=precheck),
        "post_apply_validation": build_post_apply_validation(proposal, precheck=precheck),
        "failure_handling_policy": build_failure_handling_policy(proposal),
    }


def build_apply_state_machine() -> dict:
    return {
        "state_machine_version": "v1",
        "allowed_transitions": {
            "proposed": ["approved", "halted_for_manual_review"],
            "approved": ["staged", "halted_for_manual_review"],
            "staged": ["prechecked", "halted_for_manual_review"],
            "prechecked": ["transaction_ready", "halted_for_manual_review"],
            "transaction_ready": ["backup_ready", "halted_for_manual_review"],
            "backup_ready": ["validation_passed", "halted_for_manual_review"],
            "validation_passed": ["apply_started"],
            "apply_started": ["apply_succeeded", "apply_failed", "rollback_required"],
            "apply_failed": ["rollback_required", "halted_for_manual_review"],
            "rollback_required": ["rollback_completed", "halted_for_manual_review"],
        },
    }


def build_transaction_state_contract(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    return {
        "transaction_id_format": "uuid_v4",
        "transaction_id_generation_rule": "uuid_v4",
        "transaction_id_requirements": [
            "string identifier",
            "globally unique with very low collision probability",
            "generated once before transaction state recording",
        ],
        "transaction_id_recording_order": "generated_before_transaction_state_recorded",
        "transaction_fields": [
            "transaction_id",
            "proposal_id",
            "state",
            "target_paths",
            "validation_status",
            "backup_status",
            "terminal_marker",
        ],
        "required_ordering": [
            "transaction state recorded before backup",
            "backup recorded before validation_passed",
            "validation_passed recorded before apply_started",
        ],
        "terminal_state_rules": [
            "exactly one terminal state required",
            "no success state without validation_passed",
            "blocked apply mode must halt before apply_started",
        ],
        "transaction_scope": {
            "proposal_id": proposal.get("proposal_id"),
            "target_count": len(proposal.get("target_paths", [])),
            "apply_mode": precheck.get("apply_mode", "blocked"),
        },
    }


def build_target_resolution_contract(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    target_paths = [str(path) for path in proposal.get("target_paths", [])]
    normalized_targets = [_normalize_path(path) for path in target_paths]
    return {
        "path_resolution_mode": "strict",
        "candidate_targets": target_paths,
        "normalized_targets": normalized_targets,
        "path_rules": [
            "normalize_relative_paths",
            "reject_parent_traversal",
            "reject_absolute_paths",
            "deduplicate_targets_before_apply",
        ],
        "abort_conditions": [
            "blocked_target_detected",
            "target_count_mismatch",
            "unresolvable_target_path",
        ],
        "policy_view": {
            "allowed_target_paths": precheck.get("allowed_target_paths", []),
            "blocked_target_paths": precheck.get("blocked_target_paths", []),
        },
    }


def build_atomic_write_contract(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    return {
        "atomic_write_mode": "temp_then_rename",
        "write_requirements": [
            "all backups ready before first write",
            "all validations passed before first write",
            "writes must be recorded in transaction state",
        ],
        "write_ordering_rules": [
            "no write before backup_ready",
            "no write before validation_passed",
            "all target writes belong to one transaction scope",
        ],
        "partial_write_policy": "forbidden",
        "failure_on_rename": "rollback_required",
        "policy_view": {
            "apply_mode": precheck.get("apply_mode", "blocked"),
            "target_count": len(proposal.get("target_paths", [])),
        },
    }


def build_backup_materialization_contract(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    atomicity = build_atomicity_policy(proposal, precheck=precheck)
    return {
        "backup_strategy": "copy_before_apply",
        "backup_scope": "all_target_paths",
        "backup_naming_rule": f"{atomicity['transaction_id']}.<basename>.bak",
        "backup_requirements": [
            "all targets resolved",
            "backup metadata recorded before apply",
            "backup materialization completed before first write",
        ],
        "abort_conditions": [
            "backup_target_missing",
            "backup_not_materialized",
        ],
    }


def build_rollback_execution_contract(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    return {
        "rollback_mode": "full_only",
        "rollback_requirements": [
            "all backup artifacts available",
            "transaction state recorded",
        ],
        "rollback_triggers": build_rollback_triggers(proposal, precheck=precheck).get("rollback_triggers", []),
        "on_rollback_failure": "halt_and_require_manual_review",
        "partial_rollback_policy": "forbidden",
    }


def build_apply_abort_conditions(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    abort_conditions = [
        "blocked_apply_mode",
        "critical_blocker_present",
        "missing_backup_contract",
        "failed_validation",
        "unknown_target_path_state",
        "incomplete_transaction_metadata",
    ]
    if precheck.get("blocked_target_paths"):
        abort_conditions.append("blocked_target_detected")
    return {
        "abort_conditions": abort_conditions,
        "halt_conditions": [
            "rollback_failure_detected",
            "unknown_transaction_state",
            "manual_review_required",
        ],
        "manual_review_required_conditions": [
            "blocked_apply_mode",
            "high_risk_change",
            "content_changed_risk_path",
        ],
    }


def build_transaction_markers() -> dict:
    return {
        "markers": [
            "apply_started",
            "apply_succeeded",
            "apply_failed",
            "rollback_started",
            "rollback_completed",
        ],
        "marker_rules": [
            "exactly one terminal marker required",
            "no success marker without validation_passed",
        ],
        "terminal_marker_rule_summary": "exactly one terminal marker required",
    }


def build_idempotency_policy() -> dict:
    return {
        "mode": "strict",
        "rules": [
            "no duplicate writes",
            "no duplicate markers",
            "no state mutation after terminal marker",
            "repeated execution of the same transaction_id must be a no-op once terminal",
        ],
    }


def build_transaction_runtime_storage() -> dict:
    return {
        "path_pattern": "runtime-data/runtime/<transaction_id>.json",
        "separation": "runtime_state_separate_from_staging",
        "purpose": [
            "track execution state",
            "enable rollback trace",
            "record markers",
        ],
        "storage_rules": [
            "runtime transaction state must not be embedded into staging proposal sidecars",
            "runtime state is append/update capable during execution lifecycle",
            "staging sidecars remain static contract metadata",
        ],
    }


def build_execution_prohibitions() -> dict:
    return {
        "rules": [
            "actual apply implementation is not part of this phase",
            "no file writes are allowed",
            "no backup files are created",
            "no rollback is executed",
            "no subprocess execution",
            "no automatic apply trigger",
        ],
        "notice": "This specification defines constraints for future execution and must not be interpreted as permission to execute apply.",
    }


def build_real_apply_gate(
    proposal: dict | None,
    *,
    flags: dict | None = None,
    manual_confirmation: bool = False,
    allowed_prefixes: tuple[str, ...] = REAL_APPLY_ALLOWED_PREFIXES,
) -> dict:
    proposal = proposal or {}
    flags = flags or {}
    target_paths = [str(path) for path in proposal.get("target_paths", [])]
    normalized_paths = [_normalize_path(path) for path in target_paths]
    allowed_real_paths = [
        path for path, normalized in zip(target_paths, normalized_paths)
        if any(normalized.startswith(prefix) for prefix in allowed_prefixes)
    ]
    blocked_real_paths = [path for path in target_paths if path not in allowed_real_paths]

    enable_requirements = [
        "ENABLE_REAL_APPLY flag set",
        "manual confirmation present",
        "proposal approved",
        "only allowlisted real workspace paths",
        "backup root under runtime-data/live_backups",
        "audit logging contract defined",
    ]
    required_flags = {
        "ENABLE_REAL_APPLY": bool(flags.get("ENABLE_REAL_APPLY", False)),
        "REQUIRE_MANUAL_CONFIRMATION": bool(flags.get("REQUIRE_MANUAL_CONFIRMATION", True)),
    }
    enable_blockers = []

    if not required_flags["ENABLE_REAL_APPLY"]:
        enable_blockers.append("real apply feature flag not enabled")
    if required_flags["REQUIRE_MANUAL_CONFIRMATION"] and not manual_confirmation:
        enable_blockers.append("manual confirmation required for real apply")
    if proposal.get("status") != "approved":
        enable_blockers.append("proposal must be approved before real apply consideration")
    if blocked_real_paths:
        enable_blockers.append("real apply target path outside live allowlist")
    if not target_paths:
        enable_blockers.append("real apply requires at least one target path")

    required_conditions = [
        "manual-only invocation",
        "no daemon or loop integration",
        "live backups rooted under runtime-data",
        "audit log recorded for every attempted real apply",
    ]
    real_apply_enabled = not enable_blockers
    return {
        "real_apply_enabled": real_apply_enabled,
        "enable_mode": "manual_only" if real_apply_enabled else "blocked",
        "enable_blockers": enable_blockers,
        "enable_requirements": enable_requirements,
        "required_flags": required_flags,
        "required_conditions": required_conditions,
        "manual_invocation_contract": {
            "mode": "manual_only",
            "required_confirmation_flag": "--confirm-real-apply",
            "double_confirmation_recommended": True,
            "non_interactive_automatic_invocation": "forbidden",
        },
        "allowed_real_paths": allowed_real_paths,
        "blocked_real_paths": blocked_real_paths,
        "path_policy_reason": "live workspace allowlist enforced",
        "live_backup_root": {
            "path_pattern": REAL_APPLY_BACKUP_ROOT_PATTERN,
            "workspace_internal_backup": "forbidden",
            "backup_root_scope": "runtime-data only",
        },
        "audit_logging_contract": {
            "required": True,
            "required_fields": REAL_APPLY_AUDIT_FIELDS,
            "result_visibility": "must_record_attempt_and_outcome",
        },
        "default_state": "denied_by_default",
    }


def build_executor_spec(proposal: dict | None, precheck: dict | None = None) -> dict:
    proposal = proposal or {}
    precheck = precheck or build_apply_precheck(proposal)
    return {
        "executor_spec_version": "v1",
        "proposal_id": proposal.get("proposal_id"),
        "transaction_id_format": "uuid_v4",
        "state_machine": build_apply_state_machine(),
        "transaction_state_contract": build_transaction_state_contract(proposal, precheck=precheck),
        "target_resolution_contract": build_target_resolution_contract(proposal, precheck=precheck),
        "atomic_write_contract": build_atomic_write_contract(proposal, precheck=precheck),
        "backup_materialization_contract": build_backup_materialization_contract(proposal, precheck=precheck),
        "rollback_execution_contract": build_rollback_execution_contract(proposal, precheck=precheck),
        "apply_abort_conditions": build_apply_abort_conditions(proposal, precheck=precheck),
        "transaction_markers": build_transaction_markers(),
        "transaction_runtime_storage": build_transaction_runtime_storage(),
        "idempotency_policy": build_idempotency_policy(),
        "execution_prohibitions": build_execution_prohibitions(),
    }


def load_staging_precheck(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    precheck_path = _proposal_directories(reference)["staging"] / f"{proposal_id}.precheck.json"
    if not precheck_path.exists():
        return None
    try:
        return json.loads(precheck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_staging_apply_plan(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    plan_path = _proposal_directories(reference)["staging"] / f"{proposal_id}.apply_plan.json"
    if not plan_path.exists():
        return None
    try:
        return json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_staging_apply_transaction(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    transaction_path = _proposal_directories(reference)["staging"] / f"{proposal_id}.transaction.json"
    if not transaction_path.exists():
        return None
    try:
        return json.loads(transaction_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_staging_executor_spec(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    spec_path = _proposal_directories(reference)["staging"] / f"{proposal_id}.executor_spec.json"
    if not spec_path.exists():
        return None
    try:
        return json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def record_review_decision(
    review_id: str,
    proposal_id: str | None,
    decision: str,
    *,
    reference: str | Path | None = None,
    reason: str | None = None,
    operator: str | None = None,
) -> dict:
    directories = _ensure_proposal_directories(reference)
    payload = {
        "review_id": review_id,
        "proposal_id": proposal_id,
        "decision": decision,
        "decided_at": datetime.now().isoformat(),
        "reason": reason or "none",
        "operator": operator,
    }
    filename = f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.sha256((review_id + str(proposal_id)).encode('utf-8')).hexdigest()[:10]}.json"
    decision_path = directories["review_decisions"] / filename
    decision_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = str(decision_path)
    return payload


def update_proposal_status(
    review_id: str,
    status: str,
    *,
    reference: str | Path | None = None,
) -> dict | None:
    proposal = load_proposal_by_review_id(review_id, reference=reference)
    if proposal is None:
        return None
    proposal["status"] = status
    save_proposal(proposal, reference=reference)
    return proposal


def move_to_staging(proposal_id: str, reference: str | Path | None = None) -> dict | None:
    proposal = load_proposal(proposal_id, reference=reference)
    if proposal is None:
        return None
    directories = _ensure_proposal_directories(reference)
    staged_payload = dict(proposal)
    staged_payload["status"] = "approved"
    precheck = build_apply_precheck(staged_payload)
    apply_plan_payload = {
        "proposal_id": proposal_id,
        "apply_mode": precheck.get("apply_mode", "blocked"),
        "apply_plan": build_apply_plan(staged_payload, precheck=precheck).get("apply_plan", []),
        "validation_checks": validate_apply_plan(staged_payload, precheck=precheck).get("checks", []),
        "rollback_plan": build_rollback_plan(staged_payload, precheck=precheck),
        "dry_run": build_apply_dry_run(staged_payload, precheck=precheck),
    }
    transaction_payload = build_apply_transaction(staged_payload, precheck=precheck)
    executor_spec_payload = build_executor_spec(staged_payload, precheck=precheck)
    staging_path = directories["staging"] / f"{proposal_id}.json"
    staging_path.write_text(json.dumps(staged_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    precheck_payload = build_dry_run_payload(staged_payload)
    precheck_path = directories["staging"] / f"{proposal_id}.precheck.json"
    precheck_path.write_text(json.dumps(precheck_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_plan_path = directories["staging"] / f"{proposal_id}.apply_plan.json"
    apply_plan_path.write_text(json.dumps(apply_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    transaction_path = directories["staging"] / f"{proposal_id}.transaction.json"
    transaction_path.write_text(json.dumps(transaction_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    executor_spec_path = directories["staging"] / f"{proposal_id}.executor_spec.json"
    executor_spec_path.write_text(json.dumps(executor_spec_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "staged": True,
        "path": str(staging_path),
        "proposal": staged_payload,
        "precheck_path": str(precheck_path),
        "precheck": precheck_payload,
        "apply_plan_path": str(apply_plan_path),
        "apply_plan": apply_plan_payload,
        "transaction_path": str(transaction_path),
        "transaction": transaction_payload,
        "executor_spec_path": str(executor_spec_path),
        "executor_spec": executor_spec_payload,
    }


def process_review_decision(
    review_id: str,
    decision: str,
    *,
    reference: str | Path | None = None,
    reason: str | None = None,
    operator: str | None = None,
) -> dict:
    proposal = update_proposal_status(review_id, "approved" if decision == "approved" else "rejected", reference=reference)
    decision_record = record_review_decision(
        review_id,
        proposal.get("proposal_id") if proposal else None,
        decision,
        reference=reference,
        reason=reason,
        operator=operator,
    )
    staged = None
    if decision == "approved" and proposal is not None:
        staged = move_to_staging(proposal["proposal_id"], reference=reference)
    return {
        "proposal": proposal,
        "decision": decision_record,
        "staged": staged,
    }


def create_pending_approvals(
    changes: list[dict],
    state_summary: dict,
    approval_file: str | Path,
    operational_signal: dict | None = None,
) -> dict:
    existing = load_pending_approvals(approval_file)
    warning_signatures = build_warning_signatures(changes, state_summary)
    indexed_existing = {entry.get("signature"): entry for entry in existing if entry.get("signature")}
    created = []

    for change in changes:
        if change.get("self_artifact") or change.get("risk") == "IGNORE":
            continue
        signature = (
            f"{change.get('normalized_path') or _normalize_path(change.get('path', ''))}|"
            f"{change.get('risk', 'MEDIUM')}|"
            f"{state_summary.get('recommended_action', 'ignore')}"
        )
        if signature not in warning_signatures:
            continue
        if signature in indexed_existing:
            continue
        entry = {
            "signature": signature,
            "target": change.get("path"),
            "risk": change.get("risk", "MEDIUM"),
            "recommended_action": state_summary.get("recommended_action", "ignore"),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "type": "operational_risk",
            "source": "operational_signal",
        }
        if operational_signal:
            entry.update({
                "top_suggestion": operational_signal.get("top_suggestion_text"),
                "suggestion_priority": operational_signal.get("top_suggestion_priority", 0),
                "suggestion_severity": operational_signal.get("top_suggestion_severity", "none"),
                "suggestion_certainty": operational_signal.get("top_suggestion_certainty", "none"),
                "recommended_next_step": operational_signal.get("recommended_next_step"),
                "recommended_review_scope": operational_signal.get("recommended_review_scope"),
                "priority_bucket": operational_signal.get("priority_bucket"),
                "summary_headline": operational_signal.get("summary_headline"),
                "summary_priority": operational_signal.get("summary_priority", 0),
                "summary_certainty": operational_signal.get("summary_certainty", "none"),
                "summary_next_step": operational_signal.get("summary_next_step"),
                "summary_review_scope": operational_signal.get("summary_review_scope"),
                "top_risk_cluster_label": operational_signal.get("top_risk_cluster_label"),
                "top_risk_cluster_severity": operational_signal.get("top_risk_cluster_severity"),
                "top_risk_cluster_path_count": operational_signal.get("top_risk_cluster_path_count", 0),
                "cluster_recommended_next_step": operational_signal.get("cluster_recommended_next_step"),
                "cluster_recommended_review_scope": operational_signal.get("cluster_recommended_review_scope"),
                "cluster_priority_bucket": operational_signal.get("cluster_priority_bucket"),
                "top_risk_cluster_has_content_change": operational_signal.get("top_risk_cluster_has_content_change", False),
                "top_risk_cluster_top_content_change_hint": operational_signal.get("top_risk_cluster_top_content_change_hint"),
                "top_content_change_hint": operational_signal.get("top_content_change_hint"),
                "content_changed_count": operational_signal.get("content_changed_count", 0),
            })
        existing.append(entry)
        indexed_existing[signature] = entry
        created.append(entry)
        create_proposal(entry, reference=approval_file)

    if created:
        save_pending_approvals(approval_file, existing)
    return {
        "created": created,
        "entries": existing,
    }


def update_pending_approval_status(
    approval_file: str | Path,
    signature: str,
    status: str,
) -> dict | None:
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError(f"unsupported approval status: {status}")

    entries = load_pending_approvals(approval_file)
    updated = None
    for entry in entries:
        if entry.get("signature") == signature:
            entry["status"] = status
            updated = entry
            break
    if updated is not None:
        save_pending_approvals(approval_file, entries)
    return updated


def _snapshot_entries(state: dict, decision_only: bool = False) -> set[tuple[str, int | None]]:
    file_details = state.get("file_details", [])
    entries: set[tuple[str, int | None]] = set()
    if file_details:
        for item in file_details:
            path = item.get("path")
            if not path:
                continue
            if decision_only and is_self_artifact(path):
                continue
            entries.add((path, item.get("size")))
        return entries

    for path in state.get("files", []):
        if decision_only and is_self_artifact(path):
            continue
        entries.add((path, None))
    return entries


def build_decision_snapshot(state: dict) -> dict:
    decision_files = [
        item for item in state.get("file_details", [])
        if not is_self_artifact(item.get("path", ""))
    ]
    if not decision_files and state.get("files"):
        decision_files = [
            {"path": path, "size": 0}
            for path in state.get("files", [])
            if not is_self_artifact(path)
        ]

    return {
        "files": [item["path"] for item in decision_files],
        "file_details": decision_files,
        "total_files": len(decision_files),
        "total_size_bytes": sum(item.get("size", 0) for item in decision_files),
    }


def compute_state_diff(previous_state: dict | None, current_state: dict | None) -> dict:
    previous_state = previous_state or {}
    current_state = current_state or {}

    prev_full = _snapshot_entries(previous_state, decision_only=False)
    curr_full = _snapshot_entries(current_state, decision_only=False)
    prev_decision = _snapshot_entries(previous_state, decision_only=True)
    curr_decision = _snapshot_entries(current_state, decision_only=True)

    added_full_entries = curr_full - prev_full
    removed_full_entries = prev_full - curr_full
    added_paths = sorted(path for path, _ in added_full_entries)
    removed_paths = sorted(path for path, _ in removed_full_entries)

    added_self = sorted(path for path in added_paths if is_self_artifact(path))
    removed_self = sorted(path for path in removed_paths if is_self_artifact(path))
    added_external = sorted(path for path in added_paths if not is_self_artifact(path))
    removed_external = sorted(path for path in removed_paths if not is_self_artifact(path))

    diff = StateDiff(
        full_changed=curr_full != prev_full,
        decision_changed=curr_decision != prev_decision,
        self_artifact_changed=bool(added_self or removed_self),
        external_changed=bool(added_external or removed_external or (curr_decision != prev_decision)),
        added_paths=added_paths,
        removed_paths=removed_paths,
        added_self_artifacts=added_self,
        removed_self_artifacts=removed_self,
        added_external_paths=added_external,
        removed_external_paths=removed_external,
    )
    return asdict(diff)


def aggregate_extensions(file_details: list[dict]) -> dict[str, int]:
    ext_counts: dict[str, int] = {}
    for item in file_details:
        ext = os.path.splitext(item["path"])[1] or "(no ext)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    return ext_counts


def aggregate_type_counts(ext_counts: dict[str, int]) -> dict[str, int]:
    code_exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".cs", ".go", ".rs", ".cpp", ".c", ".h", ".hpp"}
    doc_exts = {".md", ".txt", ".rst", ".pdf", ".docx"}
    log_exts = {".log", ".jsonl"}

    type_counts = {"code": 0, "doc": 0, "log": 0, "other": 0}
    for ext, count in ext_counts.items():
        if ext in code_exts:
            type_counts["code"] += count
        elif ext in doc_exts:
            type_counts["doc"] += count
        elif ext in log_exts:
            type_counts["log"] += count
        else:
            type_counts["other"] += count
    return type_counts


def scan_workspace(
    workspace: str,
    exclude_dirs: set[str] | None = None,
    exclude_file_patterns: tuple[str, ...] | None = None,
) -> dict:
    exclude_dirs = set(DEFAULT_EXCLUDED_DIRS if exclude_dirs is None else exclude_dirs)
    exclude_file_patterns = exclude_file_patterns or DEFAULT_EXCLUDED_FILE_PATTERNS
    files: list[dict] = []
    dirs: list[str] = []
    total_size = 0
    seen_file_ids: set[tuple[int, int]] = set()
    excluded_files: list[dict] = []

    for root, dirnames, filenames in os.walk(workspace, followlinks=False):
        filtered_dirs = []
        for dirname in dirnames:
            if dirname.startswith(".") or dirname in exclude_dirs:
                continue
            full_dir = os.path.join(root, dirname)
            if os.path.islink(full_dir):
                continue
            filtered_dirs.append(dirname)
        dirnames[:] = filtered_dirs

        rel_root = os.path.relpath(root, workspace)
        for dirname in dirnames:
            dirs.append(os.path.join(rel_root, dirname) if rel_root != "." else dirname)

        for filename in filenames:
            if filename.startswith("."):
                continue
            full_path = os.path.join(root, filename)
            if os.path.islink(full_path):
                continue

            try:
                stat_result = os.stat(full_path, follow_symlinks=False)
            except OSError:
                continue

            rel_path = os.path.join(rel_root, filename) if rel_root != "." else filename
            if any(fnmatch.fnmatch(filename, pattern) for pattern in exclude_file_patterns):
                excluded_files.append({
                    "path": rel_path,
                    "size": stat_result.st_size,
                    "reason": "pattern_excluded",
                })
                continue

            inode = getattr(stat_result, "st_ino", 0)
            if inode:
                file_id = (getattr(stat_result, "st_dev", 0), inode)
            else:
                file_id = ("path", os.path.realpath(full_path))
            if file_id in seen_file_ids:
                continue
            seen_file_ids.add(file_id)

            files.append({"path": rel_path, "size": stat_result.st_size})
            total_size += stat_result.st_size

    ext_counts = aggregate_extensions(files)
    type_counts = aggregate_type_counts(ext_counts)
    decision_snapshot = build_decision_snapshot({
        "files": [item["path"] for item in files],
        "file_details": files,
    })
    state = {
        "files": [item["path"] for item in files],
        "file_details": files,
        "dirs": dirs,
        "total_files": len(files),
        "total_dirs": len(dirs),
        "total_size_bytes": total_size,
        "ext_counts": ext_counts,
        "type_counts": type_counts,
        "excluded_files": excluded_files,
        "excluded_large_files": [
            item for item in excluded_files
            if item["size"] >= EXCLUDED_LARGE_FILE_BYTES
        ],
        "decision_snapshot": decision_snapshot,
        "decision_files": decision_snapshot["files"],
        "decision_file_details": decision_snapshot["file_details"],
        "decision_total_files": decision_snapshot["total_files"],
        "decision_total_size_bytes": decision_snapshot["total_size_bytes"],
        "scanned_at": datetime.now().isoformat(),
    }
    logger.info(
        f"[Metrics] files={state['total_files']} dirs={state['total_dirs']} "
        f"total_bytes={state['total_size_bytes']} included_paths={len(state['files'])} "
        f"excluded_paths={len(state['excluded_files'])}"
    )
    return state
