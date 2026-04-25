---
title: Mellow-Link Doc Coverage Status
tags:
  - catalog
  - coverage
  - docs
created: 2026-04-06
status: current
---

# Mellow-Link Doc Coverage Status

## 상태 정의

- `dedicated`
  - 원문 파일이 사실상 전용 옵시디언 노트로 연결됨
- `grouped`
  - 여러 원문 파일이 하나의 주제 노트로 묶여 요약됨
- `reference`
  - 역사성, 보조성, 주변 기능 문서라서 umbrella reference note로 연결됨
- `artifact`
  - validation 결과물이나 machine-readable 파일이라서 인벤토리/참조 용도로만 연결됨

## 현재 원칙

- 모든 현재 원문 파일에는 `primary landing note`를 하나 지정한다.
- 모든 원문 파일이 개별 전용 노트를 갖는 것은 아니다.
- 현재 대표 제품/엔진/계약/검증 기준은 dedicated 또는 grouped note 우선으로 본다.
- runtime/performance/OpenAPI/flow map 계열은 reference note로 묶는다.

## 현재 커버리지 해석

- source of truth 문서
  - dedicated 또는 grouped로 연결
- 실행 계약 문서
  - grouped contract note로 연결
- 검증 문서
  - grouped validation note 또는 artifact note로 연결
- 오래된 spec / auxiliary / runtime 자료
  - reference note로 연결

## 현재 상태 요약

- `core/mellow_link/docs` 파일은 현재 카탈로그 기준으로 모두 landing note가 지정되어 있다.
- `validation_runs` 하위 파일도 모두 `Real_Project_Validation_Runs` 계열로 연결되어 있다.
- 추가 분해가 필요한 경우는 `reference` 상태 문서군이다.

## 다음에 더 쪼갤 후보

- runtime/OpenAPI 문서군
- 성능/VRAM 튜닝 문서군
- flow map / architecture spec 문서군
- history/status 문서군

## 같이 볼 노트

- [[Mellow_Link_Source_Doc_Catalog]]
- [[Mellow_Link_Runtime_Performance_and_Integration_References]]
- [[Mellow_Link_Flow_Maps_and_Specs]]
