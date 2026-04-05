# AI_Project

AI_Project는 제품 본체(`core`), 지원 파이프라인(`pipelines`), 실험(`experiments`), 데이터(`data`), 기반 자원(`infra`)을 역할 기준으로 분리해 관리하는 작업 루트다.

핵심 원칙:
- 분리는 프로젝트 단위로 하고, 관리는 역할 기준으로 한다.
- 코드 프로젝트와 데이터 폴더를 섞지 않는다.
- 기능 구현보다 역할 분류와 구조 문서화를 먼저 한다.

## 역할 그룹

- `core`
  - 실제 제품/엔진/런타임 본체
  - 현재: [`mellow_link`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link), [`mellow_chat_runtime`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_chat_runtime), [`autonomous_agent`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/autonomous_agent)
- `pipelines`
  - 학습 재료 생성, 추출, 가공, 검증 자동화용 파이프라인
  - 현재: [`pattern_extraction_pipeline`](/C:/Users/Hyein/ClaudeAI/AI_Project/pipelines/pattern_extraction_pipeline)
- `experiments`
  - 제품 본체에 직접 포함되지 않은 실험/탐색/레드팀 자산
  - 현재: [`redteam_outside_root`](/C:/Users/Hyein/ClaudeAI/AI_Project/experiments/redteam_outside_root)
- `data`
  - 로그, 산출물, 런타임 데이터
  - 현재: [`data/runtime`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/runtime), [`data/outputs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/outputs), [`data/logs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/logs)
- `infra`
  - 모델, 템플릿, 공용 기반 자원
  - 현재: [`infra/models`](/C:/Users/Hyein/ClaudeAI/AI_Project/infra/models), [`infra/templates`](/C:/Users/Hyein/ClaudeAI/AI_Project/infra/templates)

## 현재 구조

```text
AI_Project/
├─ core/
│  ├─ mellow_link
│  ├─ mellow_chat_runtime
│  └─ autonomous_agent
├─ pipelines/
│  └─ pattern_extraction_pipeline
├─ experiments/
│  └─ redteam_outside_root
├─ data/
│  ├─ runtime/
│  │  ├─ anonymization
│  │  └─ mellow_chat_runtime_data
│  ├─ outputs/
│  └─ logs/
├─ infra/
│  ├─ models/
│  └─ templates/
├─ mellow_link/  # 호환 shim, 실제 프로젝트 루트 아님
├─ mellow_chat_runtime/  # 호환 shim, 실제 프로젝트 루트 아님
├─ node_modules/  # 임시 예외: 루트 Node/Playwright 해석 유지용
└─ launcher.py 등 루트 운영 스크립트
```

`node_modules`는 원칙상 `infra` 대상이지만, 현재 루트 기반 Node/Playwright 해석을 깨뜨리지 않기 위해 이번 정리에서는 보류했다.
`mellow_link/`, `mellow_chat_runtime/`는 기존 루트 import/실행 습관을 유지하기 위한 얇은 shim이며, 실제 프로젝트 본체는 모두 `core/` 아래에 있다.

## 현재 프로젝트 해석

- [`mellow_link`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link)
  - 현재 상용 1차 제품 본체
  - 프로젝트 생성, 분석 워크스페이스, 결과 패키지 흐름 담당
- [`mellow_chat_runtime`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_chat_runtime)
  - 분리 운영 가능한 경량 runtime API
  - 런타임 데이터는 [`data/runtime/mellow_chat_runtime_data`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/runtime/mellow_chat_runtime_data)로 관리
- [`autonomous_agent`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/autonomous_agent)
  - 후속 내부 자동화 계층
  - 현재 직접 사용자 제품 동선과는 분리
- [`pattern_extraction_pipeline`](/C:/Users/Hyein/ClaudeAI/AI_Project/pipelines/pattern_extraction_pipeline)
  - 구조/패턴 추출용 지원 파이프라인
- [`redteam_outside_root`](/C:/Users/Hyein/ClaudeAI/AI_Project/experiments/redteam_outside_root)
  - 경계 검증용 실험 자산

## 신규 프로젝트 생성 규칙

새 폴더를 만들기 전에 먼저 아래 질문으로 역할을 확정한다.

1. 실제 제품/엔진 본체인가
2. 추출/가공/배치/검증 파이프라인인가
3. 실험/탐색/검증용인가
4. 코드가 아니라 데이터/산출물/로그인가
5. 공통 기반 자원인가

분류 결과에 따라 `core`, `pipelines`, `experiments`, `data`, `infra` 중 하나에만 배치한다.

## 실행 메모

- 루트에는 `mellow_link`와 `mellow_chat_runtime` 호환 shim 패키지를 두어 기존 `python -m mellow_link.main` 같은 실행 습관을 유지한다.
- 루트 런처는 새 구조(`core/`, `data/`)를 우선 사용하되, 구 구조도 fallback으로 읽도록 보정되어 있다.
- `mellow_link`의 활성 문서는 [`core/mellow_link/docs`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/docs)를 기준으로 본다.

## 현재 제품 진입점

현재 대표 제품은 [`core/mellow_link`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link)이며 기본 사용자 진입점은 다음과 같다.

- `/`
- `/ui`
- `/projects/create`

빠른 시작:

1. Ollama를 실행한다.
2. [`core/mellow_link/.env`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/.env)에서 필수 설정을 확인한다.
3. 필요 시 `ANONYMIZATION_STORAGE_ROOT=./core/mellow_link/data/anonymization`을 지정한다.
4. `python -m mellow_link.main` 또는 [`launcher.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/launcher.py)로 서버를 실행한다.
5. `http://127.0.0.1:8000/projects/create`로 접속한다.
