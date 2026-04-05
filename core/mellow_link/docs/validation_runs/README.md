# Real Project Validation Runs

이 디렉터리는 실제 프로젝트 validation 실행 결과를 보관한다.

역할:
- reviewer가 확인할 validation record 저장
- `structural_judgment`, `recommended_strategy`, `narrative_axis`, top evidence, Q&A smoke 결과를 프로젝트 단위로 기록
- contamination 사례는 아래 3구역으로 기록
  - `confirmed observation`
  - `root cause candidate`
  - `follow-up check`

source of truth 아님:
- 엔진 구조 기준 문서 아님
- canonical payload 계약 문서 아님
- detector/scoring 정책 기준 문서 아님

기준 문서:
- [refactoring_support_engine.md](/C:/Users/Hyein/ClaudeAI/AI_Project/refactoring_support_engine.md)
- [REFACTORING_SUPPORT_ENGINE_REAL_PROJECT_VALIDATION_TEMPLATE.md](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/REFACTORING_SUPPORT_ENGINE_REAL_PROJECT_VALIDATION_TEMPLATE.md)

운영 규칙:
1. validation record는 실제 프로젝트 실행 결과를 요약한 산출물로만 본다.
2. 구조 판단 수정이 필요하면 먼저 코드와 기준 문서를 고치고, 그 다음 validation record를 새로 생성한다.
3. generated record는 회귀 기준이 아니라 reviewer evidence다.
4. rerun이 있는 경우 stored result와 rerun 결과 차이는 별도 `*-rerun-diff.md` 문서로 남긴다.
5. `migration_consideration` contamination 사례는 아래 용어를 그대로 사용한다.
   - `wrapper wording contamination`
   - `synthetic migration trigger`
   - `asset-absent decision`
   - `domain-anchor spillover`
6. validation record에는 `synthetic_signal_detected`를 반드시 기록한다.
7. `synthetic_signal_detected`는 아래 순서로 기록한다.
   - `result.extensions.decision_governance`
   - 없으면 `decision_summary` 기준 inference
8. stored result와 rerun 결과가 다르면 diff 문서에서 아래 항목을 최소 비교한다.
   - `structural_judgment`
   - `recommended_strategy`
   - `top_decision_type`
   - `decision_count`
   - `migration_count`
9. `result.extensions.review_diff.markdown`이 있으면 validation record에 `Review Diff` 섹션으로 삽입한다.
10. screenshot 세트는 `REVIEW_DIFF_SCREENSHOT_SET_2026-04-05.md`를 기준으로 관리한다.
11. screenshot 검증도 `surface_mode -> access_profile -> capability` 정책을 따라야 한다.
    - internal: review_diff 검토 화면 허용
    - external: explanation 중심 화면만 허용
