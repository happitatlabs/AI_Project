# Daily Risk Self-review UX Contract

파일명은 roadmap의 기존 operator UX 분류와 맞추지만, 초기 화면의 사용자는 Pilot operator가 아니라 DailyState를 소유한 사용자 본인이다.

## 필수 상태

| UX state | 표시 |
| --- | --- |
| `loading` | 평가 조회 중 |
| `no_assessment` | 아직 평가 없음과 실행 action |
| `evaluating` | 중복 실행이 막힌 진행 상태 |
| `completed` | overall result, category, freshness, rule version |
| `failed` | 안전한 오류와 허용된 retry |
| `insufficient_data` | 누락 입력과 Daily Check-in 이동 action |
| `no_signal` | 제한된 rule에서 signal 없음; 안전 보증 문구 금지 |
| `review_required` | 명시적 review label과 reason code |
| `urgent_review` | 눈에 띄는 텍스트 label과 support action; 임상 확정 표현 금지 |
| `acknowledged` / `resolved` / `suppressed` | 역사와 현재 active 상태 구분 |
| `conflict` | 새 상태 다시 불러오기 |
| `unauthorized` | 데이터 내용 없이 접근 차단 |

## 화면 정보

- 대상 local date와 timezone
- overall result와 비의료적 설명
- category별 signal, reason code, 안전한 evidence reference
- input freshness와 source updated time
- rule set version과 평가 시각
- acknowledge, dispute, 허용된 suppress, replay action

원 DailyState 값 전체, notes, dailyBrick, 내부 ID/경로를 assessment 화면에 복제하지 않는다.

## 안전 UX

`urgent_review`는 사용자가 직접 입력한 안전 관련 항목을 다시 확인하도록 안내한다. 화면은 analyzer가 응급 여부를 결정했다고 말하지 않으며 자동 연락이 이루어졌다고 암시하지 않는다. 지역별 지원 문구는 analyzer rule과 분리된 명시적 정책에서 제공한다.

## 접근성

- 모든 action은 keyboard로 가능하고 명확한 accessible name을 가진다.
- severity는 색상뿐 아니라 텍스트와 아이콘 의미로 표현한다.
- 비동기 완료·오류 후 focus를 결과 heading 또는 오류 summary로 이동한다.
- 오류에는 복구 action을 제공한다.
- submit 중 버튼을 비활성화하고 idempotency key로 중복 클릭을 방어한다.
- live region은 민감한 상세값을 소리 내어 반복하지 않는다.
