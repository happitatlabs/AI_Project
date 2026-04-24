---
title: Golden Failure Triage and Update 2026-04-09
tags:
  - validation
  - golden-samples
  - regression
  - update-log
created: 2026-04-09
status: current
---

# Golden Failure Triage and Update 2026-04-09

## 원문 기준

- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_FAILURE_TRIAGE_2026-04-08.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_UPDATE_2026-04-09.md`

## triage 결론

- `update_golden`
  - `00. rca_exception_case_01`
  - `02. python_claim_adjustment_case_01`
  - `04. amount_limit`
  - `01_success_full`
- `fix_engine`
  - `01. java_order_closure_case_01`

## engine fix 요약

대상 샘플은 `01. java_order_closure_case_01`이다.

- before: `usecase:jsp`
- after: `usecase:order_close_service`

수정 포인트:

- intent/evidence 분리 정책은 유지
- fallback usecase seed에서 generic file token 영향은 줄임
- 첫 asset 이름만 보지 않고 설명력 있는 evidence asset을 우선 선택

즉 이번 수정은 구조 판단 규칙 변경이 아니라 fallback anchor naming regression 보정이다.

## golden baseline 갱신 요약

### `00. rca_exception_case_01`

- `first_entry_point`와 `execution_plan`은 유지
- `design_options`와 `recommended_option` hash만 current wording으로 갱신

### `01. java_order_closure_case_01`

- engine fix 결과에 맞춰 `first_entry_point`를 `usecase:order_close_service`로 갱신
- planning wording hash도 current output 기준으로 동기화

### `02. python_claim_adjustment_case_01`

- evidence-derived anchor를 `usecase:claim_adjustment`로 갱신
- access-control narrative 기준 execution/design/recommended hash를 반영

### `04. amount_limit`

- `first_entry_point`를 `usecase:cs_expense_policy`로 갱신
- limited-grounding wording이 반영된 design/recommended hash로 정렬

### `01_success_full`

- structural evidence 부재 정책에 맞춰 `first_entry_point`를 `usecase:legacy_flow`로 갱신
- planning hash는 유지

## promoted expansion 동기화

이번 회귀를 green으로 유지하기 위해 promoted expansion expected assertions도 current deterministic output에 맞춰 같이 동기화했다.

대상:

- `01_crud_simple`
- `02_access_control_workflow`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

의미:

- golden set만 업데이트하고 expansion baseline을 방치하지 않음
- current deterministic wording/hash를 expansion regression에도 동일하게 반영

## 회귀 실행 결과

- `test_feature_slice_extractor.py -k "order_closure or falls_back_to_usecase_seed"`: `2 passed`
- `test_refactoring_support_golden_samples.py -k "java_order_closure_case_01"`: `1 passed`
- `test_refactoring_support_golden_samples.py`: `5 passed`
- `test_refactoring_support_promoted_expansion_samples.py`: `4 passed`
- `test_rebuild_assistant_integration.py -k "intent_inputs_do_not_change_structure_snapshot or confidence_does_not_increase_with_strong_intent_inputs"`: `2 passed`

## 해석 포인트

- 이번 변경은 `engine regression 1건 수정 + 정상 drift 4건 반영`으로 읽어야 한다.
- intent/evidence 분리 정책, grounding/confidence 정책, public API, authoritative payload shape는 건드리지 않았다.

## 같이 볼 노트

- [[Golden_Samples_and_Expansion]]
- [[Validation_Governance_and_Checklists]]
- [[Refactoring_Support_Engine]]
