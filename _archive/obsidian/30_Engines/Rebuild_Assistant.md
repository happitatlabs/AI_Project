---
title: Rebuild Assistant
aliases:
  - rebuild_assistant
tags:
  - engine
  - modernization
  - analysis
created: 2026-04-06
status: current
---

# Rebuild Assistant

## 한 줄 정의

`rebuild_assistant`는 JSP/Java/SQL 계열 레거시 기능을 기능 단위로 분석하고, 현대화 방향과 실행 가능한 조치를 제안하는 모듈이다.

## 위치와 관계

- 실제 위치: `core/mellow_link/modules/rebuild_assistant`
- 제품 소속: [[Mellow_Link]]
- 엔진 기준 문서: [[Refactoring_Support_Engine]]

## 기본 실행선

`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant`

## 입력

- `goal`
- `safe_bundle`
- `constraints`

공개 실행 요청은 raw asset이 아니라 `SafeAnalysisBundle` 기준으로 동작한다.

## 주된 분석 초점

- `feature_slice` 단위 구조 분석
- 기능 성격 분류
- 현대화 전략 제안
- 구조화된 결과 패키지 생성

## 현재 feature mode

- `status_permissions`
- `search_filters`
- `save_validation`

## 출력 해석

- 분석 결과
  - 목적, 결론, 요약, 레이어 재구성 초안
- 결정 지원
  - decision item, design option, recommended option, execution plan
- authoritative payload
  - 구조, 진단, 판단, 계획, 근거 인덱스

## 해석 포인트

- `execution_plan`은 자동 실행이 아니라 실행 준비 계획이다.
- AI는 설명 레이어에만 관여하고, canonical 구조/판단 block은 deterministic source를 유지한다.
