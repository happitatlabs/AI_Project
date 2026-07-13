# Pilot DOCX test failure classification (2026-07-14)

## Scope

This note separates failures related to the customer-deliverable DOCX pilot from
pre-existing repository failures. The comparison baseline is `origin/main` at
merge commit `056f023` (PR #16).

## Results

| Category | Result | Disposition |
| --- | --- | --- |
| A. Pilot regression | The variable-length look-behind prevented DOCX rendering and two project archive tests from completing. | Fixed by using a fixed-width sentence boundary and covered by focused generation/archive tests. |
| B. Intentional output contract change | One surface test still expected the previous `컨설팅 개요` heading. | Updated to the fixed nine-section pilot contract, including the one-page summary, options, and provenance sections. |
| C. Pre-existing failure | The 14 remaining failures reproduce unchanged on `origin/main`. | Not changed in this PR. |
| D. Environment/dependency | A clean test environment did not install `python-docx`; the focused import path also requires `pydantic-settings`. | Added a focused pilot test requirements file that extends the repository runtime test requirements. |
| E. Out of scope | The 14 baseline failures concern the home-page copy, analysis-family narratives, and existing golden/promoted sample expectations. | Track separately; do not mix analysis-engine or UI baseline cleanup into the DOCX delivery PR. |

## Focused verification

Clean virtual environment:

```powershell
python -m pip install -r requirements-test-pilot.txt
python -m pytest -q tests/test_docx_polish_layer.py tests/test_project_result_archive.py tests/test_pilot_demo_samples.py tests/test_source_question_guard.py
```

Result: `22 passed`.

Expanded pilot regression selection:

```powershell
python -m pytest -q tests/test_docx_polish_layer.py tests/test_project_result_archive.py tests/test_pilot_demo_samples.py tests/test_source_question_guard.py tests/test_ppt_batch_regression.py tests/test_phase1_run_flow.py::test_project_result_docx_download tests/test_phase1_run_flow.py::test_project_result_docx_download_external_surface tests/test_phase3_explanation_and_qa.py::test_export_surfaces_follow_guard_precedence_like_explanation_surface
```

Result: `26 passed`.

## Full-suite comparison

Current branch:

```powershell
python -m pytest -q
```

Result: `14 failed, 920 passed, 4 skipped`.

Baseline comparison in a detached worktree at `origin/main`:

```powershell
python -m pytest -q tests/test_family_surface_templates.py tests/test_phase1_run_flow.py::test_home_prioritizes_project_entry tests/test_refactoring_support_expansion_sample_alignment.py tests/test_refactoring_support_golden_samples.py tests/test_refactoring_support_promoted_expansion_samples.py
```

Result: `14 failed, 4 passed`. The failing node IDs and assertions match the 14
remaining failures on the current branch.

### Remaining baseline failures

- 1 family surface template expectation
- 1 home-page copy expectation
- 1 low-intensity expansion sample narrative expectation
- 7 existing golden sample expectations
- 4 promoted expansion sample expectations

These failures should be resolved only after deciding whether each analysis
output change is intended and therefore requires a golden update, or is an
analysis-engine regression. That decision is independent of the DOCX delivery
contract.
