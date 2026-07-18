# ADR: Persistent Delivery Checklist and Package Assembly

- 상태: Proposed
- 날짜: 2026-07-18
- 결정 범위: checklist, readiness evidence, package assembly, manifest, audit, idempotency
- 비결정 범위: DB/ORM, 물리 table, migration 도구, object storage, UI

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
5. `PackageAssembly` request/attempt 상태와 worker lease
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
- worker state/lease/version 변경 + audit
- manifest metadata + final artifact reference + `assembled` + audit
- failure code + `failed` + audit
- 새 package 완료 + 이전 package `superseded` 표시

어느 단계든 실패하면 해당 DB transaction은 rollback하며 성공 응답을 저장하지 않는다.

## Filesystem transaction protocol

DB와 filesystem의 분산 transaction을 가장하지 않는다. 비공개 staging, 완성 후 재열기/검증, 동일 filesystem atomic rename, 최종 DB commit 순서로 외부 visibility를 제어한다. DB가 `assembled`가 아니면 download reference를 발급하지 않는다.

재시작 recovery는 만료 lease, staging file, final file, manifest/checksum record를 비교한다. 불완전 상태를 성공으로 자동 추측하지 않으며 안전한 failure/recovery audit를 남긴다.

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

## Open Decisions

- DB, ORM, 물리 table/index 및 migration 도구
- ID 생성 방식과 actor capability 매핑
- worker/lease 구현과 storage backend
- package/checklist/audit/idempotency 보존 기간
- orphan cleanup과 package size limit 구체 값
- delivered 정정 및 영구 취소/재납품 정책
- 현재 Priority 2 `deliver`에 assembled package를 필수화할지 여부

## 관련 문서

- [ADR: Persistent Pilot State](ADR-persistent-pilot-state.md)
- [Pilot State Machine](pilot-state-machine.md)
- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Assembly Lifecycle](delivery-package-assembly.md)
- [Manifest Contract](delivery-package-manifest.md)
- [Test Contract](delivery-package-test-contract.md)
