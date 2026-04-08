---
title: Rebuild Assistant Accounting Contract
tags:
  - contract
  - rebuild-assistant
  - accounting
created: 2026-04-06
status: current
---

# Rebuild Assistant Accounting Contract

## 원문 기준

- `core/mellow_link/docs/REBUILD_ASSISTANT_ACCOUNTING_MVP_CONTRACT_2026-03-30.md`

## 핵심 목적

기존 `rebuild_assistant` 본체를 유지한 채 `structured_result.extensions.accounting` 확장만 병렬로 추가하는 계약이다.

## 범위

1. `accounting_analysis`
2. `fx_calculation`
3. `voucher_review`

## 고정 원칙

- 기존 판단 엔진 수정 금지
- `primary_judgment`, retained contract, recommended option, execution plan 변경 금지
- 입력 신뢰성이 계산 정확도보다 우선
- 필수 입력 없으면 추정 계산 금지

## 필수 입력

- `transactions`
- `exchange_rates`
- `policies`

## strict 모드

- 기본값 `strict=True`
- 불명확하면 실패
- `strict=False`여도 필수 입력 누락은 실패

## 출력 구조

- `input_validation`
- `calculation_status`
- `accounting_analysis`
- `fx_calculation`
- `voucher_review`
- `summary_sentence`

## 완료 기준 핵심

- `/projects/create` 경로에서 회계 JSON 인식
- `extensions.accounting` 생성
- 성공/실패 상태와 `summary_sentence`가 항상 일치
- result package와 polish bundle에 회계 섹션 반영

## 같이 볼 노트

- [[Rebuild_Assistant_Polish_and_Rendering_Contract]]
- [[Rebuild_Assistant_Report_and_Refinement_Contract]]
