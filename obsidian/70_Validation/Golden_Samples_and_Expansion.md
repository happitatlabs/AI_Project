---
title: Golden Samples and Expansion
tags:
  - validation
  - golden-samples
  - regression
created: 2026-04-06
status: current
---

# Golden Samples and Expansion

## 원문 기준

- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md`

## 고정 golden set

엔진 회귀 기준으로 보호하는 대표 샘플 5개:

- `00. rca_exception_case_01`
- `01. java_order_closure_case_01`
- `02. python_claim_adjustment_case_01`
- `04. amount_limit`
- `01_success_full`

## 보호하는 축

- workflow narrative
- state transition explainability
- access-control/report purpose
- amount-threshold refactor stability
- accounting extension success와 false structural decision 방지

## 확장 샘플 풀

promoted expansion regression 대상:

- `01_crud_simple`
- `02_access_control_workflow`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

## 운영 규칙

1. detector/scoring 변경 전 golden set 우선 실행
2. 기대값을 바꿀 때는 코드와 문서를 함께 수정
3. 깨진 golden sample을 문서 없이 넘어가면 안 됨

## 해석 포인트

golden set은 canonical 회귀 축이고, expansion sample은 커버리지를 넓히는 보강 축이다.  
둘은 역할이 다르므로 같은 수준의 기준 문서로 섞어 읽지 않는 편이 좋다.

## 같이 볼 노트

- [[Validation_Governance_and_Checklists]]
- [[Real_Project_Validation_Runs]]
