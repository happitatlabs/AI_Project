---
title: Rebuild Assistant Judgment and Selection Contract
tags:
  - contract
  - rebuild-assistant
  - judgment
created: 2026-04-06
status: current
---

# Rebuild Assistant Judgment and Selection Contract

## 원문 기준

- `core/mellow_link/docs/REBUILD_ASSISTANT_JUDGMENT_TEMPLATE_EXPANSION_CONTRACT_2026-03-29.md`
- `core/mellow_link/docs/REBUILD_ASSISTANT_PATTERN_SELECTION_CONTRACT_2026-03-29.md`

## 핵심 목적

판단 템플릿을 단순 점수 최대값으로 고르지 않고, 후보 수집과 충돌 규칙을 거친 뒤 `primary_judgment`를 한 번만 결정하는 계약이다.

## 템플릿 범위

- `workflow`
- `state_transition`
- `access_control`
- `validation`
- `query_filter`
- `amount_threshold`
- fallback: `validation`

## 핵심 규칙

- `primary_judgment`는 한 번만 결정한다.
- downstream 단계에서 재선택하지 않는다.
- detection 결과와 최종 `structured_result` 성격이 어긋나면 안 된다.
- canonical registry는 현재 `decision_catalog.py` 기준으로 본다.

## 충돌 해소 예

- 단계성과 게이트가 강하면 `workflow`
- 권한 설명이 주축이면 `access_control`
- 저장 전 차단이 핵심이면 `validation`
- 조회 필터가 핵심이면 `query_filter`
- 금액 구간/한도 정책이 핵심이면 `amount_threshold`

## 디버깅 포인트

1. 후보 패턴 목록
2. 각 패턴 reason
3. 최종 선택 이유
4. 탈락 후보의 rejected reason
5. payload에 남은 `primary_judgment`

## 현재 읽는 법

이 계약은 템플릿 선택 규칙과 확장 범위를 다루는 보조 문서다.  
실제 엔진 구조와 canonical source는 [[Refactoring_Support_Engine]]를 우선한다.

## 같이 볼 노트

- [[Rebuild_Assistant_Workflow_Contract]]
- [[Validation_Governance_and_Checklists]]
