# Rebuild Assistant Result Status

기준일: 2026-03-28  
상태: 판단 템플릿 3종은 통과, 실샘플은 구조상 통과 단계, 남은 작업은 문장 polish

## 1. 현재 결론

`rebuild_assistant`는 현재 `레거시 분석 요약` 단계를 넘어 `컨설턴트 의사결정 지원 도구` 구조로 정리됐다.

현재 기준으로 아래 항목은 구조상 통과로 본다.

- 판단 템플릿 샘플
  - `state_transition`
  - `access_control`
  - `validation`
- 실샘플
  - `청구 조정`
  - `상태전환`
  - `접근제어`
  - `검증`

`주문 관리 화면 현대화` 실샘플은 구조상 거의 통과이며, 남은 차이는 보조 계약과 문장 정리 수준이다.

## 2. 이번 라운드에서 정리된 항목

### 2.1 결과 패키지 구조

현재 결과 패키지는 아래 순서를 고정한다.

1. Executive Summary
2. 핵심 결론
3. 핵심 업무 규칙
4. 즉시 결정 필요
5. 유지해야 할 계약
6. 분리 우선순위
7. 확인 필요 항목
8. 설계 선택지 비교
9. 추천안
10. 실행 계획
11. 리스크
12. 전환 초안
13. 부록

### 2.2 출력 품질

아래 항목은 구조적으로 정리됐다.

- 내부 라벨 직접 노출 제거
  - `status_permissions`
  - `search_filters`
  - `save_validation`
- 내부 토큰 제거
  - `REDACTED_PATH`
  - `SAFE STRUCTURE`
  - `TBL_001`, `COL_001` 등 익명 식별자 직접 노출
- 결과 문장 결정형 통일
  - `~하는 것이 필요합니다`
  - `~를 우선 적용해야 합니다`
  - `~를 유지해야 합니다`

### 2.3 판단 템플릿 구조

현재 1차 판단 템플릿은 아래 3종이다.

- `state_transition`
- `access_control`
- `validation`

추천안, 분리 우선순위, 실행 계획은 템플릿 조합 기준으로 생성하며, 도메인명 하드코딩은 제목/앵커 수준으로만 남겼다.

### 2.4 access_control 보강

현재 `access_control` 문서는 아래 구조를 갖는다.

- 핵심 규칙 3개 구조
  - 금액 기준 권한 제한
  - 권한 위임 가능 여부
  - 승인 요청 및 처리 흐름
- 확인 필요 항목 2개 이상
  - 권한 위임 세부 범위
  - 예외 승인 조건 상세
  - 처리 후 통지와 후속 처리 절차

### 2.5 validation 보강

현재 `validation` 문서는 아래 축으로 유지된다.

- 차단 조건
- 저장 전 검증
- 검증 순서
- 중복 방지
- 선행 조건

즉시 결정 필요 3개와 분리 우선순위 1/2/3순위도 고정된다.

### 2.6 state_transition 보강

현재 `state_transition` 문서는 아래 축을 유지한다.

- 상태 전이
- 처리 가능 상태
- 전이 조건

status 계약은 결과 상태만 남기지 않고 입력 상태와 결과 상태를 함께 포함하도록 보강했다.

예:

- `PAID`
- `READY`
- `COMPLETED`

## 3. 최신 샘플 판정

### 3.1 판단 템플릿 샘플

- `검증_result (13)`  
  - 통과
- `접근제어_result (18)`  
  - 통과
- `상태전환_result (18)`  
  - 통과

### 3.2 실샘플

- `청구_조정_기능을_현대적인_서비스_구조_재구성_result (12)`  
  - 통과
  - top-level narrative가 권한/부서/승인 주체 중심으로 복구됨
- `주문_관리_화면_현대화_result (9)`  
  - 거의 통과
  - 상태 계약 오염은 제거됨
  - 보조 validation 계약이 다소 강하게 남아 있음

## 4. 최신 보정 결과

이번 단계에서 실제로 해결된 문제는 아래와 같다.

- `청구 조정` 실샘플의 top-level narrative를 `access_control` 중심으로 복구
- `상태전환` 실샘플의 status 계약에 입력 상태 + 결과 상태 동시 유지
- `status` 계약에서 `BRANCH`, `VIP`, `CLAIM_AUDIT` 같은 비상태 값 제거
- `access_control` sparse 샘플에서 보강 로직이 실제 run 생성에 반영되도록 수정

## 5. 테스트 상태

최신 회귀 테스트:

```text
pytest -q mellow_link/tests/test_phase1_run_flow.py mellow_link/tests/test_module_registry_and_runs.py mellow_link/tests/test_anonymization_mvp.py
121 passed
```

현재 회귀는 아래를 포함한다.

- 결과 패키지 구조 유지
- 내부 토큰 비노출
- 템플릿별 primary narrative 유지
- status 계약 추출 회귀
- access_control 보강 회귀
- validation 우선순위 회귀

## 6. 남은 작업

현재 남은 작업은 구조 수정이 아니라 제출용 polish다.

- 조사 오류 정리
  - 예: `한도을`
- 보조 validation 문장 축약
  - 특히 `주문 관리 화면 현대화` 실샘플
- 근거 카드 문장 자연화
- DOCX/PPTX 최종 문장 검수

## 7. 현재 해석 기준

현재 제품/품질 판단은 아래 우선순위로 본다.

1. 코드
2. 본 상태 문서
3. [`ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/ANALYSIS_OUTPUT_GAP_REPORT_2026-03-26.md)
4. 개별 샘플 산출물
