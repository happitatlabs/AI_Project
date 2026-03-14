# AI_Project

Mellow-Link는 공통 실행 엔진 위에 유스케이스 모듈을 얹는 로컬 실행형 AI 플랫폼입니다.  
사용자는 `/ui`에서 모듈을 선택해 실행을 시작하고, 모든 작업은 `run_id` 기반으로 추적됩니다.

현재 기준으로 이 프로그램은 "채팅 앱"이라기보다 `엔진 + 모듈` 구조를 가진 실행형 제품에 가깝습니다.

- `/ui`: 작업 시작
- `/runs`: 내 실행 목록
- `/user-console?run_id=...`: 실행 진행/결과 확인
- `/operator-console?run_id=...`: 운영자 개입
- `/dev-dashboard`: 전체 run 분석
- `/dev-console?run_id=...`: 특정 run 디버깅

## 이 프로그램이 하는 일

사용자가 프롬프트를 입력하거나 파일을 올리면, 시스템이 `run_id` 기준으로 실행 단위를 만들고 진행 상태를 추적합니다.

할 수 있는 일:

- 로컬 LLM을 통한 질의응답
- 문서 업로드와 RAG 기반 질의응답
- 이미지/비디오 생성 파이프라인 연동
- 실행 상태 추적, todo 진행률 표시
- 운영자 승인/중단/재시도 같은 개입
- 개발자용 이벤트/성능/원시 데이터 분석

즉, "대화" 자체보다 "실행을 만들고, 추적하고, 필요하면 개입하는" 구조가 중심입니다.

## 핵심 구성

### 1. 공통 엔진

공통 실행 엔진은 run 생성, 상태 추적, 권한, 이벤트, 공통 콘솔을 담당합니다.

- FastAPI 기반 백엔드
- 인증, 세션, run 관리
- LLM / RAG / 이미지 / 문서 / 비디오 서비스 연결
- run 이벤트 기록과 SSE 스트리밍
- 사용자/운영자/개발자 화면 제공

엔진 디렉터리:

- [mellow_link/main.py](/D:/AI_Project/mellow_link/main.py)
- [mellow_link/core](/D:/AI_Project/mellow_link/core)
- [mellow_link/services](/D:/AI_Project/mellow_link/services)
- [mellow_link/routers](/D:/AI_Project/mellow_link/routers)
- [mellow_link/static](/D:/AI_Project/mellow_link/static)
- [mellow_link/infra](/D:/AI_Project/mellow_link/infra)

### 2. 실행 모듈

실행 모듈은 "작업 시작 UI + 입력 스키마 + 실행 로직"만 다르게 가지고, run 추적과 콘솔은 공통 엔진을 그대로 공유합니다.

- [mellow_link/modules/sql_analytics](/D:/AI_Project/mellow_link/modules/sql_analytics)
- [mellow_link/modules/research_assistant](/D:/AI_Project/mellow_link/modules/research_assistant)
- [mellow_link/modules/ai_workflow_console](/D:/AI_Project/mellow_link/modules/ai_workflow_console)

대표 역할:

- `sql_analytics`: 자연어 질문을 SQL 분석 run으로 변환
- `research_assistant`: 문서 업로드와 RAG 분석 run 생성
- `ai_workflow_console`: 생성 작업 run 관리와 결과 추적

### 3. Open-LLM-VTuber

선택적으로 붙는 음성/아바타 서비스입니다.

- TTS
- ASR
- Live2D 아바타
- WebSocket 기반 음성 인터랙션

주요 위치:

- [Open-LLM-VTuber](/D:/AI_Project/Open-LLM-VTuber)

### 4. Launcher

프로그램 시작점입니다.

- 환경 점검
- Ollama 확인
- Mellow-Link 서버 실행

주요 위치:

- [launcher.py](/D:/AI_Project/launcher.py)

## 현재 제품 동선

Phase 1 기준으로 사용자 흐름은 아래처럼 정리되어 있습니다.

1. `/ui`에서 작업을 입력한다.
2. 시스템이 `run_id`를 만든다.
3. run은 기본 session에 자동 연결된다.
4. 성공적으로 시작되면 `/user-console?run_id=...`로 이동한다.
5. 이후 `/runs`에서 같은 run으로 다시 들어올 수 있다.

이 구조의 목적은 다음 두 가지입니다.

- 제품 홈과 콘솔 책임 분리
- `run_id`를 공통 축으로 같은 실행을 여러 관점에서 보기

## 화면별 책임

### `/ui`

모듈 선택과 작업 시작 전용 화면입니다.

- 실행 모듈 선택
- prompt 입력
- 파일 업로드
- run 생성
- 성공 시 user console로 이동

### `/runs`

내 run 목록 허브입니다.

- 최근 실행 목록
- 상태 기준 확인
- 특정 run 재진입

### `/user-console`

사용자 진행/결과 화면입니다.

- run 상태
- 진행률
- todo
- 최근 activity
- 중간 결과 / 최종 결과

여기에는 raw debug, routing log, tool JSON 같은 개발 정보는 노출하지 않습니다.

### `/operator-console`

운영자 개입 화면입니다.

- 승인
- 보류
- 재시도
- 중단
- 강제 종료

### `/dev-dashboard`

여러 run을 비교 분석하는 화면입니다.

- run 목록
- 타임라인 요약
- 지연 시간 비교
- mode / failure / escalation 관측

### `/dev-console`

특정 run 상세 디버깅 화면입니다.

- events
- raw data
- tool call detail
- performance
- routing 관련 정보

## 빠른 시작

환경에 따라 다르지만 기본 진입점은 보통 아래 순서입니다.

1. Ollama 실행
2. `mellow_link/.env`에 고정 JWT 시크릿 확인
3. 프로젝트 환경 준비
4. `launcher.py` 또는 `python -m mellow_link.main` 실행
5. 브라우저에서 `/ui` 접속

예시:

```env
JWT_SECRET_KEY=32자_이상_랜덤_문자열
```

로그인 유지가 중요한 이유는 JWT 시크릿이 서버 시작 시점에 고정되어야 하기 때문입니다.
현재는 [database.py](/D:/AI_Project/mellow_link/infra/database.py)가 import 시점에 `.env`를 먼저 읽도록 정리되어 있습니다.

## 주의

- 이 프로젝트는 로컬 환경과 외부 도구 의존성이 있습니다.
- `run` ownership은 session 기반으로 관리됩니다.
- 과거 `session_id` 없는 orphan run은 현재 목록에서 숨기는 정책입니다.
- 운영자/개발자 화면은 사용자 화면과 분리하는 방향으로 정리 중입니다.

## 참고 문서

- [AI_PROJECT_STRUCTURE_AND_SPEC.md](/D:/AI_Project/AI_PROJECT_STRUCTURE_AND_SPEC.md)
- [SYSTEM_ARCHITECTURE_GUIDEBOOK.md](/D:/AI_Project/SYSTEM_ARCHITECTURE_GUIDEBOOK.md)
- [TROUBLESHOOTING.md](/D:/AI_Project/TROUBLESHOOTING.md)
- [SQL_ANALYTICS_DEMO.md](/D:/AI_Project/SQL_ANALYTICS_DEMO.md)
