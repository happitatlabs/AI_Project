# Rebuild Assistant Polish UI Rendering Contract

기준일: 2026-03-30  
상태: Contract  
대상: `mellow_link` / `rebuild_assistant` 결과 화면

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 이 문서는 결과 UI가 `structured_result`와 `polish_bundle`를 어떻게 렌더링하는지만 다룬다.
- 엔진 내부 판단과 score 계산 규칙은 이 문서가 아니라 엔진 기준 문서를 따른다.

## 1. 목표

현재 안정화된 `structured_result`와 `polish_bundle` 위에, 결과 UI에서 audience / delivery mode별 표현 변형본을 선택해서 볼 수 있는 렌더링 계층을 추가한다.

이번 범위는 회계 확장 섹션을 우선 대상으로 한다.

## 2. 범위

- `/projects/{project_id}/result?format=json`
- `project_result.html`
- `polish_bundle` 전달 및 렌더링
- audience / delivery mode 선택 UI
- 회계 섹션의 원문 / 보정문 / audience variant / delivery variant 표시

## 3. 고정 원칙

### 3.1 판단 불변

아래 항목은 UI 렌더링에서 변경하지 않는다.

- `structured_result`
- `structured_result.extensions.accounting`
- `primary_judgment`
- 계산 숫자
- 코드명 / 상태값 / 역할명 / 계정코드 / 환율

### 3.2 표현만 전환

UI는 `polish_bundle`의 표현 variant만 선택해서 보여준다.

- audience
  - `developer`
  - `manager`
  - `client`
- delivery mode
  - `internal_review`
  - `client_report`
  - `proposal_appendix`

## 4. 필수 동작

1. 결과 JSON에 `polish_bundle` 포함
2. 결과 화면에 audience selector 표시
3. 결과 화면에 delivery mode selector 표시
4. 회계 섹션은 아래 3개 보기 지원
   - 원문
   - audience variant
   - delivery variant
5. 기본값은 기존 runner 기준
   - audience=`manager`
   - delivery_mode=`client_report`

## 5. 표시 대상

회계 확장 섹션:

- `summary_sentence`
- `calculation_status`
- `accounting_analysis`
- `fx_calculation`
- `voucher_review`

## 6. 금지 사항

- UI에서 판단값 재계산 금지
- UI에서 숫자/근거 일반화 금지
- 회계 외 기존 섹션 구조 변경 금지
- `polish_bundle`가 없다고 기존 결과 렌더를 깨뜨리는 변경 금지

## 7. 완료 조건

1. 결과 JSON에 `polish_bundle`가 포함된다.
2. 결과 화면에서 audience / delivery mode를 바꿀 수 있다.
3. 회계 섹션이 선택값에 따라 variant를 바꿔 보여준다.
4. `polish_bundle`가 없을 때도 기존 결과 화면은 그대로 동작한다.
5. 관련 회귀 테스트가 통과한다.
