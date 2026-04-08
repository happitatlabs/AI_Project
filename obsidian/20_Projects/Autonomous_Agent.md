---
title: Autonomous Agent
aliases:
  - Mellow Agent
  - autonomous_agent
tags:
  - autonomous-agent
  - internal
  - automation
created: 2026-04-06
status: current
---

# Autonomous Agent

## 한 줄 정의

`autonomous_agent`는 로컬 LLM 기반 자율 운영 에이전트 본체다.

## 현재 위치와 성격

- 역할 그룹: `core`
- 실제 위치: `core/autonomous_agent`
- 현재 직접 사용자 진입 제품은 아님
- `mellow_link` 이후 단계의 내부 자동화 계층으로 분리 관리

## 핵심 기능

- 워크스페이스 분석
- 제안 생성
- 안전 작업 자동 실행
- 승인 대기 흐름 관리
- 보고서 생성과 운영 기록 보관

## 운영 방식 핵심

- 안전한 작업은 자동 실행
- 위험도 있는 작업은 `pending_approvals.json`에 저장
- LLM 실패 시 규칙 기반 fallback 가능

## 대표 스킬

- `workspace_reporter`
- `code_reviewer`
- `file_classifier`

## 해석 포인트

- 현재 상용 중심 제품은 [[Mellow_Link]]다.
- 이 프로젝트는 내부 자동화와 운영 보조 성격으로 보는 것이 맞다.
