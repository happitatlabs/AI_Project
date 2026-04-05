# Rebuild Assistant Refinement Output Contract

기준일: 2026-03-30

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 이 문서는 결과 패키지 refinement와 narrative 정렬 규칙을 다루는 보조 문서다.
- 엔진 내부 detector, scoring, decision schema는 이 문서가 아니라 엔진 기준 문서를 따른다.

## 목적

`structured_result`의 판단 구조는 유지하면서, 결과 패키지의 문서 축 일관성과 완성도를 제품 수준으로 끌어올리기 위한 refinement 계약이다.

핵심 범위는 아래 4개다.

1. `report_purpose`와 실제 문서 축 일치
2. 한 문서 내 패턴 충돌 제거
3. 회계 문서 하단 섹션의 회계 전용 분리
4. 공통 문장 조합 오류 보정

## 핵심 원칙

- `primary_judgment`는 바꾸지 않는다.
- 계산 엔진과 accounting 확장 사실관계는 바꾸지 않는다.
- 문서 축은 사용자가 실제로 읽는 narrative 기준으로 일관되게 유지한다.
- 회계 문서는 상단뿐 아니라 하단 섹션도 회계 보고서 톤으로 닫혀야 한다.
- 공통 문장 보정은 의미 삭제가 아니라 조사/서술 조합 오류 수정으로 제한한다.

## 1. report_purpose 생성 규칙

- 회계 확장이 있으면 회계 목적을 우선 사용한다.
- 회계 확장이 없으면 `primary_judgment` 단독이 아니라 실제 narrative 축을 따르는 `narrative_judgment`를 기준으로 목적을 생성한다.
- 따라서 문서 본문이 `access_control` 축으로 읽히는데 `validation` 목적이 붙는 것을 허용하지 않는다.

## 2. 단일 패턴 narrative 유지

- `primary_judgment`가 결정된 뒤 사용자 노출용 narrative 축은 `selected_narrative_judgment`로 한 번 더 고정한다.
- 상단 결론, 핵심 규칙, 유지 계약, 추천안, 실행 계획은 이 축을 공유해야 한다.
- 금지:
  - `query_filter` 상단 + `workflow` 본문 혼합
  - `access_control` 상단 + `validation` 계약 혼합

## 3. 회계 문서 하단 섹션 규칙

회계 확장이 있으면 아래 섹션은 일반 현대화 템플릿을 재사용하지 않는다.

- `grounded_business_rules`
- `core_business_rules`
- `retained_contracts`
- `recomposition_draft`
- `recommended_directions`

회계 하단 섹션은 아래 축으로 닫는다.

- 계산 방식
- 환율 적용 기준
- 전표 정합성
- 입력 책임 또는 재실행 조건

금지 문구:

- `모듈형 구조`
- `API 분리`
- `계층 분리`
- `화면 재구성`

## 4. 공통 문장 조합 규칙

결과 패키지와 렌더에 아래 조합 오류를 남기지 않는다.

- `누락로` -> `누락으로`
- `금지을` -> `금지를`
- `규칙야 합니다` -> `규칙이어야 합니다`
- `이동평균법로` -> `이동평균법으로`
- `입니다. 입니다.` -> `입니다.`

문장 사유를 결합할 때는 full sentence를 그대로 이어 붙이지 않고 라벨형 표현으로 분리한다.

예:

- `환율 데이터가 누락되었습니다. 항목을 우선 보완` 금지
- `환율 데이터 누락 항목을 우선 보완` 허용

## 5. 검증 기준

- `report_purpose`가 실제 문서 축과 어긋나지 않는다.
- 단일 문서 안에서 상단/본문 패턴 축이 섞이지 않는다.
- 회계 문서 하단 섹션에 일반 현대화 문구가 남지 않는다.
- 공통 조사/서술 조합 오류가 재발하지 않는다.

## 6. 회귀 포인트

- `python_claim_adjustment_case_01`
  - purpose는 `access_control` 축이어야 한다.
- `amount_limit`
  - purpose는 `amount_threshold` 축이어야 한다.
- `rca_exception_case_01`
  - 단일 `workflow` narrative를 유지해야 한다.
- `01_success_full`
  - 회계 하단 섹션이 회계 전용이어야 한다.
