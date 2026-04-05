# Refactoring Support Engine Golden Samples

기준일: 2026-04-03  
상태: Contract  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

정답 샘플 5개를 고정하고, 엔진 변경 시 항상 같은 기준으로 품질 흔들림을 검증한다.  
이 문서는 샘플 목록과 기대 anchor를 설명하고, 실제 회귀는
[test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)로 고정한다.

주의:
- 이 문서의 `primary_judgment` 값은 현재 public contract를 유지하기 위한 compatibility/template axis다.
- engine-owned structural decision은 `structural_judgment`로 별도 해석한다.
- user-facing 설명 축은 `narrative_axis`로 분리해 본다.

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

## 확장 샘플 풀

고정 golden set과 별도로, Phase 3 전 회귀 축 확장을 위한 후보 샘플은 아래 경로에 보관한다.

- [mellow_link/modules/rebuild_assistant/samples](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples)

공통 템플릿과 pack 설명서는 아래 경로를 사용한다.

- [samples/_templates/golden_samples_expansion](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/_templates/golden_samples_expansion)

확장 샘플용 QA 체크리스트는 아래 보조 문서를 사용한다.

- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md)

현재 promoted expansion regression 대상은 아래 4개다.

- [01_crud_simple](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/01_crud_simple)
- [02_access_control_workflow](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/02_access_control_workflow)
- [04_db_heavy_query_filter](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/04_db_heavy_query_filter)
- [05_legacy_tangled_mixed](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/05_legacy_tangled_mixed)

이 회귀군이 커버하는 리스크는 아래와 같다.

- low-signal / no-decision taxonomy 분리
- workflow 중심 refactor linkage
- query_filter detector-driven refactor stability
- tangled boundary / redesign escalation

## non-regression reference set

아래 디렉터리는 golden sample이나 promoted expansion regression 대상이 아니다.

- [03. judgment_template_samples](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/03.%20judgment_template_samples)
- [05. query_filter](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/05.%20query_filter)

이들은 runnable sample contract를 갖지 않는 snippet/reference set이다. 현재는 `goal.txt`, `input_manifest.json`, `expected_assertions.yaml`이 없고, regression test도 직접 참조하지 않는다.

이 둘을 regression 대상으로 승격하려면 아래 조건을 먼저 만족해야 한다.

1. 별도 runnable sample 디렉터리로 재구성
2. `input_manifest.json` 추가
3. `expected_assertions.yaml` measured anchor 추가
4. golden 또는 promoted expansion test에 명시 편입
