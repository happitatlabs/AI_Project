---
title: AI_Project Home
aliases:
  - AI_Project
tags:
  - ai-project
  - overview
created: 2026-04-06
status: current
---

# AI_Project 홈

## 한 줄 요약

`AI_Project`는 제품 본체, 지원 파이프라인, 실험 자산, 데이터, 공용 인프라를 역할 기준으로 분리해 관리하는 작업 루트다.

## 현재 기준 핵심 해석

- 대표 제품: [[Mellow_Link]]
- 대표 엔진 기준 문서: [[Refactoring_Support_Engine]]
- 지원 파이프라인: [[Pattern_Extraction_Pipeline]]
- 지원 파이프라인 상세: [[Pattern_Extraction_Pipeline_Detail]]
- 분리 운영 runtime: [[Mellow_Chat_Runtime]]
- 내부 자동화 계층: [[Autonomous_Agent]]
- 활성 문서 인덱스: [[Mellow_Link_Docs_Index]]
- 정책 인덱스: [[Policy_Index]]
- 계약 인덱스: [[Contracts_Index]]
- 검증 인덱스: [[Validation_Index]]
- 카탈로그 인덱스: [[Catalog_Index]]

## 상위 구조

- 역할 그룹 정리: [[Role_Groups]]
- 제품 본체는 `core/`
- 지원 파이프라인은 `pipelines/`
- 실험 자산은 `experiments/`
- 런타임 데이터와 산출물은 `data/`
- 공용 자원은 `infra/`

## 현재 프로젝트 해석

- `core/mellow_link`
  - 현재 대표 사용자 제품
  - 레거시 시스템 분석과 현대화 판단 지원 담당
- `core/mellow_chat_runtime`
  - 분리 운영 가능한 경량 채팅 runtime API
- `core/autonomous_agent`
  - 내부 자동화 목적의 자율 운영 에이전트
- `pipelines/pattern_extraction_pipeline`
  - 구조/SQL 패턴 추출용 지원 파이프라인

## 문서 우선순위

1. 코드
2. 모듈 README
3. 현재 활성 문서 인덱스
4. 제안서나 백업 문서

## 추천 탐색 순서

1. [[Role_Groups]]
2. [[Mellow_Link]]
3. [[Rebuild_Assistant]]
4. [[Refactoring_Support_Engine]]
5. [[Pattern_Extraction_Pipeline]]
6. [[Mellow_Link_Docs_Index]]
7. [[Policy_Index]]
8. [[Contracts_Index]]
9. [[Validation_Index]]
10. [[Catalog_Index]]
