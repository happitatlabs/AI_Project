# Mellow Agent — v0.1

> **로컬 LLM 기반 자율 운영 에이전트 (분석 → 제안 → 실행 → 기록 자동화)** — Ollama(qwen3.5:9b)를 사용하여 워크스페이스를 분석하고, 파일 정리·보고서 생성 등 반복 운영 작업을 자동화합니다.

---

## 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [디렉터리 구조](#디렉터리-구조)
3. [빠른 시작](#빠른-시작)
4. [핵심 컴포넌트](#핵심-컴포넌트)
5. [workspace_reporter 상세](#workspace_reporter-상세)
6. [pending 승인 흐름](#pending-승인-흐름)
7. [설정 파일](#설정-파일)
8. [테스트](#테스트)
9. [Docker 검증 상자](#docker-검증-상자)
10. [v0.1 기준선 정보](#v01-기준선-정보)

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────┐
│                   Mellow Agent                      │
│                                                     │
│  run_agent.py / run_daemon.py                       │
│       │                                             │
│       ▼                                             │
│  agent/loop.py  ──→  agent/planner.py               │
│       │                    │                        │
│       │              LLM (Ollama) or rules fallback │
│       ▼                                             │
│  agent/skill_executor.py                            │
│       │                                             │
│       ├─ scan_workspace  →  LLM 분석 + 제안 생성    │
│       └─ write_report    →  보고서 파일 생성         │
│                │                                    │
│                ├─ [높음] 제안 → 자동 실행            │
│                ├─ [중간] 제안 → pending_approvals   │
│                └─ [낮음] 제안 → 기록만              │
│                                                     │
│  review_pending.py  ←  운영자 CLI 승인/거절         │
└─────────────────────────────────────────────────────┘
```

### 실행 정책 (위험도 기반)

| 우선순위 | skill risk | 처리 방식 |
|---------|-----------|----------|
| `[높음]` | `safe` | 즉시 자동 실행 ← **안전한 작업** |
| `[높음]` | `approval` | `pending_approvals.json` 저장 ← **시스템 변경 가능성 있는 작업** |
| `[중간]` | (모두) | `pending_approvals.json` 저장 ← **시스템 변경 가능성 있는 작업** |
| `[낮음]` | (모두) | 로그 기록만 |

---

## 디렉터리 구조

```
autonomous_agent/
├── agent/                    # 핵심 에이전트 모듈
│   ├── daemon.py             # 데몬 프로세스 관리
│   ├── evaluator.py          # 사이클 결과 평가
│   ├── executor.py           # 파일 시스템 액션 실행
│   ├── llm_adapter.py        # Ollama LLM 연동 (rules fallback 포함)
│   ├── loop.py               # 메인 에이전트 루프
│   ├── maintenance.py        # 로그 정리·아카이브
│   ├── memory.py             # 상태/이력 저장 구조 관리
│   ├── planner.py            # LLM 기반 계획 수립
│   ├── skill_executor.py     # 스킬 실행 엔진 (제안→액션 포함)
│   └── skill_loader.py       # 스킬 파일 로더
│
├── skills/                   # 스킬 정의 디렉터리
│   ├── workspace_reporter/   # 워크스페이스 분석·정리 스킬
│   ├── code_reviewer/        # 코드 리뷰 스킬
│   └── file_classifier/      # 파일 분류 스킬
│
├── logs/                     # 실행 로그 및 운영 로그
├── reports/                  # 생성된 보고서 파일
├── history/
│   └── history_current.jsonl # append-only 사이클 이력
├── archive/
│   ├── memory/               # memory snapshot / legacy backup
│   └── reports/              # retention으로 이동된 보고서
├── generated_skills/         # 자동 생성 스킬 초안/산출물
│
├── config.json               # 에이전트 설정 (LLM, 데몬, 유지보수)
├── agent_goal.md             # 에이전트 목표 정의
├── agent_state.json          # 작은 현재 상태 저장
├── agent.log                 # 활성 실행 로그 (자동 이동 대상 제외)
├── pending_approvals.json    # 승인 대기 액션 목록
├── self_artifacts.json       # self-artifact 판정 규칙
├── inspect_storage.py        # 저장 구조 / risk / gate 상태 조회 CLI
│
├── run_agent.py              # 단발 실행 진입점
├── run_daemon.py             # 데몬 모드 진입점
├── run_maintenance.py        # 유지보수 작업 수동 실행
├── review_pending.py         # pending 승인/거절 CLI
│
├── test_pending_approval.py  # pending 흐름 자동 테스트 (T1~T6)
├── ops_checklist.md          # 수동 운영 테스트 체크리스트
└── README.md                 # 이 문서
```

### 현재 메모리 저장 구조

- `agent_state.json`
  - 현재 사이클, recent_actions, recent_scores, trend 등 작은 현재 상태만 저장
- `history/history_current.jsonl`
  - 1행 1이벤트 append-only 이력
- `archive/memory/`
  - history 회전 스냅샷과 legacy backup 저장

이 구조는 단일 대형 JSON 누적 대신, 작은 state + append 전용 history 로 장기 운영 안정성을 높이는 목적이다.

---

## 빠른 시작

### 요구 사항

- Python 3.10+
- [Ollama](https://ollama.ai) 설치 및 실행
- `qwen3.5:9b` 모델 다운로드: `ollama pull qwen3.5:9b`

### 단발 실행

```bash
cd autonomous_agent

# 1회 테스트 실행 (처음 시작할 때 권장)
python run_agent.py --cycles 1

# 기본 실행 (config.json의 max_cycles 적용)
python run_agent.py
```

### 데몬 모드 (5분 간격 자동 실행)

```bash
python run_daemon.py
```

### Windows 작업 스케줄러 등록

```bat
setup_windows_task.bat
```

### LLM 연결 확인

```bash
python test_llm.py
```

---

## 핵심 컴포넌트

### `agent/llm_adapter.py`

Ollama REST API(`http://localhost:11434/api/chat`)와 통신합니다. LLM 응답 실패 시 `fallback_to_rules: true` 설정에 따라 규칙 기반 분석으로 자동 전환됩니다.

### `agent/planner.py`

LLM에게 현재 메모리·목표·워크스페이스 상태를 컨텍스트로 제공하고, 다음 실행할 스킬과 파라미터를 계획합니다.

### `agent/skill_executor.py`

스킬의 각 step을 순서대로 실행합니다. `workspace_reporter`의 경우 다음 파이프라인을 처리합니다:

```
scan_workspace → LLM/rules 분석 → 제안 생성
write_report   → 보고서 빌드 → 제안 실행 → 결과 포함 → 단일 파일 쓰기
```

### `agent/executor.py`

실제 파일 시스템 조작을 담당합니다 (디렉터리 생성, 파일 이동 등).

---

## workspace_reporter 상세

### 보고서 구조

생성된 보고서 파일(`workspace_reporter_YYYYMMDD_HHMMSS.md`)은 다음 구조를 가집니다:

```markdown
# Workspace Report — YYYY-MM-DD HH:MM:SS

> ⚠ 이 보고서는 **실행 전 스냅샷 기준**입니다
>   — 실제 적용 내역은 맨 아래 '후속 실행 결과' 섹션을 확인하세요.

## 개요
... (워크스페이스 상태 분석)

## 제안 사항
- **[높음]** logs/ 디렉터리로 로그 파일 정리
- **[중간]** reports/ 디렉터리로 보고서 이동
- **[낮음]** README 업데이트 권장

---

## 후속 실행 결과

> 실행 시각: 2026-03-20 21:12:34 | 자동실행 2건 · 승인대기 1건 · 기록 1건

### ✅ 자동 실행 (2건)
- [성공] logs/ 이동 적용 — `agent_trace.jsonl` 외 2개
- [성공] reports/ 보고서 정리 — `report_20260320_*.md` 외 4개

### ⏳ 승인 대기 (1건)
- [대기] config/ 설정 파일 통합 — config.yaml 이동 제안

### 📋 기록 (1건)
- [기록] README 업데이트 권장 — 현재 README.md 내용이 오래됨
```

### 자동 실행 대상 액션

| op | 조건 | 설명 |
|----|------|------|
| `mkdir_and_move` (logs) | `.log`, `.jsonl` 파일 존재 | `logs/`로 이동 (`agent.log` 제외) |
| `mkdir_and_move` (reports) | 자동 보고서 패턴 파일 존재 | `reports/`로 이동 |
| `mkdir_and_move` (config) | `.yaml`, `.ini` 파일 존재 | `config/`로 이동 (`config.json` 제외) |
| `mkdir_only` (docs) | docs 디렉터리 없을 때 | `docs/` 디렉터리 생성 |
| `create_gitignore` | .gitignore 없을 때 | `.gitignore` 생성 |
| `delete_files` | 불필요 임시 파일 | 파일 삭제 (별도 확인 필요) |

### 보호 대상 파일

다음 파일은 어떤 상황에서도 자동 이동/삭제되지 않습니다:

- `agent.log` — 활성 실행 로그
- `config.json` — 에이전트 핵심 설정

---

## pending 승인 흐름

`[중간]` 우선순위 제안은 `pending_approvals.json`에 저장되고, 운영자가 직접 승인 또는 거절해야 합니다.

### CLI 사용법

```bash
# 대기 목록 확인
python review_pending.py
python review_pending.py list

# 상세 내용 확인
python review_pending.py show 0

# 개별 승인/거절
python review_pending.py approve 0
python review_pending.py reject 1

# 전체 일괄 처리
python review_pending.py approve all
python review_pending.py reject all
```

### `pending_approvals.json` 형식

```json
[
  {
    "status": "pending",
    "priority": "중간",
    "suggestion": "config/ 디렉터리로 설정 파일을 통합하세요",
    "action": {
      "op": "mkdir_and_move",
      "target_dir": "config",
      "file_filter": "config"
    },
    "requested_at": "2026-03-20T12:34:56.789012+00:00"
  }
]
```

**`status` 값**: `pending` → `approved` | `rejected`

데몬은 다음 사이클에 `approved` 항목을 감지하여 실행합니다.

---

## 설정 파일

`config.json`의 주요 항목:

```json
{
  "llm": {
    "provider": "ollama",
    "base_url": "http://localhost:11434",
    "model": "qwen3.5:9b",
    "timeout": 60,
    "fallback_to_rules": true
  },
  "agent": {
    "max_cycles": 5,
    "cycle_delay": 0.5,
    "workspace": ".",
    "memory_file": "agent_memory.json",
    "goal_file": "agent_goal.md"
  },
  "logging": {
    "level": "INFO",
    "log_file": "agent.log"
  },
  "daemon": {
    "interval_seconds": 300,
    "max_restart_attempts": 5,
    "restart_delay_seconds": 30,
    "health_check_interval_seconds": 60,
    "pid_file": "agent.pid",
    "dangerous_action_types": ["delete", "external_send"],
    "approval_file": "pending_approvals.json",
    "approval_timeout_seconds": 120
  },
  "maintenance": {
    "log_dir": "logs",
    "archive_dir": "archive",
    "log_retention_days": 7,
    "skills_archive_days": 30,
    "memory_max_history": 100,
    "compress_old_logs": true,
    "auto_run_after_cycles": 50
  }
}
```

- `fallback_to_rules`: `true`이면 LLM 오류 시 규칙 기반 분석으로 자동 전환
- `timeout`: LLM 호출 제한 시간(초)
- `workspace`: 기본 분석 대상 경로
- `memory_file`: 설정상 legacy 이름이 남아 있지만, 실제 저장 구조는 `agent_state.json + history/history_current.jsonl + archive/memory/`를 사용
- `log_file`: 활성 실행 로그 파일
- `interval_seconds`: 데몬 실행 주기(기본 5분)
- `approval_file`: 승인 대기 파일 경로
- `dangerous_action_types`: 이 op 유형은 항상 승인 필요
- `log_dir` / `archive_dir`: 유지보수 대상 디렉토리

---

## 테스트

### 핵심 자동 테스트

```bash
pytest -q test_reports_and_metrics.py test_recent_actions_alignment.py test_memory_storage.py
```

현재 기준 핵심 회귀 테스트 범위:

- self-artifact / risk snapshot / delta / action signal
- operational signal / gate / approval payload
- inspect / review_pending / report summary 출력
- workspace_reporter / report_only / cluster-aware summary

현재 통과 상태:

- `130 passed`

### 보조 자동 테스트 (pending 흐름)

```bash
python test_pending_approval.py
```

| 테스트 | 내용 |
|--------|------|
| T1 | workspace_reporter 실행 → pending_approvals.json 기록 확인 |
| T2 | `approve <번호>` → `status: approved` 확인 |
| T3 | `reject <번호>` → `status: rejected` 확인 |
| T4 | 이미 처리된 항목 재처리 방지 확인 |
| T5 | 파일 없는 상태에서 `list` 오류 없이 동작 확인 |
| T6 | `approve all` 전체 일괄 승인 확인 |

### 수동 운영 테스트

`ops_checklist.md` 참조 — 3~5 사이클 순서로 진행하는 수동 체크리스트입니다.

### Docker 검증 테스트

Docker는 운영 엔진이 아니라 **검증 상자**로만 사용합니다.

```powershell
docker compose run --rm agent-review
docker compose run --rm agent-review review_pending.py list
docker compose run --rm agent-test
docker compose run --rm agent-report
```

현재 검증 결과:

- `agent-review` 성공
- `review_pending.py list` 성공
- `agent-test` → `130 passed`
- `agent-report` → `3 passed, 88 deselected`

---

## Docker 검증 상자

이 Docker 구성은 운영 본체가 아니라 **검증 상자(validation sandbox)** 용도입니다.

- 목적:
  - 기존 CLI/출력 계약 재현
  - `/app` 고정 코드 실행
  - `/workspace` read-only 관찰
  - `/runtime-data` writable 분리
  - 단계별 검증 가능성 확보
- 범위:
  - `pytest`
  - `inspect_storage.py`
  - `review_pending.py`
  - `workspace_reporter`
  - `report_only`
- 제외:
  - daemon 상주 운영
  - 자동 자율 실행
  - self-updating / self-modifying
  - production service 설계

### 디렉터리 경계

- `/app`
  - 이미지 내부 고정 코드
- `/workspace`
  - 호스트 폴더 bind mount
  - read-only
- `/runtime-data`
  - state / approvals / reports / history / logs / generated_skills 저장용 writable 경계

현재 compose는 코드 수정 없이 호환되도록 `/runtime-data` 하위 일부를 `/app`의 runtime 경로로 개별 mount 합니다.

### 실행 계약 문서

- proposal / staging sidecar 구조
- apply state machine
- apply 금지 조건
- actual apply 미구현 이유

위 내용은 전용 계약 문서에 고정되어 있습니다.

- [docs/apply_executor_contract.md](docs/apply_executor_contract.md)
- Operating modes와 gate 재사용 규칙은 [docs/OPERATING_MODES.md](docs/OPERATING_MODES.md)에 고정되어 있습니다.
- Generated skill 수동 승격 검토 기준은 [docs/GENERATED_SKILL_PROMOTION_CRITERIA.md](docs/GENERATED_SKILL_PROMOTION_CRITERIA.md)에 고정되어 있습니다.
- Generated skill 수동 승격 절차는 [docs/GENERATED_SKILL_PROMOTION_PROCEDURE.md](docs/GENERATED_SKILL_PROMOTION_PROCEDURE.md)에 고정되어 있습니다.
- Generated skill 수동 변환 실행 절차는 [docs/GENERATED_SKILL_MANUAL_TRANSFORM_EXECUTION.md](docs/GENERATED_SKILL_MANUAL_TRANSFORM_EXECUTION.md)에 고정되어 있습니다.
- Generated skill checklist / rollback record는 `runtime-data/generated_skill_reviews/` 아래 별도 artifact로 기록됩니다.
- Local reviewer dashboard는 review / approval / checklist / rollback record를 로컬 UI에서 읽고 쓸 수 있습니다: `python local_reviewer_dashboard.py`

### 준비

```powershell
cd autonomous_agent
docker compose build
```

runtime-data 초기화와 단계별 검증:

```powershell
.\scripts\verify_docker_review.ps1
```

report 경로까지 함께 확인:

```powershell
.\scripts\verify_docker_review.ps1 -CheckReport
```

### 개별 실행 예시

```powershell
docker compose run --rm agent-review
docker compose run --rm agent-review review_pending.py list
docker compose run --rm agent-test
docker compose run --rm agent-report
```

### 현재 검증 결과

- `docker compose run --rm agent-review` → 성공
- `docker compose run --rm agent-review review_pending.py list` → 성공
- `docker compose run --rm agent-test` → `130 passed`
- `docker compose run --rm agent-report` → `3 passed, 88 deselected`

### 주의

- `agent-test`, `agent-report`는 `-p no:cacheprovider`로 pytest cache write를 비활성화합니다.
- `runtime-data` 초기 파일은 빈 파일보다 유효 JSON이 안전합니다.
  - `agent_state.json` → `{}`
  - `pending_approvals.json` → `[]`
- baseline이 없으면 `inspect_storage.py`의 `baseline_status`는 `missing`으로 표시됩니다.
- baseline은 `python inspect_storage.py --write-baseline`으로 현재 검증된 상태를 저장해 고정할 수 있습니다.
- 현재 risk delta는 **content change가 아니라 `path + severity` 기준 비교**입니다.
  - 즉, 동일한 high-risk 파일의 **내용만 변경**된 경우에는 `high_risk_delta`와 `new_high_risk_paths`가 변하지 않을 수 있습니다.
- 현재 단계에서는 로컬 실행 방식과 Docker 검증 경로를 **병행 유지**합니다.

---

## v0.1 기준선 정보

| 항목 | 내용 |
|------|------|
| **버전** | v0.1 |
| **기준 날짜** | 2026-03-20 |
| **LLM** | Ollama qwen3.5:9b (rules fallback 포함) |
| **스킬** | workspace_reporter, code_reviewer, file_classifier |
| **핵심 기능** | 워크스페이스 분석, 파일 자동 정리, pending 승인 흐름 |
| **테스트** | T1~T6 자동 테스트 통과 기준 |

### v0.1 포함 기능

- LLM(Ollama) 연동 및 rules fallback
- 스킬 기반 실행 엔진 (`SkillExecutor`)
- `workspace_reporter`: 분석 → 제안 → 자동실행/pending/기록
- 보고서 내 "후속 실행 결과" 섹션 (원샷 쓰기)
- `pending_approvals.json` 흐름 + `review_pending.py` CLI
- `agent.log`, `config.json` 보호 로직
- 데몬 모드 (5분 간격)
- 유지보수 모듈 (로그 정리, 아카이브)

### v0.2 예정 사항 (참고용)

- daemon이 `approved` 항목을 실제로 실행하는 처리기 연결
- 스킬 자동 생성 품질 개선 (generated_skills 활용)
- 멀티 워크스페이스 지원
- 보고서 diff 비교 (이전 사이클 대비 변화 추적)

---

*이 README는 v0.1 기준선 문서입니다. 구조나 동작이 변경되면 함께 업데이트하세요.*
