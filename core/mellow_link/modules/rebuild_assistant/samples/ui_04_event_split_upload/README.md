# ui_04_event_split_upload

목적:

- 일반 실행에서 user/admin surface 분리 확인
- anonymization summary와 debug anonymization report 분리 확인

사용 방법:

- `/projects/create`에서 `README.md`를 제외한 나머지 파일을 업로드
- 권장 고객사명: `Event Split Demo`

예상 포인트:

- 일반 사용자 run snapshot에는 `anonymization_summary`만 보임
- admin dev event stream에서만 `debug_anonymization_report` 확인 가능

