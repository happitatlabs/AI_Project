# Daily Agent Risk Analyzer Scope and Terminology

- 문서 상태: Implementation contract draft
- 대상 단계: Daily Agent Phase 2
- 구현 여부: 문서 전용 PR이며 코드 구현 없음

## Agent의 정확한 의미

이 설계에서 `Daily Agent`는 인증된 사용자가 자신의 `DailyState`를 기록하고 되돌아보도록 돕는 개인용 기능을 뜻한다. 다음 저장소 개념과는 다른 도메인이다.

- Pilot 작업을 수행하는 자동 agent 또는 `AgentRun`
- `AgentFolder`, `AgentBrain`, autonomous agent
- 코드 실행 위험을 분류하는 기존 `core/risk_classifier.py`
- 프로젝트 현대화 분석, Approval Queue, Delivery Checklist 또는 Package Assembly

따라서 분석 주체는 프로젝트나 Pilot이 아니라 인증된 사용자 본인이다. `Daily Agent Risk Analyzer`를 기존 코드 위험 분류기나 Pilot 운영 상태에 연결하지 않는다.

## 분석 단위와 식별

Canonical 분석 단위는 `(subject_user_id, local_date)`다.

| 개념 | 계약 |
| --- | --- |
| `subject_user_id` | 내부 FK. 응답에는 노출하지 않음 |
| `subject_ref` | 내부 ID에서 파생한 안정적인 opaque reference |
| `local_date` | `DailyState.date`와 동일한 `YYYY-MM-DD`; UTC instant로 변환해 날짜를 바꾸지 않음 |
| `timezone` | 평가 시점에 고정한 유효한 IANA timezone 이름 |
| `evaluation_window` | 기본은 해당 local date 1일. 초기 rule set은 다른 날짜를 임상적 추세로 해석하지 않음 |

현재 `User` 모델에는 timezone이 없다. 수동 평가는 유효한 IANA timezone을 명시하고, scheduled 평가는 사용자가 명시적으로 저장한 schedule preference의 timezone을 사용한다. 서버 timezone이나 IP 위치로 추측하지 않는다.

## 실행 종류

- `manual`: 인증된 사용자가 자신의 날짜를 명시해 요청한다.
- `scheduled`: 명시적으로 opt-in한 schedule preference가 기존 scheduler adapter를 통해 같은 service contract를 호출한다.
- `backfill`: 과거 local date를 명시적으로 평가한다. 한 요청 최대 31일이다.
- `replay`: 같은 날짜를 새 input snapshot 또는 rule set version으로 다시 평가한다.

자동 schedule은 기본 비활성이다. 외부 queue나 새 worker framework를 도입하지 않으며 schedule trigger는 건강 payload를 보관하지 않는다.

## 목적과 비의료 경계

Risk Assessment는 사용자가 직접 입력한 값을 결정적 rule로 분류해 다시 확인할 항목을 설명하는 advisory record다. 의료 진단, 자살 위험의 임상적 판정, 응급 여부 확정, 처방 또는 치료 결정을 뜻하지 않는다.

`selfHarmUrge`는 사용자가 직접 입력한 0~10 값이다. 이 숫자를 검증된 임상 screening 도구로 재해석하지 않으며 NIMH ASQ 같은 별도 질문지의 결과라고 주장하지 않는다. 비영(0이 아닌) 값은 단지 사용자가 직접 안전 관련 신호를 보고했다는 사실로 처리한다.

## 권한 경계

- 기본 조회·평가·acknowledge 주체는 해당 DailyState의 사용자 본인뿐이다.
- 기존 `ADMIN` 역할만으로 다른 사용자의 건강 assessment를 읽거나 처리할 수 없다.
- 중앙 운영자 review queue나 Pilot Approval Queue를 재사용하지 않는다.
- 향후 보호자·임상가·안전 운영자 접근은 명시적 동의, 역할, 감사 정책을 먼저 설계하는 별도 범위다.

## Out of scope

- LLM 또는 생성형 AI 판단
- 질병·정신건강 진단과 치료 권고
- 약물 이름, 용량, 상호작용 또는 복용 변경 판단
- 자동 연락, push, 문자, 이메일, 가족·응급기관 호출
- Pilot 상태 변경, Delivery/Package 차단
- Green/Yellow/Orange/Red 색상 엔진
- notes 또는 daily brick 자유 텍스트 분석
- Morning/Evening Check-in, Weekly Report, Priority 5 기능

## 관련 문서

- [Input Contract](daily-risk-input-contract.md)
- [Signal Model](daily-risk-signal-model.md)
- [Rule Engine](daily-risk-rule-engine.md)
- [Actions and Review](daily-risk-actions-and-review.md)
- [Security and Privacy](daily-risk-security-privacy.md)
