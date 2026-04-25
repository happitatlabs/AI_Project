# Amount Limit Golden Sample

상태: canonical-golden  
분류: runnable golden sample

이 디렉터리는 금액 한도 정책 중심 구조를 검증하는 canonical golden 샘플이다.  
validation / amount-threshold 축과 저범위 refactor 판단이 안정적으로 유지되는지 확인할 때 사용한다.

현재 자산:
- `cs_expense_policy.cs`
- `sql_order_limit.sql`

현재 용도:
- canonical golden regression
- amount-threshold narrative baseline
- validation 중심 deterministic 판단 보호

자동 회귀 기준은 아래를 본다.
- [`REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
- [`test_refactoring_support_golden_samples.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/tests/test_refactoring_support_golden_samples.py)
