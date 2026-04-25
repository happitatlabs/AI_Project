# Missing Exchange Rates Fixture Sample

상태: fixture-only  
분류: legacy fixture / contract sample

이 디렉터리는 환율 누락 실패 경로를 재현하기 위한 fixture다.  
golden regression이나 promoted expansion regression 대상이 아니라, 특정 회계/서술/실패 경로 테스트에서 부분적으로만 읽는다.

현재 자산:
- `accounting_payload.json`
- `legacy_context.txt`

현재 비허용 용도:
- canonical golden regression
- promoted expansion regression
- measured expansion sample 실행 입력

필요 시 runnable sample로 승격하려면 아래가 추가되어야 한다.
- `input_manifest.json`
- `expected_assertions.yaml`
- 샘플 상태 정의 문서
