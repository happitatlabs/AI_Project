# 익명화/노출 검증용 UI 샘플 팩

이 문서는 `/modules/rebuild_assistant` 안내 화면에서 `/projects/create`로 이동한 뒤,
실제로 업로드해서 돌려볼 수 있는 샘플 팩을 정리한다.

중요:

- `/modules/rebuild_assistant` 자체는 raw 실행이 비활성화되어 있다.
- 실제 실행은 `/projects/create`에서 진행한다.
- 각 샘플 디렉터리에서 `README.md`를 제외한 파일을 업로드하면 된다.
- `goal.txt`는 프로젝트명 자동 채움용이다.
- `constraints.txt`는 제약 조건 자동 병합용이다.
- 고객사명은 UI에서 직접 입력해야 한다.

## 업로드 가능 샘플 팩

- `ui_01_normal_balanced_upload`
  - 정상 익명화, preview 노출, summary 생성 확인
- `ui_02_ambiguous_identifier_upload`
  - 애매한 식별자 유지와 over-redaction 방지 확인
- `ui_03_sensitive_signal_upload`
  - 민감 문자열 다수 포함 시 preview masking 안전성 확인
- `ui_04_event_split_upload`
  - 일반 실행 후 user/admin surface 분리 확인

## dev 전용 실패 fixture

- `ui_05_dev_failure_guard_mapping`
  - raw 업로드 UI만으로는 유도하기 어려운 validation fail 케이스
  - `POST /modules/rebuild_assistant/bundle-runs` 용 `bundle_run_payload.json` 포함
  - 현재 구현에서는 `safe_bundle.guard.contains_mapping=true` 로 validation fail을 유도한다.

## 권장 확인 포인트

### `ui_01_normal_balanced_upload`

- `anonymization_summary.applied=true`
- `validation_passed=true`
- preview 존재
- summary의 `asset_counts` 존재

### `ui_02_ambiguous_identifier_upload`

- over-redaction 없이 결과가 지나치게 텅 비지 않는지
- 일반 변수명/노트가 구조 판단에 과도하게 끌려가지 않는지

### `ui_03_sensitive_signal_upload`

- preview에 raw email/token/path/host/phone이 직접 남지 않는지
- user surface summary에 raw detail이 없는지

### `ui_04_event_split_upload`

- user run snapshot에는 `anonymization_summary`만 보이는지
- admin dev event stream에는 `debug_anonymization_report`가 보이는지

### `ui_05_dev_failure_guard_mapping`

- `validation.passed=false`
- `findings`에 `guard_contains_mapping`
- `source_previews=[]`

