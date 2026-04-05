# Workflow Notes

- `READY -> APPROVED -> COMPLETED` 상태 전이가 코드와 SQL 양쪽에 반복된다.
- 상태 전이 규칙이 서비스와 정책 컴포넌트에 동시에 존재한다.
- state_transition_leak detector가 안정적으로 발생하는지 확인하는 것이 목적이다.
