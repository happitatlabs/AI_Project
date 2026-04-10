# ui_03_sensitive_signal_upload

목적:

- 민감 문자열 다수 포함 시 preview masking 안전성 확인
- summary와 preview 역할 차이 확인

사용 방법:

- `/projects/create`에서 `README.md`를 제외한 나머지 파일을 업로드
- 권장 고객사명: `Sensitive Signals Inc`

예상 포인트:

- source/sql/text/framework 자산 포함
- email, phone, internal host, internal path, token 문자열 다수 포함
- preview에 raw 민감값이 직접 남지 않아야 함

