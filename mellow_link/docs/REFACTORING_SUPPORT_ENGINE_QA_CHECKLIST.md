# Refactoring Support Engine QA Checklist

기준일: 2026-04-03  
상태: Contract  
기준 문서: [`refactoring_support_engine.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

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

3. `score_breakdown`이 정책과 일치하는가
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

4. explainability가 score와 동일한 판단을 설명하는가
- `decision_rule`
- `score_formula`
- `score_summary`
- `evidence_count`
- `affected_slice_count`
- explainability는 새 판단 로직이 아니라 기존 `detector_id`와 `score_breakdown`의 설명 레이어여야 한다.
- 관련 테스트:
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)

5. slice 추출 규칙 위반이 없는가
- 우선순위: `API endpoint > UI action > business use case > data flow glue`
- 서로 다른 endpoint/action은 분리된다.
- 파일 단위/폴더 단위 grouping을 하지 않는다.
- 관련 테스트:
  - [test_feature_slice_extractor.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_feature_slice_extractor.py)
  - [test_structure_analyzer.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_structure_analyzer.py)
  - [test_refactoring_support_doc_contract.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_doc_contract.py)

6. seed structure 입력이 전달되는가
- `InputAssembler.seed_structures`
- `StructureAnalyzer.seed_structures`
- 관련 테스트:
  - [test_structure_analyzer.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_structure_analyzer.py)

7. canonical catalog 경로가 유지되는가
- 판단 템플릿 canonical source는
  [decision_catalog.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/refactoring_support_engine/decision_catalog.py)
- [judgment_templates.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/judgment_templates.py)는 compatibility re-export만 유지한다.
- 관련 테스트:
  - [test_decision_engine.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_decision_engine.py)

8. 고정 샘플 회귀가 유지되는가
- 기준 샘플은 [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)와 동일해야 한다.
- `primary_judgment`, `execution_plan`, `design_options`, `recommended_option`은 stable hash 기준으로도 drift가 없어야 한다.
- detector/scoring policy가 freeze 상태이므로 golden sample priority drift는 즉시 회귀로 간주한다.
- 관련 테스트:
  - [test_refactoring_support_golden_samples.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_refactoring_support_golden_samples.py)

9. planner가 decision anchor를 필수로 사용하는가
- planner는 `DecisionArtifacts` 없이 실행되면 실패해야 한다.
- planner는 `primary_judgment`가 바뀌면 `design_options` 또는 `execution_plan`도 함께 바뀌어야 한다.
- 관련 테스트:
  - [test_planner_dependency_direction.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_planner_dependency_direction.py)

10. AI narrative layer가 canonical block을 바꾸지 않는가
- AI는 `report_purpose`, `primary_judgment_reason`, `one_line_conclusion`, `executive_summary_v2`만 바꿀 수 있다.
- `structure_snapshot`, `diagnosis_report`, `decision_summary`, `improvement_plan_bundle`, `appendix`는 AI on/off와 무관하게 유지돼야 한다.
- 관련 테스트:
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)

11. AI validator 실패 시 fallback이 유지되는가
- 허용 필드 외 key
- 빈 값
- 새 숫자/고유 토큰
- 점수 불일치
- 위 경우 run 전체는 실패시키지 않고 `extensions.narrative.source=deterministic_fallback`으로 남겨야 한다.
- 관련 테스트:
  - [test_rebuild_assistant_integration.py](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/tests/test_rebuild_assistant_integration.py)

## 수동 확인 체크리스트

1. supporting rationale 문장 강도가 과하게 확정형으로 치우치지 않았는가
2. explainability 문장이 정책식을 왜곡하지 않는가
3. top decision이 evidence 없이 보이지 않는가
4. golden sample 결과를 읽었을 때 `왜 이 판단인지`가 score와 함께 설명되는가
5. AI narrative가 canonical fact를 덮어쓰지 않는가

## 권장 실행 명령

```powershell
pytest -q mellow_link/tests/test_refactoring_support_doc_contract.py
pytest -q mellow_link/tests/test_refactoring_support_golden_samples.py
pytest -q mellow_link/tests/test_feature_slice_extractor.py mellow_link/tests/test_structure_analyzer.py mellow_link/tests/test_diagnosis_engine.py mellow_link/tests/test_decision_engine.py mellow_link/tests/test_scoring_policy.py mellow_link/tests/test_rebuild_assistant_integration.py
```
