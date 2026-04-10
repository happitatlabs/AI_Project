# rebuild_assistant

`rebuild_assistant`는 JSP/Java/SQL 계열 레거시 기능을 단일 기능 또는 단일 페이지 단위로 분석하고, 현대화 방향과 실행 가능한 조치를 제안하는 모듈입니다.

현재 엔진 구조와 authoritative payload 기준 문서는
[`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)다.
이 README는 공개 실행선, 입력/출력 계약, 결과 패키지 해석을 요약한다.

## 현재 로드맵 상태

현재 제품 단계는 아래와 같이 고정한다.

- 1단계: 분석 + 결과 패키지 (완료)
- 2단계: 조치 제안 + 비교 (부분 구현)
- 3단계: 실행 준비 (planned)
- 4단계: 실행/검증/승인/배포 (planned)
- 5단계: 운영/로그/감사 (planned)

현재 상태 구분은 아래와 같이 고정한다.

- current: 추천안, 분리 우선순위, 설계 선택지 비교, 실행 계획
- gap: 조치 제안, 변경 요약, Before 구조, After 구조
- planned: 실행/검증/승인/배포, 운영/로그/감사

## 목적

- 레거시 화면/코드/SQL 자산 분석
- `feature_slice` 단위 구조 분석
- 기능 성격 분류
  - `status_permissions`
  - `search_filters`
  - `save_validation`
- 레이어별 재구성 전략 제안
- 구조화된 초안 생성

내부 구현은 아래 구조로 분리되어 있다.

- `modules/rebuild_assistant/service.py`
  - 공개 모듈 어댑터
- `services/refactoring_support_engine/`
  - `InputAssembler`
  - `StructureAnalyzer`
  - `DiagnosisEngine`
  - `DecisionEngine`
  - `ImprovementPlanner`
  - `ResultPackager`
  - `NarrativeAugmentationService` (runner 전용 설명 레이어)

판단 템플릿 canonical source는
[`decision_catalog.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)이며,
[`judgment_templates.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 제공한다.

V0 범위는 전체 시스템 마이그레이션이 아니라 단일 기능 수준의 재구성 초안입니다.

## 시작 경로

- UI 안내: `/modules/rebuild_assistant`
- 실제 실행 시작점: `/projects/create`
- 기본 실행선: `project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant`
- 참고: `POST /modules/rebuild_assistant/runs` 는 더 이상 공개 실행 경로가 아니며 차단됩니다.

## 입력

공개 실행 요청은 raw asset이 아니라 `SafeAnalysisBundle`을 사용합니다.

- `goal: str`
  - 필수
  - `goal.strip()` 기준 최소 8자
- `safe_bundle`
  - 익명화된 canonical source
  - canonical 기준 structure
  - 원본/매핑 미포함
- `constraints: list[str]`

회계 MVP 확장에서는 추가로 `accounting_payload.json` 자산을 같은 업로드 세트에 포함할 수 있습니다.

- `transactions`
- `exchange_rates`
- `policies`
- `vouchers`
- `account_mappings`
- `strict`

위 JSON이 있으면 `structured_result.extensions.accounting`이 함께 생성됩니다.

raw `assets` / `temp_session_id` 입력은 공개 API에서 사용하지 않습니다.

## 업로드 보조 기능

프로젝트 UI는 기존 temp upload 저장소를 재사용하지만, 분석 실행 전에 반드시 익명화 파이프라인을 거칩니다.

- 원본은 secure storage로 분리 저장됩니다.
- canonical anonymized source가 생성됩니다.
- structure는 canonical source 기준으로만 추출됩니다.
- `rebuild_assistant`는 SafeAnalysisBundle만 소비합니다.

## 익명화 v0 노출 거버넌스

현재 익명화 노출 원칙은 아래처럼 고정한다.

- v0는 차단보다 관측과 검증 우선이다.
- 공개 사용자 표면은 `anonymization_summary`만 노출한다.
- 개발자 표면은 admin-only `debug_anonymization_report`만 사용한다.
- raw/canonical content, mapping, original, export payload는 사용자 API에 포함하지 않는다.
- preview는 canonical content를 직접 자른 값이 아니다.
  - preview 전용 stricter masking을 한 번 더 거친 제한된 파생값만 허용한다.
- validation 실패 시 run은 완료하지만 preview는 숨긴다.
  - dev debug 표면에는 summary, validation findings, whitelist 기반 `bundle_debug`만 남긴다.
- `bundle_debug`는 자유형 dict가 아니라 고정 메타데이터 상자다.
  - 허용 필드: `canonical_source_count`, `structure_count`, `total_replacements`, `masking_level`, `policy_version`, `omitted_preview_count`, `validation_passed`

## 분류 모드

현재 `service.py`는 입력 자산에서 기능 신호를 추출해 `primary_feature_mode`를 고릅니다.

- `status_permissions`
  - 역할/상태 기반 액션 노출
  - approve/reject/resubmit
  - 상태 전이 규칙
- `search_filters`
  - 검색 폼
  - 복수 필터 파라미터
  - 결과 테이블/리스트
  - 동적 쿼리 조합
  - paging/sort/filter state
- `save_validation`
  - 필수값 검증
  - 중복 체크
  - 저장 가드
  - 예외 기반 검증 흐름

결과 전략과 초안은 `primary_feature_mode`를 중심으로 작성되고, 보조 신호는 필요한 범위에서만 일부 반영됩니다.

## 출력 계약

`structured_result`는 기존 flat 결과와 함께 authoritative block을 병렬 유지한다.

현재 top narrative 경로는 아래처럼 고정한다.

- `build_result()`
  - deterministic fallback 결과만 생성
- `runner`
  - optional `NarrativeAugmentationService`
- `build_polish_bundle()`
  - 표현 polish만 수행

즉 AI는 설명 레이어에만 들어가고, canonical 구조/판단 block은 항상 deterministic source를 유지한다.

[authoritative block]
- `structure_snapshot`
  - `feature_slices`
  - `components`
  - `dependencies`
  - `hotspots`
  - `layer_map`
- `diagnosis_report`
  - `issues`
  - `coverage_summary`
  - `detector_stats`
- `decision_summary`
  - `decisions`
  - `recommended_strategy`
  - `priority_queue`
- `improvement_plan_bundle`
  - `design_options`
  - `recommended_option`
  - `execution_stages`
  - `risk_checkpoints`
- `appendix`
  - `evidence_index`

[분석 결과]
- `report_purpose: str`
- `report_scope: list[str]`
- `report_questions: list[str]`
- `one_line_conclusion: str`
- `analysis_summary: list[str]`
- `rebuild_strategy: list[str]`
- `layer_reconstruction`
  - `database: list[str]`
  - `backend: list[str]`
  - `frontend: list[str]`
- `recomposition_draft`
  - `database: list[str]`
  - `backend: list[str]`
  - `frontend: list[str]`
- `risks: list[str]`
- `confidence: float`
- `missing_context: list[str]`

[결정 지원]
- `decision_items: list[DecisionItem]`
- `retained_contracts: list[RetainedContract]`
- `priority_split_items: list[PrioritySplitItem]`
- `design_options: list[DesignOption]`
- `recommended_option: RecommendedOption | None`
- `execution_plan: list[ExecutionPlanWeek]`
- `recommended_directions: list[str]`

`decision_summary.decisions[*]`는 아래 설명 필드를 함께 가진다.

- `detector_id`
- `decision_type`
- `priority_score`
- `score_breakdown`
  - `severity_component`
  - `blast_radius_component`
  - `effort_component`
  - `confidence_bonus`
  - `detector_weight`
  - `hotspot_bonus`
  - `multi_slice_bonus`
  - `redesign_bonus`
  - `final_score`
- `explainability`
  - `decision_rule`
  - `score_formula`
  - `score_summary`
  - `evidence_count`
  - `affected_slice_count`

`execution_plan`은 자동 실행이 아니라 `실행 준비 계획` 또는 `실행 준비 초안`이다.

`run_finished` payload에는 아래 메타도 함께 포함된다.

- `primary_feature_mode`
- `secondary_feature_mode`
- `scope_limited`
- `needs_more_input`
- `authoritative_payload`
  - `structure_snapshot`
  - `diagnosis_report`
  - `decision_summary`
  - `improvement_plan_bundle`
  - `appendix`
- `polish_bundle`
  - `structured_result` 원문을 보존한 표현 전용 후처리 번들
  - `polished_sections`
  - `preserved_facts`
  - `warnings`
- `structured_result.extensions.accounting`
  - `input_validation`
  - `calculation_status`
  - `accounting_analysis`
  - `fx_calculation`
  - `voucher_review`
  - `summary_sentence`
- `structured_result.extensions.narrative`
  - `source`
  - `fields_rewritten`
  - `model`
  - `prompt_version`
  - `validation_passed`
  - `failure_reason`
  - `axis`

`report_purpose`는 문서의 목적을 설명하고, `summary_sentence`는 실행 결과를 설명한다. 두 필드는 같은 역할로 재사용하지 않는다.

## 진행 단계

내부 raw todo는 5단계입니다.

- `B1` 입력 정규화
- `B2` 구조 분석
- `B3` 진단 및 판단
- `B4` 개선안 생성
- `B5` 결과 패키징

사용자 콘솔의 3단계 진행률 매핑은 아래와 같습니다.

- `준비`: `B1`, `B2`
- `처리`: `B3`, `B4`
- `완료`: `B5`

## 테스트

회귀 테스트는 아래 파일에 포함되어 있습니다.

- [mellow_link/tests/test_module_registry_and_runs.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_module_registry_and_runs.py)

현재 테스트는 아래를 검증합니다.

- 모듈 등록 및 run metadata
- raw 공개 route 차단
- safe bundle 기반 run 생성
- `structured_result` shape
- feature mode 분류 회귀
- `status_permissions` / `search_filters` / `save_validation` 샘플의 결론 문구
- todo 매핑과 runner payload

문서 기준 검증과 고정 샘플 회귀는 아래를 추가 기준으로 사용한다.

- [REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md)
- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
