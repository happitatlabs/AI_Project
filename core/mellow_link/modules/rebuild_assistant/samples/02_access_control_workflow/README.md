# Access Control Workflow Expansion Sample

상태: promoted_expansion_regression  
분류: runnable measured expansion sample

이 디렉터리는 권한 + 승인 흐름형 레거시 구조를 다루는 확장 샘플이다.  
access-control narrative와 workflow 중심 구조 판단이 안정적으로 유지되는지 확인할 때 사용한다.

현재 구성:
- `scenario.md`
- `input_manifest.json`
- `expected_assertions.yaml`
- `assets/`
- `notes/`

현재 용도:
- promoted expansion regression
- approval/access-control detector 안정성 확인
- measured anchor 기반 drift 감시

자동 회귀 기준은 아래 테스트를 본다.
- [`test_refactoring_support_promoted_expansion_samples.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/tests/test_refactoring_support_promoted_expansion_samples.py)
