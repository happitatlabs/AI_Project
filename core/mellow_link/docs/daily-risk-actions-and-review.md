# Daily Risk Actions and Review Boundary

## 자동 행동

Priority 4 analyzer가 자동으로 할 수 있는 행동은 다음뿐이다.

- immutable assessment와 signal 저장
- 사용자 본인에게 표시할 advisory action code 생성
- audit event 기록

자동 알림·연락, Pilot 상태 변경, Delivery 또는 Package 차단, 처방 조언, 자동 해결은 금지한다. `urgent_review`도 이 경계를 넓히지 않는다.

## 검토 주체

초기 review 대상은 해당 DailyState를 소유한 인증 사용자 본인이다. Pilot Operator Approval Queue는 업무 납품 승인용이므로 재사용하지 않는다. `ADMIN` 역할만으로 다른 사용자의 health assessment 접근을 허용하지 않는다.

별도 보호자·임상가·안전 운영자 큐는 동의, 최소 권한, 긴급 정책과 책임 범위를 설계한 후의 별도 작업이다.

## 허용 Action

| Action | 주체 | 결과 |
| --- | --- | --- |
| `acknowledge` | subject user | 확인 시각과 새 assessment version 기록 |
| `mark_disputed` | subject user | 제한된 reason code로 오탐/입력 오류 표시 |
| `suppress` | subject user | suppressible signal을 최대 24시간 UI active 목록에서 숨김 |
| `replay` | subject user | 최신 snapshot/rule set으로 새 immutable 평가 요청 |

`resolve`는 사용자가 안전 signal을 수동 삭제하는 명령이 아니다. 후속 평가에서 해당 signal이 더 이상 생성되지 않을 때 새 assessment가 resolved 관계를 기록한다.

## Support UX

안전 관련 signal은 비판단적인 문구로 사용자가 입력을 다시 확인하고 자신이 신뢰하는 사람이나 지역의 적절한 전문·응급 지원을 선택하도록 안내할 수 있다. 특정 국가 연락처를 하드코딩하거나 analyzer가 응급 대응을 완료했다고 주장하지 않는다. 지원 내용은 별도 정책으로 지역화한다.

## 감사

모든 action은 expected version, idempotency key, actor의 opaque self reference, event time과 reason code를 append-only audit에 남긴다. 자유 텍스트 comment는 초기 범위에 포함하지 않는다.
