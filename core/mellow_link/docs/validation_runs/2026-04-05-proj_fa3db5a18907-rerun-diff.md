# Stored Result vs Latest Governance Rerun Diff

기준 문서: [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)  
project_id: `proj_fa3db5a18907`

## Snapshot

- before_run_id: `run_20260405_135756_b3fb8010`
- after_run_id: `run_20260405_140513_64f98851`
- rerun_validation: [2026-04-05-proj_fa3db5a18907-validation-rerun.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/2026-04-05-proj_fa3db5a18907-validation-rerun.md)

## Core Judgment Diff

| 항목 | stored result | governance rerun | 판정 |
|---|---|---|---|
| structural_judgment | `refactor` | `refactor` | 유지 |
| recommended_strategy | `리팩터링 우선` | `리팩터링 우선` | 유지 |
| top_decision_type | `refactor` | `refactor` | 유지 |
| decision_count | `5` | `5` | 유지 |
| migration_count (allowed) | `0` | `0` | 유지 |
| synthetic_signal_detected | `true` | `true` | 유지 |
| review_diff persisted | `yes` | `yes` | 유지 |

## Interpretation

1. 최신 governance 기준 재실행은 core judgment를 바꾸지 않았다.
2. `refactor` core judgment와 `리팩터링 우선` 전략은 그대로 유지됐다.
3. synthetic migration candidate는 rerun에서도 생성될 수 있지만, 최신 결과에서는 blocked decision으로만 남고 allowed decision에 포함되지 않는다.
4. 이번 diff는 governance 가드와 `review_diff` surface가 함께 secondary migration contamination을 노출하고 차단한다는 운영 증거로 사용한다.

## Validation Note

- after rerun `synthetic_signal_detected=True`
- after rerun `decision_governance`와 `review_diff`는 persisted result surface에 직접 노출된다.
- current conclusion: `secondary migration_consideration`은 최신 rerun 기준에서 product surface의 core layer에는 남지 않고, review diff/debug layer에서만 검토된다.
