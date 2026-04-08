---
title: Mellow-Link Operations and Known Issues
tags:
  - mellow-link
  - operations
  - known-issues
created: 2026-04-06
status: current
---

# Mellow-Link Operations and Known Issues

## 운영 관점 핵심

현재 제품은 파일럿 범위 기준으로 설명과 분석 품질을 강화하는 단계다.  
설치, 보안, 보관 정책, 결과 provenance, 재분석 흐름이 운영 설명의 핵심이다.

## 파일럿 운영에서 챙길 것

- 프로젝트 단위 자산 영속 관리
- 결과 provenance
- 재분석 플로우
- 보안/데이터 취급 설명
- 설치 가이드
- 표준 산출물 템플릿

## 알려진 이슈 문서 해석

`KNOWN_ISSUES.md`는 일부 과거 엔진 v1 기준의 환경 의존 테스트 이슈를 기록한 문서다.

핵심 포인트:
- 몇몇 테스트는 환경/정책 차이 때문에 일부 환경에서 실패할 수 있음
- `env_policy` 성격의 테스트는 core-required와 분리해서 볼 수 있음
- 문서 시점이 2026-02-24라, 현재 full green 기록보다 오래된 이력으로 해석해야 함

## 현재 읽는 법

- 최신 엔진/결과 패키지 기준은 [[Refactoring_Support_Engine]]
- QA와 회귀 기준은 [[Mellow_Link_Engine_Governance_and_QA]]
- 최신 전체 테스트 기록은 [[Mellow_Link_Validation_and_Golden_Samples]]
- `KNOWN_ISSUES.md`는 운영 히스토리 문서로 보는 편이 맞다

## 운영 문서로 이어질 항목

- 보안/데이터 취급 브리프
- 설치형 운영 가이드
- 파일럿 제안서
- KPI/성공 기준 문서

## 같이 볼 노트

- 제품/로드맵: [[Mellow_Link_Product_and_Roadmap]]
- 보안 경계: [[Mellow_Link_Anonymization_and_Security]]
- 검증 상태: [[Mellow_Link_Validation_and_Golden_Samples]]
