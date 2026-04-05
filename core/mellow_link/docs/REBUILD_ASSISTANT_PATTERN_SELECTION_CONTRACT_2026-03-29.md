# Rebuild Assistant Pattern Selection Contract

기준일: 2026-03-29  
상태: Contract  
대상: `rebuild_assistant` 판단 템플릿 후보 수집 / 최종 선택 / 디버깅 경로

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 판단 템플릿 canonical source는
  [`mellow_link/services/refactoring_support_engine/decision_catalog.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)다.
- [`mellow_link/modules/rebuild_assistant/judgment_templates.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 유지한다.
- 이 문서는 패턴 선택 계약과 디버깅 기준을 설명하는 보조 문서다.

## 1. 목적

`rebuild_assistant`의 판단 템플릿 선택을 단순 점수 최대값이 아니라 후보 수집 + 조건 기반 선택 구조로 고정한다.

핵심 목표는 아래와 같다.

- 각 패턴이 왜 후보가 되었는지 남긴다.
- 최종 `primary_judgment`를 한 번만 결정한다.
- detection 결과와 최종 `structured_result`가 어긋나지 않게 한다.
- 이후 패턴이 추가되어도 같은 선택 구조 위에서 확장한다.

## 2. 후보 패턴

현재 관리 대상 패턴은 아래 7종이다.

- `workflow`
- `state_transition`
- `access_control`
- `validation`
- `query_filter`
- `amount_threshold`
- fallback: `validation`

## 3. 최소 성립 조건

### 3.1 workflow

- 승인 주체 신호
- 단계 구조 신호
- 의사결정 게이트 신호

위 3개 중 2개 이상 + 진행성 신호 1개 이상일 때만 성립한다.

진행성 신호 예:

- `requested`, `submitted`
- `approvalStep`, `approvalLevel`, `nextStep`
- `delegate`, `pending_delegate_assignment`
- `reject`, `hold`

### 3.2 state_transition

- 명시적 상태 변경 신호가 존재해야 한다.

예:

- `setStatus(...)`
- `SET status = ...`
- `status IN (...)`

### 3.3 access_control

- 역할 / 부서 / 승인 주체 신호가 핵심이어야 한다.
- 단순 상태 변경만으로는 성립하지 않는다.

### 3.4 validation

- 중복 방지
- 저장 전 차단
- 선행 조건
- 예외 처리

위 신호가 검증 축으로 우세할 때 성립한다.

### 3.5 query_filter

- 조회 조건
- 필터 조합
- 정렬
- 페이징

위 축이 핵심일 때 성립한다.

### 3.6 amount_threshold

- 금액 구간
- 한도 기준
- 승인 필요 경계
- 고액 처리 경계

위 축이 핵심일 때 성립한다.

## 4. 주요 충돌 규칙

### 4.1 workflow vs access_control

- 승인 흐름의 단계성과 의사결정 게이트가 있으면 `workflow`
- 권한 설명만 있고 단계성이 약하면 `access_control`

### 4.2 workflow vs amount_threshold

- 금액이 승인 시작 조건이더라도 승인 단계 / 게이트가 있으면 `workflow`
- 금액 구간과 한도 정책만 있으면 `amount_threshold`

### 4.3 amount_threshold vs query_filter

- 금액이 조회 필터일 뿐이면 `query_filter`
- 금액 구간 정책 / 승인 경계로 쓰이면 `amount_threshold`

### 4.4 state_transition vs access_control

- 핵심이 상태 이동이면 `state_transition`
- 핵심이 처리 권한과 승인 주체면 `access_control`

### 4.5 validation vs query_filter

- `primary_feature_mode = save_validation`이면 `validation`
- 조회 SQL이 같이 있어도 저장 검증, 중복 체크, 선행 차단이 주축이면 `query_filter`로 올리지 않는다
- `query_filter`는 `primary_feature_mode = search_filters` 또는 보조 조회 신호가 충분할 때만 성립한다

## 5. fallback 원칙

- 어느 패턴도 강하지 않으면 `validation`
- 단, `validation`은 너무 이르게 선택하지 않는다.
- `workflow`가 성립하면 `access_control` fallback 금지
- `save_validation`이 주축이면 `query_filter` fallback 금지

## 6. 불변성 원칙

- `primary_judgment`는 한 번만 결정한다.
- 이후 `runner`나 `result_package` 단계에서 재선택하지 않는다.
- 선택된 값은 `PreparedRebuildInput.selected_primary_judgment`에 고정하고 downstream이 재사용한다.
- `run_finished.payload_json`에는 아래를 함께 남긴다.
  - `primary_judgment`
  - `judgment_template_key`
  - `structured_result.primary_judgment`

## 7. 디버깅 방법

확인 순서:

1. 후보 패턴 목록
2. 각 패턴의 reasons
3. 최종 선택 이유
4. 탈락한 후보의 `rejected_reason`
5. `run_finished.payload_json.primary_judgment`
6. `run_finished.payload_json.structured_result`
7. `run_finished` 직전 `primary judgment selected` 로그

확인 기준:

- detection 결과와 최종 `structured_result`의 템플릿 성격이 같아야 한다.
- 어긋나면 `prepare_safe_bundle_input` 또는 후보 선택 로직을 먼저 본다.

## 8. 이번 수정에서 확인된 실제 원인

2026-03-29 workflow 서버 검증에서 아래가 확인됐다.

- raw 입력: `workflow`
- safe bundle 입력: 익명화 이후 `approverRole`, `approvalStep` 신호 약화
- 결과: `/projects` 실제 실행 경로에서 `access_control`형 결과 저장

따라서 runner 덮어쓰기보다 safe bundle 기준 workflow 신호 손실이 실제 원인이었다.
