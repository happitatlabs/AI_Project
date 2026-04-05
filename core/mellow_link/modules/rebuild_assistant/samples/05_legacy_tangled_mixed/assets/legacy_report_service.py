def submit_report(report, user, repository, ui):
    if not report.get("title"):
        ui.show_error("title is required")
        return None

    if report.get("amount", 0) >= 10000000 and user.get("dept") != "CLAIM_AUDIT":
        ui.show_error("승인 권한 없음")
        return None

    pending_count = repository.count_pending_adjustments(report["claim_id"])
    if pending_count > 0:
        ui.show_error("이미 처리 중인 건이 존재합니다.")
        return None

    if report["status"] in ("PAID", "READY") and not report.get("delivery_hold"):
        report["status"] = "COMPLETED"

    ReportRepository = repository
    ReportRepository.save_report(report)
    repository.save_report(report)
    ui.navigate("/reports/completed")
    return report
