# Delivery Checklist and Package Service Contract

- 문서 상태: Draft for implementation review
- 계약 수준: transport-neutral service contract
- 비대상 범위: FastAPI router, schema code, DB implementation

## 공통 원칙

1. checklist/readiness/package 정책은 service 계층에서 권한과 project ownership을 다시 검사한다.
2. mutation은 `expected_version`과 `idempotency_key`를 사용한다.
3. 상태 변경, audit, idempotency 결과는 하나의 transaction이다.
4. 실제 URL과 HTTP method는 구현 PR에서 기존 routing 규칙에 맞춰 정한다.
5. 응답은 opaque reference와 안전한 code만 사용하고 내부 경로/원본 filename/raw content를 반환하지 않는다.

## Capability 초안

| capability | 동작 |
| --- | --- |
| `delivery.checklist.read` | 접근 가능한 Pilot checklist/readiness 조회 |
| `delivery.checklist.verify` | item 검증 요청/확인 |
| `delivery.waive` | 허용된 item waiver |
| `delivery.package.assemble` | package assembly 요청·retry |
| `delivery.package.read` | assembly/manifest/package 목록 조회 |
| `delivery.package.download` | 무결성 검증 후 안전한 download reference 발급 |
| `delivery.audit.read` | checklist/package audit 조회 |

현재 `UserRole`과 capability의 실제 매핑은 구현 PR 결정이다. ADMIN이라는 이유만으로 tenant/project 범위를 우회하지 않는다.

## Operation 계약

### `GetDeliveryChecklist`

- 입력: `pilot_id`, actor.
- 전제: project 접근 + `delivery.checklist.read`.
- 결과: template/instance version, item 상태, 안전한 artifact metadata.
- 실패: not found, forbidden.

### `GetDeliveryChecklistItem`

- 입력: `pilot_id`, `item_key`, actor.
- 결과: 한 item의 상태와 안전한 검증 code. 내부 resolver detail은 제외.

### `VerifyChecklistItem`

- 입력: `pilot_id`, `item_key`, `expected_checklist_version`, `idempotency_key`, actor.
- 전제: mutable Pilot 상태, assembly freeze 없음, verify capability.
- 결과: resolver 재검증 후 `present`, `missing`, `invalid`, `stale` 중 하나와 checklist version +1.
- audit: `checklist_item_verified`.
- 같은 key/payload replay는 version/audit를 늘리지 않는다.

### `WaiveChecklistItem`

- 입력: `pilot_id`, `item_key`, bounded `reason`, `expected_checklist_version`, `idempotency_key`, actor.
- 전제: `delivery.waive`, item의 `waiver_allowed=true`, mutable 상태.
- 결과: `waived`, checklist version +1.
- audit: `checklist_item_waived`; manifest/일반 로그에 reason 원문 미포함.

### `GetDeliveryReadiness`

- 입력: `pilot_id`, actor.
- 결과: `ready|not_ready|stale`, source versions, blocking item code, warnings, artifact set fingerprint.
- 읽기 호출은 상태나 audit를 변경하지 않는다.

### `RequestPackageAssembly`

- 입력: `pilot_id`, `expected_pilot_version`, `expected_checklist_version`, `artifact_set_fingerprint`, `manifest_version`, `idempotency_key`, actor.
- 전제: Pilot `approved`, readiness `ready`, assemble capability.
- 결과: `pending` assembly view 또는 동일 요청의 기존 결과.
- audit: `package_assembly_requested`.
- 상태/version/fingerprint 재검증과 request/idempotency 저장은 원자적이다.

### `GetPackageAssembly`

- 입력: opaque `assembly_id`, actor.
- 결과: 상태, version, 안전한 failure code, timestamps, package ref.
- 다른 project ID 추측 접근은 forbidden 또는 저장소 표준의 은닉형 not found.

### `RetryPackageAssembly`

- 입력: `assembly_id`, `expected_assembly_version`, `idempotency_key`, actor.
- 전제: `failed`, source fingerprint가 여전히 current, retry policy 허용.
- 결과: `pending`, version +1.
- audit: `package_assembly_retried`.

### `GetPackageManifest`

- 입력: `package_id`, actor.
- 전제: `assembled`, package read capability와 project access.
- 결과: [Manifest Contract](delivery-package-manifest.md)의 external-safe manifest.

### `GetPackageDownloadReference`

- 입력: `package_id`, actor.
- 전제: assembled, checksum 재검증, download capability.
- 결과: opaque, 제한 수명의 authorized reference와 package checksum/size metadata.
- 내부 filesystem path나 storage credential을 반환하지 않는다.

### `ListDeliveryPackages`

- 결정: 포함한다. 운영자가 이전 assembled/superseded package와 audit를 추적해야 한다.
- 입력: `pilot_id`, cursor, limit, actor.
- 정렬: `created_at DESC`, opaque stable tie-breaker.
- 결과: package id/ref, status, source versions, checksum, size, created_at. 내부 path 제외.

### `GetDeliveryAuditHistory`

- checklist/package mutation event를 안정적인 cursor로 조회한다.
- project access + `delivery.audit.read` 필요.
- payload, waiver reason 원문, 내부 exception/path는 제외한다.

## 공통 오류 계약

| code | 의미 |
| --- | --- |
| `delivery_not_found` | Pilot/checklist/item/assembly/package 없음 |
| `delivery_access_denied` | capability 또는 project scope 부족 |
| `delivery_validation_error` | 입력 형식/필수값 오류 |
| `delivery_version_conflict` | expected version 불일치 |
| `delivery_state_conflict` | 현재 상태에서 operation 불가 |
| `readiness_blocked` | blocking item 또는 Pilot 상태 불충족 |
| `readiness_stale` | template/artifact/source version 변경 |
| `idempotency_key_reused` | 같은 key의 다른 command/payload 사용 |
| `assembly_already_exists` | 동일 source fingerprint의 중복 조립 |
| `invalid_artifact` | allowlist/구조/content/size 위반 |
| `package_integrity_failed` | 저장 package checksum 불일치 |

오류에는 안전한 `code`, 수정 가능한 field 정보, 현재 version/status를 넣을 수 있다. stack trace, SQL, path, 원본 filename, raw payload는 금지한다.

## Version과 idempotency

- checklist mutation: `expected_checklist_version`.
- assembly request: Pilot/checklist version과 artifact fingerprint 모두 고정.
- worker mutation: `expected_assembly_version`.
- idempotency key는 actor/client scope에서 영속 저장하며 command와 canonical request hash에 결합한다.
- 같은 key/payload는 프로세스 재시작 후에도 최초 응답을 반환한다.
- conflict/validation/권한 실패는 성공 idempotency result나 상태 전이 audit를 만들지 않는다.

## Open Decisions

- 최종 endpoint/HTTP method와 response envelope
- 현재 role과 capability의 실제 매핑
- cursor format/page size
- download reference 수명과 인증 연동
- idempotency/audit/package retention

## 관련 문서

- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Assembly Lifecycle](delivery-package-assembly.md)
- [Operator UX](delivery-package-operator-ux.md)
- [Test Contract](delivery-package-test-contract.md)
