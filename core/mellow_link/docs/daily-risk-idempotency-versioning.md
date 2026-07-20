# Daily Risk Idempotency and Versioning Contract

## Command identity

상태 변경 command는 client가 제공한 non-secret idempotency key를 subject scope 안에서 사용한다. DB에는 key의 SHA-256 hash와 canonical request hash만 저장한다.

Evaluation logical identity에는 다음이 포함된다.

- subject user internal scope
- local date와 IANA timezone
- input snapshot version
- rule set version
- command 종류

Manual과 scheduled trigger가 같은 logical evaluation을 요청하면 중복 assessment를 만들지 않는다. Trigger source는 audit metadata로만 남긴다.

## Replay 규칙

| 상황 | 결과 |
| --- | --- |
| 동일 key + 동일 payload | 기존 성공 또는 진행 결과 반환; 새 audit 없음 |
| 동일 key + 다른 payload | `idempotency_conflict`; 변경 없음 |
| 다른 key + 동일 logical identity | canonical uniqueness로 기존 evaluation 반환 |
| input snapshot 변경 | 새 evaluation; 성공 시 이전 결과 supersede |
| rule set 변경 | 새 evaluation; 이전 결과 보존 |
| 프로세스 재시작 | 영속 command result로 같은 결과 replay |

## Optimistic concurrency

Evaluation, assessment action, schedule preference는 정수 version을 가진다. mutation은 exact `expected_version`을 조건부 갱신에 포함한다. 낮거나 높은 값 모두 `version_conflict`이며 상태, audit, command result가 바뀌지 않는다. 성공한 mutation은 정확히 한 번 증가한다.

## 동시성

동일 command의 동시 요청 중 하나만 idempotency record를 생성한다. 동일 logical evaluation을 다른 key로 동시에 요청해도 unique constraint와 transaction으로 하나만 생성한다. 충돌한 caller는 canonical record를 다시 읽는다.

## 저장 수명

초기 구현은 assessment와 재현성에 필요한 idempotency record를 자동 삭제하지 않는다. 파괴적 retention은 건강 데이터 삭제·계정 정책과 함께 별도 결정한다.
