---
title: Rebuild Assistant Report and Refinement Contract
tags:
  - contract
  - rebuild-assistant
  - report
  - refinement
created: 2026-04-06
status: current
---

# Rebuild Assistant Report and Refinement Contract

## 원문 기준

- `core/mellow_link/docs/REBUILD_ASSISTANT_REPORT_PURPOSE_CONTRACT_2026-03-30.md`
- `core/mellow_link/docs/REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md`

## 핵심 목적

결과 패키지에서 `왜 이 문서가 만들어졌는지`와 `이번 실행 결과가 무엇인지`를 분리하고, 한 문서 안에서 narrative 축이 흔들리지 않게 만드는 계약이다.

## 주요 필드

- `report_purpose`
- `report_scope`
- `report_questions`

## 목적/결론 분리

- `report_purpose`
  - 문서의 의도
- `summary_sentence`
  - 실행 결과

둘은 같은 문장이 되면 안 된다.

## report 목적 생성 규칙

- 회계 확장이 있으면 회계 목적 우선
- 없으면 judgment/narrative 축 기준으로 목적 생성
- 사용자 질문 원문은 그대로 상단에 노출하지 않음

## refinement 규칙

- `primary_judgment`는 바꾸지 않음
- 사용자 노출용 narrative 축은 단일 축으로 유지
- 회계 문서는 하단 섹션도 회계 톤으로 닫혀야 함
- 공통 조사/문장 결합 오류는 보정

## 회귀 포인트

- `python_claim_adjustment_case_01`
- `amount_limit`
- `rca_exception_case_01`
- `01_success_full`

즉 purpose와 narrative 정렬이 실제 샘플에서 흔들리지 않아야 한다.

## 같이 볼 노트

- [[Rebuild_Assistant_Polish_and_Rendering_Contract]]
- [[Golden_Samples_and_Expansion]]
