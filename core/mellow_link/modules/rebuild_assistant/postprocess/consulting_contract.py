from __future__ import annotations

from typing import Any

from .information_separation import purify_diagnosis_lines, resolve_information_role
from .schemas import ConsultingMinContract

_PROBLEM_TOKENS: tuple[str, ...] = (
    "막혀",
    "문제",
    "불일치",
    "누락",
    "부족",
    "분산",
    "중복",
    "혼재",
    "복잡",
    "결합",
    "어긋",
    "흔들",
    "지연",
    "단절",
    "리스크",
    "위험",
)
_CRITERIA_TOKENS: tuple[str, ...] = (
    "기준",
    "비용",
    "리스크",
    "속도",
    "유지보수",
    "정합",
    "실행 가능",
    "일관",
    "재현",
    "호환",
    "확장",
    "검증",
    "추적",
    "우선순위",
)
_ASSUMPTION_TOKENS: tuple[str, ...] = (
    "가정",
    "전제",
    "한정",
    "전제로",
)


def build_consulting_min_contract(source: dict[str, Any]) -> ConsultingMinContract:
    normalized_source = source if isinstance(source, dict) else {}
    family = _normalized_text(normalized_source.get("family"))
    question_axis = _normalized_text(normalized_source.get("question_axis"))
    role = resolve_information_role(family=family, question_axis=question_axis)
    if role and (family == "operational_source" or (family == "option_comparison" and role == "decision")):
        return _build_operational_information_contract(normalized_source, family=family, role=role)
    return ConsultingMinContract(
        as_is=_collect_as_is(normalized_source, family=family),
        process_flow=_collect_process_flow(normalized_source, family=family),
        rules=_collect_rules(normalized_source, family=family),
        risks=_collect_risks(normalized_source),
        gap=_collect_gap(normalized_source, family=family),
        actions=_collect_actions(normalized_source, family=family),
        **_presentation_contract_fields(normalized_source),
    )


def _build_operational_information_contract(source: dict[str, Any], *, family: str, role: str) -> ConsultingMinContract:
    presentation_fields = _presentation_contract_fields(source)
    as_is = _collect_as_is(source, family=family)
    process_flow = _collect_process_flow(source, family=family)
    rules = _collect_rules(source, family=family)
    risks = _collect_risks(source)
    gap = _collect_gap(source, family=family)
    actions = _collect_actions(source, family=family)

    if role == "structure":
        return ConsultingMinContract(
            as_is=_structure_lines(as_is),
            process_flow=_structure_lines(process_flow),
            rules=[],
            risks=[],
            gap=[],
            actions=[],
            **presentation_fields,
        )
    if role == "diagnosis":
        diagnosis_focus = _diagnosis_focus_lines(source, gap=gap, risks=risks)
        return ConsultingMinContract(
            as_is=diagnosis_focus[:2],
            process_flow=[],
            rules=[],
            risks=_diagnosis_lines(risks)[:4],
            gap=_diagnosis_lines(gap or diagnosis_focus)[:3],
            actions=[],
            **presentation_fields,
        )
    if role == "decision":
        return ConsultingMinContract(
            as_is=_decision_summary_lines(source)[:2],
            process_flow=[],
            rules=_decision_criteria_lines(source, fallback=rules)[:4],
            risks=[],
            gap=_decision_basis_lines(source, fallback=gap)[:3],
            actions=_decision_action_lines(source, fallback=actions)[:3],
            **presentation_fields,
        )
    return ConsultingMinContract(
        as_is=as_is,
        process_flow=process_flow,
        rules=rules,
        risks=risks,
        gap=gap,
        actions=actions,
        **presentation_fields,
    )


def _presentation_contract_fields(source: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "context": _collect_context(source),
        "problem_definition": _collect_problem_definition(source),
        "decision_question": _collect_decision_question(source),
        "options": _collect_options(source),
        "decision_criteria": _collect_decision_criteria(source),
        "conclusion": _collect_conclusion(source),
        "key_reasons": _collect_key_reasons(source),
        "evidence": _collect_evidence(source),
        "assumptions": _collect_assumptions(source),
        "missing_information": _collect_missing_information(source),
    }


def _collect_context(source: dict[str, Any]) -> list[str]:
    items: list[str] = []
    report_purpose = _normalized_text(source.get("report_purpose"))
    if report_purpose:
        items.append(report_purpose)
    items.extend(f"범위: {item}" for item in _string_list(source.get("report_scope")))
    items.extend(f"검토 질문: {item}" for item in _string_list(source.get("report_questions")))
    customer_intent = source.get("customer_intent") or {}
    if isinstance(customer_intent, dict):
        items.extend(
            f"사용자 의도: {item}"
            for item in _string_list(customer_intent.get("items"))
        )
    return _dedupe(items)


def _collect_problem_definition(source: dict[str, Any]) -> list[str]:
    candidates = [
        *_string_list(source.get("analysis_summary")),
        _normalized_text(source.get("primary_judgment_reason")),
    ]
    return _dedupe(item for item in candidates if _looks_like_problem_definition(item))


def _collect_decision_question(source: dict[str, Any]) -> list[str]:
    return _string_list(source.get("report_questions"))


def _collect_options(source: dict[str, Any]) -> list[str]:
    option_lines: list[str] = []
    for item in source.get("design_options") or []:
        if not isinstance(item, dict):
            continue
        name = _normalized_text(item.get("name"))
        summary = _normalized_text(item.get("structure_summary"))
        if name and summary and summary.lower() != name.lower():
            option_lines.append(f"{name}: {summary}")
        elif name:
            option_lines.append(name)
    deduped = _dedupe(option_lines)
    return deduped if len(deduped) >= 2 else []


def _collect_decision_criteria(source: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    recommended_option = source.get("recommended_option") or {}
    if isinstance(recommended_option, dict):
        selection_reason = _normalized_text(recommended_option.get("selection_reason"))
        if selection_reason and _looks_like_decision_criteria(selection_reason):
            candidates.append(selection_reason)
    for item in source.get("priority_split_items") or []:
        if not isinstance(item, dict):
            continue
        reason = _normalized_text(item.get("reason"))
        if reason and _looks_like_decision_criteria(reason):
            candidates.append(reason)
    for item in source.get("decision_items") or []:
        if not isinstance(item, dict):
            continue
        rationale = _normalized_text(item.get("rationale"))
        if rationale and _looks_like_decision_criteria(rationale):
            candidates.append(rationale)
    return _dedupe(candidates)


def _collect_conclusion(source: dict[str, Any]) -> list[str]:
    recommended_option = source.get("recommended_option") or {}
    option_name = _normalized_text(recommended_option.get("name")) if isinstance(recommended_option, dict) else ""
    for candidate in (
        _normalized_text(source.get("core_conclusion")),
        option_name,
        *_string_list(source.get("recommended_directions")),
    ):
        if candidate:
            return [candidate]
    return []


def _collect_key_reasons(source: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    recommended_option = source.get("recommended_option") or {}
    if isinstance(recommended_option, dict):
        selection_reason = _normalized_text(recommended_option.get("selection_reason"))
        if selection_reason:
            candidates.append(selection_reason)
    primary_reason = _normalized_text(source.get("primary_judgment_reason"))
    if primary_reason:
        candidates.append(primary_reason)
    for item in source.get("decision_items") or []:
        if not isinstance(item, dict):
            continue
        rationale = _normalized_text(item.get("rationale"))
        if rationale:
            candidates.append(rationale)
    return _dedupe(candidates)


def _collect_evidence(source: dict[str, Any]) -> list[str]:
    items = list(_string_list(source.get("analysis_summary")))
    for item in source.get("grounded_business_rules") or []:
        if not isinstance(item, dict):
            continue
        title = _normalized_text(item.get("title"))
        description = _normalized_text(item.get("description"))
        if title and description:
            items.append(f"{title}: {description}")
        elif title:
            items.append(title)
        elif description:
            items.append(description)
    for item in source.get("retained_contracts") or []:
        if not isinstance(item, dict):
            continue
        contract_item = _normalized_text(item.get("item"))
        basis = _normalized_text(item.get("basis"))
        if contract_item and basis:
            items.append(f"{contract_item}: {basis}")
        elif contract_item:
            items.append(contract_item)
    return _dedupe(items)


def _collect_assumptions(source: dict[str, Any]) -> list[str]:
    if "assumptions" in source:
        statements: list[str] = []
        for item in source.get("assumptions") or []:
            if isinstance(item, dict):
                statement = _normalized_text(item.get("statement"))
            else:
                statement = _normalized_text(getattr(item, "statement", item))
            if statement:
                statements.append(statement)
        return _dedupe(statements)
    candidates: list[str] = []
    recommended_option = source.get("recommended_option") or {}
    if isinstance(recommended_option, dict):
        selection_reason = _normalized_text(recommended_option.get("selection_reason"))
        if selection_reason and _looks_like_assumption(selection_reason):
            candidates.append(selection_reason)
    for raw in (
        *_string_list(source.get("analysis_summary")),
        _normalized_text(source.get("primary_judgment_reason")),
        *_string_list(source.get("risks")),
    ):
        if raw and _looks_like_assumption(raw):
            candidates.append(raw)
    return _dedupe(candidates)


def _collect_missing_information(source: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for item in source.get("missing_context_details") or []:
        if not isinstance(item, dict):
            continue
        required_material = _normalized_text(item.get("required_material"))
        reason = _normalized_text(item.get("reason"))
        if required_material and reason:
            items.append(f"{required_material}: {reason}")
        elif reason:
            items.append(reason)
        elif required_material:
            items.append(required_material)
    return _dedupe(items)


def _collect_as_is(source: dict[str, Any], *, family: str = "") -> list[str]:
    analysis_summary = _string_list(source.get("analysis_summary"))
    if analysis_summary:
        return analysis_summary
    return _string_list(source.get("core_conclusion"))


def _collect_process_flow(source: dict[str, Any], *, family: str = "") -> list[str]:
    items = []
    for item in source.get("execution_plan") or []:
        if not isinstance(item, dict):
            continue
        week_label = _normalized_text(item.get("week_label"))
        goal = _normalized_text(item.get("goal"))
        if week_label and goal:
            items.append(f"{week_label}: {goal}")
        elif goal:
            items.append(goal)
        if family == "operational_source":
            first_task = next(
                (_normalized_text(task) for task in (item.get("tasks") or []) if _normalized_text(task)),
                "",
            )
            if first_task:
                items.append(first_task)
    if items:
        return _dedupe(items)
    return _string_list(source.get("recommended_directions"))


def _collect_rules(source: dict[str, Any], *, family: str = "") -> list[str]:
    items = []
    for item in source.get("grounded_business_rules") or []:
        if not isinstance(item, dict):
            continue
        title = _normalized_text(item.get("title"))
        description = _normalized_text(item.get("description"))
        if title and description:
            items.append(f"{title}: {description}")
        elif title:
            items.append(title)
        elif description:
            items.append(description)
    if items:
        return _dedupe(items)
    if family == "operational_source":
        summary_lines = [
            _normalized_text(item)
            for item in (source.get("analysis_summary") or [])
            if _normalized_text(item) and not str(_normalized_text(item)).startswith("핵심 객체는")
        ]
        if summary_lines:
            return _dedupe(summary_lines[:4])
    return _dedupe(
        _normalized_text(item.get("item"))
        for item in (source.get("retained_contracts") or [])
        if isinstance(item, dict)
    )


def _collect_risks(source: dict[str, Any]) -> list[str]:
    return _dedupe(_string_list(source.get("risks")))


def _collect_gap(source: dict[str, Any], *, family: str = "") -> list[str]:
    if family == "operational_source":
        primary_reason = _normalized_text(source.get("primary_judgment_reason"))
        if primary_reason:
            return [primary_reason]
        process_flow = _collect_process_flow(source, family=family)
        return process_flow[:2]
    items = []
    for item in source.get("decision_items") or []:
        if not isinstance(item, dict):
            continue
        rationale = _normalized_text(item.get("rationale"))
        if rationale:
            items.append(rationale)
    if items:
        return _dedupe(items)
    for item in source.get("priority_split_items") or []:
        if not isinstance(item, dict):
            continue
        reason = _normalized_text(item.get("reason"))
        if reason:
            items.append(reason)
    return _dedupe(items)


def _collect_actions(source: dict[str, Any], *, family: str = "") -> list[str]:
    if family == "operational_source":
        recommended = _string_list(source.get("recommended_directions"))
        if recommended:
            return recommended
        process_flow = _collect_process_flow(source, family=family)
        return process_flow[:3]
    items = []
    for item in source.get("decision_items") or []:
        if not isinstance(item, dict):
            continue
        statement = _normalized_text(item.get("statement"))
        if statement:
            items.append(statement)
    for item in source.get("execution_plan") or []:
        if not isinstance(item, dict):
            continue
        goal = _normalized_text(item.get("goal"))
        if goal:
            items.append(goal)
    if items:
        return _dedupe(items)
    return _string_list(source.get("recommended_directions"))


def _structure_lines(items: list[str]) -> list[str]:
    return _dedupe(
        item
        for item in items
        if not _contains_any(item, ("리스크", "위험", "문제", "불일치", "추천", "우선안", "분리", "재설계", "개선"))
    )


def _diagnosis_lines(items: list[str]) -> list[str]:
    return _dedupe(purify_diagnosis_lines("diagnosis", items, use_fallback=False))


def _diagnosis_focus_lines(source: dict[str, Any], *, gap: list[str], risks: list[str]) -> list[str]:
    lines = _diagnosis_lines([*gap, *risks])
    if lines:
        return lines
    if _is_fx_fifo_source(source):
        return [
            "전표 생성 기준과 회계 연결 기준이 달라질 가능성을 진단합니다.",
            "거래 기준번호가 유지되지 않으면 전표와 회계 반영 결과가 어긋날 수 있습니다.",
        ]
    return [
        "연계 기준이 어긋날 가능성을 진단합니다.",
        "같은 거래 기준이 유지되지 않으면 운영 정합성이 흔들릴 수 있습니다.",
    ]


def _decision_summary_lines(source: dict[str, Any]) -> list[str]:
    if _is_fx_fifo_source(source):
        return [
            "현행 FIFO 기준을 유지할지와 계산 검증 기준을 어떻게 둘지 판단합니다.",
            "선택은 계산 재현성, 환율 기준 일관성, 회계 연결 가능성을 기준으로 정리합니다.",
        ]
    return [
        "현행 계산 또는 처리 기준을 유지할지와 검증 기준을 어떻게 둘지 판단합니다.",
        "선택은 재현성, 기준 일관성, 후속 연결 가능성을 기준으로 정리합니다.",
    ]


def _decision_criteria_lines(source: dict[str, Any], *, fallback: list[str]) -> list[str]:
    if _is_fx_fifo_source(source):
        return [
            "비교 기준: FIFO 재현 가능성, 환율 기준 일관성, 회계 연결 가능성을 우선합니다.",
            "선택지 1: 현행 FIFO 기준을 유지하고 예외 검증을 보강합니다.",
            "선택지 2: 평균 기준으로 단순화하되 기존 lot 추적성 저하를 감수합니다.",
            "선택지 3: 거래별 지정 기준을 두되 운영 입력 부담을 별도로 관리합니다.",
        ]
    if fallback:
        return _dedupe(f"비교 기준: {_strip_role_prefix(item)}" for item in fallback)
    return ["비교 기준: 재현 가능성, 기준 일관성, 후속 연결 가능성을 우선합니다."]


def _decision_basis_lines(source: dict[str, Any], *, fallback: list[str]) -> list[str]:
    if _is_fx_fifo_source(source):
        return [
            "우선 판단은 현행 FIFO 기준 유지입니다.",
            "계산 결과와 회계 반영 기준을 같은 거래 기준으로 검증할 수 있어야 합니다.",
        ]
    if fallback:
        return _dedupe(_strip_role_prefix(item) for item in fallback)
    return ["우선 판단은 현행 기준 유지 후 검증 항목을 보강하는 방식입니다."]


def _decision_action_lines(source: dict[str, Any], *, fallback: list[str]) -> list[str]:
    if _is_fx_fifo_source(source):
        return [
            "추천안: 현행 FIFO 기준을 유지하고 환율 비교와 회계 연결 검증을 함께 둡니다.",
            "적용 기준: 예외와 취소 처리에서도 같은 계산 기준이 유지되는지 확인합니다.",
            "참조: 처리 단계 상세는 Structure 문서, 전표/GL 영향은 Diagnosis 문서를 따릅니다.",
        ]
    if fallback:
        return _dedupe(_strip_role_prefix(item) for item in fallback)
    return ["추천안: 현행 기준을 유지하고 검증 항목을 먼저 보강합니다."]


def _looks_like_problem_definition(text: str) -> bool:
    return _contains_any(text, _PROBLEM_TOKENS)


def _looks_like_decision_criteria(text: str) -> bool:
    return _contains_any(text, _CRITERIA_TOKENS)


def _looks_like_assumption(text: str) -> bool:
    return _contains_any(text, _ASSUMPTION_TOKENS)


def _strip_role_prefix(text: str) -> str:
    return (
        _normalized_text(text)
        .removeprefix("현행 분석:")
        .removeprefix("핵심 흐름:")
        .removeprefix("주요 업무 규칙:")
        .removeprefix("운영 리스크:")
        .strip()
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(str(needle).lower() in lowered for needle in needles)


def _is_fx_fifo_source(source: dict[str, Any]) -> bool:
    joined = " ".join(
        [
            *list(_string_list(source.get("analysis_summary"))),
            *list(_string_list(source.get("core_business_rules"))),
            *list(_string_list(source.get("recommended_directions"))),
            *list(_string_list(source.get("risks"))),
            _normalized_text(source.get("core_conclusion")),
            _normalized_text(source.get("primary_judgment_reason")),
        ]
    ).lower()
    return sum(1 for keyword in ("fifo", "lot", "환차", "전표", "gl", "외화") if keyword in joined) >= 2


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = _normalized_text(value)
        return [normalized] if normalized else []
    if not isinstance(value, list):
        return []
    return _dedupe(_normalized_text(item) for item in value)


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe(items: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalized_text(item)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output
