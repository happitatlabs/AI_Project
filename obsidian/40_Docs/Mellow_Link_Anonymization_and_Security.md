---
title: Mellow-Link Anonymization and Security
tags:
  - mellow-link
  - anonymization
  - security
created: 2026-04-06
status: current
---

# Mellow-Link Anonymization and Security

## 핵심 원칙

- canonical source는 익명화 완료본이다.
- 구조 추출은 canonical anonymized source 기준으로만 수행한다.
- `rebuild_assistant`는 raw 입력 대신 `SafeAnalysisBundle`만 소비한다.
- original content, original path, mapping 정보는 외부 응답과 결과 패키지에 노출하지 않는다.

## 익명화 계층 역할

위치:
- `core/mellow_link/services/anonymization`

주요 책임:
- 저장 경계 관리
- 토큰화와 식별자 매핑
- 구조 추출
- masking policy 적용
- `SafeAnalysisBundle` 생성
- public export 생성

## `SafeAnalysisBundle` 경계

포함:
- `asset_summary`
- `sources`
- `structures`
- `guard`

비포함:
- original content
- original file path
- mapping content
- mapping path

## 공개/비공개 기준

- `FULL`
  - internal canonical analysis source
  - 기본 외부 비공개
- `PARTIAL`
  - 외부 제공 가능
- `FULL_MASKED`
  - 외부 제공 가능

즉 masking level과 외부 다운로드 정책은 같은 개념이 아니다.

## 파일럿 운영 주의

- 자동 삭제는 아직 미지원
- 자동 만료 정책도 현재 범위 밖
- 프로젝트 자산과 익명화 산출물은 재분석을 위해 보관될 수 있음
- 이 파일럿은 운영 배포/실행 보증 문서가 아니라 의사결정 지원용 초안 제공 범위다

## 같이 볼 노트

- 제품/로드맵: [[Mellow_Link_Product_and_Roadmap]]
- 엔진 거버넌스: [[Mellow_Link_Engine_Governance_and_QA]]
- 상위 제품: [[Mellow_Link]]
