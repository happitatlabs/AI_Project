# Delivery Checklist and Package Acceptance Test Contract

- 문서 상태: Draft for implementation review
- 목적: Priority 3 구현 전에 domain, persistence, security, recovery acceptance 고정

## 테스트 원칙

- 실제 고객 정보, 개인 연락처, 실제 local path를 fixture에 사용하지 않는다.
- pure policy test와 실제 저장/filesystem 통합 test를 구분한다.
- assertion은 외부 상태, version, audit, archive bytes/checksum, 재시작 복구를 검증한다.
- 실패를 위해 validation, permission, checksum을 약화하지 않는다.

## Checklist

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| CL-001 | 신규 Pilot checklist 생성 | current template snapshot, version 0, `checklist_created` 1개 |
| CL-002 | required/optional item | 안정적인 item key와 requirement 유지 |
| CL-003 | required missing | readiness `not_ready`, blocking item 포함 |
| CL-004 | optional missing | warning만 생성, 다른 required 충족 시 ready 가능 |
| CL-005 | artifact 존재/유효 | `present`, fingerprint와 검증 시각 기록 |
| CL-006 | artifact 삭제/bytes 변경 | `stale`, assembly 차단 |
| CL-007 | 허용 required waiver | `waived`, warning/audit, reason 미노출 |
| CL-008 | waiver 금지 item | validation/state conflict, 불변 |
| CL-009 | 권한 없는 waiver | forbidden, version/audit 불변 |
| CL-010 | stale checklist version | version conflict, item 불변 |
| CL-011 | template version 변경 | 기존 instance 자동 변형 없음, stale/rebase 필요 |
| CL-012 | 수동 present 시도 | artifact 검증 없이는 거부 |

## Readiness와 Priority 2

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| RD-001 | 모든 required present | Pilot approved일 때 `ready` |
| RD-002 | required missing/invalid/pending | `not_ready` |
| RD-003 | allowed required waived | ready 가능 + warning |
| RD-004 | approved 이전 assembly | `delivery_state_conflict` |
| RD-005 | approved + ready | assembly request 허용 |
| RD-006 | delivered 조회 | checklist/package read-only 조회 가능 |
| RD-007 | stale optional artifact | `stale`, assembly 차단 |
| RD-008 | expected Pilot/checklist version mismatch | 상태/idempotency/audit 불변 |
| RD-009 | 기존 DOCX resolver | 내부 path 없이 availability/fingerprint 재사용 |

## Package assembly와 idempotency

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| PA-001 | 정상 조립 | pending→assembling→assembled, 각 version/audit 1회 |
| PA-002 | 같은 key/payload 재시도 | 최초 result replay, 중복 package/audit 없음 |
| PA-003 | 같은 key/다른 payload | idempotency conflict, 기존 결과 불변 |
| PA-004 | 다른 key/같은 fingerprint 동시 요청 | active/assembled package 1개 |
| PA-005 | 두 worker 동시 claim | 하나만 assembling lease 획득 |
| PA-006 | required artifact 누락 | request 차단, archive/idempotency 성공 없음 |
| PA-007 | checksum/manifest | entry 및 package checksum 재계산 일치 |
| PA-008 | 안전한 entry 이름 | 고정 allowlist path만 존재 |
| PA-009 | process restart during assembling | lease/recovery 계약에 따라 재개 또는 failed, 중복 package 없음 |
| PA-010 | partial write/rename 실패 | 외부 참조 없음, safe failure code, staging 격리 |
| PA-011 | failed retry | source current일 때 pending, attempt/audit 증가 |
| PA-012 | source 변경 후 retry | stale conflict, 새 readiness/request 필요 |
| PA-013 | 새 package 성공 | 이전 assembled를 보존하고 원자적으로 superseded 표시 |
| PA-014 | assembly 성공 | Pilot 상태 자동 delivered 전이 없음 |

## Transaction fault injection

| ID | 실패 지점 | 기대 결과 |
| --- | --- | --- |
| TX-001 | checklist audit insert | item/checklist/idempotency rollback |
| TX-002 | idempotency result insert | 상태/audit rollback |
| TX-003 | assembly request audit | request/idempotency rollback |
| TX-004 | manifest DB insert | assembled 상태와 download reference 없음 |
| TX-005 | assembled status update | manifest/reference commit 없음 |
| TX-006 | previous package supersede update | 새 package 완료 transaction rollback |
| TX-007 | filesystem final rename | DB remains non-assembled, safe failure/recovery |
| TX-008 | DB commit after rename | orphan 격리/recovery, 외부 download 불가 |

## Security

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| SE-001 | `../`, absolute, drive/UNC entry | validation 거부 |
| SE-002 | source symlink/hard link | allow root 검사에서 거부 |
| SE-003 | 예상하지 않은 content type | `invalid_artifact` |
| SE-004 | manifest/응답 scan | 내부 path, 원본 filename, raw text, bundle ID 없음 |
| SE-005 | error response | stack trace, SQL, local username 없음 |
| SE-006 | application log | waiver reason/package content/path 원문 없음 |
| SE-007 | 권한 없는 package/download | forbidden 또는 은닉형 not found |
| SE-008 | 다른 project package ID 추측 | project isolation 유지 |
| SE-009 | checksum 불일치 download | reference 미발급, integrity failure |
| SE-010 | fixture scan | 실제 개인정보, 이메일, 전화번호 없음 |
| SE-011 | package size limit | 개별/총 size 초과 차단 |

## Operator UX contract

- `loading`, `empty`, `ready`, `not_ready`, `assembling`, `assembled`, `failed`, `stale`, `conflict`, `unauthorized` 렌더링.
- keyboard-only item/waiver/assembly/manifest 흐름.
- 상태를 색상만으로 표현하지 않음.
- async 완료/오류 후 focus와 복구 행동 검증.
- 중복 클릭이 중복 command/package를 만들지 않음.

## Regression

구현 PR은 최소 다음 기존 suite를 다시 실행한다.

- Daily Check-in
- DOCX 생성과 재열기
- 1페이지 요약/표/provenance
- project/run 결과 보관
- Persistent Pilot State
- Approval Queue
- runtime-core
- 전체 suite의 기존 failure 목록 비교

## Service operation 연결

| Operation | Acceptance IDs |
| --- | --- |
| `GetDeliveryChecklist` / `GetDeliveryChecklistItem` | CL-001~006, SE-004/007~008 |
| `VerifyChecklistItem` | CL-005~006/010/012, TX-001~002, SE-003/006 |
| `WaiveChecklistItem` | CL-007~010, TX-001~002, SE-006~008 |
| `GetDeliveryReadiness` | RD-001~009 |
| `RequestPackageAssembly` | PA-001~006, RD-004~008, TX-003 |
| `GetPackageAssembly` / `RetryPackageAssembly` | PA-009~012, SE-007~008 |
| `GetPackageManifest` | PA-007~008, SE-001~005 |
| `GetPackageDownloadReference` | SE-007~009/011 |
| `ListDeliveryPackages` | PA-013, SE-004/007~008 |
| `GetDeliveryAuditHistory` | TX-001~006, SE-004/006~008 |

## Open Decisions

- 실제 storage에 맞는 process restart/lease fixture
- exact size limits와 allowed MIME/magic signatures
- download reference integration test 방식
- delivered 이후 correction/reassembly acceptance
- retention/cleanup 장기 test 범위

## 관련 문서

- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Manifest Contract](delivery-package-manifest.md)
- [Assembly Lifecycle](delivery-package-assembly.md)
- [API Contract](delivery-package-api-contract.md)
- [Operator UX](delivery-package-operator-ux.md)
- [Persistence ADR](ADR-delivery-package-persistence.md)
