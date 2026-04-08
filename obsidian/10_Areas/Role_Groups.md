---
title: Role Groups
tags:
  - ai-project
  - structure
created: 2026-04-06
status: current
---

# 역할 그룹 정리

## 구조 원칙

- 분리는 프로젝트 단위로 한다.
- 관리는 역할 기준으로 한다.
- 코드 프로젝트와 데이터 폴더를 섞지 않는다.

## 역할 그룹

### `core`

실제 제품, 엔진, 런타임 본체를 두는 영역이다.

- [[Mellow_Link]]
- [[Mellow_Chat_Runtime]]
- [[Autonomous_Agent]]

### `pipelines`

추출, 가공, 학습 재료 생성, 검증 자동화를 위한 지원 파이프라인 영역이다.

- [[Pattern_Extraction_Pipeline]]

### `experiments`

제품 본체에 직접 포함되지 않는 실험, 탐색, 레드팀 자산을 보관한다.

- 현재 대표 예시: `experiments/redteam_outside_root`

### `data`

로그, 산출물, 런타임 데이터 저장 영역이다.

- `data/runtime`
- `data/outputs`
- `data/logs`

### `infra`

모델, 템플릿, 공용 기반 자원을 보관한다.

- `infra/models`
- `infra/templates`

## 현재 해석 포인트

- 사용자 관점의 중심은 `core/mellow_link`다.
- `pipelines`는 제품 본체가 아니라 지원 계층이다.
- `experiments`는 검증용이며, 현재 대표 제품 정의를 바꾸지 않는다.
- `data`와 `infra`는 제품이 아니라 기반 자원이다.
