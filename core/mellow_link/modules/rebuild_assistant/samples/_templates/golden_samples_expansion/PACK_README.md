# Golden Samples Expansion Template Pack

상태: active template pack

이 디렉터리는 `refactoring_support_engine` 확장 샘플을 만들 때 복제해서 쓰는 템플릿 묶음이다.  
압축 파일 설명이나 외부 pack 기준이 아니라, 현재 repository 안의 실제 샘플 구조를 기준으로 본다.

## 목적

- measured expansion sample을 일정한 형식으로 추가
- promoted expansion regression 승격 전 필요한 파일 구조를 고정
- human review 문서와 machine assertion source를 분리

## 현재 기준 문서

- [samples/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/README.md)
- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLES.md)
- [REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_GOLDEN_SAMPLE_EXPANSION_QA_CHECKLIST.md)

## 권장 샘플 축

1. CRUD 단순형
2. 권한 + 승인 흐름형
3. 상태 전이 복잡형
4. DB-heavy / query-filter 중심형
5. 레거시 뒤엉킴 구조형

## 템플릿 파일

- `sample_contract.md`
  - 새 샘플의 목적, canonical anchor, 금지 조건을 먼저 적는 계약 초안
- `phase3_qa_question_pack.json`
  - explanation / Q&A smoke용 질문 팩

## 새 runnable sample 추가 순서

1. `samples/` 아래에 새 디렉터리를 만든다.
2. 아래 파일을 추가한다.
   - `scenario.md`
   - `input_manifest.json`
   - `expected_assertions.yaml`
   - `assets/*`
   - 필요 시 `notes/human_review_result_sample.md`
3. 실제 자산으로 엔진을 실행한다.
4. measured anchor를 `expected_assertions.yaml`에 기록한다.
5. 샘플 상태를 아래 중 하나로 정한다.
   - `provisional_measured`
   - `promoted_expansion_regression`
6. 필요한 테스트에 편입한다.

## 파일 역할 원칙

- `expected_assertions.yaml`
  - machine assertion source
- `notes/*.md`
  - 사람 검토용 참고 문서
  - regression source로 사용하지 않음
- `assets/*`
  - 실제 입력 자산

## 주의

- canonical 비교 대상은 deterministic core다.
- `primary_judgment`는 compatibility/template axis다.
- 구조 판단은 `structural_judgment`와 `decision_summary`를 기준으로 읽는다.
- `human_review_result_sample.md`를 `expected_assertions.yaml`로 그대로 옮기지 않는다.
- reference-only snippet set은 이 pack으로 직접 승격하지 않는다. runnable sample 구조로 먼저 재구성해야 한다.
