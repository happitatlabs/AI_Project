# AI_Project

`AI_Project`는 여러 실험/보조 시스템을 포함하지만, 현재 상용 1차 기준 본체는 [`mellow_link`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link)다.

현재 제품 포지션은 다음과 같다.

- 대표 제품: `레거시 현대화 분석`
- 대표 사용자 흐름: `새 프로젝트 -> 분석 워크스페이스 -> 결과 패키지`
- 대표 산출물: `진단 + 설계안 + 전환 초안`

## 현재 기준 시스템 구분

- [`mellow_link`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link)
  - 상용 1차 제품 본체
  - 프로젝트 생성, run 추적, 결과 패키지, 대표 상품 모듈 포함
- [`autonomous_agent`](/C:/Users/Hyein/ClaudeAI/AI_Project/autonomous_agent)
  - 2차 이후 내부 자동화 계층
  - 현재 사용자 제품 본체는 아님
- [`mellow_chat_runtime`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_chat_runtime)
  - 별도 경량 runtime API
  - 현 상용 1차 핵심 동선과는 분리
- [`Open-LLM-VTuber`](/C:/Users/Hyein/ClaudeAI/AI_Project/Open-LLM-VTuber)
  - 선택형 외부 인터페이스/부속 시스템

## 기본 사용자 진입점

현재 제품 기준 기본 사용자 진입점은 아래와 같다.

- `/`
- `/ui`
- `/projects/create`

위 3개는 모두 `레거시 현대화 분석` 제품 홈/프로젝트 생성 흐름으로 연결된다.

주요 사용자 화면:

- `/projects/create`
  - 새 프로젝트 생성
- `/projects/{project_id}`
  - 분석 워크스페이스
- `/projects/{project_id}/result`
  - 결과 패키지

운영/개발 화면은 유지되지만 일반 사용자 동선에서는 숨긴다.

## 현재 제품 실행 흐름

1. 사용자가 프로젝트를 생성한다.
2. 자산을 업로드한다.
3. 익명화 전처리 공통 서비스가 원본을 격리하고 canonical anonymized source를 생성한다.
4. 구조 추출은 canonical anonymized source 기준으로 수행된다.
5. `SafeAnalysisBundle`이 만들어진다.
6. [`rebuild_assistant`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant)가 `SafeAnalysisBundle`만 받아 분석을 수행한다.
7. 결과 패키지 화면에서 `진단 / 설계안 / 전환 초안 / 부록`을 확인한다.

중요 원칙:

- 공개 실행 경로에서 raw `assets` / `temp_session_id` 기반 입력은 사용하지 않는다.
- `rebuild_assistant` 공개 실행선은 safe bundle 기반이다.
- original content, original path, mapping 정보는 HTTP 응답/결과 패키지에 노출하지 않는다.

## 핵심 문서

활성 문서는 [`mellow_link/docs`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs) 아래를 기준으로 본다.

- 전체 구조: [AI_PROJECT_STRUCTURE_AND_SPEC.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/AI_PROJECT_STRUCTURE_AND_SPEC.md)
- 시스템 기준: [SYSTEM_ARCHITECTURE_GUIDEBOOK.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/SYSTEM_ARCHITECTURE_GUIDEBOOK.md)
- 제품 구조 템플릿: [PRODUCT_STRUCTURE_TEMPLATE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PRODUCT_STRUCTURE_TEMPLATE.md)
- 익명화 MVP 현황: [ANONYMIZATION_MVP_STATUS.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANONYMIZATION_MVP_STATUS.md)
- 파일럿 보안/운영 안내: [PILOT_SECURITY_AND_OPERATIONS_NOTICE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/PILOT_SECURITY_AND_OPERATIONS_NOTICE.md)
- 문서 인덱스: [README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/README.md)

## 빠른 시작

1. Ollama를 실행한다.
2. `mellow_link/.env`에서 필수 설정을 확인한다.
3. 필요 시 `ANONYMIZATION_STORAGE_ROOT`를 명시한다.
4. `python -m mellow_link.main` 또는 [launcher.py](/C:/Users/Hyein/ClaudeAI/AI_Project/launcher.py)로 서버를 실행한다.
5. `http://127.0.0.1:8000/projects/create`로 접속한다.

예시:

```env
JWT_SECRET_KEY=32자_이상_랜덤_문자열
ANONYMIZATION_STORAGE_ROOT=./mellow_link/data/anonymization
VTUBER_RELAY_ENABLED=0
AVATAR_AUTO_LAUNCH_ENABLED=0
ENABLE_EDGE_TTS=0
```

## 현재 해석 기준

- `mellow_link` = 지금 판매/데모하는 제품
- `autonomous_agent` = 추후 안 보이게 붙일 내부 자동화
- `mellow_chat_runtime` = 분리 운영 가능한 runtime 계층
- `Open-LLM-VTuber` = 선택형 부속 인터페이스
