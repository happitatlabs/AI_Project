# Mellow Agent v0.1 — 3~5 사이클 운영 테스트 체크리스트

> **목적**: 실제 운영 환경에서 workspace_reporter를 3~5회 연속 실행하여 핵심 흐름이 안정적으로 동작하는지 확인한다.
> **기준 날짜**: 2026-03-20
> **대상 버전**: v0.1

---

## 준비 사항

- [ ] `autonomous_agent/` 디렉터리에 테스트용 파일 혼재 상태 조성
  - 예: `*.log`, `*_YYYYMMDD_HHMMSS.md` (자동 보고서), `config.yaml`, `*.json` 혼합
- [ ] `pending_approvals.json` 없는 초기 상태 확인
- [ ] `agent.log` 파일 존재 여부 확인 (보호 대상)
- [ ] `config.json` 파일 존재 여부 확인 (보호 대상)

---

## 사이클 1 — 최초 실행 (초기 워크스페이스 분석)

### 실행
```bash
python run_agent.py   # 또는 daemon 기동 후 workspace_reporter 트리거
```

### 확인 항목

| # | 항목 | 확인 | 비고 |
|---|------|------|------|
| 1-1 | `workspace_reporter_YYYYMMDD_HHMMSS.md` 보고서 파일 생성됨 | ☐ | |
| 1-2 | 보고서 상단에 "실행 전 스냅샷 기준" 문구 포함 | ☐ | |
| 1-3 | 보고서 하단에 "후속 실행 결과" 섹션 존재 | ☐ | |
| 1-4 | "후속 실행 결과" 섹션 헤더에 실행 시각·건수 요약 포함 | ☐ | 예: `자동실행 2건 · 승인대기 1건 · 기록 1건` |
| 1-5 | `[높음]` 제안 → 자동 실행 항목에 표시, `[성공]` 또는 `[실패]` 표시 | ☐ | |
| 1-6 | `[중간]` 제안 → 승인 대기 항목에 표시, `[대기]` 표시 | ☐ | |
| 1-7 | `[낮음]` 제안 → 기록 항목에 표시, `[기록]` 표시 | ☐ | |
| 1-8 | `pending_approvals.json` 파일 생성됨 (중간 우선순위 제안이 있는 경우) | ☐ | |
| 1-9 | `agent.log` 파일이 `logs/`로 이동되지 않음 (보호 확인) | ☐ | |
| 1-10 | `config.json` 파일이 `config/`로 이동되지 않음 (보호 확인) | ☐ | |
| 1-11 | 자동 실행 항목 op명이 한국어 레이블로 표시됨 (예: "logs/ 이동 적용") | ☐ | `mkdir_and_move` 노출 없어야 함 |

---

## 사이클 2 — pending_approvals 승인 후 재실행

### 실행
```bash
# pending 목록 확인
python review_pending.py

# 일부 승인, 일부 거절
python review_pending.py approve 0
python review_pending.py reject 1

# 재실행
python run_agent.py
```

### 확인 항목

| # | 항목 | 확인 | 비고 |
|---|------|------|------|
| 2-1 | `python review_pending.py` 목록 출력 정상 (색상·포맷 깨짐 없음) | ☐ | |
| 2-2 | `approve 0` 실행 후 `pending_approvals.json` 내 해당 항목 `status: approved` | ☐ | |
| 2-3 | `reject 1` 실행 후 해당 항목 `status: rejected` | ☐ | |
| 2-4 | 2번째 보고서 파일이 새 타임스탬프로 생성됨 | ☐ | 기존 파일 덮어쓰기 아님 |
| 2-5 | 이전 사이클에서 이동된 파일들이 중복 이동되지 않음 | ☐ | |
| 2-6 | `pending_approvals.json`에 이번 사이클 신규 항목 추가됨 (있는 경우) | ☐ | |

---

## 사이클 3 — approve all 후 워크스페이스 정리 확인

### 실행
```bash
python review_pending.py approve all
python run_agent.py
```

### 확인 항목

| # | 항목 | 확인 | 비고 |
|---|------|------|------|
| 3-1 | `approve all` 실행 후 모든 `pending` 항목이 `approved`로 변경됨 | ☐ | |
| 3-2 | 3번째 보고서에서 자동 실행 건수 증가 (승인된 항목 실행) | ☐ | |
| 3-3 | `logs/` 디렉터리 생성 및 `.log`, `.jsonl` 파일 이동 확인 | ☐ | `agent.log` 제외 |
| 3-4 | `reports/` 디렉터리 생성 및 자동 보고서 이동 확인 | ☐ | |
| 3-5 | `config/` 디렉터리 생성 및 설정 파일 이동 확인 (해당 시) | ☐ | `config.json` 제외 |
| 3-6 | 제안 문장이 120자 이상일 경우 `...`으로 말줄임 표시됨 | ☐ | |

---

## 사이클 4 — 정리 완료 후 재스캔 (워크스페이스 안정 상태)

### 실행
```bash
python run_agent.py
```

### 확인 항목

| # | 항목 | 확인 | 비고 |
|---|------|------|------|
| 4-1 | 보고서가 정상 생성됨 (오류 없음) | ☐ | |
| 4-2 | 파일 수가 줄어든 워크스페이스 반영됨 (이전 보고서와 비교) | ☐ | |
| 4-3 | 더 이상 이동할 파일 없는 경우 "자동실행 0건" 표시 + 설명 문구 포함 | ☐ | |
| 4-4 | `pending_approvals.json` 처리 완료 항목 유지됨 (누적 기록 확인) | ☐ | |
| 4-5 | `review_pending.py list`에서 처리 완료 섹션 표시 정상 | ☐ | |

---

## 사이클 5 — 예외 케이스 및 엣지 처리

### 시나리오: 새 파일 투입 후 재스캔
```bash
# 테스트용 파일 추가
touch workspace_reporter_20260320_120000.md
echo "test" > debug_trace_20260320_120001.jsonl

python run_agent.py
```

### 확인 항목

| # | 항목 | 확인 | 비고 |
|---|------|------|------|
| 5-1 | 새로 추가된 자동 보고서 파일이 이동 대상으로 감지됨 | ☐ | |
| 5-2 | 새로 추가된 `.jsonl` 파일이 logs/ 이동 대상으로 감지됨 | ☐ | |
| 5-3 | `pending_approvals.json` show 명령으로 상세 내용 확인 가능 | ☐ | `python review_pending.py show 0` |
| 5-4 | `reject all` 실행 시 모든 pending이 rejected로 변경됨 | ☐ | |
| 5-5 | 이미 처리된 항목에 `approve` 재시도 시 "이미 처리됨" 경고 출력 | ☐ | |
| 5-6 | `pending_approvals.json` 삭제 후 `review_pending.py` 오류 없이 동작 | ☐ | |

---

## 자동 테스트 실행

위 수동 체크리스트 외에 자동 테스트를 반드시 통과해야 한다.

```bash
cd autonomous_agent
python test_pending_approval.py
```

**기대 결과**: `6/6 통과  ✅ ALL PASS`

---

## 최종 검증 기준 (v0.1 릴리스 조건)

| 조건 | 기준 |
|------|------|
| 자동 테스트 | T1~T6 모두 통과 |
| 수동 사이클 테스트 | 사이클 1~3 전 항목 ☑ |
| agent.log 보호 | 단 1회도 이동되지 않음 |
| 보고서 형식 | 실행 전 스냅샷 문구 + 후속 실행 결과 섹션 모두 포함 |
| pending 흐름 | approve/reject CLI 정상 동작 확인 |
| 이중 처리 방지 | 이미 처리된 항목 재처리 없음 확인 |
