# Rebuild Assistant Workflow Template Contract

버전: 2026-03-29  
상태: Contract

추가 메모 (2026-04-03)

- 현재 workflow 포함 judgment template canonical source는
  [`mellow_link/services/refactoring_support_engine/decision_catalog.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)다.
- [`mellow_link/modules/rebuild_assistant/judgment_templates.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 유지한다.
- 아래 반영 대상 파일 목록은 당시 작업 계약 기준이고, 현재 구조 해석은 engine catalog를 우선한다.

## 목적

`workflow (승인형)` 판단 템플릿을 `rebuild_assistant`에 추가한다.

이번 작업의 범위는 아래로 제한한다.

- `workflow` detection 추가
- `workflow` 템플릿 등록
- `workflow` 전용 결과 문장 생성
- `state_transition` fallback 유지
- 최소 테스트 4건 추가

## 완료 조건

아래를 모두 만족해야 완료다.

1. `workflow`가 judgment template registry에 등록된다.
2. 승인 주체 / 단계 구조 / 의사결정 게이트 중 2개 이상이면 `workflow`로 판정된다.
3. 단순 상태 변경은 `workflow`가 아니라 `state_transition`으로 유지된다.
4. `workflow` 결과 문서에 아래 축이 드러난다.
   - 승인 트리거 조건
   - 승인 주체
   - 승인 단계 구조
   - 의사결정 분기 조건
   - 예외 처리 흐름
5. 아래 테스트가 통과한다.
   - 단일 승인형
   - 다단계 승인형
   - 예외 포함 승인형
   - state_transition fallback

## 금지 사항

- 기존 `state_transition`, `access_control`, `validation`, `query_filter`, `amount_threshold` 판정 회귀 금지
- 단순 상태 enum만으로 `workflow` 승격 금지
- 패턴 추출 자체를 AI에 위임 금지

## 구현 기준

### 판정 기준

아래 3개 중 최소 2개 이상 만족해야 `workflow`다.

1. 승인 주체 존재
2. 단계 구조 존재
3. 의사결정 게이트 존재

2개 미만이면 `state_transition`으로 fallback 한다.

### 출력 기준

`workflow` primary일 때 문서의 중심 축은 아래다.

- 승인 트리거 조건
- 승인 주체
- 승인 단계 구조
- 예외 흐름
- 상태 전이와의 관계

### 테스트 기준

테스트는 실제 `build_result()` 결과 기준으로 검증한다.

## 반영 대상 파일

- `mellow_link/services/refactoring_support_engine/decision_catalog.py`
- `mellow_link/modules/rebuild_assistant/judgment_templates.py` (compatibility re-export)
- `mellow_link/modules/rebuild_assistant/service.py`
- `mellow_link/tests/test_module_registry_and_runs.py`
- `mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md`
