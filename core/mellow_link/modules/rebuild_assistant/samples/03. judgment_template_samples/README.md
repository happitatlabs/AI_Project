# Judgment Template Reference Set

상태: reference-only  
분류: non-regression snippet set

이 디렉터리는 runnable sample이 아니다.  
목적은 judgment/template 축을 설명하거나 수동 점검할 때 사용할 최소 code/sql snippet를 보관하는 것이다.

현재 포함된 축:
- `state_transition`
- `access_control`
- `validation`

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
- detector / template 예시 조각 확인
- 문서 설명용 reference
- 향후 runnable sample 생성 시 seed material

승격 조건:
1. 별도 runnable sample 디렉터리 생성
2. `input_manifest.json` 추가
3. `expected_assertions.yaml` 추가
4. 테스트 편입 여부 결정
