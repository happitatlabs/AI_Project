"""
skill_loader.py — skills/ 디렉토리에서 SKILL.md를 읽어 파싱

반환 형식:
[
  {
    "name": "workspace_reporter",
    "description": "...",
    "when_to_use": "...",
    "input": "...",
    "output": "...",
    "steps": ["1. scan_workspace: ...", ...],
    "risk_level": "safe",   # safe | approval | dangerous
    "path": "/abs/path/to/SKILL.md"
  },
  ...
]
"""

import logging
import os
import re
from pathlib import Path

from .workspace_metrics import score_risk_decision_signal

logger = logging.getLogger("skill_loader")


DEFAULT_BEHAVIOR_CLASSES = {
    "workspace_reporter": "observe",
    "file_classifier": "observe",
    "code_reviewer": "review",
}
OPTIONAL_RISK_HINT_FIELDS = (
    "risk_profile",
    "handles_config_changes",
    "handles_runtime_changes",
    "prefers_reopen_on_high_risk",
    "suggestion_bias",
    "review_cost",
)
BOOLEAN_RISK_HINT_FIELDS = {
    "handles_config_changes",
    "handles_runtime_changes",
    "prefers_reopen_on_high_risk",
}
DEFAULT_RISK_HINTS_BY_NAME = {
    "workspace_reporter": {
        "risk_profile": "monitoring",
        "handles_config_changes": False,
        "handles_runtime_changes": False,
        "prefers_reopen_on_high_risk": False,
        "suggestion_bias": "explain",
        "review_cost": "low",
    },
    "file_classifier": {
        "risk_profile": "monitoring",
        "handles_config_changes": True,
        "handles_runtime_changes": False,
        "prefers_reopen_on_high_risk": False,
        "suggestion_bias": "explain",
        "review_cost": "low",
    },
    "code_reviewer": {
        "risk_profile": "runtime_sensitive",
        "handles_config_changes": True,
        "handles_runtime_changes": True,
        "prefers_reopen_on_high_risk": True,
        "suggestion_bias": "action",
        "review_cost": "high",
    },
}
DEFAULT_RISK_HINTS_BY_BEHAVIOR_CLASS = {
    "review": {
        "risk_profile": "runtime_sensitive",
        "handles_config_changes": True,
        "handles_runtime_changes": True,
        "prefers_reopen_on_high_risk": True,
        "suggestion_bias": "action",
        "review_cost": "high",
    },
    "write": {
        "risk_profile": "runtime_sensitive",
        "handles_config_changes": True,
        "handles_runtime_changes": True,
        "prefers_reopen_on_high_risk": True,
        "suggestion_bias": "action",
        "review_cost": "high",
    },
    "execute": {
        "risk_profile": "runtime_sensitive",
        "handles_config_changes": True,
        "handles_runtime_changes": True,
        "prefers_reopen_on_high_risk": True,
        "suggestion_bias": "action",
        "review_cost": "high",
    },
    "observe": {
        "risk_profile": "monitoring",
        "handles_config_changes": False,
        "handles_runtime_changes": False,
        "prefers_reopen_on_high_risk": False,
        "suggestion_bias": "monitor",
        "review_cost": "low",
    },
    "report": {
        "risk_profile": "monitoring",
        "handles_config_changes": False,
        "handles_runtime_changes": False,
        "prefers_reopen_on_high_risk": False,
        "suggestion_bias": "explain",
        "review_cost": "low",
    },
}
REVIEW_KEYWORDS = ("review", "reviewer", "검토", "리뷰")
REPORT_KEYWORDS = ("report", "reporter", "보고", "요약")
EXECUTE_KEYWORDS = ("execute", "runner", "run", "command", "실행", "명령")


def _coerce_skill_metadata_value(header: str, value: str):
    if header in BOOLEAN_RISK_HINT_FIELDS:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value.strip()


def resolve_skill_risk_hints(skill: dict) -> dict:
    explicit_fields = sorted(field for field in OPTIONAL_RISK_HINT_FIELDS if field in skill)
    resolved = dict(DEFAULT_RISK_HINTS_BY_BEHAVIOR_CLASS.get(skill.get("behavior_class", "report"), {}))
    inferred_from = "behavior_class" if resolved else None
    name_defaults = DEFAULT_RISK_HINTS_BY_NAME.get(skill.get("name", ""), {})
    if name_defaults:
        resolved.update(name_defaults)
        inferred_from = "name"
    for field in OPTIONAL_RISK_HINT_FIELDS:
        if field in skill:
            resolved[field] = skill[field]
    resolved["explicit_risk_hint_fields"] = explicit_fields
    resolved["inferred_risk_metadata_used"] = len(explicit_fields) < len(OPTIONAL_RISK_HINT_FIELDS) and bool(inferred_from)
    resolved["inferred_from"] = inferred_from if resolved["inferred_risk_metadata_used"] else "explicit"
    return resolved


def _parse_skill_md(filepath: str) -> dict | None:
    """SKILL.md 파일을 파싱하여 딕셔너리로 반환. 실패 시 None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    skill: dict = {"path": filepath}
    explicit_behavior_class = False

    # ## 섹션 헤더로 분리
    # 패턴: "## fieldname\n내용\n\n## 다음섹션"
    sections = re.split(r"\n## ", content)
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        # 헤더 이름
        header = lines[0].lstrip("#").strip().lower().replace(" ", "_")
        body_lines = [l for l in lines[1:] if l.strip()]

        if header == "steps":
            # 번호 붙은 리스트 → 리스트로 파싱
            steps = []
            for line in body_lines:
                step = re.sub(r"^\d+[\.\)]\s*", "", line.strip())
                if step:
                    steps.append(step)
            skill["steps"] = steps
        elif header in ("name", "description", "when_to_use", "input",
                        "output", "risk_level", "behavior_class", *OPTIONAL_RISK_HINT_FIELDS):
            value = " ".join(body_lines).strip()
            skill[header] = _coerce_skill_metadata_value(header, value)
            if header == "behavior_class":
                explicit_behavior_class = True

    # 필수 필드 검증
    if "name" not in skill or "steps" not in skill:
        return None

    # risk_level 기본값
    skill.setdefault("risk_level", "safe")
    if explicit_behavior_class:
        skill["behavior_class_source"] = "explicit"
    else:
        skill["behavior_class"] = DEFAULT_BEHAVIOR_CLASSES.get(skill.get("name", ""), "report")
        skill["behavior_class_source"] = "fallback"
    skill.update(resolve_skill_risk_hints(skill))
    return skill


def load_skills(
    skills_dir: str,
    strict_behavior_class: bool = False,
    risk_signal: dict | None = None,
) -> list[dict]:
    """
    skills_dir 하위의 모든 SKILL.md를 스캔하여 파싱된 스킬 리스트 반환.
    파싱 실패한 스킬은 건너뜀.
    """
    skills: list[dict] = []

    if not os.path.isdir(skills_dir):
        return skills

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry, "SKILL.md")
        if not os.path.isfile(skill_path):
            continue
        parsed = _parse_skill_md(skill_path)
        if parsed:
            skills.append(parsed)

    diagnostics = get_behavior_class_diagnostics(skills)
    fallback_skills = diagnostics["fallback_skills"]
    if fallback_skills:
        logger.warning(
            "[SkillLoader] behavior_class fallback 사용 중: %s",
            ", ".join(fallback_skills),
        )
    preflight = build_strict_behavior_preflight(skills, risk_signal=risk_signal)
    if strict_behavior_class and not preflight["ready"]:
        summary = build_strict_behavior_preflight_summary(skills, risk_signal=risk_signal)
        logger.error(
            "[SkillLoader] strict preflight: fallback_blockers=%s consistency_blockers=%s primary_blocker=%s risk_blocker_score=%s",
            summary["fallback_blocker_count"],
            summary["consistency_blocker_count"],
            summary["primary_blocker"] or "none",
            summary["risk_blocker_score"],
        )
        raise ValueError(preflight["message"])

    return skills


def list_behavior_class_fallback_skills(skills: list[dict]) -> list[str]:
    return sorted(
        skill.get("name", "")
        for skill in skills
        if skill.get("behavior_class_source") == "fallback" and skill.get("name")
    )


def suggest_behavior_class(skill: dict) -> str | None:
    text = " ".join([
        skill.get("name", ""),
        skill.get("description", ""),
        skill.get("when_to_use", ""),
    ]).lower()
    if any(keyword in text for keyword in REVIEW_KEYWORDS):
        return "review"
    if any(keyword in text for keyword in EXECUTE_KEYWORDS):
        return "execute"
    if any(keyword in text for keyword in REPORT_KEYWORDS):
        return "report"
    return None


def get_behavior_class_consistency_diagnostics(skills: list[dict]) -> dict:
    inconsistent_skills: list[str] = []
    warnings: list[str] = []

    for skill in skills:
        name = skill.get("name", "")
        behavior_class = skill.get("behavior_class", "report")
        text = " ".join([
            name,
            skill.get("description", ""),
            skill.get("when_to_use", ""),
        ]).lower()

        if any(keyword in text for keyword in REVIEW_KEYWORDS):
            if behavior_class != "review":
                inconsistent_skills.append(name)
                warnings.append(f"{name}: reviewer 계열로 보이나 behavior_class={behavior_class}")
            continue
        if any(keyword in text for keyword in EXECUTE_KEYWORDS):
            if behavior_class != "execute":
                inconsistent_skills.append(name)
                warnings.append(f"{name}: execute 계열로 보이나 behavior_class={behavior_class}")
            continue
        if any(keyword in text for keyword in REPORT_KEYWORDS) and behavior_class != "report":
            inconsistent_skills.append(name)
            warnings.append(f"{name}: reporter 계열로 보이나 behavior_class={behavior_class}")

    return {
        "inconsistent_behavior_class_skills": sorted(set(filter(None, inconsistent_skills))),
        "consistency_warnings": warnings,
    }


def get_behavior_class_diagnostics(skills: list[dict]) -> dict:
    explicit_skills = sorted(
        skill.get("name", "")
        for skill in skills
        if skill.get("behavior_class_source") == "explicit" and skill.get("name")
    )
    fallback_skills = list_behavior_class_fallback_skills(skills)
    consistency = get_behavior_class_consistency_diagnostics(skills)
    return {
        "explicit_skills": explicit_skills,
        "fallback_skills": fallback_skills,
        "missing_behavior_class": fallback_skills,
        "explicit_transition_needed": fallback_skills,
        "all_explicit": not fallback_skills,
        "inconsistent_behavior_class_skills": consistency["inconsistent_behavior_class_skills"],
        "consistency_warnings": consistency["consistency_warnings"],
    }


def build_strict_behavior_readiness(diagnostics: dict, mode: str = "missing_only") -> dict:
    blockers = list(diagnostics.get("explicit_transition_needed", []))
    if mode == "include_consistency":
        blockers = sorted(set(blockers + list(diagnostics.get("inconsistent_behavior_class_skills", []))))
    return {
        "strict_ready": not blockers,
        "fallback_skill_count": len(diagnostics.get("fallback_skills", [])),
        "explicit_transition_needed_count": len(blockers),
        "blockers": blockers,
        "mode": mode,
    }


def build_explicit_transition_report(skills: list[dict], readiness_mode: str = "include_consistency") -> dict:
    diagnostics = get_behavior_class_diagnostics(skills)
    readiness = build_strict_behavior_readiness(diagnostics, mode=readiness_mode)
    suggested_behavior_class = {}
    for skill in skills:
        skill_name = skill.get("name", "")
        if not skill_name:
            continue
        if (
            skill_name in diagnostics.get("fallback_skills", [])
            or skill_name in diagnostics.get("inconsistent_behavior_class_skills", [])
        ):
            suggestion = suggest_behavior_class(skill)
            if suggestion is None and skill.get("behavior_class_source") == "fallback":
                suggestion = skill.get("behavior_class")
            if suggestion:
                suggested_behavior_class[skill_name] = suggestion

    return {
        "fallback_skills": diagnostics.get("fallback_skills", []),
        "inconsistent_behavior_class_skills": diagnostics.get("inconsistent_behavior_class_skills", []),
        "explicit_transition_needed": diagnostics.get("explicit_transition_needed", []),
        "strict_blockers": readiness.get("blockers", []),
        "suggested_behavior_class": suggested_behavior_class,
    }


def build_explicit_transition_report_detail(skills: list[dict], readiness_mode: str = "include_consistency") -> dict:
    transition_report = build_explicit_transition_report(skills, readiness_mode=readiness_mode)
    detailed_skills = []
    fallback_skills = set(transition_report["fallback_skills"])
    inconsistent_skills = set(transition_report["inconsistent_behavior_class_skills"])
    strict_blockers = set(transition_report["strict_blockers"])

    for skill in skills:
        name = skill.get("name", "")
        if not name:
            continue
        blocker_reasons = []
        if name in fallback_skills:
            blocker_reasons.append("missing_behavior_class")
        if name in inconsistent_skills:
            blocker_reasons.append("inconsistent_behavior_class")
        detailed_skills.append({
            "name": name,
            "behavior_class": skill.get("behavior_class", "report"),
            "behavior_class_source": skill.get("behavior_class_source", "fallback"),
            "suggested_behavior_class": transition_report["suggested_behavior_class"].get(name),
            "strict_blocker": name in strict_blockers,
            "strict_blocker_reasons": blocker_reasons,
        })

    return {
        **transition_report,
        "skills": detailed_skills,
    }


def build_skill_metadata_template(
    skill_name: str = "your_skill_name",
    behavior_class: str | None = None,
) -> str:
    resolved_behavior_class = behavior_class or "report"
    return (
        f"# SKILL: {skill_name}\n\n"
        "## name\n"
        f"{skill_name}\n\n"
        "## behavior_class\n"
        f"{resolved_behavior_class}\n\n"
        "## description\n"
        "스킬의 역할을 한 문장으로 설명한다.\n\n"
        "## risk_profile\n"
        "monitoring  # monitoring | runtime_sensitive | config_sensitive\n\n"
        "## handles_config_changes\n"
        "false  # true면 config/settings 변경 대응에 적합한 스킬\n\n"
        "## handles_runtime_changes\n"
        "false  # true면 runtime/script/core 경로 위험 대응에 적합한 스킬\n\n"
        "## prefers_reopen_on_high_risk\n"
        "false  # true면 REVIEW_REQUIRED/ALERT 시 reopen 우선도를 높인다\n\n"
        "## suggestion_bias\n"
        "explain  # action | explain | monitor\n\n"
        "## review_cost\n"
        "low  # low | medium | high\n\n"
        "## steps\n"
        "1. first_step: 수행할 핵심 작업\n"
    )


def write_skill_metadata_template(target: str | Path) -> dict:
    target_path = Path(target)
    skill_file = target_path if target_path.suffix.lower() == ".md" else target_path / "SKILL.md"
    if skill_file.exists():
        return {
            "created": False,
            "path": str(skill_file),
            "reason": "exists",
        }

    skill_name = skill_file.parent.name if skill_file.name.lower() == "skill.md" else skill_file.stem
    suggested_behavior_class = suggest_behavior_class({"name": skill_name}) or "report"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        build_skill_metadata_template(
            skill_name=skill_name,
            behavior_class=suggested_behavior_class,
        ),
        encoding="utf-8",
    )
    return {
        "created": True,
        "path": str(skill_file),
        "reason": "created",
        "suggested_behavior_class": suggested_behavior_class,
    }


def build_strict_risk_integration(risk_signal: dict | None = None) -> dict:
    scored = score_risk_decision_signal(risk_signal)
    return {
        "risk_blocker_candidate": scored.get("blocker_candidate"),
        "risk_blocker_score": scored.get("blocker_score", 0),
        "risk_blocker_promoted": scored.get("blocker_promoted", False),
        "risk_action": scored.get("action"),
        "risk_certainty": scored.get("certainty", "LOW"),
    }


def build_strict_behavior_preflight(skills: list[dict], risk_signal: dict | None = None) -> dict:
    diagnostics = get_behavior_class_diagnostics(skills)
    readiness = build_strict_behavior_readiness(diagnostics, mode="include_consistency")
    risk_integration = build_strict_risk_integration(risk_signal)
    risk_candidate = risk_integration["risk_blocker_candidate"]
    return {
        "ready": readiness["strict_ready"] and not risk_integration["risk_blocker_promoted"],
        "fallback_blockers": diagnostics.get("fallback_skills", []),
        "consistency_blockers": diagnostics.get("inconsistent_behavior_class_skills", []),
        **risk_integration,
        "message": (
            "strict behavior_class preflight failed: "
            f"fallback={diagnostics.get('fallback_skills', []) or 'none'}, "
            f"inconsistent={diagnostics.get('inconsistent_behavior_class_skills', []) or 'none'}, "
            f"risk={risk_candidate or 'none'}"
        ),
    }


def build_strict_behavior_preflight_summary(skills: list[dict], risk_signal: dict | None = None) -> dict:
    preflight = build_strict_behavior_preflight(skills, risk_signal=risk_signal)
    fallback_blockers = preflight.get("fallback_blockers", [])
    consistency_blockers = preflight.get("consistency_blockers", [])
    primary_blocker = None
    if fallback_blockers:
        primary_blocker = fallback_blockers[0]
    elif consistency_blockers:
        primary_blocker = consistency_blockers[0]
    elif preflight.get("risk_blocker_promoted"):
        primary_blocker = preflight.get("risk_blocker_candidate")

    return {
        "ready": preflight.get("ready", False),
        "fallback_blocker_count": len(fallback_blockers),
        "consistency_blocker_count": len(consistency_blockers),
        "primary_blocker": primary_blocker,
        "message": preflight.get("message", ""),
        "risk_blocker_candidate": preflight.get("risk_blocker_candidate"),
        "risk_blocker_score": preflight.get("risk_blocker_score", 0),
        "risk_blocker_promoted": preflight.get("risk_blocker_promoted", False),
    }


def skills_summary(skills: list[dict]) -> list[dict]:
    """LLM 프롬프트에 넣기 적합한 요약 리스트 반환 (path 제외)."""
    return [
        {
            "name":         s.get("name", ""),
            "description":  s.get("description", ""),
            "when_to_use":  s.get("when_to_use", ""),
            "risk_level":   s.get("risk_level", "safe"),
            "behavior_class": s.get("behavior_class", "report"),
            "risk_profile": s.get("risk_profile", "monitoring"),
            "suggestion_bias": s.get("suggestion_bias", "explain"),
            "inferred_risk_metadata_used": s.get("inferred_risk_metadata_used", False),
            "inferred_from": s.get("inferred_from", "explicit"),
        }
        for s in skills
    ]
