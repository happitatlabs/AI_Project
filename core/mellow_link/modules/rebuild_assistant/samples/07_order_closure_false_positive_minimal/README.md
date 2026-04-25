# Order Closure False Positive Minimal Sample

상태: heuristic-follow-up  
분류: runnable non-regression follow-up sample

이 디렉터리는 `order_closure / 주문 마감` false positive를 재현하기 위한 최소 표본이다.  
regression baseline이 아니라 heuristic follow-up과 수동 검증에 사용한다.

현재 구성:
- `scenario.md`
- `input_manifest.json`
- `expected_assertions.yaml`
- `assets/`
- `notes/`

현재 용도:
- domain-anchor spillover 재현
- false positive 수동 점검
- heuristic 추적용 reference

현재 비허용 용도:
- canonical golden regression
- promoted expansion regression

운영 규칙:
- business term을 직접 심지 않고 suspicious token만 포함하는 현재 의도를 유지한다.
- `expected_assertions.yaml`은 follow-up 기록용이지 baseline regression 승격을 뜻하지 않는다.
