# Refactoring Support Engine Real-Project Validation Template

기준일: 2026-04-04  
상태: Template  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

실제 프로젝트 1~2건에 대해 `structural_judgment`와 `decision_summary`가 실무적으로 타당한지 검증한다.  
이번 템플릿은 코어 엔진 수정이 아니라 `taxonomy 노출`, `판단 타당성`, `설명 오염 여부`를 확인하기 위한 기록 양식이다.

## 적용 범위

- 권장 프로젝트 수: 2건
- 권장 구성:
  - `refactor 중심` 프로젝트 1건
  - `redesign 중심` 프로젝트 1건

## 프로젝트 기록

### 기본 정보
- `project_id`:
- `project_name`:
- `review_date`:
- `reviewer`:
- `project_type`: `refactor-centered | redesign-centered`

### Core Judgment
- `structural_judgment`:
- `recommended_strategy`:
- `top_decision_type`:
- `top_priority_score`:

### Reviewer Verdict
- `reviewer_verdict`: `valid | partially_valid | invalid`
- `taxonomy_confusion`: `none | minor | major`
- `correction_required`: `yes | no`

## 필수 검증 체크리스트

### 1. 구조 판단 타당성
- `structural_judgment`가 실제 프로젝트 구조 문제와 일치하는가
- `recommended_strategy`가 실무적으로 수용 가능한가
- top decision 1~3개가 실제 개선 우선순위와 크게 어긋나지 않는가

### 2. 근거 연결 타당성
- `decision -> issue -> evidence -> score_breakdown` 연결이 납득 가능한가
- `score_breakdown.final_score`가 과도하거나 과소하지 않은가
- `explainability`가 score와 같은 판단을 설명하는가

### 3. 실행 가능성
- top `execution_stage`가 실제 착수 가능한가
- 첫 단계 task가 모호하지 않은가
- 리스크와 verification checkpoint가 누락되지 않았는가

### 4. taxonomy 분리 타당성
- `narrative_axis`가 설명 보조로만 동작하는가
- `narrative_axis`가 구조 판단을 오염시키지 않는가
- `primary_judgment` 없이도 reviewer가 결과를 이해할 수 있는가

### 5. explanation / Q&A 품질
- audience가 달라도 fact / score / citation이 바뀌지 않는가
- Q&A가 grounding 부족 시 억지로 답하지 않는가
- explanation surface가 `structural_judgment`를 중심으로 보여주는가

## 기록 포맷

### Confirmed Observation
- 자산 기반 사실:
- detector / issue 사실:
- decision linkage 사실:

### Root Cause Candidate
- contamination 가능 원인:
- wrapper wording contamination 여부:
- synthetic migration trigger 여부:
- asset-absent decision 여부:
- domain-anchor spillover 여부:

### Follow-up Check
- 추가 캡처 필요 항목:
- 재검증 필요 항목:
- 비교 실행 필요 항목:

### Enforcement Record
- `synthetic_signal_detected`:
- `synthetic_signal_source`: `result.extensions.decision_governance | decision_summary_inference`
- DecisionEngine 1차 가드 확인:
- ResultPackager 2차 검증 확인:
- Validation 기록 완료 여부:

### Verdict Summary
- `valid`: 핵심 판단과 전략이 실무적으로 수용 가능
- `partially_valid`: 방향은 맞지만 taxonomy/표현/세부 stage 보정 필요
- `invalid`: 판단 자체가 실제 프로젝트와 어긋남

### Confusion Notes
- 사용자가 헷갈린 taxonomy:
- 혼란 원인:
- 필요한 라벨/설명 수정:

### Correction Notes
- 수정 필요 항목:
- 수정 유형: `labeling | explanation_only | validation_gap | product_gap`
- 코어 엔진 수정 필요 여부: `yes | no`

## 완료 기준

아래 조건을 모두 만족하면 validation 1차 완료로 본다.

1. 실제 프로젝트 1~2건 기록 완료
2. `structural_judgment`와 `recommended_strategy`에 대한 reviewer verdict 확보
3. taxonomy confusion 여부 기록
4. UI 라벨 수정 필요 여부 도출
5. 코어 엔진 수정 없이 surface 조정으로 해결 가능한 범위 분리
