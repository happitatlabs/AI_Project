# Modernization Options

## AS-IS

- Legacy approval workflow and reporting logic are bundled in one service.
- Current project needs a recommendation with explicit comparison criteria.

## Option A

- Policy-centric modular service
- Pros: rule ownership is clearer, migration can be phased
- Cons: shared reporting contracts must be preserved carefully

## Option B

- Query/report split first
- Pros: reporting performance isolation is easier
- Cons: policy logic can remain duplicated during transition

## Comparison Criteria

- maintainability
- rule ownership
- migration risk
- reporting impact
