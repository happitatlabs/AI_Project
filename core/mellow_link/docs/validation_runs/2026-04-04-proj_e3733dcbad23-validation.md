# Real Project Validation Record

기준 문서: refactoring_support_engine.md  
project_id: proj_e3733dcbad23

## 기본 정보
- project_name: crud_sample
- client_name: si company
- review_date: 2026-04-04
- reviewer: Codex initial review
- project_type: refactor-centered

## Core Judgment
- structural_judgment: migration_consideration
- structural_judgment_source: explanation.taxonomy_view
- recommended_strategy: 마이그레이션 고려
- top_decision_type: migration_consideration
- top_priority_score: 7
- narrative_axis: query_filter
- narrative_axis_source: explanation.taxonomy_view

## Top Evidence Snapshot
- top_issue_summary: -
- top_issue_detectors:
-
- score_breakdown:
  - severity_component: 0
  - blast_radius_component: 0
  - effort_component: 0
  - confidence_bonus: 0
  - detector_weight: 0
  - hotspot_bonus: 0
  - multi_slice_bonus: 0
  - redesign_bonus: 0
  - final_score: 7

## Execution Snapshot
- top_execution_stage: 조회 조건, 필터 조합, 정렬 기준을 구조화합니다.
- execution_stage_count: 4
- recommended_option: 옵션 A. 조회 모델 중심 모듈형 구조

## Decision Summary Snapshot
- DEC-CAF7FEF58C | type=migration_consideration | priority=7 | rationale=스택 또는 전환 요구가 명시되어 있어 후속 마이그레이션 필요성을 함께 검토하는 편이 적절합니다.

## Reviewer Verdict
- reviewer_verdict: invalid
- taxonomy_confusion: major
- correction_required: yes

## Validation Checklist
### 1. 구조 판단 타당성
- [ ] structural_judgment가 실제 프로젝트 구조 문제와 일치한다.
- [ ] recommended_strategy가 실무적으로 수용 가능하다.
- [ ] top decision 1~3개가 실제 개선 우선순위와 크게 어긋나지 않는다.

### 2. 근거 연결 타당성
- [ ] decision -> issue -> evidence -> score_breakdown 연결이 납득 가능하다.
- [ ] score_breakdown.final_score가 과도하거나 과소하지 않다.
- [x] explainability가 score와 같은 판단을 설명한다.

### 3. 실행 가능성
- [x] top execution_stage가 실제 착수 가능하다.
- [x] 첫 단계 task가 모호하지 않다.
- [x] risk / verification checkpoint 누락이 없다.

### 4. taxonomy 분리 타당성
- [x] narrative_axis가 설명 보조로만 동작한다.
- [ ] narrative_axis가 구조 판단을 오염시키지 않는다.
- [ ] primary_judgment 없이도 reviewer가 결과를 이해할 수 있다.

### 5. explanation / Q&A 품질
- [x] audience가 달라도 fact / score / citation이 바뀌지 않는다.
- [ ] Q&A가 grounding 부족 시 억지로 답하지 않는다.
- [x] explanation surface가 structural_judgment를 중심으로 보여준다.

## Q&A Smoke Summary
- question: 왜 이게 권장 전략이야?
  - insufficient_grounding: False
  - referenced_sections: decision_summary, diagnosis_report
  - citation_count: 1
- question: 왜 이게 우선순위가 높아?
  - insufficient_grounding: False
  - referenced_sections: decision_summary
  - citation_count: 1
- question: 첫 단계에서 정확히 뭘 해야 해?
  - insufficient_grounding: False
  - referenced_sections: improvement_plan_bundle
  - citation_count: 2

## Notes
- confirmed_observation:
  - 이 프로젝트는 `query_filter` 중심 CRUD 샘플 자산인데, core judgment는 `migration_consideration`으로 내려와 설명 축과 판단 축이 크게 어긋난다.
  - `narrative_axis=query_filter`, 추천안, 실행 단계, grounded business rule은 모두 조회/필터 분리 방향을 가리키지만 `structural_judgment`만 migration으로 올라와 reviewer 관점에서 결과 해석이 충돌한다.
  - top decision은 `issue_ids=[]`, `evidence_count=0` 상태의 synthetic migration decision이다.
  - 업로드된 8개 자산 중 실제 업무 자산은 `crud_controller.py`, `crud_page.html`, `crud_repository.sql`, `schema.sql`, `usecase.md` 5개이고, 나머지 3개는 샘플 운영 메타데이터(`expected_assertions.yaml`, `input_manifest.json`, `scenario.md`)다.
  - 8개 자산 본문에서 `migration`, `마이그레이션`, `전환`, `rewrite`, `react`, `spring`, `microservice`, `order_closure`, `주문 마감` 신호는 확인되지 않았다.
  - 실제 업무 자산은 `reports` CRUD + 단일 검색 폼 + 단순 `ORDER BY created_at DESC` 구조로, `query_filter` narrative 또는 `observation_only/refactor` 경계 해석은 가능하지만 `migration_consideration`을 정당화하는 구조 근거는 없다.
  - 운영 메타데이터 자산에는 `query_filter`, `refactor`, `decision_count=0` 같은 기대 anchor가 포함돼 있어 이 프로젝트를 query/filter 저강도 샘플로 읽는 편이 자연스럽다.
- root_cause_candidate:
  - `mellow_link/modules/rebuild_assistant/api.py`의 project-wrapped 기본 goal 문구에 포함된 `전환 초안`이 `wrapper wording contamination`을 유발했을 가능성이 높다.
  - `DecisionEngine._has_migration_signal()`가 goal/constraint wording만으로 `synthetic migration trigger`를 만들었을 가능성이 높다.
  - 이번 프로젝트의 top migration decision은 `asset-absent decision` 사례로 본다.
  - `주문 마감`/`order_closure` 표현은 `domain-anchor spillover` 후보로 본다.
- follow_up_check:
  - 실제 migration 요구를 명시하지 않은 일반 프로젝트에서는 wrapped goal만으로 `migration_consideration`이 생성되지 않는지 비교 검증이 필요하다.
  - real-project validation에서는 `expected_assertions.yaml`, `input_manifest.json`, `scenario.md` 같은 non-business asset을 제외하는 절차를 별도 점검해야 한다.
  - `주문 마감`/`order_closure` 표현이 실제 업로드 자산 없이 concept/domain anchor heuristic에서 섞였는지 추가 추적이 필요하다.
- enforcement_record:
  - synthetic_signal_detected: yes
  - DecisionEngine 1차 가드 확인: not_applied
  - ResultPackager 2차 검증 확인: not_applied
  - Validation 기록 완료 여부: yes
- product_surface_change_needed:
  - yes; validation UI/record에는 `synthetic migration signal` 여부와 `evidence_count=0` 상태를 더 강하게 드러내는 경고가 필요하다.
- core_engine_change_needed: no
