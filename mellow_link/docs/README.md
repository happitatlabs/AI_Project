# Mellow-Link Docs

`mellow_link/docs`는 현재 활성 문서의 인덱스다.  
과거 복사본과 정리 대상 문서는 [`_backup`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/_backup)에 둔다.

현재 기준 핵심 제품은 `레거시 현대화 분석`이며, 기본 실행선은 아래와 같다.

`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant -> result package`

## 먼저 읽을 문서

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
- [PRODUCT_STRUCTURE_TEMPLATE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PRODUCT_STRUCTURE_TEMPLATE.md)
  - 새 분석형 제품을 붙일 때의 기준 구조
- [ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md)
  - 현재 산출물의 오분석 항목과 재테스트 통과 기준
- [REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REBUILD_ASSISTANT_RESULT_STATUS_2026-03-28.md)
  - 판단 템플릿 3종과 실샘플 최신 통과 상태, 남은 polish 항목
- [AI_AUGMENTATION_STRATEGY.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_AUGMENTATION_STRATEGY.md)
  - deterministic 분석 엔진과 AI 보정의 역할 경계, 투입 지점, 금지 원칙
- [mellow_link/modules/rebuild_assistant/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/README.md)
  - 대표 상품 실행 방식과 입력/출력 계약 요약
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
