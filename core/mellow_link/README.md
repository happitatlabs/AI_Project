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

## Persistent Pilot State and Operator Approval Queue

Priority 2는 프로젝트의 특정 분석 run에 대해 검토, 승인, 변경 요청, 전달 완료 상태를 SQLite에 영속 저장한다. 분석 실행 상태와 분리된 상태 축이며, 기존 메모리 기반 `run_approval`을 대체하거나 변경하지 않는다.

상태 흐름:

```text
draft -> ready_for_review -> under_review -> approved -> delivered
                              |
                              -> changes_requested -> ready_for_review
```

모든 생성 및 상태 변경은 idempotency key를 요구한다. 상태 변경은 예상 version을 검사하며, 상태 변경·감사 이벤트·idempotency 결과는 하나의 transaction으로 저장된다. 동일 요청의 재시도는 최초 결과를 반환하고 version이나 감사 이벤트를 추가하지 않는다.

권한 매핑은 기존 역할을 재사용한다.

- 일반 사용자: 자신이 소유한 프로젝트/run의 Pilot 생성, 조회, 제출 및 재제출
- 관리자: 운영자 queue 조회, 검토 시작, 승인, 변경 요청, 전달 완료 및 감사 이력 조회
- Guest: Pilot 기능 접근 불가

주요 API:

- `POST /pilot-states`
- `GET /pilot-states/{pilot_id}`
- `POST /pilot-states/{pilot_id}/submit`
- `POST /pilot-states/{pilot_id}/start-review`
- `POST /pilot-states/{pilot_id}/approve`
- `POST /pilot-states/{pilot_id}/request-changes`
- `POST /pilot-states/{pilot_id}/resubmit`
- `POST /pilot-states/{pilot_id}/deliver`
- `GET /pilot-states/queue/pending`
- `GET /pilot-states/queue/delivered`
- `GET /pilot-states/{pilot_id}/audit`

Queue와 감사 응답은 보고서 원문, 원본 파일명, 내부 파일 경로, bundle ID를 포함하지 않는다. 검토용 DOCX는 존재 여부만 제공한다. `deliver`는 기존 프로젝트/run 보관 경로에 DOCX가 실제로 존재할 때만 허용하며 경로 자체는 응답하지 않는다.

새 테이블은 기존 migration 방식과 동일하게 앱 시작 또는 `init_db()` 호출 시 생성된다.

```powershell
cd core
python -c "from mellow_link.infra.database import init_db; init_db()"
```

집중 테스트:

```powershell
cd core\mellow_link
python -m pytest tests/test_pilot_state_and_approval_queue.py
```
