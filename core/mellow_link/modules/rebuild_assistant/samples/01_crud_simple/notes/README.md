# Notes

이 디렉터리는 `01_crud_simple` 샘플의 사람 검토용 참고 문서를 보관한다.

- `human_review_result_sample.md`
  - 사람이 읽기 위한 결과 패키지 예시
  - 자동 회귀 기준이 아니다
  - 실제 regression anchor는 상위 경로의 `expected_assertions.yaml`을 사용한다

현재 보관된 human review 문서는 `CRUD 단순형` 정의보다 `validation-heavy` 결과에 가깝다.
따라서 canonical golden으로 승격하려면 실제 엔진 출력 기준 재측정이 필요하다.
