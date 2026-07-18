# Pilot State Model

- 문서 상태: Draft for implementation review
- 설계 수준: 논리 모델
- 의도적으로 미결정: DB 종류, 테이블명, ORM 매핑, migration 형식

## 목적

프로젝트의 특정 분석 run에 대해 운영자 검토와 납품 상태를 지속적으로 추적할 수 있는 논리 모델을 정의한다. 이 모델은 기존 `ModernizationProject.status`나 `AgentRun.status`를 대체하지 않는다.

- 프로젝트 상태: 프로젝트/분석 실행 진행 상황
- Pilot 상태: 결과의 검토, 승인, 납품 진행 상황

두 상태 축은 의미가 다르므로 같은 필드에 혼합하지 않는다.

## 논리 식별자

Pilot의 논리적 대상은 `(project_id, run_id)`다. 한 프로젝트에 재분석 run이 여러 개 존재할 수 있으므로 run별 승인 상태를 독립적으로 보존한다.

- `(project_id, run_id)` 조합은 유일해야 한다.
- `run_id`는 반드시 `project_id`에 속해야 한다.
- Pilot 생성 뒤 `project_id`와 `run_id`는 변경할 수 없다.
- 외부 API 식별에는 내부 키 구조를 노출하지 않는 opaque `pilot_id` 사용을 권장한다.

## Pilot aggregate 초안

| 필드 | 논리 타입 | 필수 | 의미 및 규칙 |
| --- | --- | --- | --- |
| `pilot_id` | opaque identifier | 예 | Pilot 자체 식별자. 생성 후 불변 |
| `project_id` | project identifier | 예 | 기존 프로젝트 참조. 생성 후 불변 |
| `run_id` | run identifier | 예 | 검토할 결과 run 참조. 생성 후 불변 |
| `status` | PilotStatus enum | 예 | 상태 머신에 정의된 현재 상태 |
| `version` | non-negative integer | 예 | 생성 시 0. 성공한 최초 상태 전이마다 정확히 1 증가 |
| `created_at` | timezone-aware instant | 예 | Pilot 생성 시각 |
| `updated_at` | timezone-aware instant | 예 | 마지막 성공 변경 시각 |
| `created_by_id` | actor identifier | 예 | Pilot 생성 행위자 참조 |
| `review_requested_at` | timezone-aware instant | 아니요 | 최근 `ready_for_review` 진입 시각 |
| `reviewer_id` | actor identifier | 아니요 | 현재 또는 마지막 검토 담당자 참조 |
| `review_started_at` | timezone-aware instant | 아니요 | 최근 `under_review` 진입 시각 |
| `approved_by_id` | actor identifier | 아니요 | 승인 행위자 참조 |
| `approved_at` | timezone-aware instant | 아니요 | `approved` 진입 시각 |
| `delivered_by_id` | actor identifier | 아니요 | 전달 완료 기록 행위자 참조 |
| `delivered_at` | timezone-aware instant | 아니요 | 실제 전달 완료 시각 |
| `change_request_reason` | bounded text | 아니요 | 최근 변경 요청/반려 사유. `changes_requested`에서는 필수 |
| `delivery_reference` | bounded text or opaque reference | 아니요 | 이메일/티켓 등 전달 증적의 최소 참조값. 민감 원문 저장 금지 |
| `last_transition_id` | opaque identifier | 아니요 | 최신 감사 이벤트 참조 |
| `audit_log_reference` | opaque reference | 아니요 | 감사 이력 집합 또는 스트림 참조. 저장 기술에 종속되지 않음 |

`reviewer`, `approval_time`, `delivery_time`, `rejection_reason` 같은 사용자 표현은 각각 `reviewer_id`, `approved_at`, `delivered_at`, `change_request_reason`으로 정규화한다. 표시 이름이나 연락처를 Pilot 레코드에 복제하지 않고 기존 사용자/행위자 식별자를 참조한다.

## 상태별 필드 불변 조건

| 상태 | 반드시 존재 | 반드시 비어 있어야 함 또는 의미 없음 |
| --- | --- | --- |
| `draft` | 기본 식별자, 생성 정보 | 승인/전달 시각 |
| `ready_for_review` | `review_requested_at` | 승인/전달 시각 |
| `under_review` | `review_requested_at`, `reviewer_id`, `review_started_at` | 승인/전달 시각 |
| `changes_requested` | `reviewer_id`, `change_request_reason` | 승인/전달 시각 |
| `approved` | `reviewer_id`, `approved_by_id`, `approved_at` | 전달 시각 |
| `delivered` | 승인 관련 필드, `delivered_by_id`, `delivered_at` | 없음 |

재검토 시 과거 reviewer와 사유를 Pilot aggregate 하나에 누적하지 않는다. 현재 상태에 필요한 최신 값만 aggregate에 두고 전체 이력은 감사 이벤트로 보존한다.

## PilotStatus 값

```text
draft
ready_for_review
under_review
changes_requested
approved
delivered
```

문자열 값은 위 목록과 정확히 일치해야 한다. 대소문자 변환, 별칭 수용, 알 수 없는 값의 fallback은 허용하지 않는다.

## 감사 이벤트 논리 모델

감사 로그는 상태 레코드의 snapshot과 분리된 append-only 이력으로 본다. 실제 저장 방식은 구현 PR에서 정한다.

| 필드 | 논리 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `event_id` | opaque identifier | 예 | 감사 이벤트 식별자 |
| `pilot_id` | Pilot identifier | 예 | 대상 Pilot |
| `project_id` | project identifier | 예 | 권한/검색용 대상 프로젝트 |
| `run_id` | run identifier | 예 | 대상 결과 run |
| `event_type` | enum/string | 예 | 아래 표에 정의된 감사 이벤트 이름 중 하나 |
| `from_status` | PilotStatus or null | 예 | 생성 이벤트는 null, 이후 이벤트는 이전 상태 |
| `to_status` | PilotStatus | 예 | 전이 후 상태 |
| `actor_id` | actor identifier | 예 | 명령을 수행한 인증 주체 |
| `occurred_at` | timezone-aware instant | 예 | 서버가 기록한 이벤트 시각 |
| `reason` | bounded text | 아니요 | 변경 요청 등 사유. 보고서 원문 금지 |
| `idempotency_key` | opaque token | 예 | 생성/상태 변경 명령의 안전한 재시도 식별자 |
| `result_version` | integer | 예 | 이벤트 적용 후 aggregate 버전 |
| `metadata` | bounded key/value set | 아니요 | 허용 목록 기반 최소 메타데이터. 임의 원문 payload 금지 |

### 권위 있는 감사 이벤트 이름

| service event | audit event | from | to |
| --- | --- | --- | --- |
| `create` | `pilot_created` | null | `draft` |
| `submit` | `pilot_submitted` | `draft` | `ready_for_review` |
| `start_review` | `pilot_review_started` | `ready_for_review` | `under_review` |
| `approve` | `pilot_approved` | `under_review` | `approved` |
| `request_changes` | `pilot_changes_requested` | `under_review` | `changes_requested` |
| `resubmit` | `pilot_resubmitted` | `changes_requested` | `ready_for_review` |
| `deliver` | `pilot_delivered` | `approved` | `delivered` |

동일 idempotency key와 동일 payload의 replay는 새 감사 이벤트가 아니다. 실패한 validation, 권한, version 또는 상태 전이 명령도 상태 전이 감사 이력을 만들지 않는다. 실패 시도에 대한 별도 보안 감사 정책은 구현 PR의 독립 결정으로 남긴다.

## 데이터 및 보안 원칙

- queue 응답과 감사 이벤트에는 보고서 본문, 원본 파일명, 내부 파일 경로, 추출 원문을 넣지 않는다.
- reviewer와 actor는 식별자만 저장하며 실명, 이메일, 연락처를 복제하지 않는다.
- 변경 사유와 전달 참조값에는 합리적인 최대 길이를 두고 제어문자 및 허용되지 않은 구조를 거부한다.
- 감사 로그 조회는 운영자 권한과 프로젝트 접근 범위를 모두 검사한다.
- 고객용 external 결과에 Pilot 내부 식별자나 감사 정보가 자동 포함되지 않는다.
- 로그에는 전체 모델이나 사유 원문을 평문으로 출력하지 않는다.

## 구현 PR에서 결정할 사항

1. DB, ORM, 물리 테이블 구조와 migration 도구
2. `pilot_id`와 idempotency key 생성 전략
3. actor capability를 기존 `UserRole`에 매핑하는 방식
4. 감사 이벤트를 전용 저장소로 둘지 기존 이벤트 기반 시설을 확장할지
5. `delivery_reference`의 허용 형식
6. 상태, 감사 및 idempotency 데이터 보존 기간
7. 영구 취소 정책과 승인 취소 정책
8. `delivered` 이후 정정 또는 재납품 정책

위 결정은 논리 불변 조건과 상태 전이 계약을 약화해서는 안 된다.

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Approval Queue Design](approval-queue-design.md)
- [Pilot API Contract](pilot-api-contract.md)
- [Pilot Test Contract](pilot-test-contract.md)
- [ADR: Persistent Pilot State](ADR-persistent-pilot-state.md)
