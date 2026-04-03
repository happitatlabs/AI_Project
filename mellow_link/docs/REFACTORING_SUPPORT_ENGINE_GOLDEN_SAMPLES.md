# Refactoring Support Engine Golden Samples

기준일: 2026-04-03  
상태: Contract  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

정답 샘플 5개를 고정하고, 엔진 변경 시 항상 같은 기준으로 품질 흔들림을 검증한다.  
이 문서는 샘플 목록과 기대 anchor를 설명하고, 실제 회귀는
[test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)로 고정한다.

## Golden Set

| Sample | 보호하는 축 | 기대 anchor |
|---|---|---|
| `00. rca_exception_case_01` | workflow narrative + redesign top decision | `primary_judgment=workflow`, `recommended_strategy=재설계 우선`, `top priority=12` |
| `01. java_order_closure_case_01` | state transition + UI/data coupling explainability | `primary_judgment=state_transition`, `recommended_strategy=리팩터링 우선`, `top priority=12` |
| `02. python_claim_adjustment_case_01` | access-control narrative purpose + redesign scoring | `report_purpose=권한 체계...`, `recommended_strategy=재설계 우선`, `top priority=15` |
| `04. amount_limit` | amount-threshold narrative + low-scope refactor | `report_purpose=금액 기준...`, `decision_count=1`, `top priority=9` |
| `01_success_full` | accounting extension success + no false structural decision | `accounting.can_calculate=true`, `decision_count=0`, 회계 목적 유지 |

## 고정 기대값

### 1. `00. rca_exception_case_01`
- `primary_judgment`: `workflow`
- `report_purpose`: `승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다.`
- `recommended_strategy`: `재설계 우선`
- `first_entry_point`: `ui:LegacyPage#submit`
- `top_decision_type`: `redesign`
- `top_priority_score`: `12`

### 2. `01. java_order_closure_case_01`
- `primary_judgment`: `state_transition`
- `report_purpose`: `상태 전이 규칙과 처리 흐름을 분석하기 위한 보고서입니다.`
- `recommended_strategy`: `리팩터링 우선`
- `first_entry_point`: `usecase:이_jsp_java`
- `top_decision_type`: `refactor`
- `top_priority_score`: `12`

### 3. `02. python_claim_adjustment_case_01`
- `primary_judgment`: `query_filter`
- `report_purpose`: `권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다.`
- `recommended_strategy`: `재설계 우선`
- `first_entry_point`: `usecase:이_python_flask`
- `top_decision_type`: `redesign`
- `top_priority_score`: `15`

### 4. `04. amount_limit`
- `primary_judgment`: `validation`
- `report_purpose`: `금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다.`
- `recommended_strategy`: `리팩터링 우선`
- `first_entry_point`: `usecase:금액_한도형_샘플`
- `top_decision_type`: `refactor`
- `top_priority_score`: `9`

### 5. `01_success_full`
- `primary_judgment`: `validation`
- `report_purpose`: `외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다.`
- `recommended_strategy`: `리팩터링 우선`
- `first_entry_point`: `usecase:전산회계_mvp_기능을`
- `decision_count`: `0`
- `accounting.can_calculate`: `true`

## 운영 규칙

1. 정책 조정, detector 튜닝, slice 규칙 변경 후에는 이 golden set을 먼저 돌린다.
2. 기대값을 바꿔야 한다면 코드와 문서를 같은 변경에서 함께 갱신한다.
3. golden sample이 깨졌는데 문서를 갱신하지 않았다면 변경은 완료로 보지 않는다.
