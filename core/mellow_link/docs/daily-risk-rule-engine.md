# Daily Risk Rule Engine Contract

## 결정

초기 analyzer는 코드로 version 관리되는 결정적 rule만 사용한다. LLM, 생성형 AI, 외부 임상 API, 학습된 위험 점수는 사용하지 않는다. 활성 rule set은 immutable identifier `daily-risk-v1`로 저장한다.

## 초기 Rule

| Rule ID | 입력 | Match | 결과 |
| --- | --- | --- | --- |
| `daily.safety.self_harm_urge_reported.v1` | `safety.selfHarmUrge` | 유효한 값이 `0`보다 큼 | category `safety`, severity `urgent_review`, reason `self_harm_urge_reported` |

값 `0`은 이 rule에 match하지 않는다. `1`부터 `10`까지를 서로 다른 임상 위험 단계로 나누지 않는다. 이는 사용자의 직접 보고를 보존하는 operational advisory이며 임박성, 자살 의도 또는 진단을 추론하지 않는다.

DailyState가 없거나 required field가 유효하지 않으면 rule을 거짓으로 취급하지 않고 assessment를 `insufficient_data`로 만든다.

## Rule metadata

각 rule은 다음 metadata를 제공한다.

- immutable `rule_id`와 정수 `version`
- category, required input field, threshold
- match 및 missing/stale 처리
- severity와 reason code
- evidence field allowlist
- enabled flag
- deterministic evaluation order

같은 ID/version의 의미를 수정하지 않는다. 변경은 새 version 또는 새 rule set으로 배포한다. 비활성 rule은 실행되지 않지만 metadata 조회에는 상태가 표시된다.

## 평가와 충돌

Rule은 canonical snapshot만 읽으며 부작용 없는 함수로 평가한다. 출력은 `(category, severity, reason_code, evidence_field)` 순으로 정렬하고 동일 `(rule_id, evidence_ref)` signal을 제거한다. 여러 signal의 결론은 [Aggregation Contract](daily-risk-aggregation.md)를 따른다.

## 변경 게이트

통증, 기분, 수면, 에너지 또는 추세 threshold를 추가하려면 다음이 필요하다.

- 명시적 안전·제품 근거와 비의료적 표현
- 새 rule/version 및 snapshot contract
- 0/10과 threshold 경계 테스트
- 오탐, 누락, stale 및 회귀 테스트
- 자동 행동 경계 재검토

## 근거 경계

WHO는 자해·자살 생각을 심각한 distress로 다루고 비판단적인 지원과 직접 확인을 권고한다. NIMH ASQ는 별도의 검증된 질문 세트다. 본 rule은 ASQ를 실시하거나 대체하지 않는다.

- [WHO: Suicide Q&A](https://www.who.int/news-room/questions-and-answers/item/suicide)
- [NIMH: ASQ Information Sheet](https://www.nimh.nih.gov/research/research-conducted-at-nimh/asq-toolkit-materials/asq-tool/asq-information-sheet)
