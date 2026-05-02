# Product Structure Template

기준일: 2026-03-25  
목적: `mellow_link`를 제품 중심으로 이해하고, 이후 새 분석형 제품을 같은 규칙으로 붙일 수 있도록 기준 구조를 고정한다.

## 1. 대표 제품 구조

```text
mellow_link
├─ core
│  └─ 공통 실행 엔진, 오케스트레이션, 상태 제어
├─ services
│  ├─ LLM, 문서 처리, RAG, 분석 지원 서비스
│  └─ anonymization
│     └─ 공통 보안/전처리 서브시스템
├─ infra
│  └─ DB, 인증, run 추적, 이벤트 저장
├─ routers
│  ├─ system.py
│  ├─ projects.py
│  └─ 기타 제품 API 라우트
├─ static
│  ├─ projects_create.html
│  ├─ user_console.html
│  ├─ project_result.html
│  └─ 기타 제품 UI
├─ modules
│  ├─ rebuild_assistant
│  │  └─ 대표 시나리오/기능: 레거시 현대화 분석
│  ├─ sql_analytics
│  ├─ research_assistant
│  └─ ai_workflow_console
├─ config
│  └─ 제품 설정 로딩
└─ utils
   └─ 경량 공통 유틸
```

## 2. 대표 상품 기준 배치

현재 상용 1차 대표 상품은 `멜로우 링크 판맥`이며, 영문명은 `MellowLink Senseframe`이다. 제품 정의는 `레거시 시스템의 구조, 흐름, 판단 근거를 분석하고 실행 가능한 현대화 방향으로 정리하는 웹 기반 판단 지원 프로그램`이다. `레거시 현대화 분석`은 대표 분석 시나리오/기능 설명으로 유지한다.

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

```text
modules/rebuild_assistant
├─ api.py
│  └─ 프로젝트 시작 / safe bundle 기반 run 연결
├─ runner.py
│  └─ safe bundle 기반 분석 실행 흐름
├─ service.py
│  └─ 기능 분류, 업무 규칙 추출, 분석 결과와 결정 지원 초안 생성
├─ schemas.py
│  └─ 입력/출력 계약
├─ manifest.py
│  └─ 모듈 등록 정보
└─ README.md
   └─ 모듈 설명
```

현재 `rebuild_assistant`의 기본 공개 실행선은 raw asset 직접 실행이 아니라 아래 흐름이다.

`project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant`

## 3. 화면 기준 배치

상용 제품의 대표 화면 3개는 아래 파일을 기준으로 유지한다.

```text
static
├─ projects_create.html   # 새 프로젝트
├─ user_console.html      # 분석 워크스페이스
└─ project_result.html    # 결과 패키지
```

현재 화면 구조는 아래처럼 해석한다.

- `projects_create.html`
  - 프로젝트 생성
- `user_console.html`
  - 분석 워크스페이스
  - 입력 정리
  - 자산 분석
  - 설계 초안
  - 조치 제안
  - 현재 상태: `조치 제안`은 gap 항목이다.
- `project_result.html`
  - 결과 패키지

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

- 실행/검증 화면
  - planned
- 로그/감사 화면
  - planned

규칙:

- 새 대표 화면은 먼저 `static/`에 둔다.
- 화면 전용 API는 `routers/`에 둔다.
- 화면이 특정 상품 전용이면 해당 상품 모듈 또는 `routers/projects.py`에서 연결한다.

## 4. 새 분석형 제품 추가 템플릿

새 분석형 제품은 아래 구조를 기본 템플릿으로 사용한다.

```text
modules/<new_product>
├─ api.py
├─ runner.py
├─ service.py
├─ schemas.py
├─ manifest.py
├─ README.md
└─ static
   └─ index.html   # 필요 시 모듈 전용 시작 화면
```

역할 규칙:

- `api.py`
  - 외부 요청을 입력 스키마로 받고 run 시작 함수에 연결한다.
- `runner.py`
  - run 이벤트, 단계 진행, 최종 payload 조립을 담당한다.
- `service.py`
  - 실제 분석 로직, 규칙 추출, 결과 생성 로직을 둔다.
- `schemas.py`
  - 입력/출력 모델과 구조화 결과 계약을 둔다.
- `manifest.py`
  - `module_id`, `name`, `description`, `run_kind`, `start_path`를 등록한다.
- `README.md`
  - 목적, 입력, 출력, 테스트 범위를 적는다.

## 5. 새 제품을 붙일 때 경로 선택 규칙

### A. 공통 기능이면

아래 위치를 우선 본다.

- `core/`
- `services/`
- `infra/`
- `utils/`

예시:

- 공통 분석 파이프라인
- 공통 결과 패키지 포맷터
- 공통 권한/감사 처리
- 공통 익명화/마스킹/반출 통제 서비스

### B. 특정 상품 전용이면

아래 위치를 우선 본다.

- `modules/<product>/`
- `static/`
- `routers/<product>.py` 또는 관련 라우터

예시:

- 상품 전용 입력 폼
- 상품 전용 결과 섹션
- 상품 전용 분류 로직
- 상품 전용 추천 방향

## 6. 권장 추가 순서

새 분석형 제품을 붙일 때는 아래 순서를 권장한다.

1. 공통 서비스가 필요한지 먼저 판정
2. 필요하면 `services/`에 공통 계층 추가
3. `modules/<new_product>/schemas.py`
4. `modules/<new_product>/service.py`
5. `modules/<new_product>/runner.py`
6. `modules/<new_product>/api.py`
7. `modules/<new_product>/manifest.py`
8. `static/` 또는 모듈 전용 UI
9. `routers/` 연결
10. 테스트 추가

## 7. 익명화 공통 계층 배치 기준

익명화 처리 MVP 같은 기능은 `utils/`가 아니라 `services/`에 둔다.

이유:

- 저장 경로와 접근 통제를 가진 상태 있는 서비스이기 때문
- 여러 제품이 재사용해야 하는 공통 전처리 계층이기 때문
- 단순 문자열 치환이 아니라 canonical source, structure, export contract를 관리하기 때문

현재 기준 예시는 아래와 같다.

```text
services/anonymization
├─ service.py            # facade only
├─ storage.py            # storage root, 저장, 경로 해석
├─ tokenizer.py          # 토큰 분리
├─ mapper.py             # 익명 식별자 매핑
├─ structure_extractor.py# canonical source 기준 구조 추출
├─ masking_policy.py     # 레벨별 정책 적용
├─ bundle_builder.py     # SafeAnalysisBundle 조립
└─ export_service.py     # PublicExportBundle 생성
```

## 8. 제품 관점 요약

현재 기준 제품 구조는 아래처럼 본다.

```text
mellow_link
├─ 공통 엔진
├─ 대표 상품: 멜로우 링크 판맥
├─ 대표 시나리오/기능: 레거시 현대화 분석
├─ 다른 분석형 제품 후보
├─ 제품 API
└─ 제품 UI
```

따라서 이후 새 기능을 붙일 때는 먼저 아래 둘 중 하나를 결정한다.

- 공통 엔진 확장인가
- 새 분석형 제품 추가인가

이 결정만 먼저 하면 폴더 위치가 대부분 자동으로 정리된다.
