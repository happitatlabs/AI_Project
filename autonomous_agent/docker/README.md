# Docker Execution Draft

이 문서는 `autonomous_agent`의 1차 검증용 Docker 실행 경로 초안이다.

## 목표

- 로컬 실행 경로는 그대로 유지
- Docker는 `pytest`, `inspect_storage.py`, `review_pending.py`, 보고서 경로 검증용으로만 사용
- 코드(`/app`)는 이미지 내부에 포함
- 호스트 워크스페이스는 `/workspace`로 read-only 마운트
- 런타임 산출물만 `runtime-data/`를 통해 write 허용

## 준비

```powershell
cd autonomous_agent
./scripts/run_docker_review.ps1
```

위 스크립트는 `runtime-data/` 하위 디렉토리와 최소 파일을 만든 뒤 `agent-review`를 실행한다.

## 주요 실행 예시

```powershell
docker compose build
docker compose run --rm agent-test
docker compose run --rm agent-review inspect_storage.py
docker compose run --rm agent-review review_pending.py list
docker compose run --rm agent-review review_pending.py show 0
docker compose run --rm agent-report
```

## 마운트 정책

- `/app`
  - 이미지 내부 코드
  - 컨테이너 rootfs는 read-only
- `/workspace`
  - 현재 프로젝트 bind mount
  - read-only
- `/app/reports`, `/app/archive`, `/app/history`, `/app/logs`
  - `./runtime-data/...`에서 write 허용
- `/app/generated_skills`
  - `./runtime-data/generated_skills`에서 write 허용
- `/app/agent_state.json`, `/app/pending_approvals.json`, `/app/agent.log`
  - `./runtime-data/...` 파일로 write 허용

## 주의

- 현재 Python 코드가 runtime 경로 환경변수를 적극적으로 소비하지는 않으므로, 1차 도입에서는 `/app` 하위 runtime 파일/디렉토리를 개별 마운트하는 방식으로 호환성을 유지한다.
- `review_pending.py approve/reject`는 `runtime-data/pending_approvals.json`에만 영향을 준다.
- daemon 상주 실행은 이 구성에 포함하지 않는다.
