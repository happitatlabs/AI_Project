# Delivery Preparedness Checklist Model

- 문서 상태: Draft for implementation review
- 대상 범위: Pilot 납품 준비물의 논리 모델과 상태 규칙
- 비대상 범위: DB/ORM 선택, migration, API/UI 구현, 패키지 조립 코드

## 목적

한 `(project_id, run_id)` Pilot이 고객 전달용 패키지를 조립할 준비가 됐는지 재현 가능하게 판단한다. 체크리스트는 파일 존재 여부를 수동 체크박스로 대신하지 않고, 버전이 고정된 template과 실제 artifact 검증 결과를 결합한다.

## 논리 모델

### ChecklistTemplate

| 필드 | 규칙 |
| --- | --- |
| `template_id` | 안정적인 opaque 식별자 |
| `template_version` | 변경 불가능한 양의 정수 또는 버전 문자열 |
| `name` | 운영자 표시명 |
| `items` | 안정적인 `item_key` 순서 목록 |
| `created_at` | timezone-aware UTC instant |
| `retired_at` | 선택. 기존 instance를 삭제하지 않음 |

### ChecklistInstance

| 필드 | 규칙 |
| --- | --- |
| `checklist_id` | opaque 식별자 |
| `pilot_id` | Priority 2 Pilot 참조 |
| `project_id`, `run_id` | 권한과 artifact resolution을 위한 불변 참조 |
| `template_id`, `template_version` | 생성 시 고정 |
| `version` | 생성 시 0, 성공한 mutation마다 정확히 +1 |
| `created_at`, `updated_at` | timezone-aware UTC instant |
| `created_by_id` | opaque actor 참조 |
| `items` | item snapshot과 현재 검증 상태 |

동일 `(pilot_id, template_id, template_version)`의 활성 instance는 하나다. 새 template version 적용은 기존 instance를 덮어쓰지 않고 명시적 `rebase_checklist` command로 새 instance 또는 새 revision을 만든다.

### ChecklistItem

| 필드 | 규칙 |
| --- | --- |
| `item_key` | template 안에서 불변인 machine identifier |
| `display_name` | 운영자용 표시명 |
| `description` | 기대 artifact와 검증 방법의 짧은 설명 |
| `requirement` | `required` 또는 `optional` |
| `artifact_type` | 허용 목록의 논리 유형 |
| `source` | 기존 archive resolver 등 허용된 source 이름 |
| `status` | 아래 canonical 상태 중 하나 |
| `artifact_ref` | 내부 경로가 아닌 opaque reference |
| `artifact_fingerprint` | content hash와 검증 정책 버전으로 계산한 안전한 fingerprint |
| `verified_by_id`, `verified_at` | 마지막 성공 검증 주체와 시각 |
| `waived_by_id`, `waived_at` | waiver 적용 시 필수 |
| `waiver_reason` | 제한 길이의 운영 사유. 일반 로그 및 manifest에 원문 미포함 |
| `version` | item mutation마다 +1 |
| `created_at`, `updated_at` | UTC instant |

## Canonical item status

```text
pending
present
missing
waived
invalid
stale
```

| 상태 | 의미 | readiness 영향 |
| --- | --- | --- |
| `pending` | 아직 검증하지 않음 | required면 blocking, optional이면 warning |
| `present` | 허용된 resolver가 artifact와 fingerprint를 검증함 | 충족 |
| `missing` | artifact를 찾지 못함 | required면 blocking, optional이면 warning |
| `waived` | 권한 있는 운영자가 사유와 함께 예외 승인 | blocking 해제, 항상 warning과 audit 유지 |
| `invalid` | 형식, content type, size 또는 구조 검증 실패 | required면 blocking, optional이면 warning |
| `stale` | 저장된 fingerprint와 현재 artifact가 다르거나 template/policy가 변경됨 | requirement와 무관하게 재검증 전 blocking |

알 수 없는 값, 대소문자 별칭, 자동 보정은 허용하지 않는다.

## 기본 item 계약

초기 template은 최소 다음 논리 증거를 포함한다. 실제 파일명이나 물리 경로는 template에 넣지 않는다.

| item key | requirement | artifact type | 검증 |
| --- | --- | --- | --- |
| `external_report_docx` | required | `external_docx` | 기존 project/run archive의 DOCX가 열리고 external 경계를 통과함 |
| `one_page_summary` | required | `one_page_summary` | 외부 DOCX 안의 고정 요약 섹션 또는 별도 안전 artifact를 구조적으로 확인 |
| `provenance_summary` | required | `external_provenance` | 외부 허용 provenance가 존재하고 내부 경로/원문이 없음 |
| `delivery_note` | optional | `delivery_note` | 허용된 bounded metadata만 확인 |

하나의 DOCX가 여러 논리 item의 근거가 될 수 있지만 각 item은 독립 검증 결과와 정책 버전을 기록한다.

## Waiver 계약

- optional missing은 waiver 없이 warning으로 남는다.
- required item waiver는 `delivery.waive` capability를 가진 운영자만 수행한다.
- `external_report_docx` 자체는 waiver 금지다. 고객 전달 산출물이 없으면 package를 조립할 수 없다.
- 그 외 required waiver 허용 여부는 template item의 `waiver_allowed`로 명시한다.
- waiver에는 비어 있지 않은 제한 길이 사유, `expected_version`, `idempotency_key`가 필요하다.
- item 상태 변경, checklist version 증가, `checklist_item_waived` audit은 하나의 transaction이다.
- waiver reason 원문은 일반 로그, queue, manifest, 외부 응답에 복제하지 않는다.

## Artifact 변경과 재검증

- `present`는 artifact fingerprint와 검증 정책 버전에 결합된다.
- bytes, content type, resolver 결과 또는 검증 정책이 달라지면 `stale`로 파생하거나 원자적으로 전환한다.
- 운영자의 수동 체크만으로 `missing`, `invalid`, `stale`을 `present`로 바꿀 수 없다.
- 자동 resolver가 검증한 뒤 운영자는 확인 행위를 기록할 수 있지만 artifact 증거를 대체하지 않는다.
- template version mismatch는 전체 checklist를 stale로 취급하고 assembly를 차단한다.

## Pilot 상태 연계

- 조회: 프로젝트 접근 권한이 있으면 모든 Pilot 상태에서 가능하다.
- 검증/waiver/rebase: `draft`, `ready_for_review`, `under_review`, `changes_requested`, `approved`에서 정책에 따라 가능하다.
- assembly가 `assembling`인 동안 해당 source checklist mutation은 conflict다.
- `delivered`에서는 읽기 전용이다. 정정은 Priority 2의 delivered 정정 정책과 함께 별도 결정한다.

## Audit events

```text
checklist_created
checklist_item_verified
checklist_item_waived
checklist_rebased
```

성공한 mutation만 append하며 actor, 이전/다음 item 상태, result version, 안전한 artifact fingerprint reference를 기록한다. artifact bytes, 내부 경로, 원본 파일명, waiver 원문 전체는 audit metadata에 넣지 않는다.

## Open Decisions

- 실제 template 배포·version 부여 방식
- `external_report_docx` 외 required item의 waiver 허용 목록
- 검증 정책별 정확한 size/content 제한
- template rebase의 물리 저장 모델과 기존 instance 보존 기간
- 실제 역할과 `delivery.waive` capability 매핑

## 관련 문서

- [Delivery Readiness Contract](delivery-readiness-contract.md)
- [Delivery Package Manifest](delivery-package-manifest.md)
- [Delivery Package Assembly](delivery-package-assembly.md)
- [Delivery Package API Contract](delivery-package-api-contract.md)
- [Delivery Package Test Contract](delivery-package-test-contract.md)
- [ADR: Delivery Persistence and Transactions](ADR-delivery-package-persistence.md)
