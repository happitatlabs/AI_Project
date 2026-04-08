# Refactoring Support Engine Golden Failure Triage

기준일: 2026-04-08  
대상: `core/mellow_link/tests/test_refactoring_support_golden_samples.py` 실패 5건  
목표: golden 갱신이 맞는지, engine 수정이 맞는지 샘플별로 판정한다.  

## 0. 판정 기준

- intent/evidence 분리 정책과 맞는가
- grounding/confidence 정책과 맞는가
- feature slice 규칙상 더 일관적인가
- 상품 문서 관점에서 더 설명 가능한가

판정 기준으로 사용한 사실:

- golden 기대값의 `design_options`는 테스트 코드에 human-readable 본문이 아니라 stable hash로만 저장되어 있다.
- 따라서 아래 `expected design_options summary`는 hash baseline, 샘플 문서, 현재 option family, hash drift 범위를 함께 보고 사람이 읽을 수 있게 복원한 요약이다.
- `d5fd84a Separate intent inputs from evidence in refactoring engine` 이후 `goal.txt / constraints.txt / scenario.md`는 intent channel로 분리되고, 구조 seed는 evidence 자산 기준으로만 잡는다.
- `457ea66 Lock refactoring support governance and polish output wording` 이후 selection reason 문구와 grounding-aware wording이 바뀌었다.

## 1. Sample-By-Sample Evidence Inventory

| sample name | intent files | SafeAnalysisBundle evidence files | analysis-visible structural assets | inventory note |
| --- | --- | --- | --- | --- |
| `00. rca_exception_case_01` | `goal.txt`, `constraints.txt` | `legacy.jsp`, `query.sql`, `schema.sql`, `service.java` | `legacy.jsp [ui]`, `query.sql [sql]`, `schema.sql [schema]`, `service.java [source]` | intent/evidence 분리가 명확하고 실제 구조 evidence가 충분하다. |
| `01. java_order_closure_case_01` | `goal.txt`, `constraints.txt` | `legacy.jsp`, `OrderCloseService.java`, `query.sql`, `schema.sql` | `legacy.jsp [ui]`, `OrderCloseService.java [source]`, `query.sql [sql]`, `schema.sql [schema]` | 구조 evidence는 충분하지만 fallback seed가 첫 UI 파일명에 끌린다. |
| `02. python_claim_adjustment_case_01` | `goal.txt`, `constraints.txt` | `claim_adjustment.html`, `legacy_app.py`, `query.sql`, `schema.sql` | `claim_adjustment.html [ui]`, `legacy_app.py [source]`, `query.sql [sql]`, `schema.sql [schema]` | evidence 안에 claim/approval/dept/amount 규칙이 모두 존재한다. |
| `04. amount_limit` | 없음 | `cs_expense_policy.cs`, `sql_order_limit.sql` | `cs_expense_policy.cs [source]`, `sql_order_limit.sql [sql]` | intent가 비어 있고 evidence만으로 샘플이 구성된다. |
| `01_success_full` | 없음 | `accounting_payload.json`, `legacy_context.txt` | `accounting_payload.json [json]` | SafeAnalysisBundle evidence는 2개지만 source/ui/sql/schema가 없어서 구조 seed용 structural evidence는 사실상 없다. |

## 2. Expected vs Actual Diff Summary

`expected design_options summary`는 human-readable baseline이 없는 항목에 한해 추정 요약임.

| sample name | intent files | evidence files | expected first_entry_point | actual first_entry_point | expected design_options summary | actual design_options summary | difference reason | judgment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `00. rca_exception_case_01` | `goal.txt`, `constraints.txt` | `legacy.jsp`, `query.sql`, `schema.sql`, `service.java` | `ui:LegacyPage#submit` | `ui:LegacyPage#submit` | workflow option family baseline. 현재와 같은 `승인 흐름 중심 / 단계 분리형 / 예외 승인 분리형` 구조로 보이며, old hash는 pre-polish wording capture다. | `옵션 A. 승인 흐름 중심 모듈형 구조` 중심. 실행계획 hash는 동일하고 selection reason만 governance wording으로 정리됐다. | 구조 anchor와 execution plan은 유지됐다. drift는 2026-04-08 wording lock 이후 `selection_reason` 문장만 바뀐 케이스다. | `update_golden` |
| `01. java_order_closure_case_01` | `goal.txt`, `constraints.txt` | `legacy.jsp`, `OrderCloseService.java`, `query.sql`, `schema.sql` | `usecase:이_jsp_java` | `usecase:jsp` | state-transition option family baseline. 현재와 같은 `상태 전이 중심 / 상태 검증 우선 / 화면 우선` 구조의 pre-polish wording capture로 보인다. | `옵션 A. 상태 전이 중심 모듈형 구조` 중심. design hash drift는 selection reason wording 영향이 크다. | intent contamination 제거는 맞지만, fallback seed가 첫 UI 파일명에서 `jsp`만 남겨 feature slice 명이 지나치게 빈약해졌다. evidence-consistent이긴 해도 상품 문서 관점에서는 `주문 마감`을 설명하지 못한다. | `fix_engine` |
| `02. python_claim_adjustment_case_01` | `goal.txt`, `constraints.txt` | `claim_adjustment.html`, `legacy_app.py`, `query.sql`, `schema.sql` | `usecase:이_python_flask` | `usecase:claim_adjustment_html` | old golden hash-only baseline. pre-separation 기준에서는 query-filter 쪽 설계/실행계획 capture였을 가능성이 높다. | `옵션 A. 권한 정책 중심 모듈형 구조` 중심. grounded rule도 `FRAUD 본사 심사`, `300만원 한도`, `CLAIM_AUDIT`, `B99 선승인`으로 access-control narrative에 직접 맞는다. | first entry point는 goal-derived에서 evidence-derived로 이동했다. design/execution도 access-control narrative로 정렬됐는데, 이는 현재 report purpose와 grounded rules, 2026-03-28 narrative 단일화 문서와 일치한다. | `update_golden` |
| `04. amount_limit` | 없음 | `cs_expense_policy.cs`, `sql_order_limit.sql` | `usecase:금액_한도형_샘플` | `usecase:cs_expense_policy` | amount-threshold option family baseline. 현재와 같은 `금액 한도 정책 중심 / 한도 기준 우선 / 처리 결과 우선` 구조의 pre-grounding-aware wording capture다. | `옵션 A. 금액 한도 정책 중심 모듈형 구조` 중심. `직접 확인된 구조 근거가 제한적이므로 ... 우선 검토안` 문구가 추가됐다. | goal title 기반 seed가 source evidence 기반 seed로 바뀌었다. design/recommended drift는 insufficient-grounding 정책에 맞춘 wording 보강이다. execution hash는 유지됐다. | `update_golden` |
| `01_success_full` | 없음 | `accounting_payload.json`, `legacy_context.txt` | `usecase:전산회계_mvp_기능을` | `usecase:legacy_flow` | 회계 전용 option family baseline. current hash와 동일하다. | `옵션 A. 현재 회계 방식 유지 및 입력 통제 강화` 중심. design/execution/recommended hash 모두 기대값과 동일하다. | source/ui/sql/schema evidence가 없으므로 구조 seed를 goal에서 가져오지 않는 현재 동작이 맞다. `legacy_flow`는 설명성이 낮지만 허위 structural anchor를 만들지 않는다는 점에서 governance에 부합한다. | `update_golden` |

## 3. Regression 여부 판정

| sample name | regression 여부 | 근거 |
| --- | --- | --- |
| `00. rca_exception_case_01` | no | core judgment, first entry point, execution plan이 유지되고 wording만 바뀌었다. |
| `01. java_order_closure_case_01` | yes | intent contamination 제거 자체는 맞지만 `usecase:jsp`는 feature slice anchor로 지나치게 빈약하다. evidence-first 정책을 지키면서도 더 설명 가능한 seed를 선택해야 한다. |
| `02. python_claim_adjustment_case_01` | no | access-control narrative 정렬이 현재 grounded rule과 report purpose에 더 잘 맞는다. old golden이 현재 정책보다 뒤처진 상태로 보인다. |
| `04. amount_limit` | no | evidence-first seed + limited-grounding wording 강화로 보는 편이 타당하다. |
| `01_success_full` | no | goal-driven structural anchor를 제거한 것이 오히려 governance 준수다. |

## 4. Golden Update가 맞는 항목

| sample name | 이유 |
| --- | --- |
| `00. rca_exception_case_01` | selection reason wording drift만 존재하고 deterministic core는 유지됐다. |
| `02. python_claim_adjustment_case_01` | intent-derived seed와 old narrative baseline이 남아 있는 쪽이 더 부정확하다. current actual이 evidence/grounding/doc narrative에 더 잘 맞는다. |
| `04. amount_limit` | evidence-first seed와 insufficient-grounding wording이 현재 정책과 일치한다. |
| `01_success_full` | structural evidence 부재 상태에서 goal-derived entry point를 유지하면 intent contamination이 된다. |

## 5. Engine Fix가 맞는 항목

| sample name | 이유 | 권장 수정 방향 |
| --- | --- | --- |
| `01. java_order_closure_case_01` | `usecase:jsp`는 evidence-derived이지만 feature slice 이름으로는 설명력이 너무 낮다. 현재 evidence 안에는 `OrderCloseService.java`, `status`, `close` 규칙이 존재하므로 더 좋은 seed 후보가 있다. | fallback usecase seed에서 `legacy`, `jsp`, `html`, `java`, `py` 같은 generic file token은 제거하고, 첫 asset 순서 대신 source/service/domain token 또는 grounded rule concept를 우선 선택한다. |

## 6. Needs Review

현재 단계에서 별도 `needs_review`로 남길 항목은 없다.  
다만 `02. python_claim_adjustment_case_01`의 `claim_adjustment_html`처럼 file-extension 토큰이 anchor에 남는 현상은 후속 품질 개선 후보로 볼 수 있다.

## 7. 최종 결론

- golden drift로 보는 항목: 4건
  - `00. rca_exception_case_01`
  - `02. python_claim_adjustment_case_01`
  - `04. amount_limit`
  - `01_success_full`
- engine regression으로 보는 항목: 1건
  - `01. java_order_closure_case_01`

따라서 다음 작업 순서는 아래가 맞다.

1. `01. java_order_closure_case_01`의 fallback `first_entry_point` naming heuristic를 먼저 고친다.
2. 그 이후 남은 4건은 current policy 기준으로 golden을 갱신한다.
3. 마지막으로 golden 5건 전체와 promoted expansion sample을 다시 회귀 실행한다.
