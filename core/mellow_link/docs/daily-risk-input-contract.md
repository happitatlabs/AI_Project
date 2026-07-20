# Daily Risk Input and Freshness Contract

- 문서 상태: Implementation contract draft
- 권위 source: 인증된 사용자의 `DailyState`

## Source allowlist

초기 `daily-risk-v1`은 정확히 한 날짜의 구조화된 `DailyState`에서 아래 필드만 읽는다.

| Source field | 필요성 | 용도 |
| --- | --- | --- |
| `date` | required | local date 일치 검증 |
| `safety.selfHarmUrge` | required | 초기 안전 signal rule |
| `updatedAt` | required | source provenance와 최신 record 확인; snapshot digest에는 미포함 |

다음 구조화 필드는 초기 rule 입력과 snapshot digest 모두에 포함하지 않는다.

- `sleepHours`, `wakeCount`
- pain의 wrist/elbow/back/foot
- mood의 anxiety/depression/irritation
- meals, hydration
- medication morning/evening check
- energy, dailyBrickCompleted

이 값에 새 threshold를 적용하려면 rule ID, version, snapshot allowlist, 안전 근거, 테스트를 포함한 별도 계약 변경이 필요하다. 관련 없는 field 수정만으로 assessment를 supersede하지 않는다.

## 명시적 제외

- `notes`와 `dailyBrick` 원문
- 실제 약 이름, 처방 정보, 의료 이력
- ChatMessage, UserMemory, 업로드 문서
- Pilot State, Approval Queue, Delivery Readiness, Package Assembly
- 외부 API 또는 LLM 결과

자유 텍스트는 읽거나 snapshot, signal, audit, log에 복제하지 않는다.

## Required, missing, stale

- 대상 날짜의 `DailyState`가 없으면 evaluation은 `completed`될 수 있지만 assessment 결과는 `insufficient_data`다.
- required field가 schema 범위를 벗어나거나 읽을 수 없으면 `insufficient_data`와 안전한 reason code를 남긴다. 값을 조용히 보정하지 않는다.
- 과거 날짜의 정확한 DailyState는 시간 경과만으로 stale이 되지 않는다.
- 평가 후 DailyState의 canonical snapshot digest가 바뀌면 기존 assessment는 `superseded` 대상이며 최신 결과로 취급하지 않는다.
- live query 결과를 assessment 저장 뒤 다시 섞지 않는다. 한 evaluation은 하나의 고정 snapshot만 사용한다.

## Snapshot 계약

`input_snapshot_version`은 다음을 key 정렬한 canonical JSON의 SHA-256이다.

```text
schema_version
local_date
safety.selfHarmUrge
```

내부 user ID, source timestamp, notes, dailyBrick 원문은 digest payload에 넣지 않는다. 저장소에는 digest, source record의 opaque reference, source `updatedAt`만 provenance로 저장하며 전체 DailyState JSON을 복제하지 않는다. 같은 날짜의 `selfHarmUrge`가 바뀔 때만 초기 rule의 input snapshot version이 바뀐다.

## 날짜와 timezone

- `local_date`는 날짜 타입으로 유지한다.
- `timezone`은 IANA 이름으로 검증하고 평가 record에 고정한다.
- timezone은 날짜를 변환하기 위한 값이 아니라 schedule instant와 평가 시각을 해석하기 위한 metadata다.
- DST의 존재하지 않는 local time은 다음 유효 instant로 이동한다.
- DST의 중복 local time은 첫 번째 instant를 사용하되 `(subject, local_date, rule_set_version, snapshot)` uniqueness로 하루 두 번 실행하지 않는다.

## Ownership

Repository query는 항상 `DailyState.user_id == authenticated_user.id`와 `DailyState.date == local_date`를 함께 사용한다. 다른 사용자의 record ID나 assessment ID를 추측해도 데이터가 섞이지 않아야 한다.

## 향후 입력

Morning/Evening Check-in 또는 Weekly Report가 추가돼도 자동으로 risk source가 되지 않는다. 새 source는 freshness, consent, snapshot field allowlist, missing 규칙과 version migration을 먼저 정의해야 한다.

## 관련 문서

- [Scope and Terminology](daily-risk-scope-and-terminology.md)
- [Rule Engine](daily-risk-rule-engine.md)
- [Idempotency and Versioning](daily-risk-idempotency-versioning.md)
- [Security and Privacy](daily-risk-security-privacy.md)
