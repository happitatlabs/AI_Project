# Refactoring Support Engine Secondary Migration Surface Rules

기준일: 2026-04-05  
상태: Locked  
기준 문서: [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

이 문서는 `secondary migration_consideration`이 존재할 때 UI와 explanation surface에서 어떻게 라벨링할지 고정한다.  
핵심 원칙은 아래와 같다.

- core judgment는 항상 `structural_judgment`와 `decision_summary.recommended_strategy`가 대표한다.
- `secondary migration_consideration`은 core judgment를 덮어쓰면 안 된다.
- synthetic 또는 asset-absent migration은 기본 surface에서 숨긴다.

## 정의

`secondary migration_consideration`은 아래 조건을 모두 만족하는 decision이다.

- `decision_type == "migration_consideration"`
- top decision이 아니다
- `structural_judgment != "migration_consideration"`
- `recommended_strategy != "마이그레이션 고려"`

## Surface 계층

### 1. Core Judgment Surface
- 카드: `구조 판단`
- 카드: `권장 전략`
- 카드: `판단 근거`
- 여기에는 secondary migration을 넣지 않는다.

허용 항목:
- `structural_judgment`
- `recommended_strategy`
- top `decision_type`
- top `score_breakdown`
- top evidence linkage

금지 항목:
- secondary migration badge
- migration 강조 색상
- migration headline
- migration을 top recommendation처럼 보이게 하는 카피

### 2. Supporting Decision Surface
- 위치: `추가 고려사항` 또는 `보조 판단`
- 표기 원칙:
  - 기본값은 접힘 상태
  - core 카드 밖에서만 노출
  - 문구는 약한 수준으로 제한

권장 라벨:
- `보조 고려사항: 단계적 전환 검토`
- `추가 검토: 전환 영향 범위 확인`

금지 라벨:
- `권장 전환`
- `전환 필요`
- `마이그레이션 우선`

### 3. Hidden / Validation Surface

아래 조건이면 기본 UI에서 숨긴다.

- `synthetic_signal_detected == true`
- `issue_ids == []`
- `evidence_ids == []`
- validation 또는 governance rule에서 contamination으로 분류됨

이 경우 노출 위치:
- validation 문서
- debug JSON
- internal reviewer panel

## 라벨링 규칙

### Rule-01. Core Non-Override
- top/core judgment가 `refactor` 또는 `observation_only`이면 secondary migration은 core label을 바꾸지 않는다.

### Rule-02. Weak Surface Only
- secondary migration이 legitimate하더라도 기본 surface에서는 `보조 고려사항` 수준으로만 노출한다.

### Rule-03. No Strategy Mutation
- secondary migration은 `recommended_strategy`를 바꾸지 않는다.

### Rule-04. No Badge Escalation
- secondary migration은 headline, title badge, summary card primary chip으로 쓰지 않는다.

### Rule-05. Contamination Hide
- `synthetic_signal_detected=true` 또는 asset-absent 조건이면 기본 UI에서 숨기고 validation/debug에서만 기록한다.

## API 노출 규칙

### `/result`
- raw canonical + compatibility payload를 유지한다.
- secondary migration decision은 `decision_summary.decisions`에 남을 수 있다.

### `/result/explanation`
- `taxonomy_view.core_judgment`에는 반영하지 않는다.
- full decision diff는 노출하지 않는다.
- 필요하면 `review_diff_preview` 또는 `section_views` 보조 note로만 약하게 노출한다.
- `secondary migration_consideration`은 additive note로만 넣는다.

권장 additive 필드 예시:
- `supplementary_considerations[]`
  - `kind: migration_consideration`
  - `label: 보조 고려사항: 단계적 전환 검토`
  - `decision_id`
  - `evidence_ids`

## 운영 메모

- 이번 규칙의 목적은 migration decision을 숨기는 것이 아니라 core judgment 계층을 보호하는 것이다.
- `secondary migration_consideration`이 있더라도 core 판단은 `structural_judgment`가 대표한다.
- contamination으로 판정된 migration은 default surface에 남겨두지 않는다.
