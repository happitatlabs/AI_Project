from __future__ import annotations

import re
from typing import Any


OPERATIONAL_INFORMATION_ROLE_BY_AXIS: dict[str, str] = {
    "processing_flow": "structure",
    "journal_linkage": "diagnosis",
    "calculation_rule": "decision",
}

ROLE_LABELS: dict[str, str] = {
    "structure": "Structure",
    "diagnosis": "Diagnosis",
    "decision": "Decision",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "structure": "흐름 중심 문서",
    "diagnosis": "전표/GL 연계 진단 문서",
    "decision": "선택/계산 규칙 판단 문서",
}

DIAGNOSIS_FORBIDDEN_TERMS: tuple[str, ...] = (
    "옵션",
    "option",
    "선택지",
    "추천안",
    "추천",
    "검토안",
    "개선안",
    "구조 개선",
    "개선",
    "설계",
    "조치",
    "후속",
    "실행 계획",
    "실행",
    "추진 계획",
    "추진",
    "주차",
    "단계별",
    "단계",
)

DIAGNOSIS_SECTION_FALLBACKS: dict[str, tuple[str, ...]] = {
    "report_purpose": (
        "외화 입출금 결과와 전표/GL 연결 기준의 불일치 가능성을 요약합니다.",
    ),
    "executive_summary_v2": (
        "전표 생성 기준과 GL 연결 기준이 같은 거래 기준으로 이어지는지 불명확합니다.",
        "lot 소진 순서, 환율 기준, 취소 역처리, 회계 연결 기준이 서로 달라질 수 있습니다.",
        "취소나 역처리 시 원거래 기준 유지 여부가 불명확합니다.",
    ),
    "primary_judgment_reason": (
        "전표 기준과 회계 연결 기준이 달라질 경우 계산 결과와 전표 반영 간 불일치가 발생할 수 있습니다.",
    ),
    "risks": (
        "회계 반영 누락, 중복 반영, 취소·역처리 불일치가 발생할 수 있습니다.",
    ),
}


def operational_information_role(question_axis: str | None) -> str:
    axis = str(question_axis or "").strip()
    return OPERATIONAL_INFORMATION_ROLE_BY_AXIS.get(axis, "structure")


def resolve_information_role(*, family: str | None, question_axis: str | None) -> str:
    normalized_family = str(family or "").strip()
    if normalized_family == "operational_source":
        return operational_information_role(question_axis)
    if normalized_family == "option_comparison":
        return "decision"
    return ""


def role_label(role: str | None) -> str:
    return ROLE_LABELS.get(str(role or "").strip(), "")


def role_description(role: str | None) -> str:
    return ROLE_DESCRIPTIONS.get(str(role or "").strip(), "")


def diagnosis_line_is_forbidden(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).strip().lower()
    if not normalized:
        return True
    return any(term in normalized for term in DIAGNOSIS_FORBIDDEN_TERMS)


def _normalize_diagnosis_line(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return ""
    if normalized.startswith("참조:"):
        return ""
    normalized = re.sub(r"가능성을\s*(?:점검|확인)해야\s*합니다\.?", "가능성이 있습니다.", normalized)
    normalized = re.sub(r"여부를\s*(?:점검|확인)합니다\.?", "여부가 불명확합니다.", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized).strip()
    if "해야" in normalized:
        return ""
    if diagnosis_line_is_forbidden(normalized):
        return ""
    return normalized


def purify_diagnosis_lines(
    section_key: str,
    lines: list[str] | tuple[str, ...] | None,
    *,
    use_fallback: bool = True,
) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw_line in list(lines or []):
        normalized = _normalize_diagnosis_line(str(raw_line or ""))
        key = re.sub(r"[\s\W_]+", "", normalized).lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    if output or not use_fallback:
        return output
    fallback = DIAGNOSIS_SECTION_FALLBACKS.get(str(section_key or "").strip()) or ()
    return [item for item in fallback if item]


def role_header(*, family: str | None, question_axis: str | None) -> str:
    role = resolve_information_role(family=family, question_axis=question_axis)
    label = role_label(role)
    description = role_description(role)
    if not label:
        return ""
    return f"Role: {label} - {description}" if description else f"Role: {label}"


def package_question_axis(pkg: dict[str, Any]) -> str:
    direct = str(pkg.get("question_axis") or "").strip() if isinstance(pkg, dict) else ""
    if direct:
        return direct
    canonical = pkg.get("canonical_payload") if isinstance(pkg, dict) else {}
    canonical = canonical if isinstance(canonical, dict) else {}
    request_context = canonical.get("request_context") if isinstance(canonical.get("request_context"), dict) else {}
    return str(request_context.get("question_axis") or "").strip()


def package_information_role(pkg: dict[str, Any]) -> str:
    if not isinstance(pkg, dict):
        return ""
    family = pkg.get("family_classification")
    family = family if isinstance(family, dict) else {}
    if not family:
        authoritative = pkg.get("authoritative_payload") if isinstance(pkg.get("authoritative_payload"), dict) else {}
        family = authoritative.get("family_classification") if isinstance(authoritative.get("family_classification"), dict) else {}
    return resolve_information_role(
        family=str(family.get("family") or "").strip(),
        question_axis=package_question_axis(pkg),
    )


def role_payload(*, family: str | None, question_axis: str | None) -> dict[str, str]:
    role = resolve_information_role(family=family, question_axis=question_axis)
    return {
        "information_role": role,
        "role_label": role_label(role),
        "role_description": role_description(role),
        "role_header": role_header(family=family, question_axis=question_axis),
    }
