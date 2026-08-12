# Daily Risk API and Service Contract

이 문서는 transport-neutral service 계약이다. 최종 URL은 구현 시 기존 FastAPI naming convention을 따르되 아래 operation 이름과 의미를 바꾸지 않는다.

## 공통 경계

- 모든 operation은 인증된 subject user 자신의 데이터만 처리한다.
- `ADMIN`, Pilot operator capability 또는 project ownership은 cross-user 접근 권한이 아니다.
- mutation은 exact expected version과 idempotency key를 요구한다.
- 응답은 opaque reference만 제공하고 DB ID, 내부 경로, notes, dailyBrick 원문을 포함하지 않는다.

## Operations

| Operation | 입력 | 성공 결과 | 주요 오류 |
| --- | --- | --- | --- |
| `request_daily_risk_evaluation` | local date, IANA timezone, trigger, key | run ref/status 또는 replay 결과 | invalid_date/timezone, insufficient source, idempotency conflict |
| `get_risk_evaluation` | run ref | status, safe error code, assessment ref | not_found |
| `get_daily_assessment` | local date | latest canonical assessment | not_found |
| `list_recent_assessments` | cursor, limit 1..100 | newest-first page | invalid_cursor |
| `get_risk_signal` | assessment ref, signal ref | rule/reason/evidence metadata | not_found |
| `acknowledge_assessment` | ref, expected version, key | updated action view | version/idempotency conflict |
| `mark_signal_disputed` | refs, reason code, version, key | action view | action_not_allowed, conflict |
| `suppress_signal` | refs, reason, expiry, version, key | suppression view | urgent_not_suppressible, conflict |
| `request_risk_replay` | date, timezone, expected latest ref, key | new/existing run | replay_conflict |
| `request_risk_backfill` | inclusive dates <=31, timezone, key | per-date run refs | range_too_large |
| `get_risk_rule_metadata` | rule set version optional | public rule metadata | version_not_found |
| `get_self_review_items` | cursor, limit | subject's active review items | invalid_cursor |
| `get_schedule_preference` | none | disabled/enabled preference | none |
| `update_schedule_preference` | enabled, timezone, local time, version, key | updated preference | invalid timezone/time, conflict |

`insufficient_data`는 평가 요청의 일반 4xx 실패가 아니라 completed assessment 결과다. DailyState가 전혀 없을 때도 원인을 안전하게 설명할 수 있다.

## Response fields

Assessment response는 local date, timezone, lifecycle/status, overall result, version, input freshness, snapshot/rule versions, evaluated time, signal summaries와 permitted actions를 포함한다. Evidence는 `daily_state:<opaque-ref>#safety.selfHarmUrge` 같은 안전한 reference만 사용하며 값 원문을 반복하지 않는다.

## Error taxonomy

- `not_found`: 존재하지 않거나 다른 subject scope의 resource
- `unauthorized`: 인증 부재
- `version_conflict`
- `idempotency_conflict`
- `action_not_allowed`
- `invalid_input`
- `evaluation_conflict`
- `stale_input`
- `internal_error`: stack trace 없이 correlation reference만 제공

존재 여부를 이용한 cross-user enumeration을 막기 위해 다른 사용자의 ref는 `not_found`로 처리한다.

## Audit

Evaluation request, completion/failure, replay/backfill, schedule 변경, acknowledge/dispute/suppress를 기록한다. raw request, health field values, token 원문은 저장하지 않는다.
