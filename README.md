# AI_Project

AI_Project는 여러 코드베이스, 운영 자산, 실험, 보관 자료를 함께 두는 작업 루트다.  
현재 대표 제품은 [`core/mellow_link`](core/mellow_link)이며, 이 문서는 이상적 목표 구조가 아니라 현재 디스크 상태를 기준으로 정리한다.

## 한눈에 보기

- 대표 제품: [`core/mellow_link`](core/mellow_link)
- 보조 런타임: [`core/mellow_chat_runtime`](core/mellow_chat_runtime)
- 내부 자동화 계층: [`core/autonomous_agent`](core/autonomous_agent)
- 루트 비코드 상태: [`data`](data), [`outputs`](outputs)
- 실험/검증 자산: [`experiments`](experiments)
- 공용 기반 자원: [`infra`](infra)
- 보관/격리 영역: [`_archive`](./_archive), [`_isolation`](./_isolation)
- 문서용 셸: [`pattern_extraction_pipeline`](pattern_extraction_pipeline)

## 관리 원칙

- 분리는 프로젝트 단위가 아니라 역할 기준으로 한다.
- 코드 프로젝트와 비코드 상태를 같은 영역에 섞지 않는다.
- 활성 경로와 보관 경로를 분리한다.
- 문서는 목표 구조가 아니라 현재 디스크 상태를 우선 기록한다.

## 주요 디렉터리

| 경로 | 역할 | 현재 상태 |
| --- | --- | --- |
| [`core`](core) | 실제 제품/엔진/런타임 본체 | `mellow_link`, `mellow_chat_runtime`, `autonomous_agent`, 빈 `models/`, `templates/` |
| [`data`](data) | 루트 비코드 상태 저장 | 현재 `anonymization/` 존재 |
| [`outputs`](outputs) | 루트 산출물 저장 | 현재 `final/`, `images/`, `transcripts/`, `uploads/`, `videos/` 존재 |
| [`experiments`](experiments) | 실험/검증 자산 | 현재 `redteam_outside_root/` 중심 |
| [`infra`](infra) | 공용 기반 자원 | 현재 `models/`만 있고 비어 있음 |
| [`_archive`](./_archive) | 보관 가치가 있는 코드/문서/산출물 | `artifacts/`, `obsidian/`, 보관된 파이프라인 코드 |
| [`_isolation`](./_isolation) | 중복·삭제 후보 격리 | `*_what_is` 계열 경로 존재 |
| [`pattern_extraction_pipeline`](pattern_extraction_pipeline) | 실행 코드가 아닌 문서용 랜딩 셸 | `README.md`, `OBSIDIAN_EXPORT.md`만 유지 |
| `node_modules` | 루트 Node/Playwright 해석 유지용 예외 경로 | 현재 그대로 유지 |

## 현재 구조

```text
AI_Project/
├─ _archive/
│  ├─ artifacts/
│  ├─ obsidian/
│  └─ pipelines/
│     └─ pattern_extraction_pipeline/
├─ _isolation/
│  ├─ data_what_is/
│  ├─ mellow_chat_runtime_what_is/
│  ├─ mellow_link_what_is/
│  ├─ models_what_is/
│  └─ templates_what_is/
├─ core/
│  ├─ autonomous_agent/
│  ├─ data/
│  ├─ mellow_chat_runtime/
│  ├─ mellow_link/
│  ├─ models/     # 현재 비어 있음
│  └─ templates/  # 현재 비어 있음
├─ data/
│  └─ anonymization/
├─ experiments/
│  └─ redteam_outside_root/
├─ infra/
│  └─ models/     # 현재 비어 있음
├─ outputs/
│  ├─ final/
│  ├─ images/
│  ├─ transcripts/
│  ├─ uploads/
│  └─ videos/
├─ pattern_extraction_pipeline/
│  ├─ OBSIDIAN_EXPORT.md
│  └─ README.md
├─ node_modules/
└─ launcher.py 등 루트 운영 스크립트와 보조 파일
```

루트에는 launcher 스크립트, 테스트 보조 파일, 임시 캡처/로그 파일도 함께 존재한다.  
새 자산의 소속은 이런 루트 개별 파일이 아니라 상위 디렉터리 역할을 기준으로 판단한다.

## 현재 프로젝트 해석

| 경로 | 상태 | 설명 |
| --- | --- | --- |
| [`core/mellow_link`](core/mellow_link) | 활성 | 현재 대표 제품 본체. 프로젝트 생성, 분석 워크스페이스, 결과 패키지 흐름 담당 |
| [`core/mellow_chat_runtime`](core/mellow_chat_runtime) | 활성 | 분리 운영 가능한 경량 runtime API |
| [`core/autonomous_agent`](core/autonomous_agent) | 활성 | 후속 내부 자동화 계층. 직접 사용자 제품 동선과는 분리 |
| [`experiments/redteam_outside_root`](experiments/redteam_outside_root) | 실험 | 경계 검증용 실험 자산 |
| [`_archive/pipelines/pattern_extraction_pipeline`](./_archive/pipelines/pattern_extraction_pipeline) | 보관 | 구조/패턴 추출용 지원 파이프라인의 보관본 |
| [`pattern_extraction_pipeline`](pattern_extraction_pipeline) | 문서용 | 실행 코드가 아니라 문서 랜딩 셸 |

## 운영 메모

- 루트 런처는 기본적으로 [`core/mellow_link`](core/mellow_link)를 우선 사용한다.
- `mellow_link`의 활성 문서는 [`core/mellow_link/docs`](core/mellow_link/docs)를 기준으로 본다.
- 비코드 상태는 현재 루트 [`data`](data), [`outputs`](outputs)뿐 아니라 [`core/mellow_link/data`](core/mellow_link/data), [`core/mellow_link/outputs`](core/mellow_link/outputs), [`core/mellow_link/logs`](core/mellow_link/logs), [`core/data/anonymization`](core/data/anonymization)에도 분산되어 있다.
- [`core/models`](core/models), [`core/templates`](core/templates), [`infra/models`](infra/models)은 현재 비어 있다.
- [`_archive`](./_archive)와 [`_isolation`](./_isolation)은 활성 import 루트가 아니라 보관/격리 영역이다.
- 루트 [`pattern_extraction_pipeline`](pattern_extraction_pipeline)은 실행 대상이 아니라 문서용 셸이다.
- `node_modules`는 원칙상 별도 관리 대상이지만, 현재 루트 기반 Node/Playwright 해석을 깨뜨리지 않기 위해 그대로 둔다.

## 새 폴더 만들기 전 체크

새 폴더를 만들기 전에 먼저 아래 질문으로 역할을 확정한다.

1. 실제 제품/엔진 본체인가
2. 실험/탐색/검증용인가
3. 공용 기반 자원인가
4. 비코드 상태나 산출물 저장소인가
5. 즉시 사용하지 않고 보관/격리해야 하는가

분류 기준:

- 실제 제품/엔진 본체면 `core`
- 실험/검증 자산이면 `experiments`
- 공용 기반 자원이면 `infra`
- 비코드 상태면 `data`, 산출물이면 `outputs`
- 보관/격리 대상이면 `_archive` 또는 `_isolation`

## 빠른 시작

1. Ollama를 실행한다.
2. [`core/mellow_link/.env`](core/mellow_link/.env)에서 필수 설정을 확인한다.
3. 필요하면 `ANONYMIZATION_STORAGE_ROOT=./core/mellow_link/data/anonymization`을 지정한다.
4. `python -m mellow_link.main` 또는 [`launcher.py`](launcher.py)로 서버를 실행한다.
5. `http://127.0.0.1:8000/projects/create`로 접속한다.

## 현재 제품 진입점

현재 대표 제품은 [`core/mellow_link`](core/mellow_link)이며 기본 사용자 진입점은 다음과 같다.

- `/`
- `/ui`
- `/projects/create`
- `/projects/{project_id}`
- `/projects/{project_id}/result?surface_mode=internal|external`

`/modules/rebuild_assistant`는 현재 실행 화면이 아니라 안내 진입점이다.  
실제 프로젝트 생성과 분석 시작은 `/projects/create`에서 진행한다.
