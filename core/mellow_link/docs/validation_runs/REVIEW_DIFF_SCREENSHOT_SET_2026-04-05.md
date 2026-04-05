# Review Diff Screenshot Set

기준일: 2026-04-05  
생성 방식: live `http://127.0.0.1:8000` + Playwright actual browser capture  
생성 원칙: 수동 덮어쓰기 없음, 최신 rerun 결과만 사용

현재 캡처 기준:
- internal / external surface는 같은 canonical result를 사용한다.
- 차이는 `surface_mode -> access_profile -> capability` policy에 따른 노출 깊이만 있다.
- external screenshot에는 `review_diff`, blocked decision, governance trace 흔적이 남으면 안 된다.

## 고정 산출물 4종

1. internal 기본 화면  
프로젝트: `proj_e3733dcbad23`  
run_id: `run_20260405_162900_b4ded60d`  
목적: blocked `migration_consideration`와 governance 차단 결과 확인  
파일: [2026-04-05-proj_e3733dcbad23-internal-review-diff.png](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/screenshots/2026-04-05-proj_e3733dcbad23-internal-review-diff.png)

2. internal 구조 패턴 비교 펼친 화면  
프로젝트: `proj_fa3db5a18907`  
run_id: `run_20260405_162816_3138a680`  
목적: 실제 `구조 패턴 비교` 패널이 열리는 내부 검토 화면 확인  
파일: [2026-04-05-proj_fa3db5a18907-internal-structure-pattern-expanded.png](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/screenshots/2026-04-05-proj_fa3db5a18907-internal-structure-pattern-expanded.png)

3. external 기본 화면  
프로젝트: `proj_fa3db5a18907`  
run_id: `run_20260405_162816_3138a680`  
목적: Review Diff가 숨겨진 external surface 기본 상태 확인  
파일: [2026-04-05-proj_fa3db5a18907-external-review-diff.png](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/screenshots/2026-04-05-proj_fa3db5a18907-external-review-diff.png)

4. external explanation 중심 화면  
프로젝트: `proj_fa3db5a18907`  
run_id: `run_20260405_162816_3138a680`  
목적: explanation section 중심 외부 공유 화면 확인  
파일: [2026-04-05-proj_fa3db5a18907-external-explanation-centered.png](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/screenshots/2026-04-05-proj_fa3db5a18907-external-explanation-centered.png)

## 최근 갱신 시각

- `proj_e3733dcbad23` internal 기본: `2026-04-05 17:27:58`
- `proj_fa3db5a18907` internal 구조 비교 펼침: `2026-04-05 17:28:01`
- `proj_fa3db5a18907` external 기본: `2026-04-05 17:29:56`
- `proj_fa3db5a18907` external explanation 중심: `2026-04-05 17:29:57`

## 확인 포인트

- internal 기본 화면
  - sticky summary bar가 보인다
  - blocked migration 또는 governance 상태를 직접 읽을 수 있다
- internal 구조 비교 펼친 화면
  - `현재 구조 vs 권장 구조 비교`가 실제로 열려 있다
  - observed / expected_pattern evidence가 노출된다
- external 기본 화면
  - Review Diff 섹션이 없다
  - explanation 중심 카드만 보인다
- external explanation 중심 화면
  - 외부용 완성형 surface처럼 보여야 한다
  - 비어 있는 internal 화면처럼 보이면 안 된다

## 선택 기준

- `proj_e3733dcbad23`
  - blocked migration 사례를 가장 선명하게 보여준다
  - 최신 rerun에서도 `code_diff.available = false`이므로 `구조 패턴 비교 펼친 화면` 용도로는 부적합하다

- `proj_fa3db5a18907`
  - 정상 `refactor` 판단 + blocked migration 보조 사례를 함께 보여준다
  - 최신 rerun에서 `code_diff.available = true`가 확인되어 `구조 패턴 비교 펼친 화면` 용도로 적합하다
  - external explanation surface도 안정적으로 구성된다

## 저장 폴더

- [screenshots](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/docs/validation_runs/screenshots)
