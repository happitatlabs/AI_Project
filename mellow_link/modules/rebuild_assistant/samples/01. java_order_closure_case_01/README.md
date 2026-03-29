# java_order_closure_case_01

JSP/Java 기반 주문 마감 기능의 레거시 샘플이다.

## 포함 파일

- `goal.txt`
- `constraints.txt`
- `legacy.jsp`
- `OrderCloseService.java`
- `query.sql`
- `schema.sql`

## 샘플 의도

이 샘플은 "주문 마감 규칙이 화면, 서비스, SQL에 동시에 퍼져 있는 상태"를 가정한다.

포인트:

- JSP에서 권한/상태 체크가 1차로 수행됨
- Java 서비스에서 금액, 채널, 고객등급 예외 처리 수행
- SQL이 이미 상태와 회수 조건을 일부 내장함
- 숨은 규칙:
  - VIP 고객 건은 야간 마감 금지
  - 대리점 채널은 본사 승인 없이는 고액 마감 금지
  - 배송보류 건은 마감과 동시에 해제 금지

## 추천 입력 방식

1. `goal.txt`를 프로젝트 목표에 사용
2. `legacy.jsp`, `OrderCloseService.java` 업로드
3. `query.sql`, `schema.sql` 업로드
4. `constraints.txt`를 제약 조건에 입력
