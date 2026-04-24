---
title: Real Project Validation Runs
tags:
  - validation
  - real-project
  - test-status
created: 2026-04-06
status: current
---

# Real Project Validation Runs

## 원문 기준

- `core/mellow_link/docs/validation_runs/README.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_TEST_STATUS_2026-04-05.md`

## 역할

실제 프로젝트 validation 결과와 rerun diff, screenshot evidence를 저장하는 reviewer evidence 레이어다.

## source of truth 아님

이 레이어는 아래가 아니다.

- 엔진 구조 기준 문서
- canonical payload 계약 문서
- detector/scoring 정책 기준 문서

즉 실행 결과를 기록하는 증적 저장소로 본다.

## validation record에 남기는 것

- `structural_judgment`
- `recommended_strategy`
- `narrative_axis`
- top evidence
- Q&A smoke 결과
- contamination 사례와 `synthetic_signal_detected`

## contamination 기록 형식

- `confirmed observation`
- `root cause candidate`
- `follow-up check`

## 현재 테스트 상태 메모

2026-04-05 기록 기준:

- `pytest -q mellow_link/tests`
- `644 passed`
- `4 skipped`

즉 review layer, explanation/Q&A, role-ready surface access까지 포함한 저장소 테스트가 green 상태로 기록돼 있다.

## 같이 볼 노트

- [[Validation_Governance_and_Checklists]]
- [[Mellow_Link_Validation_and_Golden_Samples]]
