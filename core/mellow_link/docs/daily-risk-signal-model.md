# Daily Risk Signal Model

- 문서 상태: Implementation contract draft
- rule set: `daily-risk-v1`

## 모델

`RiskEvaluationRun`은 한 번의 실행, `DailyRiskAssessment`는 일별 결론, `RiskSignal`은 versioned rule이 만든 설명 가능한 근거다.

| 필드 | 계약 |
| --- | --- |
| `assessment_ref` / `signal_ref` | 외부에 안전한 opaque reference |
| `subject_ref`, `local_date`, `timezone` | 분석 주체와 local-date 경계 |
| `rule_id`, `rule_version`, `rule_set_version` | 결과를 재현하는 불변 버전 |
| `category` | 초기에는 `safety`만 허용 |
| `severity` | `notice`, `review_required`, `urgent_review` |
| `reason_code` | 자유 텍스트가 아닌 안정적인 코드 |
| `evidence_ref` | source 원문이 아닌 DailyState의 안전한 reference와 field name |
| `detected_at`, `evaluation_window` | UTC instant와 평가 대상 local date |
| `input_snapshot_version` | canonical input digest |
| `acknowledged_at`, `resolved_at`, `suppression` | 운영 행동 상태; 원 평가를 덮어쓰지 않음 |

`confidence`와 확률은 사용하지 않는다. 결정적 threshold 결과에 임상적 확률처럼 보이는 값을 붙이지 않는다.

## Severity 의미

- `notice`: 정보성 advisory. 초기 rule set은 생성하지 않지만 확장 가능한 최저 단계다.
- `review_required`: 사용자가 결과와 입력을 다시 확인해야 한다.
- `urgent_review`: 사용자가 직접 보고한 안전 관련 입력을 즉시 눈에 띄게 다시 확인해야 한다. 임박성, 의도, 진단을 의미하지 않는다.

색상만으로 severity를 표현하지 않고 라벨과 설명을 함께 제공한다.

## Assessment 결과

`overall_result`는 다음만 허용한다.

- `no_signal`
- `review_required`
- `urgent_review`
- `insufficient_data`

`no_signal`은 건강상 안전함을 보증하지 않는다. 정의된 rule이 현재 snapshot에서 signal을 만들지 않았다는 뜻뿐이다.

## 상태 보존

Assessment와 signal은 생성 후 불변이다. acknowledge, dispute, suppression 같은 행동은 별도 action record와 version 증가로 기록한다. 새 입력 또는 rule version으로 재평가하면 새 assessment를 만들고 이전 것을 `superseded`로 연결한다.

## 관련 문서

- [Rule Engine](daily-risk-rule-engine.md)
- [Aggregation](daily-risk-aggregation.md)
- [False-positive Handling](daily-risk-false-positive-handling.md)
