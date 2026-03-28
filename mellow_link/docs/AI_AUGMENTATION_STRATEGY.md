# AI Augmentation Strategy

기준일: 2026-03-29  
대상: `mellow_link`의 `rebuild_assistant` 결과 품질 보정 구조

## 1. 목적

AI를 무분별하게 사용하는 것이 아니라, 분석 엔진의 신뢰성을 유지하면서 해석력과 실무 가치를 강화하기 위한 정확한 투입 지점을 정의한다.

이 전략의 목표는 아래와 같다.

- 결과의 일관성 유지
- 결과의 이해도 상승
- 결과의 컨설팅 활용성 강화
- `분석 도구`를 `컨설팅 보조 시스템`으로 진화

## 2. 핵심 원칙

### 2.1 역할 분리 원칙

| 영역 | 담당 |
|---|---|
| 패턴 추출 | Deterministic Engine |
| 의미 해석 | AI |
| 누락 탐지 | AI |
| 결과 번역 | AI |
| 최종 검증 | Deterministic Guard |

### 2.2 금지 원칙

아래 영역에는 AI를 직접 투입하지 않는다.

- 패턴 추출 단계
- 전체 분석 위임
- 재현성이 깨지는 판정 기준
- 원본 evidence를 덮어쓰는 수정

즉, `AI가 사실을 판정`하게 두지 않는다.  
AI는 `보정`, `해석`, `번역`에만 사용한다.

### 2.3 운영 원칙

- 같은 입력이면 같은 구조 결과가 먼저 나와야 한다.
- AI는 그 구조 결과를 더 잘 읽히게 만드는 보정기여야 한다.
- deterministic 결과와 AI 해석이 충돌하면 deterministic 결과를 우선한다.

## 3. 전체 구조

```text
Deterministic Engine
  -> signal / evidence / rule candidate 추출
  -> contract / template candidate 생성
  -> AI 보정 1. 규칙 해석
  -> AI 보정 2. 누락 탐지
  -> AI 보정 3. 결과 번역
  -> Deterministic Guard
  -> Result Package
```

핵심은 다음 한 줄이다.

- 패턴 추출은 절대 고정
- AI는 해석, 누락 탐지, 결과 번역만 담당

## 4. AI 보정 지점

### 4.1 규칙 해석 보정

위치:

- 패턴 추출 직후

입력:

- SQL 조건
- 코드 조건문
- 상태 값
- 필터 조건
- grounded rule candidate
- evidence ref

출력:

- 규칙명
- 업무 의미
- 자연어 설명

예:

- 입력: `status IN ('A', 'B')`
- 출력: `진행 중 상태 데이터 조회 조건`

역할:

- 기술 조건을 업무 의미로 변환
- 사람이 이해 가능한 규칙 문장 생성

### 4.2 규칙 보강 / 누락 탐지

위치:

- 규칙 세트 완성 이후

입력:

- 전체 규칙 집합
- 상태 흐름
- 승인 구조
- retained contracts
- flow summary

출력:

- 누락된 규칙 후보
- 모순 탐지
- 불완전 흐름 경고

예:

- 입력: 승인 규칙 존재
- 출력: `반려 처리 경로가 정의되지 않았을 가능성`

역할:

- 숨은 리스크 탐지
- 컨설팅 수준의 판단 보조

### 4.3 결과 번역 / 압축

위치:

- `Structured Result -> Result Package` 직전

입력:

- 분석 결과 전체
- 규칙 및 리스크 정보
- 선택된 판단 템플릿

출력:

- Executive Summary
- 핵심 결론
- 추천안 이유
- 우선순위 문장
- 대상별 설명 문장

예:

- 개발자: `status 조건 분기 누락`
- 팀장: `업무 흐름 누락 위험`
- 고객: `처리 누락 가능성 존재`

역할:

- 결과를 보고서 수준으로 번역
- 대상별 이해도 최적화

## 5. 입력 / 출력 계약

### 5.1 Interpretation Layer

입력:

- `signals`
- `grounded rule candidates`
- `evidence refs`

출력:

- `interpreted_rules[]`

### 5.2 Validation Layer

입력:

- `interpreted_rules`
- `retained_contracts`
- `flow_summary`

출력:

- `missing_rule_candidates[]`
- `consistency_warnings[]`

### 5.3 Presentation Layer

입력:

- `structured_result`

출력:

- `executive_summary`
- `selection_reason`
- `priority wording`
- `report phrasing`

## 6. AI가 수정하면 안 되는 영역

아래 필드는 deterministic 결과로 고정한다.

- `primary_template`
- `raw signals`
- `retained_contract evidence`
- `status contract raw values`
- `asset presence`
- `public/private masking boundaries`
- `safe bundle guard`

즉:

- AI는 해석과 표현은 가능
- AI는 사실 판정 원본은 수정 불가

## 7. 비허용 영역

### 7.1 패턴 추출 단계

문제:

- AI는 확률 기반
- 패턴 추출은 규칙 기반

위 두 층을 직접 결합하면 아래 문제가 생긴다.

- 재현성 붕괴
- 신뢰도 하락
- 디버깅 불가능

### 7.2 전체 분석 위임

금지 예:

- `AI야 분석해줘`

이 방식의 결과:

- 엔진 구조 무력화
- 제품 차별성 상실
- 품질 통제 불가능

## 8. 충돌 시 우선순위 규칙

아래 규칙을 고정한다.

1. deterministic 결과와 AI 해석이 충돌하면 deterministic 결과 우선
2. AI confidence가 낮으면 기존 규칙 기반 결과 유지
3. AI 출력은 금지 표현 필터와 구조 validator를 통과해야 반영
4. evidence 없는 신규 사실은 결과에 확정으로 올리지 않음

## 9. 현재 `mellow_link`에 적용하는 기준

현재 `rebuild_assistant`에서는 아래처럼 해석한다.

- `state_transition`
  - 상태 전이
  - 처리 가능 상태
  - 전이 조건
- `access_control`
  - 권한
  - 부서
  - 승인 주체
  - 예외 승인
- `validation`
  - 차단 조건
  - 저장 전 검증
  - 검증 순서
  - 중복 방지

따라서 AI는 아래를 보정하는 데 쓴다.

- top-level narrative 선택
- 핵심 규칙 2~3개 우선순위 정리
- 추천안 이유 정리
- 우선순위 / 실행 계획 설명
- 근거 카드 자연어 요약
- 문장 polish

반대로 아래는 코드로 고정한다.

- 자산 존재 판정
- 상태/권한/금액/검증 신호 추출
- status 계약 원값 추출
- retained contract 후보 생성
- 템플릿 판정 기준
- 금지 표현 검증

## 10. 최종 결론

AI는 많이 넣는 것이 아니라 정확한 위치에 넣는 것이 핵심이다.

현재 `mellow_link` 기준으로는 아래 3곳이 AI 보정의 유효 지점이다.

1. 규칙 해석
2. 누락 탐지
3. 결과 번역

이 구조를 유지하면:

- 분석 엔진의 재현성은 지키고
- 결과의 이해도와 설득력은 높이고
- 제품은 `레거시 분석 도구`를 넘어 `컨설팅 보조 시스템`으로 진화할 수 있다.
