# Delivery Readiness Contract

- 문서 상태: Draft for implementation review
- 기준: checklist와 artifact 검증에서 파생되는 읽기 모델

## 결정

`package_ready`는 저장된 수동 boolean이 아니다. 요청 시점의 Pilot 상태, checklist/template version, item 상태, artifact fingerprint를 결합해 결정적으로 계산한다. 응답 snapshot을 캐시할 수 있지만 source version이 달라지면 폐기한다.

## Readiness 값

```text
ready
not_ready
stale
```

- `ready`: assembly 전제조건과 모든 blocking item을 충족했다.
- `not_ready`: missing/pending/invalid 또는 Pilot 상태 때문에 차단됐다.
- `stale`: 이전 검증 뒤 artifact, template 또는 policy version이 변경됐다.

## 판정 입력

| 입력 | 규칙 |
| --- | --- |
| Pilot status/version | assembly는 정확히 `approved`에서만 요청 가능 |
| checklist/template version | 현재 활성 template과 일치해야 함 |
| required items | 모두 `present` 또는 허용된 `waived` |
| optional items | 누락은 warning이며 단독으로 차단하지 않음 |
| artifact fingerprint | 현재 resolver 결과와 일치해야 함 |
| active assembly | 같은 source snapshot의 중복 요청은 replay, 다른 snapshot이면 conflict 또는 새 version |

## Blocking 규칙

다음 중 하나라도 참이면 `package_ready=false`다.

1. Pilot이 `approved`가 아니다.
2. 활성 checklist가 없거나 template version이 현재 정책과 다르다.
3. required item이 `pending`, `missing`, `invalid`, `stale`다.
4. waiver 금지 required item이 `waived`다.
5. optional을 포함한 어떤 item이라도 `stale`다.
6. DOCX resolver가 파일 부재, 손상, 예상하지 않은 content type, size 정책 위반을 보고한다.
7. source artifact set이 검증 snapshot 이후 변경됐다.

`stale`은 불확실한 자료를 조립하지 않기 위해 requirement와 무관하게 blocking으로 처리한다.

## Warning 규칙

- optional item의 `pending`, `missing`, `invalid`
- 허용된 required waiver
- non-blocking delivery note 부재

warning은 응답에 안정적인 code와 item key만 제공한다. waiver reason이나 내부 resolver 오류 원문은 포함하지 않는다.

## Readiness 응답

| 필드 | 의미 |
| --- | --- |
| `pilot_ref` | 안전한 opaque reference |
| `pilot_status`, `pilot_version` | 계산에 사용된 Priority 2 snapshot |
| `checklist_id`, `checklist_version`, `template_version` | 계산 snapshot |
| `readiness` | `ready`, `not_ready`, `stale` |
| `blocking_items` | item key와 안전한 reason code |
| `warnings` | non-blocking code 목록 |
| `artifact_set_fingerprint` | 정렬된 artifact fingerprint의 digest |
| `evaluated_at` | UTC instant |

내부 경로, 원본 파일명, raw report text, 고객 개인정보는 반환하지 않는다.

## Priority 2와의 관계

- checklist 조회는 모든 기존 Pilot 상태를 바꾸지 않는다.
- assembly 요청은 `approved`를 전제로 하지만 성공해도 Pilot을 자동으로 `delivered`로 바꾸지 않는다.
- `delivered`는 실제 전달 확인 command로 남고 package 상태는 별도 축이다.
- 현재 Priority 2 `deliver`는 DOCX 존재를 전제로 한다. 완성 package까지 필수로 만들지는 별도 Open Decision이며 Priority 2 계약을 조용히 강화하지 않는다.
- 기존 project/run DOCX archive resolver를 재사용하고 물리 경로 계산을 복제하지 않는다.
- approval queue와 package assembly queue는 별도 read model이다. Pilot 상태가 두 큐의 공통 권위 원천이다.

## 동시성과 stale 처리

- readiness 응답은 assembly command의 권한 증표가 아니다.
- assembly 요청은 `expected_pilot_version`, `expected_checklist_version`, `artifact_set_fingerprint`를 다시 검증한다.
- 값이 하나라도 달라지면 `readiness_stale` 또는 version conflict이며 assembly/idempotency 성공 record를 만들지 않는다.
- 검사와 assembly request 저장은 동일 transaction 경계에서 재확인한다.

## Open Decisions

- Priority 3 도입 후 기존 `deliver`에 assembled package를 필수 전제로 추가할지 여부
- readiness snapshot cache 저장 여부와 TTL
- artifact size/content policy의 구체 값
- delivered 이후 package 재조회 외 재조립을 허용할지 여부

## 관련 문서

- [Pilot State Machine](pilot-state-machine.md)
- [Approval Queue Design](approval-queue-design.md)
- [Pilot API Contract](pilot-api-contract.md)
- [Checklist Model](delivery-checklist-model.md)
- [Package Assembly](delivery-package-assembly.md)
- [API Contract](delivery-package-api-contract.md)
- [Test Contract](delivery-package-test-contract.md)
