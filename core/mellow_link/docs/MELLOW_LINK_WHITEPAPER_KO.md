# 멜로우 링크 판맥 백서

기준일: 2026-05-02  
문서 상태: Draft  
대상 시스템: `core/mellow_link` 중심의 멜로우 링크 판맥(MellowLink Senseframe)

## 1. 요약

멜로우 링크 판맥(MellowLink Senseframe)은 레거시 시스템의 문서와 코드성 자산을 업로드하면, 입력을 안전하게 정규화하고 익명화한 뒤 판단 질문, 판단 근거, 부족한 정보, 설계 선택지, 실행 가능 여부를 정리하는 웹 기반 판단 지원 프로그램이다.

이 시스템의 핵심 목적은 단순한 요약 생성이 아니다. 입력 자산에서 확인 가능한 근거를 중심으로 구조와 의존성을 해석하고, 현대화 또는 리팩터링 의사결정에 필요한 판단판과 실행 준비 후보를 제공하는 것이다.

현재 대표 제품 정의는 다음과 같다.

> 레거시 시스템의 구조, 흐름, 판단 근거를 분석하고 실행 가능한 현대화 방향으로 정리하는 웹 기반 판단 지원 프로그램

현재 구현 범위는 분석 결과 패키지와 결정 지원 영역에 집중되어 있다. 실행, 검증, 승인, 배포, 운영 감사까지의 전 과정 자동화는 향후 단계로 분리되어 있다.

## 2. 문제 정의

레거시 시스템 현대화 프로젝트에서는 다음 문제가 반복된다.

- 업무 문서, 화면 설명, SQL, 코드, 운영 규칙이 분산되어 있어 전체 구조를 한 번에 파악하기 어렵다.
- 컨설팅 문서나 전환 계획이 작성되더라도 근거 자산과 판단 사이의 연결이 약해 검토 비용이 크다.
- 사용자 목표나 프로젝트 설명 문구가 실제 자산보다 앞서면서, 근거 없는 전환 권고나 도메인 오염이 발생할 수 있다.
- 분석 결과가 실행 계획으로 이어지지 않아 후속 작업의 우선순위, 검증 지점, 위험 통제가 불명확해진다.

멜로우 링크 판맥은 이 문제를 "자산 기반 분석", "판단 통제", "결정 지원 패키징"의 세 축으로 다룬다.

## 3. 제품 범위

현재 제품명은 "멜로우 링크 판맥"으로 해석한다. "레거시 현대화 분석"은 대표 분석 시나리오/기능 설명으로 유지한다.

현재 단계:

- 1단계: 분석 + 결과 패키지 완료
- 2단계: 조치 제안 + 비교 부분 구현
- 3단계: 실행 준비 planned
- 4단계: 실행, 검증, 승인, 배포 planned
- 5단계: 운영, 로그, 감사 planned

현재 제공 가능한 결과는 크게 두 그룹이다.

분석 결과:

- 진단
- 설계안
- 전환 초안

결정 지원:

- 추천안
- 분리 우선순위
- 설계 선택지 비교
- 실행 준비 계획

여기서 `execution_plan`은 자동 실행 계획이 아니라 실행 준비 계획으로 해석한다. 즉, 시스템이 변경을 직접 수행한다기보다 사람이 검토하고 착수할 수 있는 단계, 체크포인트, 위험 조건을 정리한다.

## 4. 핵심 아키텍처

대표 실행선은 다음과 같다.

```text
project
-> anonymization
-> SafeAnalysisBundle
-> analysis context
-> question guard
-> prepared input
-> refactoring support engine
-> result package
```

실제 분석 파이프라인은 다음 흐름을 따른다.

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

### 4.1 입력 계층

업로드 계층은 PPT/PPTX, 문서, 코드성 텍스트 등 다양한 입력을 분석 가능한 텍스트와 구조 표현으로 변환한다. PPT/PPTX는 원본 바이너리를 직접 분석하지 않고 SML 형태의 canonical text로 정규화한다.

이 계층의 목표는 원본 파일의 표현 형식에 덜 의존하면서 downstream 엔진이 일관된 구조로 분석할 수 있게 만드는 것이다.

### 4.2 익명화 계층

익명화 계층은 원본 자산에서 민감 정보를 분리하고, 분석 가능한 safe bundle을 만든다. 핵심 산출물은 `SafeAnalysisBundle`이며, 검토용 review report와 safe preview도 함께 생성된다.

이 계층은 제품 신뢰의 하한선이다. 분석 엔진은 원본 정보가 아니라 익명화와 정규화가 적용된 safe bundle을 중심으로 동작한다.

### 4.3 분석 컨텍스트 계층

`AnalysisContextBuilder`는 safe bundle을 `AnalysisContextBundle`로 고정한다. 여기에는 자산 목록, source block, evidence index, analysis frame, trust 정보가 포함된다.

이 계층은 "무엇을 근거로 분석했는가"를 downstream 단계에 전달하는 canonical 경계다.

### 4.4 질문 가드 계층

`SourceQuestionGuardService`는 사용자 질문과 목표가 실제 source에 기반하는지 확인한다. source 기반 질문 후보를 생성하고, 허용 가능한 질문, 검토가 필요한 질문, 차단해야 하는 질문을 구분한다.

이 계층은 사용자의 의도가 분석을 돕는 보조 입력으로 쓰이게 하되, 근거 없는 결론을 만드는 신호로 과잉 승격되지 않도록 막는다.

### 4.5 판단 엔진 계층

`RefactoringSupportEngineFacade`는 다음 순서를 강제한다.

1. 구조 분석
2. 진단
3. 판단
4. 검증
5. 개선 계획
6. 결과 패키징

각 단계는 stage control과 validation contract를 통해 순서를 유지한다. 판단 결과는 `DecisionBasis`, `DecisionConflict`, `DecisionValidationResult`, `recommendation_strength` 같은 구조화된 계약으로 관리된다.

### 4.6 결과 표현 계층

결과 표현 계층은 내부 판단을 바꾸지 않고 사용자에게 보여줄 문장을 정리한다. `ExplanationPresenter`와 `consulting_deck`은 입력 성격을 `document`, `code`, `mixed`로 분류하고, 외부용 wording을 각각 `document_style`, `technical_style`, `mixed_style`로 조정한다.

중요한 원칙은 표현 레이어가 판단 내용을 바꾸지 않는다는 점이다. `DecisionEngine`, `ImprovementPlanner`, `CanonicalRebuildPayload`의 계약은 유지하고, surface wording만 조정한다.

## 5. 판단 통제 원칙

멜로우 링크 판맥의 핵심 차별점은 "그럴듯한 답변"보다 "근거가 추적되는 판단"을 우선한다는 점이다.

판단 위계는 다음 순서로 고정한다.

```text
asset-derived > detector-derived > decision linkage > goal wording
```

의미는 다음과 같다.

- `asset-derived`: 코드, UI, SQL, schema, business document에서 직접 확인된 신호
- `detector-derived`: structure analysis와 diagnosis 결과로 생성된 issue
- `decision linkage`: issue id, evidence id, score, explainability
- `goal wording`: 사용자 목표, 제약, 프로젝트 설명 문구

사용자 목표와 제약은 중요하지만, 구조 판단의 단독 근거가 될 수 없다. 특히 migration 관련 판단은 자산 기반 근거 없이 생성되면 안 된다.

Hard Guard Rule은 다음 위험을 차단한다.

- 자산 근거 없는 migration 판단
- goal 문구만으로 생성된 migration signal
- wrapper wording contamination
- domain-anchor spillover
- evidence 부족 상태의 과도한 추천

## 6. 결과 패키지

최종 결과는 단순 markdown 요약이 아니라 decision support package로 해석한다.

대표 구성은 다음과 같다.

- `family_classification`: 입력 또는 문제 유형 분류
- `structure_snapshot`: 구조, component, dependency, slice 요약
- `diagnosis_report`: 구조 문제와 원인 후보
- `decision_summary`: 핵심 판단과 근거
- `improvement_plan_bundle`: 추천 옵션, 실행 단계, 검증 체크포인트
- `appendix`: context linkage와 추가 근거
- `extensions.question_guard`: 질문 가드 결과
- `extensions.decision_governance`: 판단 강도, 근거 점수, validation summary

추천 강도는 다음 상태를 가진다.

- `assertive`: 근거가 충분하고 실행 권고가 비교적 명확한 상태
- `conditional`: 조건부 권고가 적절한 상태
- `review_required`: 추가 검토가 필요한 상태
- `blocked`: 근거 부족 또는 충돌로 권고를 차단해야 하는 상태

이 상태는 planner, packager, external surface에서 서로 어긋나지 않게 유지되어야 한다.

## 7. 품질 기준

회귀 검증 기준은 exact output snapshot이 아니라 판단 구조와 도메인 적합성이다. 문장 표현은 바뀔 수 있지만, 판단 품질과 실행 가능성은 유지되어야 한다.

좋은 결과의 최소 조건은 다음 다섯 가지다.

- 도메인 적합: 입력 샘플군의 expected domain profile과 결과의 핵심 판단 축이 맞아야 한다.
- 근거 기반: source, SML, safe source, question guard, evidence ref 없이 결론이 과도하게 강해지면 안 된다.
- 오염 없음: source에 없는 외부 도메인 문구가 결론에 섞이면 안 된다.
- 실행 가능: 판단 결과가 planner의 단계, checkpoint, priority와 연결되어야 한다.
- 과도한 확신 없음: evidence 부족, conflict, blocked 또는 review_required 상태에서는 단정형 결론을 피해야 한다.

대표 회귀 진입점은 `core/mellow_link/tests/test_ppt_batch_regression.py`이며, batch 결과는 `core/mellow_link/tests/output/ppt_regression_report.json`에 기록된다.

## 8. 보안과 운영 경계

멜로우 링크 판맥의 보안 모델은 "입력 원본을 그대로 판단에 노출하지 않고, safe bundle을 중심으로 분석한다"는 방향에 기반한다.

주요 운영 경계는 다음과 같다.

- 업로드 파일은 staged upload로 수신된다.
- 프로젝트 자산은 승격 과정을 거친다.
- 익명화 파이프라인은 review report와 safe bundle을 생성한다.
- 분석 컨텍스트는 safe bundle에서 파생된다.
- 결과 surface는 internal과 external로 나뉜다.

현재 review 고위험은 advisory 성격이며, 모든 경우에 create를 차단하는 강제 정책으로 해석하지 않는다. 향후 파일럿 또는 상용 운영 단계에서는 high-risk review 결과에 대한 승인 정책, 보관 정책, 반출 정책을 더 명확히 고정할 필요가 있다.

## 9. 현재 한계와 기술 부채

현재 구조에서 우선 관리해야 하는 위험은 다음과 같다.

- `PreparedRebuildInput`이 여러 중간 산출물을 누적하는 공유 변이 컨테이너로 쓰인다.
- `legacy_service`의 비공개 메서드에 diagnosis와 result packager가 의존한다.
- `stage_control`은 아직 typed schema가 아니라 dict 기반이다.
- `projects.py`, module API, runner가 context 생성 책임을 일부 중복 보유한다.
- runner event payload 전체가 별도 schema로 완전히 고정되어 있지는 않다.
- external surface style 분류가 heuristic 기반이다.
- PPT 추출 fallback별 품질 차이가 analysis trust metadata로 충분히 고정되어 있지 않다.

이 한계는 제품 방향의 실패가 아니라, 다음 안정화 단계에서 다뤄야 할 계약 정리 대상이다.

## 10. 로드맵

우선순위가 높은 후속 작업은 다음과 같다.

1. `PreparedRebuildInput` 단계 분리
   - raw input, guarded input, analysis input을 별도 타입으로 분리한다.

2. `legacy_service` 계약 표면화
   - diagnosis와 result packager가 요구하는 메서드 집합을 public adapter 또는 protocol로 고정한다.

3. `stage_control` 및 runner event schema 고정
   - validation contract와 같은 수준으로 stage와 event payload를 typed surface로 승격한다.

4. `projects.py` 오케스트레이션 축소
   - preview, create, reanalysis에서 safe bundle, context, guard 조립을 공통 service로 묶는다.

5. `DecisionBasis` score policy 외부화
   - threshold와 downgrade rule을 policy 또는 config로 분리한다.

6. extraction, anonymization, guard 진단 메타데이터 연결 강화
   - safe bundle부터 result까지 provenance를 한 번에 추적할 수 있게 한다.

7. question guard와 surface style 분류 정렬
   - 도메인 분류, 질문 후보 생성, 외부 표현 스타일이 같은 source signal을 공유하게 한다.

## 11. 적용 대상

멜로우 링크 판맥이 특히 유효한 대상은 다음과 같다.

- 레거시 시스템 현대화 사전 진단
- 업무 문서와 코드성 자산이 함께 존재하는 시스템 분석
- 화면, SQL, 운영 규칙이 얽힌 업무 흐름의 구조화
- 컨설팅 산출물의 근거 추적성 강화
- 실행 전 분리 우선순위와 검증 체크포인트 도출

반대로, 현재 단계에서 다음 용도는 제한적으로 해석해야 한다.

- 자동 코드 변경
- 승인 없는 배포 자동화
- 운영 감사 로그의 완전한 대체
- 보안 심사 없이 민감 원본을 외부로 반출하는 분석

## 12. 결론

멜로우 링크 판맥은 대표 시나리오인 레거시 현대화 분석을 "문서 요약"이 아니라 "근거 기반 판단과 실행 준비" 문제로 다룬다. 입력 정규화, 익명화, source-grounded question guard, 단계형 판단 엔진, validation, 결과 패키징을 연결해 사람이 검토 가능한 결정 지원 문서를 생성한다.

현재 시스템은 분석과 결과 패키지 영역에서 실사용 가능한 주 경로를 갖추고 있으며, 조치 제안과 비교 기능은 부분 구현 상태다. 다음 발전 단계의 핵심은 실행 자동화 자체보다 먼저 계약 안정화, provenance 강화, typed schema 확장, 운영 정책 고정이다.

## 참고 기준 문서

- `README.md`
- `MODULE_CONTRACT_STATUS.md`
- `core/mellow_link/docs/README.md`
- `core/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_DECISION_GOVERNANCE.md`
- `core/mellow_link/docs/ANONYMIZATION_MVP_STATUS.md`
- `core/mellow_link/docs/PILOT_SECURITY_AND_OPERATIONS_NOTICE.md`
- `refactoring_support_engine.md`
