# Refactoring Support Engine QA Checklist

기준일: 2026-04-03  
상태: Contract  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)
질문 샘플 팩: [`REFACTORING_SUPPORT_ENGINE_QA_QUESTION_PACK.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_QA_QUESTION_PACK.md)

## 목적

`refactoring_support_engine` 변경이 문서 기준과 계속 정합한지 확인하는 검증 루프다.  
이 체크리스트는 말로만 확인하지 않고, 가능한 항목은 반드시 테스트로 고정한다.

## 자동 검증 체크리스트

1. 결과 payload가 기준 문서와 일치하는가
- `structure_snapshot`
- `diagnosis_report`
- `decision_summary`
- `improvement_plan_bundle`
- `appendix`
- 관련 테스트:
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)

2. decision이 `detector_id` 기준으로 분기되는가
- `category`는 UI/요약용 분류이고, 엔진 분기는 항상 `detector_id`를 본다.
- 관련 테스트:
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)

3. judgment taxonomy가 additive split 규칙을 지키는가
- `primary_judgment`는 compatibility/template axis다.
- `template_judgment`는 legacy template axis를 명시적으로 드러낸다.
- `structural_judgment`는 `decision_summary`에서 파생된 engine-owned structural decision이다.
- `narrative_axis`는 설명 축이며 score나 decision linkage를 바꾸지 않는다.
- `feature_signal_mode`는 legacy feature signal family 보존 필드다.
- 관련 테스트:
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)
  - [test_refactoring_support_promoted_expansion_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_promoted_expansion_samples.py)

4. `score_breakdown`이 정책과 일치하는가
- `severity * severity_multiplier`
- `blast_radius * blast_radius_multiplier`
- `effort * effort_multiplier`
- `confidence_bonus`
- `detector_weight`
- `hotspot_bonus`
- `multi_slice_bonus`
- `redesign_bonus`
- `final_score`
- 관련 테스트:
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)
  - [test_scoring_policy.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_scoring_policy.py)
- 운영 규칙:
  - Phase 3 전에는 detector/scoring policy 값을 변경하지 않는다.
  - detector base severity, default effort, detector weight, multiplier, bonus 값 조정은 금지다.

5. explainability가 score와 동일한 판단을 설명하는가
- `decision_rule`
- `score_formula`
- `score_summary`
- `evidence_count`
- `affected_slice_count`
- explainability는 새 판단 로직이 아니라 기존 `detector_id`와 `score_breakdown`의 설명 레이어여야 한다.
- 관련 테스트:
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)

6. slice 추출 규칙 위반이 없는가
- 우선순위: `API endpoint > UI action > business use case > data flow glue`
- 서로 다른 endpoint/action은 분리된다.
- 파일 단위/폴더 단위 grouping을 하지 않는다.
- 관련 테스트:
  - [test_feature_slice_extractor.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_feature_slice_extractor.py)
  - [test_structure_analyzer.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_structure_analyzer.py)
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)

7. seed structure 입력이 전달되는가
- `InputAssembler.seed_structures`
- `StructureAnalyzer.seed_structures`
- 관련 테스트:
  - [test_structure_analyzer.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_structure_analyzer.py)

8. canonical catalog 경로가 유지되는가
- 판단 템플릿 canonical source는
  [decision_catalog.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)
- [judgment_templates.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 유지한다.
- 관련 테스트:
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)

9. 고정 샘플 회귀가 유지되는가
- 기준 샘플은 [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)와 동일해야 한다.
- `primary_judgment`, `execution_plan`, `design_options`, `recommended_option`은 stable hash 기준으로도 drift가 없어야 한다.
- detector/scoring policy가 freeze 상태이므로 golden sample priority drift는 즉시 회귀로 간주한다.
- 관련 테스트:
  - [test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)

10. planner가 decision anchor를 필수로 사용하는가
- planner는 `DecisionArtifacts` 없이 실행되면 실패해야 한다.
- planner는 `primary_judgment`가 바뀌면 `design_options` 또는 `execution_plan`도 함께 바뀌어야 한다.
- 관련 테스트:
  - [test_planner_dependency_direction.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_planner_dependency_direction.py)

11. AI narrative layer가 canonical block을 바꾸지 않는가
- AI는 `report_purpose`, `primary_judgment_reason`, `one_line_conclusion`, `executive_summary_v2`만 바꿀 수 있다.
- AI on/off와 관계없이 `extensions.narrative.axis == result.narrative_axis`를 유지해야 한다.
- `structure_snapshot`, `diagnosis_report`, `decision_summary`, `improvement_plan_bundle`, `appendix`는 AI on/off와 무관하게 유지돼야 한다.
- 관련 테스트:
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)

12. AI validator 실패 시 fallback이 유지되는가
- 허용 필드 외 key
- 빈 값
- 새 숫자/고유 토큰
- 점수 불일치
- 위 경우 run 전체는 실패시키지 않고 `extensions.narrative.source=deterministic_fallback`으로 남겨야 한다.
- 관련 테스트:
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)

13. audience 변경이 canonical fact를 바꾸지 않는가
- `developer`, `manager`, `client`는 wording만 달라질 수 있다.
- 아래 값은 audience 변경으로 달라지면 안 된다.
  - `recommended_strategy`
  - `decision_type`
  - `priority_score`
  - `score_breakdown`
  - `execution stage linkage`
  - citations
- 관련 테스트:
  - [test_phase3_explanation_and_qa.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_phase3_explanation_and_qa.py)

14. explanation endpoint가 additive이고 delivery_mode를 강제하지 않는가
- `GET /projects/{id}/result` response shape는 그대로 유지한다.
- `GET /projects/{id}/result/explanation`은 audience 기반 읽기 전용 view만 추가한다.
- `taxonomy_view.core_judgment`는 `structural_judgment`와 `decision_summary`만 사용한다.
- `taxonomy_view.explanation_context`는 `narrative_axis`만 노출한다.
- `primary_judgment`, `template_judgment`, `feature_signal_mode`는 explanation surface에서 직접 노출하지 않는다.
- 첫 Phase 3 구현에서는 `delivery_mode_applied=false`를 유지한다.
- 관련 테스트:
  - [test_phase3_explanation_and_qa.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_phase3_explanation_and_qa.py)

15. result Q&A가 grounded, stateless, read-only인가
- intent는 `strategy`, `priority`, `evidence`, `execution`, `risk`, `scope`만 지원한다.
- 답변은 항상 citation과 referenced section을 가진다.
- grounding 부족 시 `insufficient_grounding=true`로 응답한다.
- 같은 질문 + 같은 결과에서는 deterministic draft가 동일해야 한다.
- 관련 테스트:
  - [test_phase3_explanation_and_qa.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_phase3_explanation_and_qa.py)

16. migration contamination guard 기준을 위반하지 않는가
- 판단 위계는 `asset-derived > detector-derived > decision linkage > goal wording` 순서를 지켜야 한다.
- `migration_consideration`인데 아래가 모두 비어 있으면 contamination 후보로 본다.
  - `issue_ids`
  - `evidence_ids`
- goal wording만으로 migration signal이 생성되지 않았는지 확인한다.
- business asset에 migration 관련 근거가 실제로 있는지 확인한다.
- `asset-derived` 판단과 `goal-derived` 판단이 충돌하지 않는지 확인한다.
- contamination 용어는 아래를 사용한다.
  - `wrapper wording contamination`
  - `synthetic migration trigger`
  - `asset-absent decision`
  - `domain-anchor spillover`
- 기준 문서:
  - [REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md)

## 수동 확인 체크리스트

1. supporting rationale 문장 강도가 과하게 확정형으로 치우치지 않았는가
2. explainability 문장이 정책식을 왜곡하지 않는가
3. top decision이 evidence 없이 보이지 않는가
4. golden sample 결과를 읽었을 때 `왜 이 판단인지`가 score와 함께 설명되는가
5. AI narrative가 canonical fact를 덮어쓰지 않는가
6. audience를 바꿔도 사실 자체가 달라지지 않는가
7. Q&A 응답이 새 판단 없이 기존 evidence와 decision만 설명하는가
8. migration 판단이 asset 근거 없이 goal wording만으로 만들어지지 않았는가
9. `synthetic migration trigger`가 `structural_judgment`를 오염시키지 않았는가

## 권장 실행 명령

```powershell
pytest -q mellow_link/tests/test_refactoring_support_doc_contract.py
pytest -q mellow_link/tests/test_refactoring_support_golden_samples.py
pytest -q mellow_link/tests/test_feature_slice_extractor.py mellow_link/tests/test_structure_analyzer.py mellow_link/tests/test_diagnosis_engine.py mellow_link/tests/test_decision_engine.py mellow_link/tests/test_scoring_policy.py mellow_link/tests/test_rebuild_assistant_integration.py
pytest -q mellow_link/tests/test_phase3_explanation_and_qa.py
```
