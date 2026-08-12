# ADR: Persistent Daily Risk Assessment and Deterministic Rules

- 상태: Proposed for the implementation PR
- 범위: Daily Agent Phase 2 design

## Context

Daily Check-in은 사용자별 local-date record를 영속 저장하지만 위험 분석 결과, rule version, replay 및 사용자 action을 재현할 계약이 없다. 메모리 결과는 재시작, 동시 요청, 감사 및 입력 변경 추적을 견디지 못한다.

## Decision

기존 SQLAlchemy와 repository/service/transaction 패턴을 사용해 다음 논리 record를 additive schema로 영속화한다.

- `daily_risk_evaluation_runs`
- `daily_risk_assessments`
- `daily_risk_signals`
- `daily_risk_actions`
- `daily_risk_command_results`
- `daily_risk_audit_events`
- `daily_risk_schedule_preferences`

물리 이름은 구현 시 충돌 여부를 확인하되 의미와 제약을 유지한다. 기존 `Base.metadata.create_all()` additive 방식과 SQLite 테스트를 우선 재사용하며 새 migration framework는 도입하지 않는다.

## 주요 제약

- Evaluation logical identity unique: subject, local date, snapshot version, rule set version
- Assessment는 evaluation당 하나
- Signal unique: assessment, rule ID/version, evidence reference
- Command result unique: subject scope, hashed idempotency key
- Schedule preference unique: subject user
- 모든 mutable aggregate에 integer version과 UTC created/updated timestamp
- subject FK는 기존 User, source reference는 기존 DailyState로 연결하되 외부 응답에 내부 ID를 노출하지 않음

## Transaction 경계

- run 생성 + idempotency
- assessment + signals + run completion + audit
- failure + safe error audit
- action + assessment version + audit + idempotency
- replay completion + previous canonical assessment supersede

Audit는 append-only이며 일반 API로 수정·삭제하지 않는다.

## 실행 및 복구

결정적 평가를 동기 service로 실행한다. 별도 worker/queue는 만들지 않는다. 5분 이상 갱신 없는 evaluating run은 conditional version/claim으로 failed 처리하고, 명시적 retry 최대 3회를 허용한다.

## Retention

초기 구현은 assessment, signal, action, audit, idempotency를 자동 삭제하지 않는다. raw input snapshot이나 자유 텍스트는 저장하지 않는다. Schedule preference는 비활성화 또는 계정 lifecycle까지 유지한다. 건강 데이터의 장기 보존·삭제·export 정책은 별도 개인정보 정책과 migration을 거쳐야 한다.

## Backfill

기존 DailyState에 assessment를 자동 생성하지 않는다. 사용자가 명시적으로 요청한 날짜만 평가하며 backfill은 요청당 31일로 제한한다.

## 고려한 대안

1. 메모리 평가: 단순하지만 재시작·idempotency·감사를 만족하지 못해 제외.
2. 기존 Pilot Approval Queue 재사용: 업무 승인과 개인 건강 데이터의 권한·보존 경계가 달라 제외.
3. LLM 분석: 비결정적이고 설명·안전 계약이 부족해 범위 밖.
4. 외부 scheduler/queue: 현재 rule 계산에 과도하고 새 운영 의존성을 만들므로 제외.

## 결과와 운영 주의

Additive table만 생성하고 기존 data/table을 수정·삭제하지 않는다. 코드 rollback 후 신규 table은 남으며 자동 down migration을 제공하지 않는다. 운영 배포 전 backup과 schema 생성 권한을 확인한다. 향후 파괴적 변경은 별도 migration 전략이 필요하다.

## 확정된 정책 요약

- Agent는 DailyState 사용자 본인이다.
- 날짜 경계는 명시적 IANA timezone의 local date다.
- 초기 input은 DailyState의 구조화 allowlist뿐이다.
- rule은 `daily-risk-v1` deterministic code contract다.
- 집계는 최고 severity이며 확률 점수를 사용하지 않는다.
- 결과는 advisory이고 자동 차단·연락을 하지 않는다.
- self-review를 사용하고 Pilot queue를 재사용하지 않는다.
- schedule은 opt-in, 동기 service, 5분 orphan, 3회 수동 retry다.
- replay/backfill은 새 immutable 평가를 만들며 최대 31일이다.
- 자동 retention deletion은 없다.
- urgent signal suppress는 금지하고 false positive는 bounded dispute로 기록한다.
- Priority 5 input은 계약 변경 전 자동 연결하지 않는다.
