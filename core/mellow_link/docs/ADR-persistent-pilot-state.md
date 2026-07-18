# ADR: Persistent Pilot State and Approval Queue

- 상태: Proposed
- 날짜: 2026-07-14
- 결정 범위: 파일럿 결과 검토, 승인, 반려, 납품 상태
- 비결정 범위: 특정 DB/ORM/테이블, migration 도구, UI, 알림, 납품 패키지 조립

## Context

현재 `mellow_link.infra.run_approval`은 `RUN_APPROVAL_STATE` 메모리 딕셔너리와 `threading.Event`를 사용해 특정 run을 승인/거부까지 대기시킨다. 이 구조는 실행 중 PolicyGuardian 승인 대기를 위한 국소 기능으로는 단순하지만, 유료 파일럿 운영의 상태 원장과 작업 큐 역할을 맡기에는 다음 한계가 있다.

- 프로세스 재시작 시 대기 상태와 결정 정보가 사라진다.
- 단일 프로세스 메모리에 묶여 여러 worker/instance에서 일관된 큐를 제공하기 어렵다.
- 24시간 blocking wait와 파일럿의 며칠 단위 검토/납품 수명 주기가 맞지 않는다.
- `run_id` 중심의 임시 상태라 프로젝트/run별 승인 이력과 납품 상태를 장기간 조회하기 어렵다.
- 승인, 변경 요청, 재제출, 전달 완료의 명시적 상태 전이 규칙이 없다.
- 중복 승인, stale update, 두 reviewer 경쟁을 저장 계층에서 원자적으로 막기 어렵다.
- 운영자가 조회할 durable Pending/Delivered queue와 append-only 감사 이력이 없다.
- 메모리 entry가 제거된 뒤에는 누가 언제 어떤 결정을 내렸는지 재구성하기 어렵다.

파일럿 결과는 분석 실행 완료와 별개로 사람의 검토, 승인, 전달 확인을 거친다. 따라서 실행 스레드를 기다리게 하는 구조가 아니라 장기 수명 주기의 영속 workflow state가 필요하다.

## Decision

파일럿별 영속 `Pilot State` aggregate와 상태에서 파생되는 `Approval Queue`, append-only `Pilot Audit History`를 도입한다.

핵심 결정은 다음과 같다.

1. 파일럿의 논리 대상은 `(project_id, run_id)`이며 조합별 상태를 독립 보존한다.
2. 상태는 `draft`, `ready_for_review`, `under_review`, `changes_requested`, `approved`, `delivered`로 제한한다.
3. 상태 전이는 중앙 policy/service를 통해서만 수행한다.
4. 상태 변경과 감사 이벤트 기록은 원자적이어야 한다.
5. Approval Queue는 별도 복제 상태가 아니라 영속 Pilot 상태를 필터/정렬한 조회 모델이다.
6. 모든 상태 변경은 `expected_version`을 검사하고, 모든 생성/상태 변경은 `idempotency_key`를 요구해 중복 승인, 네트워크 재시도, 동시 reviewer 충돌을 일관되게 처리한다.
7. existing project ownership과 operator capability를 모두 적용한다.
8. queue/audit에는 보고서 원문, 원본 파일명, 내부 경로를 복제하지 않는다.

이 ADR은 저장 기술을 선택하지 않는다. 현재 프로젝트의 기존 저장/세션/migration 관례를 구현 PR에서 우선 재사용하되, 위 논리 계약을 만족해야 한다.

## 기존 메모리 승인과의 관계

Persistent Pilot State는 기존 `run_approval`의 스레드 대기 구현을 그대로 영속화하는 작업이 아니다.

- 기존 `run_approval`: 실행 중 특정 판단을 즉시 승인/거부할 때 사용하는 runtime coordination.
- 새 Pilot State: 결과 생성 이후 검토, 승인, 변경 요청, 전달을 추적하는 durable business workflow.

다음 구현 PR에서는 Pilot workflow를 독립적으로 추가하고 기존 runtime 승인 흐름을 불필요하게 리팩터링하지 않는다. 장기적으로 통합이 필요하면 별도 ADR과 migration 계획을 작성한다.

## 고려한 대안

### 대안 A: 기존 메모리 딕셔너리 확장

설명: `RUN_APPROVAL_STATE`에 파일럿 상태와 목록 조회 필드를 추가한다.

장점:

- 구현량이 가장 작다.
- 기존 승인/거부 함수와 직접 연결하기 쉽다.

단점:

- 재시작과 다중 worker에서 상태를 잃거나 분기시킨다.
- 장기 queue와 감사 이력을 신뢰할 수 없다.
- 동시성 및 중복 처리를 프로세스 lock에 의존한다.

판정: 파일럿 운영의 내구성 요구를 충족하지 못해 채택하지 않는다.

### 대안 B: `AgentRun.status`와 `AgentRunEvent`만 재사용

설명: 기존 run 상태에 검토/승인/전달 값을 추가하고 run event로 이력을 남긴다.

장점:

- 기존 영속 모델과 이벤트 조회를 활용할 수 있다.
- 새 aggregate 수가 줄어든다.

단점:

- 실행 상태와 비즈니스 승인 상태가 한 필드에 섞인다.
- 하나의 run이 `completed`이면서 동시에 `under_review`일 수 있는 두 축을 표현하지 못한다.
- 기존 runtime/UI가 기대하는 run 상태 의미를 깨뜨릴 위험이 있다.
- Pilot 전용 유일성, reviewer, 승인/전달 시각, concurrency 규칙이 불명확해진다.

판정: 의미 축 혼합과 기존 회귀 위험 때문에 채택하지 않는다. 감사 저장 구현에서 기존 이벤트 인프라를 부분 재사용할지는 별도 구현 결정으로 남긴다.

### 대안 C: 영속 Pilot aggregate + append-only audit + 파생 queue

설명: 실행 상태와 분리된 Pilot 상태를 두고 상태 전이마다 감사를 기록하며 queue는 상태 조회로 구성한다.

장점:

- 상태 의미와 책임이 명확하다.
- 재시작, 장기 검토, 다중 worker에 대응할 수 있다.
- 전이 규칙, 동시성, idempotency, 감사 요구를 독립적으로 테스트할 수 있다.
- 향후 SLA, reviewer assignment, delivery evidence를 확장하기 쉽다.

단점:

- 새 모델과 migration, service, 권한 정책이 필요하다.
- project/run과의 정합성 및 상태/audit 원자성을 설계해야 한다.
- 기존 실행 상태와 Pilot 상태를 UI에서 혼동하지 않도록 명명해야 한다.

판정: 채택한다.

### 대안 D: 외부 workflow engine 도입

설명: 파일럿 상태와 human task를 외부 workflow 제품에 위임한다.

장점:

- 복잡한 workflow, retry, timer, human task 확장에 유리하다.
- 다중 instance와 장기 실행을 기본 지원할 수 있다.

단점:

- 현재 범위에 비해 운영 복잡도와 의존성이 크다.
- 외부 전송, 자격 증명, 배포, 개인정보 검토 범위가 확대된다.
- 작은 독립 PR 목표와 맞지 않는다.

판정: 현재는 채택하지 않는다. workflow가 복수 팀/다단계 SLA로 확장될 때 재검토한다.

## 선택 이유

- 파일럿의 검토/납품 상태는 프로세스 수명보다 오래 지속된다.
- 분석 실행 상태와 승인 상태는 동시에 존재하는 독립 축이다.
- 유료 납품에는 누가 언제 승인/반려/전달했는지 재현 가능한 감사 정보가 필요하다.
- 운영자 queue는 재시작 후에도 동일해야 하고 동시 처리 충돌을 안전하게 거부해야 한다.
- 외부 workflow engine 없이도 현재 저장소의 기존 인증/영속 패턴 안에서 작은 독립 PR로 구현 가능하다.

## 긍정적 결과

- 프로세스 재시작 후에도 상태, queue, 감사 이력을 복구할 수 있다.
- 승인 전 전달, delivered 되돌리기 같은 잘못된 전이를 중앙에서 차단한다.
- 중복 승인과 두 reviewer 경쟁을 명시적으로 테스트할 수 있다.
- 프로젝트/run별 운영 현황과 Delivered 이력을 안정적으로 조회할 수 있다.
- 이후 준비물 체크리스트나 납품 조립 기능이 승인 상태를 신뢰할 수 있다.

## 부정적 결과 및 비용

- schema/migration과 repository/service 계층이 추가된다.
- 상태와 감사의 transaction 경계를 구현하고 검증해야 한다.
- 권한 모델에 reviewer/deliver capability를 매핑해야 한다.
- 기존 프로젝트 status와 Pilot status가 UI/API 명칭상 혼동될 수 있다.
- retention, correction, permanent cancellation 정책이 아직 없으므로 후속 결정이 필요하다.

## 구현 가드레일

- 기존 `ModernizationProject.status`와 `AgentRun.status` 값을 Pilot 상태로 재사용하지 않는다.
- 기존 `run_approval` 동작을 이번 PR에서 광범위하게 리팩터링하지 않는다.
- Pilot 상태와 audit을 별도 commit으로 저장하지 않는다.
- 최초 성공한 전이와 단 하나의 canonical 감사 이벤트를 원자적으로 저장하며, 동일 key/payload replay에는 상태, version, 감사 이벤트를 추가하지 않는다.
- 상태를 라우터나 UI에서 직접 갱신하지 않고 service 전이 정책을 호출한다.
- 저장 계층에서도 `(project_id, run_id)` 유일성과 동시성 보호를 적용한다.
- audit payload에 결과 본문, 원본 파일명, 내부 경로를 저장하지 않는다.
- 자동 전달, 알림, 납품 ZIP 조립을 결합하지 않는다.

## 향후 확장성

이 결정은 다음을 추가할 수 있는 기반을 제공한다.

- reviewer assignment와 업무량 분배
- 검토 SLA 및 overdue 조회
- 승인 체크리스트 참조
- 납품 패키지 조립과 전달 증적 연결
- 승인 정책 버전과 규칙 버전 기록
- 재검토 cycle 통계
- 보존/정정/취소 정책
- 알림 또는 외부 workflow 연동

각 확장은 별도 정책, 개인정보 검토, 테스트 계약과 함께 진행한다.

## 후속 결정 필요

1. 구체적인 저장 모델과 migration 전략
2. 기존 `AgentRunEvent` 재사용 여부와 Pilot audit 전용 저장소 여부
3. capability와 현재 `UserRole` 매핑
4. permanent cancellation/withdrawal 필요 여부
5. delivered 이후 정정 방식
6. 감사 및 idempotency record 보존 기간
7. queue SLA와 reviewer 재할당 정책

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Pilot State Model](pilot-state-model.md)
- [Approval Queue Design](approval-queue-design.md)
- [Pilot API Contract](pilot-api-contract.md)
- [Pilot Test Contract](pilot-test-contract.md)
