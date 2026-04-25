---
title: AI Augmentation Policy
tags:
  - policy
  - ai
  - augmentation
created: 2026-04-06
status: current
---

# AI Augmentation Policy

## 원문 기준

- `core/mellow_link/docs/AI_AUGMENTATION_STRATEGY.md`

## 핵심 정의

AI는 분석 엔진을 대체하는 것이 아니라, deterministic 엔진 결과를 해석하고 읽기 좋게 만드는 보정 계층으로만 사용한다.

## 역할 분리

- 패턴 추출: Deterministic Engine
- 의미 해석: AI
- 누락 탐지: AI
- 결과 번역: AI
- 최종 검증: Deterministic Guard

## 허용 지점

1. 규칙 해석 보정
2. 규칙 보강/누락 탐지
3. 결과 번역/압축

## 금지 지점

- 패턴 추출 단계
- 전체 분석 위임
- 재현성이 깨지는 판정 기준
- 원본 evidence를 덮어쓰는 수정

## 충돌 규칙

- deterministic 결과와 AI 해석이 충돌하면 deterministic 결과 우선
- evidence 없는 신규 사실은 확정으로 올리지 않음
- 구조 validator를 통과하지 못하면 반영하지 않음

## 현재 제품 해석

`rebuild_assistant`에서 AI는 narrative 선택, 핵심 규칙 정리, 추천안 이유 정리, 문장 polish를 돕는다.  
반대로 자산 존재 판정, feature signal 추출, retained contract 후보 생성, 템플릿 판정 기준은 코드로 고정한다.

## 같이 볼 노트

- [[Refactoring_Support_Engine]]
- [[Mellow_Link_Engine_Governance_and_QA]]
