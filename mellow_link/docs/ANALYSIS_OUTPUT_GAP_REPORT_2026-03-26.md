# Analysis Output Gap Report

기준일: 2026-03-26  
목적: 현재 `rebuild_assistant` 산출물의 오분석 항목을 고정하고, 다음 수정 이후 재테스트 기준으로 사용한다.

대상 산출물:

- [주문_관리_화면_현대화_result.md](/C:/Users/Hyein/Downloads/주문_관리_화면_현대화_result.md)
- [청구_조정_기능을_현대적인_서비스_구조_재구성_result.md](/C:/Users/Hyein/Downloads/청구_조정_기능을_현대적인_서비스_구조_재구성_result.md)

입력 샘플 기준:

- [java_order_closure_case_01](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/java_order_closure_case_01)
- [python_claim_adjustment_case_01](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/python_claim_adjustment_case_01)

## 1. 공통 문제

### 1.1 추가 자료 요청 오탐

문제:

- 두 산출물 모두 `DB 스키마 또는 핵심 SQL`을 추가 요청한다.
- 실제 입력 자산에는 `schema.sql`, `query.sql`이 이미 포함되어 있다.

판정:

- 입력 자산 존재 여부를 고려하지 못한 오탐
- 자산 결합 분석 실패

기대 결과:

- 이미 업로드된 자산은 추가 자료 요청에서 제외해야 한다.
- 정말 누락된 자료만 요청해야 한다.

### 1.2 내부용 feature mode 노출

문제:

- `status_permissions`
- `search_filters`
- `save_validation`

위 표현이 사용자 산출물에 그대로 드러난다.

판정:

- 내부 추론/분류용 라벨이 사용자 결과 화면과 Markdown 산출물에 노출됨

기대 결과:

- 사용자용 기능 유형명으로 번역되어야 한다.
- 예:
  - 권한 및 상태 규칙
  - 조회 조건 규칙
  - 저장 검증 규칙

### 1.3 템플릿형 설계안 과다

문제:

- 두 산출물 모두 `React + REST API + repository` 같은 일반론적 현대화 문구가 중심이다.
- 입력 샘플별 차이보다 공통 템플릿이 더 강하게 보인다.

판정:

- 샘플 특화 분석보다 일반 현대화 템플릿이 우세

기대 결과:

- 샘플별 핵심 규칙과 제약이 설계안에 직접 반영되어야 한다.

### 1.4 익명화 문구 품질 부족

문제:

- `role[REDACTED_PATH]`
- `UI[REDACTED_PATH]`
- `command[REDACTED_PATH]`

같은 표현이 결과 문장에 남아 있다.

판정:

- 보안 경계는 지켰지만 사용자 결과 문장 품질이 떨어짐

기대 결과:

- 의미는 유지하되 사용자 문장으로 자연스럽게 재서술해야 한다.

## 2. Java 샘플 오분석 항목

대상:

- [주문_관리_화면_현대화_result.md](/C:/Users/Hyein/Downloads/주문_관리_화면_현대화_result.md)
- 샘플 입력: [java_order_closure_case_01/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/java_order_closure_case_01/README.md)

### 2.1 핵심 기능명 불충분

현재 결과:

- `order 기능`
- `주문 관리 화면 현대화`

문제:

- 실제 샘플은 일반 주문 관리가 아니라 `주문 마감 기능`이다.
- 핵심 액션이 `마감(close)`인데 결과에서 이 동작이 흐려진다.

기대 결과:

- `주문 마감 기능`
- `주문 마감 승인/제한 규칙`
- `마감 상태 전이`

### 2.2 핵심 업무 규칙 복원 실패

샘플에서 반드시 잡혀야 하는 규칙:

- VIP 고객은 야간 마감 금지
- 대리점 채널 고액 주문은 본사만 마감 가능
- 배송보류 건은 마감 전 해제 필요
- 수출 주문 고액건은 `REVIEW_REQUIRED` 전환

현재 결과 문제:

- 위 규칙이 설계안/진단/전환 초안에 구체적으로 정리되지 않음
- `권한`, `상태 전이`, `검색`, `저장 검증` 같은 추상 표현으로만 묶임

### 2.3 SQL/스키마 활용 부족

문제:

- `query.sql`, `schema.sql`이 존재하는데도 database 초안이 `자산 부족`으로 처리된다.

기대 결과:

- `sales_order`
- `order_close_history`
- `status`, `channel_code`, `customer_grade`, `delivery_hold_flag`, `order_type`

같은 실제 컬럼과 테이블 기반 설명이 들어가야 한다.

## 3. Python 샘플 오분석 항목

대상:

- [청구_조정_기능을_현대적인_서비스_구조_재구성_result.md](/C:/Users/Hyein/Downloads/청구_조정_기능을_현대적인_서비스_구조_재구성_result.md)
- 샘플 입력: [python_claim_adjustment_case_01/README.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/samples/python_claim_adjustment_case_01/README.md)

### 3.1 주 기능 오식별

현재 결과:

- 핵심 기능을 `approval` 중심으로 표현

문제:

- 실제 샘플의 중심 기능은 `청구 조정(claim adjustment)`이다.
- 승인 규칙은 그 기능 안의 일부다.

기대 결과:

- `청구 조정 기능`
- `조정 가능 여부 판단 규칙`
- `청구 조정 승인 한도 및 예외 처리`

### 3.2 핵심 업무 규칙 복원 실패

샘플에서 반드시 잡혀야 하는 규칙:

- `FRAUD` 사고는 `HQ_REVIEWER`만 처리 가능
- `BRANCH_MANAGER`는 300만원 이상 조정 불가
- 1천만원 이상은 `CLAIM_AUDIT` 부서만 조정 가능
- 특수지점 `B99` 긴급건은 본사 선승인 필요
- `CLOSED`, `CANCELLED` 상태는 조정 불가

현재 결과 문제:

- 위 규칙이 개별 규칙으로 드러나지 않음
- `save_validation`, `status_permissions` 같은 내부 라벨로 흐려짐

### 3.3 도메인 구조 추론 부족

기대되는 도메인 개념:

- claim
- adjustment
- reviewer
- branch manager
- audit department
- urgent claim

현재 결과 문제:

- `approval`, `request`, `customer` 중심으로 일반화돼서 도메인 손실이 큼

## 4. 재테스트 통과 기준

다음 수정 후에는 아래 항목이 충족되어야 한다.

### 4.1 공통

- 이미 업로드된 `schema.sql`, `query.sql`이 있으면 `추가 자료 요청`에 다시 나오지 않아야 한다.
- 내부 라벨(`status_permissions`, `save_validation`, `search_filters`)이 사용자 산출물에서 사라져야 한다.
- `REDACTED_PATH` 기반 문구가 사용자 설명문에서 제거되어야 한다.

### 4.2 Java 샘플

- 핵심 기능명이 `주문 마감`으로 표현되어야 한다.
- 아래 규칙 중 최소 3개 이상이 명시적으로 결과 본문에 포함되어야 한다.
  - VIP 야간 마감 금지
  - 대리점 고액 주문 HQ only
  - 배송보류 해제 선행
  - 수출 주문 고액건 리뷰 필요

### 4.3 Python 샘플

- 핵심 기능명이 `청구 조정`으로 표현되어야 한다.
- 아래 규칙 중 최소 4개 이상이 명시적으로 결과 본문에 포함되어야 한다.
  - FRAUD -> HQ_REVIEWER only
  - 지점장 300만원 한도
  - 1천만원 이상 CLAIM_AUDIT only
  - B99 긴급건 본사 선승인
  - CLOSED/CANCELLED 조정 불가

## 5. 수정 우선순위

1. 업로드 자산 기반 `추가 자료 요청` 오탐 제거
2. feature mode -> 사용자용 기능 유형명 번역
3. goal/제약조건/파일명 기반 도메인명 유지 강화
4. 코드/SQL/화면/문서 교차 규칙 추출 보강
5. 결과 문장 품질 정리
