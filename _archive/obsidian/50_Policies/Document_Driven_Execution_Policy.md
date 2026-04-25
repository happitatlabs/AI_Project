---
title: Document-Driven Execution Policy
tags:
  - policy
  - execution
  - docs
created: 2026-04-06
status: current
---

# Document-Driven Execution Policy

## 원문 기준

- `core/mellow_link/docs/DOCUMENT_DRIVEN_AI_EXECUTION_PIPELINE_RULES.md`

## 핵심 목적

문서를 많이 쌓는 것이 아니라, 에이전트가 실제로 따라야 할 실행 기준 문서만 남기도록 통제하는 정책이다.

## 문서 상태 3종

- `Draft`
  - 아이디어 초안
  - 바로 실행 기준으로 쓰지 않음
- `Contract`
  - 현재 작업의 공식 실행 기준
  - 목표, 범위, 완료 조건, 금지 사항이 명확해야 함
- `Locked`
  - 실행과 검토를 거쳐 장기 기준으로 확정된 문서

## 입력 우선순위

`Locked > Contract > Draft > 대화 임시 문장`

즉 대화에서 나온 문장은 문서에 반영되기 전까지 공식 기준이 아니다.

## 실행 금지 조건

아래 중 하나면 기본적으로 실행하면 안 된다.

- Contract 문서가 없음
- Contract끼리 충돌함
- 수정 범위가 불명확함
- 완료 조건이 없음
- 금지 사항이 없음
- Locked 문서와 정면 충돌함

## 기본 루프

1. Draft 생성
2. Contract 확정
3. Build 실행
4. 결과 Reflect
5. KEEP/MODIFY/DELETE 분류
6. Locked 갱신

## 운영 의미

- 사람은 세부 구현자가 아니라 유지/수정/삭제를 판단하는 오너로 남는다.
- 실행 후 문서를 갱신하지 않으면 기준이 오염된다.
- `rebuild_assistant` 후속 반영 시 상태 문서 갱신이 필수다.

## 같이 볼 노트

- [[AI_Augmentation_Policy]]
- [[Contracts_Index]]
