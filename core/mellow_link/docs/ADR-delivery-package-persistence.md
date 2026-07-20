# ADR: Persistent Delivery Checklist and Package Assembly

- 상태: Accepted for Priority 3 implementation
- 날짜: 2026-07-18
- 결정 범위: checklist, readiness evidence, package assembly, manifest, audit, idempotency
- 비결정 범위: UI 구현, 장기 파괴적 retention, delivered 정정/재납품 자동화

## Context

Priority 1은 결정적 project/run archive에 고객 검토용 DOCX를 만들고, Priority 2는 Pilot 검토·승인·전달 상태를 영속화한다. 그러나 운영자가 필요한 artifact를 매번 수동 확인하거나 package를 임시 폴더에서 조립하면 다음 문제가 남는다.

- 누락된 required artifact가 전달 단계까지 발견되지 않을 수 있다.
- artifact 변경 뒤 이전 확인 결과가 그대로 남을 수 있다.
- 재시도와 동시 요청이 중복 ZIP을 만들 수 있다.
- package 구성, checksum, source version을 재현하기 어렵다.
- filesystem 성공과 DB 상태 성공 사이의 부분 실패를 복구하기 어렵다.
- 내부 path와 원본 filename이 package/manifest로 새어 나갈 수 있다.

## Decision

다음 영속 논리 record를 분리한다.

1. immutable `ChecklistTemplate` version
2. Pilot별 `ChecklistInstance`와 item validation snapshot
3. checklist/package mutation의 append-only audit
4. 영속 idempotency command result
5. `PackageAssembly` request/attempt 상태와 동기 claim/recovery 정보
6. assembled package의 immutable manifest와 opaque artifact reference

Readiness는 저장된 수동 boolean이 아니라 Pilot/checklist/artifact version에서 파생한다. Approval Queue와 Package Assembly Queue도 각 권위 상태의 read model이다.

## 저장 및 관계 불변 조건

- 활성 checklist는 `(pilot_id, template_version)` 논리 중복을 저장 계층에서 막는다.
- item은 `(checklist_id, item_key)`로 유일하다.
- 동일 canonical assembly fingerprint의 active/assembled package는 하나다.
- manifest와 assembled package bytes는 생성 뒤 수정하지 않는다.
- 새로운 source snapshot은 새 package version을 만들고 이전 package를 보존하거나 `superseded`로 표시한다.
- idempotency result는 actor scope key + canonical request hash에 결합한다.

## Transaction 경계

반드시 원자적인 DB 작업:

- checklist/item 상태 변경 + checklist version + audit + idempotency result
- waiver + actor/time/reason + audit + idempotency result
- assembly request + source snapshot + audit + idempotency result
- assembly state/version 변경 + audit
- manifest metadata + final artifact reference + `assembled` + audit
- failure code + `failed` + audit
- 새 package 완료 + 이전 package `superseded` 표시

어느 단계든 실패하면 해당 DB transaction은 rollback하며 성공 응답을 저장하지 않는다.

## Filesystem transaction protocol

DB와 filesystem의 분산 transaction을 가장하지 않는다. 비공개 staging, 완성 후 재열기/검증, 동일 filesystem atomic rename, 최종 DB commit 순서로 외부 visibility를 제어한다. DB가 `assembled`가 아니면 download reference를 발급하지 않는다.

재시작 recovery는 10분을 넘긴 `assembling`, staging file, final file, manifest/checksum record를 비교한다. 불완전 상태를 성공으로 자동 추측하지 않으며 안전한 failure/recovery audit를 남긴다.

## 고려한 대안

### 수동 boolean과 임시 ZIP

구현은 작지만 stale, 동시성, 감사, 부분 실패를 신뢰할 수 없어 채택하지 않는다.

### Pilot aggregate에 checklist/package JSON 포함

table 수는 줄지만 Priority 2 상태 version과 artifact lifecycle이 결합되고 append-only package 보존이 어려워 채택하지 않는다.

### 외부 workflow/object-storage 제품 즉시 도입

장기적으로 유용할 수 있으나 현재 범위에서 외부 전송, credential, 운영 복잡도를 확대하므로 채택하지 않는다.

### 별도 영속 aggregate + 파생 readiness/queue

Priority 2 의미를 유지하고 재시작, 동시성, audit, package version을 독립 검증할 수 있어 채택한다.

## Migration과 backfill

- 기존 approved/delivered Pilot을 자동으로 ready로 표시하지 않는다.
- 구현 migration은 새 구조를 additive하게 만든다.
- backfill이 필요하면 기존 archive resolver로 checklist를 생성하고 item을 `pending`으로 두며 명시적 검증을 거친다.
- 기존 DOCX bytes나 path를 DB payload로 복제하지 않는다.
- rollback은 새 기능 진입점을 제거하고 새 record를 inert하게 보존하는 비파괴 방식을 우선한다.

## Security

- artifact reference는 opaque하고 project ownership으로 보호한다.
- canonical path가 허용 root 안인지 검사하고 symlink/path traversal을 거부한다.
- package content, path, waiver 원문, customer payload를 application log에 기록하지 않는다.
- manifest는 안전한 filename과 checksum만 포함한다.
- 테스트는 합성 데이터만 사용한다.

## 비용과 위험

- 새 aggregate와 recovery worker가 필요하다.
- DB/file 경계는 운영 runbook과 orphan cleanup이 필요하다.
- template/policy version 관리가 추가된다.
- retention 정책이 정해지기 전 storage가 증가할 수 있다.

## 구현 결정

### Persistence와 additive migration

- 기존 SQLAlchemy ORM, SQLite, `Base.metadata.create_all()` additive schema 방식을 사용한다. 별도 ORM/migration framework와 파괴적 `ALTER/DROP`을 도입하지 않는다.
- opaque ID는 기존 Pilot과 같은 UUID4 hex를 사용하며 external response에는 hash 기반 safe reference만 제공한다.
- 물리 table은 다음과 같다.

| table | primary/foreign keys와 핵심 constraint |
| --- | --- |
| `delivery_checklist_templates` | `template_id` PK, `(template_key, template_version)` unique, immutable version metadata |
| `delivery_checklist_template_items` | `template_item_id` PK, template FK, `(template_id, item_key)` unique |
| `delivery_checklists` | `checklist_id` PK, Pilot/project/run/template FK, `(pilot_id, template_id, template_version)` unique, `version >= 0` |
| `delivery_checklist_items` | `checklist_item_id` PK, checklist FK, `(checklist_id, item_key)` unique, canonical status/version constraints |
| `delivery_package_assemblies` | `assembly_id` PK, checklist/Pilot/project/run FK, canonical fingerprint unique for non-superseded lifecycle, status/version/attempt constraints |
| `delivery_packages` | `package_id` PK, assembly FK unique, immutable manifest JSON, opaque storage reference, byte size/checksum |
| `delivery_audit_events` | `event_id` PK, Pilot/project/run FK, append-only safe event metadata |
| `delivery_command_results` | integer PK, actor FK, `(actor_id, idempotency_key)` unique, operation/request hash/result JSON |
| `delivery_download_references` | `reference_id` PK, package/actor FK, token digest unique, expiry/consumed timestamps |

모든 mutable aggregate는 timezone-aware `created_at`/`updated_at`과 version을 갖는다. 기존 record는 backfill하지 않고 첫 명시적 checklist 생성 때 초기화한다. rollback은 endpoint를 비활성화하고 새 table과 binary를 inert하게 보존한다.

### 권한과 API 경계

- 기존 `UserRole`과 Priority 2 service 계층 project ownership 검사를 재사용한다. 소유 `USER`와 `ADMIN`은 안전한 읽기, `ADMIN`은 verify/waive/assemble/retry/download/audit를 수행하고 `GUEST`는 거부한다.
- capability 이름과 endpoint는 [API Contract](delivery-package-api-contract.md)에 고정한다. 내부 numeric ID, path, 원본 filename은 반환하지 않는다.

### 크기와 content policy

- DOCX/개별 artifact 25 MiB, delivery note 64 KiB, artifact 20개, 압축 전 100 MiB, ZIP 50 MiB를 상한으로 한다.
- 허용 입력은 구조 검증된 OOXML DOCX와 제한된 UTF-8 plain text뿐이다. 배포 설정은 상한을 낮출 수만 있다.

### 실행, storage와 recovery

- 현재 저장소에 durable worker가 없으므로 외부 queue 없이 동기 assembly를 사용한다. 조건부 version 갱신이 동시 claim을 보호한다.
- 자동 retry/backoff는 없고 운영자 수동 retry만 최대 3 attempts다. `assembling` 10분 초과는 중단으로 판단하며 service 시작/assembly 진입 시 lazy recovery한다.
- 기존 project/run result filesystem root 아래 `delivery_packages`를 사용한다. 같은 filesystem의 비공개 staging에서 작성하고 atomic rename한다. symlink와 허용 root 이탈을 거부한다.
- download token은 256-bit opaque, DB에는 digest만 저장, 15분 single-use이며 redemption 시 권한과 checksum을 재검증한다.

### Retention과 delivered 호환성

- Phase 3은 checklist/item history, manifest, package binary, audit, idempotency record를 자동 삭제하지 않는다. staging/부분 파일은 24시간 뒤 정리하고 download reference는 15분 뒤 사용할 수 없다.
- `delivered`는 terminal이다. 정정/재납품은 새 run과 새 Pilot으로 처리하며 자동화는 범위 밖이다.
- 기존 Priority 2 `deliver`의 DOCX 존재 조건을 유지한다. assembled package를 새 필수 조건으로 추가하지 않아 기존 API/테스트/backfill에 영향이 없다.

## 비차단 후속 결정

- 장기 법적/운영 retention과 파괴적 삭제 정책
- 별도 durable worker 또는 object storage 도입 기준
- delivered 결과의 정정·재납품 UX와 운영 승인 정책

## 관련 문서

- [ADR: Persistent Pilot State](ADR-persistent-pilot-state.md)
- [Pilot State Machine](pilot-state-machine.md)
- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Assembly Lifecycle](delivery-package-assembly.md)
- [Manifest Contract](delivery-package-manifest.md)
- [Test Contract](delivery-package-test-contract.md)
