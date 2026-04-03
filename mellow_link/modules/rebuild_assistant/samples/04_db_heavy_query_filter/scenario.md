# DB-heavy / Query Filter형

## 샘플 ID
- 04_db_heavy_query_filter

## 분류
- db_heavy_query_filter

## 목적
- query_filter_leak, duplicate predicate, DB-heavy 구조에서 판단/계획 안정성 검증

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
