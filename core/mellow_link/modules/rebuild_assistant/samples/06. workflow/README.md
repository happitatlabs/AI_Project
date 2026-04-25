# Workflow Fixture Sample

상태: fixture-only  
분류: legacy fixture / contract sample

이 디렉터리는 workflow 서술/계약 테스트에서 사용하는 최소 fixture다.  
golden regression이나 promoted expansion regression 대상이 아니라, 특정 workflow narrative 확인용 보조 자산으로만 사용한다.

현재 자산:
- `cs_leave_workflow.cs`
- `ts_approval_flow.ts`

현재 허용 용도:
- workflow 설명 축 수동 점검
- 계약/서술 테스트용 fixture

현재 비허용 용도:
- canonical golden regression
- promoted expansion regression
- measured expansion sample 실행 입력
