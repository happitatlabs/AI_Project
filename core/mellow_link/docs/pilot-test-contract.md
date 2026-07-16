# Pilot State and Approval Queue Test Contract

- 문서 상태: Draft for implementation review
- 목적: 구현 전에 상태, 영속성, 권한, 감사, 동시성의 acceptance contract 고정
- 비대상 범위: 테스트 코드 및 fixture 구현

## 테스트 원칙

- 기존 저장소의 pytest 스타일과 fixture 패턴을 재사용한다.
- 실제 고객 정보, 실명, 연락처, 실제 파일 경로를 사용하지 않는다.
- 상태 정책의 순수 단위 테스트와 실제 영속 계층을 거치는 통합 테스트를 분리한다.
- 테스트는 내부 함수 호출 순서보다 외부 상태, 응답, 감사 이력, 재시작 내구성을 검증한다.
- 허용되지 않은 값이나 전이를 조용히 보정하는 기대값을 만들지 않는다.
- 시간은 timezone-aware 고정 clock 또는 동등한 test seam을 사용한다.

## 기준 fixture

최소 합성 데이터 집합:

- 사용자 A: 프로젝트 소유자 또는 제출 권한자.
- 사용자 B: 다른 프로젝트 소유자.
- 운영자 OP1: `pilot.review` 권한 보유.
- 운영자 OP2: 두 번째 reviewer, 동시성 검증용.
- 운영자 D1: `pilot.deliver` 권한 보유.
- 프로젝트 P1 / run RUN1: 정상 Pilot 대상.
- 프로젝트 P2 / run RUN2: 사용자 격리 검증용.

fixture에는 고객명, 개인 이름, 개인 연락처, 실제 소스 파일명 또는 원문을 포함하지 않는다.

## 상태 전이 단위 계약

### 허용 전이

| ID | Given | event | Then | audit event |
| --- | --- | --- | --- | --- |
| ST-001 | Pilot 없음 | `create` | `draft`, version 0 | `pilot_created` |
| ST-002 | `draft` | `submit` | `ready_for_review`, version +1 | `pilot_submitted` |
| ST-003 | `ready_for_review` | `start_review` | `under_review`, reviewer와 시작 시각 기록, version +1 | `pilot_review_started` |
| ST-004 | `under_review` | `approve` | `approved`, 승인자와 승인 시각 기록, version +1 | `pilot_approved` |
| ST-005 | `under_review` | `request_changes` | `changes_requested`, 사유 기록, version +1 | `pilot_changes_requested` |
| ST-006 | `changes_requested` | `resubmit` | `ready_for_review`, 새 요청 시각 기록, version +1 | `pilot_resubmitted` |
| ST-007 | `approved` | `deliver` | `delivered`, 처리자와 전달 시각 기록, version +1 | `pilot_delivered` |

각 성공 케이스는 감사 이벤트가 정확히 하나 추가되고 `from_status`, `to_status`, actor, result version이 일치하는지도 검증한다.

### 금지 전이

| ID | Given | Command/Target | Then |
| --- | --- | --- | --- |
| ST-101 | `draft` | `deliver` | transition conflict, 상태 불변 |
| ST-102 | `draft` | `approve` | transition conflict, 상태 불변 |
| ST-103 | `ready_for_review` | `approve` | transition conflict, 상태 불변 |
| ST-104 | `changes_requested` | `approve` | transition conflict, 상태 불변 |
| ST-105 | `approved` | `start_review` 또는 `request_changes` | transition conflict, 상태 불변 |
| ST-106 | `delivered` | `submit`, `start_review`, `approve`, `request_changes`, `resubmit`, 새 `deliver` | 모두 transition conflict |
| ST-107 | 모든 상태 | 같은 상태로 전이 | 새 이벤트 없는 transition conflict |
| ST-108 | 모든 상태 | 권위 있는 전이표의 선행 상태가 아닌 곳에서 command 실행 | transition conflict, 상태 불변 |

모든 실패 케이스는 version, timestamp, reviewer/approval/delivery 필드, 감사 이벤트 수가 변하지 않아야 한다.

## 입력 검증 계약

| ID | 입력 | 기대 결과 |
| --- | --- | --- |
| VL-001 | 알 수 없는 상태 문자열 | validation error |
| VL-002 | 비어 있는 `project_id` 또는 `run_id` | validation error |
| VL-003 | 프로젝트에 속하지 않는 run | not found 또는 relation validation error |
| VL-004 | 빈 변경 사유 | validation error |
| VL-005 | 최대 길이를 넘는 변경 사유 | validation error, 잘라 저장하지 않음 |
| VL-006 | 최대 길이를 넘는 전달 참조값 | validation error |
| VL-007 | 음수 `expected_version` | validation error |
| VL-008 | offset 없는 timestamp를 외부 입력으로 허용하는 경우 | validation error 또는 명시적 UTC 정책 적용; 조용한 현지시간 추측 금지 |
| VL-009 | 생성/상태 변경 명령의 빈 idempotency key | validation error |

정확한 문자열 최대 길이는 구현 PR에서 정하고 경계값 `max` 허용, `max + 1` 거부 테스트를 추가한다.

## 존재 및 중복 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| ER-001 | 존재하지 않는 Pilot 조회 | not found |
| ER-002 | 존재하지 않는 Pilot 상태 변경 | not found, 감사 이벤트 없음 |
| ER-003 | 동일 `(project_id, run_id)` Pilot 두 번 생성 | duplicate conflict |
| ER-004 | 존재하지 않는 프로젝트 또는 run으로 생성 | not found |
| ER-005 | run이 다른 project에 속함 | 생성 거부 |

중복 생성은 애플리케이션 검증뿐 아니라 선택한 저장 계층의 원자적 유일성 보호도 통합 테스트한다.

## 중복 명령 및 동시성 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| CC-001 | 같은 승인 idempotency key와 payload를 재전송 | 최초 성공 응답/result version 재사용, `pilot_approved` 1개 |
| CC-002 | 같은 key에 다른 payload 사용 | idempotency conflict |
| CC-003 | 승인 후 최신 version과 다른 key로 재승인 | transition conflict, 감사 이벤트 추가 없음 |
| CC-004 | OP1과 OP2가 같은 version으로 `start_review` 경쟁 | 한 요청만 성공, 다른 요청은 version conflict |
| CC-005 | `approve`와 `request_changes`가 같은 version으로 경쟁 | 한 요청만 성공, 다른 요청은 version conflict, aggregate와 audit 일치 |
| CC-006 | 오래된 version으로 임의 상태 변경 | version conflict, 상태와 감사 이력 불변 |
| CC-007 | 같은 deliver key/payload를 `delivered` 이후 재전송 | 최초 전달 결과 재사용, `pilot_delivered` 1개 |
| CC-008 | 네트워크 재시도로 동일 생성/상태 변경 요청 반복 | 같은 key/payload면 최초 결과 재사용, version/audit 증가 없음 |
| CC-009 | 같은 key로 `submit`, `start_review`, `resubmit` 재시도 | 각 최초 결과 재사용, 각 audit event 1개 |
| CC-010 | 같은 create key와 payload 재시도 | 동일 Pilot/version 0 반환, `pilot_created` 1개 |

같은 key를 다른 command에 사용해도 CC-002와 같은 idempotency conflict다. 이미 `delivered`인 Pilot에 새 key로 `deliver`하면 오래된 expected version은 version conflict, 최신 expected version은 transition conflict다.

동시성 테스트는 단순 순차 mock만으로 대체하지 않고, 선택한 저장 계층에서 실제 충돌 보호가 작동하는 통합 경로를 하나 이상 포함한다.

## 영속성 및 원자성 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| PS-001 | Pilot 생성 후 새 session/process에서 조회 | 동일 상태와 version 조회 |
| PS-002 | 승인 후 애플리케이션 재시작 | `approved`와 감사 이력 유지 |
| PS-003 | Delivered 후 재시작 | Delivered queue에서 조회 |
| PS-004 | 상태 저장 성공, 감사 저장 실패를 유도 | 전체 rollback |
| PS-005 | 감사 저장 성공, 상태 저장 실패를 유도 | 전체 rollback |
| PS-006 | changes_requested → resubmit 반복 | aggregate는 최신 상태, audit은 전체 순서 보존 |

메모리 캐시가 있더라도 테스트는 캐시를 비운 뒤 영속 저장에서 상태를 복구해야 한다.

## Queue 조회 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| QU-001 | 상태가 혼합된 Pilot 집합 | Pending은 `ready_for_review`, `under_review`만 포함 |
| QU-002 | 동일 제출 시각 여러 건 | 응답에 내부 key를 노출하지 않는 안정적인 cursor tie-breaker 순서 |
| QU-003 | reviewer 필터 | 해당 reviewer의 `under_review`만 반환 |
| QU-004 | Delivered 조회 | `delivered_at DESC`와 안정적인 tie-breaker |
| QU-005 | pagination 경계 | 누락/중복 없이 다음 cursor로 이어짐 |
| QU-006 | 상태 변경 직후 재조회 | 이전 큐에서 제거되고 올바른 큐에 나타남 |
| QU-007 | 변경 요청 항목 | Pending 승인 큐가 아닌 Changes requested에 나타남 |
| QU-008 | 모든 큐 item | 생성/변경 시각, 담당 운영자 표시값, version, `docx_available` 포함 |
| QU-009 | 모든 큐 item | 내부 경로, 원본 파일명, raw content, bundle ID 미포함 |
| QU-010 | `approved` 항목 | 승인 완료/전달 대기 목록에 포함되고 Pending/Delivered에는 미포함 |

## 권한 및 데이터 격리 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| AU-001 | 인증되지 않은 호출 | unauthorized |
| AU-002 | 사용자 A가 사용자 B의 Pilot 조회/변경 | forbidden 또는 저장소 표준에 맞는 은닉형 not found |
| AU-003 | `pilot.review` 없는 사용자가 Pending queue/검토 시작/승인/변경 요청 | forbidden |
| AU-004 | review 권한만 가진 운영자가 Deliver | forbidden |
| AU-005 | deliver 권한만 가진 운영자가 Approve/Request changes | forbidden |
| AU-006 | 허용된 운영자가 범위 밖 tenant/project 접근 | forbidden |
| AU-007 | `pilot.audit.read` 또는 internal 결과 권한이 없는 reviewer | 감사 이력 forbidden, internal 링크/내용 미노출 |
| AU-008 | `pilot.deliver`만 가진 운영자 | 범위 안 approved/delivered 목록은 허용하고 pending/review/changes 목록과 검토 동작은 forbidden |

저장소의 기존 프로젝트 소유권 패턴과 일관된 HTTP 의미를 선택하되, 우회 경로가 없어야 한다.

## 감사 이력 계약

| ID | 상황 | 기대 결과 |
| --- | --- | --- |
| AD-001 | 정상 전체 흐름 | `pilot_created`, `pilot_submitted`, `pilot_review_started`, `pilot_approved`, `pilot_delivered` 순서로 존재 |
| AD-002 | changes requested 재검토 루프 | 두 review cycle이 손실 없이 기록 |
| AD-003 | validation/권한/version/상태 전이 실패 | 상태 전이 감사 이벤트 추가 없음 |
| AD-004 | audit pagination | 안정적 순서, 누락/중복 없음 |
| AD-005 | 권한 없는 audit 조회 | forbidden |
| AD-006 | 이벤트 actor/version | aggregate 전이 결과와 일치 |
| AD-007 | 동일 idempotency replay | 감사 이벤트 수와 aggregate version 불변 |

실패한 명령을 별도 보안 감사로 남길지는 구현 전 보안 정책에서 결정한다. 남긴다면 상태 전이 감사와 구분하고 민감 payload를 저장하지 않는다.

## Service Contract Acceptance 연결

| Service operation | 성공 | 권한 오류 | 상태 충돌 | version 충돌 | 중복 요청 |
| --- | --- | --- | --- | --- | --- |
| `CreatePilot` | ST-001 | AU-001~002 | ER-003~005 | 해당 없음 | CC-002/010 |
| `SubmitForReview` | ST-002 | AU-001~002 | ST-106~108 | CC-006 | CC-008~009 |
| `StartReview` | ST-003 | AU-003/006 | ST-105~108 | CC-004/006 | CC-008~009 |
| `ApprovePilot` | ST-004 | AU-003/005~006 | ST-102~108 | CC-005~006 | CC-001~003/008 |
| `RequestChanges` | ST-005 | AU-003/006 | ST-105~108 | CC-005~006 | CC-002/008 |
| `ResubmitPilot` | ST-006 | AU-001~002 | ST-106~108 | CC-006 | CC-008~009 |
| `MarkDelivered` | ST-007 | AU-004/006 | ST-101/106~108 | CC-006 | CC-007~008 |
| `ListPilotQueue` / `GetPendingQueue` / `GetDeliveredQueue` | QU-001~010 | AU-003/006/008 | 해당 없음 | 해당 없음 | read 재호출은 동일 snapshot 의미 |
| `GetAuditHistory` | AD-001~007 | AU-006~007 | 해당 없음 | 해당 없음 | read 재호출은 이벤트 추가 없음 |

각 상태 변경 operation은 성공 시 정확히 한 상태 전이 감사 이벤트를 원자적으로 기록한다. 같은 key/payload의 replay는 동일 성공 결과를 반환하지만 새 상태 변경이나 새 감사 이벤트를 만들지 않는다.

## 개인정보 및 로그 계약

| ID | 점검 대상 | 기대 결과 |
| --- | --- | --- |
| PV-001 | Pending/Delivered 응답 | 보고서 원문 미포함 |
| PV-002 | Queue/Audit 응답 | 원본 파일명과 내부 경로 미포함 |
| PV-003 | 감사 이벤트 | 실명, 이메일, 연락처를 복제하지 않고 actor ID만 기록 |
| PV-004 | validation/storage 오류 로그 | 변경 사유 전체와 결과 본문 미출력 |
| PV-005 | 합성 fixture | 실제 고객/개인정보 없음 |
| PV-006 | external 결과 | Pilot 내부 ID와 감사 메타데이터 자동 추가 없음 |

테스트 sentinel은 명백한 합성 값으로 만들고 실제 시스템 경로나 사용자 이름을 사용하지 않는다.

## Service 통합 계약

- Create Pilot은 `draft`, version 0과 `pilot_created`를 반환하고 논리 중복은 conflict다.
- 각 intent operation은 상태 머신과 동일한 precondition을 적용한다.
- transition conflict 응답은 안전한 현재 상태와 version을 제공한다.
- validation 오류는 잘못된 필드를 식별하되 내부 exception/SQL을 노출하지 않는다.
- queue 응답 pagination과 필터는 service 결과와 일치한다.
- transport나 관리자 경로가 service를 우회해 status를 직접 기록하는 backdoor가 없어야 한다.

## 완료 게이트

구현 PR은 최소한 다음을 모두 통과해야 한다.

1. 전체 허용 전이와 금지 전이 matrix.
2. duplicate Pilot, missing Pilot, invalid status.
3. duplicate approve, duplicate deliver, stale version, 동시 reviewer 경쟁.
4. 재시작 후 상태와 audit 복구.
5. 상태와 audit의 원자성.
6. Pending/Changes requested/Approved/Delivered queue 분류와 정렬.
7. 사용자/운영자 권한 및 프로젝트 격리.
8. queue/audit/log의 민감 정보 미노출.
9. 기존 프로젝트 및 run 기능 회귀 없음.

## Implementation PR Decisions

- 실제 저장 엔진에 맞는 restart/transaction/concurrency integration fixture
- DB, ORM, 물리 테이블 구조와 migration 도구
- 최종 API URL과 인증 역할-capability 매핑
- ID 생성과 idempotency record 보존 방식
- 문자열 최대 길이, page size와 cursor 형식
- 영구 취소와 `delivered` 이후 정정 정책
- 상태, 감사 및 idempotency 데이터 보존 기간

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Pilot State Model](pilot-state-model.md)
- [Approval Queue Design](approval-queue-design.md)
- [Pilot API Contract](pilot-api-contract.md)
- [ADR: Persistent Pilot State](ADR-persistent-pilot-state.md)
