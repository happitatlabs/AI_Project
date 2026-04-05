# AI_Project Structure And Spec

기준일: 2026-04-01  
해석 기준: 현재 상용 1차 제품은 `mellow_link`의 상품 `레거시 현대화 분석`이며, 제품 정의는 `레거시 시스템을 분석하고, 현대화 방향과 실행 가능한 조치를 제안하는 AI 도구`다.

## 1. 현재 제품 기준 요약

- 대표 상품명: `레거시 현대화 분석`
- 제품 정의: `레거시 시스템을 분석하고, 현대화 방향과 실행 가능한 조치를 제안하는 AI 도구`
- 대표 모듈: [`modules/rebuild_assistant`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant)
- 대표 사용자 흐름:
  1. 새 프로젝트
  2. 분석 워크스페이스
  3. 결과 패키지

현재 공개 실행선은 아래로 고정한다.

`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant -> result package`

## 2. 제품 단계 아키텍처

- 1단계: 분석 + 결과 패키지 (완료)
- 2단계: 조치 제안 + 비교 (부분 구현)
- 3단계: 실행 준비 (planned)
- 4단계: 실행/검증/승인/배포 (planned)
- 5단계: 운영/로그/감사 (planned)

현재 상태 구분은 아래와 같이 고정한다.

- current: 추천안, 분리 우선순위, 설계 선택지 비교, 실행 계획
- gap: 조치 제안, 변경 요약, Before 구조, After 구조
- planned: 실행/검증/승인/배포, 운영/로그/감사

## 3. 현재 디렉토리 구조

```text
AI_Project
├─ mellow_link
│  ├─ core
│  ├─ services
│  │  └─ anonymization
│  ├─ infra
│  ├─ routers
│  ├─ static
│  ├─ modules
│  │  ├─ rebuild_assistant
│  │  ├─ sql_analytics
│  │  ├─ research_assistant
│  │  └─ ai_workflow_console
│  ├─ config
│  └─ utils
├─ autonomous_agent
├─ mellow_chat_runtime
├─ mellow_chat_runtime_data
└─ Open-LLM-VTuber
```

제품 우선순위 해석:

- `mellow_link`
  - 현재 팔고 있는 제품 본체
- `autonomous_agent`
  - 2차 이후 내부 자동화 계층
- `mellow_chat_runtime`
  - 별도 runtime 계층
- `Open-LLM-VTuber`
  - 선택형 외부 인터페이스

## 4. mellow_link 내부 구조

```text
mellow_link
├─ core
│  └─ 공통 실행 엔진, 오케스트레이션, 정책, 상태 제어
├─ services
│  ├─ llm/doc/rag 등 공통 서비스
│  └─ anonymization
│     └─ 공통 보안/전처리 서브시스템
├─ infra
│  └─ DB, 인증, run 추적, 이벤트 저장
├─ routers
│  ├─ system.py
│  ├─ projects.py
│  └─ 기타 API 라우터
├─ static
│  ├─ projects_create.html
│  ├─ user_console.html
│  └─ project_result.html
├─ modules
│  ├─ rebuild_assistant
│  ├─ sql_analytics
│  ├─ research_assistant
│  └─ ai_workflow_console
├─ config
└─ utils
```

## 5. 대표 상품 구조

```text
modules/rebuild_assistant
├─ api.py
├─ runner.py
├─ service.py
├─ schemas.py
├─ manifest.py
├─ compat.py
├─ static
│  └─ index.html
└─ README.md
```

해석 기준:

- `api.py`
  - project-scoped safe bundle 실행 연결
- `runner.py`
  - safe bundle 기반 run 실행
- `service.py`
  - 기능 분류, 규칙 추출, 분석 결과와 결정 지원 초안 생성
- `schemas.py`
  - 구조화 결과 및 safe bundle 입력 계약
- `compat.py`
  - migration-only raw compatibility path
  - 공개 실행선 아님

## 6. 익명화 MVP 구조

```text
services/anonymization
├─ schemas.py
├─ service.py
├─ storage.py
├─ tokenizer.py
├─ mapper.py
├─ structure_extractor.py
├─ masking_levels.py
├─ masking_policy.py
├─ bundle_builder.py
└─ export_service.py
```

고정 규칙:

- canonical source는 익명화 완료본이다.
- 구조 추출은 canonical source 기준으로만 수행한다.
- `rebuild_assistant`는 `SafeAnalysisBundle`만 소비한다.
- original content/path, mapping은 외부 응답에 포함되지 않는다.
- storage root는 `ANONYMIZATION_STORAGE_ROOT` 설정으로 관리한다.

## 7. 현재 사용자 동선

주요 사용자 라우트:

- `/`
- `/ui`
- `/projects/create`
- `/projects/{project_id}`
- `/projects/{project_id}/result`

사용자에게 숨기는 정보:

- `run_id`
- `trace_id`
- `runtime_impl`
- `model_tier`

운영/개발 콘솔은 유지하되 일반 사용자 홈/메뉴에서는 노출하지 않는다.

## 8. 현재 결과 패키지 계약

결과 패키지는 아래 2개 그룹으로 해석한다.
실제 UI는 해당 그룹이 명시적으로 나뉘지 않고 혼합된 형태로 배치된다.
이 구조는 UI 구조가 아니라 결과 해석 모델이다.

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

stage 2 gap 산출물은 아래와 같다.

- 조치 제안
조치 제안은 변경 대상, 변경 방식, 영향 범위, 예상 효과, 리스크 단위로 구성된다.
- 변경 요약
- Before 구조
- After 구조

현재 구현은 위 2개 그룹을 더 세분화해 `핵심 결론`, `추천 방향`, `핵심 업무 규칙`, `즉시 결정 필요`, `유지해야 할 계약`, `확인 필요 항목`, `리스크`, `부록`을 함께 제공한다.

`structured_result` 일부가 비어 있어도 가능한 필드만 렌더링하고, 누락 구간은 `결과 생성 중` 또는 `데이터 없음`으로 표시한다.

내보내기:

- 웹 뷰
- Markdown 다운로드
- 브라우저 PDF

## 9. 문서 해석 우선순위

현재 구조 판단이 필요할 때는 아래 우선순위로 해석한다.

1. 코드
2. [`modules/rebuild_assistant/README.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/README.md)
3. [ANONYMIZATION_MVP_STATUS.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANONYMIZATION_MVP_STATUS.md)
4. 이 문서

proposal 성격 문서나 backup 문서는 현재 구현보다 우선하지 않는다.
