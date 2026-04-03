Refactoring Support Engine policy values are loaded from typed Python objects in
`mellow_link.services.refactoring_support_engine.policies`.

Current Phase:
- deterministic in-repo defaults only
- no user-provided override
- no JSON or YAML loader

Extension point:
- keep `load_engine_policy_bundle()` as the single policy loader entry
- add project-type branching behind that loader when overrides are introduced
