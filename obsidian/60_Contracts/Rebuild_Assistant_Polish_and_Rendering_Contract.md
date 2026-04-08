---
title: Rebuild Assistant Polish and Rendering Contract
tags:
  - contract
  - rebuild-assistant
  - polish
  - rendering
created: 2026-04-06
status: current
---

# Rebuild Assistant Polish and Rendering Contract

## 원문 기준

- `core/mellow_link/docs/REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md`
- `core/mellow_link/docs/REBUILD_ASSISTANT_POLISH_UI_RENDERING_CONTRACT_2026-03-30.md`

## 핵심 목적

`structured_result`를 바꾸지 않은 채, 표현 후처리와 UI 렌더 계층만 별도로 두는 계약이다.

## 판단 불변 원칙

후처리나 UI 렌더에서 바꾸면 안 되는 것:

- `primary_judgment`
- `template_judgment`
- `structural_judgment`
- `narrative_axis`
- 근거 규칙과 retained contract
- 추천안과 execution plan
- 숫자, 상태값, 코드명, 역할명

## 후처리 3단계

1. sentence polish
2. audience summary transform
3. delivery tone rewrite

## audience / delivery 축

- audience
  - `developer`
  - `manager`
  - `client`
- delivery mode
  - `internal_review`
  - `client_report`
  - `proposal_appendix`

## UI 렌더 핵심

- 결과 JSON에 `polish_bundle` 포함
- 결과 화면에 audience selector 표시
- 결과 화면에 delivery mode selector 표시
- 회계 섹션은 원문/variant를 전환해 볼 수 있음
- `polish_bundle`가 없어도 기존 렌더는 깨지지 않아야 함

## 현재 읽는 법

이 계약은 표현 계층만 다룬다.  
구조 분석, score 계산, canonical judgment 규칙은 엔진 기준 문서로 본다.

## 같이 볼 노트

- [[Rebuild_Assistant_Report_and_Refinement_Contract]]
- [[Rebuild_Assistant_Accounting_Contract]]
