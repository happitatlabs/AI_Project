# State Transition Complex Expansion Sample

상태: provisional_measured  
분류: runnable measured expansion sample

이 디렉터리는 상태 전이 복잡형 구조를 다루는 확장 샘플이다.  
현재는 measured sample 상태로 유지하며, promoted regression에는 아직 포함하지 않는다.

현재 구성:
- `scenario.md`
- `input_manifest.json`
- `expected_assertions.yaml`
- `assets/`
- `notes/`

현재 용도:
- 상태 전이 refactor 축 수동/반자동 검증
- measured anchor 기록
- promotion 후보 비교

현재 비허용 용도:
- canonical golden regression
- promoted expansion regression의 고정 축

참고:
- 현재 promotion 세트 대비 증분 검증 가치가 낮아 measured 상태로 유지한다.
