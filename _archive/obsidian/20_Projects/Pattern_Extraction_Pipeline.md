---
title: Pattern Extraction Pipeline
aliases:
  - pattern_extraction_pipeline
tags:
  - pipeline
  - sql
  - training-data
created: 2026-04-06
status: current
---

# Pattern Extraction Pipeline

## 한 줄 정의

익명화된 SQL/구조 자산에서 실무 패턴을 추출해, 후속 추천 엔진이나 catalog가 쓸 학습 재료를 생성하는 지원 파이프라인이다.

## 현재 위치와 역할

- 역할 그룹: `pipelines`
- 실제 위치: `pipelines/pattern_extraction_pipeline`
- 본체 제품이 아니라 학습 재료 생성용 지원 계층

## 핵심 목표

- 샘플 SQL 입력
- normalization 수행
- 패턴 1개 이상 추출
- 결과 JSON 저장
- training bundle 생성

## 파이프라인 단계

1. `input_loader`
2. `normalizer`
3. `pattern_extractor`
4. `pattern_serializer`
5. `training_bundle_builder`

## 생성 결과

- 패턴 결과 JSON
- training bundle JSON

## 범위 제약

- [[Mellow_Link]] 본체 코드 수정 없음
- 추천 로직 구현 없음
- 벡터 DB 연동 없음
- 최소 실행 골격만 구현

## 관련 노트

- 상세본: [[Pattern_Extraction_Pipeline_Detail]]
- 상위 구조: [[Role_Groups]]
- 프로젝트 홈: [[AI_Project_Home]]
