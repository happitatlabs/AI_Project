Refactoring Support Engine policy values are loaded from typed Python objects in
`mellow_link.services.refactoring_support_engine.policies`.

Current Phase:
- deterministic in-repo defaults only
- no user-provided override
- no JSON or YAML loader
- detector/scoring policy freeze until Phase 3

Freeze Rule:
- do not change `DEFAULT_DETECTOR_POLICIES` before Phase 3
- do not change `DEFAULT_SCORING_POLICY` before Phase 3
- do not tune detector weight, base severity, default effort, multiplier, or bonus values before Phase 3

Extension point:
- keep `load_engine_policy_bundle()` as the single policy loader entry
- add project-type branching behind that loader when overrides are introduced
