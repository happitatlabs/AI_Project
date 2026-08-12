# Daily Risk Evaluation Lifecycle

## 실행 상태

```text
queued -> evaluating -> completed
                    -> failed
completed -> superseded
```

- `queued`: command와 idempotency가 원자적으로 저장됨.
- `evaluating`: 한 evaluator가 exact version 조건으로 claim함.
- `completed`: assessment와 signal이 원자적으로 저장됨.
- `failed`: 안전한 error code와 retry count가 기록됨.
- `superseded`: 더 최신 snapshot 또는 rule set 결과가 canonical이 됨.

`not_evaluated`는 저장 상태가 아니며 record 부재다. `replayed`는 trigger type이지 lifecycle state가 아니다.

## 실행 방식

평가는 작은 구조화 snapshot을 대상으로 하는 동기식 결정적 service다. API는 blocking service boundary를 안전하게 호출한다. Scheduled run도 동일 service contract를 사용하며 scheduler record에는 health payload를 저장하지 않는다.

## Uniqueness와 실행

- canonical key: `(subject_user_id, local_date, input_snapshot_version, rule_set_version)`
- 동일 key 실행은 trigger가 manual/scheduled여도 기존 결과를 반환한다.
- project별이 아니라 subject별 하루 단위다.
- backfill은 한 요청 최대 31일이며 각 날짜가 독립 transaction이다.
- input 또는 rule version이 바뀌면 새 run을 만들고 성공 후 이전 canonical result를 supersede한다.

## Retry와 Recovery

- `evaluating`이 5분 이상 갱신되지 않으면 orphan candidate다.
- recovery는 expected version conditional claim으로 한 process만 실패 전환한다.
- 자동 반복 retry는 하지 않는다. subject user의 명시적 retry로 최대 3회까지 허용한다.
- old evaluator의 late commit은 run version/claim token 불일치로 차단한다.
- retry exhaustion은 `failed`로 남고 원문 exception 대신 bounded error code만 저장한다.

새 worker framework나 외부 queue는 도입하지 않는다.

## Scheduled Run과 DST

자동 schedule은 opt-in이며 기본 비활성이다. preference는 IANA timezone과 local execution time을 가진다. 존재하지 않는 DST 시간은 다음 유효 instant, 중복 시간은 첫 instant를 사용한다. canonical uniqueness가 같은 local date의 이중 평가를 방지한다.

## Transaction

- run 생성 + idempotency record
- assessment + signals + run completed + audit
- failure state + safe error audit
- new canonical result + previous result supersede links

각 묶음은 원자적이다.
