# Refactoring Support Engine Decision Governance

기준일: 2026-04-05  
상태: Locked  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## Section 1. Overview

이 문서는 `refactoring_support_engine`의 판단 통제 기준을 고정하는 운영 표준이다.  
목적은 `migration_consideration` 같은 구조 판단이 자산 기반 근거 없이 wrapper 문구나 보조 입력만으로 생성되지 않도록 막는 것이다.

엔진 정의는 아래 문장으로 고정한다.

- `레거시 시스템을 해석하여 구조와 의존성을 진단하고, 신규 환경으로 이전 가능한 구조 초안과 의사결정 근거를 생성하는 엔진`

현재 확인된 대표 오염 사례는 다음과 같다.

- `judgment hierarchy violation`
- `wrapper wording contamination`
- `synthetic migration trigger`
- `asset-absent decision`

핵심 root cause는 아래로 고정한다.

- `project-wrapped goal`의 고정 문구가 `goal-derived signal`을 과잉 활성화할 수 있다.
- `goal/constraint wording`이 자산 기반 근거보다 앞서면 core judgment가 오염된다.
- `migration_consideration`은 자산 기반 근거 없이 생성되면 안 된다.

왜 필요한가:
- goal contamination은 실제 구조 판단을 가린다.
- asset-absent decision은 evidence 기반 엔진이라는 제품 정의를 깨뜨린다.

## Section 2. Judgment Hierarchy

엔진 판단 위계는 아래 순서로 고정한다.

`asset-derived > detector-derived > decision linkage > goal wording`

### 2.1 asset-derived
- code, UI, SQL, schema, business document에서 직접 확인된 신호
- 구조 판단의 최상위 근거다

### 2.2 detector-derived
- structure analysis와 diagnosis 결과로 생성된 issue
- asset-derived signal을 구조 문제로 정리한 계층이다

### 2.3 decision linkage
- `issue_ids`
- `evidence_ids`
- `score_breakdown`
- `explainability`
- 결정 결과를 추적 가능하게 만드는 계층이다

### 2.4 goal / constraint
- 사용자 목표, wrapper가 생성한 goal, 제약 조건
- 구조 판단의 보조 입력이다
- 단독으로 core judgment를 만들면 안 된다

운영 규칙:
- `goal/constraint wording`은 항상 보조 입력이다.
- `asset-derived evidence`가 없는 decision은 contamination 후보로 본다.
- `migration_consideration`은 반드시 asset 또는 issue 계층에 닿아 있어야 한다.

## Section 3. Migration Consideration Rules

### 3.1 허용 조건
- business asset 안에 migration 관련 신호가 직접 존재한다.
- detector issue가 migration 방향과 연결된다.
- 사용자 명시 요구가 있고, 최소한의 구조 근거가 같이 존재한다.

최소 구조 근거는 아래 중 하나다.
- `issue_ids`가 비어 있지 않다.
- `evidence_ids`가 비어 있지 않다.
- business asset에서 migration 관련 명시 신호가 직접 확인된다.

### 3.2 금지 조건
- goal 문구만으로 migration signal이 생성된다.
- `issue_ids == []`
- `evidence_ids == []`
- business asset에 migration 관련 신호가 없다.
- `narrative_axis` 또는 `template_judgment`만 migration을 시사하고 core judgment 계층은 비어 있다.

### 3.3 예외 조건
- 사용자가 migration 목표를 명시했지만 자산이 얕은 경우는 예외적으로 검토할 수 있다.
- 이 경우도 core judgment 확정이 아니라 advisory note로만 다룬다.
- validation 문서에는 반드시 `asset-derived support 부족`을 남긴다.

## Section 4. Hard Guard Rules

Hard Guard Rule은 엔진이 반드시 지켜야 하는 규칙이다.  
validation 메모가 아니라 실행 레벨 가드 기준으로 해석한다.

### Guard-01: Asset-Absent Migration Block

조건:
- `decision_type == "migration_consideration"`
- `issue_ids == []`
- `evidence_ids == []`

강제 동작:
- `synthetic_signal_detected = true`
- downgrade 수행

downgrade 규칙:
- `diagnosis_report.issues`가 0건이면 `observation_only`
- `diagnosis_report.issues`가 1건 이상이면 `refactor`

의미:
- asset 기반 근거 없는 migration은 허용하지 않는다.

### Guard-02: Goal-Only Migration Block

조건:
- migration signal source가 `goal/constraint wording`뿐이다
- asset text, detector issue, evidence 중 migration 관련 근거가 없다

강제 동작:
- `synthetic_signal_detected = true`
- `migration_consideration` 생성 금지

의미:
- wrapper wording은 판단 근거가 아니라 contamination source다.

### Guard-03: Validation Escalation

조건:
- migration decision이 유지된다
- asset-derived support가 약하거나 간접적이다

강제 동작:
- validation record에 아래 3구역을 필수로 남긴다
  - `confirmed observation`
  - `root cause candidate`
  - `follow-up check`

의미:
- 불완전한 migration 판단은 검증 대상으로 승격하고 그대로 통과시키지 않는다.

## Section 5. Contamination Types

### wrapper wording contamination
- 시스템 wrapper가 생성한 고정 goal 문구가 판단 신호를 오염시키는 현상

### synthetic migration trigger
- 자산/issue/evidence 없이 goal/constraint 텍스트만으로 `migration_consideration`이 생성되는 현상

### asset-absent decision
- `issue_ids`와 `evidence_ids`가 비어 있는데 decision이 존재하는 상태

### domain-anchor spillover
- 실제 자산 도메인과 무관한 concept/domain anchor가 표현 또는 규칙 생성에 섞이는 현상

## Section 6. Validation Standard

validation run 문서는 아래 3구역으로 고정한다.

### confirmed observation
- 자산 기반 사실만 기록한다.
- 예:
  - migration 신호 미검출
  - CRUD + 단일 검색 폼 + 단순 정렬 구조
  - `issue_ids=[]`, `evidence_ids=[]`

### root cause candidate
- contamination 원인 후보만 기록한다.
- 예:
  - wrapped goal의 `전환 초안`
  - goal/constraint 기반 migration signal
  - 샘플 운영 메타데이터 포함
  - domain anchor heuristic 과잉 매칭

### follow-up check
- 추가 검증 항목만 기록한다.
- 예:
  - `prepared.goal`, `prepared.constraints` 캡처
  - wrapper 문구 제거 시 migration 유지 여부 비교
  - `order_closure` 유입 경로 추적

## Section 7. QA Checklist Additions

QA에는 아래 항목을 추가한다.

- `migration_consideration` decision인데 `evidence_ids`가 비어 있지 않은가
- `migration_consideration` decision인데 `issue_ids`가 비어 있지 않은가
- migration signal source가 goal wording만은 아닌가
- business asset에서 migration 관련 근거가 실제로 확인되는가
- `asset-derived` 판단과 `goal-derived` 판단이 충돌하지 않는가
- `synthetic_signal_detected` 케이스가 validation에서 별도 표기되는가
- `narrative_axis`가 migration이 아닌데 core judgment만 migration으로 올라오지 않는가

## Section 8. Action Plan

1. [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)에 `Migration Consideration Governance Rules` 요약 섹션을 유지한다.
2. [`REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md)에 migration contamination 체크 항목을 유지한다.
3. [`REFACTORING_SUPPORT_ENGINE_REAL_PROJECT_VALIDATION_TEMPLATE.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_REAL_PROJECT_VALIDATION_TEMPLATE.md)에 validation 3구역 구조를 유지한다.
4. validation run 문서에는 `wrapped goal`, `constraints`, contamination 용어를 기록한다.
5. `goal wording contamination`은 real-project validation의 표준 root cause candidate로 사용한다.
6. `order_closure` 또는 `주문 마감` heuristic 유입 경로는 2차 점검 대상으로 관리한다.
7. 실제 프로젝트 1건 이상을 추가로 검증해 contamination 재현 여부를 비교한다.

## Section 9. Enforcement Point

이 규칙은 아래 지점에서 강제되어야 한다.

- `DecisionEngine`: `migration_consideration` 생성 직후
- `ResultPackager`: 최종 decision 확정 직전
- `Validation Layer`: validation run 기록 시

최소 요구:
- Hard Guard Rule은 `DecisionEngine` 내부에서 1차 적용한다.
- `ResultPackager`에서 2차 검증한다.
- validation에서는 `synthetic_signal_detected`를 반드시 기록한다.

운영 의미:
- `DecisionEngine`는 contamination이 decision으로 승격되기 전에 1차 차단한다.
- `ResultPackager`는 persisted 결과 surface에 synthetic migration이 남지 않도록 2차 확인한다.
- validation은 실행 후 증적을 남기는 마지막 통제 계층이다.

## Section 10. Intent Usage Policy

intent channel은 아래 3개로 고정한다.

- `goal`
- `constraints`
- `scenario`

evidence channel은 아래 5개로 고정한다.

- `source_code`
- `ui`
- `sql`
- `schema`
- `framework/runtime`

단계별 허용 범위는 아래로 고정한다.

- `StructureAnalyzer`: intent 사용 금지
- `DiagnosisEngine`: intent 사용 금지
- `DecisionEngine.goal`: 우선순위/추천 정렬 보조만 허용
- `DecisionEngine.constraints`: 금지 조건/배제 조건 필터 정의만 허용
- `DecisionEngine.scenario`: 설명 보강용으로만 허용
- `ImprovementPlanner.goal`: recommendation wording 또는 sort 보조만 허용
- `ImprovementPlanner.constraints`: exclusion filter만 허용
- `ImprovementPlanner.scenario`: explanation only

아래 영향은 모든 단계에서 금지한다.

- dependency 판정
- `structure_snapshot` 변경
- issue detection 변경
- confidence 상승

## Section 11. Insufficient Grounding Policy

evidence 부족 상태에서 recommendation, strategy, narrative는 과신되면 안 된다.

고정 규칙:

- evidence-backed decision이 없으면 `insufficient_grounding = true`
- direct structural evidence가 없으면 `insufficient_grounding = true`
- low confidence 상태에서는 recommendation을 observation 수준으로 downgrade 한다
- insufficient 상태에서는 recommended option을 확정안으로 표현하지 않는다
- limited grounding 상태에서는 recommendation을 draft/검토안으로만 표현한다

판단 문서는 아래 순서를 유지해야 한다.

- `recommended_strategy -> rationale -> evidence -> risk -> next_step`

## Section 12. Confidence Policy

confidence는 evidence 기반으로만 계산한다.

confidence 상승에 포함 가능한 신호:

- source code
- ui template
- sql query
- schema
- framework/runtime evidence

confidence 상승에 절대 포함되면 안 되는 신호:

- goal
- constraints
- scenario
- supporting docs
- narrative fallback

## Section 13. Output Polishing Policy

이 엔진의 최종 결과 패키지는 단순 분석 나열이 아니라 사람이 검토 가능한 판단 문서로 읽혀야 한다.

고정 규칙:

- `executive_summary_v2`는 항상 아래 4문장 구조를 유지한다
  - `문제`
  - `영향`
  - `조치`
  - `다음 단계`
- `one_line_conclusion`은 decision 문장처럼 읽혀야 하며 vague wording을 남용하면 안 된다
- `recommended_strategy`와 `recommended_option` 문장은 설계 제안처럼 읽혀야 한다
- `rationale` 문장은 반드시 근거 자산 또는 detector 판단을 암시해야 한다
- `risk`는 실제 이전/개발 리스크를 설명해야 한다
- `next_step`은 바로 실행 가능한 식별/분리/확인 행동이어야 한다

grounding-aware wording 규칙:

- `grounded`: 단정형 recommendation 허용
- `limited`: 조건형 recommendation만 허용, `검토안` 또는 `우선 검토` 톤 유지
- `insufficient`: recommendation 확정 금지, observation/근거 확보 문장만 허용

표현 일관성 규칙:

- 같은 narrative axis는 같은 문장 패턴을 유지해야 한다
- `validation` 계열은 차단 조건, 검증 순서, 저장 전 검증 분리 패턴을 유지한다
- `workflow` 계열은 승인 트리거, 승인 단계, 예외 처리 경계 분리 패턴을 유지한다
- `state_transition` 계열은 상태 전이, 처리 가능 상태, 전이 조건 분리 패턴을 유지한다
- `access_control` 계열은 승인 권한, 승인 주체, 부서 책임 분리 패턴을 유지한다
- `query_filter` 계열은 조회 조건, 필터 조합, 결과 목록 분리 패턴을 유지한다
- `amount_threshold` 계열은 금액 구간, 한도 정책, 고액 처리 경계 분리 패턴을 유지한다
