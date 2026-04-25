# Operational Source Golden Sample Plan

운영 소스형 golden sample 확장 후보를 아래 4개 축으로 정리한다.

## 목표

- 운영 소스 입력에서 `analysis-first governance`가 FX/FIFO 외 도메인에도 유지되는지 고정한다.
- 내부 taxonomy가 `refactor`여도 외부 표면은 `현행 분석 우선` 또는 `운영 로직 검토 우선`으로 노출되는지 검증한다.
- 결과 첫 문단과 section heading이 실제 객체명과 처리 흐름 중심으로 유지되는지 확인한다.

## 승격 기준

- 입력 자산의 다수가 SQL, DDL, DML, trigger, procedure, batch source다.
- 사용자 goal에 `재설계`, `전환`, `서비스 분리`, `마이그레이션`이 명시되지 않는다.
- 실제 객체명과 현행 처리 흐름을 복원할 수 있다.
- 결과 첫 문단이 자산 정체와 현행 흐름으로 시작한다.
- `display_strategy`가 운영 소스형 analysis-first wording으로 분리된다.
- 개선 제안은 `recommended_option` 또는 follow-up 성격 섹션에만 남는다.

## 후보 1. Approval Operational Source

- 목적: 승인 단계, 승인 이력, 보류/반려, 재상신 흐름이 운영 소스 기반으로 먼저 복원되는지 검증
- seed:
  - `02_access_control_workflow`
  - `03_state_transition_complex`
- 필요한 runnable 자산:
  - `TN_APPRHDR`, `TN_APPRDTL`, `TN_APPRHIS`, `TN_APPRIF`
  - 승인 단계 trigger
  - 반려/재상신 procedure
  - 승인 이력 적재 SQL
- 기대 surface wording:
  - `운영 로직 검토 우선`
- golden focus:
  - 승인 개시 조건
  - 단계 전이 순서
  - 보류/반려/재상신 정합성
  - 승인 이력/인터페이스 누락 리스크

## 후보 2. Settlement And Journal Operational Source

- 목적: 정산 헤더/상세, 분개, GL 적재, 취소/역분개 흐름을 현행 분석 우선으로 복원하는지 검증
- seed:
  - `01_success_full`
  - `09_fx_fifo_operational_source`
- 필요한 runnable 자산:
  - `TN_STLHDR`, `TN_STLDTL`, `TN_JE_HDR`, `TN_JE_LINE`, `GL_INTERFACE`
  - 정산 완료 trigger
  - 분개 생성 procedure
  - 취소/역분개 procedure
- 기대 surface wording:
  - `현행 분석 우선`
- golden focus:
  - 정산 완료 조건
  - 전표 생성 체인
  - GL 인터페이스 적재
  - 취소/역분개 정합성

## 후보 3. State-History Operational Source

- 목적: 상태 테이블, 이력 테이블, 이벤트 적재와 재처리 흐름이 redesign 없이 현행 로직 분석으로 시작하는지 검증
- seed:
  - `03_state_transition_complex`
  - `01. java_order_closure_case_01`
- 필요한 runnable 자산:
  - `TN_STATUS_HDR`, `TN_STATUS_HIS`, `TN_EVENT_OUTBOX`, `TN_EVENT_RETRY`
  - 상태 변경 trigger
  - 이벤트 적재/재처리 procedure
- 기대 surface wording:
  - `운영 로직 검토 우선`
- golden focus:
  - 상태 전이 조건
  - 이력 적재
  - 재처리 순서
  - reopen/cancel/retry 리스크

## 후보 4. Interface-Linkage Operational Source

- 목적: interface staging, ack, retry, failure history가 current-state 분석 우선으로 복원되는지 검증
- seed:
  - 신규 샘플 필요
- 필요한 runnable 자산:
  - `TN_IF_STG`, `TN_IF_ACK`, `TN_IF_RETRY`, `TN_IF_FAIL`
  - 인터페이스 송신 trigger
  - ack 반영 procedure
  - retry scheduler source
- 기대 surface wording:
  - `운영 로직 검토 우선`
- golden focus:
  - staging -> ack -> retry chain
  - 실패 이력 누락
  - 중복 전송/중복 반영 리스크

## 추가 순서

1. Approval operational source
2. Settlement and journal operational source
3. State-history operational source
4. Interface-linkage operational source

## 회귀 체크리스트

- `recommended_strategy`는 internal taxonomy로 유지된다.
- `display_strategy`는 analysis-first wording으로 분리된다.
- external summary card title이 `분석 성격`, `우선 검토 기준`, `검토 순서` 계열로 나온다.
- markdown/export heading이 `분석 목적`, `자산 정체`, `운영 리스크` 계열로 나온다.
- 실제 객체명과 처리 흐름이 첫 문단에 포함된다.
