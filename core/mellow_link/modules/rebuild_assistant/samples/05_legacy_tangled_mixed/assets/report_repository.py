class ReportRepository:
    def count_pending_adjustments(self, claim_id):
        query = "SELECT COUNT(*) FROM claim_adjustments WHERE claim_id = :claim_id AND status = 'PENDING'"
        return query, claim_id

    def save_report(self, report):
        if report["status"] in ("PAID", "READY") and not report.get("delivery_hold"):
            report["status"] = "COMPLETED"
        statement = "UPDATE reports SET status = :status WHERE report_id = :report_id"
        return statement, report
