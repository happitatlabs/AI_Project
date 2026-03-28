if (existsPendingAdjustment(claimId)) {
    throw new IllegalStateException("이미 처리 중인 건이 존재합니다.");
}