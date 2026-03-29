if claim.amount >= 10000000:
    if user.dept != "CLAIM_AUDIT":
        raise PermissionError("승인 권한 없음")