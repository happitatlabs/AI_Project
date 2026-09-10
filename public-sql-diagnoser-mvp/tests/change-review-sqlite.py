"""Counterexamples on isolated fixture expressions, not a full-query equivalence test."""
import json
import re
import sqlite3
from pathlib import Path

queries = json.loads(Path("reports/change-review/isolated-sql.json").read_text(encoding="utf-8"))
schema = """
CREATE TABLE customers(customer_id INTEGER, customer_name TEXT, region TEXT);
CREATE TABLE orders(order_id INTEGER, customer_id INTEGER, status TEXT, order_date TEXT);
CREATE TABLE order_items(order_id INTEGER, product_id INTEGER, quantity REAL, unit_price REAL);
CREATE TABLE payments(payment_id INTEGER, customer_id INTEGER, payment_status TEXT, payment_date TEXT, amount REAL);
CREATE TABLE products(product_id INTEGER, category_id INTEGER, price REAL);
CREATE TABLE refunds(customer_id INTEGER, refund_amount REAL);
"""
results = []


def check(name, query_name, rows, expected_before, expected_after):
    with sqlite3.connect(":memory:") as db:
        db.executescript(schema)
        db.execute("INSERT INTO customers VALUES (1, 'test', 'R')")
        for table, values in rows.items():
            for row in values:
                db.execute("INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in row) + ")", row)
        outputs = {}
        for side, sql in queries[query_name].items():
            # SQLite has no ANSI DATE literal. ISO date-only TEXT is an explicit test assumption.
            adapted = re.sub(r"\bDATE ('\d{4}-\d{2}-\d{2}')", r"\1", sql)
            outputs[side] = db.execute(adapted).fetchall()
        assert outputs["before"] == expected_before, (name, outputs)
        assert outputs["after"] == expected_after, (name, outputs)
        results.append({"case": name, **outputs})


check("different prices for same order/product", "total_sales", {
    "orders": [(10, 1, "COMPLETED", "2025-01-01")],
    "order_items": [(10, 1, 1, 10), (10, 1, 1, 20)],
}, [(40.0,)], [(30.0,)])
check("latest completed order without details", "last_order_date", {
    "orders": [(10, 1, "COMPLETED", "2025-01-01"), (11, 1, "COMPLETED", "2025-02-01")],
    "order_items": [(10, 1, 1, 10)],
}, [("2025-01-01",)], [("2025-02-01",)])
check("no successful payment", "successful_payment_amount", {
    "orders": [(10, 1, "COMPLETED", "2025-01-01")],
    "order_items": [(10, 1, 1, 10)],
}, [(0,)], [(None,)])
check("earlier completed order without details moves payment boundary", "successful_payment_amount", {
    "orders": [(10, 1, "COMPLETED", "2025-01-01"), (11, 1, "COMPLETED", "2025-02-01")],
    "order_items": [(11, 1, 1, 10)],
    "payments": [(1, 1, "SUCCESS", "2025-01-15", 100)],
}, [(0,)], [(100.0,)])
check("expensive product bought only in pending order", "expensive_purchase", {
    "orders": [(10, 1, "PENDING", "2025-01-01")],
    "order_items": [(10, 1, 1, 100)],
    "products": [(1, 1, 100), (2, 1, 10)],
}, [(1,)], [])
check("neither successful payment nor recent activity", "additional_filter", {}, [], [(1,)])
check("nullable refund customer enters NOT IN result", "refund_null", {
    "orders": [(10, 2, "COMPLETED", "2025-01-02")],
    "refunds": [(2, 10), (None, 100)],
}, [(1,)], [])

report = {
    "engine": "SQLite", "version": sqlite3.sqlite_version,
    "scope": "isolated projections/predicates extracted from supplied SQL; not the entire A/B query",
    "assumptions": ["ISO date-only TEXT; ANSI DATE literals adapted only in tests", "nullable customer_id in refunds", "no uniqueness or foreign-key constraints imposed", "REAL amounts with exactly representable test values", "results do not prove universal equivalence"],
    "results": results,
}
Path("reports/change-review/sqlite-counterexamples.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
