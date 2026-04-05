# Refactoring Support Engine MVP 보강안

**Summary**
- MVP 분석 단위는 `feature_slice`로 고정한다.
- 공개 실행선은 유지한다: `project -> anonymization -> SafeAnalysisBundle -> rebuild_assistant -> result package`.
- 현재의 거대 단일 조립기인 [service.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/service.py)는 얇은 어댑터로 축소하고, 실제 엔진은 `services/refactoring_support_engine`로 분리한다.
- 결과는 `structure_snapshot -> diagnosis_report -> decision_summary -> improvement_plan_bundle -> appendix`의 authoritative block을 기준으로 만들고, 기존 UI는 이 block에서 flat field를 파생한다.
- 현재 제품 상태는 `deterministic engine core + optional AI narrative layer`다.
- AI narrative layer는 runner에서만 동작하고, `build_result()` 직접 호출 경로는 항상 deterministic fallback 결과를 유지한다.
- Phase 3 첫 구현은 `audience-first explanation + read-only result Q&A`까지 포함한다.
- Phase 3 첫 구현에서도 `delivery_mode`는 설명 API에 적용하지 않고 2차 범위로 미룬다.
- audience가 `developer | manager | client`로 바뀌어도 canonical fact, score, citation, decision linkage는 바뀌지 않는다.
- 현재 엔진 소유권은 `DecisionEngine + JudgmentSynthesizer`, `ImprovementPlanner + PlanningSynthesizer` 기준으로 정리한다.
- `service.py`는 공개 입력/실행 진입점, polish, extension/accounting bridge, sanitize 중심의 compatibility adapter로 유지한다.
- `detector policy`와 `scoring policy`는 Phase 3 시작 전까지 freeze 상태로 유지한다.
- Phase 3 전에는 `DEFAULT_DETECTOR_POLICIES`, `DEFAULT_SCORING_POLICY`, detector weight, score formula, bonus 규칙을 변경하지 않는다.
- taxonomy는 additive split 상태로 유지한다.
  - `primary_judgment`: compatibility용 template axis
  - `template_judgment`: legacy consulting/template axis의 명시 필드
  - `structural_judgment`: engine-owned structural decision
  - `narrative_axis`: user-facing explanation axis
  - `feature_signal_mode`: legacy feature signal family
- 자동화, 코드 생성, 마이그레이션 스크립트는 MVP 제외다. `migration_consideration`은 판단만 제공한다.

**Current vs Target 구조 비교**
| 현재 | 타깃 MVP | 처리 방침 |
|---|---|---|
| `prepare_safe_bundle_input()`가 입력 정규화와 자산 분류를 함께 수행 | `InputAssembler`로 분리 | 재사용 후 이동 |
| `analyze_assets`, `extract_rules`, `build_grounded_business_rules`가 혼재 | `StructureAnalyzer` + `DiagnosisEngine` | 분해 |
| `judgment_templates.py` + `select_primary_judgment()`가 판단 담당 | `DecisionEngine` + `decision_catalog` + `JudgmentSynthesizer` | 엔진 소유 |
| `build_design_options`, `build_execution_plan`이 결과 조립과 섞여 있음 | `ImprovementPlanner` + `PlanningSynthesizer` | 엔진 소유 |
| `build_result()`가 전 단계를 일괄 조립 | `ResultPackager`가 authoritative payload 생성 | 분해 |
| `postprocess` polish layer | 동일 유지 | 재사용 |
| `/projects/{id}/result` 결과 패키지 | 동일 유지 | 호환 유지 |

- 현재 코드 매핑은 아래로 고정한다.
- `prepare_safe_bundle_input` -> `InputAssembler`
- `extract_feature_signals`, seed structure 활용 -> `StructureAnalyzer`
- `analyze_assets`, `extract_rules`, grounded rule 생성 -> `DiagnosisEngine`
- `select_primary_judgment`, `build_decision_items` -> `DecisionEngine`
- `build_design_options`, `pick_recommended_option`, `build_execution_plan` -> `ImprovementPlanner`
- `build_result` -> `ResultPackager`
- `build_polish_bundle` -> 기존 `postprocess` 유지

**Module Architecture**
| Module | Responsibility | Input | Output |
|---|---|---|---|
| `InputAssembler` | safe bundle, goal, constraint를 엔진용 정규 입력으로 변환 | `SafeAnalysisBundle`, `goal`, `constraints` | `RefactoringAnalysisInput` |
| `StructureAnalyzer` | 컴포넌트/의존성/레이어/데이터 흐름/슬라이스 추출 | `RefactoringAnalysisInput` | `StructureAnalysisResult` |
| `DiagnosisEngine` | detector 실행, issue 생성, evidence 연결 | `StructureAnalysisResult` | `DiagnosisReport` |
| `DecisionEngine` | `refactor / redesign / migration_consideration` 판단, 우선순위 계산, primary judgment/pattern candidate/decision item 생성 | `StructureAnalysisResult`, `DiagnosisReport` | `DecisionSummary` |
| `ImprovementPlanner` | 설계 옵션, 추천안, 실행 단계 생성 | `StructureAnalysisResult`, `DiagnosisReport`, `DecisionSummary` | `ImprovementPlanBundle` |
| `ResultPackager` | authoritative payload와 기존 UI 호환 flat field 생성 | 전 단계 결과 | `StructuredRefactoringResult` |

- `FeatureSliceExtractor`는 `StructureAnalyzer` 내부 서브컴포넌트로 둔다.
- `decision_catalog`는 기존 [judgment_templates.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py) 규칙을 초기 seed로 사용하되, 위치는 새 엔진 패키지로 옮기고 기존 파일은 compatibility re-export만 남긴다.
- `JudgmentSynthesizer`는 template scoring, pattern candidate, primary judgment, decision item의 deterministic synthesis를 소유한다.
- `PlanningSynthesizer`는 decision anchor를 기준으로 design option, recommended option, verification checkpoint, execution plan의 deterministic synthesis를 소유한다.
- planner는 `DecisionArtifacts` 없이 실행하지 않는다.
- detector는 slice-local 실행 후 cross-slice aggregate를 한 번 더 수행한다.
- 모든 ID는 deterministic hash로 만든다. `slice_id`, `issue_id`, `evidence_id`, `decision_id`, `stage_id`는 입력 fingerprint가 같으면 항상 같아야 한다.

| Detector | Deterministic Rule | Evidence |
|---|---|---|
| `mixed_responsibility` | 한 컴포넌트에 책임 family 2개 이상 존재. family는 `validation`, `business`, `persistence`, `ui_orchestration`, `async_orchestration`로 고정 | excerpt, function/class locator |
| `ui_data_access_coupling` | UI layer가 SQL keyword 또는 repository/db dependency를 직접 가짐 | `UI -> DB/Repo` 경로, excerpt |
| `rule_scatter` | 동일 조건 fingerprint가 2개 이상 위치에서 반복 | 조건 excerpt, 위치 목록 |
| `duplicate_logic_candidate` | normalized token similarity `>= 0.85`, 유효 토큰 `>= 8` | 유사 코드 블록 2개 이상 |
| `boundary_mismatch` | 금지된 layer edge 또는 하위 layer의 business keyword 보유 | dependency path, layer info |
| `state_transition_leak` | 동일 상태 변경 fingerprint가 다수 위치에 존재 | 상태 변경 excerpt |
| `validation_guard_leak` | 동일 validation fingerprint가 여러 layer에 존재 | validation 조건 목록 |
| `query_filter_leak` | 동일 where/predicate fingerprint가 여러 query에 반복 | SQL excerpt |

- fingerprint 규칙은 공통으로 고정한다.
- 소문자화, 공백 정규화, 숫자/문자열 리터럴 placeholder 치환, 연산자 spacing 통일 후 비교한다.
- `rule_scatter`, `validation_guard_leak`, `state_transition_leak`, `query_filter_leak`는 같은 fingerprint map 유틸을 공유한다.
- 점수 규칙은 아래로 고정한다.
- `severity`: detector base 3, cross-layer면 `+1`, write path 또는 승인/상태 변경이면 `+1`, 최대 5
- `blast_radius`: 영향받는 `components + layers + slices`를 bucket 1~5로 환산
- `effort`: helper 추출 1, service split 3, boundary redesign 5
- `priority_score = severity*2 + blast_radius - effort + confidence_bonus + detector_weight + hotspot_bonus + multi_slice_bonus + redesign_bonus`
- 위 detector/scoring 정책값은 Phase 3 전까지 변경 금지다.

**Data Schema**
```json
{
  "structure_snapshot": {},
  "diagnosis_report": {},
  "decision_summary": {},
  "improvement_plan_bundle": {},
  "appendix": { "evidence_index": [] }
}
```

```python
FunctionSlice:
  slice_id: str
  name: str
  entry_points: list[str]        # "api:POST /orders", "ui:OrderPage#submit"
  related_components: list[str]
  related_tables: list[str]
  business_rules: list[str]
  dependencies: list[str]

StructuralIssue:
  issue_id: str
  detector_id: str                     # e.g. mixed_responsibility
  category: str                        # policy-defined category, e.g. structure/boundary/duplication
  severity: int
  blast_radius: int
  effort: int
  summary: str
  affected_component_ids: list[str]
  affected_slice_ids: list[str]
  evidence_ids: list[str]
  confidence: float

DecisionRecord:
  decision_id: str
  issue_ids: list[str]
  decision_type: Literal["refactor", "redesign", "migration_consideration"]
  target_component_ids: list[str]
  priority_score: int
  score_breakdown:
    severity_component: int
    blast_radius_component: int
    effort_component: int
    confidence_bonus: int
    detector_weight: int
    hotspot_bonus: int
    multi_slice_bonus: int
    redesign_bonus: int
    final_score: int
  explainability:
    decision_rule: str
    score_formula: str
    score_summary: str
    evidence_count: int
    affected_slice_count: int
  rationale: str
  confidence: float
  evidence_ids: list[str]

Decision taxonomy:
  primary_judgment: str        # compatibility/template axis
  template_judgment: str       # explicit legacy template axis
  structural_judgment: str     # engine-owned structural decision
  narrative_axis: str          # user-facing explanation axis
  feature_signal_mode: str     # extracted legacy feature signal family

ExecutionStage:
  stage_id: str
  title: str
  tasks: list[str]
  decision_ids: list[str]
  verification_checkpoint_ids: list[str]
  risk_ids: list[str]
  depends_on: list[str]

EvidenceLink:
  evidence_id: str
  asset_id: str
  asset_name: str
  asset_type: str
  locator: str
  excerpt: str
  fingerprint: str
```

- `structure_snapshot`에는 `feature_slices`, `components`, `dependencies`, `hotspots`, `layer_map`를 반드시 둔다.
- `diagnosis_report`에는 `issues`, `coverage_summary`, `detector_stats`를 둔다.
- `decision_summary`에는 `decisions`, `recommended_strategy`, `priority_queue`를 둔다.
- `improvement_plan_bundle`에는 `design_options`, `recommended_option`, `execution_stages`, `risk_checkpoints`를 둔다.
- 규칙은 아래로 고정한다.
- `category`는 정책 기반 분류이며 UI/요약용이다.
- `detector_id`는 로직 분기 및 판단 기준으로 사용된다.
- 엔진 내부 분기는 항상 `detector_id` 기준으로 수행한다.
- `score_breakdown`은 정책 계산 결과를 그대로 노출한다.
- `explainability`는 새 판단을 추가하지 않고 `detector_id`, 정책식, 계산 결과를 설명하는 파생 레이어다.
- `primary_judgment`는 backward compatibility를 위해 유지되는 template axis다.
- `template_judgment`는 `primary_judgment`와 같은 legacy/template taxonomy를 명시적으로 드러낸다.
- `structural_judgment`는 `decision_summary`에서 파생된 engine-owned structural judgment다.
- `narrative_axis`는 설명/표현용 축이며 `priority_score`, `decision_type`, `recommended_strategy`를 바꾸지 않는다.
- `feature_signal_mode`는 legacy feature extraction 결과를 보존하는 필드이며, structural decision의 canonical source가 아니다.
- `query_filter`, `workflow`, `validation`, `access_control`, `state_transition`, `amount_threshold` 같은 값은 현재 `template_judgment`/`narrative_axis` 계층으로 해석한다.
- `extensions["narrative"]`는 설명 레이어 provenance만 저장한다.
  - `source`: `ai` 또는 `deterministic_fallback`
  - `fields_rewritten`
  - `model`
  - `prompt_version`
  - `validation_passed`
  - `failure_reason`
  - `axis`
- 모든 `decision`은 최소 1개의 `issue_id`를 가진다.
- 모든 `issue`는 최소 1개의 `evidence_id`를 가진다.
- 모든 `execution_stage`는 최소 1개의 `decision_id`를 가진다.
- summary text는 authoritative block에서만 파생하고 직접 수기 작성하지 않는다.
- 기존 `StructuredRebuildResult` flat field는 authoritative block에서 계산한 파생값만 저장한다.

**Migration Consideration Governance Rules**
- 기준 문서: [`REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md)
- 판단 위계는 아래로 고정한다.
  - `asset-derived > detector-derived > decision linkage > goal wording`
- `goal/constraint wording`은 보조 입력일 뿐이며, 단독으로 core judgment를 만들면 안 된다.
- `migration_consideration`은 아래 조건이 모두 어긋나면 contamination으로 본다.
  - business asset에 migration 근거 없음
  - `issue_ids == []`
  - `evidence_ids == []`
- Hard Guard Rule은 아래로 고정한다.
  - `decision_type == "migration_consideration"` 이고 `issue_ids == []` 이며 `evidence_ids == []` 이면 synthetic migration으로 간주한다.
  - 이 경우 `synthetic_signal_detected = true`로 기록하고 downgrade 규칙을 적용해야 한다.
  - `diagnosis_report.issues == 0`이면 `observation_only`
  - 그 외에는 `refactor`
- 강제 지점은 아래로 고정한다.
  - `DecisionEngine`: `migration_consideration` 생성 직후 1차 적용
  - `ResultPackager`: 최종 decision 확정 직전 2차 검증
  - `Validation Layer`: `synthetic_signal_detected` 필수 기록
- contamination 용어는 아래를 사용한다.
  - `wrapper wording contamination`
  - `synthetic migration trigger`
  - `asset-absent decision`
  - `domain-anchor spillover`
- real-project validation 문서는 아래 3구역으로 기록한다.
  - `confirmed observation`
  - `root cause candidate`
  - `follow-up check`

**Narrative Layer**
- canonical source는 항상 아래 5개 block이다.
  - `structure_snapshot`
  - `diagnosis_report`
  - `decision_summary`
  - `improvement_plan_bundle`
  - `appendix`
- Phase 1.8에서 AI가 수정 가능한 필드는 아래 4개로 고정한다.
  - `report_purpose`
  - `primary_judgment_reason`
  - `one_line_conclusion`
  - `executive_summary_v2`
- AI는 `판단`, `점수`, `evidence`, `priority`, `execution stage linkage`를 수정하지 않는다.
- AI validator는 허용 필드 외 key, 빈 값, 새 숫자/고유 토큰, 점수 불일치를 막고 실패 시 deterministic fallback으로 내려간다.

**Phase 3 Presentation Layer**
- Phase 3는 `deterministic engine core`를 유지한 채 설명/표현/상호작용 레이어만 확장한다.
- 첫 구현 범위는 아래로 고정한다.
  - `ExplanationPresenter`
  - audience preset: `developer | manager | client`
  - `ResultQuestionAnsweringService`
  - stateless, read-only Q&A
- 첫 구현에서는 `delivery_mode`를 endpoint에 적용하지 않는다.
- explanation view는 아래 우선순위를 따른다.
  - fact source: `authoritative_payload`
  - wording base: `polish_bundle.polished_sections[*].audience_variants`
  - top narrative override: 이미 materialized 된 top 4 fields만 허용
- audience가 바뀌어도 아래 값은 바뀌면 안 된다.
  - `recommended_strategy`
  - `decision_type`
  - `priority_score`
  - `score_breakdown`
  - `execution stage linkage`
  - citations
- taxonomy surface 정책은 아래로 고정한다.
  - Core Judgment Layer: `structural_judgment`, `decision_summary`
  - Explanation Layer: `narrative_axis`
  - Hidden / Compatibility Layer: `primary_judgment`, `template_judgment`, `feature_signal_mode`
- `/projects/{id}/result/explanation`은 additive `taxonomy_view`를 제공한다.
  - `core_judgment`
    - `structural_judgment`
    - `recommended_strategy`
    - `top_decision_type`
  - `evidence_view`
    - `top_priority_score`
    - `score_breakdown`
    - `explainability`
    - `citations`
  - `explanation_context`
    - `narrative_axis`
- 기본 UI/설명 surface에서는 `primary_judgment`, `template_judgment`, `feature_signal_mode`를 직접 노출하지 않는다.
- Human Review용 Diff Layer는 canonical payload가 아니라 additive `extensions["review_diff"]`로 생성한다.
  - 구성은 `Structural Diff`, `Evidence Diff`, `Decision Diff`로 고정한다.
  - validation run 문서는 `extensions["review_diff"]["markdown"]`를 소비하는 generated surface로 둔다.
- `/projects/{id}/result`는 full `review_diff`를 유지한다.
- `/projects/{id}/result/explanation`는 full diff 대신 compact `review_diff_preview`만 노출한다.
- Review Diff는 기본적으로 internal artifact다.
  - internal: full `review_diff`와 compact preview 허용
  - external: canonical judgment/evidence만 허용하고 Review Diff는 직접 노출하지 않는다
- explanation API는 `surface_mode=internal|external` additive rule을 따른다.
  - `surface_mode`는 current public selector다.
  - 내부 구현은 `surface_mode -> access_profile -> capability` policy로 분리한다.
  - 현재 mapping은 `internal -> internal_full`, `external -> external_basic`으로 고정한다.
  - capability 이름은 `can_view_*` / `can_export_*` 기준으로 고정한다.
    - 예: `can_view_review_diff`, `can_view_code_diff`, `can_view_block_reasons`, `can_view_governance_trace`, `can_view_detector_locator`, `can_export_review_artifacts`
  - `internal`: `review_diff_preview` 허용
  - `external`: `review_diff_preview` 숨김, canonical explanation만 노출
- export도 같은 `surface_mode` 규칙을 따른다.
  - `internal` export: 검토용 결과와 `review_diff` 포함
  - `external` export: explanation 중심, `review_diff`/blocked decision/governance trace 비포함
- `review_diff`는 internal-only `code_diff` evidence layer를 가질 수 있다.
  - 이 레이어는 실제 패치가 아니라 현재 구조와 권장 패턴의 차이를 검토하기 위한 현재 구조 vs 권장 구조 비교다
  - 최소 `observed / expected_pattern` snippet만 포함
  - external surface에서는 `code_diff`를 전달하지 않는다
  - execution patch와는 별도 레이어로 유지한다
- 결과 UI는 internal mode에서 `Primary / Blocked / Confidence` sticky summary를 먼저 보여주고, `Decision Result / Why this decision? / Structural Difference` 순서로 Review Diff를 렌더링한다.
- 기본 open 상태는 `Decision Result` 항상 열림, `Why this decision?` 기본 열림, `Evidence Detail`과 `현재 구조 vs 권장 구조 비교` 기본 접힘으로 고정한다.
- filtered artifact는 `absent`와 `hidden_by_policy`를 구분한다.
  - `absent`: 원래 데이터가 없음
  - `hidden_by_policy`: 데이터는 있었지만 surface policy로 숨김
  - 실제 external payload는 계속 제거 가능하지만, provenance/debug trace는 이 구분을 남겨야 한다.
- Q&A는 아래 intent만 지원한다.
  - `strategy`
  - `priority`
  - `evidence`
  - `execution`
  - `risk`
  - `scope`
- Q&A는 새 판단을 만들지 않는다. 기존 판단, 근거, 실행 단계를 설명만 한다.
- grounding이 부족하면 `insufficient_grounding=true`로 응답하고 억지로 답을 만들지 않는다.

**Execution Flow**
1. `[routers/projects.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/routers/projects.py)`와 anonymization 흐름은 그대로 유지한다.
2. `InputAssembler`가 `SafeAnalysisBundle`에서 asset inventory, source block, seed structure, missing context를 만든다.
3. `FeatureSliceExtractor`가 slice seed를 추출한다. 우선순위는 `API endpoint > UI action > business use case > data flow glue`로 고정한다.
4. slice seed 이름은 `api:METHOD /path`, `ui:Screen#action`, `usecase:verb_noun` 규칙으로 정규화한다.
5. slice 확장은 dependency graph BFS로 수행하되 `다른 endpoint`, `다른 사용자 액션`, `다른 데이터 변경 대상`, `다른 책임 family`, `sync/async 경계`를 만나면 중단한다.
6. 동일 endpoint 내부 분기 로직은 한 slice로 유지한다.
7. 같은 테이블을 쓴다는 이유만으로 merge하지 않는다. `data flow glue`는 1~3순위 seed를 보조 연결할 때만 사용한다.
8. 파일 단위, 폴더 단위, 서브시스템 단위 grouping은 금지한다.
9. `StructureAnalyzer`가 component/layer/dependency/data-flow/hotspot을 확정한다.
10. `DiagnosisEngine`가 8개 detector를 순서 고정으로 실행한다. 실행 순서는 표에 나온 순서를 그대로 사용한다.
11. `DecisionEngine`가 issue를 `refactor`, `redesign`, `migration_consideration`으로 분류한다. 기준은 데이터 계약 변경 필요성, 경계 재정의 필요성, 스택/전환 필요성이다.
12. `ImprovementPlanner`가 `DecisionArtifacts`를 anchor로 사용해 decision별 design option과 execution stage를 만든다.
13. `ResultPackager`가 authoritative payload를 만든 뒤 현재 결과 패키지용 flat field와 `polish_bundle` 입력을 파생한다.
14. `runner`는 `build_result()` 뒤에 optional `NarrativeAugmentationService`를 한 번 호출하고, 그 다음 `build_polish_bundle()`을 호출한다.
15. runner todo는 기존 `B1~B5`를 유지하되 의미만 `입력 정규화 -> 구조 분석 -> 진단/판단 -> 개선안 생성 -> 패키징`으로 바꾼다.

**Implementation Plan**
1. `services/refactoring_support_engine` 패키지를 만들고 `schemas.py`, `facade.py`, `input_assembler.py`를 먼저 도입한다.
2. `modules/rebuild_assistant/service.py`는 facade 호출 어댑터로 축소하고 기존 public schema, accounting extension, polish 호출만 유지한다.
3. `structure_analyzer.py`에 `ComponentCollector`, `DependencyResolver`, `FeatureSliceExtractor`, `HotspotScorer`를 구현한다.
4. feature slice 추출 회귀 테스트를 먼저 만든다. 기준 샘플은 endpoint 중심, UI action 중심, use case fallback, async split 케이스 4종으로 고정한다.
5. `diagnosis_engine.py`에 8개 detector와 공통 fingerprint/evidence 유틸을 구현한다.
6. `decision_engine.py`에 priority scoring, recommended strategy selection, engine 내부 `decision_catalog` 기반 판단 연결을 구현한다.
7. `improvement_planner.py`에 design options, recommended option, execution stages를 구현한다.
8. `result_packager.py`에서 authoritative payload를 만들고, 현재 `/projects/{id}/result`가 기대하는 flat field를 파생한다.
9. 기존 [runner.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/runner.py)와 `run_events` 계약은 유지한다. 이벤트 payload에 authoritative payload 전체를 넣고 기존 `structured_result` 키는 계속 유지한다.
10. 테스트는 엔진 단위와 통합 단위로 분리한다. 기존 `test_module_registry_and_runs.py` 호환성 테스트는 유지하고, 새 엔진 전용 테스트를 추가한다.

**Validation Loop**
- 문서 기준 검증은 [`REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_QA_CHECKLIST.md)로 관리한다.
- 고정 회귀 샘플은 [`REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)와 `test_refactoring_support_golden_samples.py`를 함께 기준으로 삼는다.
- 구조/정책 변경은 아래를 동시에 통과해야 한다.
  - authoritative payload shape 검증
  - detector_id 기준 decision 분기 검증
  - `template_judgment / structural_judgment / narrative_axis / feature_signal_mode` taxonomy 정합성 검증
  - score_breakdown / explainability 검증
  - feature_slice 규칙 검증
  - golden sample 회귀 검증
- 단, Phase 3 전에는 구조 변경만 허용하고 detector/scoring policy 값 변경은 허용하지 않는다.

**File Structure**
```text
mellow_link/
├─ services/
│  └─ refactoring_support_engine/
│     ├─ __init__.py
│     ├─ facade.py
│     ├─ schemas.py
│     ├─ input_assembler.py
│     ├─ structure_analyzer.py
│     ├─ diagnosis_engine.py
│     ├─ decision_engine.py
│     ├─ decision_catalog.py
│     ├─ improvement_planner.py
│     └─ result_packager.py
├─ modules/
│  └─ rebuild_assistant/
│     ├─ service.py
│     ├─ schemas.py
│     ├─ runner.py
│     ├─ judgment_templates.py   # compatibility re-export
│     └─ postprocess/
└─ tests/
   ├─ test_feature_slice_extractor.py
   ├─ test_structure_analyzer.py
   ├─ test_diagnosis_engine.py
   ├─ test_decision_engine.py
   ├─ test_improvement_planner.py
   └─ test_rebuild_assistant_integration.py
```

**Assumptions**
- 업로드 자산이 실제로 하나의 기능만 포함하면 결과 slice 수가 1개일 수 있다. 이 경우도 `project-wide`가 아니라 `single feature slice`로 취급한다.
- `migration_consideration`은 실행 자동화가 아니라 후속 단계 필요성 표시다.
- 기존 결과 UI는 authoritative payload를 직접 렌더하지 않고, 당분간 기존 flat field를 계속 소비한다.
