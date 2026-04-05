# Refactoring Support Engine Review Layer Design

기준일: 2026-04-05  
상태: Active  
기준 문서: [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)

## 목적

Review Layer의 목적은 AI 설명이 아니라 reviewer가 구조 차이, detector 근거, decision 차단 사유를 직접 검증할 수 있게 하는 것이다.

핵심 원칙:
- canonical payload는 변경하지 않는다.
- Review Layer는 additive artifact다.
- machine-readable source는 `extensions["review_diff"]`다.
- validation run 문서는 `review_diff`를 소비하는 generated surface다.

## 구성

### Structural Diff
- component 구조
- dependency 흐름
- layer 경계
- data flow

### Evidence Diff
- fingerprint 반복
- detector 근거 locator
- scatter / leak / coupling trace

### Decision Diff
- allowed decision
- blocked decision
- block reason
- `synthetic_signal_detected`
- governance guard 적용 여부

### 현재 구조 vs 권장 구조 비교
- `review_diff.code_diff`
- internal-only evidence layer
- 실제 패치가 아니라 현재 구조와 권장 패턴의 차이를 검토하기 위한 비교 예시다
- 최소 `observed / expected_pattern` snippet만 포함
- external surface에는 포함하지 않음
- execution patch와는 별도 레이어로 유지한다

## 배치 원칙

- 선택: `extensions["review_diff"]`
- 비선택: `appendix` 직접 확장
- generated consumer: validation run 문서의 `Review Diff` 섹션

선택 이유:
- `appendix`는 authoritative payload 일부라 canonical payload 비변경 원칙과 충돌한다.
- validation 문서만 source로 두면 UI/QA에서 재사용할 machine-readable 구조가 없다.

## Surface Policy

Review Layer surface는 아래로 고정한다.

### `/projects/{id}/result`
- full machine-readable `extensions["review_diff"]`를 노출한다.
- reviewer UI와 validation script의 source of truth로 사용한다.

### `/projects/{id}/result/explanation`
- full markdown diff를 직접 노출하지 않는다.
- additive `review_diff_preview`만 노출한다.
- preview에는 아래만 포함한다.
  - structural summary 1~3개
  - evidence summary 1~3개
  - blocked decision summary
  - `synthetic_signal_detected`
  - governance guard 적용 여부

### Result UI
- raw `/result`를 읽는 결과 화면은 Review Diff를 3블록으로 렌더링한다.
  - `Decision Result`
  - `Why this decision?`
  - `Structural Difference`
- 순서는 항상 `Decision -> Evidence -> Structural`로 유지한다.
- `allowed`, `blocked`, `synthetic_signal_detected`, governance guard 정보는 `Decision Result`에서 가장 먼저 강조한다.
- internal mode에서는 `Primary / Blocked / Confidence` sticky summary bar를 먼저 고정 노출한다.
- 기본 open 상태는 아래로 고정한다.
  - `Decision Result`: 항상 열림
  - `Why this decision?`: 기본 열림
  - `Evidence Detail`: 기본 접힘
  - `현재 구조 vs 권장 구조 비교`: 기본 접힘
- full markdown은 접힘 영역에서만 보여준다.

## Internal / External Exposure Policy

이 문서에서 `internal`은 reviewer, QA, validation, debug consumer를 뜻한다.  
`external`은 client-facing surface, 공유용 산출물, 일반 사용자 설명 surface를 뜻한다.

기본 원칙:
- `review_diff`는 내부 검증 artifact다.
- external surface는 canonical judgment와 evidence만 사용한다.
- external surface에 `review_diff`의 full diff를 직접 노출하지 않는다.
- `surface_mode`는 현재 public selector이고, 실제 field gating은 internal `access_profile/capability` policy가 담당한다.
- capability 이름은 행동(action)이 아니라 노출(view/access) 기준으로 고정한다.
  - 예: `can_view_review_diff`, `can_view_code_diff`, `can_view_block_reasons`, `can_view_governance_trace`, `can_view_detector_locator`, `can_export_review_artifacts`

| Surface | Artifact | Internal | External | 기본 정책 |
|---|---|---|---|---|
| `/projects/{id}/result` | `extensions["review_diff"]` full JSON | 허용 | 비노출 | internal source of truth |
| Result UI | `Decision Result / Why this decision? / Structural Difference` | 허용 | 비노출 | reviewer 전용 |
| `/projects/{id}/result/explanation` | `review_diff_preview` | 허용 | 기본 비노출 | internal compact preview |
| validation run 문서 | full markdown diff | 허용 | 비공유 | governance / contamination 기록 |
| QA 스크린샷 | rendered Review Diff | 허용 | 비공유 | UI regression evidence |
| md/docx/pptx export | Review Diff section | 허용 | 비포함 | 같은 canonical source를 surface rule로 필터링 |

external 금지 항목:
- `blocked_decisions`
- `block_reasons`
- `synthetic_signal_detected`
- `decision_engine_guard_applied`
- `result_packager_guard_applied`
- fingerprint alias
- detector locator
- file/line 기반 diff trace

external 허용 기준:
- `structural_judgment`
- `recommended_strategy`
- top `decision_type`
- `score_breakdown`의 사용자용 요약
- citation이 연결된 evidence 설명

export 원칙:
- internal export는 검토용 산출물이다.
- internal export는 `review_diff`와 governance trace를 포함할 수 있다.
- external export는 설명용 산출물이다.
- external export는 `review_diff`, blocked decision, contamination trace를 포함하지 않는다.
- internal/external export는 다른 분석을 만들지 않고 같은 canonical source를 surface별로 필터링한다.

운영 메모:
- current implementation의 public selector는 `surface_mode=internal|external`다.
- 내부 구현은 `surface_mode -> access_profile -> capability` 구조로 동작한다.
- 현재 mapping은 아래로 고정한다.
  - `internal` -> `internal_full`
  - `external` -> `external_basic`
- 향후 확장 profile 예시는 아래를 기준으로 한다.
  - `internal_limited`
  - `external_advanced`
- external에서 필요한 것은 Review Diff가 아니라 canonical judgment explanation이다.

### Filtered Artifact Trace

filtered artifact 상태는 `없음`과 `숨김`을 구분한다.

- `absent`
  - 원래 데이터가 없음
- `hidden_by_policy`
  - 데이터는 있었지만 surface policy로 숨김

현재 응답 payload는 surface policy에 맞춰 실제 필드를 제거할 수 있다.  
대신 provenance/debug trace는 `field_visibility`를 통해 `absent`와 `hidden_by_policy`를 구분할 수 있어야 한다.

## Mode Flow

### Internal Reviewer Flow
1. `/projects/{id}/result` 진입
2. `Decision Result`에서 allowed / blocked / contamination 여부 확인
3. `Why this decision?`에서 positive evidence / no migration signals 확인
4. `Structural Difference`에서 구조 차이와 expected pattern 확인
5. 필요 시 validation run 문서와 raw JSON으로 drill-down

### External Presentation Flow
1. `/projects/{id}/result/explanation?surface_mode=external` 진입
2. `구조 판단`, `권장 전략`, `판단 근거`, `설명 관점`만 확인
3. citation과 section view로 canonical explanation 확인
4. Review Diff, blocked decision, governance detail은 노출하지 않음

운영 원칙:
- internal flow는 검증 중심이다.
- external flow는 설명 중심이다.
- external flow는 canonical judgment를 전달하지만 governance artifact를 직접 보여주지 않는다.

## Shared vs Branched Components

### Shared Components
- `taxonomy_view.core_judgment`
- `taxonomy_view.evidence_view`
- `taxonomy_view.explanation_context`
- `summary_cards`
- `section_views`
- citation rendering

### Internal-Only Components
- `extensions["review_diff"]` full JSON
- Review Diff UI
  - `Decision Result`
  - `Why this decision?`
  - `Structural Difference`
- `review_diff_preview`
- validation markdown diff
- governance flag display
  - `synthetic_signal_detected`
  - `decision_engine_guard_applied`
  - `result_packager_guard_applied`

### External-Only Restrictions
- `review_diff_preview` 숨김
- blocked decision 숨김
- contamination / guard detail 숨김
- detector locator, fingerprint alias, file/line trace 숨김
- `code_diff` 필드 제거

## 익명화 규칙

- 실제 코드 식별자는 Review Diff에 그대로 쓰지 않는다.
- 일반화된 이름을 사용한다.
  - `Component01`
  - `QueryFragment01`
  - `ValidationRule01`
- 파일명과 locator는 유지할 수 있다.
- raw excerpt는 기본 surface에서 직접 노출하지 않는다.

## validation 연동

- real-project validation script는 `extensions["review_diff"]["markdown"]`가 있으면 `## Review Diff` 섹션에 삽입한다.
- reviewer 메모는 validation 문서에 추가할 수 있지만, machine-readable source of truth는 계속 `extensions["review_diff"]`다.
