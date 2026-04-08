---
title: Mellow Chat Runtime
aliases:
  - mellow_chat_runtime
tags:
  - runtime
  - core
created: 2026-04-06
status: current
---

# Mellow Chat Runtime

## 한 줄 정의

`mellow_chat_runtime`는 분리 운영 가능한 경량 채팅 runtime API다.

## 현재 위치와 역할

- 역할 그룹: `core`
- 실제 위치: `core/mellow_chat_runtime`
- 데이터 위치: `data/runtime/mellow_chat_runtime_data`

## 관계 정리

- [[Mellow_Link]]와는 별도 운영 가능한 계층이다.
- 사용자 대표 제품의 중심은 아니지만, 독립 실행 가능한 runtime으로 관리된다.
- 프로젝트 구조상 `core` 소속이므로 실험 자산이나 지원 파이프라인과는 구분해서 본다.

## 볼 때의 기준

- 제품 본체와 분리된 runtime/API 계층
- 저장 데이터는 코드 루트가 아니라 `data/runtime`에 둠
