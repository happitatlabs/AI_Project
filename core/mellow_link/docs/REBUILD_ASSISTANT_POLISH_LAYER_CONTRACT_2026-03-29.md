# Rebuild Assistant Polish Layer Contract

기준일: 2026-03-29  
상태: Contract  
대상: `mellow_link/modules/rebuild_assistant`

2026-04-03 정합성 메모:

- 현재 엔진 구조와 authoritative payload 기준 문서는
  [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
- 이 문서는 `structured_result` 이후 `polish_bundle` 표현 후처리 계약만 다룬다.
- 구조 분석, 진단, 의사결정, 개선안 생성 규칙은 이 문서가 아니라 엔진 기준 문서를 따른다.

## 1. 목적

안정화된 `structured_result` 위에 표현 전용 후처리 레이어를 추가한다.

이 레이어의 목적은 아래 3가지를 분리해서 제공하는 것이다.

- 문장 polish
- audience별 요약 변형
- delivery mode별 납품 톤 변환

핵심 원칙은 `판단 불변`이다.

## 2. 판단 불변 원칙

아래 값은 후처리 레이어에서 변경하지 않는다.

- `primary_judgment`
- `template_judgment`
- `structural_judgment`
- `narrative_axis`
- `grounded_business_rules`
- `retained_contracts`
- `recommended_option`
- `execution_plan`
- 수치, 상태값, 코드명, 역할명, 경계값

원문 `structured_result`는 그대로 유지하고, 보정 결과는 별도 번들로 관리한다.

## 3. 후처리 3단계 구조

```text
structured_result
  -> sentence polish
  -> audience summary transform
  -> delivery tone rewrite
  -> polish bundle
```

### 3.1 sentence polish

포함:

- 중복 토큰 제거
- 조사 보정
- 반복 표현 압축
- 패턴 순도 훼손 표현 경고
  - 경고 축은 `primary_judgment`가 아니라 `narrative_axis`를 우선 사용한다.
  - `narrative_axis`가 없으면 `template_judgment`, 그 다음 `primary_judgment`로 fallback한다.

금지:

- 사실 삭제
- 숫자/코드명 일반화
- 패턴 변경

### 3.2 audience summary transform

기본 audience:

- `developer`
- `manager`
- `client`

목표:

- 같은 사실을 유지한 채 역할별 강조 섹션만 다르게 제공

### 3.3 delivery tone rewrite

기본 delivery mode:

- `internal_review`
- `client_report`
- `proposal_appendix`

목표:

- 보고서/부록/내부 검토에 맞는 문장 톤 제공
- 사실은 동일하게 유지

## 4. 데이터 구조

후처리 결과는 아래 구조를 갖는다.

- `primary_judgment`
- `template_judgment`
- `structural_judgment`
- `narrative_axis`
- `feature_signal_mode`
- `original_result`
- `polished_sections`
- `preserved_facts`
- `warnings`

각 섹션은 아래를 가진다.

- `section_key`
- `title`
- `original_text`
- `polished_text`
- `audience_variants`
- `delivery_variants`

## 5. 구현 경계

권장 위치:

- `mellow_link/modules/rebuild_assistant/postprocess/`

구성:

- `schemas.py`
- `rules.py`
- `audience.py`
- `delivery.py`
- `service.py`

기본 구현은 deterministic rule 기반으로 한다.

## 6. AI 재서술 훅

AI 재서술은 optional hook로만 설계한다.

- 기본값: `use_ai_rewrite=False`
- 입력은 `structured_result` 전체가 아니라 deterministic explanation block으로 제한한다.
- schema 검증 필수
- preserved facts 누락 금지
- deterministic 결과와 충돌 시 deterministic 우선

AI 재서술 입력 블록은 아래를 포함해야 한다.

- `block_id`
- `original_text`
- `critical_facts`
- `decision_driving_evidence`
- `locked_fields`

`locked_fields`는 최소 아래를 포함한다.

- `recommended_strategy`
- `decision_type`
- `priority_score`
- `score_breakdown`

Narrative Guard Contract:

- `Narrative must:`
  - `only rephrase existing facts`
  - `preserve all critical facts present in the input block`
  - `not introduce new claims`
  - `not change priority or recommendation`
  - `not generalize beyond given evidence`
  - `not omit decision-driving evidence`
  - `not merge distinct facts into ambiguous statements`
- `If validation fails:`
  - `fallback: deterministic explanation block`

validator는 아래를 실패로 본다.

- `critical_facts` coverage 누락
- `decision_driving_evidence` coverage 누락
- `locked_fields` 값 변경
- 입력 블록에 없는 신규 주장 추가
- evidence를 벗어난 일반화
- 서로 다른 사실을 하나의 애매한 문장으로 병합한 경우

실패 시 AI 결과는 버리고, 입력 deterministic explanation block을 그대로 사용한다.

## 7. 테스트 기준

필수 통과 조건:

- 원문 불변성 유지
- 중복 토큰/조사 오류 보정
- audience variant 3종 생성
- delivery mode 3종 생성
- 패턴 순도 유지
- `critical_facts` coverage 100%
- `decision_driving_evidence` coverage 100%
- `locked_fields` 무변경
- unsupported claim 0건
- ambiguous fact merge 0건

## 8. 금지 사항

- `structured_result` 원문 덮어쓰기
- 판단값 변경
- AI 재서술만 믿고 schema 검증 생략
- 표현 polish를 이유로 근거 삭제
- 표현 polish를 이유로 decision-driving evidence 삭제
- 표현 polish를 이유로 distinct fact를 뭉개기
- evidence 밖 일반화
- 본체 판단 엔진 수정
