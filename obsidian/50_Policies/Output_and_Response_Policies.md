---
title: Output and Response Policies
tags:
  - policy
  - output
  - response
created: 2026-04-06
status: current
---

# Output and Response Policies

## 원문 기준

- `core/mellow_link/docs/OUTPUT_POLICY.md`
- `core/mellow_link/docs/LONG_FORM_OUTPUT_POLICY.md`
- `core/mellow_link/docs/PROGRESSIVE_OUTPUT_POLICY.md`
- `core/mellow_link/docs/TOOL_OUTPUT_LIMITS.md`

## 출력 정제 기본

Output sanitizer는 다음을 보장한다.

- tool-call JSON 누출 방지
- 한국어만 출력 가드
- 허가 없는 페르소나 전환 차단
- plan intent 감지

## 장문 응답 정책

- 기본은 summary-first
- THINKING/RESEARCH 계열에서 장문 질문을 요약 우선으로 제한
- 사용자가 `확장`, `확장2`, `확장3`을 요청할 때만 단계적으로 상세화

## progressive disclosure

- Layer 1: 요약 우선
- Layer 2: 확장 레벨별 상세 응답
- Layer 3: `thinking-lite`
  - 짧은 분석용 경량 모드
  - 도구 호출도 제한적으로 허용

## 도구 출력 상한

로컬 도구 결과는 p95 지연을 낮추기 위해 상한을 둔다.

- 디렉터리 목록
- 최근 파일/제안 요약
- 프로세스 목록 등

잘린 경우 `[TRUNCATED]` 푸터와 메타 정보를 같이 붙인다.

## 현재 해석

이 정책군은 제품 분석 로직 자체보다는 `agent_brain`, 출력 품질, UX 응답 시간 제어에 가깝다.  
즉 제품 본체의 판단 계약이라기보다, 응답 계층 운영 정책으로 보는 편이 맞다.

## 같이 볼 노트

- [[Document_Driven_Execution_Policy]]
- [[AI_Augmentation_Policy]]
