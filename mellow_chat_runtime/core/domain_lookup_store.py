from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional


class DomainLookupStore:
    """Small JSON-backed domain store for chatbot context lookup."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self._data_path = data_path
        self._lock = RLock()
        self._data: Dict[str, Any] = {
            "personas": {
                "default": {
                    "id": "default",
                    "name": "Narrator",
                    "description": "A concise in-world guide who keeps continuity and tone.",
                }
            },
            "user_profiles": {},
            "lorebook": {},
            "memories": {},
            "world_state": {
                "default": {
                    "location": "Unknown",
                    "time": "Unknown",
                    "state": "Stable",
                }
            },
            "dialogue_priority": {
                "default": {
                    "major_weight": 1.0,
                    "minor_weight": 0.5,
                    "rules": "Major characters speak first unless minor has urgent state change.",
                }
            },
        }
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._data_path:
            return
        if not self._data_path.exists():
            return
        raw = json.loads(self._data_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            self._data.update(raw)

    def _save_to_disk(self) -> None:
        if not self._data_path:
            return
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._data_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_persona(self, persona_id: str = "default") -> Dict[str, Any]:
        return dict(self._data.get("personas", {}).get(persona_id, self._data["personas"]["default"]))

    def get_user_profile(self, profile_id: str) -> Dict[str, Any]:
        return dict(self._data.get("user_profiles", {}).get(profile_id, {}))

    def get_lore(self, topic: str) -> Dict[str, Any]:
        return dict(self._data.get("lorebook", {}).get(topic, {}))

    def get_memory_and_possessions(self, character_id: str) -> Dict[str, Any]:
        return dict(self._data.get("memories", {}).get(character_id, {"important": [], "possessions": []}))

    def get_world_state(self, world_id: str = "default") -> Dict[str, Any]:
        return dict(self._data.get("world_state", {}).get(world_id, self._data["world_state"]["default"]))

    def get_dialogue_priority(self, scene_id: str = "default") -> Dict[str, Any]:
        return dict(self._data.get("dialogue_priority", {}).get(scene_id, self._data["dialogue_priority"]["default"]))

    def upsert(self, section: str, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            target = self._data.setdefault(section, {})
            if isinstance(target, dict):
                target[key] = value
                self._save_to_disk()


_global_store: Optional[DomainLookupStore] = None


def get_domain_store(data_path: Optional[Path] = None) -> DomainLookupStore:
    global _global_store
    if _global_store is None:
        _global_store = DomainLookupStore(data_path=data_path)
    return _global_store
