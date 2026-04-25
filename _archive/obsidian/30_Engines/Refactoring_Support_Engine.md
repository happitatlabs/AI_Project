---
title: Refactoring Support Engine
aliases:
  - refactoring_support_engine
tags:
  - engine
  - source-of-truth
  - modernization
created: 2026-04-06
status: current
---

# Refactoring Support Engine

## 한 줄 정의

`refactoring_support_engine`는 `rebuild_assistant`의 실제 분석 엔진 기준을 정의하는 source of truth 문서이자 구조 계약이다.

## 핵심 관점

- 분석 단위는 `feature_slice`
- 공개 실행선은 유지
- 결과는 authoritative block 기준으로 생성
- 현재 상태는 `deterministic engine core + optional AI narrative layer`

## 엔진 모듈 구조

- `InputAssembler`
  - 입력 정규화
- `StructureAnalyzer`
  - 컴포넌트, 의존성, 레이어, slice 추출
  - fallback `usecase` seed는 intent가 아니라 evidence asset을 기준으로 잡고, generic file token보다 설명력 있는 asset label을 우선 사용
- `DiagnosisEngine`
  - detector 실행과 issue 생성
- `DecisionEngine`
  - 판단, 우선순위, decision 생성
- `ImprovementPlanner`
  - 설계 옵션과 실행 단계 생성
- `ResultPackager`
  - authoritative payload와 UI 호환 결과 파생

## authoritative payload

- `structure_snapshot`
- `diagnosis_report`
- `decision_summary`
- `improvement_plan_bundle`
- `appendix`

## 판단/통제 핵심

- detector policy와 scoring policy는 Phase 3 전까지 freeze
- `migration_consideration`은 evidence 없는 synthetic trigger가 되면 downgrade 규칙 적용
- audience가 바뀌어도 canonical fact, score, citation, decision linkage는 바뀌면 안 됨

## 표현 레이어 규칙

- AI가 수정 가능한 필드는 설명 계층 일부로 제한
- 판단, 점수, evidence, priority, execution stage linkage는 수정 금지
- 실패 시 deterministic fallback 유지

## 같이 볼 노트

- 상위 제품: [[Mellow_Link]]
- 실행 모듈: [[Rebuild_Assistant]]
- 상위 인덱스: [[AI_Project_Home]]
