# 07_order_closure_false_positive_minimal

이 샘플은 `order_closure / 주문 마감` false positive를 수동 재현하기 위한 heuristic follow-up sample이다.

목표:
- business asset은 검토 대기열(review queue) 도메인으로 유지한다.
- 실제 주문/마감 도메인 없이도 아래 토큰이 domain anchor를 오염시키는지 확인한다.
  - `review_required`
  - `display_order`
  - `closeDialog`

운영 규칙:
- regression 대상이 아니다.
- heuristic 추적 또는 validation follow-up에서만 사용한다.
- 기대 방향은 `주문 마감` anchor가 선택되지 않는 것이다.
