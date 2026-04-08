# Refactoring Support Engine Golden Update

기준일: 2026-04-09  
기준 triage: [`REFACTORING_SUPPORT_ENGINE_GOLDEN_FAILURE_TRIAGE_2026-04-08.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_FAILURE_TRIAGE_2026-04-08.md)

## 1. 이번 변경 범위

- engine regression 수정: `01. java_order_closure_case_01`
- current policy 기준 golden expectation 갱신: `00. rca_exception_case_01`, `02. python_claim_adjustment_case_01`, `04. amount_limit`, `01_success_full`
- golden baseline 정합성 유지를 위해 `01. java_order_closure_case_01` expectation도 engine fix 결과에 맞춰 함께 갱신

## 2. Engine Fix Summary

대상: `01. java_order_closure_case_01`

- before: `usecase:jsp`
- after: `usecase:order_close_service`
- 원인: fallback usecase seed가 첫 UI asset 이름 `legacy.jsp`에 과하게 끌려 generic token만 남았다.
- 수정: fallback seed에서 설명력 있는 evidence asset을 우선 고르도록 바꾸고, file stem 기준 label을 사용해 확장자 토큰 영향만 제거했다.
- 유지한 정책:
  - intent/evidence 분리 유지
  - goal wording이 structure seed를 바꾸지 않음
  - grounding/confidence 계산 로직 미변경

## 3. Sample별 Golden 변경 요약

### `00. rca_exception_case_01`

- 유지된 것:
  - `first_entry_point = ui:LegacyPage#submit`
  - `execution_plan_hash = 3106dcfb72e529015acd29860b5307cb3dd001ec`
- 갱신된 것:
  - `design_options_hash = e700271e07ed685a6c32eaa38c471ad6bc7f525d`
  - `recommended_option_hash = 070f62770a8c78431784aad7bb86350621c40cb7`
- 이유:
  - deterministic core는 유지됐고, selection reason wording만 governance/polish 기준으로 정리됐다.

### `01. java_order_closure_case_01`

- 갱신된 것:
  - `first_entry_point = usecase:order_close_service`
  - `design_options_hash = 22018f0263412d23f55971b55db787cb66eb8544`
  - `recommended_option_hash = 5e3e314bcee7322303e8acff41e7a1a4479a3ce4`
- 유지된 것:
  - `execution_plan_hash = ca5de017988d630e6a0fd65c924991444e2431b3`
- 이유:
  - regression fix로 seed anchor가 설명 가능한 evidence asset 쪽으로 이동했다.
  - planning core는 그대로고 selection reason wording baseline만 current output에 맞춰 정렬됐다.

### `02. python_claim_adjustment_case_01`

- 갱신된 것:
  - `first_entry_point = usecase:claim_adjustment`
  - `execution_plan_hash = 364cc6049b30dbb93d8426f55f78564710297d92`
  - `design_options_hash = 1fd04aae3f3d698b66175d9a34b865b9ac48a345`
  - `recommended_option_hash = 494d0b28390eb7c3b09d670873a9bb66aa943b2e`
- 이유:
  - evidence-derived anchor와 access-control narrative 정렬이 current policy와 report purpose에 더 부합한다.
  - 이번 heuristic 보정으로 `claim_adjustment.html`의 확장자 토큰도 제거돼 anchor가 더 간결해졌다.

### `04. amount_limit`

- 갱신된 것:
  - `first_entry_point = usecase:cs_expense_policy`
  - `design_options_hash = 53186b26b15e58839731522f43b25e4a71d6902b`
  - `recommended_option_hash = 1b3be67c22e777a6e1513ac3bf6d1209bf5744ed`
- 유지된 것:
  - `execution_plan_hash = 647b3f32501d37ecb9576e57272de1429fd5dca4`
- 이유:
  - goal-derived anchor를 버리고 evidence-first seed를 유지했다.
  - limited-grounding wording이 current governance에 맞게 보강됐다.

### `01_success_full`

- 갱신된 것:
  - `first_entry_point = usecase:legacy_flow`
- 유지된 것:
  - `execution_plan_hash = 147dfc031bc3e756e0417cf65ab36057a5f13f09`
  - `design_options_hash = da4eaeff6172c713b745116bdc6301bc6a9a3574`
  - `recommended_option_hash = 9c90dd147bfb8c7063de62b03361ae04f9bd2a35`
- 이유:
  - structural evidence가 없는 accounting-only sample에서 goal-derived anchor를 제거하는 쪽이 governance에 맞다.

## 4. 영향 범위 메모

- public API / authoritative payload shape 변경 없음
- decision, grounding, confidence 정책 변경 없음
- change surface는 fallback `first_entry_point` naming과 golden baseline 정렬에 한정됨
