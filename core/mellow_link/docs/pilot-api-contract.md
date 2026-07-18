# Pilot API and Service Contract

- 문서 상태: Draft for implementation review
- 계약 수준: transport-neutral service contract
- 비대상 범위: 라우터 구현, 스키마 코드, DB/ORM, migration, UI

## 설계 원칙

1. 상태 정책은 service 계층의 단일 전이 함수에서 검증한다.
2. 공개 API는 임의의 `status` PATCH보다 의도가 드러나는 명령을 제공한다.
3. 모든 생성/상태 변경 명령은 idempotency key를 요구하고, 모든 상태 변경 명령은 기대 버전을 검사한다.
4. 성공한 상태 변경과 감사 이벤트는 원자적으로 기록한다.
5. 감사 이벤트 이름과 상태 전이는 [Pilot State Machine](pilot-state-machine.md)의 권위 있는 전이표를 따른다.
6. queue와 audit 응답은 보고서 원문이나 내부 파일 정보를 포함하지 않는다.

## 공통 표현

### PilotStatus

```text
draft
ready_for_review
under_review
changes_requested
approved
delivered
```

### PilotView

응답의 논리 필드다. 실제 직렬화 도구는 구현 PR에서 정한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `pilot_id` | string | opaque Pilot 식별자 |
| `project_id` | string | 대상 프로젝트 |
| `run_id` | string | 대상 분석 run |
| `status` | PilotStatus | 현재 상태 |
| `version` | integer | 현재 동시성 버전 |
| `created_at` | RFC 3339 instant | 생성 시각 |
| `updated_at` | RFC 3339 instant | 최근 변경 시각 |
| `review_requested_at` | RFC 3339 instant or null | 최근 검토 요청 시각 |
| `reviewer_id` | string or null | 검토 담당자 식별자 |
| `review_started_at` | RFC 3339 instant or null | 검토 시작 시각 |
| `approved_by_id` | string or null | 승인자 식별자 |
| `approved_at` | RFC 3339 instant or null | 승인 시각 |
| `delivered_by_id` | string or null | 전달 처리자 식별자 |
| `delivered_at` | RFC 3339 instant or null | 전달 시각 |
| `change_request_reason` | string or null | 접근 권한이 있을 때만 보이는 최근 변경 사유 |
| `delivery_reference` | string or null | 제한된 전달 참조값 |

표시 이름, 이메일, 연락처는 이 응답에 복제하지 않는다. 필요한 표시 정보는 기존 사용자 표시 정책을 통해 별도로 결합한다.

## Service Contract

### `CreatePilot`

- 입력: `project_id`, `run_id`, `idempotency_key`, actor.
- 전제: actor가 `pilot.create`와 프로젝트 접근 권한을 가지고, run이 프로젝트에 속하며 동일 `(project_id, run_id)` Pilot이 없다.
- 결과: `draft`, `version = 0`인 PilotView와 `pilot_created` 감사 이벤트.
- 실패: validation, not found, forbidden, duplicate conflict.

### `GetPilot`

- 입력: `pilot_id`, actor.
- 전제: actor가 Pilot과 대상 프로젝트를 조회할 권한이 있다.
- 결과: PilotView.
- 실패: not found, forbidden.

### `TransitionPilotStatus`

모든 상태 변경 명령이 내부적으로 사용하는 중앙 정책 함수다.

- 입력: `pilot_id`, command, `expected_version`, `idempotency_key`, actor, command payload.
- 검증 순서: 입력 형식 → 인증/존재/접근 권한 → 기존 idempotency 결과 또는 key 충돌 → 기대 버전 → 현재 상태와 명령별 조건.
- 결과: 변경된 PilotView와 단 하나의 감사 이벤트.
- 원자성: aggregate 변경과 감사 이벤트가 함께 성공하거나 함께 실패한다.
- 공개 라우터에서 임의 `to_status`를 직접 받는 용도로 노출하지 않는다.

### 의도별 명령과 테스트 추적

| Service operation / event | 선행 상태 | 성공 상태/결과 | capability | 필수 입력 | audit event | Acceptance IDs |
| --- | --- | --- | --- | --- | --- | --- |
| `CreatePilot` / `create` | Pilot 없음 | `draft`, version 0 | `pilot.create` + 프로젝트 접근 | `project_id`, `run_id`, `idempotency_key` | `pilot_created` | ST-001, ER-003~005, CC-010, AU-001~002 |
| `SubmitForReview` / `submit` | `draft` | `ready_for_review`, version +1 | `pilot.submit` + 프로젝트 접근 | `expected_version`, `idempotency_key` | `pilot_submitted` | ST-002, ST-106~108, CC-006/008~009, AU-001~002 |
| `StartReview` / `start_review` | `ready_for_review` | `under_review`, reviewer 설정, version +1 | `pilot.review` | `expected_version`, `idempotency_key` | `pilot_review_started` | ST-003, ST-105~108, CC-004/006/008~009, AU-003 |
| `ApprovePilot` / `approve` | `under_review` | `approved`, 승인자/시각 설정, version +1 | `pilot.review` | `expected_version`, `idempotency_key` | `pilot_approved` | ST-004, ST-102~108, CC-001~005, AU-003~005 |
| `RequestChanges` / `request_changes` | `under_review` | `changes_requested`, 사유 설정, version +1 | `pilot.review` | `reason`, `expected_version`, `idempotency_key` | `pilot_changes_requested` | ST-005, ST-105~108, VL-004~005, CC-002/005/008, AU-003 |
| `ResubmitPilot` / `resubmit` | `changes_requested` | `ready_for_review`, 새 요청 시각, version +1 | `pilot.submit` + 프로젝트 접근 | `expected_version`, `idempotency_key` | `pilot_resubmitted` | ST-006, ST-106~108, CC-006/008~009, AU-001~002 |
| `MarkDelivered` / `deliver` | `approved` | `delivered`, 전달자/시각 설정, version +1 | `pilot.deliver` | `expected_version`, `idempotency_key`; `delivery_reference` 선택 | `pilot_delivered` | ST-007, ST-101/106~108, CC-006~008, AU-004 |
| `ListPilotQueue` / `GetPendingQueue` / `GetDeliveredQueue` | 해당 없음 | 다섯 기본 목록 또는 지정 상태 목록 | 요청 상태에 따른 `pilot.review` 또는 `pilot.deliver` | 허용된 filters, cursor, limit | 없음 | QU-001~010, AU-003/006/008 |
| `GetAuditHistory` | 모든 상태 | 순서가 안정적인 감사 이력 | `pilot.audit.read` + 프로젝트 접근 | `pilot_id`, cursor, limit | 없음 | AD-001~007, AU-006~007 |

운영 문구의 Reject/반려는 `RequestChanges`와 같은 operation이다. 결과 상태는 `changes_requested`이며 별도 상태를 추가하지 않는다.

### `ListPilotQueue`

- 입력: actor, 허용된 상태 필터, reviewer 필터, project 필터, 기간, cursor, limit.
- 기본 목록: 검토 대기(`ready_for_review`), 검토 중(`under_review`), 변경 요청(`changes_requested`), 승인 완료(`approved`), 전달 완료(`delivered`).
- 결과: 선택한 상태의 최소 메타데이터 queue item 목록과 다음 cursor.
- 권한: 검토 대기/중/변경 요청은 `pilot.review`, 승인 완료/전달 완료는 `pilot.deliver`를 요구한다. 두 범주의 상태를 함께 요청하면 두 capability가 모두 필요하며 각 프로젝트 접근 범위도 적용한다.
- 실패: unauthorized, forbidden, invalid filter.

### `GetPendingQueue`

- `ListPilotQueue`의 검토 대기/검토 중 preset이다.
- 입력: actor, reviewer 필터, project 필터, 기간, cursor, limit.
- 기본 상태: `ready_for_review`, `under_review`.
- 기본 정렬: `review_requested_at ASC` 뒤 안정적인 cursor tie-breaker.
- 결과: 최소 메타데이터의 queue item 목록과 다음 cursor.
- 실패: unauthorized, forbidden, invalid filter.

### `GetDeliveredQueue`

- 입력: actor, project 필터, 전달 기간, cursor, limit.
- 상태: `delivered`로 고정.
- 기본 정렬: `delivered_at DESC` 뒤 안정적인 cursor tie-breaker.
- 결과: 읽기 전용 delivered item 목록.

### `GetAuditHistory`

- 입력: `pilot_id`, actor, cursor, limit.
- 전제: `pilot.audit.read`와 프로젝트 접근 범위.
- 정렬: `occurred_at ASC`, 안정적인 `event_id ASC`.
- 결과: 상태 전이 메타데이터 목록. 보고서 본문과 파일 정보는 제외.

## Transport Mapping

최종 API URL, HTTP method, 프레임워크, request/response envelope는 이번 문서에서 확정하지 않는다. 어떤 transport를 선택하더라도 위 Service Contract, 오류 분류, 권한, version, idempotency, 감사 원자성을 그대로 적용해야 한다.

## 명령 요청 예시

### 승인

```json
{
  "expected_version": 2,
  "idempotency_key": "opaque-client-command-id"
}
```

### 변경 요청/반려

```json
{
  "expected_version": 2,
  "idempotency_key": "opaque-client-command-id",
  "reason": "표현 범위와 external 노출 항목을 다시 확인해 주세요."
}
```

### 전달 완료

```json
{
  "expected_version": 3,
  "idempotency_key": "opaque-client-command-id",
  "delivery_reference": "delivery-ticket-reference"
}
```

idempotency key와 전달 참조값은 비밀키나 고객 연락처가 아니다. 서버는 길이와 허용 문자 정책을 적용하고 일반 로그에 원문을 남기지 않는다.

## QueueItem 초안

| 필드 | 설명 |
| --- | --- |
| `pilot_id` | 상태 변경용 opaque 식별자. 민감한 내부 key를 UI label로 사용하지 않음 |
| `project_ref` | 안전한 프로젝트 표시 reference |
| `project_display_name` | 권한 범위 안에서 허용된 프로젝트 표시명 |
| `run_ref` | 운영자가 구분 가능한 안전한 run reference |
| `status` | 현재 PilotStatus |
| `version` | 변경 명령에 사용할 현재 버전 |
| `created_at` | Pilot 생성 시각 |
| `updated_at` | 마지막 성공 변경 시각 |
| `review_requested_at` | 대기 시작 기준 시각 |
| `reviewer_display` | 현재 담당 운영자의 허용된 표시값 또는 null |
| `review_started_at` | 검토 시작 시각 또는 null |
| `approved_at` | 승인 시각 또는 null |
| `delivered_at` | 전달 시각 또는 null |
| `docx_available` | 검토용 DOCX 존재 여부 boolean. 파일 경로는 포함하지 않음 |

QueueItem에는 보고서 원문, 원본 파일명, 내부 경로, bundle ID 같은 민감한 내부 식별자를 넣지 않는다. 상세 검토는 권한이 적용된 별도 상세 조회 또는 기존 결과 화면을 사용한다. external 고객 응답에는 QueueItem을 노출하지 않는다.

## 오류 계약

| 분류 | 코드 예시 | 의미 |
| --- | --- | --- |
| Validation | `invalid_pilot_status`, `reason_required` | 입력 형식 또는 필수값 오류 |
| Unauthorized | `authentication_required` | 인증 없음/만료 |
| Forbidden | `pilot_access_denied` | capability 또는 프로젝트 접근 범위 부족 |
| Not found | `pilot_not_found`, `project_run_not_found` | 대상이 존재하지 않음 |
| Duplicate | `pilot_already_exists` | 같은 논리 식별자 Pilot 중복 생성 |
| Invalid transition | `pilot_transition_not_allowed` | 현재 상태에서 명령 불가 |
| Concurrency | `pilot_version_conflict` | 기대 버전이 현재 버전과 다름 |
| Idempotency conflict | `idempotency_key_reused` | 같은 키가 다른 명령 payload에 사용됨 |

오류 응답은 `code`, 안전한 `message`, `current_status`와 `current_version`(충돌일 때), `field_errors`(validation일 때)를 포함할 수 있다. 보고서 원문과 내부 예외 문자열은 반환하지 않는다.

## Idempotency 계약

- 모든 생성/상태 변경 명령은 idempotency key를 요구한다.
- key는 operation과 actor/client scope 안에서 해석하고 최초 payload에 결합한다. `create`는 아직 `pilot_id`가 없으므로 논리 대상 `(project_id, run_id)`도 결합한다.
- 같은 key와 같은 operation/payload의 재시도는 최초 응답과 result version을 재사용하고 새 감사 이벤트를 생성하지 않는다.
- 같은 key에 다른 operation 또는 payload가 오면 idempotency conflict다.
- idempotency 보존 기간과 저장 방식은 구현 PR에서 정한다.
- 같은 version으로 경쟁하는 서로 다른 key의 명령은 하나만 성공하고 나머지는 version conflict다.
- 이미 `delivered`인 Pilot의 같은 deliver key/payload 재시도는 최초 결과를 반환한다. 새 key는 version 또는 state transition conflict다.

## 권한 및 소유권

- Pilot 생성과 제출은 기존 프로젝트 소유권 검사를 우회하지 않는다.
- 운영자 queue는 일반 사용자의 프로젝트 목록 API와 분리하며 `pilot.review` capability를 요구한다.
- 운영자라도 허용된 tenant/project 범위를 벗어난 데이터는 조회하거나 변경할 수 없다.
- internal 결과 링크는 별도의 internal export 권한을 재검사한다.
- transport 계층과 service 계층 모두 권한 경계를 유지한다.

## Implementation PR Decisions

1. DB, ORM, 물리 테이블 구조와 migration 도구
2. 최종 API URL, method, 프레임워크와 response envelope
3. 기존 사용자 역할과 capability 매핑
4. ID 생성 방식
5. cursor 형식과 기본/최대 page size
6. idempotency key 및 감사 데이터 보존 기간
7. 전달 참조값의 허용 형식
8. 영구 취소 정책과 `delivered` 이후 정정 정책

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Pilot State Model](pilot-state-model.md)
- [Approval Queue Design](approval-queue-design.md)
- [Pilot Test Contract](pilot-test-contract.md)
- [ADR: Persistent Pilot State](ADR-persistent-pilot-state.md)
