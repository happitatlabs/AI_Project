# Refactoring Support Engine Order Closure False Positive Sample Design

기준일: 2026-04-05  
상태: Draft for Follow-up  
기준 문서: [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)  
관련 문서: [REFACTORING_SUPPORT_ENGINE_ORDER_CLOSURE_HEURISTIC_FOLLOWUP.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_ORDER_CLOSURE_HEURISTIC_FOLLOWUP.md)
실제 샘플 경로: [07_order_closure_false_positive_minimal](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/07_order_closure_false_positive_minimal)

## 목적

이 문서는 `order_closure / 주문 마감` false positive를 최소 자산으로 재현하기 위한 synthetic sample 설계를 고정한다.  
목표는 수정안 제시가 아니라, `domain-anchor spillover`를 안정적으로 재현할 수 있는 최소 표본을 정의하는 것이다.

## 재현 목표

다음 현상을 재현 대상으로 본다.

- 실제 business asset은 주문 마감 도메인이 아니다.
- 그럼에도 `_resolve_domain_anchor()`가 `주문 마감`을 선택한다.
- 이후 concept cascade가 아래까지 전파된다.
  - business rule 추출
  - retained contract
  - rule template
  - resource slug

## 최소 synthetic sample 구성

### business asset 4개

1. `review_queue_controller.py`
- 도메인: 문서 검토 대기열
- 실제 역할: 단순 조회 + 검토 완료 처리
- 의도된 오염 토큰:
  - `review_required`
  - `display_order`

2. `review_queue_page.html`
- 도메인: 검토 대기열 화면
- 실제 역할: 목록 조회 + 상태 필터
- 의도된 오염 토큰:
  - `display_order`
  - `closeDialog()`

3. `review_queue.sql`
- 도메인: 검토 대기열 조회
- 실제 역할: 상태 필터 + 정렬
- 의도된 오염 토큰:
  - `display_order`
  - `closed_at`

4. `schema.sql`
- 도메인: review queue schema
- 실제 역할: review queue / review note
- 의도된 오염 토큰:
  - `review_required`

### non-business note 1개

5. `scenario.md`
- 도메인 설명은 `문서 검토 대기열`
- 명시적으로 아래를 적는다.
  - 주문 처리 아님
  - 주문 마감 아님
  - 전환 요구 없음

## 의도된 신호 설계

### 실제로 있어야 하는 것
- `query/filter`
- `review_required`
- `display_order`
- `closeDialog`

### 없어야 하는 것
- `order_closure`
- `주문 마감`
- `deliveryhold`
- `agency`
- 실제 주문/배송/채널 도메인 규칙

## 재현 포인트

### Variant A. Token-Only Spillover
- `review_required`만으로 `주문 마감` anchor가 생기는지 본다.
- 기대: false positive면 `domain-anchor spillover`

### Variant B. Order/Close String Collision
- `display_order`와 `closeDialog`가 한 문서에 같이 있을 때 anchor가 생기는지 본다.
- 기대: 파일명 또는 본문 텍스트 조합이 과잉 해석되면 false positive

### Variant C. Filename Bias
- 파일명에 `review_order_close_helper.py` 같은 문자열을 둔다.
- business domain은 review queue인데 filename만으로 anchor가 생기는지 본다.

## 기대 결과

### 정상 기대
- `narrative_axis != 주문 마감`
- `core_business_rules`에 주문 마감 규칙이 나오지 않는다.
- `_retained_contract_specs()`가 주문 마감 전용 계약을 추가하지 않는다.
- `_resource_name()`이 `order_closures`로 바뀌지 않는다.

### false positive 기대
- `주문 마감` anchor가 선택된다.
- `주문 마감` 전용 rule template가 적용된다.
- retained contract에 `orders.status`, `delivery_hold_flag` 같은 무관 계약이 끼어든다.

## assertion 초안

- `structural_judgment`는 `observation_only` 또는 `refactor`에 머물러야 한다.
- `template_judgment` 또는 `narrative_axis`가 `주문 마감`으로 나오면 false positive 후보로 기록한다.
- `synthetic_signal_detected`와는 별개로 `domain_anchor_spillover_detected` 메모를 validation에 남긴다.

## 운영 메모

- 이 sample은 golden 승격용이 아니라 heuristic follow-up용이다.
- 1차 원인인 `goal wording contamination` 정리 이후에 재현 실험 대상으로 사용한다.
- false positive가 확인되면 별도 validation run 또는 sample note로 증거를 남긴다.
