# Refactoring Support Engine QA Question Pack

기준일: 2026-04-04  
상태: Operational  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

Phase 3의 `result/explanation`, `result/qa` 품질을 실제 질문 샘플로 빠르게 점검하기 위한 운영용 팩이다.  
이 문서는 질문 의도, 샘플별 추천 질문, audience 불변 조건을 함께 고정한다.

## 핵심 규칙

1. `audience`가 바뀌어도 fact는 바뀌면 안 된다.
- `recommended_strategy`
- `decision_type`
- `priority_score`
- `score_breakdown`
- `execution stage linkage`
- `citations`

2. `audience`가 바뀌면 달라져도 되는 것은 wording뿐이다.
- 문장 길이
- 강조 순서
- 설명 깊이

3. `result/qa`는 항상 grounded response여야 한다.
- `citations`가 있어야 한다.
- `referenced_sections`가 있어야 한다.
- grounding이 부족하면 `insufficient_grounding=true`여야 한다.

4. 첫 Phase 3 구현에서는 `delivery_mode`를 평가 항목에 넣지 않는다.

## 실행 순서

1. golden sample 또는 실제 프로젝트의 최신 결과를 준비한다.
2. 아래 질문 세트를 `POST /projects/{project_id}/result/qa`로 보낸다.
3. audience 불변 체크 질문은 같은 질문을 `developer`, `manager`, `client`로 반복한다.
4. 아래 기준으로 통과 여부를 확인한다.

## 공통 확인 기준

### A. Answer Quality
- 답변이 질문 intent와 맞는다.
- 새 판단을 만들지 않는다.
- 새 숫자나 새 고유명사를 만들지 않는다.

### B. Grounding Quality
- `citations`가 비어 있지 않다.
- `referenced_sections`가 intent와 맞다.
- 근거가 약하면 억지로 답하지 않는다.

### C. Audience Invariance
- 세 audience에서 `citations`가 동일하다.
- 세 audience에서 score/decision/stage title 같은 fact가 동일하다.
- 세 audience에서 wording만 달라진다.

## 공통 audience 불변 체크 질문

아래 3개 질문은 모든 샘플에 공통으로 권장한다.

1. `왜 이게 우선순위가 높아?`
- intent: `priority`
- audience: `developer`, `manager`, `client`
- 확인:
  - `priority_score` 동일
  - `score_breakdown` 관련 숫자 동일
  - `citations` 동일

2. `이 판단의 직접 근거는 뭐야?`
- intent: `evidence`
- audience: `developer`, `manager`, `client`
- 확인:
  - `citations` 동일
  - excerpt/locator 동일

3. `실행 단계는 어떻게 잡혀 있어?`
- intent: `execution`
- audience: `developer`, `manager`, `client`
- 확인:
  - stage count 동일
  - top stage title 동일
  - `citations` 동일

## Sample-Specific Question Sets

### 1. `00. rca_exception_case_01`
- focus: workflow narrative + redesign
- 질문
  - `왜 refactor가 아니라 redesign이야?`
  - `가장 큰 구조 문제는 뭐야?`
  - `첫 실행 단계가 workflow 관점에서 왜 필요한 거야?`
- 기대
  - `recommended_strategy=재설계 우선`
  - top decision type은 `redesign`
  - workflow/예외 처리 흐름 관련 rationale이 나와야 한다

### 2. `01. java_order_closure_case_01`
- focus: state transition + UI/data coupling
- 질문
  - `왜 이게 리팩터링 우선이야?`
  - `상태 전이 기준에서 어떤 근거가 잡혔어?`
  - `첫 단계에서 어떤 책임을 분리해야 해?`
- 기대
  - `recommended_strategy=리팩터링 우선`
  - top decision type은 `refactor`
  - 상태 전이 또는 UI/data coupling evidence가 연결돼야 한다

### 3. `02. python_claim_adjustment_case_01`
- focus: access-control narrative + redesign
- 질문
  - `권한 구조 때문에 왜 redesign이 필요한 거야?`
  - `이 판단의 직접 근거는 뭐야?`
  - `조직별 처리 범위가 어디서 확인됐어?`
- 기대
  - `recommended_strategy=재설계 우선`
  - access-control 성격의 rationale이 노출돼야 한다
  - evidence와 locator가 따라와야 한다

### 4. `04. amount_limit`
- focus: amount-threshold + low-scope refactor
- 질문
  - `왜 우선순위가 9야?`
  - `금액 기준 관련 직접 근거는 뭐야?`
  - `이건 왜 redesign이 아니라 refactor야?`
- 기대
  - `recommended_strategy=리팩터링 우선`
  - top priority score는 `9`
  - 한도/경계 조건 근거가 citation으로 연결돼야 한다

### 5. `01_success_full`
- focus: accounting extension + no false structural decision
- 질문
  - `이번 분석 범위는 어디까지야?`
  - `실행 계획은 어떻게 정리됐어?`
  - `구조 판단보다 회계 계산 검토가 왜 중심이야?`
- 기대
  - `decision_count=0`
  - accounting 중심 설명이 나와야 한다
  - 구조 decision을 억지로 만들어내면 안 된다
  - 세 번째 질문은 `insufficient_grounding=true`로 거절되는 것이 정상이다

## API Example

```http
POST /projects/{project_id}/result/qa
Content-Type: application/json

{
  "question": "왜 이게 우선순위가 높아?",
  "audience": "manager"
}
```

```http
GET /projects/{project_id}/result/explanation?audience=developer
```

## Smoke Script

실제 프로젝트에 질문 팩을 바로 태우려면 아래 스크립트를 사용한다.

- [run_result_qa_question_pack.ps1](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/scripts/run_result_qa_question_pack.ps1)

예시:

```powershell
pwsh -File C:\Users\Hyein\ClaudeAI\AI_Project\mellow_link\scripts\run_result_qa_question_pack.ps1 `
  -ProjectId proj_xxxxx `
  -Token <ACCESS_TOKEN> `
  -BaseUrl http://127.0.0.1:8000
```

golden sample에 맞는 상세 질문까지 같이 돌리려면 `-SampleName`을 추가한다.

```powershell
pwsh -File C:\Users\Hyein\ClaudeAI\AI_Project\mellow_link\scripts\run_result_qa_question_pack.ps1 `
  -ProjectId proj_xxxxx `
  -Token <ACCESS_TOKEN> `
  -BaseUrl http://127.0.0.1:8000 `
  -SampleName "01. java_order_closure_case_01"
```

## 저장 위치

- 실행용 질문 세트 JSON:
  [phase3_qa_question_pack.json](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/_templates/phase3_qa_question_pack.json)
- golden sample 기준:
  [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
