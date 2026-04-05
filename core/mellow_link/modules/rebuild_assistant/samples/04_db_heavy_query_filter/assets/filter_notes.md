# Filter Notes

- category, keyword, requester, hidden 여부 조건이 여러 query에 반복된다.
- UI 필터 조립과 SQL predicate가 서로 비슷한 조회 조건을 가진다.
- query_filter_leak와 반복 조회 조건 탐지가 주요 검증 포인트다.
