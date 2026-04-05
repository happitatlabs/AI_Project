# Stored Result vs Latest Governance Rerun Diff

기준 문서: [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)  
project_id: `proj_e3733dcbad23`

## Snapshot

- before_run_id: `run_20260405_135828_065d4577`
- after_run_id: `run_20260405_140546_162ef17d`
- rerun_validation: [2026-04-05-proj_e3733dcbad23-validation-rerun.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/2026-04-05-proj_e3733dcbad23-validation-rerun.md)

## Core Judgment Diff

| 항목 | before | after | 판정 |
|---|---|---|---|
| structural_judgment | `observation_only` | `observation_only` | 유지 |
| top_decision_type | `none` | `none` | 유지 |
| decision_count | `0` | `0` | 유지 |
| synthetic_signal_detected | `true` | `true` | 유지 |
| review_diff persisted | `yes` | `yes` | 유지 |

## Interpretation

1. governance 가드 적용 이후 core judgment는 `observation_only`로 안정화되어 있다.
2. synthetic migration signal은 계속 감지되지만, 최종 decision surface에는 남지 않는다.
3. 이 케이스는 `goal wording contamination`이 final decision을 통과하지 못한다는 운영 증거로 사용한다.
