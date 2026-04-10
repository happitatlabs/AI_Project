# ui_05_dev_failure_guard_mapping

목적:

- validation fail 시 preview 차단 동작 확인
- `guard_contains_mapping` finding/risk flag 확인

중요:

- 이 케이스는 `/projects/create` raw 업로드만으로 재현되지 않는다.
- 현재 구현 기준으로는 `safe_bundle.guard.contains_mapping=true` 같은 dev fixture 조작이 필요하다.
- 따라서 `bundle_run_payload.json`을 `POST /modules/rebuild_assistant/bundle-runs`에 보내서 확인한다.

예상 포인트:

- `validation.passed=false`
- `validation.findings[*].code = guard_contains_mapping`
- `source_previews=[]`
- run 자체는 완료됨

