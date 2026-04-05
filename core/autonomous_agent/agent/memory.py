"""
memory.py — 상태/이력 분리형 메모리 시스템

역할:
- agent_state.json에 현재 상태만 저장
- history/history_current.jsonl 에 append 전용 이력 저장
- archive/memory/ 에 회전 스냅샷/레거시 백업 보관
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("memory")

RECENT_ACTION_COOLDOWN_SECONDS = 3600
STATE_MAX_BYTES = 256 * 1024
HISTORY_MAX_BYTES = 5 * 1024 * 1024
LEGACY_IMPORT_MAX_BYTES = 50 * 1024 * 1024
RECENT_ACTION_LIMIT = 10
RECENT_FALLBACK_LIMIT = 5
RECENT_SCORE_LIMIT = 10
RUNTIME_HISTORY_LIMIT = 50
FALLBACK_NAMES = {"report_only", "change_summarizer", "memory_analyzer", "create", "wait", "noop"}
REPORT_PATH_RE = re.compile(r"(reports/[^\s]+\.md|generated_[^\s]+\.md)")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _trim_text(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def summarize_recent_actions(
    recent_actions: list[dict] | None,
    cooldown_seconds: int = RECENT_ACTION_COOLDOWN_SECONDS,
    skill_cooldowns: dict[str, int] | None = None,
    now: datetime | None = None,
) -> list[dict]:
    now = now or _utc_now()
    summary: list[dict] = []

    for entry in recent_actions or []:
        executed_at = _parse_utc_timestamp(entry.get("executed_at"))
        if executed_at is None:
            continue

        skill_name = entry.get("skill")
        effective_cooldown = skill_cooldowns.get(skill_name, cooldown_seconds) if skill_cooldowns else cooldown_seconds
        cooldown_until = executed_at + timedelta(seconds=effective_cooldown)
        age_seconds = max(0, int((now - executed_at).total_seconds()))
        normalized = dict(entry)
        normalized.update({
            "summary": _trim_text(entry.get("summary", "")),
            "executed_at": _format_utc_timestamp(executed_at),
            "cooldown_until": _format_utc_timestamp(cooldown_until),
            "cooldown_seconds": effective_cooldown,
            "age_seconds": age_seconds,
            "on_cooldown": now < cooldown_until,
        })
        summary.append(normalized)

    return summary


def is_skill_on_cooldown(
    skill_name: str,
    recent_actions: list[dict] | None,
    cooldown_seconds: int = RECENT_ACTION_COOLDOWN_SECONDS,
    skill_cooldowns: dict[str, int] | None = None,
    now: datetime | None = None,
) -> bool:
    return any(
        entry.get("skill") == skill_name and entry.get("on_cooldown")
        for entry in summarize_recent_actions(
            recent_actions,
            cooldown_seconds=cooldown_seconds,
            skill_cooldowns=skill_cooldowns,
            now=now,
        )
    )


class Memory:
    def __init__(
        self,
        filepath: str = "agent_memory.json",
        state_file: str | None = None,
        history_dir: str | None = None,
        archive_dir: str | None = None,
        state_max_bytes: int = STATE_MAX_BYTES,
        history_max_bytes: int = HISTORY_MAX_BYTES,
        legacy_import_max_bytes: int = LEGACY_IMPORT_MAX_BYTES,
    ):
        base_dir = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
        self.legacy_file = filepath
        self.state_file = state_file or os.path.join(base_dir, "agent_state.json")
        self.history_dir = history_dir or os.path.join(base_dir, "history")
        self.history_current_file = os.path.join(self.history_dir, "history_current.jsonl")
        self.archive_dir = archive_dir or os.path.join(base_dir, "archive", "memory")
        self.state_max_bytes = state_max_bytes
        self.history_max_bytes = history_max_bytes
        self.legacy_import_max_bytes = legacy_import_max_bytes
        self.base_dir = base_dir
        self.data = None
        self._storage_events = self._new_storage_events()

    def load(self) -> dict:
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        self._storage_events = self._new_storage_events()

        if os.path.exists(self.state_file):
            state = self._load_state_file()
        elif os.path.exists(self.legacy_file):
            state = self._migrate_legacy_memory()
        else:
            state = self._default_state()
            self._atomic_write_json(self.state_file, state)
            print("[Memory] 새 상태 저장소 초기화")

        history_tail = self._tail_history_events(10)
        self.data = self._build_runtime_data(state, history_tail)
        print(f"[Memory] 상태 로드 완료 (사이클 {self.data['metadata']['total_cycles']}회)")
        return self.data

    def save(self) -> None:
        state = self._build_persisted_state()
        state["trend"] = self._compute_trend_from_scores(state.get("recent_scores", []))
        state["last_run_at"] = _format_utc_timestamp(_utc_now())
        self._atomic_write_json(self.state_file, state)
        self._warn_if_state_large()
        self._sync_runtime_state(state)
        print(f"[Memory] 저장 완료 → {self.state_file}")

    def add_history(self, entry: dict) -> None:
        event = self._compact_history_event(entry)
        self._append_history_event(event)

        self.data["history"].append(event)
        self.data["history"] = self.data["history"][-RUNTIME_HISTORY_LIMIT:]
        if event.get("score") is not None:
            self.data["recent_scores"].append(event["score"])
            self.data["recent_scores"] = self.data["recent_scores"][-RECENT_SCORE_LIMIT:]
        if event.get("success"):
            self.data["last_success_at"] = event["timestamp"]
        self.data["trend"] = self._compute_trend_from_scores(self.data["recent_scores"])
        self._rotate_history_if_needed()

    def set_state(self, state: dict) -> None:
        self.data["last_state"] = state

    def set_goals(self, goals: list[str]) -> None:
        self.data["goals"] = goals

    def increment_cycle(self) -> int:
        self.data["current_cycle"] += 1
        self.data["metadata"]["total_cycles"] = self.data["current_cycle"]
        return self.data["current_cycle"]

    def get_recent_history(self, n: int = 5) -> list[dict]:
        history = self._tail_history_events(n)
        self.data["history"] = history[-RUNTIME_HISTORY_LIMIT:]
        return history

    def record_action(self, skill_name: str, summary: str = "", report_path: str | None = None) -> None:
        entry = {
            "skill": skill_name,
            "summary": _trim_text(summary),
            "report_path": report_path or self._extract_report_path(summary),
            "executed_at": _format_utc_timestamp(_utc_now()),
        }
        self.data["recent_actions"].append(entry)
        self.data["recent_actions"] = self.data["recent_actions"][-RECENT_ACTION_LIMIT:]

        if skill_name in FALLBACK_NAMES:
            self.data["recent_fallbacks"].append(entry)
            self.data["recent_fallbacks"] = self.data["recent_fallbacks"][-RECENT_FALLBACK_LIMIT:]

    def is_recent_action(
        self,
        skill_name: str,
        cooldown_seconds: int = RECENT_ACTION_COOLDOWN_SECONDS,
    ) -> bool:
        return is_skill_on_cooldown(
            skill_name,
            self.data.get("recent_actions", []),
            cooldown_seconds=cooldown_seconds,
        )

    def get_recent_actions(self, n: int = 5, skill_cooldowns: dict[str, int] | None = None) -> list[dict]:
        return summarize_recent_actions(self.data.get("recent_actions", [])[-n:], skill_cooldowns=skill_cooldowns)

    def _default_state(self) -> dict:
        return {
            "current_cycle": 0,
            "recent_actions": [],
            "recent_fallbacks": [],
            "recent_scores": [],
            "trend": {"trend": "no_data", "avg_score": 0, "samples": 0},
            "last_run_at": None,
            "last_success_at": None,
        }

    def get_storage_status(self) -> dict:
        try:
            state_size = os.path.getsize(self.state_file)
        except OSError:
            state_size = 0
        try:
            history_size = os.path.getsize(self.history_current_file)
        except OSError:
            history_size = 0

        archived = bool(self._storage_events["history_rotated"] or self._storage_events["legacy_archived"])
        return {
            "state_bytes": state_size,
            "history_bytes": history_size,
            "rotated": bool(self._storage_events["history_rotated"]),
            "archived": archived,
            "recent_actions": len(self.data.get("recent_actions", [])) if self.data else 0,
            "history_rotated_files": list(self._storage_events["history_rotated"]),
            "legacy_archived_files": list(self._storage_events["legacy_archived"]),
            "state_warning": self._storage_events["state_warning"],
        }

    def format_storage_status(self, status: dict | None = None) -> str:
        status = status or self.get_storage_status()
        return (
            f"[Storage] state={self._format_bytes(status['state_bytes'])} "
            f"history={self._format_bytes(status['history_bytes'])} "
            f"rotated={'yes' if status['rotated'] else 'no'} "
            f"archived={'yes' if status['archived'] else 'no'} "
            f"recent_actions={status['recent_actions']}"
        )

    def log_storage_status(self) -> str:
        status = self.get_storage_status()
        line = self.format_storage_status(status)
        logger.info(line)
        self._storage_events = self._new_storage_events()
        return line

    def get_score_trend(self) -> dict:
        trend = self._compute_trend_from_scores(self.data.get("recent_scores", []) if self.data else [])
        if self.data is not None:
            self.data["trend"] = trend
        return trend

    @staticmethod
    def _format_bytes(value: int) -> str:
        if value >= 1024 * 1024:
            return f"{round(value / (1024 * 1024))}MB"
        return f"{max(1, round(value / 1024)) if value else 0}KB"

    @staticmethod
    def _new_storage_events() -> dict:
        return {
            "history_rotated": [],
            "legacy_archived": [],
            "state_warning": False,
        }

    def _load_state_file(self) -> dict:
        with open(self.state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        default_state = self._default_state()
        default_state.update(state)
        default_state["recent_actions"] = summarize_recent_actions(default_state.get("recent_actions", []))[-RECENT_ACTION_LIMIT:]
        default_state["recent_fallbacks"] = summarize_recent_actions(default_state.get("recent_fallbacks", []))[-RECENT_FALLBACK_LIMIT:]
        default_state["recent_scores"] = list(default_state.get("recent_scores", []))[-RECENT_SCORE_LIMIT:]
        default_state["trend"] = self._compute_trend_from_scores(default_state["recent_scores"])
        return default_state

    def _build_runtime_data(self, state: dict, history_tail: list[dict]) -> dict:
        return {
            "goals": [],
            "history": history_tail[-RUNTIME_HISTORY_LIMIT:],
            "recent_actions": state.get("recent_actions", []),
            "recent_fallbacks": state.get("recent_fallbacks", []),
            "recent_scores": state.get("recent_scores", []),
            "trend": state.get("trend", {"trend": "no_data", "avg_score": 0, "samples": 0}),
            "last_run_at": state.get("last_run_at"),
            "last_success_at": state.get("last_success_at"),
            "last_state": {},
            "current_cycle": state.get("current_cycle", 0),
            "metadata": {
                "total_cycles": state.get("current_cycle", 0),
                "last_updated": state.get("last_run_at"),
            },
        }

    def _build_persisted_state(self) -> dict:
        return {
            "current_cycle": self.data.get("current_cycle", 0),
            "recent_actions": [
                {
                    "skill": item.get("skill"),
                    "summary": _trim_text(item.get("summary", "")),
                    "report_path": item.get("report_path"),
                    "executed_at": item.get("executed_at"),
                }
                for item in self.data.get("recent_actions", [])[-RECENT_ACTION_LIMIT:]
            ],
            "recent_fallbacks": [
                {
                    "skill": item.get("skill"),
                    "summary": _trim_text(item.get("summary", "")),
                    "report_path": item.get("report_path"),
                    "executed_at": item.get("executed_at"),
                }
                for item in self.data.get("recent_fallbacks", [])[-RECENT_FALLBACK_LIMIT:]
            ],
            "recent_scores": list(self.data.get("recent_scores", []))[-RECENT_SCORE_LIMIT:],
            "trend": self.data.get("trend", {"trend": "no_data", "avg_score": 0, "samples": 0}),
            "last_run_at": self.data.get("last_run_at"),
            "last_success_at": self.data.get("last_success_at"),
        }

    def _sync_runtime_state(self, state: dict) -> None:
        self.data["current_cycle"] = state["current_cycle"]
        self.data["recent_actions"] = state["recent_actions"]
        self.data["recent_fallbacks"] = state["recent_fallbacks"]
        self.data["recent_scores"] = state["recent_scores"]
        self.data["trend"] = state["trend"]
        self.data["last_run_at"] = state["last_run_at"]
        self.data["last_success_at"] = state["last_success_at"]
        self.data["metadata"]["total_cycles"] = state["current_cycle"]
        self.data["metadata"]["last_updated"] = state["last_run_at"]

    def _atomic_write_json(self, path: str, payload: dict) -> None:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def _append_history_event(self, event: dict) -> None:
        with open(self.history_current_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _history_files(self) -> list[str]:
        files = []
        if os.path.isdir(self.history_dir):
            for name in os.listdir(self.history_dir):
                if name == "history_current.jsonl" or (
                    name.startswith("history_") and name.endswith(".jsonl")
                ):
                    files.append(os.path.join(self.history_dir, name))
        return sorted(files, key=lambda path: (os.path.basename(path) == "history_current.jsonl", path))

    def _tail_history_events(self, n: int) -> list[dict]:
        events: list[dict] = []
        files = self._history_files()
        for path in reversed(files):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(events) >= n:
                    break
            if len(events) >= n:
                break
        return list(reversed(events))

    def _compact_history_event(self, entry: dict) -> dict:
        timestamp = _format_utc_timestamp(_utc_now())
        action = entry.get("action", {})
        result = entry.get("result", {})
        evaluation = entry.get("evaluation", {})
        action_type = action.get("type", "unknown")
        source = action.get("source", "")
        skill_name = action.get("skill_name")
        fallback_name = action.get("fallback_kind") or (
            action.get("type") if source == "cooldown_fallback" else None
        )
        event_type = "fallback" if source == "cooldown_fallback" else ("skill" if action_type == "skill" else "action")
        report_path = (
            result.get("report_file")
            or result.get("created_file")
            or self._extract_report_path(result.get("output", ""))
        )
        summary = _trim_text(result.get("output") or action.get("description") or "")
        return {
            "timestamp": timestamp,
            "cycle": entry.get("cycle"),
            "event": event_type,
            "action_type": action_type,
            "skill_name": skill_name,
            "fallback_name": fallback_name,
            "action_source": result.get("meta", {}).get("action_source") or action.get("action_source") or source,
            "work_type": result.get("meta", {}).get("work_type") or fallback_name or skill_name or action_type,
            "score": evaluation.get("score"),
            "status": evaluation.get("status"),
            "grade": evaluation.get("grade"),
            "success": result.get("success"),
            "report_path": report_path,
            "summary": summary,
        }

    def _extract_report_path(self, text: str) -> str | None:
        if not text:
            return None
        match = REPORT_PATH_RE.search(text.replace("\\", "/"))
        return match.group(1) if match else None

    def _compute_trend_from_scores(self, scores: list[int]) -> dict:
        scores = scores[-RECENT_SCORE_LIMIT:]
        if not scores:
            return {"trend": "no_data", "avg_score": 0, "samples": 0}
        avg = round(sum(scores) / len(scores), 1)
        if len(scores) >= 2:
            split = max(1, len(scores) // 2)
            first_half = sum(scores[:split]) / split
            second_half = sum(scores[split:]) / max(1, len(scores) - split)
            if second_half > first_half + 5:
                trend = "improving"
            elif second_half < first_half - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient"
        return {"trend": trend, "avg_score": avg, "samples": len(scores), "recent_scores": scores}

    def _warn_if_state_large(self) -> None:
        try:
            size = os.path.getsize(self.state_file)
        except OSError:
            return
        if size > self.state_max_bytes:
            self._storage_events["state_warning"] = True
            logger.warning("[Storage] warning: agent_state.json exceeds 256KB")

    def _rotate_history_if_needed(self) -> None:
        try:
            current_size = os.path.getsize(self.history_current_file)
        except OSError:
            return
        if current_size <= self.history_max_bytes:
            return

        stamp = datetime.now().strftime("%Y%m%d")
        index = 1
        while True:
            rotated_name = f"history_{stamp}_{index:02d}.jsonl"
            rotated_path = os.path.join(self.history_dir, rotated_name)
            if not os.path.exists(rotated_path):
                break
            index += 1

        os.replace(self.history_current_file, rotated_path)
        snapshot_name = datetime.now().strftime("state_%Y%m%d_%H%M%S.json")
        self._atomic_write_json(os.path.join(self.archive_dir, snapshot_name), self._build_persisted_state())
        self._storage_events["history_rotated"].append(rotated_name)
        self._storage_events["legacy_archived"].append(snapshot_name)
        logger.info(f"[Storage] history rotated -> {rotated_name}")
        logger.info(f"[Memory] history rotation: {rotated_name}")

    def _migrate_legacy_memory(self) -> dict:
        legacy_size = os.path.getsize(self.legacy_file)
        backup_name = datetime.now().strftime("legacy_agent_memory_%Y%m%d_%H%M%S.json")
        backup_path = os.path.join(self.archive_dir, backup_name)

        if legacy_size > self.legacy_import_max_bytes:
            shutil.move(self.legacy_file, backup_path)
            rel_backup = os.path.relpath(backup_path, self.base_dir).replace("\\", "/")
            self._storage_events["legacy_archived"].append(rel_backup)
            logger.info(f"[Storage] legacy memory archived -> {rel_backup}")
            logger.warning(
                f"[Memory] legacy memory too large to import safely ({legacy_size} bytes). "
                f"Archived to {backup_path} and initialized fresh state."
            )
            state = self._default_state()
            self._atomic_write_json(self.state_file, state)
            return state

        with open(self.legacy_file, "r", encoding="utf-8") as f:
            legacy = json.load(f)

        state = self._default_state()
        state["current_cycle"] = legacy.get("metadata", {}).get("total_cycles", 0)
        state["recent_actions"] = summarize_recent_actions(legacy.get("recent_actions", []))[-RECENT_ACTION_LIMIT:]
        state["recent_fallbacks"] = [
            item for item in state["recent_actions"]
            if item.get("skill") in FALLBACK_NAMES
        ][-RECENT_FALLBACK_LIMIT:]

        history = legacy.get("history", [])
        recent_scores = [
            item.get("evaluation", {}).get("score")
            for item in history
            if item.get("evaluation", {}).get("score") is not None
        ][-RECENT_SCORE_LIMIT:]
        state["recent_scores"] = recent_scores
        state["trend"] = self._compute_trend_from_scores(recent_scores)
        state["last_run_at"] = legacy.get("metadata", {}).get("last_updated")

        success_entries = [
            item for item in history
            if item.get("result", {}).get("success")
        ]
        if success_entries:
            last_success = success_entries[-1].get("timestamp") or success_entries[-1].get("evaluation", {}).get("evaluated_at")
            state["last_success_at"] = last_success

        for item in history:
            compact = self._compact_history_event(item)
            self._append_history_event(compact)
        shutil.move(self.legacy_file, backup_path)
        rel_backup = os.path.relpath(backup_path, self.base_dir).replace("\\", "/")
        self._storage_events["legacy_archived"].append(rel_backup)
        logger.info(f"[Storage] legacy memory archived -> {rel_backup}")
        self._atomic_write_json(self.state_file, state)
        logger.info(f"[Memory] legacy memory migrated -> {self.state_file}, backup={backup_path}")
        return state
