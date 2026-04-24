---
title: Mellow-Link Runtime Performance and Integration References
tags:
  - mellow-link
  - runtime
  - performance
  - integration
  - reference
created: 2026-04-06
status: current
---

# Mellow-Link Runtime Performance and Integration References

## 용도

이 노트는 runtime, chat/media integration, OpenAPI, 성능 튜닝, 보조 실험 문서를 한 묶음으로 보는 참고 노트다.

## 포함하는 문서군

- chat/runtime/media 관련 소개, 브리프, OpenAPI
- runtime 구현 과제, 테스트 제안, UI migration 자료
- output/queue/token/TTFT/VRAM/performance 최적화 문서
- evolution/self-evolution/tool usage 보조 문서
- SQL analytics, auxiliary engine, integration 참고 문서

## 어떻게 읽어야 하나

- 현재 대표 제품 정의는 [[Mellow_Link]]와 [[Mellow_Link_Product_and_Roadmap]]를 우선한다.
- 이 문서군은 직접적인 제품 핵심 계약이라기보다, 주변 런타임과 운영 최적화, 보조 기능, 과거 확장 방향을 설명하는 참고 자료다.
- 일부는 역사 문서거나 sidecar 성격 문서일 수 있다.

## 주의

- 현재 상용 1차 제품 기준과 직접 연결되지 않는 문서가 섞여 있다.
- 계약이나 canonical 판단 규칙이 필요하면 엔진/계약/검증 레이어를 먼저 본다.

## 같이 볼 노트

- [[Mellow_Link_Operations_and_Known_Issues]]
- [[Output_and_Response_Policies]]
- [[Mellow_Link_Flow_Maps_and_Specs]]
