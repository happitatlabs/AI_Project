# Daily Risk Analyzer Acceptance Test Contract

이 문서는 구현 PR의 최소 acceptance 기준이다. 모든 fixture는 합성이며 실제 개인정보를 사용하지 않는다.

## Input과 날짜

- 유효한 DailyState snapshot 생성
- optional 구조화 field 누락 처리
- DailyState 부재 및 required field invalid 시 `insufficient_data`
- 다른 user의 DailyState 혼입 차단
- notes와 dailyBrick이 snapshot, signal, log에 미포함
- 입력 변경 시 snapshot version 변경 및 이전 assessment supersede
- `YYYY-MM-DD` local date가 UTC 변환으로 이동하지 않음
- 유효/무효 IANA timezone과 DST 존재하지 않음/중복 시간

## Rule과 집계

- `selfHarmUrge=0`은 signal 없음
- `1`과 `10`은 동일 rule의 `urgent_review` boundary로 허용
- 범위 밖 값은 평가 전 source validation error/insufficient data
- 동일 input/rule version 결과 결정성
- disabled rule 미실행
- rule set version 변경 시 새 assessment
- 중복 signal 제거 및 최고 severity 집계
- input 부재를 `no_signal`로 낮추지 않음

## Evaluation lifecycle

- 정상 manual 및 opt-in scheduled evaluation
- schedule 기본 비활성
- 동일 logical evaluation 중복 생성 방지
- 동일 idempotency key/same payload replay
- 동일 key/different payload conflict
- 동시 evaluation 하나만 생성
- 프로세스 재시작 후 command replay
- 5분 전 run은 orphan 아님, 5분 후 conditional recovery
- old evaluator late commit 차단
- 명시적 retry 최대 3회
- backfill 최대 31일과 날짜별 transaction
- 새 input/rule replay가 이전 결과를 보존하고 supersede

## 사용자 Action

- acknowledge 성공 및 중복 replay
- bounded dispute reason과 자유 텍스트 거부
- suppressible signal 최대 24시간
- `urgent_review` suppression 거부
- stale/high expected version conflict
- 다른 user 및 일반 admin action 차단
- 후속 evaluation에서 resolved relation과 과거 signal 보존

## API와 UX

- 각 service operation의 success/error mapping
- recent/self-review cursor pagination과 limit 1..100
- `not_found`, unauthorized, version/idempotency/action conflict 구분
- stack trace와 내부 ID 비노출
- assessment에 freshness, rule version, evaluated time 포함
- severity를 text label로 제공하고 색상만 사용하지 않음
- 중복 submit 방지와 conflict recovery action

## Transaction과 persistence

- run 저장 실패 시 idempotency/audit 없음
- signal 저장 실패 시 assessment/run completion rollback
- audit 저장 실패 시 state/action rollback
- action 실패 시 version 증가 없음
- unique logical evaluation 및 command result constraint
- clean DB additive table 생성, `create_all()` 두 번 실행 가능
- 기존 DailyState와 Pilot/Delivery data 유지
- append-only audit 수정/삭제 API 없음

## Security와 privacy

- cross-user assessment/signal ID 추측 차단
- list와 cursor에서 user 격리
- DB ID, file path, username, email, phone 비노출
- notes, dailyBrick, health payload가 response/audit/log에 없음
- idempotency key 원문 미저장
- error response stack trace 없음
- 합성 fixture만 사용
- `ADMIN`만으로 cross-user access 불가

## 회귀

- Daily Check-in CRUD와 user/date uniqueness
- Pilot State와 Approval Queue
- DOCX 생성, 1페이지 요약, 결과 보관
- Delivery Checklist와 Package Assembly
- runtime-core

전체 suite의 기존 실패는 base와 정확히 비교하고 신규 실패를 숨기거나 skip/assertion 약화로 우회하지 않는다.

## 계약 연결

| Operation | 필수 acceptance 영역 |
| --- | --- |
| evaluation request/status | input, lifecycle, idempotency, ownership |
| daily/recent assessment | aggregation, pagination, isolation |
| signal detail | evidence minimization, rule metadata |
| acknowledge/dispute/suppress | version, permission, audit, retry |
| replay/backfill | immutable history, limits, supersede |
| rule metadata | immutable version and enabled state |
| self-review list | active/suppressed state, isolation |
| schedule preference | opt-in, timezone/DST, version |
