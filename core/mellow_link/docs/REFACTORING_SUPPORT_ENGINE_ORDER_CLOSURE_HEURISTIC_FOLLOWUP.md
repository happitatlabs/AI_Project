# Refactoring Support Engine Order Closure Heuristic Follow-up

기준일: 2026-04-05  
상태: Follow-up  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

`order_closure / 주문 마감` 계열 표현이 실제 자산과 무관하게 결과 표현에 섞이는지 점검하기 위한 follow-up 문서다.  
이번 문서는 수정안이 아니라 유입 경로와 점검 우선순위를 고정한다.

## 현재 판단

1차 원인은 `goal wording contamination`으로 이미 분리됐다.  
`order_closure / 주문 마감`은 2차 점검 대상이며, 현재는 `domain-anchor spillover` 후보로 관리한다.

## 현재 확인된 유입 경로

### 1. Domain Anchor 진입점
- 파일: [service.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/service.py)
- 함수: `_resolve_domain_anchor()`
- 조건:
  - 정규식
    - `order[_/\\-.]?(close|closure)`
    - `(close|closure)[_/\\-.]?order`
    - `orderclose`
    - `orderclosure`
    - `closeorder`
    - `closureorder`
    - `주문.{0,10}마감`
    - `마감.{0,10}주문`
  - 토큰
    - `vip`
    - `agency`
    - `deliveryhold`
    - `review_required`
    - `배송보류`
- 결과:
  - 위 패턴 또는 토큰이 있으면 concept를 `주문 마감`으로 고정한다.

### 2. Concept 확정 이후 영향 범위
- 함수: `_primary_concept()`
  - `_resolve_domain_anchor()`가 값을 반환하면 그 값을 우선 사용한다.
- 함수: `extract_core_business_rules()`
  - `주문 마감`이면 `_extract_java_closure_rules()`로 분기한다.
- 함수: `_rule_templates_for_concept()`
  - `주문 마감` 전용 rule template를 강제로 사용한다.
- 함수: `_retained_contract_specs()`
  - `orders.status`, `delivery_hold_flag`, `channel_code='AGENCY'` 계약을 유지 대상으로 추가한다.
- 함수: `_resource_name()`
  - `주문 마감`이면 resource slug를 `order_closures`로 고정한다.

## 현재 리스크

### Risk-01. Pattern Overreach
- `close`, `closure`, `review_required` 같은 토큰은 일반 구조나 다른 도메인에서도 등장할 수 있다.
- 실제 주문 마감 자산이 없어도 `주문 마감` concept가 고정될 수 있다.

### Risk-02. Concept Cascade
- domain anchor가 한 번 `주문 마감`으로 확정되면
  - business rule 추출
  - retained contract
  - rule template
  - resource slug
  가 연쇄적으로 같은 concept를 따른다.
- 이 경우 오염이 top narrative를 넘어 계획/계약 표현까지 전파된다.

### Risk-03. Mixed Input Source
- `_resolve_domain_anchor()`는 아래를 한 문자열로 합쳐 본다.
  - `goal`
  - `constraints`
  - asset file names
  - source/ui/sql/schema 본문
- 따라서 business asset이 아니라 wrapper wording이나 file naming도 concept anchor를 오염시킬 수 있다.

## 점검 우선순위

### 1순위. false positive 재현
- 실제 주문 마감 자산이 아닌데 아래 중 하나로 anchor가 `주문 마감`이 되는지 확인
  - `close`
  - `closure`
  - `review_required`
  - `deliveryhold`

### 2순위. source separation 확인
- 아래 입력원을 분리해서 어떤 source가 anchor를 만들었는지 기록
  - goal/constraints
  - asset names
  - source code
  - SQL/schema

### 3순위. cascade 영향 범위 캡처
- `주문 마감` anchor가 잡혔을 때 실제로 아래 결과가 바뀌는지 확인
  - core_business_rules
  - retained_contracts
  - recommended_option
  - execution_plan
  - resource_name

## follow-up 체크리스트

- `주문 마감` anchor가 business asset 없이도 활성화되는가
- trigger source가 `goal`, `constraint`, `asset name`, `source body` 중 어디인가
- anchor 활성화 후 `_extract_java_closure_rules()`가 실제로 호출되는가
- anchor 활성화 후 `_rule_templates_for_concept("주문 마감")`가 적용되는가
- anchor 활성화 후 `_retained_contract_specs("주문 마감")`가 적용되는가
- anchor 활성화 후 `_resource_name()`이 `order_closures`로 바뀌는가

## 운영 메모

- 이 문서는 2차 점검용이다.
- 현재 기준에서 즉시 막아야 하는 1차 오염은 `goal wording contamination`이다.
- `order_closure / 주문 마감`은 governance 가드 이후 별도 표본으로 추적한다.
