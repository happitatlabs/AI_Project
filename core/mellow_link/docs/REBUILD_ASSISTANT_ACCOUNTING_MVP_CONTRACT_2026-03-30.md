# Rebuild Assistant Accounting MVP Contract

기준일: 2026-03-30  
상태: Contract  
대상: `mellow_link` / `rebuild_assistant`

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 이 문서는 `structured_result.extensions.accounting` 확장 계약을 설명하는 보조 문서다.
- 구조 분석, 진단, 의사결정, 개선안 생성의 canonical rule은 엔진 기준 문서를 따른다.

## 1. 목표

기존 `rebuild_assistant`의 판단 엔진과 `structured_result` 본체를 유지한 상태에서, 전산회계 MVP 기능을 확장 필드로 추가한다.

이번 MVP의 목적은 아래를 하나의 실행 흐름으로 연결하는 것이다.

- 분석
- 회계 규칙 식별
- 실제 계산
- 결과 리포트

즉, `설명형 분석 도구`가 아니라 `회계 판단 + 계산 보조 도구`로 확장한다.

## 2. 범위

이번 작업 범위는 아래 3개 기능으로 제한한다.

1. `accounting_analysis`
2. `fx_calculation`
3. `voucher_review`

## 3. 고정 원칙

### 3.1 판단 불변

아래 항목은 회계 확장에서 변경하지 않는다.

- `primary_judgment`
- `grounded_business_rules`
- `retained_contracts`
- `recommended_option`
- `execution_plan`

즉, 회계 확장은 `structured_result` 위에 병렬 확장으로만 추가한다.

### 3.2 입력 신뢰성 우선

계산 정확도보다 입력 신뢰성이 더 중요하다.

필수 입력:

- `transactions`
- `exchange_rates`
- `policies`

위 항목이 없으면 계산을 중단하고 명시적 실패를 반환한다.  
그럴듯한 추정 계산은 금지한다.

### 3.3 strict 모드

- 기본값: `strict=True`
- `strict=True`
  - 하나라도 불명확하면 해당 계산/검토 단계 실패
- `strict=False`
  - warning을 남기고 가능한 범위만 계속 진행

단, 필수 입력 누락은 `strict=False`여도 실패다.

### 3.4 source tagging

계산/검토 결과는 반드시 source tagging을 가진다.

최소 태그:

- `policy`
- `transaction`
- `inferred`

확장 태그:

- `exchange_rate`
- `account_mapping`
- `voucher`

## 4. 출력 구조

기존 `structured_result`는 유지하고, 새 확장 필드 하나만 추가한다.

- `extensions.accounting.input_validation`
- `extensions.accounting.calculation_status`
- `extensions.accounting.accounting_analysis`
- `extensions.accounting.fx_calculation`
- `extensions.accounting.voucher_review`
- `extensions.accounting.summary_sentence`

### 4.1 calculation_status

계산 가능 여부를 즉시 판단할 수 있어야 한다.

성공 예:

```json
{
  "can_calculate": true,
  "reason": "all required inputs present"
}
```

실패 예:

```json
{
  "can_calculate": false,
  "blocking_issue": "missing exchange_rates"
}
```

### 4.2 summary_sentence

성공 시:

- 숫자 포함 결론 문장
- 예: `이 시스템은 이동평균법을 사용하며, 현재 기준 환차익은 22,500원입니다.`

실패 시:

- 실패형 문장을 반드시 생성
- 예: `회계 계산을 수행할 수 없습니다. 환율 데이터가 누락되었습니다.`

## 5. 계산 방식

지원 정책:

- `MOVING_AVERAGE`
- `FIFO`
- `SPECIFIC_ID`

필수 acceptance:

- moving average 결과 `22500`
- FIFO 결과 `25000`

`SPECIFIC_ID`는 lot/source 지정이 없으면 실패한다.

## 6. 실행 표면

- 새 모듈 추가 금지
- 기존 `/projects/create` 사용
- 업로드 자산은 기존 레거시 파일 + `accounting_payload.json`

## 7. 테스트 기준

필수 테스트:

- 입력 누락 실패
- strict mode 분기
- moving average 계산
- FIFO 계산
- SPECIFIC_ID 실패
- voucher review 불일치
- `calculation_status` 생성
- 실패형 `summary_sentence`
- result package / polish bundle 회계 섹션 반영

## 8. 금지 사항

- 기존 판단 엔진 수정
- 추정 계산
- 자동 분개 생성
- 자동 수정 제안
- 회계 확장에서 기존 `structured_result` 원문 덮어쓰기

## 9. 완료 조건

아래 조건을 모두 만족하면 완료로 본다.

1. `/projects/create` 경로에서 회계 JSON이 인식된다.
2. `structured_result.extensions.accounting`가 생성된다.
3. 필수 입력 누락 시 계산이 중단되고 명시적 실패가 반환된다.
4. 성공 시 숫자 계산 결과가 실제로 출력된다.
5. `summary_sentence`가 성공/실패 상태와 항상 일치한다.
6. result package와 polish bundle에 회계 섹션이 반영된다.
7. 회귀 테스트가 통과한다.
