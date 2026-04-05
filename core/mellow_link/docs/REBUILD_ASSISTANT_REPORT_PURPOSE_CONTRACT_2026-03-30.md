# Rebuild Assistant Report Purpose Contract

기준일: 2026-03-30  
상태: Contract  
대상: `mellow_link` / `rebuild_assistant`

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 이 문서는 `report_purpose`, `report_scope`, `report_questions`의 렌더/설명 계약을 다룬다.
- 의사결정 자체의 canonical source는 `decision_summary`이며, 목적 문장은 structured block에서 파생된 결과를 설명하는 용도로만 사용한다.

## 1. 목표

`structured_result`에 보고서 목적을 명시적으로 부여해, 문서를 여는 즉시 이 결과가 무엇을 위한 보고서인지 이해할 수 있게 한다.

이번 계약의 핵심은 아래와 같다.

- 목적은 문서의 의도를 설명한다.
- 결론은 실행 결과를 설명한다.
- 질문 원문은 보고서 상단에 그대로 노출하지 않는다.

## 2. 출력 필드

`StructuredRebuildResult`는 아래 필드를 추가로 가진다.

- `report_purpose`
- `report_scope`
- `report_questions`

기존 필드 의미는 변경하지 않는다.

## 3. 목적 생성 원칙

### 3.1 회계 목적 우선

`extensions.accounting`가 존재하면 일반 현대화 목적보다 회계 목적을 우선 생성한다.

우선순위는 아래 순서를 따른다.

1. `fx_calculation + voucher_review`
2. `fx_calculation`
3. `voucher_review`
4. `accounting_analysis`
5. generic accounting fallback

### 3.2 일반 fallback

회계 확장이 없으면 `primary_judgment` 기준으로 목적을 생성한다.

- `query_filter`
- `amount_threshold`
- `workflow`
- `access_control`
- `state_transition`
- `validation`

## 4. 질문 원문 비노출 원칙

사용자 질문은 목적 문장 생성의 참고 입력으로만 사용한다.

- raw question 문장 그대로 상단 출력 금지
- 목적은 보고서용 서술형 문장으로 재작성
- `report_questions`도 보고서용 질문 형태로 정리

## 5. 목적 / 결론 분리 원칙

아래 두 필드는 같은 역할을 하면 안 된다.

- `report_purpose`
  - 왜 이 문서를 만들었는가
- `summary_sentence`
  - 이번 실행 결과가 무엇인가

계산 실패 시에도 목적은 유지한다.

예:

- `report_purpose`
  - `외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 계산 근거를 검증하기 위한 보고서입니다.`
- `summary_sentence`
  - `회계 계산을 수행할 수 없습니다. 환율 데이터가 누락되었습니다.`

## 6. 결과 패키지 렌더 원칙

결과 패키지와 렌더는 아래 구조를 상단에 공통으로 사용한다.

1. `보고서 목적`
2. `핵심 결론`
3. `분석 범위`
4. `검증 질문`

HTML / Markdown / JSON은 같은 목적 문장을 공유해야 한다.

## 7. 금지 사항

- 사용자 질문 raw text를 문서 맨 위에 그대로 출력
- 회계 확장이 있는데 일반 현대화 목적만 출력
- `report_purpose`와 `summary_sentence`를 같은 문장으로 처리
- 목적 필드를 렌더 단계에서만 임시 생성하고 `structured_result`에는 넣지 않는 방식
