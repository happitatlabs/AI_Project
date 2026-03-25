from __future__ import annotations


# Result package scope_notice single source of truth.
# Static UI copies such as projects_create.html must stay text-identical to this
# constant and be updated together when wording changes.
PROJECT_SCOPE_NOTICE = {
    "version_label": "단일 기능 / 단일 화면 V0",
    "summary": "이 결과는 단일 기능·단일 화면·단일 업무 흐름 기준의 현대화 분석 초안입니다.",
    "supported": [
        "단일 기능 / 단일 화면 / 단일 업무 흐름 기준 분석",
        "레거시 구조 진단과 기능 분류",
        "업무 규칙 추출",
        "현대화 설계안 및 전환 초안 제시",
        "설명 가능한 결과 패키지 제공",
    ],
    "not_supported": [
        "전체 시스템 자동 전환",
        "자동 코드 치환",
        "운영 배포 및 실행 보장",
        "대규모 리팩터링 일괄 수행",
        "멀티서비스/전사 아키텍처 자동 생성",
    ],
}
