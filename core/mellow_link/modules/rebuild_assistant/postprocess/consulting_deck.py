from __future__ import annotations

import re

from .schemas import ConsultingMinContract
from .information_separation import (
    resolve_information_role,
    role_description,
    role_header,
    role_label,
)


_EMPTY_STATE_MESSAGES: dict[str, str] = {
    "as_is": "현재 상태 요약 정보가 충분하지 않습니다.",
    "process_flow": "현재 프로세스 흐름 정보가 충분하지 않습니다.",
    "rules": "핵심 규칙 정보는 추가 확인이 필요합니다.",
    "risks": "주요 리스크는 추가 분석 후 정리해야 합니다.",
    "gap": "현재 구조와 목표 구조 간 차이를 추가 확인해야 합니다.",
    "actions": "후속 실행 항목은 추가 분석 후 확정이 필요합니다.",
}

_EXTERNAL_EMPTY_STATE_MESSAGES: dict[str, str] = {
    "as_is": "현재 상태 요약 정보가 충분하지 않습니다.",
    "process_flow": "현재 프로세스 흐름 정보가 충분하지 않습니다.",
    "rules": "핵심 규칙 정보는 추가 확인 전입니다.",
    "risks": "주요 리스크는 추가 분석 전입니다.",
    "gap": "현재 구조와 목표 구조 간 차이는 추가 확인 전입니다.",
    "actions": "후속 실행 항목은 추가 분석 후 확정 전입니다.",
}

_SECTION_TITLES: dict[str, dict[str, str]] = {
    "overview": {
        "as_is": "상황 / 목적",
    },
    "approach": {
        "gap": "판단 구조",
        "risks": "가정 / 누락 / 리스크",
    },
    "implementation": {
        "process_flow": "단계별 추진 흐름",
        "actions": "중점 실행 과제",
    },
    "design": {
        "rules": "근거 / 핵심 규칙",
        "process_flow": "설계 흐름",
    },
    "vision": {
        "actions": "적용 방향",
    },
}

_FAMILY_SECTION_TITLES: dict[str, dict[str, dict[str, str]]] = {
    "operational_source": {
        "overview": {
            "as_is": "현행 요약",
        },
        "approach": {
            "gap": "처리 흐름",
            "risks": "운영 리스크",
        },
        "implementation": {
            "process_flow": "검토 순서",
            "actions": "추가 확인 항목",
        },
        "design": {
            "rules": "주요 업무 규칙",
            "process_flow": "계산 / 연계 흐름",
        },
        "vision": {
            "actions": "운영 점검 메모",
        },
    },
    "option_comparison": {
        "overview": {
            "as_is": "비교 요약",
        },
        "approach": {
            "gap": "비교 기준",
            "risks": "선택 시 유의점",
        },
        "implementation": {
            "process_flow": "도입 단계",
            "actions": "검토 후보",
        },
        "design": {
            "rules": "추천 근거",
            "process_flow": "선택지 구조 메모",
        },
        "vision": {
            "actions": "후속 검토",
        },
    },
}

_CHAPTER_ORDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overview", ("as_is",)),
    ("approach", ("gap", "risks")),
    ("implementation", ("process_flow", "actions")),
    ("design", ("rules", "process_flow")),
    ("vision", ("actions",)),
)

_OPERATIONAL_ROLE_CHAPTER_ORDER: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "structure": (
        ("overview", ("as_is",)),
        ("implementation", ("process_flow",)),
    ),
    "diagnosis": (
        ("overview", ("as_is",)),
        ("approach", ("gap", "risks")),
    ),
    "decision": (
        ("overview", ("as_is",)),
        ("design", ("rules",)),
        ("vision", ("actions",)),
    ),
}

_CHAPTER_TITLES: dict[str, dict[str, str]] = {
    "internal": {
        "overview": "컨설팅 개요",
        "approach": "컨설팅 전개",
        "implementation": "컨설팅 구현",
        "design": "컨설팅 설계",
        "vision": "컨설팅 비전",
    },
    "external": {
        "overview": "컨설팅 개요",
        "approach": "컨설팅 전개",
        "implementation": "컨설팅 구현",
        "design": "컨설팅 설계",
        "vision": "컨설팅 비전",
    },
}

_FAMILY_CHAPTER_TITLES: dict[str, dict[str, dict[str, str]]] = {
    "operational_source": {
        "internal": {
            "overview": "현행 분석 개요",
            "approach": "처리 흐름 검토",
            "implementation": "분석 단계",
            "design": "업무 규칙과 계산 기준",
            "vision": "후속 확인 항목",
        },
        "external": {
            "overview": "현행 분석 개요",
            "approach": "처리 흐름 검토",
            "implementation": "분석 단계",
            "design": "업무 규칙과 계산 기준",
            "vision": "후속 확인 항목",
        },
    },
    "option_comparison": {
        "internal": {
            "overview": "비교 개요",
            "approach": "비교 기준",
            "implementation": "도입 단계",
            "design": "추천안 구조",
            "vision": "후속 검토",
        },
        "external": {
            "overview": "비교 개요",
            "approach": "비교 기준",
            "implementation": "도입 단계",
            "design": "추천안 구조",
            "vision": "후속 검토",
        },
    },
}

_OPERATIONAL_ROLE_CHAPTER_TITLES: dict[str, dict[str, str]] = {
    "structure": {
        "overview": "Structure - 흐름 중심",
        "implementation": "Structure - 처리 단계",
    },
    "diagnosis": {
        "overview": "Diagnosis - 현행 요약",
        "approach": "Diagnosis - 영향과 리스크",
    },
    "decision": {
        "overview": "Decision - 판단 요약",
        "design": "Decision - 비교 기준",
        "vision": "Decision - 추천안",
    },
}

_OPERATIONAL_ROLE_SECTION_TITLES: dict[str, dict[tuple[str, str], str]] = {
    "structure": {
        ("overview", "as_is"): "무엇이 일어나는가",
        ("implementation", "process_flow"): "처리 단계",
    },
    "diagnosis": {
        ("overview", "as_is"): "현행 요약",
        ("approach", "gap"): "문제 정의",
        ("approach", "risks"): "리스크",
    },
    "decision": {
        ("overview", "as_is"): "선택 요약",
        ("design", "rules"): "비교 기준",
        ("vision", "actions"): "추천안",
    },
}

_FX_FIFO_KEYWORDS: tuple[str, ...] = ("외화", "fifo", "lot", "환차", "전표", "gl")
_OVERVIEW_NOISE_PATTERNS: tuple[str, ...] = ("ui 가깝게 결합",)
_DESIGN_FLOW_KEYWORDS: tuple[str, ...] = ("구조", "설계", "규칙", "계산", "연계", "전표", "gl", "lot")
_CONCISE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("정리하는 편이 적절합니다", "정리합니다"),
    ("검토하는 편이 적절합니다", "검토합니다"),
    ("유지하는 편이 안전합니다", "유지합니다"),
    ("우선 보존해야 합니다", "우선 보존합니다"),
    ("유지해야 합니다", "유지합니다"),
    ("관리해야 합니다", "관리합니다"),
    ("연결해야 합니다", "연결합니다"),
    ("고정해야 합니다", "고정합니다"),
    ("설계해야 합니다", "설계합니다"),
    ("계산해야 합니다", "계산합니다"),
    ("반영해야 합니다", "반영합니다"),
    ("차감해야 합니다", "차감합니다"),
    ("분리해야 합니다", "분리합니다"),
)

_EXTERNAL_LABEL_PREFIXES: dict[str, str] = {
    "상황 / 목적": "",
    "문제 정의": "문제: ",
    "판단 질문": "검토 질문: ",
    "선택지 비교": "선택지: ",
    "판단 기준": "기준: ",
    "결론": "",
    "핵심 이유": "이유: ",
    "누락된 정보": "추가 확인 필요: ",
    "리스크": "리스크: ",
    "숨겨진 전제 / 가정": "가정: ",
    "단계별 추진 흐름": "",
    "중점 실행 과제": "",
    "근거": "근거: ",
    "핵심 규칙": "핵심 규칙: ",
    "설계 흐름": "",
    "적용 방향": "적용 방향: ",
    "후속 판단 포인트": "후속 판단 포인트: ",
}

_CODE_INPUT_HINTS: tuple[str, ...] = (
    r"\bselect\b",
    r"\bjoin\b",
    r"\bwhere\b",
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bsql\b",
    r"\bapi\b",
    r"\bclass\b",
    r"\bfunction\b",
    r"\bdef\b",
    r"\btable\b",
    r"\bschema\b",
    r"\bgl\b",
    r"\bfifo\b",
    r"\blot\b",
    r"입력 검증",
    r"저장 전",
    r"차단 조건",
    r"예외 처리",
    r"파라미터",
    r"조회 조건",
    r"전표",
    r"검증 규칙",
)

_DOCUMENT_INPUT_HINTS: tuple[str, ...] = (
    r"보고서",
    r"컨설팅",
    r"개요",
    r"배경",
    r"목적",
    r"비전",
    r"계획",
    r"전략",
    r"방향",
    r"효과",
    r"현행",
    r"추진",
    r"개선",
    r"문제 정의",
    r"검토 질문",
    r"제안",
)


def build_consulting_deck(
    contract: ConsultingMinContract,
    *,
    project_name: str,
    client_name: str,
    surface_mode: str,
    family: str = "",
    question_axis: str = "",
) -> dict[str, object]:
    normalized_surface_mode = "external" if surface_mode == "external" else "internal"
    normalized_family = _normalized_family(family)
    information_role = resolve_information_role(family=normalized_family, question_axis=question_axis)
    surface_style = _surface_style(contract, family=normalized_family, surface_mode=normalized_surface_mode)
    implementation_actions = _implementation_action_items(contract)
    vision_actions = _vision_action_items(implementation_actions)
    chapters = []
    for chapter_key, section_keys in _chapter_order(family=normalized_family, information_role=information_role):
        sections = []
        for section_key in section_keys:
            items = _section_items(
                contract,
                chapter_key=chapter_key,
                section_key=section_key,
                implementation_actions=implementation_actions,
                vision_actions=vision_actions,
                family=normalized_family,
                information_role=information_role,
            )
            resolved_items = _presentation_items(
                items,
                surface_mode=normalized_surface_mode,
                chapter_key=chapter_key,
                section_key=section_key,
                surface_style=surface_style,
            )
            sections.append(
                {
                    "section_key": section_key,
                    "title": _section_title(
                        chapter_key,
                        section_key,
                        family=normalized_family,
                        information_role=information_role,
                        surface_mode=normalized_surface_mode,
                        surface_style=surface_style,
                    ),
                    "items": resolved_items or [_empty_state_message(section_key, surface_mode=normalized_surface_mode)],
                    "uses_placeholder": not bool(resolved_items),
                }
            )
        chapters.append(
            {
                "chapter_key": chapter_key,
                "title": _chapter_title(
                    chapter_key,
                    family=normalized_family,
                    surface_mode=normalized_surface_mode,
                    information_role=information_role,
                ),
                "sections": sections,
            }
        )
    return {
        "project_name": project_name,
        "client_name": client_name,
        "surface_mode": normalized_surface_mode,
        "information_role": information_role,
        "role_label": role_label(information_role),
        "role_description": role_description(information_role),
        "role_header": role_header(family=normalized_family, question_axis=question_axis),
        "chapters": chapters,
    }


def _section_items(
    contract: ConsultingMinContract,
    *,
    chapter_key: str,
    section_key: str,
    implementation_actions: list[str],
    vision_actions: list[str],
    family: str = "",
    information_role: str = "",
) -> list[str]:
    if family == "operational_source":
        if information_role == "structure":
            if chapter_key == "overview" and section_key == "as_is":
                return _limit_items(contract.as_is, max_items=5)
            if chapter_key == "implementation" and section_key == "process_flow":
                return _process_flow_items(contract.process_flow, include_week_label=True, max_items=5)
            return []
        if information_role == "diagnosis":
            if chapter_key == "overview" and section_key == "as_is":
                return _limit_items(contract.as_is, max_items=2)
            if chapter_key == "approach" and section_key == "gap":
                return _limit_items(contract.gap, max_items=3)
            if chapter_key == "approach" and section_key == "risks":
                return _limit_items(contract.risks, max_items=4)
            return []
        if information_role == "decision":
            if chapter_key == "overview" and section_key == "as_is":
                return _limit_items(contract.as_is, max_items=2)
            if chapter_key == "design" and section_key == "rules":
                return _limit_items(contract.rules, max_items=4)
            if chapter_key == "vision" and section_key == "actions":
                return _limit_items(contract.actions, max_items=3)
            return []
        if chapter_key == "overview" and section_key == "as_is":
            return _overview_items(contract)
        if chapter_key == "approach" and section_key == "gap":
            return _limit_items(contract.gap, max_items=3) or _process_flow_items(contract.process_flow, include_week_label=False, max_items=3)
        if chapter_key == "approach" and section_key == "risks":
            return _limit_items(contract.risks, max_items=4)
        if chapter_key == "implementation" and section_key == "process_flow":
            return _process_flow_items(contract.process_flow, include_week_label=True, max_items=4)
        if chapter_key == "implementation" and section_key == "actions":
            return _limit_items(contract.actions, max_items=3)
        if chapter_key == "design" and section_key == "rules":
            return _limit_items(contract.rules, max_items=4)
        if chapter_key == "design" and section_key == "process_flow":
            return _design_flow_items(contract.process_flow)
        if chapter_key == "vision" and section_key == "actions":
            return _limit_items(contract.actions, max_items=3)
    if chapter_key == "overview" and section_key == "as_is":
        return _generic_overview_items(contract)
    if chapter_key == "approach" and section_key == "gap":
        return _generic_judgment_items(contract)
    if chapter_key == "approach" and section_key == "risks":
        return _generic_risk_items(contract)
    if chapter_key == "implementation" and section_key == "process_flow":
        return _labeled_group_items(
            [
                (
                    "단계별 추진 흐름",
                    _process_flow_items(contract.process_flow, include_week_label=True, max_items=4),
                )
            ]
        )
    if chapter_key == "implementation" and section_key == "actions":
        return _labeled_group_items([("중점 실행 과제", implementation_actions)])
    if chapter_key == "design" and section_key == "rules":
        return _labeled_group_items(
            [
                ("근거", _limit_items(contract.evidence, max_items=4)),
                ("핵심 규칙", _limit_items(contract.rules, max_items=4)),
            ]
        )
    if chapter_key == "design" and section_key == "process_flow":
        return _labeled_group_items([("설계 흐름", _design_flow_items(contract.process_flow))])
    if chapter_key == "vision" and section_key == "actions":
        follow_up_items = _limit_items(contract.missing_information, max_items=2) or _limit_items(contract.decision_question, max_items=1)
        application_items = vision_actions or _softened_conclusion_items(contract.conclusion, contract.missing_information)
        return _labeled_group_items(
            [
                ("적용 방향", application_items),
                ("후속 판단 포인트", follow_up_items),
            ]
        )
    return _limit_items(getattr(contract, section_key, []) or [], max_items=4)


def _normalized_family(family: str) -> str:
    normalized = _normalize_spaces(family)
    return normalized if normalized in _FAMILY_CHAPTER_TITLES else ""


def _surface_style(contract: ConsultingMinContract, *, family: str, surface_mode: str) -> str:
    if surface_mode != "external":
        return "document_style"
    if family == "operational_source":
        return "technical_style"
    joined = " ".join(
        [
            *list(contract.context or []),
            *list(contract.problem_definition or []),
            *list(contract.decision_question or []),
            *list(contract.options or []),
            *list(contract.decision_criteria or []),
            *list(contract.evidence or []),
            *list(contract.missing_information or []),
            *list(contract.as_is or []),
            *list(contract.process_flow or []),
            *list(contract.rules or []),
            *list(contract.risks or []),
            *list(contract.actions or []),
        ]
    ).lower()
    code_score = sum(1 for pattern in _CODE_INPUT_HINTS if re.search(pattern, joined, re.IGNORECASE))
    document_score = sum(1 for pattern in _DOCUMENT_INPUT_HINTS if re.search(pattern, joined, re.IGNORECASE))
    if code_score >= 4 and (document_score <= 2 or code_score >= document_score * 2):
        return "technical_style"
    if code_score >= 3 and document_score >= 3:
        return "mixed_style"
    return "document_style"


def _chapter_order(*, family: str, information_role: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if family in {"operational_source", "option_comparison"} and information_role in _OPERATIONAL_ROLE_CHAPTER_ORDER:
        return _OPERATIONAL_ROLE_CHAPTER_ORDER[information_role]
    return _CHAPTER_ORDER


def _section_title(
    chapter_key: str,
    section_key: str,
    *,
    family: str,
    information_role: str = "",
    surface_mode: str = "internal",
    surface_style: str = "document_style",
) -> str:
    if surface_mode == "external":
        if surface_style == "technical_style":
            overrides = {
                ("overview", "as_is"): "핵심 문제",
                ("approach", "risks"): "영향",
                ("implementation", "actions"): "권장 조치",
                ("design", "rules"): "검증 포인트",
            }
            title = overrides.get((chapter_key, section_key))
            if title:
                return title
        if surface_style == "mixed_style":
            overrides = {
                ("implementation", "process_flow"): "코드 분석 포인트",
                ("design", "rules"): "코드 검증 포인트",
            }
            title = overrides.get((chapter_key, section_key))
            if title:
                return title
    role_title = _OPERATIONAL_ROLE_SECTION_TITLES.get(information_role, {}).get((chapter_key, section_key))
    if family in {"operational_source", "option_comparison"} and role_title:
        return role_title
    family_titles = _FAMILY_SECTION_TITLES.get(family, {})
    family_section_titles = family_titles.get(chapter_key, {})
    title = family_section_titles.get(section_key)
    if title:
        return title
    return _SECTION_TITLES[chapter_key][section_key]


def _chapter_title(chapter_key: str, *, family: str, surface_mode: str, information_role: str = "") -> str:
    role_title = _OPERATIONAL_ROLE_CHAPTER_TITLES.get(information_role, {}).get(chapter_key)
    if family in {"operational_source", "option_comparison"} and role_title:
        return role_title
    family_titles = _FAMILY_CHAPTER_TITLES.get(family, {})
    mode_titles = family_titles.get(surface_mode, {})
    title = mode_titles.get(chapter_key)
    if title:
        return title
    return _CHAPTER_TITLES[surface_mode][chapter_key]


def _presentation_items(
    items: list[str],
    *,
    surface_mode: str,
    chapter_key: str = "",
    section_key: str = "",
    surface_style: str = "document_style",
) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = _normalize_spaces(item) if surface_mode != "external" else _externalize_item(item)
        key = _comparison_key(normalized)
        if not normalized or not key or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    if surface_mode == "external" and chapter_key == "approach" and section_key == "gap":
        return _compact_external_judgment_items(output)
    if surface_mode == "external" and surface_style == "technical_style":
        section_map = {
            ("overview", "as_is"): "핵심 문제",
            ("approach", "risks"): "영향",
            ("implementation", "actions"): "권장 조치",
            ("design", "rules"): "검증 포인트",
        }
        prefix = section_map.get((chapter_key, section_key))
        if prefix:
            return _style_prefixed_items(output, prefix)
    if surface_mode == "external" and surface_style == "mixed_style":
        section_map = {
            ("implementation", "process_flow"): "코드 분석 포인트",
            ("design", "rules"): "검증 포인트",
        }
        prefix = section_map.get((chapter_key, section_key))
        if prefix:
            return _style_prefixed_items(output, prefix)
    return output


def _empty_state_message(section_key: str, *, surface_mode: str) -> str:
    if surface_mode == "external":
        return _EXTERNAL_EMPTY_STATE_MESSAGES[section_key]
    return _EMPTY_STATE_MESSAGES[section_key]


def _externalize_text(text: str) -> str:
    normalized = _concise_text(text)
    if not normalized:
        return ""
    replacements = (
        ("해야 합니다", ""),
        ("해야합니다", ""),
        ("해야 한다", ""),
        ("하는 것이 필요합니다", ""),
        ("할 필요가 있습니다", ""),
        ("가 필요합니다", ""),
        ("이 필요합니다", ""),
        ("필요합니다", ""),
        ("확인하는 편이 좋습니다", "확인하는 편이 안전합니다"),
        ("검토하는 편이 적절합니다", "검토하는 편이 안전합니다"),
        ("유지하는 편이 안전합니다", "유지하는 편이 안전합니다"),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"^(따라서|즉|그리고)\s+", "", normalized)
    normalized = normalized.replace("우선 검토안", "적용 방향")
    normalized = normalized.replace("검토안", "적용 방향")
    normalized = normalized.replace("개선 후보", "개선안")
    normalized = normalized.replace("후속 개선 후보", "후속 개선안")
    normalized = normalized.replace("후보", "대상")
    normalized = normalized.strip(" ,")
    return normalized


def _externalize_item(text: str) -> str:
    normalized = _normalize_spaces(text)
    if not normalized:
        return ""
    match = re.match(r"^\[(?P<label>[^\]]+)\]\s*(?P<body>.+)$", normalized)
    if not match:
        return _externalize_text(normalized)
    label = str(match.group("label") or "").strip()
    body = _externalize_text(str(match.group("body") or "").strip())
    if not body:
        return ""
    if label == "결론":
        body = re.sub(r"^현 단계 우선 검토안:\s*", "", body).strip()
        body = re.sub(r"^우선 검토안:\s*", "", body).strip()
        body = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", body).strip()
        if body == "추가 확인 후 확정 필요":
            return "추가 확인 후 재판단"
        return f"검증 후 적용: {_short_external_fragment(body, max_length=30)}" if body else ""
    prefix = _EXTERNAL_LABEL_PREFIXES.get(label, "")
    rendered = f"{prefix}{body}" if prefix else body
    return _short_external_fragment(rendered, max_length=34 if label in {"핵심 이유", "근거", "누락된 정보", "리스크"} else 40)


def _compact_external_judgment_items(items: list[str]) -> list[str]:
    if not items:
        return []
    state_item = next((item for item in items if re.match(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가):", item)), "")
    reason_item = next((item for item in items if item.startswith("이유: ")), "")
    support_item = next((item for item in items if item.startswith("근거: ") or item.startswith("기준: ")), "")
    follow_up_item = next((item for item in items if item.startswith("추가 확인 필요: ")), "")
    compacted = [item for item in (state_item, reason_item, follow_up_item or support_item) if item]
    return compacted or items[:3]


def _style_prefixed_items(items: list[str], prefix: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _short_external_fragment(_normalize_spaces(item), max_length=34)
        normalized = re.sub(r"^(실행 착수 가능|조건 확인 후 실행|검증 후 적용|실행 불가)\s*:?\s*", "", normalized).strip()
        if not normalized:
            continue
        rendered = f"{prefix}: {normalized}"
        key = _comparison_key(rendered)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(rendered)
        if len(output) >= 3:
            break
    return output


def _overview_items(contract: ConsultingMinContract) -> list[str]:
    items = _limit_items(contract.as_is, max_items=3)
    if not items or not _is_fx_fifo_contract(contract):
        return items
    filtered = [
        item
        for item in items
        if not any(pattern in item.lower() for pattern in _OVERVIEW_NOISE_PATTERNS)
    ]
    return filtered or items


def _generic_overview_items(contract: ConsultingMinContract) -> list[str]:
    context_items = _limit_items(contract.context, max_items=4)
    problem_items = _limit_items(contract.problem_definition, max_items=3) or _overview_items(contract)
    return _labeled_group_items(
        [
            ("상황 / 목적", context_items),
            ("문제 정의", problem_items),
        ]
    )


def _generic_judgment_items(contract: ConsultingMinContract) -> list[str]:
    key_reason_items = _limit_items(contract.key_reasons, max_items=3) or _limit_items(contract.gap, max_items=4)
    return _labeled_group_items(
        [
            ("판단 질문", _limit_items(contract.decision_question, max_items=2)),
            ("선택지 비교", _limit_items(contract.options, max_items=3)),
            ("판단 기준", _limit_items(contract.decision_criteria, max_items=3)),
            ("결론", _softened_conclusion_items(contract.conclusion, contract.missing_information)),
            ("핵심 이유", key_reason_items),
        ]
    )


def _generic_risk_items(contract: ConsultingMinContract) -> list[str]:
    return _labeled_group_items(
        [
            ("숨겨진 전제 / 가정", _limit_items(contract.assumptions, max_items=2)),
            ("누락된 정보", _limit_items(contract.missing_information, max_items=3)),
            ("리스크", _limit_items(contract.risks, max_items=4)),
        ]
    )


def _softened_conclusion_items(items: list[str], missing_information: list[str]) -> list[str]:
    conclusions = _limit_items(items, max_items=1)
    if not missing_information:
        return conclusions
    if conclusions:
        return [f"검증 후 적용: {conclusions[0]}"]
    return ["추가 확인 후 재판단"]


def _labeled_group_items(groups: list[tuple[str, list[str]]]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for label, items in groups:
        normalized_items: list[str] = []
        for item in items or []:
            normalized = _normalize_spaces(item)
            key = _comparison_key(normalized)
            if not normalized or not key or key in seen:
                continue
            seen.add(key)
            normalized_items.append(normalized)
        for index, item in enumerate(normalized_items):
            output.append(f"[{label}] {item}" if index == 0 else item)
    return output


def _process_flow_items(items: list[str], *, include_week_label: bool, max_items: int) -> list[str]:
    prepared: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        concise = _concise_text(item)
        if not concise:
            continue
        rendered = concise if include_week_label else _strip_week_label(concise)
        key = _comparison_key(rendered)
        if not key or key in seen:
            continue
        seen.add(key)
        prepared.append(rendered)
    return prepared[:max_items]


def _design_flow_items(items: list[str]) -> list[str]:
    process_items = _process_flow_items(items, include_week_label=False, max_items=4)
    if not process_items:
        return []
    selected = [
        item
        for item in process_items
        if any(keyword in item.lower() for keyword in _DESIGN_FLOW_KEYWORDS)
    ]
    return (selected or process_items)[:3]


def _implementation_action_items(contract: ConsultingMinContract) -> list[str]:
    process_keys = {
        _comparison_key(_strip_week_label(item))
        for item in contract.process_flow or []
        if _comparison_key(_strip_week_label(item))
    }
    prepared: list[str] = []
    seen: set[str] = set()
    for item in contract.actions or []:
        concise = _concise_action_text(item)
        if not concise:
            continue
        key = _comparison_key(concise)
        if not key or key in seen or key in process_keys:
            continue
        seen.add(key)
        prepared.append(concise)
    return _drop_common_prefix(prepared)[:3]


def _vision_action_items(implementation_actions: list[str]) -> list[str]:
    vision_items = [_visionize_text(item) for item in implementation_actions]
    return _limit_items(vision_items, max_items=3)


def _visionize_text(text: str) -> str:
    normalized = _normalize_spaces(text).rstrip(".")
    if not normalized:
        return ""
    if normalized.endswith("분리"):
        return f"{normalized} 체계"
    if normalized.endswith("고정"):
        return f"{normalized} 기준"
    if normalized.endswith("연결"):
        return f"{normalized} 체계"
    if normalized.endswith("반영"):
        return f"{normalized} 흐름"
    return normalized


def _limit_items(items: list[str], *, max_items: int) -> list[str]:
    prepared: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        concise = _concise_text(item)
        key = _comparison_key(concise)
        if not concise or not key or key in seen:
            continue
        seen.add(key)
        prepared.append(concise)
    return prepared[:max_items]


def _concise_action_text(text: str) -> str:
    normalized = _concise_text(text)
    if not normalized:
        return ""
    normalized = re.sub(r"하는 것이 필요합니다$", "", normalized).strip()
    normalized = re.sub(r"할 필요가 있습니다$", "", normalized).strip()
    normalized = re.sub(r"가 필요합니다$", "", normalized).strip()
    normalized = re.sub(r"이 필요합니다$", "", normalized).strip()
    normalized = normalized.rstrip(" ,.")
    return normalized


def _concise_text(text: str) -> str:
    normalized = _normalize_spaces(text).rstrip(".")
    if not normalized:
        return ""
    for old, new in _CONCISE_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    return normalized.strip(" ,")


def _short_external_fragment(text: str, *, max_length: int = 32) -> str:
    normalized = _normalize_spaces(text).strip(" ,.")
    if not normalized:
        return ""
    separators = ("입니다 ", "이며 ", "이므로 ", ", ", " · ", " 및 ", "해서 ", "하고 ")
    for separator in separators:
        if len(normalized) <= max_length:
            break
        if separator in normalized:
            candidate = normalized.split(separator, 1)[0].strip(" ,.")
            if candidate:
                normalized = candidate
    if len(normalized) <= max_length:
        return normalized
    clipped = normalized[: max_length + 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return clipped.strip(" ,.")


def _normalize_spaces(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _strip_week_label(text: str) -> str:
    return re.sub(r"^\d+\s*주차\s*:\s*", "", _normalize_spaces(text))


def _comparison_key(text: str) -> str:
    normalized = _strip_week_label(_normalize_spaces(text)).lower()
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def _drop_common_prefix(items: list[str]) -> list[str]:
    if len(items) < 2:
        return items
    prefix = items[0]
    for item in items[1:]:
        while prefix and not item.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            return items
    marker = prefix.rfind("의 ")
    if marker < 4:
        return items
    removable_prefix = prefix[: marker + 2]
    trimmed = [item[len(removable_prefix):].strip() for item in items if item.startswith(removable_prefix)]
    if len(trimmed) != len(items) or any(not item for item in trimmed):
        return items
    return trimmed


def _is_fx_fifo_contract(contract: ConsultingMinContract) -> bool:
    joined = " ".join(
        [
            *list(contract.as_is or []),
            *list(contract.process_flow or []),
            *list(contract.rules or []),
            *list(contract.risks or []),
            *list(contract.gap or []),
            *list(contract.actions or []),
        ]
    ).lower()
    hits = sum(1 for keyword in _FX_FIFO_KEYWORDS if keyword in joined)
    return hits >= 2
