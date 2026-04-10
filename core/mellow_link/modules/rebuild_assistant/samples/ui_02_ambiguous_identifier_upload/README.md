# ui_02_ambiguous_identifier_upload

목적:

- 애매한 식별자 유지 확인
- over-redaction 방지 확인

사용 방법:

- `/projects/create`에서 `README.md`를 제외한 나머지 파일을 업로드
- 권장 고객사명: `Ambiguous Lab`

예상 포인트:

- `data`, `mode`, `helperFlag` 같은 일반 변수명이 많음
- 고신뢰 구조 식별자는 제한적으로만 존재
- 결과가 전부 토큰화되거나 텅 비면 안 됨

