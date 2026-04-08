---
title: Mellow-Link Engine Governance and QA
tags:
  - mellow-link
  - governance
  - qa
  - engine
created: 2026-04-06
status: current
---

# Mellow-Link Engine Governance and QA

## 중심 기준

엔진 구조의 source of truth는 [[Refactoring_Support_Engine]]이다.  
이 노트는 그 엔진을 운영할 때 필요한 판단 통제와 QA 규칙을 요약한다.

## 판단 위계

고정 순서:

`asset-derived > detector-derived > decision linkage > goal wording`

의미:
- goal/constraint wording은 보조 입력일 뿐이다.
- 자산 기반 evidence 없이 core judgment를 만들면 contamination 후보다.

## 주요 contamination 유형

- `wrapper wording contamination`
- `synthetic migration trigger`
- `asset-absent decision`
- `domain-anchor spillover`

## migration guard 핵심

다음 조건이면 migration 판단을 그대로 두면 안 된다.

- `decision_type == migration_consideration`
- `issue_ids == []`
- `evidence_ids == []`

이 경우:
- `synthetic_signal_detected = true`
- downgrade 규칙 적용

## QA에서 반드시 보는 축

- authoritative payload shape 유지 여부
- decision이 `detector_id` 기준으로 분기되는지
- taxonomy split 일관성
- `score_breakdown`과 `explainability` 정합성
- feature slice 규칙 유지 여부
- AI narrative가 canonical block을 건드리지 않는지
- audience 변경 시 canonical fact가 변하지 않는지
- migration contamination guard 위반이 없는지

## Review Layer 원칙

- canonical payload는 바꾸지 않는다.
- Review Layer는 additive artifact다.
- machine-readable source는 `extensions["review_diff"]`
- external surface에는 full review diff를 직접 노출하지 않는다.

## surface 해석

- internal
  - reviewer, QA, validation, debug용
  - `review_diff`, blocked decision, guard trace 확인 가능
- external
  - client-facing explanation용
  - canonical judgment와 evidence 설명만 노출

## 같이 볼 노트

- 엔진 기준: [[Refactoring_Support_Engine]]
- 골든샘플/검증: [[Mellow_Link_Validation_and_Golden_Samples]]
- 운영 이슈: [[Mellow_Link_Operations_and_Known_Issues]]
