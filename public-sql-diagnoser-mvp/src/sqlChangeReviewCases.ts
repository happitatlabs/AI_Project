import type { SqlChangeSeverity } from "./sqlChangeReview.js";

export type SqlChangeReviewCase = {
  afterSql: string;
  beforeSql: string;
  description: string;
  expected: {
    findingIds: string[];
    questionIds: string[];
    severity: SqlChangeSeverity;
    structuralChange: boolean;
  };
  id: string;
  label: string;
};

export const SQL_CHANGE_REVIEW_CASES: SqlChangeReviewCase[] = [
  {
    id: "join-aggregation-change",
    label: "JOIN 및 집계 기준 변경",
    description: "결제 테이블과 날짜 조건이 추가되고 집계 대상이 주문 항목 금액에서 결제 금액으로 바뀐 사례입니다.",
    beforeSql: `SELECT
  o.order_id,
  o.customer_id,
  SUM(oi.quantity * oi.unit_price) AS order_amount
FROM orders o
JOIN order_items oi
  ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.order_id, o.customer_id;`,
    afterSql: `SELECT
  o.order_id,
  o.customer_id,
  SUM(p.payment_amount) AS paid_amount
FROM orders o
JOIN order_items oi
  ON oi.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
WHERE o.order_date >= DATE '2026-01-01'
GROUP BY o.order_id, o.customer_id;`,
    expected: {
      findingIds: ["filter-change", "join-change"],
      questionIds: ["verify-filter-scope", "verify-join-cardinality"],
      severity: "warning",
      structuralChange: true,
    },
  },
  {
    id: "unsafe-update-scope",
    label: "UPDATE 범위 조건 제거",
    description: "특정 주문만 변경하던 UPDATE에서 WHERE 조건이 사라진 고위험 사례입니다.",
    beforeSql: `UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = :orderId;`,
    afterSql: `UPDATE orders
SET status = 'CANCELLED';`,
    expected: {
      findingIds: ["write-filter-removed"],
      questionIds: ["verify-write-scope", "verify-rollback"],
      severity: "critical",
      structuralChange: true,
    },
  },
  {
    id: "write-target-change",
    label: "쓰기 대상 테이블 변경",
    description: "동일한 UPDATE 문이 임시 적재 테이블 대신 운영 고객 테이블을 변경하도록 바뀐 사례입니다.",
    beforeSql: `UPDATE customer_staging
SET status = 'ACTIVE'
WHERE batch_id = :batchId;`,
    afterSql: `UPDATE customers
SET status = 'ACTIVE'
WHERE batch_id = :batchId;`,
    expected: {
      findingIds: ["operation-change"],
      questionIds: ["verify-rollback", "verify-table-impact"],
      severity: "critical",
      structuralChange: true,
    },
  },
  {
    id: "select-star-introduced",
    label: "SELECT * 도입",
    description: "명시 컬럼 조회가 전체 컬럼 조회로 바뀌어 스키마 변경 영향이 커질 수 있는 사례입니다.",
    beforeSql: `SELECT order_id, customer_id, status
FROM orders
WHERE status = 'PAID';`,
    afterSql: `SELECT *
FROM orders
WHERE status = 'PAID';`,
    expected: {
      findingIds: ["new-risk-select_star"],
      questionIds: ["verify-unparsed-difference"],
      severity: "notice",
      structuralChange: true,
    },
  },
  {
    id: "formatting-only",
    label: "표현만 변경된 SQL",
    description: "공백과 줄바꿈만 달라지고 파서가 인식한 주요 구조는 동일한 대조 사례입니다.",
    beforeSql: `SELECT order_id
FROM orders
WHERE status = 'PAID';`,
    afterSql: `SELECT
  order_id
FROM orders
WHERE status = 'PAID';`,
    expected: {
      findingIds: ["no-structural-change"],
      questionIds: ["verify-unparsed-difference"],
      severity: "info",
      structuralChange: false,
    },
  },
];
