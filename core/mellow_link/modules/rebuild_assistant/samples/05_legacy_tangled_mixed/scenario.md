# 레거시 뒤엉킴 구조형

## 샘플 ID
- 05_legacy_tangled_mixed

## 분류
- legacy_tangled_mixed

## 목적
- 여러 책임 혼합, boundary mismatch, mixed responsibility가 동시에 나오는 최악 구조 샘플 검증

## 채워야 할 자산
- code
- sql
- ui
- schema
- supporting docs

## 기대 포인트
- feature slice 추출이 과분할/과소분할 없이 안정적이어야 함
- detector와 decision이 이 샘플 특성에 맞게 나와야 함
- recommended option과 execution plan linkage가 유지돼야 함
