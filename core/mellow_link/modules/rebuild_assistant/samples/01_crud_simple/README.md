# CRUD Simple Expansion Sample

상태: promoted_expansion_regression  
분류: runnable measured expansion sample

이 디렉터리는 CRUD 단순형 레거시 구조를 대상으로 한 확장 샘플이다.  
low-signal / no-decision 분리와 얇은 CRUD 구조 해석이 흔들리지 않는지 확인할 때 사용한다.

현재 구성:
- `scenario.md`
- `input_manifest.json`
- `expected_assertions.yaml`
- `assets/`
- `notes/`

현재 용도:
- promoted expansion regression
- deterministic core / measured anchor 안정성 확인
- human review 결과와 machine assertion source 분리 연습

현재 비허용 용도:
- canonical golden set 대체
- 단순 reference snippet

자동 회귀 기준은 아래 테스트를 본다.
- [`test_refactoring_support_promoted_expansion_samples.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/tests/test_refactoring_support_promoted_expansion_samples.py)
