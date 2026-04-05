# SYSTEM BOUNDARY

이 문서는 `autonomous_agent`의 현재 설계 동결 상태를 고정하는 문서다.

## ✅ 확정(verified)

- 지금은 **actual apply 미구현** 상태다.
- 현재 허용 범위는 아래까지만이다.
  - `dry-run`
  - `precheck`
  - `proposal`
  - `staging`
  - `runtime transaction state` metadata 기록
  - `inspect_transaction_runtime.py` read-only debug 조회
- `workspace` 직접 write는 금지다.
- `backup` / `rollback`은 **metadata-only** 계약만 존재한다.
- `runtime state writer`와 `marker recorder`는 **mock metadata layer** 수준으로만 구현돼 있다.
- 장기 loop / autonomy / auto-apply는 현재 범위에 없다.

## 현재 허용 범위

현재 시스템은 아래 흐름만 안전하게 지원한다.

1. 판단
2. 설명
3. 검토
4. proposal 생성
5. approval / reject 기록
6. staging 복사
7. precheck / apply plan preview / executor spec 조회
8. runtime transaction state mock 기록
9. runtime transaction state read-only debug 조회

즉, 지금 시스템은 “실행 엔진”이 아니라 “검토 가능한 전달 상자”까지를 지원한다.

## 현재 금지 범위

아래는 현재 단계에서 금지다.

- actual apply 실행
- workspace 파일 생성 / 수정 / 삭제
- patch apply
- backup 파일 생성
- rollback 실행
- subprocess 기반 apply 흐름
- auto-apply
- loop / autonomy 기반 실행 연결
- self-modifying / self-updating 동작

## metadata-only 경계

현재 apply 관련 sidecar는 모두 계약 또는 preview 용도다.

- `.precheck.json`
- `.apply_plan.json`
- `.transaction.json`
- `.executor_spec.json`

이 파일들은 “어떻게 실행해야 안전한지”를 설명할 뿐, 실행 권한을 의미하지 않는다.

핵심 해석 규칙:

> This specification defines constraints for future execution and must not be interpreted as permission to execute apply.

## runtime state 관련 현재 상태

future runtime transaction state 경로 규칙은 이미 계약으로만 고정돼 있다.

```text
runtime-data/runtime/<transaction_id>.json
```

현재는 아래가 **mock / metadata-only** 수준으로 구현돼 있다.

- runtime state writer
- marker runtime recorder
- read-only debug reader

다만 아래는 아직 미구현이다.

- actual apply와 연결된 runtime state persistence
- rollback trace runtime materialization
- apply lifecycle 전 구간 marker runtime enforcement

즉, runtime state 경로와 mock 기록 계층은 존재하지만, actual apply 실행 계층은 아직 없다.

## actual apply를 켜기 전 필수 조건

아래 조건이 모두 충족되기 전에는 actual apply를 활성화하면 안 된다.

1. runtime state writer 구현
   - `transaction_id`
   - state transition
   - marker 기록
   - terminal state 고정
   - actual apply lifecycle 연동

2. backup materialization 구현
   - 모든 target에 대한 backup 생성
   - backup completeness 검증
   - first write 전 backup 준비 완료 보장

3. atomic write executor 구현
   - `temp_then_rename`
   - `all_or_nothing`
   - partial write detection
   - rename failure -> rollback required

4. rollback executor 구현
   - full rollback only
   - partial rollback 금지
   - rollback completion 검증
   - rollback failure -> manual review

5. pre-apply validation 강제
   - proposal approved 확인
   - blocked target path 차단
   - executor spec 조건 충족 확인
   - backup / rollback contract 충족 확인

6. post-apply validation 강제
   - target count 일치
   - changed files match plan
   - partial apply 미발생 확인
   - terminal marker 정합성 확인

7. idempotency enforcement 구현
   - duplicate write 금지
   - duplicate marker 금지
   - terminal marker 이후 state mutation 금지

8. failure visibility 구현
   - apply_started / apply_failed / rollback_started / rollback_completed 기록
   - unknown state 발생 시 halt + manual review
   - success / failure marker 없이 종료되는 상태 금지

## 운영 해석 원칙

- proposal은 실행 지시가 아니다.
- staging은 적용 대기함이 아니라 승인된 제안의 고정 복사본이다.
- precheck가 존재해도 apply 허가를 뜻하지 않는다.
- dry-run은 실행 preview일 뿐, write permission이 아니다.
- executor spec는 future executor를 제한하는 계약이지, 실행 허용 문서가 아니다.

## 현재 결론

현재 `autonomous_agent`는 다음 상태로 동결한다.

- actual apply: disabled
- workspace write: disabled
- backup / rollback: metadata-only
- runtime state writer: mock implemented
- marker recorder: mock implemented
- runtime transaction debug CLI: read-only enabled
- loop / autonomy apply path: not implemented

즉, 지금은 **apply를 구현하기 전 단계가 아니라, apply를 쉽게 켜지 못하게 막아두는 단계**다.
