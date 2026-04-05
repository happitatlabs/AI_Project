# Rebuild Assistant Result Status

기준일: 2026-03-30  
상태: 판단 템플릿 6종 + 표현 polish layer + 회계 MVP 확장 + 보고서 목적 자동 생성 + 회계 상단 narrative 분리 + legacy 회계 payload 호환 반영 완료, 기존 실샘플은 구조상 통과 단계, `/projects` 실제 실행 경로 회귀 통과

상태 해석 메모 (2026-04-03)

- 이 문서는 상태/샘플/회귀 기록 문서다.
- 현재 엔진 구조와 authoritative payload source of truth는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 현재 canonical judgment template registry는
  [`mellow_link/services/refactoring_support_engine/decision_catalog.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)다.
- [`mellow_link/modules/rebuild_assistant/judgment_templates.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 유지한다.
- 현재 `decision_summary.decisions[*]`에는 `score_breakdown`이 함께 포함되며, `priority_score`의 구성요소를 설명 가능하게 유지한다.

## 1. 현재 결론

`rebuild_assistant`는 현재 `레거시 분석 요약` 단계를 넘어 `컨설턴트 의사결정 지원 도구` 구조로 정리됐다.

이 문서는 `rebuild_assistant` 실행 결과를 반영하는 상태 문서이며, 관련 실행 또는 품질 판정 이후 반드시 갱신해야 한다.

현재 기준으로 아래 항목은 구조상 통과로 본다.

- 판단 템플릿 샘플
  - `state_transition`
  - `workflow`
  - `access_control`
  - `validation`
  - `query_filter`
  - `amount_threshold`
- 실샘플
  - `청구 조정`
  - `상태전환`
  - `접근제어`
  - `검증`

`주문 관리 화면 현대화` 실샘플은 구조상 거의 통과이며, 남은 차이는 보조 계약과 문장 정리 수준이다.

`workflow`는 2026-03-29 서버 재검증에서 `/projects` 실제 실행 경로의 새 run `run_20260329_210444_20efdfa0`가 access_control형 `structured_result`를 저장하는 문제가 있었으나, 원인이 runner 덮어쓰기가 아니라 `safe_bundle` 익명화 이후 승인 역할/단계 신호 약화임을 확인했다. 이후 safe bundle 기준 workflow 신호 보강을 적용했고, 재실행 run `run_20260329_211803_608231af`에서 아래를 확인했다.

- `primary_judgment = workflow`
- `one_line_conclusion = 승인 트리거와 승인 단계 구조를 기준으로 승인 흐름...`
- 상위 규칙
  - `의사결정 분기 조건`
  - `예외 처리 흐름`
  - `승인 단계 구조`
  - `승인 트리거 조건`
- `retained_contracts = 4`
- `recommended_option = 옵션 A. 승인 흐름 중심 모듈형 구조`

따라서 현재 기준으로 `workflow`는 코드/테스트/실제 `/projects` 실행 경로까지 모두 통과로 본다.

2026-03-29 기준으로 `structured_result` 위에 별도 `polish_bundle`을 생성하는 표현 전용 후처리 레이어도 추가했다. 이 레이어는 원문 `structured_result`를 덮어쓰지 않고 아래 3단계를 별도 번들로 제공한다.

- `sentence polish`
- `audience summary transform`
- `delivery tone rewrite`

관련 contract: [REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md)

2026-03-30 기준으로 `structured_result` 위에 `extensions.accounting` 확장을 추가했다. 이 확장은 기존 판단을 바꾸지 않고 아래를 병렬로 제공한다.

- `input_validation`
- `calculation_status`
- `accounting_analysis`
- `fx_calculation`
- `voucher_review`
- `summary_sentence`

관련 contract: [REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md)

같은 날 `structured_result` 상단에는 보고서 목적 필드를 추가했다.

- `report_purpose`
- `report_scope`
- `report_questions`

목적 생성은 회계 확장을 우선으로 하며, 회계 확장이 없으면 `primary_judgment` 기준 목적을 생성한다. 사용자 질문은 목적 생성의 참고 입력으로만 사용하고, 질문 원문을 문서 맨 위에 그대로 노출하지 않는다. 또한 `report_purpose`는 문서의 의도를 설명하고 `summary_sentence`는 실행 결과를 설명하도록 분리했다.

결과 패키지와 렌더 상단도 아래 순서로 고정했다.

1. `보고서 목적`
2. `핵심 결론`
3. `분석 범위`
4. `검증 질문`

관련 contract: [REBUILD_ASSISTANT_REPORT_PURPOSE_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_REPORT_PURPOSE_CONTRACT_2026-03-30.md)

같은 날 회계 확장이 있는 문서는 상단 narrative도 일반 현대화 템플릿에서 분리했다.

- 성공형
  - 계산 방식 / 계산 금액 / 전표 검토 상태 중심
- 실패형
  - 계산 불가 / 누락 입력 / 재실행 조건 중심
- 경고형
  - 계산 가능 / warning 존재 / 검토용 초안 중심

따라서 회계 문서의 `Executive Summary`, `핵심 판단`, `추천안`, `실행 계획`은 더 이상 `검증 규칙 중심 모듈형 구조`, `단계적 분리`, `화면 재구성` 같은 일반 현대화 서사를 사용하지 않는다. 회계 문서는 `입력 확인 -> 계산 검토 -> 전표 검토 -> 기준 확정` 흐름으로 읽히도록 고정했다.

관련 contract:

- [REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md)
- [REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md)

추가로 회계 샘플 `01_success_full`, `02_failure_missing_exchange_rates`, `03_warning_lenient_policy`에서 쓰던 구형 payload shape도 호환 처리했다.

- `vouchers`
  - legacy top-level `debit` / `credit` / `source_tx_ids` 입력 허용
- `account_mappings`
  - legacy `account` / `type` 입력 허용

이 보강으로 파일명은 success/warning인데 실제 결과는 schema failure로 떨어지던 문제가 해소됐다. 동시에 회계 실패/경고 사유를 상단 narrative에 끼워 넣을 때 `입니다. 입니다.`, `습니다.와` 같은 문장 깨짐이 생기지 않도록 failure/warning label을 분리했다.

같은 날 결과 패키지 UI도 보강했다. `/projects/{id}/result` HTML은 `polish_bundle`를 JSON으로 함께 받고, 회계 확장 섹션에 대해 아래 선택 렌더링을 지원한다.

- `audience`
  - `developer`
  - `manager`
  - `client`
- `delivery mode`
  - `internal_review`
  - `client_report`
  - `proposal_appendix`

원문 회계 결과와 선택된 표현 변형본은 병렬로 노출되며, `structured_result` 원문과 `extensions.accounting` 사실관계는 변경하지 않는다.

또한 `voucher_review`에서 `vouchers` 또는 `account_mappings`가 누락된 경우, 이를 단순 실패가 아니라 `input_missing` 상태로 구분하고 UI에서는 `차변/대변 균형`, `정책 일치`를 `검토 불가`로 표시하도록 보정했다. 이 경우 계산 엔진 오류가 아니라 입력 부족임을 바로 구분할 수 있다.

추가로 결과 페이지 HTML 템플릿의 회계 카드/라벨도 humanize 했다.

- `Accounting Extension` -> `회계 확장`
- `Audience` -> `열람 대상`
- `Delivery` -> `납품 톤`
- `Polish Warnings` -> `표현 보정 경고`
- 회계 표현 변형본 섹션 제목은 내부 `section_key` 대신 사용자 제목으로 매핑
  - `accounting_summary` -> `회계 계산 요약`
  - `accounting_status` -> `계산 가능 여부`
  - `accounting_analysis` -> `회계 방식 분석`
  - `fx_calculation` -> `외화 계산 결과`
  - `voucher_review` -> `전표 검토 결과`
- 회계 raw 카드의 내부 키 직접 노출 제거
  - `can_calculate` -> `계산 가능 여부`
  - `reason` -> `판단 근거`
  - `blocking_issue` -> `차단 사유`
  - `missing_required_inputs` -> `누락 입력`

같은 날 결과 패키지 Markdown/JSON 조립 경로도 보정했다. success moving average 샘플 기준으로 아래 문제가 재발하지 않도록 회귀를 추가했다.

- `핵심 업무 규칙` / `유지해야 할 계약`에 `ready` placeholder 직접 노출 금지
- `decision_items` 중복 문장 제거
- 회계 결과의 영문 내부 값 직접 노출 금지
  - `MOVING_AVERAGE` -> `이동평균법`
  - `all required inputs present` -> `필수 입력이 모두 제공되었습니다.`
  - `voucher_review requires vouchers and account_mappings` -> `전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다.`
- accounting success 샘플의 도메인 앵커를 일반 `account 기능`이 아니라 `회계 기능`으로 고정

관련 contract: [REBUILD_ASSISTANT_POLISH_UI_RENDERING_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_POLISH_UI_RENDERING_CONTRACT_2026-03-30.md)

같은 날 refinement 단계 보정도 추가했다. 이 보정의 목적은 판단 구조를 바꾸지 않고 결과 패키지의 문서 축과 완성도를 맞추는 것이다.

- `report_purpose`는 더 이상 기계적으로 `primary_judgment`만 따르지 않고, 사용자가 실제로 읽는 narrative 축을 따르는 `selected_narrative_judgment`를 기준으로 생성한다.
  - `python_claim_adjustment_case_01` -> `access_control` 목적
  - `amount_limit` -> `amount_threshold` 목적
- 한 문서 안에서 상단/본문 패턴이 섞이지 않도록 narrative 축을 단일화했다.
  - `rca_exception_case_01`은 `workflow` 상단/본문/계약을 같은 축으로 유지한다.
- 회계 문서는 상단 narrative뿐 아니라 하단 섹션도 회계 전용 템플릿으로 분리했다.
  - `grounded_business_rules`
  - `core_business_rules`
  - `retained_contracts`
  - `recomposition_draft`
  - `recommended_directions`
- 공통 문장 조합기도 보강했다.
  - `누락로` -> `누락으로`
  - `금지을` -> `금지를`
  - `규칙야 합니다` -> `규칙이어야 합니다`
  - `이동평균법로` -> `이동평균법으로`
  - `입니다. 입니다.` -> `입니다.`

관련 contract: [REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md)

## 2. 이번 라운드에서 정리된 항목

### 2.1 결과 패키지 구조

현재 결과 패키지는 아래 순서를 고정한다.

1. Executive Summary
2. 핵심 결론
3. 핵심 업무 규칙
4. 즉시 결정 필요
5. 유지해야 할 계약
6. 분리 우선순위
7. 확인 필요 항목
8. 설계 선택지 비교
9. 추천안
10. 실행 계획
11. 리스크
12. 전환 초안
13. 부록

내부 authoritative payload는 아래 5개 block을 기준으로 유지한다.

- `structure_snapshot`
- `diagnosis_report`
- `decision_summary`
- `improvement_plan_bundle`
- `appendix`

Flat 결과와 UI 문장은 위 authoritative block에서 파생한다.

### 2.2 출력 품질

아래 항목은 구조적으로 정리됐다.

- 내부 라벨 직접 노출 제거
  - `status_permissions`
  - `search_filters`
  - `save_validation`
- 내부 토큰 제거
  - `REDACTED_PATH`
  - `SAFE STRUCTURE`
  - `TBL_001`, `COL_001` 등 익명 식별자 직접 노출
- 결과 문장 강도 분리
  - 핵심 결론은 도메인 축을 유지한다.
  - 판단 근거, selection reason, 보조 요약 문장은 필요 이상 확정형으로 밀지 않는다.
  - `왜 이 판단인지` 설명 가능한 방향으로 `score_breakdown`과 함께 읽히도록 유지한다.

### 2.3 판단 템플릿 구조

현재 판단 템플릿은 아래 6종이다.

- `state_transition`
- `workflow`
- `access_control`
- `validation`
- `query_filter`
- `amount_threshold`

추천안, 분리 우선순위, 실행 계획은 템플릿 조합 기준으로 생성하며, 도메인명 하드코딩은 제목/앵커 수준으로만 남겼다.

2026-03-29 기준으로 패턴 선택 경로는 후보 수집 + 최종 선택 + 불변성 추적 구조로 보강했다.

- safe bundle 기준 workflow 신호 보강
- `run_finished.payload_json.primary_judgment` 기록
- `run_finished.payload_json.judgment_template_key` 기록
- 관련 contract: [REBUILD_ASSISTANT_PATTERN_SELECTION_CONTRACT_2026-03-29.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_PATTERN_SELECTION_CONTRACT_2026-03-29.md)

### 2.4 access_control 보강

현재 `access_control` 문서는 아래 구조를 갖는다.

- 핵심 규칙 3개 구조
  - 금액 기준 권한 제한
  - 권한 위임 가능 여부
  - 승인 요청 및 처리 흐름
- 확인 필요 항목 2개 이상
  - 권한 위임 세부 범위
  - 예외 승인 조건 상세
  - 처리 후 통지와 후속 처리 절차

### 2.5 validation 보강

현재 `validation` 문서는 아래 축으로 유지된다.

- 차단 조건
- 저장 전 검증
- 검증 순서
- 중복 방지
- 선행 조건

즉시 결정 필요 3개와 분리 우선순위 1/2/3순위도 고정된다.

### 2.6 query_filter / amount_threshold 1차 추가

현재 1차 확장으로 아래 템플릿이 추가됐다.

- `query_filter`
  - 조회 조건
  - 필터 조합
  - 정렬
  - 페이징
- `amount_threshold`
  - 금액 구간
  - 한도 정책
  - 임계값
  - 고액 처리 경계

이번 단계에서는 템플릿 registry, scoring, 추천안, 우선순위, 실행 계획, 전환 초안까지 새 템플릿을 처리할 수 있게 반영했다.

### 2.7 workflow 1차 추가

현재 1차 도입으로 `workflow` 템플릿이 추가됐다.

- 판정 기준
  - 승인 주체
  - 단계 구조
  - 의사결정 게이트
  - 위 3개 중 2개 이상일 때만 `workflow`
- 출력 축
  - 승인 트리거 조건
  - 승인 주체
  - 승인 단계 구조
  - 예외 처리 흐름
  - 상태 전이와의 관계
- fallback
  - 조건이 부족하면 `state_transition`

`workflow` 신호는 goal/constraints가 아니라 실제 자산 본문에서만 읽도록 제한했다. 그래서 기존 `access_control`, `state_transition`, `amount_threshold` 샘플을 과탐지하지 않는다.

### 2.8 회귀 테스트 상태

현재 기준 회귀 테스트는 아래를 통과한다.

- `workflow` 단일 승인형
- `workflow` 다단계 승인형
- `workflow` 예외 포함 승인형
- `state_transition` fallback

전체 회귀 결과:

- `159 passed`

### 2.9 패턴 후보 선택 경로 고정

2026-03-29 기준으로 `primary_judgment` 선택은 아래 구조로 고정됐다.

- `pattern_candidates`
  - 각 패턴별 `matched`, `score`, `reasons`, `rejected_reason`
- `select_primary_judgment(...)`
  - 단순 최대 점수 선택 금지
  - 최소 성립 조건 + 충돌 규칙 + 우선순위 기반 선택
- 불변성
  - 선택 결과를 `PreparedRebuildInput.selected_primary_judgment`에 고정
  - downstream과 `structured_result`는 같은 값을 재사용
- 디버깅
  - `run_finished.payload_json.primary_judgment`
  - `run_finished.payload_json.judgment_template_key`
  - `run_finished.payload_json.structured_result.primary_judgment`
  - `primary judgment selected` 로그 이벤트

추가로 `save_validation`이 주축인 샘플에서 `query_filter`가 과선택되던 회귀를 수정했다.

- `query_filter`
  - `search_filters`가 실제 주축일 때만 선택
- `validation`
  - `primary_feature_mode = save_validation`이면 `query_filter`보다 우선

### 2.10 청구 조정 access_control 정렬 보정

2026-03-29 기준으로 `청구 조정` 실샘플에서 아래 문제가 있었다.

- `primary_judgment = access_control`
- 하지만 핵심 업무 규칙 1순위가 `금액 한도 검증`
- 유지 계약 상단도 validation 계약이 점유

이번 보정으로 아래를 고정했다.

- claim 실샘플에서 `branch_manager`, `HQ_REVIEWER`, `CLAIM_AUDIT`, `B99`, `FRAUD`, `선승인` 신호가 강하면
  - access_control 규칙을 grounded rule 상단으로 우선 정렬
  - amount/validation 규칙은 보조로 하향
- 유지 계약도
  - `지점장 승인 경계`
  - `CLAIM_AUDIT 전담 부서 규칙`
  - `FRAUD 본사 심사 규칙`
  - `B99 긴급건 본사 선승인 규칙`
  을 우선 노출

따라서 현재 `청구 조정` 문서는 access_control 문서로 읽히도록 정렬이 맞춰진 상태다.

### 2.11 표현 전용 polish 레이어 추가

2026-03-29 기준으로 `rebuild_assistant`는 `structured_result` 외에 `polish_bundle`을 별도 생성한다.

- 원문 불변
  - `primary_judgment`
  - `grounded_business_rules`
  - `retained_contracts`
  - `recommended_option`
  - `execution_plan`
  - 숫자, 상태값, 코드명
- 후처리 3단계
  - `sentence polish`
  - `audience summary transform`
  - `delivery tone rewrite`
- audience
  - `developer`
  - `manager`
  - `client`
- delivery mode
  - `internal_review`
  - `client_report`
  - `proposal_appendix`

현재 구현은 deterministic v1이며, optional AI rewrite hook은 설계만 열어두고 기본값 `OFF`로 둔다.

### 2.12 회계 MVP 확장 추가

2026-03-30 기준으로 기존 `rebuild_assistant` 판단 엔진 위에 전산회계 MVP 확장을 추가했다.

- 입력
  - `accounting_payload.json`
  - `transactions`
  - `exchange_rates`
  - `policies`
  - `vouchers`
  - `account_mappings`
  - `strict`
- 계산 가능 여부
  - `calculation_status.can_calculate`
  - `reason`
  - `blocking_issue`
- 계산 기능
  - `accounting_analysis`
  - `fx_calculation`
  - `voucher_review`
- 실패 정책
  - 필수 입력 누락 시 계산 중단
  - 실패형 `summary_sentence` 강제 생성
- strict 모드
  - `strict=True` 기본값
  - ambiguity / inferred-only 핵심 계산 실패
  - `strict=False`는 warning 후 가능한 범위만 계속

현재 acceptance 기준 계산은 아래를 통과한다.

- `MOVING_AVERAGE = 22500`
- `FIFO = 25000`
- `missing exchange_rates -> can_calculate = false`
- `summary_sentence` 성공/실패 문장 동기화
- result package / polish bundle 회계 섹션 생성

## 3. workflow 실문서 검증 결과

2026-03-29 기준으로 `workflow` 샘플 4종을 현재 코드로 재생성해 실제 결과 패키지 텍스트를 검증했다.

- 단일 승인형
  - 판정: `workflow`
  - 상태: 부분 통과
- 다단계 승인형
  - 판정: `workflow`
  - 상태: 부분 통과
- 예외 포함 승인형
  - 판정: `workflow`
  - 상태: 부분 통과
- 단순 상태 변경 fallback
  - 판정: `state_transition`
  - 상태: 통과

현재 `workflow`의 핵심 판정과 fallback 경계는 맞고, 1차 문서 품질 보강도 반영됐다.

- 핵심 규칙 정렬
  - `승인 트리거 조건`
  - `승인 단계 구조`
  - `의사결정 분기 조건`
  - `예외 처리 흐름`
  중심으로 재정렬
- 유지 계약
  - `승인 경로와 처리 순서 계약`
  - `단계별 승인 순서 계약`
  - `승인 경로와 예외 승인 규칙 계약`
  생성 보강
- verification
  - access_control 기본 확인 항목 대신 workflow 전용 확인 항목 사용
- 결론 문장
  - `승인 트리거와 승인 단계 구조` 고정 문구로 조사 오류 제거

즉, `workflow`는 현재

- detection: 통과
- state_transition fallback: 통과
- 실제 결과 문서 품질: 통과

### 3.1 최신 재생성 검증

샘플:

- `mellow_link/modules/rebuild_assistant/samples/06. workflow/cs_leave_workflow.cs`
- `mellow_link/modules/rebuild_assistant/samples/06. workflow/ts_approval_flow.ts`

재생성 결과 기준 확인:

- 문서 성격
  - 권한 정책 중심이 아니라 승인 흐름 중심으로 읽힘
- 핵심 업무 규칙 상위
  - `의사결정 분기 조건`
  - `예외 처리 흐름`
  - `승인 트리거 조건`
  - `승인 주체 정의`
  - `승인 단계 구조`
- 유지 계약
  - `승인 경로와 처리 순서 계약`
  - `승인 권한 체계 계약`
  - `단계별 승인 순서 계약`
  - `승인 경로와 예외 승인 규칙 계약`
- 실행 계획
  - 트리거 -> 주체 -> 단계 -> 예외 -> 상태 전이 통합 순서 유지

### 2.8 query_filter / amount_threshold 순도 게이트

이번 실행에서 `query_filter`, `amount_threshold`는 템플릿 판정뿐 아니라 섹션 선택 단계까지 primary 영향을 주도록 보강했다.

- `query_filter`
  - 핵심 업무 규칙 상위 후보에서 상태전이 문장을 내림
  - 리스크는 primary 템플릿 기준으로만 우선 노출
  - 도메인 앵커는 일반 `request` 대신 `조회/필터`로 보정
- `amount_threshold`
  - 핵심 업무 규칙 상위 후보에서 조회/필터 문장을 제외
  - 유지 계약은 필드명 + 비교 연산 + 문맥 기준으로 금액 구간 경계 / 한도 기준 / 승인 필요 경계로 매핑
  - 전환 초안은 금액 구간, 한도 임계값, 고액 처리 경계 중심으로 보정
  - top-level narrative는 검증형이 아니라 금액 구간/한도 정책 중심으로 강제
  - 실행 계획도 검증형 공통 경로가 아니라 금액 정책 전용 경로로 분기
  - 숫자 추출은 필드명 + 비교 연산 + 주변 문맥 기준으로 다시 매핑
  - 실행 계획 2~4주차는 승인 필요 구간, 한도 초과 처리, 정책 결과 반영 중심으로 정리

### 2.7 state_transition 보강

현재 `state_transition` 문서는 아래 축을 유지한다.

- 상태 전이
- 처리 가능 상태
- 전이 조건

status 계약은 결과 상태만 남기지 않고 입력 상태와 결과 상태를 함께 포함하도록 보강했다.

예:

- `PAID`
- `READY`
- `COMPLETED`

## 3. 최신 샘플 판정

### 3.1 판단 템플릿 샘플

- `검증_result (13)`  
  - 통과
- `접근제어_result (18)`  
  - 통과
- `상태전환_result (18)`  
  - 통과
- `조회/필터형` 샘플  
  - 코드/테스트 기준 통과
  - 산출물 재검수 필요
- `금액/한도형` 샘플  
  - 코드/테스트 기준 통과
  - 산출물 재검수 필요

### 3.2 실샘플

- `청구_조정_기능을_현대적인_서비스_구조_재구성_result (12)`  
  - 통과
  - top-level narrative가 권한/부서/승인 주체 중심으로 복구됨
- `주문_관리_화면_현대화_result (9)`  
  - 거의 통과
  - 상태 계약 오염은 제거됨
  - 보조 validation 계약이 다소 강하게 남아 있음

## 4. 최신 보정 결과

이번 단계에서 실제로 해결된 문제는 아래와 같다.

- `청구 조정` 실샘플의 top-level narrative를 `access_control` 중심으로 복구
- `상태전환` 실샘플의 status 계약에 입력 상태 + 결과 상태 동시 유지
- `status` 계약에서 `BRANCH`, `VIP`, `CLAIM_AUDIT` 같은 비상태 값 제거
- `access_control` sparse 샘플에서 보강 로직이 실제 run 생성에 반영되도록 수정
- `search_filters`를 `query_filter` 판단 템플릿으로 승격
- 순수 금액 한도 샘플을 `amount_threshold` 판단 템플릿으로 승격
- `query_filter` primary 문서에서 상태전이 문장이 핵심 섹션으로 올라오지 않도록 게이트 적용
- `amount_threshold` primary 문서에서 조회/필터 규칙이 핵심 규칙으로 섞이지 않도록 게이트 적용
- `amount_threshold` 유지 계약을 금액 구간 경계 / 한도 기준 / 승인 필요 경계 기준으로 재매핑
- `amount_threshold` 실행 계획을 금액 정책 문서 기준으로 전용 분기
- `query_filter` 유지 계약을 조회 조건 파라미터 / 정렬·페이징 기본값 / 필터 조합 기준으로 보강
- `query_filter` 실행 계획과 전환 초안의 중복 토큰 조합을 보정
- `amount_threshold` 실행 계획에서 검증형 표현을 제거하고 금액 정책 절차 중심으로 고정
- `query_filter` 문장에서 `조회 조회`, `분리을`, `규칙 규칙`, `정합성를` 같은 중복/조사 오류를 최소 보정
- `amount_threshold` 확인 필요 항목을 `검증 실패` 문장에서 `한도 초과 이후 후속 처리 기준` 문장으로 교체
- `규칙 규칙`, `정합성를`가 다시 생기지 않도록 규칙 suffix 조합과 조사 부착 로직을 생성 단계에 추가
- `amount_threshold` 결과 문서에서 `검증` 단어가 남아 있던 옵션명과 리스크 문장을 금액 정책 표현으로 최종 정리

## 5. 테스트 상태

최신 회귀 테스트:

```text
pytest -q mellow_link/tests/test_phase1_run_flow.py mellow_link/tests/test_module_registry_and_runs.py mellow_link/tests/test_anonymization_mvp.py
159 passed
```

현재 회귀는 아래를 포함한다.

- 결과 패키지 구조 유지
- 내부 토큰 비노출
- 템플릿별 primary narrative 유지
- status 계약 추출 회귀
- access_control 보강 회귀
- validation 우선순위 회귀
- query_filter 적용 회귀
- amount_threshold 적용 회귀
- amount_threshold verification 비검증형 문장 회귀
- query_filter / amount_threshold 중복 토큰 및 조사 오류 회귀
- amount_threshold 결과 문자열 전체 `검증` 비노출 회귀
- accounting 입력 책임 / 계산 가능 여부 / 실패형 summary 회귀
- report purpose 자동 생성 / 회계 목적 우선 / 질문 원문 비노출 회귀
- accounting 상단 narrative 성공 / 실패 / 경고형 회귀
- accounting invalid schema failure humanize 회귀
- report purpose와 visible narrative 축 정렬 회귀
- `rca_exception_case_01` 단일 패턴 narrative 회귀
- accounting success 하단 섹션 회계 전용 분리 회귀
- 공통 조사/서술 조합 오류 회귀
- accounting 입력 책임 / 계산 가능 여부 / 실패형 summary 회귀
- report purpose 자동 생성 / 회계 목적 우선 / 질문 원문 비노출 회귀

## 6. 남은 작업

현재 남은 작업은 템플릿 구조 보강이 아니라 실샘플 제출본 polish와 확장 범위 검토다.

- 실샘플 근거 카드 문장 자연화
- `주문 관리 화면 현대화` 등 기존 실샘플의 보조 validation 문장 축약
- DOCX/PPTX 최종 문장 검수
- `approval(workflow)` 템플릿 도입 여부 검토

## 7. 현재 해석 기준

현재 제품/품질 판단은 아래 우선순위로 본다.

1. 코드
2. 본 상태 문서
3. [`ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md)
4. 개별 샘플 산출물
