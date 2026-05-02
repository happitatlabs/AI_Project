# mellow_link

역할: core  
목적: 멜로우 링크 판맥(MellowLink Senseframe)의 메인 웹/API 본체다. 레거시 현대화 분석은 대표 분석 시나리오/기능으로 유지한다.
연결: 결과 산출물은 [`data/outputs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/outputs), 런타임 로그는 [`data/logs`](/C:/Users/Hyein/ClaudeAI/AI_Project/data/logs), 관련 지원 파이프라인은 [`pipelines/pattern_extraction_pipeline`](/C:/Users/Hyein/ClaudeAI/AI_Project/pipelines/pattern_extraction_pipeline)와 연결된다.

대표 사용자 진입점:
- `/projects/create`
- `/projects/{project_id}`
- `/projects/{project_id}/result?surface_mode=internal|external`

`/modules/rebuild_assistant`는 현재 안내 진입점이며, 실제 실행 시작은 `/projects/create`다.
