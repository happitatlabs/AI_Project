# Lenient Policy Warning Fixture Sample

상태: fixture-only  
분류: legacy fixture / contract sample

이 디렉터리는 lenient policy 경고 경로를 재현하기 위한 fixture다.  
golden regression 기준이 아니라 특정 narrative / accounting 경고 테스트에서만 부분적으로 사용한다.

현재 자산:
- `accounting_payload.json`
- `legacy_context.txt`

현재 비허용 용도:
- canonical golden regression
- promoted expansion regression
- measured expansion sample 실행 입력

필요 시 승격 조건:
1. 샘플 목적을 별도 문서로 고정
2. `input_manifest.json` 추가
3. `expected_assertions.yaml` 추가
