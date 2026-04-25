# Legacy Tangled Mixed Expansion Sample

상태: promoted_expansion_regression  
분류: runnable measured expansion sample

이 디렉터리는 경계가 뒤엉킨 레거시 혼합 구조를 다루는 확장 샘플이다.  
tangled boundary, mixed evidence 해석, operational_source 우선 surface가 안정적으로 유지되는지 확인할 때 사용한다.

현재 구성:
- `scenario.md`
- `input_manifest.json`
- `expected_assertions.yaml`
- `assets/`
- `notes/`

현재 용도:
- promoted expansion regression
- operational_source + secondary redesign signal 검증
- tangled 구조에서의 detector / planning drift 감시

자동 회귀 기준은 아래 테스트를 본다.
- [`test_refactoring_support_promoted_expansion_samples.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/tests/test_refactoring_support_promoted_expansion_samples.py)
