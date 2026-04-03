# rebuild_assistant 샘플 세트 목록

현재 포함된 샘플:

- `rca_exception_case_01`
  - JSP/Java 기반 예외 규칙 분산 샘플
- `python_claim_adjustment_case_01`
  - Python/Flask 기반 청구 조정 기능 레거시 샘플
- `java_order_closure_case_01`
  - JSP/Java 기반 주문 마감 기능 레거시 샘플

고정 회귀 샘플 세트는 아래 5개를 기준으로 사용한다.

- `00. rca_exception_case_01`
- `01. java_order_closure_case_01`
- `02. python_claim_adjustment_case_01`
- `04. amount_limit`
- `01_success_full`

위 샘플의 기대 결과는 아래 문서와 테스트로 함께 고정한다.

- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
- [test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)

모든 샘플은 아래 파일 구성을 기본으로 맞춘다.

- `README.md`
- `goal.txt`
- `constraints.txt`
- 레거시 코드 파일
- SQL 파일
- 스키마 파일

권장 사용 방식:

1. `goal.txt`를 프로젝트 목적 설명으로 사용
2. 코드/SQL/화면 파일을 업로드
3. `constraints.txt`를 제약 조건으로 입력
