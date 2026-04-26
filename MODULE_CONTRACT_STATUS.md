# MODULE_CONTRACT_STATUS

## 1. 전체 요약

- 분석 기준 시점: 2026-04-26
- 문서 갱신 기준: 4단계 실행 로드맵 후반 고도화 + external surface wording style branching 반영
- 백업 상태: 전체 작업공간 백업 확보 완료
- 백업 파일: `C:\Users\Hyein\ClaudeAI\backups\AI_Project_20260426_145859.zip`
- 현재 전체 흐름의 주 경로는 다음과 같이 정리된다.

```text
PPT/PPTX 업로드
-> /chat/upload-temp
-> extract_text_from_file()
-> extract_presentation_sml()
-> staged upload / project asset promotion
-> AnonymizationService.run_anonymization_pipeline()
-> AnalysisContextBuilder.build()
-> SourceQuestionGuardService.evaluate()
-> InputAssembler.prepare_analysis_context_input()
-> RefactoringSupportEngineFacade.build_result()
   -> StructureAnalyzer.analyze()
   -> DiagnosisEngine.run()
   -> DecisionEngine.run()
   -> ValidationEngine.validate_decision()
   -> ImprovementPlanner.run()
   -> ResultPackager.package()
-> runner event emit / result surface
```

- 현재 구조는 `safe bundle -> analysis context -> prepared input -> engine facade -> packaged result`의 계층은 비교적 명확하다.
- 3단계 판단 계약은 이제 `GuardedDecisionInput`, `JudgmentCriteria`, `DecisionBasis`, `DecisionConflict`, `DecisionValidationResult`를 중심으로 한 typed 내부 계약을 갖는다.
- `DecisionBasis`는 `0.0 ~ 1.0` 스케일의 정량 점수와 `recommendation_strength(assertive / conditional / review_required / blocked)`를 가진다.
- `ImprovementPlanner`는 위 판단 강도와 validation/conflict/missing evidence를 읽어 실행안 강도를 조절하고, option strategy와 lightweight schedule hint까지 생성한다.
- `ResultPackager`와 planner/governance surface는 `blocked / review_required / conditional / assertive` 상태를 서로 어긋나지 않게 유지하도록 최소 일관성 보정을 가진다.
- 결과 표현 레이어는 이제 입력을 `document / code / mixed`로 분류하고, 외부용 wording을 `document_style / technical_style / mixed_style`로 나누어 설명한다.
- 이 표현 분기는 `ExplanationPresenter`와 `consulting_deck`에서만 수행되며, 판단 엔진과 canonical payload 계약은 바꾸지 않는다.
- `runner.py`의 `authoritative_payload`는 다시 stable public key set으로 정리되었고, `judgment_canvas`, `validation_result`, `stage_control`은 `structured_result` 본문과 다른 surface에 남는다.
- 반면 `PreparedRebuildInput` 하나에 다수의 중간 산출물을 누적해서 싣는 방식, `legacy_service`의 비공개 메서드 의존, 라우터/러너/서비스에 오케스트레이션이 분산된 부분은 여전히 계약 파손 위험이 높다.

## 1.1 품질 원칙

- 현재 시스템의 골든샘플 기반 회귀는 exact output snapshot이 아니라, 판단 구조와 도메인 적합성을 검증하는 방식으로 설계되어 있다.
- 목적은 표현 변화에는 유연하게 대응하면서도, 도메인 오염과 근거 부족, 과도한 확신, 실행 불가능한 결과를 안정적으로 막는 것이다.
- 좋은 결과의 최소 조건은 아래 다섯 가지다.
  - 도메인 적합: 입력 샘플군의 expected domain profile과 결과의 핵심 도메인 축이 일치해야 한다.
  - 근거 기반: source, SML, safe source, question guard, evidence ref에 연결되지 않은 강한 결론은 허용하지 않는다.
  - 오염 없음: source에 없는 `product`, `저장 전 검증`, `sql 파라미터`, `api validation` 같은 외부 도메인 문구는 실패로 본다.
  - 실행 가능: 판단 결과가 planner 단계, verification checkpoint, priority, phase와 연결되어 실제 조치 가능해야 한다.
  - 과도한 확신 없음: evidence 부족, conflict, blocked/review_required 상태에서는 단정형 결론과 공격적인 실행 권고를 피해야 한다.
- 대표 회귀 기준은 `core/mellow_link/tests/test_ppt_batch_regression.py`에 있고, 최신 batch 결과는 `core/mellow_link/tests/output/ppt_regression_report.json`으로 확인한다.

## 2. 주요 모듈 목록

| 구분 | 모듈 | 핵심 파일 / 함수·클래스 |
| --- | --- | --- |
| 앱 진입 | FastAPI 앱 등록 / 라우터 결합 | `core/mellow_link/main.py:651`, `:662`, `:666`, `:678`, `:831` |
| 업로드 진입 | 임시 업로드 수신, staged 저장 | `core/mellow_link/routers/chat.py:63` `upload_temp_document()` |
| 문서 추출 | 파일 형식별 텍스트/SML 추출 | `core/mellow_link/services/rag_service.py:91` `extract_text_from_file()` |
| PPT 정규화 | PPT/PPTX -> SML canonical text | `core/mellow_link/services/presentation_extraction.py:35` `extract_presentation_sml()` |
| 프로젝트 라우터 | safe bundle 생성, preview, create, rerun | `core/mellow_link/routers/projects.py:1008`, `:1072`, `:4459`, `:4556`, `:4859` |
| 익명화 파이프라인 | safe bundle / review report 생성 | `core/mellow_link/services/anonymization/service.py:15`, `:39` |
| 분석 컨텍스트 | safe bundle -> canonical analysis context | `core/mellow_link/services/refactoring_support_engine/analysis_context_builder.py:61`, `:64` |
| 질문 가드 | source 기반 질문 후보 추출 / 차단 | `core/mellow_link/services/refactoring_support_engine/source_question_guard.py:61`, `:64` |
| 입력 조립 | context/safe bundle -> prepared input | `core/mellow_link/services/refactoring_support_engine/input_assembler.py:28`, `:56`, `:105`, `:127`, `:287` |
| 실행 API | run/session 생성, safe bundle run 시작 | `core/mellow_link/modules/rebuild_assistant/api.py:52`, `:108`, `:163` |
| 비동기 러너 | run 이벤트, thread spawn, 최종 emit | `core/mellow_link/modules/rebuild_assistant/runner.py:69`, `:305` |
| 엔진 퍼사드 | stage orchestration 총괄 | `core/mellow_link/services/refactoring_support_engine/facade.py:16`, `:28` |
| 구조 분석 | component/dependency/slice 도출 | `core/mellow_link/services/refactoring_support_engine/structure_analyzer.py:721`, `:728` |
| 진단 | structural issue / analysis summary / extracted rules | `core/mellow_link/services/refactoring_support_engine/diagnosis_engine.py:61`, `:77`, `:159`, `:212` |
| 판단 | family classification / decision summary | `core/mellow_link/services/refactoring_support_engine/decision_engine.py:25`, `:86` |
| 검증 루프 | evidence/conflict/stage 검증 | `core/mellow_link/services/refactoring_support_engine/validation_engine.py:8`, `:9` |
| 계획 | design option / execution stage 생성 | `core/mellow_link/services/refactoring_support_engine/improvement_planner.py:19`, `:23` |
| 결과 패키징 | judgment canvas / canonical payload 생성 | `core/mellow_link/services/refactoring_support_engine/result_packager.py:31`, `:38`, `:292` |
| 표현 정리 | internal/external surface wording, 상태 문구, 입력 타입별 스타일 분기 | `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`, `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py` |
| 런타임 계약 | stage control, stage assertion | `core/mellow_link/services/refactoring_support_engine/runtime_contracts.py:6`, `:32`, `:58`, `:71` |
| 공유 스키마 | 분석/결과 공용 데이터 구조 | `core/mellow_link/services/refactoring_support_engine/schemas.py:149`, `:164`, `:245`, `:340`, `:389`, `:427`, `:468`, `:482` |
| 익명화 스키마 | safe bundle / review report 공용 구조 | `core/mellow_link/services/anonymization/schemas.py:99`, `:109`, `:170`, `:191` |
| 결과 스키마 | structured result / canonical payload | `core/mellow_link/modules/rebuild_assistant/schemas.py:285`, `:407`, `:478` |

## 3. 모듈별 책임

- `main.py`
  - FastAPI 앱에 `chat_router`, `projects_router` 등을 등록한다.
  - 최상위 웹 진입점이다.

- `routers/chat.py`
  - 업로드 파일을 읽고 `extract_text_from_file()`로 텍스트/SML을 뽑는다.
  - staged upload와 `TEMP_CONTEXT_STORE` 갱신을 담당한다.

- `services/rag_service.py`
  - 파일 확장자별 추출 라우팅을 담당한다.
  - PPT/PPTX는 `extract_presentation_sml()`로 위임한다.

- `services/presentation_extraction.py`
  - PPT/PPTX 원본 바이너리를 분석 입력으로 직접 쓰지 않고 SML로 정규화한다.
  - `.pptx`, `.ppt`별 fallback 경로 품질 차이가 존재한다.

- `routers/projects.py`
  - 프로젝트 자산 승격, safe bundle 생성, analysis context 저장, preview 응답, 실제 run 시작을 담당한다.
  - 현재 오케스트레이션 책임이 가장 많이 몰린 라우터다.

- `services/anonymization/service.py`
  - 익명화 tokenization, mapping, canonical structure 추출, review report, safe bundle 재구성을 담당한다.

- `services/refactoring_support_engine/analysis_context_builder.py`
  - safe bundle을 `AnalysisContextBundle`로 고정한다.
  - asset/source/evidence/frame/fingerprint를 한 번 묶는 canonical 경계다.

- `services/refactoring_support_engine/source_question_guard.py`
  - safe source text를 읽고 source-grounded 질문 후보를 만들고 사용자 질문을 `allowed / blocked / needs_review`로 가른다.

- `services/refactoring_support_engine/input_assembler.py`
  - safe bundle 또는 analysis context를 `PreparedRebuildInput`으로 재조립한다.
  - `raw goal/constraints/question_axis`와 `effective goal/constraints/question_axis`를 `guarded_decision_input`으로 분리한다.
  - `asset_inventory`, `source_blocks`의 deterministic ordering도 여기서 보장한다.

- `modules/rebuild_assistant/api.py`
  - run/session 생성과 `start_rebuild_assistant_safe_bundle_run()` 호출을 담당한다.
  - project goal 우선순위도 여기서 정한다.

- `modules/rebuild_assistant/runner.py`
  - 별도 thread에서 run을 실행하고 event bus에 단계별 로그와 최종 result를 적재한다.

- `services/refactoring_support_engine/facade.py`
  - `analysis -> diagnosis -> decision -> validation -> planning -> package` 순서를 강제한다.

- `services/refactoring_support_engine/structure_analyzer.py`
  - source block에서 component, dependency, feature slice, hotspot, coverage를 만든다.

- `services/refactoring_support_engine/diagnosis_engine.py`
  - 구조 문제를 detector 기반으로 식별한다.
  - 동시에 legacy service를 이용해 analysis summary, extracted rules, grounded business rules도 만든다.

- `services/refactoring_support_engine/decision_engine.py`
  - family classification, template selection, primary judgment, decision record를 만든다.
  - 동시에 `DecisionBasis` 정량 점수, `DecisionConflict`, `recommendation_strength`를 만든다.

- `services/refactoring_support_engine/validation_engine.py`
  - evidence 부족, 판단 충돌, 금지 조건, stage 위반을 검사한다.
  - 내부적으로는 typed `DecisionValidationResult`를 반환하고, 외부 surface는 dict 호환을 유지한다.

- `services/refactoring_support_engine/improvement_planner.py`
  - design option, recommended option, verification, execution stage, risk checkpoint를 만든다.
  - `DecisionBasis.recommendation_strength`와 validation/conflict를 읽어 실행 계획 강도를 조절한다.
  - option strategy와 lightweight schedule hint도 함께 만든다.

- `services/refactoring_support_engine/result_packager.py`
  - judgment canvas, canonical payload, appendix, narrative fallback metadata까지 포함한 최종 결과를 만든다.
  - `recommendation_strength`를 읽어 conclusion wording, governance wording, recommended option 강도를 조절한다.

- `services/refactoring_support_engine/explanation_presenter.py`
  - 같은 판단 결과를 internal/external surface로 다르게 정리한다.
  - 외부용에서는 반복 문장을 줄이고, 핵심 이유를 짧게 압축하며, 입력을 `document / code / mixed`로 분류해 style별 wording을 적용한다.

- `modules/rebuild_assistant/postprocess/consulting_deck.py`
  - deck/markdown surface를 external용으로 다시 정리한다.
  - 입력 성격에 따라 `document_style / technical_style / mixed_style` 제목과 section label을 적용한다.

## 4. 모듈 간 계약

### 4.1 업로드 -> SML 추출 계약

- 호출 주체
  - `core/mellow_link/routers/chat.py:63` `upload_temp_document()`
- 호출 대상
  - `core/mellow_link/services/rag_service.py:91` `extract_text_from_file()`
  - `core/mellow_link/services/presentation_extraction.py:35` `extract_presentation_sml()`
- 입력
  - `UploadFile`, `session_id`
  - `Path(filename)`, `content_bytes`
- 출력
  - 추출 텍스트 문자열
  - PPT/PPTX는 SML 문자열
  - staged upload metadata와 `TEMP_CONTEXT_STORE` 누적 텍스트
- 실패/예외 처리
  - 빈 파일, `session_id` 누락, 추출 텍스트 5자 미만이면 `HTTPException(400)`
  - 예외 발생 시 staged 자산 정리 후 `HTTPException(500)`
- 의존 방향
  - Router -> extractor service -> presentation normalization
- 근거
  - `core/mellow_link/routers/chat.py:63`
  - `core/mellow_link/services/rag_service.py:91`
  - `core/mellow_link/services/presentation_extraction.py:35`

### 4.2 프로젝트 자산 -> Safe Bundle 계약

- 호출 주체
  - `core/mellow_link/routers/projects.py:1008` `_build_safe_bundle_for_project()`
  - `core/mellow_link/routers/projects.py:4459` `project_anonymization_review_preview()`
- 호출 대상
  - `core/mellow_link/services/anonymization/service.py:39` `AnonymizationService.run_anonymization_pipeline()`
- 입력
  - `AnonymizationAsset[]`
  - 각 자산은 `asset_id`, `name`, `kind_hint`, `content_text`, `original_bytes`
  - `AnonymizationRunRequest`
- 출력
  - `AnonymizationRunResult`
  - 핵심 downstream 입력은 `safe_bundle`
  - preview 경로는 `review_report`, `display_review_report`도 함께 사용
- 실패/예외 처리
  - project asset 파일 누락 시 `HTTPException(500)`
  - review 고위험은 현재 advisory이며 create를 막지 않는다
- 의존 방향
  - Project router -> anonymization service -> safe bundle/review report
- 근거
  - `core/mellow_link/routers/projects.py:1008`
  - `core/mellow_link/routers/projects.py:4459`
  - `core/mellow_link/services/anonymization/schemas.py:99`
  - `core/mellow_link/services/anonymization/schemas.py:109`
  - `core/mellow_link/services/anonymization/schemas.py:191`

### 4.3 Safe Bundle -> Analysis Context 계약

- 호출 주체
  - `core/mellow_link/routers/projects.py:1072` `_build_and_store_analysis_context()`
  - `core/mellow_link/modules/rebuild_assistant/api.py:108` `start_project_wrapped_run()`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:305` `start_rebuild_assistant_safe_bundle_run()`
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/analysis_context_builder.py:64` `AnalysisContextBuilder.build()`
- 입력
  - `SafeAnalysisBundle`
  - `goal`, `constraints`
  - 선택적으로 `project_name`, `client_name`, `template_key`, `warnings`
- 출력
  - `AnalysisContextBundle`
  - 내부에 `intent`, `assets`, `source_blocks`, `analysis_frame`, `evidence_index`, `trust`, `run`
- 실패/예외 처리
  - 함수 자체는 예외를 삼키지 않는다
  - 저장 경로에서는 `_persist_analysis_context()`가 DB commit/update를 수행한다
- 의존 방향
  - Router/API/runner -> analysis context builder
- 근거
  - `core/mellow_link/services/refactoring_support_engine/analysis_context_builder.py:61`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:149`
  - `core/mellow_link/routers/projects.py:1072`
  - `core/mellow_link/modules/rebuild_assistant/api.py:108`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:305`

### 4.4 Analysis Context -> Question Guard 계약

- 호출 주체
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:127` `prepare_analysis_context_input()`
  - `core/mellow_link/routers/projects.py:4459` `project_anonymization_review_preview()`
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/source_question_guard.py:64` `SourceQuestionGuardService.evaluate()`
- 입력
  - `AnalysisContextBundle`
  - `raw_goal`, `raw_constraints`
- 출력
  - `SourceQuestionGuardArtifacts`
  - `source_question_candidates`
  - `blocked_user_questions`
  - `review_user_questions`
  - `question_guard_summary`
  - `effective_goal`, `effective_constraints`, `preferred_question_axis`
- 실패/예외 처리
  - 후보가 부족하면 예외 대신 `needs_review`, `no_candidate_reasons`로 내린다
- 의존 방향
  - preview/create pipeline -> question guard
- 근거
  - `core/mellow_link/services/refactoring_support_engine/source_question_guard.py:61`
  - `core/mellow_link/services/refactoring_support_engine/question_guard_schemas.py`
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:127`
  - `core/mellow_link/routers/projects.py:4459`

### 4.5 Analysis Context -> Prepared Input -> Analysis Input 계약

- 호출 주체
  - `core/mellow_link/modules/rebuild_assistant/runner.py:305` `start_rebuild_assistant_safe_bundle_run()`
  - `core/mellow_link/routers/projects.py:1072` `_build_and_store_analysis_context()`
  - `core/mellow_link/modules/rebuild_assistant/service.py` `prepare_analysis_context_input()`, `prepare_safe_bundle_input()`, `prepare_input()`
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:56`, `:105`, `:127`, `:287`
- 입력
  - raw assets 또는 `SafeAnalysisBundle` 또는 `AnalysisContextBundle`
  - `goal`, `constraints`, `temp_context`
- 출력
  - `PreparedRebuildInput`
  - `PreparedRebuildInput.guarded_decision_input`
  - 이후 `assemble()`을 통해 `RefactoringAnalysisInput`
- 실패/예외 처리
  - `assemble()`는 `assert_stage_action()`으로 analysis stage를 강제한다
  - 나머지 prepare 계층은 주로 누락값을 빈 구조로 보정한다
- 의존 방향
  - API/runner/legacy service facade -> input assembler
- 추가 계약 메모
  - source question guard 결과는 `prepared.goal/constraints/question_axis`를 직접 덮어쓸 수 있지만, 원본 의도는 `raw_goal/raw_constraints`와 `guarded_decision_input.raw_*`에 분리 보관된다.
  - `asset_inventory`, `source_blocks`는 입력 순서가 아니라 deterministic 정렬을 거친다.
- 근거
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:56`
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:105`
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:127`
  - `core/mellow_link/services/refactoring_support_engine/input_assembler.py:287`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:164`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:245`

### 4.6 엔진 퍼사드 오케스트레이션 계약

- 호출 주체
  - `core/mellow_link/modules/rebuild_assistant/service.py:636` `RebuildAssistantService.build_result()`
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/facade.py:28` `RefactoringSupportEngineFacade.build_result()`
  - 내부 순서:
    - `InputAssembler.assemble()`
    - `StructureAnalyzer.analyze()`
    - `DiagnosisEngine.run()`
    - `DecisionEngine.run()`
    - `ValidationEngine.validate_decision()`
    - `ImprovementPlanner.run()`
    - `ResultPackager.package()`
- 입력
  - `PreparedRebuildInput`
  - `prepared.stage_control`
- 출력
  - `StructuredRebuildResult`
- 중간 제어
  - facade는 typed `DecisionValidationResult`를 받은 뒤 `prepared.decision_validation_result`에도 저장해 planner bridge에서 재사용한다.
- 실패/예외 처리
  - validation fail 시 decision 1회 재시도
  - 재시도 후에도 fail이면 `ValueError("validation failed after single retry: ...")`
  - 각 하위 엔진은 stage mismatch 시 `StageControlViolation`
- 의존 방향
  - legacy service facade -> refactoring support facade -> stage-specific engines
- 근거
  - `core/mellow_link/services/refactoring_support_engine/facade.py:16`
  - `core/mellow_link/services/refactoring_support_engine/facade.py:28`
  - `core/mellow_link/services/refactoring_support_engine/runtime_contracts.py:32`
  - `core/mellow_link/services/refactoring_support_engine/runtime_contracts.py:71`

### 4.7 구조 분석 -> 진단 -> 판단 -> 검증 -> 계획 계약

- 호출 주체
  - `RefactoringSupportEngineFacade.build_result()`
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/structure_analyzer.py:728` `StructureAnalyzer.analyze()`
  - `core/mellow_link/services/refactoring_support_engine/diagnosis_engine.py:77` `DiagnosisEngine.run()`
  - `core/mellow_link/services/refactoring_support_engine/decision_engine.py:86` `DecisionEngine.run()`
  - `core/mellow_link/services/refactoring_support_engine/validation_engine.py:9` `ValidationEngine.validate_decision()`
  - `core/mellow_link/services/refactoring_support_engine/improvement_planner.py:23` `ImprovementPlanner.run()`
- 입력
  - `RefactoringAnalysisInput`
  - `PreparedRebuildInput`
  - `StructureAnalysisResult`
  - `DiagnosisArtifacts`
  - `DecisionArtifacts`
- 출력
  - `StructureAnalysisResult`
  - `DiagnosisArtifacts`
  - `DecisionArtifacts`
    - `decision_summary`
    - `decision_basis`
    - `conflicts`
  - 내부 `DecisionValidationResult`
  - 외부 호환 `validation_result` dict
  - `ImprovementArtifacts`
- 실패/예외 처리
  - `ImprovementPlanner.run()`은 `decisions is None`이면 `ValueError`
  - `ValidationEngine.validate_decision()`은 typed result를 반환하고 facade가 1회 retry 규칙에 따라 이를 해석한다
- 추가 계약 메모
  - `DecisionBasis`는 `0.0_to_1.0` 스케일 점수와 `recommendation_strength`를 포함한다.
  - planner는 top decision basis와 validation/conflict를 읽어 `assertive / conditional / review_required / blocked` 실행 강도를 결정한다.
- 의존 방향
  - facade -> stage engines
  - diagnosis/decision/planning은 `PreparedRebuildInput`과 `legacy_service`에 동시에 의존한다
- 근거
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:340`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:389`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:427`
  - `core/mellow_link/services/refactoring_support_engine/schemas.py:468`

### 4.8 결과 패키징 계약

- 호출 주체
  - `RefactoringSupportEngineFacade.build_result()`
  - 이후 `runner.py`가 narrative augmentation과 event emit를 추가한다
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/result_packager.py:38` `ResultPackager.package()`
  - `core/mellow_link/services/refactoring_support_engine/result_packager.py:292` `_build_judgment_canvas()`
- 입력
  - `PreparedRebuildInput`
  - `StructureAnalysisResult`
  - `DiagnosisArtifacts`
  - `DecisionArtifacts`
  - `ImprovementArtifacts`
  - `validation_result`
  - `legacy_service`
- 출력
  - `StructuredRebuildResult`
  - `CanonicalRebuildPayload`
  - `judgment_canvas`
  - `appendix.context_linkage`
  - `extensions.question_guard`
  - `extensions.decision_governance.recommendation_strength`
  - `extensions.decision_governance.decision_basis`
  - `extensions.decision_governance.validation_summary`
- 실패/예외 처리
  - stage mismatch 시 `StageControlViolation`
  - judgment canvas 필수 필드는 내부 `_validate_judgment_canvas()`로 검증된다
- 추가 계약 메모
  - packager는 `recommendation_strength`에 따라 conclusion/risk wording을 조절한다.
  - `blocked`면 recommended option을 제거하고 결론을 강하게 확정하지 않는다.
- 의존 방향
  - result packager -> legacy service helper + deterministic narrative fallback
  - runner -> packager result -> event surface
- 근거
  - `core/mellow_link/services/refactoring_support_engine/result_packager.py:38`
  - `core/mellow_link/services/refactoring_support_engine/result_packager.py:292`
  - `core/mellow_link/modules/rebuild_assistant/schemas.py:285`
  - `core/mellow_link/modules/rebuild_assistant/schemas.py:407`

### 4.10 결과 표현 정리 계약

- 호출 주체
  - internal/external surface export 경로
  - consulting deck postprocess 경로
- 호출 대상
  - `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`
  - `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py`
- 입력
  - `StructuredRebuildResult` 또는 그 내부 `canonical_payload`, `judgment_canvas`, `extensions.decision_governance`
  - `surface_mode=internal|external`
- 출력
  - internal surface wording
  - external surface wording
  - external은 입력 성격에 따라 `document_style / technical_style / mixed_style` 중 하나를 적용한 설명 결과
- 실패/예외 처리
  - 별도 예외보다 deterministic fallback 문구를 우선 사용한다
  - planner/governance metadata가 부족하면 기존 외부용 fallback을 유지한다
- 추가 계약 메모
  - 입력 타입 분류는 payload를 새로 만들지 않고 기존 `report_scope`, `consulting_min_contract`, `analysis_summary`, `evidence_index`, `family` 정보를 읽어 수행한다.
  - `document`는 컨설팅 문서형, `code`는 기술 요약형, `mixed`는 문서형 설명 + 코드 분석 블록 분리를 의미한다.
  - 이 단계는 wording만 바꾸며 `DecisionEngine`, `ImprovementPlanner`, `CanonicalRebuildPayload` 자체는 수정하지 않는다.
- 의존 방향
  - packaged result -> explanation/deck surface layer
- 근거
  - `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`
  - `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py`

### 4.9 실행 API / 러너 계약

- 호출 주체
  - `core/mellow_link/routers/projects.py:4556` `create_project()`
  - `core/mellow_link/routers/projects.py:4859` `run_project_analysis()`
  - `core/mellow_link/modules/rebuild_assistant/api.py:163` `start_rebuild_assistant_from_bundle()`
- 호출 대상
  - `core/mellow_link/modules/rebuild_assistant/api.py:108` `start_project_wrapped_run()`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:305` `start_rebuild_assistant_safe_bundle_run()`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:69` `_spawn_rebuild_run()`
- 입력
  - `run_id`, `session_id`, `goal`, `constraints`, `safe_bundle`, `analysis_context`
- 출력
  - 비동기 thread 시작
  - run event stream
  - `EVENT_TYPE_RUN_FINISHED` payload에 `structured_result`, `authoritative_payload`, `canonical_payload` 포함
- 실패/예외 처리
  - runner thread 내부 예외는 run event failure로 흘러간다
  - create/reanalysis 라우터는 일부 실패 시 run status를 failed로 마킹한다
- 추가 계약 메모
  - runner event의 `authoritative_payload`는 stable public surface로 유지되며 현재 key set은
    - `family_classification`
    - `structure_snapshot`
    - `diagnosis_report`
    - `decision_summary`
    - `improvement_plan_bundle`
    - `appendix`
  - `judgment_canvas`, `validation_result`, `stage_control`은 `structured_result`에는 남지만 runner authoritative block에는 직접 섞지 않는다.
- 의존 방향
  - project router / module API -> runner thread -> event bus
- 근거
  - `core/mellow_link/modules/rebuild_assistant/api.py:108`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:69`
  - `core/mellow_link/modules/rebuild_assistant/runner.py:305`

## 5. 계약 명확도

### ✅ 명확

- `AnonymizationService.run_anonymization_pipeline()`
  - 이유: request/result가 `AnonymizationRunRequest`, `AnonymizationRunResult`, `SafeAnalysisBundle`, `AnonymizationReviewReport`로 명시됨
  - 근거: `core/mellow_link/services/anonymization/service.py:39`, `core/mellow_link/services/anonymization/schemas.py:99`, `:109`, `:170`, `:191`

- `AnalysisContextBuilder.build()`
  - 이유: safe bundle -> `AnalysisContextBundle` 전환 경계가 뚜렷하고 fingerprint/evidence/trust가 명시됨
  - 근거: `core/mellow_link/services/refactoring_support_engine/analysis_context_builder.py:64`, `core/mellow_link/services/refactoring_support_engine/schemas.py:149`

- `SourceQuestionGuardService.evaluate()`
  - 이유: 입력과 출력이 모두 구조화되어 있고 `QuestionGuardSummary` 진단 필드도 비교적 명확함
  - 근거: `core/mellow_link/services/refactoring_support_engine/source_question_guard.py:64`, `core/mellow_link/services/refactoring_support_engine/question_guard_schemas.py`

- `RefactoringSupportEngineFacade.build_result()`
  - 이유: stage 순서, retry 규칙, validation fail 처리까지 한 함수에 드러남
  - 근거: `core/mellow_link/services/refactoring_support_engine/facade.py:28`

- `ValidationEngine.validate_decision()`
  - 이유: 내부 결과가 `DecisionValidationResult`로 고정되었고, `passed / issues / conflicts / missing_evidence / retry_recommended / blocking_reason`가 명시됨
  - 근거: `core/mellow_link/services/refactoring_support_engine/validation_engine.py`, `core/mellow_link/services/refactoring_support_engine/schemas.py`

- `DecisionEngine.run()`
  - 이유: `DecisionBasis`, `DecisionConflict`, `recommendation_strength`가 명시적 schema로 고정되었고 score range도 `0.0_to_1.0`로 수렴함
  - 근거: `core/mellow_link/services/refactoring_support_engine/decision_engine.py`, `core/mellow_link/services/refactoring_support_engine/schemas.py`

- `runtime_contracts.py`
  - 이유: stage/action 허용/금지 규칙이 중앙 정의됨
  - 근거: `core/mellow_link/services/refactoring_support_engine/runtime_contracts.py:32`, `:58`, `:71`

- `ExplanationPresenter` / `consulting_deck`의 external wording style 분기
  - 이유: 판단 엔진과 payload를 바꾸지 않고, 입력 타입별 surface 표현만 분기하는 경계가 비교적 선명하다
  - 근거: `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`, `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py`

### ⚠️ 암묵적

- `InputAssembler.prepare_analysis_context_input()`
  - 이유: source block을 `source/schema/sql/ui/doc/framework`로 다시 분류하는 기준이 휴리스틱 중심이며, guard 결과가 여전히 `PreparedRebuildInput` 본체에 반영된다
  - 근거: `core/mellow_link/services/refactoring_support_engine/input_assembler.py:127`

- `RebuildAssistantService`와 하위 엔진의 상호작용
  - 이유: diagnosis/result packager가 `legacy_service`의 비공개 메서드에 의존한다
  - 예: `extract_feature_signals`, `detect_missing_context`, `build_grounded_business_rules`, `_sanitize_structured_result`
  - 근거: `core/mellow_link/modules/rebuild_assistant/service.py`, `core/mellow_link/services/refactoring_support_engine/diagnosis_engine.py:77`, `core/mellow_link/services/refactoring_support_engine/result_packager.py:38`

- `projects.py`의 preview/create/reanalysis 경로
  - 이유: safe bundle, analysis context, guard 호출 규칙이 퍼져 있어 한 군데 규칙 변경 시 동기화 누락 위험이 있다
  - 근거: `core/mellow_link/routers/projects.py:1008`, `:1072`, `:4459`, `:4556`, `:4859`

- `runner.py`의 이벤트 payload
  - 이유: authoritative block은 안정화됐지만 run event 전체 payload는 여전히 별도 schema로 고정되지 않았다
  - 근거: `core/mellow_link/modules/rebuild_assistant/runner.py:69`

- external surface의 입력 타입 분류 휴리스틱
  - 이유: `document / code / mixed` 분류는 기존 payload 텍스트를 읽는 heuristic 기반이며, 문서 안에 기술 용어가 많은 경우 `mixed`로 기울 수 있다
  - 근거: `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`, `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py`

### ❌ 위험

- `PreparedRebuildInput`를 공유 변이 컨테이너로 사용하는 방식
  - 이유: `guarded_decision_input`로 raw/effective ownership은 분리됐지만, 본체 `PreparedRebuildInput`는 여전히 `goal`, `constraints`, `question_axis`, `signals`, `missing_context`, `source_question_candidates`, `stage_control`, `decision_validation_result` 등을 누적해서 싣는다
  - 영향: 어느 단계가 값을 최종 소유하는지 불분명해질 수 있다
  - 근거: `core/mellow_link/services/refactoring_support_engine/schemas.py:164`, `core/mellow_link/services/refactoring_support_engine/input_assembler.py:127`

- `legacy_service`의 비공개 메서드 계약
  - 이유: 하위 엔진이 공개 인터페이스가 아닌 underscore 메서드에 강하게 결합되어 있다
  - 영향: `RebuildAssistantService` 내부 리팩터링이 곧 하위 엔진 파손으로 이어질 수 있다
  - 근거: `core/mellow_link/services/refactoring_support_engine/diagnosis_engine.py:77`, `core/mellow_link/services/refactoring_support_engine/result_packager.py:38`

- dict 기반 `stage_control`
  - 이유: validation 결과는 typed 내부 계약으로 정리됐지만 `stage_control`은 여전히 문자열 key 기반 dict다
  - 영향: key 오타, 구조 확장 시 회귀 가능성
  - 근거: `core/mellow_link/services/refactoring_support_engine/runtime_contracts.py`

- 라우터와 모듈 API가 context 생성 책임을 중복 보유
  - 이유: `projects.py`, `api.py`, `runner.py` 모두 `AnalysisContextBuilder.build()`를 직접 호출할 수 있다
  - 영향: 생성 규칙 drift 가능성
  - 근거: `core/mellow_link/routers/projects.py:1072`, `core/mellow_link/modules/rebuild_assistant/api.py:108`, `core/mellow_link/modules/rebuild_assistant/runner.py:305`

## 6. 수정이 필요한 후보

- `PreparedRebuildInput`를 immutable 단계 산출물로 분리하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: 입력 정규화, guard 적용, engine 입력의 책임 분리가 필요함

- `legacy_service` 의존을 명시적 protocol 또는 public adapter로 끌어올리는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: diagnosis/result packager가 비공개 메서드에 묶여 있음

- external surface style 분류 규칙을 별도 policy로 분리하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: 현재 `document / code / mixed` 판정은 표현 레이어 내부 heuristic에 남아 있어 조정 포인트가 코드에 박혀 있다

- `projects.py`의 safe bundle/context/guard orchestration을 service 레이어로 이동하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: preview/create/reanalysis 흐름의 중복이 큼

- `stage_control`를 typed schema로 승격하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: validation 결과는 내부 typed contract로 정리됐지만 stage control은 아직 dict 기반이라 회귀 추적이 약함

- runner event payload 계약을 별도 schema로 고정하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: `model_dump()` 결과에 consumer가 암묵적으로 의존하고 있음

- `DecisionBasis` score 정책을 별도 policy/config로 분리하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: 현재 score는 deterministic이지만 still heuristic이라 calibration 근거를 코드 밖으로 뺄 필요가 있다

- planner의 `review_required / blocked` 실행 템플릿을 stage-specific artifact로 명시하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: 지금은 최소 bridge 수준이라 verification-first roadmap이 helper 로직에 묻혀 있다

- PPT 추출 fallback별 품질 진단을 `AnalysisContextTrust` 또는 별도 extraction metadata로 고정하는 후보
  - 오늘은 수정하지 않음
  - 후보 이유: `.pptx`, `.ppt`, zip/xml fallback, binary fallback의 품질 차이가 현재 구조상 명시 계약으로 남지 않음

## 7. 다음 작업 제안

1. `PreparedRebuildInput` 단계 분리 우선
   - `raw input -> guarded input -> analysis input`을 별도 타입으로 분리하는 것이 우선순위가 가장 높다.

2. `legacy_service` 계약 표면화
   - diagnosis/result packager가 실제로 요구하는 메서드 집합을 public adapter로 고정할 필요가 있다.

3. `stage_control` 및 runner event schema 고정
   - validation contract는 정리됐고, 다음은 stage control과 run event authoritative contract를 typed surface로 고정할 차례다.

4. `projects.py` 오케스트레이션 축소
   - create/preview/reanalysis에서 safe bundle/context/guard 조립을 공통 서비스로 묶는 것이 다음 우선순위다.

5. `DecisionBasis` score policy 외부화
   - score threshold와 downgrade rule을 policy/config로 빼면 3단계 판단 계약의 변경 비용이 낮아진다.

6. extraction/anonymization/guard 진단 메타데이터 연결 강화
   - 현재는 개별 진단은 있지만 end-to-end 계약서 형태로는 흩어져 있다.
   - 이후에는 `safe_bundle -> analysis_context -> prepared -> result` 전체의 provenance를 한 번에 볼 수 있게 묶는 것이 좋다.

7. question guard 도메인 확장과 surface style 분류 정렬
   - 현재 question guard는 원가 중심 도메인 키워드에 더 강하고, external surface style은 별도 heuristic으로 `document / code / mixed`를 판단한다.
   - 이후에는 도메인 분류, 질문 후보 생성, external wording style이 같은 source signal을 공유하도록 맞추는 것이 좋다.
