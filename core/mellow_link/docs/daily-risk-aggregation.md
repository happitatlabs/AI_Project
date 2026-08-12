# Daily Risk Aggregation Contract

## 집계 방식

복잡한 점수나 가중치 합산을 사용하지 않는다. 유효한 active signal 중 가장 높은 severity를 overall result로 사용한다.

```text
urgent_review > review_required > notice
```

초기 rule set에서 signal이 없으면 `no_signal`이다. 필수 입력이 없거나 유효하지 않으면 `insufficient_data`이며 `no_signal`로 낮추지 않는다.

## 세부 규칙

- Category별 signal은 그대로 보존한다.
- 같은 rule과 evidence의 중복 signal은 하나만 유지한다.
- acknowledged signal은 assessment의 역사적 severity를 바꾸지 않는다.
- resolved 또는 suppressed signal은 UI의 active 목록에서 분리하지만 원 평가를 삭제하지 않는다.
- `urgent_review` signal은 suppress할 수 없다.
- 최신 canonical assessment는 같은 날짜의 superseded 결과를 집계에 포함하지 않는다.

## 결과 결정성

Signal 정렬 순서는 severity 내림차순, category, rule ID, evidence reference다. 동일 snapshot과 동일 rule set은 timestamp와 opaque ID를 제외하고 의미상 동일한 assessment를 만든다.

## 한계

Overall result는 임상 진단이나 안전 보증이 아니다. `no_signal`은 제한된 입력과 rule에서 신호가 없었다는 의미이고, `urgent_review`도 응급 여부를 자동 확정하지 않는다.
