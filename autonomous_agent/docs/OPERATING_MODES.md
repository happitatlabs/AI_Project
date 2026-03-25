# OPERATING MODES

이 문서는 `autonomous_agent`의 운영 모드와 실험 모드를 명확히 분리해 설명하고, future entrypoint가 execution gate를 우회하지 못하도록 프로젝트 규칙을 고정한다.

중요:

- 이 문서는 기능 확장 문서가 아니다.
- real apply를 여는 문서가 아니다.
- 현재 구조를 흔들리지 않게 유지하기 위한 운영 규칙 문서다.

## 1. Mode 개요

현재 지원하는 execution mode는 아래 두 가지다.

### `operational`

- 기본값
- review / proposal / staging / precheck 중심
- real apply 금지
- sandbox apply 자동 진입 금지

### `experimental_sandbox`

- 명시적 opt-in일 때만 진입
- temp-dir sandbox 안에서만 mock apply / rollback / marker 흐름 허용
- real workspace는 여전히 금지

## 2. Mode 차이

### `operational`

의미:

- 현재 시스템의 기본 운영 모드다.
- proposal 생성, review, staging, precheck, dry-run metadata, runtime transaction state debug 흐름을 다룬다.
- apply executor는 이 모드에서 real workspace를 수정하지 않는다.

핵심 해석:

- 기본 모드는 항상 `operational`이다.
- `operational`에서 apply 관련 계약은 설명용 / 검토용 / metadata용이다.
- `operational`은 실행 허가 모드가 아니다.

### `experimental_sandbox`

의미:

- isolated temp-dir 안에서만 mock apply 경로를 검증하기 위한 실험 모드다.
- 기존 `sandbox apply v0` 흐름은 이 mode 경로로 정리되어 있다.
- rollback / marker / runtime state가 temp-dir sandbox 기준으로 동작하는지 확인하는 목적이다.

핵심 해석:

- `experimental_sandbox`는 real workspace apply permission이 아니다.
- temp-dir sandbox success는 real apply enable 신호가 아니다.
- sandbox 결과는 검증 신호일 뿐, 실행 허가가 아니다.

## 3. Required Flags

`experimental_sandbox`에 진입하려면 아래 두 플래그가 모두 필요하다.

- `--experimental-sandbox`
- `--confirm-experimental`

해석 규칙:

- 둘 중 하나라도 없으면 mode는 `operational`로 남는다.
- 두 플래그가 모두 있어도 sandbox root가 system temp directory 밖이면 즉시 차단된다.

## 4. 허용 / 금지 항목

### `operational`에서 허용되는 것

- review / proposal / staging 흐름
- precheck / apply plan preview / executor spec 조회
- runtime transaction state writer / marker recorder / debug CLI 사용
- inspect / review / report / read-only verification 흐름

### `operational`에서 금지되는 것

- real workspace apply
- temp-dir sandbox apply 자동 진입
- subprocess 기반 apply
- network 기반 apply
- daemon / loop 경로에서 auto-apply
- real workspace backup / rollback 실행

### `experimental_sandbox`에서 허용되는 것

- explicit opt-in 이후 temp-dir sandbox 안에서의 mock apply 흐름
- temp-dir sandbox 안에서의 backup materialization
- temp-dir sandbox 안에서의 rollback / marker / runtime state 검증
- runtime-data 기준 결과 기록과 debug 확인

### `experimental_sandbox`에서도 금지되는 것

- real workspace write
- temp-dir 밖 경로 대상 실행
- subprocess 실행
- network 사용
- daemon integration
- automatic apply
- real apply

## 5. 중요한 해석

아래 해석은 항상 유지된다.

- real apply는 여전히 금지다.
- `experimental_sandbox` success는 real apply permission이 아니다.
- sandbox 결과는 "검증 신호"이지 "실행 허가"가 아니다.
- `runtime-data/runtime/<transaction_id>.json`과 marker 기록이 존재해도 real workspace에 대한 실행 권한을 뜻하지 않는다.
- executor specification은 future executor를 제한하는 계약이지 실행 허가 문서가 아니다.

## 6. 작은 실행 예시

아래 예시는 현재 구현 상태와 맞는 read-only 또는 sandbox-only 예시만 포함한다.

### A. 운영 모드 proposal / review 흐름 예시

```powershell
cd autonomous_agent
python inspect_storage.py
python review_pending.py list
python review_pending.py show 0
```

해석:

- 위 흐름은 inspect -> review list/show -> proposal/staging 확인용이다.
- 이 예시는 `operational` 모드에서 허용되는 read / review 중심 흐름이다.

### B. `experimental_sandbox` apply 흐름 예시

현재 전용 apply CLI는 없다. 현재 구현에 맞는 가장 작은 예시는 temp-dir sandbox에서 helper 기반으로 실행하는 방식이다.

```python
from pathlib import Path
import tempfile

from agent.apply_executor_v0 import run_isolated_apply_v0


sandbox_root = Path(tempfile.mkdtemp()) / "sandbox"
target = sandbox_root / "config" / "prod.yaml"
target.parent.mkdir(parents=True)
target.write_text("mode: prod\n", encoding="utf-8")

result = run_isolated_apply_v0(
    {
        "proposal_id": "proposal_temp_apply",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    },
    sandbox_root=sandbox_root,
    content_map={"config/prod.yaml": "mode: canary\n"},
    reference=sandbox_root.parent / "pending_approvals.json",
    execution_flags={
        "experimental_sandbox": True,
        "confirm_experimental": True,
    },
)
```

해석:

- explicit opt-in flag 의미를 `execution_flags`로 전달한다.
- sandbox root는 반드시 system temp directory 안이어야 한다.
- 이 예시는 sandbox-only 검증 경로다.
- 이 예시는 real apply 예시가 아니다.

### C. runtime state / debug CLI 보는 법

```powershell
cd autonomous_agent
python inspect_transaction_runtime.py --transaction-id <transaction_id> --reference <reference_path>
```

확인 가능한 항목:

- `execution_mode`
- marker 순서
- `terminal_marker`
- runtime notes

## 7. Mode Gate Reuse Rule

이 절은 프로젝트 규칙이다.

### Rule 1. 모든 새 entrypoint는 `execution_mode.py`를 재사용해야 한다

새 CLI, 새 엔트리포인트, 새 실행 경로를 추가할 때는 반드시 아래 helper를 재사용해야 한다.

- `add_experimental_sandbox_flags(...)`
- `normalize_execution_flags(...)`
- `resolve_execution_mode(...)`
- `build_experimental_sandbox_gate(...)`

### Rule 2. duplicate gate 구현 금지

아래 로직을 개별 파일에서 다시 작성하면 안 된다.

- operational / experimental mode 분기
- explicit flag 조합 판정
- sandbox root temp-dir 검증
- experimental mode enable / block 판정

### Rule 3. sandbox root 검증 로직 재구현 금지

future entrypoint는 temp-dir 여부를 독자적으로 해석하면 안 된다.

반드시 `execution_mode.py`의 gate helper를 통해 판단해야 한다.

### Rule 4. future entrypoints must normalize flags through `execution_mode.py`

새 진입점이 argument parser를 가지면:

1. `execution_mode.py`의 flag helper를 통해 플래그를 추가하고
2. 동일 모듈에서 flag normalization을 수행하고
3. 동일 모듈의 gate helper 결과를 실행 조건으로 사용해야 한다

### Rule 5. mode logic을 개별 비즈니스 로직으로 흩뜨리지 않는다

mode 분기와 gate 판정은 공통 helper 계층에 유지한다.

개별 executor, CLI, utility 파일이 독자적인 mode 정책을 들고 있으면 안 된다.

### Rule 6. gate bypass를 허용하는 예외를 만들지 않는다

아래 예외는 허용되지 않는다.

- "테스트 전용"이라는 이유로 duplicate gate 추가
- "간단한 CLI"라는 이유로 직접 flag 체크
- "sandbox only"라는 이유로 temp-dir 검증 생략
- "internal tool"이라는 이유로 `execution_mode.py` 우회

## 8. 현재 결론

현재 `autonomous_agent`의 execution 구조는 아래처럼 해석해야 한다.

- 기본은 `operational`
- 명시적 opt-in + temp-dir 조건을 모두 만족할 때만 `experimental_sandbox`
- real apply는 여전히 금지
- sandbox validation은 real apply permission이 아니다
- future entrypoint는 반드시 `execution_mode.py`를 재사용해야 한다
