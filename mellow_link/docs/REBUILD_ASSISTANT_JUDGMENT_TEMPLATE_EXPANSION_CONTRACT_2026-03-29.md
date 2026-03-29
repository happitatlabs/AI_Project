# Rebuild Assistant Judgment Template Expansion Contract

기준일: 2026-03-29  
상태: Contract  
범위: `rebuild_assistant` 판단 템플릿에 `조회/필터형`, `금액/한도형` 2종을 1차로 추가

## 1. 작업 목표

현재 1차 판단 템플릿 `state_transition`, `access_control`, `validation`에 더해 아래 2개를 추가한다.

1. `조회/필터형`
2. `금액/한도형`

이번 작업의 목적은 새 템플릿을 기존 deterministic 판단 구조에 안전하게 넣고, 결과 패키지 생성에서 템플릿 조합을 활용할 수 있는 기반을 만드는 것이다.

## 2. 현재 상태

- 기존 판단 템플릿:
  - `state_transition`
  - `access_control`
  - `validation`
- 기존 feature mode:
  - `status_permissions`
  - `search_filters`
  - `save_validation`
- 현재 `search_filters`는 사용자용 설명과 일부 feature mode로는 쓰이지만, 독립 판단 템플릿으로는 승격되지 않았다.
- 금액/한도 규칙은 `validation` 또는 `access_control` 보조 신호로만 일부 반영된다.

## 3. 이번 범위

이번 Contract에서 수정하는 대상은 아래로 제한한다.

- [`mellow_link/modules/rebuild_assistant/judgment_templates.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)
- [`mellow_link/modules/rebuild_assistant/schemas.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/schemas.py)
- [`mellow_link/modules/rebuild_assistant/service.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/service.py)
- [`mellow_link/tests/test_module_registry_and_runs.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_module_registry_and_runs.py)
- 필요 시 [`mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md)

## 4. 완료 조건

아래 항목이 충족되면 완료로 본다.

### 4.1 조회/필터형

- 판단 템플릿 레지스트리에 `query_filter` 또는 동등한 ID로 추가
- `search_filters` 신호가 강한 샘플에서 적용 가능
- core questions, retained contract candidates, decision patterns, risk patterns, priority defaults, execution defaults를 가짐

### 4.2 금액/한도형

- 판단 템플릿 레지스트리에 `amount_threshold` 또는 동등한 ID로 추가
- 금액 한도/threshold 신호가 강한 샘플에서 적용 가능
- core questions, retained contract candidates, decision patterns, risk patterns, priority defaults, execution defaults를 가짐

### 4.3 엔진 반영

- `AppliedJudgmentTemplate` 계산에서 새 템플릿 2종이 반영됨
- 추천안 / 우선순위 / 실행 계획 생성 로직이 새 템플릿을 처리함
- 기존 `state_transition`, `access_control`, `validation` 회귀가 깨지지 않음

### 4.4 테스트

- 조회/필터형 샘플이 새 템플릿으로 적용되는 테스트
- 금액/한도형 샘플이 새 템플릿으로 적용되는 테스트
- 기존 3개 템플릿 회귀 테스트 통과

## 5. 금지 사항

- 기존 판단 템플릿 3종의 의미를 바꾸지 않는다.
- 패턴 추출을 AI에 위임하지 않는다.
- 문장 polish 범위까지 확장하지 않는다.
- `approval(workflow)` 템플릿은 이번 범위에 포함하지 않는다.

## 6. 산출물 형태

- 코드 변경
- 회귀 테스트 추가
- 상태 문서 갱신

## 7. 검증 기준

최소 검증은 아래를 사용한다.

```text
pytest -q mellow_link/tests/test_module_registry_and_runs.py
```

필요 시 전체 회귀까지 확장한다.
