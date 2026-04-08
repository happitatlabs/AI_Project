---
title: Validation Governance and Checklists
tags:
  - validation
  - governance
  - qa
created: 2026-04-06
status: current
---

# Validation Governance and Checklists

## 원문 기준

- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_REVIEW_LAYER_DESIGN.md`

## 검증 핵심

QA는 단순 결과 확인이 아니라, 엔진 구조/판단/표현이 기준 문서와 계속 정합한지 보는 통제 레이어다.

## 반드시 확인하는 축

- authoritative payload shape
- `detector_id` 기준 decision 분기
- taxonomy split 정합성
- `score_breakdown`과 explainability 정합성
- feature slice 규칙
- AI narrative가 canonical block을 바꾸지 않는지
- audience 변경 시 canonical fact 불변
- migration contamination guard 위반 여부

## migration governance 핵심

판단 위계:

`asset-derived > detector-derived > decision linkage > goal wording`

특히 `migration_consideration`은 evidence 없이 goal wording만으로 생성되면 안 된다.

## Review Layer 핵심

- canonical payload는 변경하지 않음
- `extensions["review_diff"]`는 additive artifact
- internal surface는 full diff 허용
- external surface는 canonical explanation만 허용

## 해석 포인트

이 노트는 QA 절차와 통제 규칙을 묶는다.  
샘플 자체나 실제 validation record는 별도 노트에서 본다.

## 같이 볼 노트

- [[Golden_Samples_and_Expansion]]
- [[Real_Project_Validation_Runs]]
