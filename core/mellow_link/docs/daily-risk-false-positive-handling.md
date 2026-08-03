# Daily Risk False-positive and Self-review Action Contract

## 원칙

과거 assessment와 signal은 삭제하거나 수정하지 않는다. 오탐, 사용자 입력 정정, rule 변경은 별도 action 및 후속 assessment로 표현한다.

## Action 계약

| Event | 선행 조건 | 필수 입력 | 결과 |
| --- | --- | --- | --- |
| `acknowledge` | latest completed assessment | expected version, idempotency key | acknowledged action과 version +1 |
| `mark_disputed` | latest completed assessment | bounded reason code, expected version, key | disputed action과 version +1 |
| `suppress` | suppressible non-urgent signal | reason code, 최대 24시간, version, key | 만료 가능한 suppression action |
| `reopen` | suppression/dispute가 있고 signal이 후속 평가에서 재발 | 새 evaluation reference | 원 action을 보존하고 active 표시 |

허용 dispute reason은 `input_entry_error`, `rule_not_applicable`, `already_addressed`, `other_bounded`다. 자유 텍스트 의료 정보는 받지 않는다.

`urgent_review`는 suppress할 수 없고 acknowledge 또는 dispute만 가능하다. acknowledge와 dispute는 severity를 낮추거나 signal을 해결하지 않는다.

## Version과 Idempotency

모든 action은 assessment의 exact expected version을 요구한다. stale 또는 임의로 높은 version은 `version_conflict`다. 동일 key와 동일 payload는 기존 결과를 반환하고 audit를 늘리지 않는다. 같은 key의 다른 payload는 `idempotency_conflict`다.

## Rule 변경과 재평가

Rule set version이 달라지면 이전 assessment를 다시 쓰지 않고 새 assessment를 생성한다. 후속 평가에서 signal이 사라지면 관계 event `resolved_by_evaluation`을 기록한다. 기존 평가의 당시 판단은 감사 가능하도록 유지한다.

## 권한

초기에는 subject user만 action을 수행한다. 일반 관리자, Pilot reviewer, 프로젝트 운영자 capability는 권한 근거가 아니다.
