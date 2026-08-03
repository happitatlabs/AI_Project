# Daily Risk Security and Privacy Contract

## 데이터 분류와 최소화

DailyState와 risk 결과는 민감한 건강 관련 개인정보다. Analyzer는 구조화 allowlist만 읽고 notes, dailyBrick, 약 이름, 의료 이력, 메시지 또는 업로드 원문을 복제하지 않는다. Snapshot은 SHA-256 digest와 opaque source reference만 저장한다.

## 접근 제어

- 모든 repository/service query는 authenticated subject user scope를 강제한다.
- 다른 사용자의 opaque ref 추측은 `not_found`로 처리한다.
- 기존 `ADMIN`, Pilot operator, project ownership은 cross-user health access를 부여하지 않는다.
- delegated review는 동의·철회·목적 제한을 설계한 후에만 추가한다.

## 외부 비노출

- 내부 DB ID, filesystem path, local username, bundle identifier
- DailyState 원문 payload, notes, dailyBrick
- 실제 이메일, 전화번호, 연락처
- stack trace, SQL, idempotency key 원문
- 임상적 진단 또는 검증되지 않은 민감 추론

Evidence는 opaque source와 allowlisted field name만 포함한다. Actor도 self-scoped opaque reference로 표현한다.

## Logging과 Audit

Application log는 안전한 event/error code, opaque run ref, rule ID만 기록한다. health value, assessment summary 원문, action reason 원문, request payload를 기록하지 않는다. Audit는 append-only metadata이며 raw source가 아니다.

## 의료·안전 경계

- analyzer는 의료기기, 임상 screening 또는 의사의 대체물이 아니다.
- `selfHarmUrge` 값을 임박성·의도·진단으로 확장 추론하지 않는다.
- 약물 추천, 용량 변경, 자동 응급 대응, 위험 색상 엔진을 제공하지 않는다.
- 자동 행동은 advisory record 생성으로 제한한다.

## 테스트와 운영

Fixture는 합성 사용자와 값만 사용하고 실제 개인정보를 넣지 않는다. 오류·로그 capture test로 원문 비노출을 검증한다. 초기 retention은 비파괴이며 삭제 정책 전에는 자동 purge를 구현하지 않는다.

## Threat cases

- 다른 user의 assessment/signal/action IDOR
- cursor나 error detail을 통한 존재 여부 추론
- idempotency key 재사용/충돌
- stale version으로 action 덮어쓰기
- schedule timezone 조작으로 날짜 중복 실행
- notes/free text가 snapshot 또는 log로 유출

각 위협은 service-level ownership, opaque reference, conditional update, canonical uniqueness와 field allowlist로 차단한다.
