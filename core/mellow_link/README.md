# mellow_link

역할: core  
목적: 멜로우 링크 판맥(MellowLink Senseframe)의 메인 웹/API 본체다. 레거시 현대화 분석은 대표 분석 시나리오/기능으로 유지한다.
연결: 결과 산출물은 [`data/outputs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/outputs), 런타임 로그는 [`data/logs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/logs), 관련 지원 파이프라인은 [`pipelines/pattern_extraction_pipeline`](/C:/Users/Hyein/ClaudeAI/AI_Project/pipelines/pattern_extraction_pipeline)와 연결된다.

대표 사용자 진입점:
- `/projects/create`
- `/projects/{project_id}`
- `/projects/{project_id}/result?surface_mode=internal|external`

`/modules/rebuild_assistant`는 현재 안내 진입점이며, 실제 실행 시작은 `/projects/create`다.

## Daily Check-in Core

Daily Check-in Core는 개인용 일일 상태 체크 AI 에이전트의 1단계 기반 기능이다. 현재 범위는 AI 판단, 위험도 색상 판정, 알림, 의료 조언 없이 사용자가 직접 입력한 일일 기록을 저장하고 날짜별로 조회/수정하는 도메인과 저장 계층이다.

API는 인증된 사용자 기준으로만 동작한다.

- `POST /daily-states`: 특정 로컬 날짜의 기록 생성
- `GET /daily-states/{YYYY-MM-DD}`: 특정 날짜 기록 조회
- `PUT /daily-states/{YYYY-MM-DD}`: 특정 날짜 기록 수정
- `GET /daily-states?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`: 날짜 범위 목록 조회

데이터 모델은 `daily_states` SQLite 테이블에 저장된다. 주요 필드는 사용자 ID, 로컬 날짜, 수면 시간, 기상 횟수, 통증 점수, 기분 점수, 사용자가 직접 입력한 self-harm urge 점수, 식사 체크, 수분 섭취량, 아침/저녁 복약 체크, 에너지, 오늘의 작은 목표, 완료 여부, 메모, 생성/수정 시각이다. 실제 약 이름, 진단, 복용량 판단, 외부 전송 데이터는 포함하지 않는다.

마이그레이션은 기존 방식과 같이 앱 시작 또는 `init_db()` 호출 시 적용된다.

```powershell
cd C:\Users\Hyein\ClaudeAI\AI_Project\core
python -c "from mellow_link.infra.database import init_db; init_db()"
```

관련 테스트:

```powershell
cd C:\Users\Hyein\ClaudeAI\AI_Project\core\mellow_link
python -m pytest tests/test_daily_checkin_core.py
```
