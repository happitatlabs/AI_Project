---
title: Mellow-Link Validation and Golden Samples
tags:
  - mellow-link
  - validation
  - regression
  - samples
created: 2026-04-06
status: current
---

# Mellow-Link Validation and Golden Samples

## 목적

엔진 변경 후에도 판단 품질이 흔들리지 않는지 고정 샘플과 실제 프로젝트 검증 기록으로 확인한다.

## golden set 역할

고정 샘플 5개를 기준으로 다음 축을 보호한다.

- workflow narrative
- state transition explainability
- access-control/report purpose
- amount-threshold/low-scope refactor
- accounting extension success와 false structural decision 방지

## 운영 규칙

1. 정책 조정이나 detector 튜닝 후 golden set을 먼저 실행
2. 기대값이 바뀌면 코드와 문서를 같은 변경에서 갱신
3. golden sample이 깨졌는데 문서 갱신이 없으면 변경 완료로 보지 않음

## 확장 샘플 풀

주요 promoted expansion regression 대상:

- `01_crud_simple`
- `02_access_control_workflow`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

이 샘플들은 low-signal, workflow, query filter, tangled boundary 축의 회귀를 보강한다.

## real project validation 역할

`validation_runs`는 source of truth가 아니라 reviewer evidence 저장소다.

기록 목적:
- `structural_judgment`
- `recommended_strategy`
- `narrative_axis`
- top evidence
- Q&A smoke 결과
- contamination 사례 기록

## contamination 기록 3구역

- `confirmed observation`
- `root cause candidate`
- `follow-up check`

## 현재 테스트 상태

2026-04-05 기준 `mellow_link/tests` 전체 재실행 결과:

- `644 passed`
- `4 skipped`

즉 review layer, role-ready surface access, explanation/Q&A, regression 축까지 full green 상태로 기록되어 있다.

## 같이 볼 노트

- 거버넌스/QA: [[Mellow_Link_Engine_Governance_and_QA]]
- 제품/로드맵: [[Mellow_Link_Product_and_Roadmap]]
- 엔진 기준: [[Refactoring_Support_Engine]]
