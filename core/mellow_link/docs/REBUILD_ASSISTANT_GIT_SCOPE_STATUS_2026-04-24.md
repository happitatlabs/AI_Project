# Rebuild Assistant Git Scope Status (2026-04-24)

## Purpose

This document records which work on `codex/judgment-board-ui` has already been pushed, which work remains local only, and which artifacts should not be pushed.

## Branch Status

- Branch: `codex/judgment-board-ui`
- Remote branch: `origin/codex/judgment-board-ui`
- Latest pushed commit: `2dcca79` `Add analysis context linkage to rebuild results`

## Already Pushed

The following bundles are already pushed to `origin/codex/judgment-board-ui`.

1. `bb1fa01` `Rework project result judgment board UI`
   - Judgment board UI in `core/mellow_link/static/project_result.html`

2. `823a87b` `Ignore ppt judgment analysis outputs`
   - Ignore `outputs/ppt_judgment_analysis/`

3. `e87303c` `Archive obsidian and legacy pipelines`
   - Archive move for `obsidian/` and `pipelines/`

4. `9eff24d` `Introduce analysis context core bundle`
   - `AnalysisContextBundle` schema
   - analysis context builder
   - `analysis_contexts` DB table
   - `InputAssembler` context-first path

5. `fda53a0` `Persist analysis context through project runs`
   - project create/re-run flow stores analysis context
   - wrapped run receives `context_id` and `input_fingerprint`

6. `2dcca79` `Add analysis context linkage to rebuild results`
   - result top-level linkage
   - `appendix.context_linkage`
   - `canonical_payload.appendix.context_linkage`
   - evidence degradation policy for unsupported confirmed claims
   - focused tests in `core/mellow_link/tests/test_analysis_context_bundle.py`

## Local Only: Defer and Split Before Push

The following groups are still local-only and should be pushed only after being split into small, reviewable commits.

### 1. Narrative / Presentation Expansion

- `core/mellow_link/services/refactoring_support_engine/narrative_augmentation.py`
- `core/mellow_link/services/refactoring_support_engine/template_support.py`
- `core/mellow_link/services/refactoring_support_engine/explanation_presenter.py`
- `core/mellow_link/services/doc_service.py`
- `core/mellow_link/services/refactoring_support_engine/narrative_fallback.py`
- `core/mellow_link/services/refactoring_support_engine/result_question_answering.py`
- `core/mellow_link/static/projects_create.html`
- `core/mellow_link/static/user_console.html`

### 2. Core Engine Changes Not Yet Split Cleanly

These files already have partially pushed work. Remaining local diffs must be reviewed and split before any further push.

- `core/mellow_link/modules/rebuild_assistant/runner.py`
- `core/mellow_link/modules/rebuild_assistant/schemas.py`
- `core/mellow_link/modules/rebuild_assistant/service.py`
- `core/mellow_link/services/refactoring_support_engine/result_packager.py`
- `core/mellow_link/routers/projects.py`
- `core/mellow_link/services/__init__.py`
- `core/mellow_link/services/refactoring_support_engine/decision_engine.py`
- `core/mellow_link/services/refactoring_support_engine/diagnosis_engine.py`
- `core/mellow_link/services/refactoring_support_engine/judgment_synthesizer.py`

### 3. Postprocess / Consulting Output Layer

- `core/mellow_link/modules/rebuild_assistant/postprocess/__init__.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/schemas.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/service.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_contract.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/consulting_deck.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/information_separation.py`
- `core/mellow_link/modules/rebuild_assistant/postprocess/slide_schema.py`

### 4. Provider / Family Classification Extensions

- `core/mellow_link/app_state.py`
- `core/mellow_link/config/settings.py`
- `core/mellow_link/main.py`
- `core/mellow_link/services/azure_openai_service.py`
- `core/mellow_link/services/openai_narrative_service.py`
- `core/mellow_link/services/project_results/`
- `core/mellow_link/services/refactoring_support_engine/family_classifier.py`

### 5. Tests and Golden Samples

These should be pushed only after the corresponding production code bundle is fixed and reviewed.

- `core/mellow_link/modules/rebuild_assistant/samples/**`
- `core/mellow_link/tests/refactoring_support_golden_samples.py`
- `core/mellow_link/tests/test_decision_governance.py`
- `core/mellow_link/tests/test_module_registry_and_runs.py`
- `core/mellow_link/tests/test_phase1_run_flow.py`
- `core/mellow_link/tests/test_phase3_explanation_and_qa.py`
- `core/mellow_link/tests/test_rebuild_assistant_integration.py`
- `core/mellow_link/tests/test_refactoring_support_doc_contract.py`
- `core/mellow_link/tests/test_refactoring_support_expansion_sample_alignment.py`
- `core/mellow_link/tests/test_refactoring_support_golden_samples.py`
- `core/mellow_link/tests/test_review_diff.py`
- `core/mellow_link/tests/family_classifier_golden_samples.py`
- `core/mellow_link/tests/test_azure_openai_service.py`
- `core/mellow_link/tests/test_consulting_contract_and_deck.py`
- `core/mellow_link/tests/test_family_classifier.py`
- `core/mellow_link/tests/test_family_surface_templates.py`
- `core/mellow_link/tests/test_fx_fifo_domain_guard.py`
- `core/mellow_link/tests/test_openai_narrative_service.py`
- `core/mellow_link/tests/test_operational_source_domain_guard.py`
- `core/mellow_link/tests/test_rebuild_assistant_narrative_pipeline.py`
- `core/mellow_link/tests/test_slide_schema_renderer.py`

### 6. Docs and Reference Notes

Documentation can be pushed later, but it should not be mixed into code-splitting commits.

- `README.md`
- `core/mellow_link/docs/README.md`
- `core/mellow_link/docs/REBUILD_ASSISTANT_POLISH_LAYER_CONTRACT_2026-03-29.md`
- `core/mellow_link/docs/MELLOW_LINK_BEGINNER_USER_GUIDE_KO.md`
- `core/mellow_link/docs/OPERATIONAL_SOURCE_GOLDEN_SAMPLE_PLAN_2026-04-19.md`
- `refactoring_support_engine.md`

### 7. Package Marker Deletions: Hold Until Confirmed

Do not push these deletions unless package-layout intent is confirmed.

- `mellow_chat_runtime/__init__.py`
- `mellow_link/__init__.py`

## Local Only: Do Not Push

These are generated, temporary, runtime, or archival artifacts. They should stay out of Git pushes.

### Runtime / Generated Data

- `_archive/artifacts/`
- `_isolation/`
- `core/autonomous_agent/runtime-data/review_decisions/*.json`
- `core/autonomous_agent/pending_approvals.json`
- `core/diff_numstat.txt`

### Experiments / Temporary Comparison

- `experiments/consulting_flow_compare.py`

## Working Rules

1. Do not use `git add .` in this worktree.
2. Stage only one logical bundle at a time.
3. Files with already-pushed partial changes must be split with index-only staging when needed.
4. Docs, samples, and generated artifacts must not be mixed with core pipeline commits.
5. If a file belongs to `Local Only: Do Not Push`, keep it untracked or ignored unless there is an explicit reason to version it.

## Update Rule

When another bundle is pushed, append the commit here and move the corresponding files out of the `Local Only` sections.
