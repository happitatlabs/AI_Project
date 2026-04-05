# GENERATED SKILL MANUAL TRANSFORM EXECUTION

이 문서는 `autonomous_agent`의 generated skill을 **production candidate artifact로 수동 변환하는 절차**를 고정한다.

중요:

- 이 문서는 production registration 실행 문서가 아니다.
- 이 문서는 generated draft를 production skill로 직접 옮기는 절차가 아니다.
- 이 문서는 approval 이후에도 production 반영 전에 반드시 거쳐야 하는 **인간 개입 단계**만 정의한다.

## 1. 목적과 범위

이 문서의 목적은 다음 하나다.

> generated skill transform template을 사람이 검토하고 보완해서, production candidate artifact 초안을 안전하게 만드는 순서와 규칙을 고정한다.

이 문서가 다루지 않는 것:

- production skill promotion 실행
- production skill registration
- `skills/` 디렉토리 write
- queue 상태 변경
- review decision / approval record 자동 생성
- sandbox 재실행

핵심 원칙:

- generated draft direct move 금지
- transform template direct promotion 금지
- approval record가 있어도 production 등록 권한은 생기지 않음
- production candidate artifact는 여전히 **후속 수동 단계의 입력**일 뿐이다

## 2. 입력 artifact

수동 변환 전 reviewer/operator는 아래 artifact를 모두 확보해야 한다.

### Generated skill draft

- 경로:
  - `runtime-data/generated_skills/<skill_id>.json`
- 의미:
  - generated skill의 원본 draft
  - `sandbox_only = true`, `promotion_required = true` invariant가 남아 있는 runtime artifact

### Queue record

- 경로:
  - `runtime-data/generated_skill_queue/<skill_id>.json`
- 의미:
  - `queued_for_manual_promotion` 이후의 manual review queue 상태
  - `promotion_status = pending_manual_review` 여부 확인용

### Validation result

- 경로:
  - draft 내부 `last_validation_report`
- 의미:
  - generated skill 구조/metadata 검증 결과
  - validation passed 여부 확인용

### Sandbox result

- 경로:
  - `runtime-data/generated_skill_results/<run_id>.json`
- 의미:
  - `experimental_sandbox`에서 생성된 실행 결과
  - sandbox passed 여부와 `execution_mode` 확인용

### Review decision record

- 경로:
  - `runtime-data/generated_skill_reviews/<skill_id>.review.json`
- 의미:
  - 이 generated skill을 승격 검토 대상으로 볼지에 대한 수동 판단
  - `approve_for_consideration | rejected | needs_followup`

### Promotion packet

- 경로:
  - `runtime-data/generated_skill_packets/<skill_id>.packet.json`
- 의미:
  - draft / queue / validation / sandbox / review decision을 묶은 read-only 검토 artifact

### Transform template

- 경로:
  - `runtime-data/generated_skill_transforms/<skill_id>.transform.json`
- 의미:
  - production candidate artifact를 만들기 위한 수동 변환 양식
  - placeholder와 `required_manual_edits`를 포함하는 guide artifact

### Approval record

- 경로:
  - `runtime-data/generated_skill_reviews/<skill_id>.approval.json`
- 의미:
  - `promotion_approval` 또는 `transform_approval`에 대한 최종 승인 흔적
  - approval file 내부 `records` map으로 type별 record를 구분함

### Candidate registration checklist record

- 경로:
  - `runtime-data/generated_skill_reviews/<skill_id>.checklist.json`
- 의미:
  - reviewer/operator가 candidate readiness를 yes/no 항목으로 고정한 최종 checklist
  - `all_checks_passed`는 checklist boolean 필드들로부터 계산되는 파생 필드

## 3. 수동 변환 절차

수동 변환은 아래 순서를 따른다.

1. queue candidate 확인
   - `runtime-data/generated_skill_queue/<skill_id>.json` 또는 `python review_generated_skills.py show <skill_id>`
   - `pending_manual_review`, validation ok, sandbox passed 여부를 먼저 확인한다.

2. review decision 확인
   - `runtime-data/generated_skill_reviews/<skill_id>.review.json`
   - `approve_for_consideration`인지 확인한다.
   - `rejected` 또는 `needs_followup`이면 수동 변환을 진행하지 않는다.

3. promotion packet 확인
   - `runtime-data/generated_skill_packets/<skill_id>.packet.json`
   - `criteria_check_passed`, `blockers`, `overwrite_risk`, `requires_manual_transform`를 확인한다.

4. transform template 생성 및 검토
   - `runtime-data/generated_skill_transforms/<skill_id>.transform.json`
   - `required_manual_edits`, `removed_fields`, `adjusted_fields`, `risk_checks`를 읽는다.

5. `target_name` 수동 결정
   - generated draft 이름을 그대로 사용하지 않는다.
   - production-safe naming을 사람이 직접 정한다.
   - unresolved naming collision 상태에서는 진행하지 않는다.

6. production candidate metadata 수동 보완
   - description
   - capabilities
   - inputs
   - outputs
   - candidate target path
   - 위 항목은 transform template의 placeholder/초안 값을 그대로 신뢰하지 않는다.

7. generated-only field 제거 확인
   - `sandbox_only`
   - `promotion_required`
   - `validation_summary`
   - `sandbox_result_summary`
   - `last_validation_report`
   - `last_sandbox_result`
   - `last_queue_entry`
   - 위 필드는 production candidate 본문에 포함하지 않는다.

8. overwrite / naming / core conflict 재검토
   - transform template의 `risk_checks`를 다시 본다.
   - `overwrite_risk != none`이면 중단 또는 follow-up 처리한다.
   - core skill overwrite 가능성이 있으면 진행하지 않는다.

9. approval record 확인
   - `runtime-data/generated_skill_reviews/<skill_id>.approval.json`
   - process상 필요하다면 `transform_approval` 또는 `promotion_approval` 존재 여부를 확인한다.
   - approval record는 실행 권한이 아니라 audit 흔적이다.

10. production candidate artifact 초안 생성
   - 이 문서에서 정의하는 candidate schema로 사람이 별도 초안을 만든다.
   - generated draft 파일을 move/rename 하지 않는다.
   - transform template을 자동 반영하지 않는다.

11. 최종 승격 여부는 별도 단계로 남김
   - production registration은 이 문서의 범위 밖이다.
   - candidate artifact 작성이 곧 promotion이 아니다.

## 4. Production Candidate Artifact 규격

production candidate artifact는 실제 production 등록 파일이 아니라, **human-reviewed candidate artifact 초안**으로 해석한다.

권장 구조:

```json
{
  "target_name": "runtime_state_summarizer_v1",
  "target_path": "skills/runtime_state_summarizer_v1.json",
  "reviewed_description": "Human-reviewed production candidate description",
  "reviewed_capabilities": ["read_only", "summary", "formatting"],
  "reviewed_inputs": ["runtime_state"],
  "reviewed_outputs": ["summary_lines", "summary_text"],
  "source_skill_id": "runtime_state_summarizer_xxx",
  "source_packet_id": "runtime_state_summarizer_xxx.packet",
  "source_transform_template": "runtime_state_summarizer_xxx.transform",
  "source_approval_record": "runtime_state_summarizer_xxx.approval",
  "manual_transform_completed_by": "mellow",
  "manual_transform_completed_at": "2026-03-23T14:30:00+09:00",
  "overwrite_risk": "none",
  "rollback_reference": "runtime_state_summarizer_xxx.rollback",
  "notes": [
    "candidate only",
    "production registration still requires separate manual step"
  ]
}
```

규칙:

- generated 전용 필드는 candidate 본문에 넣지 않는다.
- `sandbox_only`, `promotion_required`, runtime-only metadata는 candidate 본문에서 제거한다.
- source reference는 audit와 traceability 용도로 유지할 수 있다.
- `target_path`는 candidate 경로 해석일 뿐, 실제 write 권한을 의미하지 않는다.

## 5. 금지 규칙

아래는 항상 금지다.

- `runtime-data/generated_skills/*.json`를 `skills/`로 직접 move/rename 하는 것
- transform template을 자동으로 production artifact로 승격하는 것
- approval record가 있다고 해서 production registration을 수행하는 것
- review decision / approval decision을 promotion execution으로 해석하는 것
- core skill overwrite
- naming collision unresolved 상태에서 진행하는 것

핵심 해석:

> generated draft는 source material이고, transform template은 guide이며, approval record는 흔적이다. 셋 모두 production artifact 자체가 아니다.

## 6. approval / transform 관계

세 개념은 서로 다르다.

### Review decision

- 의미:
  - 이 generated skill을 승격 검토 대상으로 볼지에 대한 판단
- enum:
  - `approve_for_consideration`
  - `rejected`
  - `needs_followup`

### Approval record

- 의미:
  - transform/promotion 단계에서 최종 승인 흔적
- enum:
  - `approved`
  - `rejected`
  - `needs_followup`
- type:
  - `transform_approval`
  - `promotion_approval`

### Manual transform execution

- 의미:
  - review decision과 approval record를 근거로, 사람이 production candidate artifact를 만드는 과정

중요:

- review decision은 approval로 자동 변환되지 않는다.
- approval record는 transform template을 자동 반영하지 않는다.
- manual transform execution은 위 둘을 참고할 뿐, 자동 합성 단계가 아니다.

## 7. rollback / disable 준비

실제 rollback 실행은 이 문서의 범위가 아니다.

다만 수동 변환 단계에서 아래를 준비해야 한다.

- rollback reference 확보
- `runtime-data/generated_skill_reviews/<skill_id>.rollback.json` 경로 규칙 참조
- candidate 채택 후 철회 시 어떤 record를 남길지 미리 정리

유지 원칙:

- runtime-data 원본 artifact는 audit로 유지한다
- queue/history는 삭제하지 않는다
- rollback은 production 반영본에 대한 별도 수동 조치로 남긴다

## 8. Reviewer / Operator Checklist

아래 항목은 모두 `yes`여야 한다.

- review decision exists
- approval record exists if the current process requires it
- candidate registration checklist exists if readiness has already been recorded
- validation passed
- sandbox passed
- sandbox_only invariant confirmed
- promotion_required invariant confirmed
- generated-only fields removed
- target_name manually chosen
- naming collision resolved
- core skill overwrite absent
- rollback reference prepared
- direct move not used

하나라도 `no`면 production candidate artifact 초안을 확정하지 않는다.

## 9. 예시

### runtime_state_summarizer 계열

- source:
  - `runtime-data/generated_skills/runtime_state_summarizer_xxx.json`
- candidate 해석:
  - runtime state를 요약하는 production candidate 초안
- 수동 보완 포인트:
  - target name 확정
  - 운영 설명문 보강
  - output contract 검토

### proposal_summary_formatter 계열

- source:
  - `runtime-data/generated_skills/proposal_summary_formatter_xxx.json`
- candidate 해석:
  - proposal summary formatting 전용 candidate 초안
- 수동 보완 포인트:
  - proposal metadata 설명 정리
  - capabilities 재확인
  - naming collision 검토

### review_note_compactor 계열

- source:
  - `runtime-data/generated_skills/review_note_compactor_xxx.json`
- candidate 해석:
  - duplicated review note compaction candidate 초안
- 수동 보완 포인트:
  - compacted output policy 정리
  - reviewer-facing description 재작성

예시 해석:

- 위 예시는 모두 candidate artifact 단계까지만 허용된다.
- 실제 production 반영 예시는 이 문서에 포함하지 않는다.

## 10. 현재 결론

현재 `autonomous_agent`에서 generated skill manual transform execution은 아래처럼 해석해야 한다.

- generated draft direct move는 금지다
- transform template은 guide artifact다
- approval record는 execution이 아니라 approval trace다
- production candidate artifact는 사람이 따로 작성해야 한다
- production registration은 여전히 별도 수동 단계다
