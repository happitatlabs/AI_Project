---
title: Pattern Extraction Pipeline Detail
tags:
  - pipeline
  - sql
  - detail
created: 2026-04-06
status: current
---

# Pattern Extraction Pipeline Detail

## 개요

익명화된 SQL/구조 자산에서 실무 패턴을 추출하고, 향후 추천 엔진이 사용할 학습 재료 JSON과 bundle을 생성하는 최소 실행 파이프라인이다.

## 핵심 목표

- 샘플 SQL 1개 입력
- normalization 수행
- 패턴 최소 1개 이상 추출
- 결과 JSON 저장
- training bundle 생성

## 범위 제약

- 멜로우 엔진 본체 수정 없음
- 추천 로직 구현 없음
- 벡터 DB 연동 없음
- 최소 실행 가능한 골격만 구현

## 단계별 구성

1. `input_loader`
2. `normalizer`
3. `pattern_extractor`
4. `pattern_serializer`
5. `training_bundle_builder`

## 추출 대상 패턴 예시

- `join_style`
- `where_condition_style`
- `subquery_usage`
- `grouping_style`

## 결과 포맷

```json
{
  "source_id": "string",
  "normalized_sql": "string",
  "patterns": [
    {
      "type": "string",
      "description": "string",
      "evidence": ["string"]
    }
  ]
}
```

## 실행 결과 경로

- 결과 JSON: `pattern_extraction_pipeline/pipeline/output/sample_sql_001_patterns.json`
- training bundle: `pattern_extraction_pipeline/pipeline/output/training_bundle.json`

## 실행 메모

프로젝트 루트 기준:

```powershell
python pattern_extraction_pipeline/pipeline/main.py
```

## 현재 해석

이 파이프라인은 제품 본체가 아니라 학습 재료 생성 계층이다.  
즉 추천 엔진을 직접 수행하는 게 아니라, 추천 엔진이 쓸 pattern artifact를 만드는 지원 프로젝트로 보는 것이 맞다.

## 같이 볼 노트

- 요약본: [[Pattern_Extraction_Pipeline]]
- 상위 구조: [[Role_Groups]]
- 프로젝트 홈: [[AI_Project_Home]]
