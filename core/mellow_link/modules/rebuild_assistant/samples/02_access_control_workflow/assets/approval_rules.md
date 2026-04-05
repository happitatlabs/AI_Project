# Approval Rules

- 1천만 원 이상 청구는 `CLAIM_AUDIT` 부서만 승인할 수 있다.
- `REQUESTED -> TEAM_LEAD_APPROVED -> AUDIT_APPROVED` 순서로 상태가 전이된다.
- 승인자는 자신의 현재 역할과 단계에 맞는 액션만 수행할 수 있다.
- 같은 승인 단계 조건이 서비스와 정책 컴포넌트 양쪽에 동시에 존재한다.
