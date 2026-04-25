# Success Full Golden Sample

상태: canonical-golden  
분류: runnable golden sample

이 디렉터리는 회계 확장 성공 경로를 고정 검증하는 canonical golden 샘플이다.  
거짓 구조 판단 없이 accounting extension이 정상적으로 계산 가능 상태를 유지하는지 확인할 때 사용한다.

현재 자산:
- `accounting_payload.json`
- `legacy_context.txt`

현재 용도:
- canonical golden regression
- accounting success path baseline
- `decision_count=0` 계열 기대값 보호

자동 회귀 기준은 아래를 본다.
- [`REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
- [`test_refactoring_support_golden_samples.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/tests/test_refactoring_support_golden_samples.py)
