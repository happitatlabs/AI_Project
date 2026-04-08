---
title: Mellow-Link
aliases:
  - 레거시 현대화 분석
tags:
  - mellow-link
  - product
  - current
created: 2026-04-06
status: current
---

# Mellow-Link

## 한 줄 정의

Mellow-Link는 레거시 시스템 자산을 익명화하고 구조 분석한 뒤, 현대화 방향과 실행 준비용 결과 패키지를 제공하는 웹/API 기반 분석 도구다.

## 현재 제품 정의

- 역할 그룹: `core`
- 실제 위치: `core/mellow_link`
- 현재 대표 시작점: `/projects/create`
- 현재 제품 단계: 분석 + 결과 패키지 중심

## 기본 실행선

`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant -> result package`

## 핵심 기능

- 프로젝트 생성과 자산 업로드
- 익명화와 구조 분석
- 기능 단위 분해
- 현대화 방향 제안
- 설계 선택지 비교
- 분리 우선순위 제시
- 실행 준비 계획 제공

## 주요 산출물

### 분석 결과

- 진단
- 설계안
- 전환 초안

### 결정 지원

- 추천안
- 분리 우선순위
- 설계 선택지 비교
- 실행 준비 계획

## 관련 노트

- 실행 모듈 요약: [[Rebuild_Assistant]]
- 엔진 구조 기준: [[Refactoring_Support_Engine]]
- 활성 문서 묶음: [[Mellow_Link_Docs_Index]]
- 상위 프로젝트 맵: [[AI_Project_Home]]

## 해석 주의

과거 문서 중 일부는 `Mellow-Link`를 더 넓은 AI 오케스트레이션 시스템처럼 설명하지만, 현재 활성 제품 정의는 레거시 현대화 분석 제품으로 고정해 보는 것이 맞다.
