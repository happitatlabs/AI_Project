# rebuild_assistant 샘플 세트 목록

현재 포함된 샘플:

- `rca_exception_case_01`
  - JSP/Java 기반 예외 규칙 분산 샘플
- `python_claim_adjustment_case_01`
  - Python/Flask 기반 청구 조정 기능 레거시 샘플
- `java_order_closure_case_01`
  - JSP/Java 기반 주문 마감 기능 레거시 샘플
- `ui_01_normal_balanced_upload`
  - `/projects/create` 업로드용 정상 익명화 검증 팩
- `ui_02_ambiguous_identifier_upload`
  - `/projects/create` 업로드용 애매한 식별자 유지 검증 팩
- `ui_03_sensitive_signal_upload`
  - `/projects/create` 업로드용 민감정보 다수 포함 검증 팩
- `ui_04_event_split_upload`
  - `/projects/create` 업로드용 user/dev surface 분리 확인 팩
- `ui_05_dev_failure_guard_mapping`
  - `bundle-runs`용 validation fail dev fixture

UI 업로드/익명화 검증 전용 팩 사용법은 아래 문서를 본다.

- [ANONYMIZATION_UI_SAMPLE_PACKS.md](/C:/Users/Hyein/ClaudeAI/AI_Project/core/mellow_link/modules/rebuild_assistant/samples/ANONYMIZATION_UI_SAMPLE_PACKS.md)

고정 회귀 샘플 세트는 아래 5개를 기준으로 사용한다.

- `00. rca_exception_case_01`
- `01. java_order_closure_case_01`
- `02. python_claim_adjustment_case_01`
- `04. amount_limit`
- `01_success_full`

위 샘플의 기대 결과는 아래 문서와 테스트로 함께 고정한다.

- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
- [test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)

고정 golden set 외에 Phase 3 준비용 확장 샘플 풀도 이 디렉터리에 함께 둔다.

- `01_crud_simple`
- `02_access_control_workflow`
- `03_state_transition_complex`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

새로운 샘플 팩은 `mellow_link/modules` 루트에 별도 폴더로 두지 않는다. 샘플 본문은 항상 이 디렉터리 아래에 두고, 공통 템플릿은 아래 경로에 둔다.

- [samples/_templates/golden_samples_expansion](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/_templates/golden_samples_expansion)

확장 샘플 검증 메모는 아래 문서에 둔다.

- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md)

샘플은 아래 두 계열로 나뉜다.

## 1. 고정 golden set

직접 실행 가능한 입력 자산 묶음이다. 보통 아래 파일 구성을 가진다.

- `README.md`
- `goal.txt`
- `constraints.txt`
- 레거시 코드 파일
- SQL 파일
- 스키마 파일

이 계열은 현재 아래 5개가 canonical 회귀 기준이다.

- `00. rca_exception_case_01`
- `01. java_order_closure_case_01`
- `02. python_claim_adjustment_case_01`
- `04. amount_limit`
- `01_success_full`

## 2. 확장 샘플 풀

Phase 3 전후의 후보 샘플 팩이다. 이 계열은 실행용 자산보다 샘플 정의와 기대 anchor를 먼저 정리하는 구조를 사용한다.

기본 파일 역할은 아래와 같다.

- `scenario.md`
  - 샘플 목적, 분류, 기대 포인트를 설명하는 정의 문서
- `input_manifest.json`
  - 현재 확보한 자산 목록과 기대 focus를 기록하는 인벤토리
- `expected_assertions.yaml`
  - machine-readable golden assertion source
- `notes/*`
  - 사람 검토용 참고 문서
  - 예: `human_review_result_sample.md`
  - 자동 회귀 source로 사용하지 않는다
- `assets/*`
  - 실제 code/sql/ui/schema/doc 입력 자산을 채워 넣는 위치

확장 샘플 풀의 현재 대상은 아래와 같다.

- `01_crud_simple`
- `02_access_control_workflow`
- `03_state_transition_complex`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

이 중 아래 4개는 measured anchor와 stable hash를 기준으로 별도 promoted expansion regression에 포함한다.

- `01_crud_simple`
- `02_access_control_workflow`
- `04_db_heavy_query_filter`
- `05_legacy_tangled_mixed`

이 회귀는 canonical golden 5개를 대체하지 않고, 아래 테스트로 별도 유지한다.

- [test_refactoring_support_promoted_expansion_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_promoted_expansion_samples.py)

나머지 확장 샘플은 아직 measured sample 상태로 유지한다.

- `03_state_transition_complex`

`03_state_transition_complex`를 measured로 유지하는 이유는 품질 문제가 아니라 현재 canonical/promotion 세트 대비 증분 검증 가치가 가장 낮기 때문이다. 상태 전이 refactor 축은 이미 아래 샘플이 상당 부분 커버한다.

- `01. java_order_closure_case_01`
- `05_legacy_tangled_mixed`

## 3. legacy fixture / contract sample

아래 샘플은 golden regression이나 expansion promotion 대상이 아니라, 특정 계약/서술/워크플로 테스트에서만 사용하는 fixture다.

- `02_failure_missing_exchange_rates`
- `03_warning_lenient_policy`
- `06. workflow`

이 계열은 보통 특정 narrative/accounting/workflow 테스트에서 부분적으로만 읽는다. 새로운 golden assertion source를 추가하지 않는다.

## 4. reference-only snippet set

아래 디렉터리는 실행용 샘플 케이스가 아니라 reference snippet 모음이다.

- `03. judgment_template_samples`
- `05. query_filter`

이 계열의 역할은 아래로 제한한다.

- detector / template 축 예시 조각 제공
- 설명 문서나 로컬 수동 점검용 reference
- 향후 runnable sample을 만들 때 seed material 제공

이 계열에는 현재 아래가 없다.

- `goal.txt`
- `constraints.txt`
- `input_manifest.json`
- `expected_assertions.yaml`

따라서 기본 회귀나 promoted regression 대상으로 취급하지 않는다. 승격하려면 별도 runnable sample 디렉터리로 재구성해야 한다.

## 5. heuristic follow-up sample

아래 디렉터리는 runnable asset set이지만 regression 대상이 아니라 heuristic follow-up용 표본이다.

- `07_order_closure_false_positive_minimal`

이 계열의 역할은 아래로 고정한다.

- `domain-anchor spillover` 재현용 최소 자산 제공
- `order_closure / 주문 마감` false positive 수동 점검
- validation 또는 heuristic 추적용 reference

이 계열은 현재 아래 규칙을 따른다.

- `input_manifest.json`과 `expected_assertions.yaml`을 포함한다.
- golden / promoted regression에는 편입하지 않는다.
- 직접적인 `order_closure`, `주문 마감` business term 없이 suspicious token만 포함한다.

권장 사용 방식:

1. 고정 golden set은 기존 자산 파일을 그대로 테스트 입력으로 사용한다.
2. 확장 샘플 풀은 `scenario.md`와 `input_manifest.json`으로 샘플 역할을 먼저 확정한다.
3. 사람이 검토한 Markdown 결과물은 `notes/` 아래에 참고 문서로 보관한다.
4. 자동 회귀 기준은 항상 `expected_assertions.yaml`로만 관리한다.
