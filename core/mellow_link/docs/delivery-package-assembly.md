# Delivery Package Assembly Lifecycle

- 문서 상태: Implementation contract
- 대상: 조립 request, 동기 실행 상태, idempotency, 재시작 복구

## Canonical 상태

persisted assembly record가 없으면 `not_requested`로 표현하지만 저장 상태 값에는 포함하지 않는다.

```text
pending
assembling
assembled
failed
superseded
```

`retrying`은 command/event이며 별도 장기 상태가 아니다.

## 상태 전이

| 현재 | event | 다음 | 규칙 |
| --- | --- | --- | --- |
| 없음 | `request_assembly` | `pending` | readiness snapshot과 idempotency를 원자적으로 저장 |
| `pending` | `start_assembly` | `assembling` | 같은 요청을 처리하는 service가 expected version으로 claim |
| `assembling` | `complete_assembly` | `assembled` | manifest, archive reference, checksums와 원자적 완료 |
| `assembling` | `fail_assembly` | `failed` | 안전한 failure code만 저장 |
| `failed` | `retry_assembly` | `pending` | retry count/policy 검사, 같은 source snapshot 유지 |
| `assembled` | `supersede_package` | `superseded` | 새 package가 성공적으로 확정될 때 이전 record를 원자적으로 표시 |

`assembled` package를 같은 record에서 다시 `assembling`으로 되돌리지 않는다. source가 바뀐 재조립은 새 assembly/package record다.

## Request identity와 idempotency

Canonical request fingerprint는 다음을 정렬·직렬화해 계산한다.

- `pilot_id`
- `source_pilot_version`
- `checklist_id`와 `checklist_version`
- `template_version`
- `artifact_set_fingerprint`
- output profile와 manifest version

모든 mutation은 actor scope의 `idempotency_key`를 요구한다.

- 같은 key + 같은 fingerprint: 최초 assembly view를 반환하며 record/audit를 추가하지 않는다.
- 같은 key + 다른 payload/fingerprint: `idempotency_key_reused` conflict.
- 다른 key + 같은 fingerprint: 기존 active/assembled assembly를 반환하거나 명시적 `assembly_already_exists` conflict. 중복 archive는 만들지 않는다.
- 다른 fingerprint: Pilot이 여전히 `approved`이고 현재 readiness가 `ready`일 때만 새 request를 만들 수 있다.

영속 idempotency record를 사용하며 프로세스 메모리 Map만으로 처리하지 않는다.

## 동시성

- request에는 `expected_pilot_version`, `expected_checklist_version`, `artifact_set_fingerprint`가 필요하다.
- conditional insert/unique constraint 또는 동등한 저장 계층 보호로 동일 fingerprint의 active assembly를 하나만 허용한다.
- Phase 3은 외부 worker framework가 없는 현재 저장소에 맞춰 요청 thread가 동기적으로 assembly를 수행한다.
- service는 `expected_assembly_version` 조건부 갱신으로 pending record를 claim한다. 동시에 두 요청이 들어와도 하나만 `assembling`이 된다.
- 상태, version, audit, idempotency result는 동일 DB transaction이다.

## File/DB transaction 경계

filesystem과 DB는 하나의 ACID transaction이 될 수 없으므로 다음 visibility protocol을 사용한다.

1. DB에서 request를 `pending`으로 원자 저장한다.
2. 요청을 처리하는 service가 조건부 갱신으로 `assembling`을 획득한다.
3. 비공개 staging 디렉터리에 고유 임시 이름으로 archive를 작성한다.
4. archive를 재열고 manifest/entry checksum/size를 검증한다.
5. 같은 filesystem의 final archive root로 atomic rename한다.
6. manifest record, final opaque artifact reference, checksum, `assembled` 상태와 audit을 한 DB transaction으로 저장한다.
7. DB commit 전에는 download reference를 발급하지 않는다.

5단계 뒤 DB commit이 실패하면 final file은 orphan 후보이며 recovery가 참조 record 없이 식별해 격리한다. orphan path는 API나 일반 로그에 노출하지 않는다.

## 재시작 복구

- `pending`: 요청 처리 또는 명시적 retry가 다시 claim할 수 있다.
- `assembling`이 10분 이내면 다른 요청이 건드리지 않는다.
- `assembling`이 10분을 넘으면 process interruption으로 간주한다. service 시작 및 assembly/retry 호출 전 recovery가 staging/final checksum과 DB record를 검사해 `failed`로 전환하고, 자동 성공으로 추측하지 않는다.
- 완성 파일과 manifest가 검증되지만 DB 완료가 없는 경우 자동 성공으로 추측하지 않는다. recovery policy에 따라 재연결 또는 격리하며 audit를 남긴다.
- partial/staging file은 외부 download 대상이 아니다.

## 실패와 retry

- failure에는 allowlist `failure_code`, 발생 시각, attempt만 저장한다.
- 내부 exception, path, raw content는 응답/audit/application log에 복제하지 않는다.
- retry는 같은 source fingerprint에서만 가능하다. source가 바뀌면 새 readiness 검증과 새 request가 필요하다.
- 자동 retry와 background backoff는 없다. 운영자의 명시적 retry만 허용하며 최초 attempt를 포함해 최대 3회다.

## Priority 2 연결

- assembly request는 `approved`에서만 가능하다.
- assembly 성공은 `pilot_delivered`를 자동 생성하지 않는다.
- 실제 전달은 기존 Priority 2 `deliver` command로 별도 기록한다.
- `delivered`에서는 package와 manifest 조회만 허용하고 일반 재조립은 금지한다.
- approval queue와 assembly queue는 별도 read model이며 서로 상태를 복제하지 않는다.

## Audit events

```text
package_assembly_requested
package_assembly_started
package_assembled
package_assembly_failed
package_assembly_retried
package_superseded
```

## 구현 결정

- 별도 durable worker, lease, heartbeat, periodic recovery scheduler를 도입하지 않는다. 동기 service와 조건부 상태/version 갱신을 사용한다.
- stale `assembling` 기준은 10분이며 recovery는 service 시작과 assembly/retry 진입 시 수행한다. recovery event는 append-only audit로 남긴다.
- retry는 운영자 수동 방식, 최대 3 attempts, 자동 backoff 없음이다. `invalid_artifact`, `readiness_stale`, `package_size_exceeded`는 source를 수정하고 새 request를 만들어야 하므로 같은 record에서 retry할 수 없다.
- staging/부분 파일은 24시간 뒤 recovery에서 삭제한다. 최종 위치의 미참조 orphan은 외부에 노출하지 않고 격리하며 자동 삭제하지 않는다.
- archive는 기존 project/run result root 아래 전용 `delivery_packages` 디렉터리에 저장한다. staging은 같은 filesystem의 sibling 비공개 디렉터리를 사용해 atomic rename을 보장한다.
- delivered 이후 정정·재납품은 Phase 3 범위 밖이다. 새 run과 새 Pilot을 만들며 terminal Pilot과 기존 package를 변경하지 않는다.

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Pilot API Contract](pilot-api-contract.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Manifest Contract](delivery-package-manifest.md)
- [API Contract](delivery-package-api-contract.md)
- [Persistence ADR](ADR-delivery-package-persistence.md)
- [Test Contract](delivery-package-test-contract.md)
