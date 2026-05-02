# Type Surface Review Criteria v1

This document defines the first human review gate for external result surfaces.
It is not an engine contract and does not change canonical payloads. The goal is
to judge whether the same decision is expressed correctly for `document`,
`code`, and `mixed` input surfaces.

## Scope

- Applies to external result surfaces only.
- Internal surfaces may retain labels, detailed evidence, and diagnostic traces.
- Verdicts are `OK`, `WARN`, or `FAIL`.
- A single `FAIL` item makes the sample fail.
- `WARN` items do not fail the sample, but they must be recorded.

## Common Criteria

### OK Criteria

- The reviewer can identify what to inspect within 10 seconds.
- The reviewer can identify the next action within 30 seconds.
- The execution state is clear and uses one of the four standard labels.
- The wording matches the detected input type.
- No internal label, debug field, or raw governance metadata is exposed.
- The result remains evidence-based and does not overstate confidence.

### FAIL Criteria

- [COMMON-F01] The surface states or implies the wrong input type.
- [COMMON-F02] The execution state is not visible as `실행 착수 가능`, `조건 확인 후 실행`, `검증 후 적용`, or `실행 불가`.
- [COMMON-F03] The next action is missing or impossible to infer.
- [COMMON-F04] Internal labels, debug fields, or raw governance metadata are exposed.
- [COMMON-F05] The same sentence appears more than once in the same section.
- [COMMON-F06] The conclusion and execution plan contradict each other.
- [COMMON-F07] The result confirms execution while evidence is missing, conflicted, blocked, or review-required.

### WARN Criteria

- [COMMON-W01] The meaning is correct, but sentences are too long to scan quickly.
- [COMMON-W02] The core reason is present but not visible at a glance.
- [COMMON-W03] The action is directionally correct but too generic.
- [COMMON-W04] Verification points are present but not directly checkable.
- [COMMON-W05] Option differences are present but weak.
- [COMMON-W06] The state label is correct, but the surrounding tone is awkward or draft-like.

## Document Criteria

Use this section for PPT decks, reports, consulting documents, proposals, and overview materials.

### FAIL Criteria

- [DOCUMENT-F01] A consulting document is expressed mainly as code or SQL analysis.
- [DOCUMENT-F02] The `problem / options / conclusion / reason` flow is missing or broken.
- [DOCUMENT-F03] Detailed explanation appears before the conclusion and hides the main point.
- [DOCUMENT-F04] Internal labels such as `[상황 / 목적]`, `[문제 정의]`, or `[핵심 이유]` remain visible.
- [DOCUMENT-F05] The recommended option does not match the document purpose or stated scope.
- [DOCUMENT-F06] The surface makes a firm execution conclusion despite weak or missing source evidence.

### WARN Criteria

- [DOCUMENT-W01] The flow is correct, but paragraphs are too long.
- [DOCUMENT-W02] Option differences are not sharp enough.
- [DOCUMENT-W03] The core reason exceeds three short bullets or three short lines.
- [DOCUMENT-W04] Risks are abstract and do not name a concrete review point.
- [DOCUMENT-W05] The execution plan is more technical than the consulting document requires.
- [DOCUMENT-W06] The result is readable but still feels like an internal draft.

## Code Criteria

Use this section for SQL, Python, Java, API logic, operational rules, validation code, state transitions, and similar technical inputs.

### FAIL Criteria

- [CODE-F01] Code or SQL input is expressed only as a consulting document narrative.
- [CODE-F02] The `핵심 문제 / 영향 / 권장 조치 / 검증 포인트` structure is not visible.
- [CODE-F03] The affected code area, SQL condition, rule, or validation target is unclear.
- [CODE-F04] The recommended action cannot lead to an implementation or verification task.
- [CODE-F05] SQL or code terms are misinterpreted.
- [CODE-F06] The surface confirms refactoring without source evidence or validation basis.

### WARN Criteria

- [CODE-W01] The core problem is correct, but the impact is weak.
- [CODE-W02] The recommended action is too generic to implement.
- [CODE-W03] Verification points are not testable as unit, integration, SQL, or regression checks.
- [CODE-W04] It is unclear whether the main risk is performance, consistency, exception handling, access control, or state transition.
- [CODE-W05] Technical terms and consulting terms are mixed in a way that slows reading.
- [CODE-W06] The result names a fix but does not identify what evidence should confirm it.

## Mixed Criteria

Use this section when narrative document material and SQL, code, logs, or operational rules appear together.

### FAIL Criteria

- [MIXED-F01] Document explanation and code analysis are not separated.
- [MIXED-F02] The document purpose is preserved, but the code evidence is ignored.
- [MIXED-F03] The code evidence is preserved, but the document purpose disappears.
- [MIXED-F04] The execution plan is biased entirely toward either document work or code work.
- [MIXED-F05] The surface uses only `document_style` or only `technical_style` for clearly mixed input.
- [MIXED-F06] Code verification points are not connected to the document conclusion.

### WARN Criteria

- [MIXED-W01] Document and code blocks are separated, but the transition between them is weak.
- [MIXED-W02] The technical block is too long compared with the document summary.
- [MIXED-W03] The priority between document-level judgment and technical action is unclear.
- [MIXED-W04] Verification points exist, but it is unclear which conclusion they validate.
- [MIXED-W05] The execution flow breaks between document steps and code steps.
- [MIXED-W06] The result is correct but requires rereading to understand how document evidence and code evidence connect.

## Status Wording

External surfaces may use only the following status labels.

- `실행 착수 가능`
- `조건 확인 후 실행`
- `검증 후 적용`
- `실행 불가`

The labels mean:

- `실행 착수 가능`: evidence is sufficient and no blocking issue remains.
- `조건 확인 후 실행`: execution is reasonable only after explicit conditions pass.
- `검증 후 적용`: review, evidence gathering, or conflict resolution must happen before applying the option.
- `실행 불가`: execution must not be recommended until blockers are resolved.

## Review Report Template

```markdown
# Type Surface Review Report

## Sample
- sample_name:
- input_type_expected: document / code / mixed
- input_type_detected:
- surface_style:

## Verdict
- status: OK / WARN / FAIL
- reason:

## Checklist
### Common
- 상태 명확성:
- 다음 행동:
- 반복 문장:
- 내부 라벨 노출:
- 근거와 확신 수준:

### Type-specific
- 타입 적합성:
- 구조 적합성:
- 표현 적합성:
- 검증 가능성:

## Issues
| severity | category | finding | expected | suggested_fix |
| --- | --- | --- | --- | --- |

## Final Note
- keep:
- fix:
- defer:
```

## Review Use

- Start with common criteria.
- Apply the expected input type criteria next.
- Record every `FAIL`; one fail is enough to mark the sample as failed.
- Record `WARN` items separately, even when the final status is `OK`.
- Do not change engine logic from this review. File follow-up issues for wording, classification, or sample quality.
