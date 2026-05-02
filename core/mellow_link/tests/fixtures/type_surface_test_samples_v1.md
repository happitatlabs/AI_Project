# Type Surface Test Samples v1

This file contains the minimum manual review sample set for `document`, `code`,
and `mixed` external surfaces.

## CODE Sample: SQL JOIN Query

### Input

```sql
SELECT o.order_id, o.status, u.name
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'PENDING'
AND o.created_at >= '2024-01-01';
```

### Expected Structure

```text
핵심 문제:
- 상태 조건 필터가 하드코딩되어 있음

영향:
- 특정 기간/상태 변경 시 쿼리 수정 필요
- 유지보수 비용 증가

권장 조치:
- 상태 값을 파라미터화
- 조회 조건 분리

검증 포인트:
- 상태 변경 시 쿼리 수정 여부
- 인덱스 사용 여부
```

## CODE Sample: Pre-save Validation Logic

### Input

```sql
INSERT INTO orders (user_id, amount)
SELECT user_id, amount
FROM temp_orders
WHERE amount > 0
AND user_id IS NOT NULL;
```

### Expected Structure

```text
핵심 문제:
- 입력 검증 로직이 SQL에 직접 포함됨

영향:
- 검증 정책 변경 시 쿼리 수정 필요

권장 조치:
- 검증 로직을 서비스 계층으로 분리

검증 포인트:
- 음수 금액 입력 차단 여부
- NULL user_id 처리 방식
```

## DOCUMENT Sample: Approval Process Description

### Input

```text
승인 프로세스는 승인 요청, 승인 단계, 예외 처리로 구성됩니다.
각 단계에서 승인 권한과 상태 전이 규칙이 다르게 적용됩니다.
```

### Expected Structure

```text
문제:
- 승인 규칙과 상태 전이 로직이 분산됨

선택지:
- 승인 흐름 중심 구조
- 단계 분리 구조

결론:
- 승인 흐름 중심 구조 검증 후 적용

이유:
- 흐름 일관성 확보
- 예외 처리 분리 필요
```

## MIXED Sample: Description Plus SQL

### Input

```text
주문 마감은 상태 전이 조건에 따라 자동 처리됩니다.

SELECT order_id
FROM orders
WHERE status = 'READY'
AND closing_time < NOW();
```

### Expected Structure

```text
문서 요약:
- 주문 마감은 상태 기반 자동 처리

코드 분석:
핵심 문제:
- 상태 조건이 하드코딩됨

영향:
- 마감 조건 변경 시 쿼리 수정 필요

권장 조치:
- 상태 조건 분리

검증 포인트:
- 마감 조건 변경 시 영향 범위
```

## Review Use

1. Run each sample through the system.
2. Export or view the external result.
3. Compare the structure with the expected output shape.
4. Record `OK`, `WARN`, or `FAIL` with the criteria in `type_surface_review_criteria.md`.
