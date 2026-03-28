from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


JudgmentTemplateId = Literal["state_transition", "access_control", "validation"]


@dataclass(frozen=True)
class JudgmentTemplateSpec:
    template_id: JudgmentTemplateId
    label: str
    signal_types: tuple[str, ...]
    core_questions: tuple[str, ...]
    retained_contract_candidates: tuple[str, ...]
    decision_patterns: tuple[str, ...]
    risk_patterns: tuple[str, ...]
    priority_split_defaults: tuple[dict[str, str], ...]
    execution_plan_defaults: tuple[dict[str, object], ...]


JUDGMENT_TEMPLATE_REGISTRY: dict[JudgmentTemplateId, JudgmentTemplateSpec] = {
    "state_transition": JudgmentTemplateSpec(
        template_id="state_transition",
        label="상태 전이형",
        signal_types=("status", "transition", "processable_state", "blocked_state"),
        core_questions=(
            "어떤 상태에서 어떤 전이가 허용되는지 확인해야 합니다.",
            "처리 가능 상태와 차단 상태를 어디서 통제해야 하는지 정리해야 합니다.",
        ),
        retained_contract_candidates=("status_codes", "status_column", "transition_condition"),
        decision_patterns=(
            "상태 전이 규칙을 별도 정책 계층으로 분리하는 것이 필요합니다.",
            "처리 가능 상태를 API 진입 전 검증으로 고정하는 것이 필요합니다.",
        ),
        risk_patterns=(
            "상태 전이 규칙이 분산되면 예외 전이 누락이 발생할 수 있습니다.",
            "처리 가능 상태 계약이 흔들리면 후속 승인과 화면 표시가 불일치할 수 있습니다.",
        ),
        priority_split_defaults=(
            {
                "title": "상태 전이 정책 분리",
                "item": "핵심 상태 전이 규칙을 먼저 분리하는 것이 필요합니다.",
                "reason": "직접 확인된 상태 전이 규칙이 기능 흐름을 좌우합니다.",
                "impact_scope": "처리 가능 상태, 예외 전이, 후속 승인 흐름",
                "prerequisite": "상태 코드와 상태 컬럼 계약 확정",
            },
            {
                "title": "상태 기반 검증 분리",
                "item": "처리 가능 상태 검증을 정책 다음 단계로 분리하는 것이 필요합니다.",
                "reason": "차단 조건을 명시적으로 분리해야 회귀 범위를 줄일 수 있습니다.",
                "impact_scope": "API 진입 검증, 상태 기반 차단, 오류 메시지 처리",
                "prerequisite": "상태 전이 정책 인터페이스 정의",
            },
        ),
        execution_plan_defaults=(
            {
                "week_label": "1주차",
                "goal": "핵심 상태 전이 규칙과 처리 가능 상태를 구조화합니다.",
                "deliverables": ("상태 전이 표", "처리 가능 상태 목록"),
            },
            {
                "week_label": "2주차",
                "goal": "상태 전이 정책과 상태 기반 검증 구조를 설계합니다.",
                "deliverables": ("상태 전이 API 명세", "상태 기반 검증 흐름도"),
            },
        ),
    ),
    "access_control": JudgmentTemplateSpec(
        template_id="access_control",
        label="권한 제어형",
        signal_types=("role", "department", "approval_authority", "exception_owner"),
        core_questions=(
            "누가 어떤 조건에서 처리 가능한지 정리해야 합니다.",
            "예외 승인 주체와 일반 처리 주체를 어디서 나눌지 결정해야 합니다.",
        ),
        retained_contract_candidates=("role_codes", "department_codes", "approval_conditions"),
        decision_patterns=(
            "권한과 승인 규칙을 별도 정책 서비스로 분리하는 것이 필요합니다.",
            "예외 승인 경로를 일반 처리 흐름과 분리하는 것이 필요합니다.",
        ),
        risk_patterns=(
            "권한 규칙이 화면과 서비스에 분산되면 예외 승인 누락이 발생할 수 있습니다.",
            "부서 또는 조직 코드 계약이 바뀌면 승인 경로가 달라질 수 있습니다.",
        ),
        priority_split_defaults=(
            {
                "title": "권한 정책 분리",
                "item": "권한과 승인 주체 규칙을 먼저 분리하는 것이 필요합니다.",
                "reason": "직접 확인된 권한 규칙이 처리 가능 범위를 결정합니다.",
                "impact_scope": "승인 경로, 조직별 처리 권한, 액션 노출",
                "prerequisite": "역할 또는 부서 코드 계약 확정",
            },
            {
                "title": "승인 경로 정리",
                "item": "예외 승인 경로를 일반 처리 흐름과 분리하는 것이 필요합니다.",
                "reason": "예외 승인 규칙을 별도 경로로 고정해야 누락을 줄일 수 있습니다.",
                "impact_scope": "예외 승인, 본사 승인, 심사 전담 경로",
                "prerequisite": "권한 정책 경계 정의",
            },
        ),
        execution_plan_defaults=(
            {
                "week_label": "1주차",
                "goal": "권한 주체, 부서, 예외 승인 규칙을 구조화합니다.",
                "deliverables": ("권한 규칙 목록", "승인 주체 매트릭스"),
            },
            {
                "week_label": "2주차",
                "goal": "권한 정책과 예외 승인 경계를 설계합니다.",
                "deliverables": ("권한 정책 설계안", "승인 경로 흐름도"),
            },
        ),
    ),
    "validation": JudgmentTemplateSpec(
        template_id="validation",
        label="검증형",
        signal_types=("threshold", "blocking_condition", "precondition", "save_guard"),
        core_questions=(
            "무엇이 차단 조건인지와 허용 조건인지 정리해야 합니다.",
            "정책 검증과 저장 전 검증을 어디서 나눌지 결정해야 합니다.",
        ),
        retained_contract_candidates=("threshold_rules", "required_columns", "blocking_flags"),
        decision_patterns=(
            "핵심 검증 규칙을 저장 흐름과 분리하는 것이 필요합니다.",
            "선행 차단 조건을 API 진입 전 검증으로 고정하는 것이 필요합니다.",
        ),
        risk_patterns=(
            "금액 한도나 선행 차단 규칙이 저장 흐름에 섞이면 예외 누락이 발생할 수 있습니다.",
            "검증 순서가 달라지면 기존 차단 조건과 화면 메시지가 어긋날 수 있습니다.",
        ),
        priority_split_defaults=(
            {
                "title": "핵심 검증 분리",
                "item": "핵심 검증 규칙을 우선 분리하는 것이 필요합니다.",
                "reason": "직접 확인된 차단 조건과 한도 규칙이 처리 가능 범위를 좌우합니다.",
                "impact_scope": "저장 전 검증, 금액 한도, 선행 차단",
                "prerequisite": "검증 기준 컬럼과 플래그 계약 확정",
            },
            {
                "title": "검증 순서 정리",
                "item": "저장 전 검증 순서를 명시적으로 재정렬하는 것이 필요합니다.",
                "reason": "검증 순서를 고정해야 차단 메시지와 승인 흐름 충돌을 줄일 수 있습니다.",
                "impact_scope": "API 검증 계층, 저장 전 차단, 예외 메시지 처리",
                "prerequisite": "핵심 검증 규칙 목록 정리",
            },
        ),
        execution_plan_defaults=(
            {
                "week_label": "1주차",
                "goal": "금액 한도, 선행 차단, 상태 제한 검증 규칙을 구조화합니다.",
                "deliverables": ("검증 규칙 목록", "차단 조건 표"),
            },
            {
                "week_label": "2주차",
                "goal": "검증 계층과 저장 전 검증 순서를 설계합니다.",
                "deliverables": ("검증 흐름도", "저장 전 검증 설계안"),
            },
        ),
    ),
}


def get_judgment_template_spec(template_id: JudgmentTemplateId) -> JudgmentTemplateSpec:
    return JUDGMENT_TEMPLATE_REGISTRY[template_id]


def get_judgment_template_specs() -> tuple[JudgmentTemplateSpec, ...]:
    return tuple(JUDGMENT_TEMPLATE_REGISTRY.values())
