"""
planner.py — 목표 비교 및 행동 계획 수립 (LLM-powered)

역할:
- agent_goal.md에서 목표를 파싱
- 현재 상태와 목표를 LLM에 전달하여 행동 목록 생성
- LLM 미연결 시 기존 규칙 기반 로직으로 자동 fallback
- pick_next_action도 LLM 판단 우선, 실패 시 dedup 규칙으로 fallback

LLM 연결 여부:
  llm_adapter가 None이거나 Ollama 미응답이면 규칙 기반으로 전환됨.
  에이전트 동작 자체는 중단되지 않음.
"""

import json
import logging
import os

from .llm_adapter import LLMAdapter
from .memory import RECENT_ACTION_COOLDOWN_SECONDS, is_skill_on_cooldown, summarize_recent_actions
from .workspace_metrics import rank_reopen_candidates, score_risk_decision_signal

logger = logging.getLogger("planner")

# 행동 타입 목록 (LLM 프롬프트에도 제공)
ACTION_TYPES = ["analyze", "organize", "create", "report"]

# 후보 스킬이 모두 이 점수 이하이면 noop 처리 (executor 기본 행동으로 전환)
_NOOP_THRESHOLD = 0
DEFAULT_SKILL_COOLDOWNS = {
    "workspace_reporter": 10,
    "file_classifier": 15,
    "code_reviewer": 20,
}
REOPEN_PRIORITY = ["workspace_reporter", "file_classifier", "code_reviewer"]
FALLBACK_NAMES = {"report_only", "change_summarizer", "memory_analyzer", "create", "wait", "noop"}
GATE_ALLOWED_BEHAVIOR_CLASSES = {
    "ignore": {"observe", "report"},
    "observe_only": {"observe", "report"},
    "review_allowed": {"observe", "report", "review"},
    "blocked": {"observe"},
}


def _score_skill(skill: dict, goals: list[str]) -> int:
    """
    목표 텍스트와 스킬 메타데이터의 양방향 키워드 겹침으로 적합도 점수를 계산.

    - 순방향: 목표 단어가 스킬 텍스트에 등장 → 각 +1
    - 역방향: 스킬 단어가 목표 텍스트에 등장 → 각 +1
      (역방향은 한국어 형태소 변형 대응: "분석" ∈ "분석하고" 처럼 substring 매칭)
    """
    combined_goals = " ".join(goals).lower()
    target = " ".join([
        skill.get("when_to_use", ""),
        skill.get("description", ""),
        skill.get("name", "").replace("_", " "),
    ]).lower()

    # len >= 2: 한국어 2글자 단어(분석·정리·파일 등)까지 포함
    score = sum(1 for w in combined_goals.split() if len(w) >= 2 and w in target)
    score += sum(1 for w in target.split()         if len(w) >= 2 and w in combined_goals)
    return score


def _keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _normalize_skill_cooldowns(skill_cooldowns: dict[str, int] | None = None) -> dict[str, int]:
    configured = skill_cooldowns or DEFAULT_SKILL_COOLDOWNS
    return {
        name: max(60, int(value) * 60)
        for name, value in configured.items()
    }


def _last_executed_skill_name(recent_actions: list[dict], available_skill_names: set[str]) -> str | None:
    for entry in reversed(recent_actions):
        skill_name = entry.get("skill")
        if skill_name in available_skill_names:
            return skill_name
    return None


def is_blocked_by_same_skill_rule(
    skill_name: str,
    last_skill_name: str | None,
    same_skill_block_cycles: int = 1,
) -> bool:
    return bool(same_skill_block_cycles >= 1 and last_skill_name and skill_name == last_skill_name)


def should_reopen_one_skill(cycle_state: dict) -> bool:
    reopen_score = score_reopen_signal(cycle_state)
    return reopen_score["should_reopen"]


def score_reopen_signal(cycle_state: dict) -> dict:
    recent_history = cycle_state.get("recent_history", [])[-2:]
    state_diff = cycle_state.get("state_diff", {})
    recent_fallback = any(
        entry.get("event") == "fallback"
        or entry.get("action", {}).get("source") == "cooldown_fallback"
        or entry.get("action_source") == "fallback"
        for entry in recent_history
    )
    external_changed = state_diff.get("external_changed", False)
    self_only_repeat = state_diff.get("self_artifact_changed", False) and not external_changed
    risk_score = score_risk_decision_signal(
        cycle_state.get("operational_risk_signal")
        or {
            "action_signal": {
                "action": cycle_state.get("operational_signal", {}).get("risk_action"),
                "certainty": cycle_state.get("operational_signal", {}).get("risk_certainty"),
            },
            "baseline_status": cycle_state.get("operational_signal", {}).get("baseline_status", "missing"),
            "baseline_reason": cycle_state.get("operational_signal", {}).get("baseline_reason", "missing_snapshot"),
            "blocker_candidate": cycle_state.get("operational_signal", {}).get("blocker_candidate"),
        }
    )
    score = 0
    reasons = []
    if recent_fallback:
        score += 2
        reasons.append("recent_fallback")
    if external_changed:
        score += 2
        reasons.append("external_changed")
    if self_only_repeat:
        score += 1
        reasons.append("self_artifact_repeat")
    if risk_score.get("reopen_score", 0) > 0:
        score += risk_score["reopen_score"]
        reasons.append(
            f"risk:{risk_score.get('action')}:{risk_score.get('certainty')}:{risk_score.get('reopen_score')}"
        )
    return {
        "should_reopen": score > 0,
        "score": score,
        "reasons": reasons,
        "risk": risk_score,
    }


def pick_reopen_candidate(
    skills: list[dict],
    cooldowns: dict[str, int],
    last_skill_name: str | None,
    risk_signal: dict | None = None,
) -> dict | None:
    ranked = rank_reopen_candidates(
        skills,
        risk_signal=risk_signal,
        priority_order=REOPEN_PRIORITY,
        last_skill_name=last_skill_name,
    )
    if ranked:
        return ranked[0]
    for skill in skills:
        if skill["name"] != last_skill_name:
            return {
                "skill": skill["name"],
                "reopen_priority": 0,
                "reopen_rank_reason": "fallback_priority_order",
                "reopen_sort_key": (0, 9999, skill["name"]),
            }
    return None


def _skill_choice_reason(prefix: str, detail: str) -> str:
    return f"{prefix} ({detail})" if detail else prefix


def _choose_all_cooldown_fallback(
    goals: list[str],
    current_state: dict,
    recent_actions: list[dict] | None = None,
) -> dict:
    goal_text = " ".join(goals).lower()
    total_files = current_state.get("total_files", 0)
    total_dirs = current_state.get("total_dirs", 0)
    workspace_known = (total_files + total_dirs) > 0
    recent_actions = recent_actions or []
    recent_fallbacks = [
        entry["skill"]
        for entry in recent_actions[-5:]
        if entry.get("skill") in FALLBACK_NAMES
    ]
    last_fallback = recent_fallbacks[-1] if recent_fallbacks else None

    scores = {
        "report_only": _keyword_hits(goal_text, ["보고", "report", "문서", "기록", "요약", "상태"]) + (2 if workspace_known else 0),
        "change_summarizer": _keyword_hits(goal_text, ["변화", "변경", "diff", "최근", "요약", "상태"]) + (2 if workspace_known else 0),
        "memory_analyzer": _keyword_hits(goal_text, ["메모리", "행동", "반복", "history", "로그", "분석"]) + (2 if recent_actions else 0),
        "create": _keyword_hits(goal_text, ["생성", "create", "작성", "만들"]) + (1 if workspace_known else 0),
        "wait": _keyword_hits(goal_text, ["대기", "wait", "보류"]) + (2 if not workspace_known else 0),
        "noop": 1,
    }

    for fallback_name in recent_fallbacks:
        if fallback_name in scores:
            scores[fallback_name] -= 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fallback_type = ranked[0][0]
    if last_fallback == fallback_type:
        for candidate, score in ranked[1:]:
            if candidate != last_fallback and score > 0:
                fallback_type = candidate
                break

    descriptions = {
        "report_only": "cooldown 상태 요약 보고서 생성",
        "change_summarizer": "최근 변화 요약 생성",
        "memory_analyzer": "최근 행동 분석 생성",
        "create": "cooldown 상태에서 기본 초안 생성",
        "wait": "모든 스킬 cooldown 해제까지 대기",
        "noop": "모든 스킬 cooldown 상태로 이번 사이클 실행 생략",
    }
    action_types = {
        "report_only": "report",
        "change_summarizer": "change_summarizer",
        "memory_analyzer": "memory_analyzer",
        "create": "create",
        "wait": "wait",
        "noop": "noop",
    }
    reason = (
        f"사용 가능한 스킬이 없어 "
        f"{fallback_type} fallback 선택"
    )
    detail = (
        f"fallback_scores={scores}, "
        f"recent_fallbacks={recent_fallbacks or []}, "
        f"selected={fallback_type}"
    )
    logger.info(f"[Planner] cooldown fallback 선택: {detail}")
    return {
        "skill": None,
        "fallback": fallback_type,
        "reason": f"{reason} ({detail})",
        "source": "fallback",
        "action": {
            "type": action_types[fallback_type],
            "description": descriptions[fallback_type],
            "goal": goals[0] if goals else "",
            "priority": 1,
            "reason": f"{reason} ({detail})",
            "source": "cooldown_fallback",
            "action_source": "fallback",
            "fallback_kind": fallback_type,
        },
    }

SYSTEM_PROMPT = """You are an autonomous agent planner.
Your job is to analyze a workspace state and a set of goals,
then decide what actions to take.

Available action types: analyze, organize, create, report

STRICT OUTPUT RULES:
- Output raw JSON ONLY. No explanation. No markdown. No prose. No code block.
- For analyze_gap  : output a JSON ARRAY  starting with [ and ending with ]
- For pick_next_action: output a single JSON OBJECT starting with { and ending with }
- The very first character of your response must be [ or {
- The very last character of your response must be ] or }

Action object schema:
{
  "type": "<one of: analyze | organize | create | report>",
  "description": "<short description in Korean>",
  "goal": "<the goal this action addresses>",
  "priority": <integer 1-5, lower = higher priority>,
  "reason": "<why this action is needed>"
}
"""


class Planner:
    def __init__(
        self,
        goal_file: str = "agent_goal.md",
        llm: LLMAdapter | None = None,
        skill_cooldowns: dict[str, int] | None = None,
        same_skill_block_cycles: int = 1,
    ):
        self.goal_file = goal_file
        self.llm = llm  # None이면 규칙 기반 전용
        self.skill_cooldowns = _normalize_skill_cooldowns(skill_cooldowns)
        self.same_skill_block_cycles = same_skill_block_cycles

    def get_recent_actions(self, recent_actions: list[dict] | None) -> list[dict]:
        return summarize_recent_actions(recent_actions, skill_cooldowns=self.skill_cooldowns)

    @staticmethod
    def apply_operational_gate(available_skills: list[dict], current_state: dict) -> list[dict]:
        gate = current_state.get("operational_gate", {})
        mode = gate.get("mode", "ignore")
        allowed_classes = GATE_ALLOWED_BEHAVIOR_CLASSES.get(mode)
        if not allowed_classes:
            return available_skills

        filtered = [
            skill for skill in available_skills
            if skill.get("behavior_class", "report") in allowed_classes
        ]
        if len(filtered) != len(available_skills):
            logger.info(
                f"[Planner] operational gate={mode} → behavior_class 기준 후보 제한"
            )
        return filtered

    def get_last_skill_name(self, recent_actions: list[dict] | None, available_skills: list[dict]) -> str | None:
        return _last_executed_skill_name(
            self.get_recent_actions(recent_actions),
            {skill["name"] for skill in available_skills},
        )

    def is_skill_blocked(self, skill_name: str, recent_actions: list[dict] | None, available_skills: list[dict], source: str = "normal") -> bool:
        recent_summary = self.get_recent_actions(recent_actions)
        last_skill_name = self.get_last_skill_name(recent_summary, available_skills)
        if is_blocked_by_same_skill_rule(skill_name, last_skill_name, self.same_skill_block_cycles):
            return True
        if source == "cooldown_reopen":
            return False
        return is_skill_on_cooldown(
            skill_name,
            recent_summary,
            skill_cooldowns=self.skill_cooldowns,
        )

    # ── 목표 로드 ──────────────────────────────────────

    def load_goals(self) -> list[str]:
        """agent_goal.md를 읽어 목표 리스트로 파싱."""
        if not os.path.exists(self.goal_file):
            logger.warning(f"[Planner] {self.goal_file} 없음 → 기본 목표 사용")
            return ["workspace 내 파일 구조를 분석하고 정리한다"]

        with open(self.goal_file, "r", encoding="utf-8") as f:
            content = f.read()

        goals = []
        for line in content.strip().splitlines():
            line = line.strip()
            if line and (
                line.startswith("- ")
                or line.startswith("* ")
                or (len(line) > 2 and line[0].isdigit() and line[1] in ".)")
            ):
                goal = line.lstrip("-*0123456789.) ").strip()
                if goal:
                    goals.append(goal)

        if not goals and content.strip():
            goals = [content.strip()]

        return goals

    # ── Gap 분석: LLM → fallback ───────────────────────

    def analyze_gap(self, goals: list[str], current_state: dict) -> list[dict]:
        """목표와 현재 상태를 비교하여 필요한 행동 리스트를 반환."""
        if self.llm is not None:
            result = self._analyze_gap_llm(goals, current_state)
            if result is not None:
                return result
            logger.warning("[Planner] LLM gap 분석 실패 → 규칙 기반으로 fallback")

        return self._analyze_gap_rules(goals, current_state)

    def _analyze_gap_llm(
        self, goals: list[str], current_state: dict
    ) -> list[dict] | None:
        """LLM에 현재 상태 + 목표를 주고 행동 목록을 받아온다."""
        state_summary = {
            "total_files": current_state.get("total_files", 0),
            "total_dirs": current_state.get("total_dirs", 0),
            "total_size_bytes": current_state.get("total_size_bytes", 0),
            "files": current_state.get("files", [])[:20],  # 최대 20개
        }

        prompt = f"""<state>
{json.dumps(state_summary, ensure_ascii=False, indent=2)}
</state>

<goals>
{json.dumps(goals, ensure_ascii=False, indent=2)}
</goals>

OUTPUT RULES (STRICT — NO EXCEPTIONS):
- Your ENTIRE response must be a valid JSON array.
- Do NOT write ANY text before [ or after ].
- Do NOT use markdown, code fences, or explanations.
- Do NOT wrap the array in an object.
- First character: [   Last character: ]

[
  {{
    "type": "analyze",
    "description": "한글 설명",
    "goal": "해당 목표",
    "priority": 1,
    "reason": "이유"
  }}
]"""

        response = self.llm.chat(prompt, system=SYSTEM_PROMPT, temperature=0.2)
        if response is None:
            return None

        parsed = self.llm.parse_json_response(response)

        # 배열 형태 검증 — LLM이 {"actions": [...]} 같은 객체로 감싸면 자동 언랩
        if isinstance(parsed, dict):
            # 값 중 첫 번째 list를 꺼냄
            for v in parsed.values():
                if isinstance(v, list):
                    logger.info("[Planner] LLM 응답이 객체로 감싸진 배열 → 자동 언랩")
                    parsed = v
                    break
            else:
                logger.warning(f"[Planner] LLM 응답이 배열이 아님: {type(parsed)}")
                return None

        if not isinstance(parsed, list):
            logger.warning(f"[Planner] LLM 응답이 배열이 아님: {type(parsed)}")
            return None

        # 각 항목 검증 및 보정
        validated = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            action_type = item.get("type", "analyze")
            if action_type not in ACTION_TYPES:
                action_type = "analyze"
            validated.append({
                "type": action_type,
                "description": item.get("description", f"LLM 제안 행동: {action_type}"),
                "goal": item.get("goal", goals[0] if goals else ""),
                "priority": int(item.get("priority", 2)),
                "reason": item.get("reason", ""),
                "source": "llm",
            })

        if not validated:
            logger.warning("[Planner] LLM 응답에서 유효한 행동 없음")
            return None

        validated.sort(key=lambda a: a["priority"])
        logger.info(f"[Planner] LLM이 {len(validated)}개 행동 제안")
        return validated

    def _analyze_gap_rules(
        self, goals: list[str], current_state: dict
    ) -> list[dict]:
        """기존 규칙 기반 gap 분석 (LLM 없을 때 사용)."""
        actions = []
        for goal in goals:
            g = goal.lower()
            if any(kw in g for kw in ["분석", "analyze", "scan"]):
                t = "analyze"
            elif any(kw in g for kw in ["정리", "organize", "clean"]):
                t = "organize"
            elif any(kw in g for kw in ["생성", "create", "만들"]):
                t = "create"
            elif any(kw in g for kw in ["기록", "log", "report", "문서"]):
                t = "report"
            else:
                t = "analyze"

            actions.append({
                "type": t,
                "description": f"{t} 수행: {goal}",
                "goal": goal,
                "priority": {"analyze": 1, "organize": 2, "create": 2, "report": 3}.get(t, 2),
                "reason": "규칙 기반 매핑",
                "source": "rules",
            })

        actions.sort(key=lambda a: a["priority"])
        return actions

    # ── 다음 행동 선택: LLM → fallback ────────────────

    def pick_next_action(
        self, actions: list[dict], history: list[dict]
    ) -> dict | None:
        """LLM을 우선으로 하여 다음 실행할 행동을 하나 선택."""
        if not actions:
            return None

        if self.llm is not None:
            result = self._pick_action_llm(actions, history)
            if result is not None:
                return result
            logger.warning("[Planner] LLM 행동 선택 실패 → 규칙 기반으로 fallback")

        return self._pick_action_rules(actions, history)

    def _pick_action_llm(
        self, actions: list[dict], history: list[dict]
    ) -> dict | None:
        """LLM에 행동 목록 + 히스토리를 주고 최적 행동 하나를 선택."""
        recent = [
            {
                "action_type": h.get("action", {}).get("type"),
                "description": h.get("action", {}).get("description"),
                "score": h.get("evaluation", {}).get("score"),
                "status": h.get("evaluation", {}).get("status"),
            }
            for h in history[-5:]
        ]

        prompt = f"""Recent execution history (last 5 cycles):
{json.dumps(recent, ensure_ascii=False, indent=2)}

Available actions to choose from:
{json.dumps(actions, ensure_ascii=False, indent=2)}

Select the single best next action considering:
1. Avoid repeating recently failed actions
2. Prefer actions not yet executed
3. Higher priority number = higher importance

Respond with a single action object JSON only."""

        response = self.llm.chat(prompt, system=SYSTEM_PROMPT, temperature=0.1)
        if response is None:
            return None

        parsed = self.llm.parse_json_response(response)
        if not isinstance(parsed, dict):
            return None

        action_type = parsed.get("type", "analyze")
        if action_type not in ACTION_TYPES:
            action_type = "analyze"

        result = {
            "type": action_type,
            "description": parsed.get("description", f"LLM 선택: {action_type}"),
            "goal": parsed.get("goal", ""),
            "priority": int(parsed.get("priority", 2)),
            "reason": parsed.get("reason", ""),
            "source": "llm",
        }
        logger.info(f"[Planner] LLM 선택: [{result['type']}] {result['description']}")
        return result

    def _pick_action_rules(
        self, actions: list[dict], history: list[dict]
    ) -> dict | None:
        """기존 dedup 기반 행동 선택."""
        recent_descriptions = {
            h.get("action", {}).get("description", "")
            for h in history[-10:]
        }
        for action in actions:
            if action["description"] not in recent_descriptions:
                return action
        return actions[0]

    # ── 스킬 선택 (신규) ──────────────────────────────────

    def pick_skill(
        self,
        goals: list[str],
        current_state: dict,
        available_skills: list[dict],
        recent_actions: list[dict] | None = None,
    ) -> dict | None:
        """
        현재 목표와 상태를 보고 사용할 스킬 하나를 선택.
        LLM 우선, 실패 시 키워드 매칭 fallback.

        반환: {"skill": "skill_name", "reason": "..."} | None
        """
        if not available_skills:
            return None

        available_skills = self.apply_operational_gate(available_skills, current_state)
        if not available_skills:
            logger.info("[Planner] operational gate 적용 후 사용 가능한 스킬 없음")
            return _choose_all_cooldown_fallback(goals, current_state, recent_actions or [])

        recent_actions = recent_actions or []

        if self.llm is not None:
            result = self._pick_skill_llm(goals, current_state, available_skills, recent_actions)
            if result is not None:
                return result
            logger.warning("[Planner] LLM 스킬 선택 실패 → 키워드 fallback")

        return self._pick_skill_rules(goals, current_state, available_skills, recent_actions)

    def _maybe_reopen_skill(
        self,
        goals: list[str],
        current_state: dict,
        available_skills: list[dict],
        recent_summary: list[dict],
        last_skill_name: str | None,
    ) -> dict | None:
        cycle_state = {
            "recent_history": current_state.get("recent_history", []),
            "state_diff": current_state.get("state_diff", {}),
            "operational_signal": current_state.get("operational_signal", {}),
            "operational_risk_signal": current_state.get("operational_risk_signal", {}),
        }
        reopen_signal = score_reopen_signal(cycle_state)
        if not reopen_signal["should_reopen"]:
            return None

        candidate_info = pick_reopen_candidate(
            available_skills,
            self.skill_cooldowns,
            last_skill_name,
            risk_signal=current_state.get("operational_risk_signal", {}),
        )
        if not candidate_info:
            return None

        detail = (
            f"skill={candidate_info['skill']}, "
            f"last_skill={last_skill_name}, "
            f"state_diff={current_state.get('state_diff', {})}, "
            f"reopen_score={reopen_signal['score']}, "
            f"reasons={reopen_signal['reasons']}, "
            f"rank={candidate_info.get('reopen_priority', 0)}, "
            f"rank_reason={candidate_info.get('reopen_rank_reason', '')}"
        )
        logger.info(f"[Planner] cooldown reopen 선택: {detail}")
        return {
            "skill": candidate_info["skill"],
            "reason": _skill_choice_reason("모든 스킬이 cooldown이지만 reopen 조건 충족", detail),
            "source": "cooldown_reopen",
            "reopen_priority": candidate_info.get("reopen_priority", 0),
            "reopen_rank_reason": candidate_info.get("reopen_rank_reason"),
            "reopen_sort_key": candidate_info.get("reopen_sort_key"),
        }

    def _pick_skill_llm(
        self,
        goals: list[str],
        current_state: dict,
        available_skills: list[dict],
        recent_actions: list[dict] | None = None,
    ) -> dict | None:
        """LLM에게 목표+상태+스킬 목록을 주고 하나를 선택하게 함."""
        from .skill_loader import skills_summary

        recent_summary = self.get_recent_actions(recent_actions)[-5:]
        last_skill_name = self.get_last_skill_name(recent_summary, available_skills)
        blocked_skills = {
            entry["skill"]
            for entry in recent_summary
            if entry.get("on_cooldown")
        }
        eligible_skills = [
            skill for skill in available_skills
            if skill["name"] not in blocked_skills
        ]
        eligible_skills = [
            skill for skill in eligible_skills
            if not is_blocked_by_same_skill_rule(skill["name"], last_skill_name, self.same_skill_block_cycles)
        ]

        if not eligible_skills:
            reopened = self._maybe_reopen_skill(goals, current_state, available_skills, recent_summary, last_skill_name)
            if reopened is not None:
                return reopened
            logger.info("[Planner] LLM 선택 제외 후 사용 가능한 스킬 없음 → fallback")
            return _choose_all_cooldown_fallback(goals, current_state, recent_summary)

        recent_block = ""
        if recent_summary:
            llm_recent_summary = [
                {
                    "skill": entry["skill"],
                    "executed_at_utc": entry["executed_at"],
                    "cooldown_until_utc": entry["cooldown_until"],
                    "on_cooldown": entry["on_cooldown"],
                }
                for entry in recent_summary
            ]
            recent_block = f"""
Recent skill executions (UTC, ISO-8601):
{json.dumps(llm_recent_summary, ensure_ascii=False, indent=2)}

Forbidden skills during cooldown:
{json.dumps(sorted(blocked_skills), ensure_ascii=False)}

RULE: You MUST choose exactly one skill from the allowed list below.
      Any skill in the forbidden list is excluded and must never be selected.
      The same skill as the last executed skill ({json.dumps(last_skill_name, ensure_ascii=False)}) is also excluded for one cycle.
"""

        prompt = f"""Current goals:
{json.dumps(goals, ensure_ascii=False)}

Workspace state:
- files: {current_state.get('total_files', '?')}
- dirs: {current_state.get('total_dirs', '?')}
{recent_block}
Allowed skills:
{json.dumps(skills_summary(eligible_skills), ensure_ascii=False, indent=2)}

Choose ONE skill that best matches the goals.
Reply with JSON only:
{{"skill": "<skill_name>", "reason": "<why in Korean>"}}"""

        response = self.llm.chat(
            prompt,
            system='You are an agent skill selector. Reply with valid JSON only.',
            temperature=0.1,
        )
        if response is None:
            return None
        parsed = self.llm.parse_json_response(response)
        if not isinstance(parsed, dict) or "skill" not in parsed:
            return None
        if parsed["skill"] not in {skill["name"] for skill in eligible_skills}:
            logger.warning(f"[Planner] LLM이 제외된/없는 스킬 선택: {parsed['skill']}")
            return None
        logger.info(f"[Planner] LLM 스킬 선택: {parsed['skill']} — {parsed.get('reason','')}")
        parsed["source"] = "normal"
        return parsed

    def _pick_skill_rules(
        self,
        goals: list[str],
        current_state: dict,
        available_skills: list[dict],
        recent_actions: list[dict] | None = None,
    ) -> dict | None:
        """
        목표 적합도 점수 기반 스킬 선택. 최근 실행 스킬은 후보에서 제외.

        로그 출력:
          - 제외된 스킬 목록
          - 후보 스킬별 적합도 점수
          - 최종 선택 스킬과 선택 이유 (또는 noop 사유)
        """
        recent_summary = self.get_recent_actions(recent_actions)
        recently_done = {
            entry["skill"]
            for entry in recent_summary
            if entry.get("on_cooldown")
        }
        last_skill_name = self.get_last_skill_name(recent_summary, available_skills)

        # ① 제외 스킬 로그
        excluded = [s["name"] for s in available_skills if s["name"] in recently_done]
        if excluded:
            logger.info(f"[Planner] 반복 제외 스킬: {excluded}")

        # ② 후보 목록 + 적합도 점수 계산
        candidates = [
            (skill, _score_skill(skill, goals))
            for skill in available_skills
            if skill["name"] not in recently_done
            and not is_blocked_by_same_skill_rule(skill["name"], last_skill_name, self.same_skill_block_cycles)
        ]

        # ③ 사용 가능한 스킬이 없으면 reopen 판단 후 fallback
        if not candidates:
            reopened = self._maybe_reopen_skill(goals, current_state, available_skills, recent_summary, last_skill_name)
            if reopened is not None:
                return reopened
            logger.info("[Planner] 모든 스킬이 cooldown 상태 → 적합 fallback 선택")
            return _choose_all_cooldown_fallback(goals, current_state, recent_summary)

        # ④ 후보 점수 로그
        score_log = {s["name"]: sc for s, sc in candidates}
        logger.info(f"[Planner] 후보 적합도: {score_log}")

        # ⑤ 최고 점수 스킬 선택
        best_skill, best_score = max(candidates, key=lambda x: x[1])

        # ⑥ 점수 미달 → noop (executor 기본 행동으로 전환)
        if best_score <= _NOOP_THRESHOLD:
            logger.info(
                f"[Planner] 적합한 스킬 없음 (최고 점수={best_score} ≤ {_NOOP_THRESHOLD})"
                " → noop/wait — executor 기본 행동으로 전환"
            )
            return None

        reason = f"적합도 {best_score}점 (후보 {len(candidates)}개 중 최고)"
        logger.info(f"[Planner] 선택: {best_skill['name']} — {reason}")
        return {"skill": best_skill["name"], "reason": reason, "source": "normal"}
