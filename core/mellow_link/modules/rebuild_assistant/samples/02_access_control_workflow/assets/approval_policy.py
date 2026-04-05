def apply_approval_policy(claim, user):
    if claim["amount"] >= 10000000 and user["dept"] != "CLAIM_AUDIT":
        raise PermissionError("승인 권한 없음")

    if claim["status"] == "REQUESTED" and user["role"] == "TEAM_LEAD":
        claim["status"] = "TEAM_LEAD_APPROVED"
        return claim

    if claim["status"] == "TEAM_LEAD_APPROVED" and user["role"] == "AUDITOR":
        claim["status"] = "AUDIT_APPROVED"
        return claim

    raise PermissionError("승인 가능한 단계가 아님")
