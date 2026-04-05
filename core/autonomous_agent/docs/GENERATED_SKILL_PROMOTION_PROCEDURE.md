# GENERATED SKILL PROMOTION PROCEDURE

이 문서는 `autonomous_agent`의 generated skill에 대한 **수동 승격 절차**를 고정한다.

중요:

- 이 문서는 자동 promotion 문서가 아니다.
- 이 문서는 production skill 등록 실행 코드가 아니다.
- 이 문서는 `GENERATED_SKILL_PROMOTION_CRITERIA.md` 다음 단계의 **사람 절차**만 정의한다.

## 1. 현재 범위

현재 구현된 것은 아래까지다.

- generated skill draft 저장
- validation
- experimental sandbox 실행
- manual promotion queue 적재
- read-only queue viewer

현재 구현되지 않은 것:

- production skill 자동 등록
- queue 상태 자동 변경
- promotion 실행
- disable / rollback 자동화

즉, 이 문서는 현재 없는 기능을 열어주는 문서가 아니라, future manual operation이 어떻게 진행되어야 하는지를 잠그는 문서다.

## 2. 절차 시작 전 확인 항목

reviewer는 먼저 queue에서 아래를 확인한다.

### Queue quick scan

```powershell
cd autonomous_agent
python review_generated_skills.py list
```

빠르게 봐야 하는 항목:

- `pending_manual_review`
- `validation: ok`
- `sandbox: passed`

핵심 해석:

- 위 세 조건이 보여도 promotion 완료가 아니다.
- 위 세 조건은 "상세 검토를 시작해도 되는가"만 의미한다.

### Queue detail review

```powershell
python review_generated_skills.py show <skill_id>
```

상세에서 반드시 확인할 항목:

- `skill_id`
- `purpose`
- `status`
- `promotion_status`
- `validation_summary`
- validation errors / warnings
- `sandbox_result_summary`
- `run_id`
- `sandbox_result`
- `execution_mode`
- `sandbox_only`
- `promotion_required`
- `promoted`

## 3. review_generated_skills.py 사용 순서

수동 승격 절차는 아래 순서를 따른다.

1. `python review_generated_skills.py list`
2. 검토할 `skill_id` 선택
3. `python review_generated_skills.py show <skill_id>`
4. `GENERATED_SKILL_PROMOTION_CRITERIA.md` 기준으로 통과 여부 판단
5. 통과/보류/거절 판단을 수동 review record에 남김
6. promotion 전 추가 확인 항목 수행
7. 별도 변환 단계 준비
8. production 반영 여부를 별도 수동 절차로 결정

중요:

- `review_generated_skills.py`는 viewer다.
- approve / promote / retry / rerun 명령은 없다.
- viewer는 queue를 읽기만 하고 변경하지 않는다.

## 4. 승인 기록은 어디에 남기는가

승인 기록은 queue 파일에 덮어쓰지 않는다.

권장 기록 위치:

- `runtime-data/generated_skill_reviews/<skill_id>.review.json`

이 경로는 절차상 review record 위치로 고정한다.

권장 record 필드:

- `skill_id`
- `reviewed_at`
- `reviewer`
- `decision`
  - `approved_for_manual_promotion_consideration`
  - `rejected`
  - `needs_followup`
- `reason`
- `criteria_version`
- `queue_record_ref`
- `sandbox_result_ref`
- `notes`

중요:

- review record는 promotion 자체가 아니다.
- queue 파일을 승인 상태로 덮어쓰지 않는다.
- generated skill draft 원본도 수정 대상으로 보지 않는다.

candidate readiness checklist를 구조적으로 남길 때는 별도 checklist record를 사용한다.

- `runtime-data/generated_skill_reviews/<skill_id>.checklist.json`

## 5. promotion 전 추가 확인 항목

criteria 문서 통과 후에도 아래를 추가로 확인한다.

### 1. 목적과 실제 동작 일치 여부

- `purpose`가 실제 sandbox output과 맞는가
- summary/formatting 범위를 벗어나지 않는가

### 2. production naming collision 여부

- 기존 production `skills/` 아래 core skill 이름과 충돌하지 않는가
- 기존 generated skill과도 이름/역할이 과도하게 중복되지 않는가

### 3. core skill overwrite 금지 여부

- core skill 교체 목적인가
- 기존 skill을 덮어쓰는 구조인가

위 둘 중 하나라도 해당하면 중단한다.

### 4. sandbox-only invariant 유지 여부

- generated artifact 자체는 계속 `sandbox_only = true`로 남아야 한다
- promotion 검토가 draft 원본 의미를 바꾸면 안 된다

### 5. 수동 변환 필요성 확인

- generated draft를 production skill로 그대로 옮겨도 되는가를 묻지 않는다
- 항상 "변환 단계가 필요한가"를 먼저 묻는다

현재 원칙:

> 변환 단계는 항상 필요하다.

## 6. production skill로 올릴 때 직접 이동 금지 / 허용 여부

직접 이동:

- 금지

직접 rename:

- 금지

`runtime-data/generated_skills/`에서 `skills/`로 파일을 그대로 옮기는 행위:

- 금지

허용되는 방식:

- manual review 통과 후
- 별도 수동 변환 단계를 거쳐
- production skill 포맷에 맞는 새 artifact를 명시적으로 만들고
- 별도 수동 변경으로 반영

핵심 해석:

> generated draft는 promotion source material일 뿐, production artifact가 아니다.

## 7. 변환 단계가 필요한가

필요하다.

현재 generated skill은 sandbox experiment 구조에 맞춰 저장된다.

- runtime-data artifact
- queue metadata
- sandbox result linkage
- generated metadata가 포함된 draft

반면 production skill은 별도 loader / packaging / naming / review 기준을 따라야 한다.

따라서 promotion 전에는 아래 중 하나의 변환 단계가 필요하다.

- production skill 문서/메타데이터로 수동 재작성
- production skill packaging 규칙에 맞춘 수동 변환
- 별도 PR/patch에서 human-reviewed artifact 생성

핵심 원칙:

- generated draft를 production skill로 간주하지 않는다
- production artifact는 별도로 만든다

## 8. 승격 후 disable / rollback은 어떻게 하는가

현재 자동 disable / rollback은 없다.

따라서 future manual promotion이 이루어졌다면 아래 수동 원칙을 따른다.

### Disable

- production path에서 해당 skill을 비활성화하는 별도 수동 변경을 수행한다
- generated draft와 queue record는 audit 흔적으로 유지한다
- disable 이유를 review record 또는 후속 rollback record에 남긴다

### Rollback

- production 반영본만 수동 제거 또는 수동 revert 한다
- `runtime-data/generated_skills/` 원본은 rollback 대상으로 보지 않는다
- queue record를 "없던 일"로 지우지 않는다
- rollback 사실은 별도 기록으로 남긴다

권장 rollback record 위치:

- `runtime-data/generated_skill_reviews/<skill_id>.rollback.json`

권장 필드:

- `skill_id`
- `rolled_back_at`
- `operator`
- `reason`
- `production_artifact_ref`
- `review_record_ref`

핵심 해석:

- rollback은 production 반영본에 대한 수동 조치다
- generated runtime artifacts를 덮어써서 이력을 지우는 절차가 아니다

## 9. core skill overwrite 금지 재명시

아래는 항상 금지다.

- core skill overwrite
- 기존 production skill replacement를 generated draft가 자동 수행하는 것
- 기존 skill loader가 generated draft를 production skill처럼 읽는 것
- runtime-data artifact를 production canonical source처럼 취급하는 것

즉:

> generated skill promotion은 "새 artifact를 별도 human-reviewed change로 도입"하는 절차여야 하며, "기존 core skill 덮어쓰기"가 되어서는 안 된다.

## 10. 현재 결론

현재 generated skill promotion procedure는 아래처럼 해석해야 한다.

- queue에서 먼저 `list/show`로 읽기 전용 검토를 한다
- 승인 기록은 queue 파일이 아니라 별도 review record에 남긴다
- promotion 전 추가 확인을 반드시 수행한다
- direct move는 금지다
- 변환 단계는 필수다
- disable / rollback도 수동 절차로만 다룬다
- core skill overwrite는 여전히 금지다
