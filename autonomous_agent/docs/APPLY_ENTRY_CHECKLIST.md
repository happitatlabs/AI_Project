# APPLY ENTRY CHECKLIST

이 문서는 `autonomous_agent`에서 future actual apply를 **언제까지 금지해야 하는지**를 판단하는 체크리스트다.

## ✅ 확정(verified)

아래 항목이 모두 충족되기 전에는 actual apply를 켜면 안 된다.

## 현재 상태 반영

- [x] runtime state writer mock 구현 완료
- [x] marker recorder mock 구현 완료
- [x] runtime transaction debug reader / CLI 구현 완료
- [x] isolated temp-dir integration 통과 (runtime metadata mock 범위)
- [ ] actual apply enable 기준 충족

위 완료 항목은 모두 **metadata-only mock 계층** 기준이다.
이것만으로는 actual apply를 켤 수 없다.

## Apply 금지 해제 전 필수 체크리스트

- [ ] runtime state writer actual apply integration 완료
- [ ] marker recorder actual apply integration 완료
- [ ] backup materializer 구현 완료
- [ ] rollback executor 구현 완료
- [ ] atomic writer (`temp_then_rename`) 구현 완료
- [ ] partial write detection 구현 완료
- [ ] terminal marker enforcement 구현 완료
- [ ] idempotency enforcement 구현 완료
- [ ] pre-apply validation enforcement 구현 완료
- [ ] post-apply validation enforcement 구현 완료
- [ ] blocked target / path traversal / absolute path 차단 enforcement 완료
- [ ] backup completeness verification 구현 완료
- [ ] rollback completion verification 구현 완료
- [ ] failure visibility 기록 구현 완료
- [ ] unknown state -> halt and manual review 경로 구현 완료
- [ ] failure injection matrix 통과
- [x] isolated temp-dir integration 통과
- [ ] transaction state consistency 검증 통과
- [ ] manual-only invocation 유지
- [ ] 실제 workspace 대상 테스트 금지 유지

## 항목 설명

### runtime state / marker

- `runtime-data/runtime/<transaction_id>.json` writer가 실제로 동작해야 한다.
- 현재는 mock metadata writer/recorder와 read-only debug CLI까지만 완료된 상태다.
- 아래 marker를 기록할 수 있어야 한다.
  - `apply_started`
  - `apply_succeeded`
  - `apply_failed`
  - `rollback_started`
  - `rollback_completed`
- `exactly one terminal marker required` 규칙을 실제로 강제해야 한다.

### backup / rollback

- 모든 target path에 대해 backup을 먼저 materialize해야 한다.
- backup 미완료 상태에서는 first write가 시작되면 안 된다.
- rollback은 `full rollback only`여야 한다.
- partial rollback 경로는 없어야 한다.

### atomic write

- write 전략은 `temp_then_rename`이어야 한다.
- `all_or_nothing`을 실제로 강제해야 한다.
- rename 실패 시 즉시 `rollback_required`로 들어가야 한다.
- 일부만 적용된 상태를 감지할 수 있어야 한다.

### validation / failure handling

- pre-apply validation 실패 시 write 시작 금지
- post-apply validation 실패 시 success marker 기록 금지
- unknown state 발생 시 자동 진행 금지
- manual review 강제 경로가 있어야 한다.

### test boundary

- integration 검증은 isolated temp-dir에서만 허용한다.
- runtime metadata mock 범위의 temp-dir integration은 이미 통과했다.
- 실제 workspace를 대상으로 apply 테스트를 하면 안 된다.
- actual apply enable 이전에는 manual-only invocation만 허용한다.

## 운영 해석 규칙

이 체크리스트는 “준비되면 바로 apply해도 된다”는 승인 문서가 아니다.

목적은 반대다.

- 아직 부족한 항목을 명확히 보이게 하고
- 하나라도 비어 있으면 actual apply를 금지하고
- 느슨한 상태에서 실행으로 넘어가지 못하게 막는 것

핵심 원칙:

> 이 체크리스트가 전부 충족되기 전에는 actual apply 금지.

현재 해석:

> runtime state mock / debug reader가 들어와도 backup, rollback, atomic write, validation enforcement가 비어 있으면 actual apply 금지.
