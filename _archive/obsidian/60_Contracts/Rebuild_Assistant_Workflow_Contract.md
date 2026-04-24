---
title: Rebuild Assistant Workflow Contract
tags:
  - contract
  - rebuild-assistant
  - workflow
created: 2026-04-06
status: current
---

# Rebuild Assistant Workflow Contract

## 원문 기준

- `core/mellow_link/docs/REBUILD_ASSISTANT_WORKFLOW_TEMPLATE_CONTRACT_2026-03-29.md`

## 핵심 목적

승인형 `workflow` 템플릿을 `rebuild_assistant` 판단 체계에 추가하고, 단순 상태 변경과 구분하는 계약이다.

## `workflow` 성립 조건

아래 3개 중 2개 이상:

1. 승인 주체 존재
2. 단계 구조 존재
3. 의사결정 게이트 존재

2개 미만이면 `state_transition`으로 fallback 한다.

## 결과 문서에 드러나야 하는 축

- 승인 트리거 조건
- 승인 주체
- 승인 단계 구조
- 의사결정 분기
- 예외 처리 흐름

## 금지 사항

- 단순 상태 enum만으로 `workflow` 승격
- 기존 `state_transition`, `access_control`, `validation`, `query_filter`, `amount_threshold` 회귀
- 패턴 추출을 AI에 위임

## 현재 읽는 법

workflow는 현재 template family 중 하나지만, canonical registry는 `decision_catalog.py` 기준이다.  
즉 이 문서는 workflow 도입 당시의 실행 계약과 fallback 규칙을 읽는 보조 문서로 보면 된다.

## 같이 볼 노트

- [[Rebuild_Assistant_Judgment_and_Selection_Contract]]
