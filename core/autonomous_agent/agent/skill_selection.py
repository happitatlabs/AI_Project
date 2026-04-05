import re
from pathlib import Path

from .generated_skill_sandbox import list_generated_skill_queue, load_generated_skill_draft
from .skill_loader import load_skills


DEFAULT_BUILTIN_CAPABILITIES = {
    "report": ["read_only", "summary", "reporting"],
    "observe": ["read_only", "summary", "monitoring"],
    "review": ["read_only", "analysis", "review"],
    "execute": ["execution_candidate"],
    "write": ["write_candidate"],
}
TASK_HINTS = {
    "runtime_state_summarizer": ("runtime", "state", "marker", "transaction", "summarize"),
    "proposal_summary_formatter": ("proposal", "summary", "format", "staging"),
    "review_note_compactor": ("review", "note", "compact", "dedupe"),
    "diff_hint_reformatter": ("diff", "hint", "reformat", "patch"),
    "workspace_reporter": ("workspace", "report", "status", "summary"),
    "code_reviewer": ("code", "review", "bug", "regression"),
    "file_classifier": ("file", "classify", "categorize", "sort"),
}


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokenize(value: str | None) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", _normalize_text(value))
        if len(token) >= 3
    }


def _builtin_capabilities(skill: dict) -> list[str]:
    behavior_class = skill.get("behavior_class", "report")
    return list(DEFAULT_BUILTIN_CAPABILITIES.get(behavior_class, ["read_only"]))


def _queue_eligible_generated_skill(queue_entry: dict, draft: dict) -> bool:
    validation_report = draft.get("last_validation_report") or {}
    sandbox_result = draft.get("last_sandbox_result") or {}
    promotion_status = queue_entry.get("promotion_status")
    return (
        draft.get("status") == "queued_for_manual_promotion"
        and (promotion_status in {None, "pending_manual_review"})
        and draft.get("sandbox_only") is True
        and draft.get("promotion_required") is True
        and validation_report.get("validation_passed") is True
        and sandbox_result.get("sandbox_result") == "passed"
    )


def collect_available_skills(
    *,
    reference: str | Path | None = None,
    skills_dir: str | Path | None = None,
) -> list[dict]:
    candidates: list[dict] = []

    if skills_dir is not None:
        for skill in load_skills(str(skills_dir)):
            candidates.append(
                {
                    "skill_id": skill.get("name", ""),
                    "skill_kind": skill.get("name", ""),
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "when_to_use": skill.get("when_to_use", ""),
                    "capabilities": _builtin_capabilities(skill),
                    "source": "builtin",
                    "behavior_class": skill.get("behavior_class", "report"),
                    "risk_level": skill.get("risk_level", "safe"),
                }
            )

    for queue_entry in list_generated_skill_queue(reference=reference):
        skill_id = str(queue_entry.get("skill_id", ""))
        draft = load_generated_skill_draft(skill_id, reference=reference)
        if draft is None or not _queue_eligible_generated_skill(queue_entry, draft):
            continue
        skill_definition = draft.get("skill_definition") or {}
        candidates.append(
            {
                "skill_id": skill_id,
                "skill_kind": skill_definition.get("skill_kind", "generated"),
                "name": skill_definition.get("name", skill_id),
                "description": skill_definition.get("description", ""),
                "when_to_use": skill_definition.get("when_to_use", ""),
                "capabilities": list(skill_definition.get("capabilities", [])),
                "source": "generated",
                "behavior_class": skill_definition.get("behavior_class", "report"),
                "risk_level": skill_definition.get("risk_level", "safe"),
            }
        )

    return sorted(
        candidates,
        key=lambda item: (
            item.get("source", ""),
            item.get("skill_kind", ""),
            item.get("skill_id", ""),
        ),
    )


def build_skill_selection_input(
    *,
    task_description: str,
    available_skills: list[dict],
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
) -> dict:
    return {
        "task_description": task_description,
        "available_skills": available_skills,
        "recent_runtime_state_summary": recent_runtime_state_summary or {},
        "past_skill_memory": past_skill_memory or {},
    }


def _candidate_task_score(candidate: dict, task_text: str) -> int:
    score = 0
    task_tokens = _tokenize(task_text)
    candidate_tokens = set()
    for field in ("skill_id", "skill_kind", "name", "description", "when_to_use"):
        candidate_tokens.update(_tokenize(candidate.get(field)))
    for capability in candidate.get("capabilities", []):
        candidate_tokens.update(_tokenize(str(capability)))

    overlap = task_tokens & candidate_tokens
    score += len(overlap) * 3

    hints = TASK_HINTS.get(candidate.get("skill_kind")) or TASK_HINTS.get(candidate.get("name")) or ()
    matched_hints = sum(1 for hint in hints if hint in task_text)
    score += matched_hints * 4

    behavior_class = candidate.get("behavior_class", "report")
    if behavior_class in {"report", "observe"} and any(token in task_text for token in ("summary", "report", "status", "summarize")):
        score += 2
    if behavior_class == "review" and any(token in task_text for token in ("review", "bug", "regression")):
        score += 2

    return score


def _normalize_past_skill_memory(past_skill_memory: dict | list[dict] | None) -> dict[str, dict]:
    if not past_skill_memory:
        return {}
    if isinstance(past_skill_memory, dict):
        normalized = {}
        for skill_id, memory in past_skill_memory.items():
            if not isinstance(memory, dict):
                continue
            normalized[str(skill_id)] = {
                "success": int(memory.get("success", 0) or 0),
                "failure": int(memory.get("failure", 0) or 0),
            }
        return normalized

    normalized: dict[str, dict] = {}
    for item in past_skill_memory:
        skill_id = str(item.get("skill_id") or "")
        if not skill_id:
            continue
        bucket = normalized.setdefault(skill_id, {"success": 0, "failure": 0})
        outcome = _normalize_text(item.get("outcome"))
        if outcome in {"success", "passed", "completed"}:
            bucket["success"] += 1
        elif outcome in {"failed", "error", "rejected"}:
            bucket["failure"] += 1
    return normalized


def _memory_score(skill_id: str, normalized_memory: dict[str, dict]) -> int:
    memory = normalized_memory.get(skill_id, {})
    return int(memory.get("success", 0)) * 2 - int(memory.get("failure", 0)) * 2


def rank_skill_candidates(
    available_skills: list[dict],
    *,
    task_description: str,
    past_skill_memory: dict | list[dict] | None = None,
) -> list[dict]:
    ranked = []
    task_text = _normalize_text(task_description)
    memory = _normalize_past_skill_memory(past_skill_memory)
    for candidate in available_skills:
        rule_score = _candidate_task_score(candidate, task_text)
        history_score = _memory_score(candidate.get("skill_id", ""), memory)
        total_score = rule_score + history_score
        ranked.append(
            {
                **candidate,
                "selection_score": total_score,
                "selection_notes": {
                    "rule_score": rule_score,
                    "history_score": history_score,
                },
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            -item.get("selection_score", 0),
            item.get("selection_notes", {}).get("history_score", 0) * -1,
            item.get("source", ""),
            item.get("skill_id", ""),
        ),
    )


def _deterministic_fallback(available_skills: list[dict]) -> dict | None:
    if not available_skills:
        return None
    for preferred in ("workspace_reporter", "runtime_state_summarizer", "code_reviewer"):
        for candidate in available_skills:
            if candidate.get("skill_kind") == preferred or candidate.get("skill_id") == preferred:
                return candidate
    return sorted(
        available_skills,
        key=lambda item: (
            item.get("source", ""),
            item.get("skill_id", ""),
        ),
    )[0]


def _confidence_from_ranked(ranked: list[dict]) -> str:
    if not ranked:
        return "low"
    top_score = ranked[0].get("selection_score", 0)
    next_score = ranked[1].get("selection_score", 0) if len(ranked) > 1 else 0
    margin = top_score - next_score
    if top_score >= 8 and margin >= 3:
        return "high"
    if top_score >= 3:
        return "medium"
    return "low"


def select_skill_for_task(
    *,
    task_description: str,
    available_skills: list[dict] | None = None,
    recent_runtime_state_summary: dict | None = None,
    past_skill_memory: dict | list[dict] | None = None,
    reference: str | Path | None = None,
    skills_dir: str | Path | None = None,
    llm_selector=None,
) -> dict:
    candidates = available_skills or collect_available_skills(reference=reference, skills_dir=skills_dir)
    selection_input = build_skill_selection_input(
        task_description=task_description,
        available_skills=candidates,
        recent_runtime_state_summary=recent_runtime_state_summary,
        past_skill_memory=past_skill_memory,
    )

    task_text = _normalize_text(task_description)
    if llm_selector is not None:
        llm_result = llm_selector(selection_input)
        if isinstance(llm_result, dict) and llm_result.get("selected_skill"):
            selected = str(llm_result["selected_skill"])
            if any(candidate.get("skill_id") == selected for candidate in candidates):
                alternatives = [
                    candidate.get("skill_id")
                    for candidate in candidates
                    if candidate.get("skill_id") != selected
                ][:3]
                return {
                    "selected_skill": selected,
                    "reason": llm_result.get("reason") or "llm selector chose the skill",
                    "confidence": llm_result.get("confidence") or "medium",
                    "alternative_candidates": alternatives,
                }

    if not task_text:
        fallback = _deterministic_fallback(candidates)
        return {
            "selected_skill": fallback.get("skill_id") if fallback else None,
            "reason": "task description missing or invalid; deterministic fallback applied",
            "confidence": "low",
            "alternative_candidates": [
                candidate.get("skill_id")
                for candidate in candidates
                if fallback is None or candidate.get("skill_id") != fallback.get("skill_id")
            ][:3],
        }

    ranked = rank_skill_candidates(
        candidates,
        task_description=task_description,
        past_skill_memory=past_skill_memory,
    )
    if ranked and ranked[0].get("selection_score", 0) <= 0:
        fallback = _deterministic_fallback(candidates)
        return {
            "selected_skill": fallback.get("skill_id") if fallback else None,
            "reason": "task was ambiguous for available candidates; deterministic fallback applied",
            "confidence": "low",
            "alternative_candidates": [
                candidate.get("skill_id")
                for candidate in candidates
                if fallback is None or candidate.get("skill_id") != fallback.get("skill_id")
            ][:3],
        }

    selected = ranked[0] if ranked else _deterministic_fallback(candidates)
    alternatives = [candidate.get("skill_id") for candidate in ranked[1:4]] if ranked else []
    selected_skill_id = selected.get("skill_id") if selected else None
    selected_notes = selected.get("selection_notes", {}) if selected else {}
    memory_reason = ""
    if selected_notes.get("history_score", 0) > 0:
        memory_reason = " with positive prior success memory"
    elif selected_notes.get("history_score", 0) < 0:
        memory_reason = " despite negative prior failure memory"
    reason = (
        f"selected {selected_skill_id} via rule ranking "
        f"(score={selected.get('selection_score', 0)}, source={selected.get('source', 'unknown')})"
        f"{memory_reason}"
        if selected
        else "no available skill candidates"
    )
    return {
        "selected_skill": selected_skill_id,
        "reason": reason,
        "confidence": _confidence_from_ranked(ranked),
        "alternative_candidates": alternatives,
    }


def build_skill_selection_report(selection: dict) -> dict:
    return {
        "selected_skill": selection.get("selected_skill"),
        "reason": selection.get("reason", ""),
        "confidence": selection.get("confidence", "low"),
        "alternative_candidates": list(selection.get("alternative_candidates", [])),
    }
