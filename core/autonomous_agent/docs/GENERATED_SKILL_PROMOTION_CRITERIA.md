# GENERATED SKILL PROMOTION CRITERIA

이 문서는 `autonomous_agent`의 generated skill에 대한 **수동 승격 검토 기준**을 고정한다.

절차 자체는 `GENERATED_SKILL_PROMOTION_PROCEDURE.md`를 따른다.

중요:

- 이 문서는 production promotion 실행 문서가 아니다.
- 이 문서는 자동 등록 허가 문서가 아니다.
- 현재 단계에서는 generated skill의 **queue viewer 기반 수동 검토 기준**만 정의한다.

## 1. 현재 전제

generated skill은 production skill과 분리되어 아래 경로에서만 관리된다.

- `runtime-data/generated_skills/`
- `runtime-data/generated_skill_results/`
- `runtime-data/generated_skill_queue/`

현재 구조에서 보장되는 점:

- generated skill은 기본적으로 `sandbox_only = true`
- generated skill은 기본적으로 `promotion_required = true`
- sandbox 성공 후에도 자동 promotion은 없다
- queue 적재는 promotion이 아니다
- production `skills/` 디렉토리는 현재 단계에서 직접 수정하지 않는다

## 2. Manual Review의 목적

manual review의 목적은 다음 하나다.

> "이 generated skill이 future manual promotion 검토 대상으로 볼 만한가"

manual review의 목적이 아닌 것:

- production 등록 실행
- core skill overwrite
- sandbox 재실행
- skill loader 연결
- real workspace 실행 허가

즉, 현재 단계의 manual review는 **판단**만 다루고 **승격 실행**은 다루지 않는다.

## 3. 검토 대상 진입 조건

아래 조건을 모두 만족할 때만 generated skill은 manual review 대상으로 간주한다.

1. `runtime-data/generated_skill_queue/`에 queue record가 존재한다
2. queue record의 `promotion_status == pending_manual_review`
3. generated skill draft의 `status == queued_for_manual_promotion`
4. generated skill draft의 `sandbox_only == true`
5. generated skill draft의 `promotion_required == true`
6. validation summary가 `validated` 계열이다
7. sandbox result summary가 존재한다
8. sandbox result는 `experimental_sandbox` 경로에서 생성되었다

이 조건 중 하나라도 깨지면 production promotion 검토 대상이 아니다.

## 4. 하드 블로커

아래 항목이 하나라도 보이면 승격 검토를 중단한다.

- validation failed 이력
- forbidden capability 흔적
- `sandbox_only != true`
- `promotion_required != true`
- subprocess / shell / network 의도
- file write / file delete / file modify 의도
- apply / rollback / backup 관련 의도
- core overwrite / production registration 의도
- real workspace path를 요구하거나 전제하는 구조
- sandbox 결과가 실패이거나 불명확한 경우

핵심 해석:

> generated skill은 low-risk read-only summary/formatting 계열만 검토 대상이다.

## 5. 허용 범위

현재 단계에서 검토 가능한 generated skill 범위는 아래처럼 제한된다.

- `runtime_state_summarizer`
- `proposal_summary_formatter`
- `review_note_compactor`
- `diff_hint_reformatter`

허용되는 성격:

- read-only
- summary
- formatting

허용되지 않는 성격:

- file writer
- file mutator
- subprocess runner
- networked skill
- daemon/loop integration
- apply executor helper
- rollback/backup helper
- production registration helper
- core contract mutation helper

## 6. Manual Reviewer Checklist

reviewer는 아래 순서로 본다.

### Step 1. Queue viewer에서 빠르게 훑기

```powershell
cd autonomous_agent
python review_generated_skills.py list
```

확인 포인트:

- `pending_manual_review`
- `validation: ok`
- `sandbox: passed`

### Step 2. 개별 record 상세 확인

```powershell
python review_generated_skills.py show <skill_id>
```

확인 포인트:

- `[Skill]`
  - `skill_id`
  - `purpose`
  - `status`
  - `promotion_status`
- `[Validation]`
  - `validation_summary`
  - validation errors / warnings
- `[Sandbox]`
  - `sandbox_result_summary`
  - `run_id`
  - `sandbox_result`
  - `execution_mode`
- `[Promotion Queue]`
  - `queued_at`
  - `sandbox_only`
  - `promotion_required`
  - `promoted`

### Step 3. 하드 블로커 확인

아래가 보이면 검토 중단:

- validation error 존재
- `sandbox_only: False`
- `promotion_required: False`
- `promoted: True` 같은 예상 밖 상태
- execution mode 불명확
- purpose와 실제 skill kind가 맞지 않음

### Step 4. 기능 범위 확인

reviewer는 "이 스킬이 정말 read-only summary/formatting 성격인가"를 본다.

아래면 검토 보류:

- 파일 변경을 암시하는 설명
- 운영 경로에 직접 연결되는 설명
- apply, rollback, backup, overwrite, register 같은 승격성 단어
- sandbox를 벗어난 입력을 요구하는 설명

## 7. 승격 검토 가능 / 불가 판정

### 승격 검토 가능

아래를 모두 만족할 때만 "검토 가능"으로 본다.

- queue record 존재
- pending manual review 상태
- validation passed
- sandbox passed
- execution mode가 `experimental_sandbox`
- low-risk read-only summary/formatting 범위 유지
- sandbox-only / promotion-required 속성 유지

### 승격 검토 불가

아래 중 하나라도 해당하면 "검토 불가"다.

- queue record 없음
- validation failed
- sandbox failed
- operational mode 경로에서만 확인된 skill
- forbidden capability 또는 forbidden intent 존재
- generated skill 범위 밖 kind
- production path 의존 또는 overwrite 의도

## 8. 중요한 해석 규칙

아래 해석은 항상 유지된다.

- `queued_for_manual_promotion`은 promotion 완료가 아니다
- `pending_manual_review`는 승인 상태가 아니다
- sandbox success는 production skill 등록 허가가 아니다
- viewer에 보인다고 해서 promotion 가능한 것이 아니다
- generated skill queue는 수동 검토 창이지 실행 경로가 아니다

## 9. 현재 결론

현재 `autonomous_agent`에서 generated skill promotion은 아래처럼 해석해야 한다.

- self-authoring은 sandbox에서만 실험한다
- sandbox 성공 결과는 queue에 올릴 수 있다
- queue는 사람이 읽기 전용으로 검토한다
- production promotion은 아직 수행하지 않는다
- 승격 기준은 이 문서로 고정한다
