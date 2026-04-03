# Golden Samples Expansion Pack

이 압축 파일은 `refactoring_support_engine`의 골든 샘플 확장을 위한 시작 패키지입니다.

구성 목적:
- Phase 3 전 운영 안정화용 샘플 세트 확장
- 구조/진단/판단/계획/AI narrative on-off 회귀 검증용 기준 샘플 확보
- 샘플별 입력/기대결과/검증 포인트를 일정한 형식으로 관리

권장 샘플 축:
1. CRUD 단순형
2. 권한 + 승인 흐름형
3. 상태 전이 복잡형
4. DB-heavy / query-filter 중심형
5. 레거시 뒤엉킴 구조형

## 권장 사용 순서
1. `samples/*/scenario.md`를 기준으로 실제 입력 자산을 채웁니다.
2. `input_manifest.json`에 자산 목록과 의도를 기록합니다.
3. 분석 실행 후 `expected_assertions.yaml`을 실제 기대값으로 채웁니다.
4. `templates/test_refactoring_support_golden_sample_case.py`를 참고해 테스트에 편입합니다.
5. AI narrative on/off 비교 검증도 함께 고정합니다.

## 폴더 구조
- `samples/`: 샘플별 개별 폴더
- `templates/`: 새 샘플 추가 시 복제할 공통 템플릿
- `ci/`: 검증 체크리스트 및 CI 반영 메모

## 주의
- 이 패키지는 구조 템플릿과 검증 뼈대를 제공합니다.
- 실제 golden expected 값은 현재 엔진 출력 기준으로 채워야 합니다.
- canonical 비교 대상은 narrative가 아니라 deterministic core입니다.
