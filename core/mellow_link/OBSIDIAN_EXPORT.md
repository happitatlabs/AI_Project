---
title: 멜로우 링크 판맥 - Obsidian Export
tags:
  - mellow-link
  - legacy-modernization
  - analysis-tool
  - ai-project
created: 2026-04-06
status: current
---

# 멜로우 링크 판맥 정리 메모

## 한 줄 정의

멜로우 링크 판맥(MellowLink Senseframe)은 레거시 시스템 자산을 익명화하고 구조 분석한 뒤, 판단 근거, 현대화 방향, 실행 준비용 결과 패키지를 제공하는 웹/API 기반 판단 지원 프로그램이다.

## 현재 제품 정의

- 역할 그룹: `core`
- 실제 위치: `AI_Project/core/mellow_link`
- 현재 대표 제품명: `멜로우 링크 판맥`
- 영문명: `MellowLink Senseframe`
- 대표 시나리오/기능: `레거시 현대화 분석`
- 성격: 자동 배포 엔진이 아니라 분석, 판단, 실행 준비를 지원하는 제품
- 실제 사용자 시작점: `/projects/create`

## 무엇을 하는 프로그램인가

사용자가 JSP, Java, SQL, 화면 자산 같은 레거시 자료를 프로젝트 단위로 올리면, 시스템은 먼저 익명화와 구조 추출을 수행한다. 그 다음 `rebuild_assistant`가 기능 단위를 해석하고, 판단 질문, 판단 근거, 부족한 정보, 현대화 방향, 분리 우선순위, 설계 선택지, 실행 준비 계획을 결과 패키지로 정리해 준다.

즉 이 프로그램의 핵심은 "코드를 바로 배포하는 것"이 아니라 "레거시 시스템을 어떤 순서와 기준으로 현대화할지 판단할 수 있게 만드는 것"이다.

## 기본 실행 흐름

```text
project
  -> anonymization
  -> SafeAnalysisBundle
  -> rebuild_assistant
  -> result package
```

## 핵심 기능

- 프로젝트 생성과 자산 업로드
- 원본 자산 익명화
- 구조 분석과 기능 단위 분해
- 기능 성격 분류
  - `status_permissions`
  - `search_filters`
  - `save_validation`
- 진단 결과 생성
- 현대화 방향 제안
- 설계 선택지 비교
- 분리 우선순위 제시
- 실행 준비용 결과 패키지 제공

## 사용자에게 나가는 주요 산출물

### 분석 결과

- 진단
- 설계안
- 전환 초안

### 결정 지원

- 추천안
- 분리 우선순위
- 설계 선택지 비교
- 실행 계획

`execution_plan`은 자동 실행이 아니라 `실행 준비 계획` 또는 `실행 준비 초안`으로 해석한다.

## 현재 로드맵 상태

- 1단계: 분석 + 결과 패키지
  - 완료
- 2단계: 조치 제안 + 비교
  - 부분 구현
- 3단계: 실행 준비
  - planned
- 4단계: 실행, 검증, 승인, 배포
  - planned
- 5단계: 운영, 로그, 감사
  - planned

## 내부 핵심 모듈

- `modules/rebuild_assistant`
  - 공개 분석 모듈
- `services/refactoring_support_engine`
  - 입력 조립, 구조 분석, 진단, 판단, 개선 계획, 결과 패키징 담당
- `docs`
  - 제품 상태, 계약, 운영 맥락 문서

## 관련 프로젝트

- `AI_Project/core/mellow_link`
  - 메인 제품 본체
- `AI_Project/core/mellow_chat_runtime`
  - 별도 운영 가능한 경량 채팅/runtime API
- `AI_Project/core/autonomous_agent`
  - 내부 자동화 계층
- `AI_Project/pipelines/pattern_extraction_pipeline`
  - 지원 파이프라인
- `AI_Project/experiments/redteam_outside_root`
  - 실험 및 경계 검증 자산

## 해석할 때 주의할 점

과거 문서 중에는 `Mellow-Link`를 로컬 AI 오케스트레이션 시스템처럼 설명한 스펙도 있다. 하지만 현재 활성 제품 정의는 `core/mellow_link/docs/README.md`와 `modules/rebuild_assistant/README.md` 기준으로 보는 것이 맞다.

현재 기준의 제품 정의는 아래 문장으로 고정한다.

> 레거시 시스템의 구조, 흐름, 판단 근거를 분석하고 실행 가능한 현대화 방향으로 정리하는 웹 기반 판단 지원 프로그램

## 현재 기준 대표 진입점

- `/`
- `/ui`
- `/projects/create`

## 참고 문서

- `AI_Project/core/mellow_link/docs/README.md`
- `AI_Project/refactoring_support_engine.md`
- `AI_Project/core/mellow_link/modules/rebuild_assistant/README.md`
- `AI_Project/core/mellow_link/README.md`

## 짧은 요약

Mellow-Link는 레거시 시스템 현대화를 위한 분석 제품이다.  
사용자가 자산을 업로드하면 익명화와 구조 분석을 거쳐, 현대화 방향과 우선순위, 설계 선택지, 실행 준비 계획을 결과 패키지 형태로 제공한다.
