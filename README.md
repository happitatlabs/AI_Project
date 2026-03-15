# AI_Project

Mellow-Link는 공통 실행 엔진 위에 유스케이스 모듈을 얹는 로컬 실행형 AI 플랫폼입니다.  
사용자는 `/ui`에서 모듈을 선택해 작업을 시작하고, 모든 실행은 `run_id` 기준으로 생성·추적됩니다.

현재 이 프로젝트의 핵심 프레임은 `엔진 + 모듈`입니다.

- 공통 엔진
  - `core`
  - `services`
  - `routers`
  - `static`
  - `infra`
- 실행 모듈
  - `sql_analytics`
  - `research_assistant`
  - `rebuild_assistant`
  - `ai_workflow_console`

## 제품 동선

현재 기준 기본 사용자 흐름은 아래와 같습니다.

1. `/ui`에서 모듈을 선택하고 작업을 시작합니다.
2. 시스템이 `run_id`를 생성합니다.
3. run은 기본 session에 자동 연결됩니다.
4. 실행이 시작되면 `/user-console?run_id=...`로 이동합니다.
5. 이후 `/runs`에서 같은 run에 다시 진입할 수 있습니다.

핵심 URL:

- `/ui`: 제품 홈, 작업 시작
- `/runs`: 실행 목록
- `/user-console?run_id=...`: 사용자 진행/결과 뷰
- `/operator-console?run_id=...`: 운영자 제어 뷰
- `/dev-dashboard`: 다중 run 비교 뷰
- `/dev-console?run_id=...`: 특정 run 디버깅 뷰

## 이 프로그램이 하는 일

이 프로젝트는 단순 채팅 앱이 아니라, 실행을 만들고 추적하고 필요하면 운영/디버깅까지 이어지는 구조를 목표로 합니다.

주요 기능:

- 로컬 LLM 기반 실행 처리
- 문서 업로드 후 분석 run 생성
- 실행 상태, 진행률, activity, 결과 추적
- 운영자 제어와 개발자 디버깅 화면 분리
- 이미지/비디오/아바타 같은 선택 서비스 연동

## 구조

### 공통 엔진

공통 엔진은 인증, run 생성, 상태 추적, 서비스 연결, 공통 콘솔을 담당합니다.

주요 위치:

- [mellow_link/main.py](/D:/AI_Project/mellow_link/main.py)
- [mellow_link/core](/D:/AI_Project/mellow_link/core)
- [mellow_link/services](/D:/AI_Project/mellow_link/services)
- [mellow_link/routers](/D:/AI_Project/mellow_link/routers)
- [mellow_link/static](/D:/AI_Project/mellow_link/static)
- [mellow_link/infra](/D:/AI_Project/mellow_link/infra)

### 실행 모듈

모듈은 `작업 시작 UI + 입력 스키마 + 실행 로직`만 다르게 가지고, run 추적과 콘솔은 공통 엔진을 그대로 공유합니다.

- [mellow_link/modules/sql_analytics](/D:/AI_Project/mellow_link/modules/sql_analytics)
  - 자연어 질문을 SQL 분석 run으로 변환
- [mellow_link/modules/research_assistant](/D:/AI_Project/mellow_link/modules/research_assistant)
  - 문서 업로드 후 문서 기반 분석 run 생성
- [mellow_link/modules/rebuild_assistant](/D:/AI_Project/mellow_link/modules/rebuild_assistant)
  - 레거시 기능을 분석해 재구성 전략과 구조화 초안 생성
- [mellow_link/modules/ai_workflow_console](/D:/AI_Project/mellow_link/modules/ai_workflow_console)
  - 생성/워크플로우 실행 관리용 시작점

## 화면 책임

### `/ui`

제품 홈입니다.

- 모듈 선택
- 입력/업로드
- run 생성
- 성공 시 `/user-console`로 이동

### `/runs`

실행 목록 허브입니다.

- 최근 run 목록
- 상태 기준 재진입
- 모듈/실행 유형 확인

### `/user-console`

사용자 진행/결과 화면입니다.

- run 상태
- 정규화된 3단계 진행률
- 최근 activity
- 중간 결과 / 최종 결과

여기에는 raw debug, prompt, tool JSON, routing log를 노출하지 않습니다.

### `/operator-console`

운영자 제어 화면입니다.

- 시작/재시도/취소/강제 종료
- 현재 상태
- 최소 요약

### `/dev-dashboard`

다중 run 비교 화면입니다.

- run 목록
- status / module / duration / summary preview
- 필터 / 정렬

### `/dev-console`

특정 run 디버깅 화면입니다.

- raw event log
- step trace
- prompt / response
- tool usage
- error detail

## 현재 상태

현재 기준으로 상대적으로 안정화된 흐름은 아래와 같습니다.

- `sql_analytics`
  - 자연어 질문 -> SQL 분석 run 생성 -> `/user-console` 결과 확인
- `research_assistant`
  - 문서 업로드 -> 분석 run 생성 -> `/user-console` 결과 확인
- `rebuild_assistant`
  - 레거시 파일/입력 자산 -> 재구성 run 생성 -> `/user-console` 결과 확인

최근 정리된 점:

- `run_id` 중심 공통 콘솔 구조 정리
- 사용자용 진행률을 모듈별 raw todo에서 정규화된 3단계로 통일
- `research_assistant`는 범용 tool loop 대신 direct research inference 경로 사용
- research retry는 같은 lifecycle 안에서 재시도하고, 종료 후에만 모델 unload
- `rebuild_assistant`는 `status_permissions` / `search_filters` / `save_validation` feature mode를 분리해 구조화 결과를 생성

## 빠른 시작

1. Ollama를 실행합니다.
2. `mellow_link/.env`에서 JWT 시크릿을 고정합니다.
3. 필요하면 선택 서비스를 켜거나 끕니다.
4. `python -m mellow_link.main` 또는 [launcher.py](/D:/AI_Project/launcher.py)로 서버를 실행합니다.
5. 브라우저에서 `http://127.0.0.1:8000/ui`로 접속합니다.

예시:

```env
JWT_SECRET_KEY=32자_이상_랜덤_문자열
VTUBER_RELAY_ENABLED=0
AVATAR_AUTO_LAUNCH_ENABLED=0
ENABLE_EDGE_TTS=0
```

## 선택 서비스

아래 서비스는 선택 사항입니다.

- Ollama
  - 필수
- ComfyUI
  - 이미지/비디오 생성 시 사용
- Open-LLM-VTuber
  - 음성/아바타 인터페이스용

현재 `.env`에서 VTuber 관련 기능은 비활성화해 둘 수 있습니다.

주요 위치:

- [Open-LLM-VTuber](/D:/AI_Project/Open-LLM-VTuber)

## 참고 문서

- [AI_PROJECT_STRUCTURE_AND_SPEC.md](/D:/AI_Project/AI_PROJECT_STRUCTURE_AND_SPEC.md)
- [SYSTEM_ARCHITECTURE_GUIDEBOOK.md](/D:/AI_Project/SYSTEM_ARCHITECTURE_GUIDEBOOK.md)
- [TROUBLESHOOTING.md](/D:/AI_Project/TROUBLESHOOTING.md)
- [SQL_ANALYTICS_DEMO.md](/D:/AI_Project/SQL_ANALYTICS_DEMO.md)
