# Query Filter Reference Set

상태: reference-only  
분류: non-regression snippet set

이 디렉터리는 runnable sample이 아니다.  
목적은 query/filter 축의 최소 TypeScript + SQL snippet를 reference로 보관하는 것이다.

현재 포함된 파일:
- `ts_request_filter.ts`
- `sql_request_search.sql`

현재 이 디렉터리에 없는 것:
- `goal.txt`
- `constraints.txt`
- `input_manifest.json`
- `expected_assertions.yaml`

따라서 아래 용도로는 사용하지 않는다.
- canonical golden regression
- promoted expansion regression
- measured expansion sample 실행 입력

현재 허용 용도:
- query_filter narrative/template axis 설명
- query_filter detector 예시 reference
- 향후 runnable sample 구성 시 seed material

승격 조건:
1. 별도 runnable sample 디렉터리 생성 또는 현재 디렉터리 재구성
2. `input_manifest.json` 추가
3. `expected_assertions.yaml` measured anchor 추가
4. regression test 편입
