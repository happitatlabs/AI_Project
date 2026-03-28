# python_claim_adjustment_case_01

Python/Flask 기반 보험 청구 조정 기능의 레거시 샘플이다.

## 포함 파일

- `goal.txt`
- `constraints.txt`
- `legacy_app.py`
- `claim_adjustment.html`
- `query.sql`
- `schema.sql`

## 샘플 의도

이 샘플은 "화면, Python 서비스, SQL에 업무 규칙이 분산된 청구 조정 기능"을 가정한다.

포인트:

- Flask route 안에 권한, 상태, 금액 제한 규칙이 섞여 있음
- HTML 템플릿에 승인 가능 조건이 중복 노출됨
- SQL 조건에 부서/상태/긴급건 예외가 같이 들어 있음
- 단일 화면이지만 숨은 승인 규칙과 예외 처리 규칙이 많음

## 추천 입력 방식

1. `goal.txt` 내용을 프로젝트 목적에 사용
2. `legacy_app.py`와 `claim_adjustment.html` 업로드
3. `schema.sql`, `query.sql` 업로드
4. `constraints.txt`를 제약 조건에 입력
