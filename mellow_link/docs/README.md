# Mellow-Link Docs

`mellow_link/docs`는 현재 활성 문서의 인덱스다.  
과거 복사본과 정리 대상 문서는 [`_backup`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/_backup)에 둔다.

`rebuild_assistant` / `refactoring_support_engine` 구조의 source of truth는
[`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
`mellow_link/docs` 아래 문서는 제품 상태, 계약, 운영 맥락을 보조 설명한다.

현재 기준 핵심 제품은 상품명 `레거시 현대화 분석`이며, 제품 정의는 `레거시 시스템을 분석하고, 현대화 방향과 실행 가능한 조치를 제안하는 AI 도구`다.

현재 제품 단계는 아래와 같이 고정한다.

- 1단계: 분석 + 결과 패키지 (완료)
- 2단계: 조치 제안 + 비교 (부분 구현)
- 3단계: 실행 준비 (planned)
- 4단계: 실행/검증/승인/배포 (planned)
- 5단계: 운영/로그/감사 (planned)

현재 상태 구분은 아래와 같이 고정한다.

- current: 추천안, 분리 우선순위, 설계 선택지 비교, 실행 계획
- gap: 조치 제안, 변경 요약, Before 구조, After 구조
- planned: 실행/검증/승인/배포, 운영/로그/감사

결과 패키지는 아래 2개 그룹으로 해석한다.

[분석 결과]
- 진단
- 설계안
- 전환 초안

[결정 지원]
- 추천안
- 분리 우선순위
- 설계 선택지 비교
- 실행 계획

`execution_plan`은 자동 실행이 아니라 `실행 준비 계획`으로 해석한다.

기본 실행선은 아래와 같다.
`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant -> result package`

## 먼저 읽을 문서

문서 우선순위는 아래로 해석한다.

1. [DOCUMENT_DRIVEN_AI_EXECUTION_PIPELINE_RULES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/DOCUMENT_DRIVEN_AI_EXECUTION_PIPELINE_RULES.md)
2. [AI_AUGMENTATION_STRATEGY.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_AUGMENTATION_STRATEGY.md)
3. [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)
4. 상태 / 설명 / 제안 문서

`Contract` 문서가 없으면 실행하지 않는다.  
`rebuild_assistant` 관련 구조 변경 후에는 먼저 [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)를 갱신하고,
상태/샘플 변화가 있으면 [REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md)를 후속 갱신한다.

1. 구조/제품 기준
   - [AI_PROJECT_STRUCTURE_AND_SPEC.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_PROJECT_STRUCTURE_AND_SPEC.md)
   - [PRODUCT_STRUCTURE_TEMPLATE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PRODUCT_STRUCTURE_TEMPLATE.md)
2. 익명화/보안 경계
   - [ANONYMIZATION_MVP_STATUS.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANONYMIZATION_MVP_STATUS.md)
   - [PILOT_SECURITY_AND_OPERATIONS_NOTICE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PILOT_SECURITY_AND_OPERATIONS_NOTICE.md)
     - 고객 제출/설명용 문서
3. 대표 상품/흐름
   - [mellow_link/modules/rebuild_assistant/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/README.md)
   - [PILOT_CONTRACT_READINESS_PLAN.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PILOT_CONTRACT_READINESS_PLAN.md)
4. 시스템 기준
   - [SYSTEM_ARCHITECTURE_GUIDEBOOK.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/SYSTEM_ARCHITECTURE_GUIDEBOOK.md)
   - [TROUBLESHOOTING.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/TROUBLESHOOTING.md)

## 활성 문서

### 제품 / 구조

- [AI_PROJECT_STRUCTURE_AND_SPEC.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_PROJECT_STRUCTURE_AND_SPEC.md)
  - 현재 제품 구조, 디렉토리 구분, 대표 실행 흐름
- [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)
  - `rebuild_assistant` Phase 1 엔진 구조, authoritative payload, feature slice/diagnosis/decision 흐름의 기준 문서
- [PRODUCT_STRUCTURE_TEMPLATE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PRODUCT_STRUCTURE_TEMPLATE.md)
  - 새 분석형 제품을 붙일 때의 기준 구조
- [ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md)
  - 현재 산출물의 오분석 항목과 재테스트 통과 기준
- [REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md)
  - 상태/샘플/회귀 기록 문서
  - 엔진 구조와 payload source of truth로 사용하지 않는다
- [AI_AUGMENTATION_STRATEGY.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_AUGMENTATION_STRATEGY.md)
  - deterministic 분석 엔진과 AI 보정의 역할 경계, 투입 지점, 금지 원칙
- [DOCUMENT_DRIVEN_AI_EXECUTION_PIPELINE_RULES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/DOCUMENT_DRIVEN_AI_EXECUTION_PIPELINE_RULES.md)
  - Draft / Contract / Locked 기준과 문서 기반 실행 루프 운영 규칙
- [REBUILD_ASSISTANT_JUDGMENT_TEMPLATE_EXPANSION_CONTRACT_2026-03-29.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_JUDGMENT_TEMPLATE_EXPANSION_CONTRACT_2026-03-29.md)
  - `query_filter`, `amount_threshold` 1차 확장 작업용 Contract
- [REBUILD_ASSISTANT_PATTERN_SELECTION_CONTRACT_2026-03-29.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_PATTERN_SELECTION_CONTRACT_2026-03-29.md)
  - 패턴 후보 수집, 우선순위 선택, fallback, 디버깅 기준 Contract
- [REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md)
  - `structured_result` 위에 얹는 표현 전용 후처리 레이어 Contract
- [REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md)
  - 회계 JSON 입력, 계산 가능 여부, 환차손익 계산, 전표 검토 확장 Contract
- [REBUILD_ASSISTANT_REPORT_PURPOSE_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_REPORT_PURPOSE_CONTRACT_2026-03-30.md)
  - 보고서 목적 자동 생성, 회계 목적 우선, 질문 원문 비노출, 목적/결론 분리 Contract
- [REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_REFINEMENT_OUTPUT_CONTRACT_2026-03-30.md)
  - purpose-문서축 정렬, 단일 패턴 narrative 강제, 회계 하단 섹션 분리, 문장 조합 오류 보정 Contract
- [REBUILD_ASSISTANT_POLISH_UI_RENDERING_CONTRACT_2026-03-30.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_POLISH_UI_RENDERING_CONTRACT_2026-03-30.md)
  - 결과 패키지 UI에서 audience / delivery mode별 회계 표현 변형본 선택 렌더링 Contract
- [mellow_link/modules/rebuild_assistant/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/README.md)
  - 대표 상품 실행 방식과 입력/출력 계약, 결정 지원 필드 요약
- [REBUILD_ASSISTANT_PROPOSAL.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_PROPOSAL.md)
  - 초기 제안서 성격 문서
  - 현재 구현 기준은 모듈 README와 익명화 상태 문서를 우선 본다

### 익명화 / 보안

- [ANONYMIZATION_MVP_STATUS.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANONYMIZATION_MVP_STATUS.md)
  - 익명화 MVP 범위, SafeAnalysisBundle, canonical-only 구조 추출 규칙
- [PILOT_SECURITY_AND_OPERATIONS_NOTICE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PILOT_SECURITY_AND_OPERATIONS_NOTICE.md)
  - 고객 설명용 현재 보안/저장/반출 경계
- [SECURITY_HOTFIX_2026-02-24.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/SECURITY_HOTFIX_2026-02-24.md)
  - 별도 보안 핫픽스 이력

### 제품 운영 / 계획

- [PILOT_CONTRACT_READINESS_PLAN.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PILOT_CONTRACT_READINESS_PLAN.md)
  - 파일럿 계약 준비 상태와 남은 작업
- [PYTEST_REPRODUCE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PYTEST_REPRODUCE.md)
  - 회귀 테스트 재현 방법
- [KNOWN_ISSUES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/KNOWN_ISSUES.md)
  - 현재 알려진 이슈

### 시스템 / 참고

- [SYSTEM_ARCHITECTURE_GUIDEBOOK.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/SYSTEM_ARCHITECTURE_GUIDEBOOK.md)
- [system_map.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/system_map.md)
- [TECHNICAL_SPECIFICATION_v1.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/TECHNICAL_SPECIFICATION_v1.md)

## 비활성 또는 역사 문서 해석 기준

- `_backup/` 아래 문서는 현재 활성 기준이 아니다.
- `REBUILD_ASSISTANT_PROPOSAL.md`는 최초 제안 문서다.
- Runtime, dev/operator, 자율 에이전트 관련 문서는 현재 상용 1차 UX보다 범위가 넓을 수 있다.
- 제품 판단이 필요한 경우 다음 우선순위로 해석한다.
  1. 코드
  2. 모듈 README
  3. 익명화 상태 문서
  4. 본 인덱스
