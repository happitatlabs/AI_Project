# Delivery Checklist and Package Service Contract

- 문서 상태: Implementation contract
- 계약 수준: transport-neutral service contract
- 비대상 범위: FastAPI router, schema code, DB implementation

## 공통 원칙

1. checklist/readiness/package 정책은 service 계층에서 권한과 project ownership을 다시 검사한다.
2. mutation은 `expected_version`과 `idempotency_key`를 사용한다.
3. 상태 변경, audit, idempotency 결과는 하나의 transaction이다.
4. URL과 HTTP method는 아래 FastAPI transport mapping을 따른다.
5. 응답은 opaque reference와 안전한 code만 사용하고 내부 경로/원본 filename/raw content를 반환하지 않는다.

## Capability 및 역할 매핑

| capability | 동작 |
| --- | --- |
| `delivery.checklist.read` | 접근 가능한 Pilot checklist/readiness 조회 |
| `delivery.checklist.create` | 현재 template으로 Pilot checklist 생성 |
| `delivery.checklist.verify` | item 검증 요청/확인 |
| `delivery.waive` | 허용된 item waiver |
| `delivery.package.assemble` | package assembly 요청·retry |
| `delivery.package.read` | assembly/manifest/package 목록 조회 |
| `delivery.package.download` | 무결성 검증 후 안전한 download reference 발급 |
| `delivery.audit.read` | checklist/package audit 조회 |

| role | 허용 capability |
| --- | --- |
| `USER` | 소유 프로젝트의 `delivery.checklist.read`, `delivery.package.read` |
| `ADMIN` | 위 읽기와 create, verify, waive, assemble/retry, download, audit. mutation마다 대상 project 존재와 scope를 service에서 확인 |
| `GUEST` | 없음 |

현재 저장소에는 별도 tenant/capability store가 없으므로 capability는 위 `UserRole` mapping으로 구현한다. 새로운 인증 체계를 만들지 않으며 router 검사만 신뢰하지 않는다.

## FastAPI transport mapping

| Operation | Method and path |
| --- | --- |
| checklist 생성/조회 | `POST/GET /pilot-delivery/pilots/{pilot_id}/checklist` |
| item 조회/검증/waiver | `GET /pilot-delivery/pilots/{pilot_id}/checklist/items/{item_key}`, `POST .../verify`, `POST .../waive` |
| readiness | `GET /pilot-delivery/pilots/{pilot_id}/readiness` |
| assembly 요청/조회/retry | `POST /pilot-delivery/pilots/{pilot_id}/assemblies`, `GET /pilot-delivery/assemblies/{assembly_id}`, `POST .../retry` |
| package 목록/manifest | `GET /pilot-delivery/pilots/{pilot_id}/packages`, `GET /pilot-delivery/packages/{package_id}/manifest` |
| download reference/사용 | `POST /pilot-delivery/packages/{package_id}/download-references`, `GET /pilot-delivery/downloads/{token}` |
| audit | `GET /pilot-delivery/pilots/{pilot_id}/audit` |

JSON response는 기존 router처럼 response model을 직접 반환하고 오류는 `detail.code`와 안전한 message를 사용한다. 목록 기본 limit은 50, 최대 100이며 opaque cursor를 사용한다.

## Operation 계약

### `CreateDeliveryChecklist`

- 입력: `pilot_id`, `idempotency_key`, actor.
- 전제: project 접근 + `delivery.checklist.create`; Pilot이 `delivered`가 아님.
- 결과: 현재 immutable template의 version 0 checklist와 item snapshot. 동일 Pilot/template version은 하나만 생성한다.
- audit: `checklist_created`; 같은 key/payload의 재요청은 기존 결과를 반환한다.
- 이미 같은 template checklist가 있고 다른 key로 요청하면 기존 checklist를 반환하며 추가 audit/idempotency 성공 record를 만들지 않는다.

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
- 결과: 동기 조립이 완료되면 `assembled`, 안전하게 실패하면 `failed`, 동일 요청이면 기존 결과를 반환한다. DB에는 `pending`과 `assembling` 전이가 모두 보존된다.
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
- assembly 상태 mutation: `expected_assembly_version`.
- idempotency key는 actor/client scope에서 영속 저장하며 command와 canonical request hash에 결합한다.
- 같은 key/payload는 프로세스 재시작 후에도 최초 응답을 반환한다.
- conflict/validation/권한 실패는 성공 idempotency result나 상태 전이 audit를 만들지 않는다.

## 구현 결정

- endpoint, 역할, pagination은 위 표를 따른다.
- download reference는 15분 single-use이며 token 사용 시 현재 인증과 권한을 다시 검사한다.
- idempotency, audit, checklist, manifest, package binary는 Phase 3에서 자동 삭제하지 않는다. download token은 만료/사용 상태를 유지하고 staging/부분 파일만 24시간 정책으로 정리한다.

## 관련 문서

- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Assembly Lifecycle](delivery-package-assembly.md)
- [Operator UX](delivery-package-operator-ux.md)
- [Test Contract](delivery-package-test-contract.md)
