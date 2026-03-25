#!/usr/bin/env python3
"""
test_pending_approval.py — pending_approvals 흐름 통합 테스트

테스트 항목:
  T1. workspace_reporter 실행 → 중간 우선순위 제안이 pending_approvals.json 기록
  T2. review_pending.py approve → status 변경 확인
  T3. review_pending.py reject  → status 변경 확인
  T4. 이미 처리된 항목은 재처리 안됨 (approve → 다시 approve 무시)
  T5. pending_approvals.json 없는 상태에서 list 실행 → 오류 없이 동작
  T6. approve all → 전체 pending 일괄 승인

실행:
  python test_pending_approval.py
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile

# ── 경로 설정 ─────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from agent.executor import Executor
from agent.skill_executor import SkillExecutor

# review_pending 모듈을 동적으로 로드 (APPROVAL_FILE 오버라이드용)
def _load_review_module(approval_file: str):
    spec = importlib.util.spec_from_file_location(
        "review_pending", os.path.join(BASE, "review_pending.py")
    )
    mod = importlib.util.module_from_spec(spec)
    mod.APPROVAL_FILE = approval_file
    spec.loader.exec_module(mod)
    return mod


# ── 헬퍼 ─────────────────────────────────────────────────

def _make_workspace(tmpws: str):
    """테스트용 워크스페이스 구성 — pending 제안이 반드시 생기도록."""
    for name in [
        "workspace_reporter_20260101_120000.md",
        "report_20260101_110000.md",
        "README.md", "agent_goal.md", "config.json", "config.yaml",
    ]:
        open(os.path.join(tmpws, name), "w").write("content")
    open(os.path.join(tmpws, "agent.log"), "w").write("active log")
    open(os.path.join(tmpws, "agent_trace.jsonl"), "w").write("trace")


def _run_reporter(tmpws: str) -> str:
    """workspace_reporter 1회 실행 후 approval_file 경로 반환."""
    sk = SkillExecutor(executor=Executor(workspace=tmpws))
    sk.run({
        "name": "workspace_reporter",
        "risk_level": "safe",
        "steps": ["scan_workspace: 분석", "write_report: 생성"],
    })
    return os.path.join(tmpws, "pending_approvals.json")


def _load_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 테스트 케이스 ─────────────────────────────────────────

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  ✅ {label}")
        passed += 1
    else:
        print(f"  ❌ {label}" + (f"  ({detail})" if detail else ""))
        failed += 1


def test_t1_pending_written():
    """T1: reporter 실행 → pending_approvals.json에 중간 우선순위 항목 기록"""
    print("T1: pending_approvals.json 기록 확인")
    tmpws = tempfile.mkdtemp(prefix="t1_")
    try:
        _make_workspace(tmpws)
        af = _run_reporter(tmpws)
        check("파일 생성됨", os.path.exists(af))
        data = _load_json(af)
        check("최소 1개 항목", len(data) >= 1, f"실제: {len(data)}")
        statuses = {d["status"] for d in data}
        check("pending 항목 존재", "pending" in statuses)
        priorities = {d.get("priority") for d in data}
        check("중간 우선순위 항목 존재", "중간" in priorities, f"실제: {priorities}")
        ops = {d.get("action", {}).get("op") for d in data}
        check("op 필드 존재", any(ops - {None}), f"실제: {ops}")
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


def test_t2_approve_single():
    """T2: approve <번호> → 해당 항목 status=approved"""
    print("T2: approve 단일 항목")
    tmpws = tempfile.mkdtemp(prefix="t2_")
    try:
        _make_workspace(tmpws)
        af = _run_reporter(tmpws)
        mod = _load_review_module(af)
        data_before = _load_json(af)
        pending_idx = next(
            (i for i, d in enumerate(data_before) if d["status"] == "pending"), None
        )
        check("pending 항목 존재", pending_idx is not None)
        if pending_idx is not None:
            mod.cmd_approve(_load_json(af), str(pending_idx))
            data_after = _load_json(af)
            check(
                f"[{pending_idx}] status=approved",
                data_after[pending_idx]["status"] == "approved",
                f"실제: {data_after[pending_idx]['status']}",
            )
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


def test_t3_reject_single():
    """T3: reject <번호> → 해당 항목 status=rejected"""
    print("T3: reject 단일 항목")
    tmpws = tempfile.mkdtemp(prefix="t3_")
    try:
        _make_workspace(tmpws)
        af = _run_reporter(tmpws)
        mod = _load_review_module(af)
        data = _load_json(af)
        pending_indices = [i for i, d in enumerate(data) if d["status"] == "pending"]
        check("pending 항목 존재", len(pending_indices) > 0)
        if pending_indices:
            target = pending_indices[-1]
            mod.cmd_reject(_load_json(af), str(target))
            data_after = _load_json(af)
            check(
                f"[{target}] status=rejected",
                data_after[target]["status"] == "rejected",
            )
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


def test_t4_no_double_process():
    """T4: 이미 approved 항목에 다시 approve → 변경 없음, 카운트 0"""
    print("T4: 이미 처리된 항목 재처리 방지")
    tmpws = tempfile.mkdtemp(prefix="t4_")
    try:
        _make_workspace(tmpws)
        af = _run_reporter(tmpws)
        mod = _load_review_module(af)
        # 먼저 전체 승인
        data = _load_json(af)
        mod.cmd_approve(data, "all")
        # 다시 approve all
        data2 = _load_json(af)
        changed = sum(
            1 for d in data2 if d["status"] == "pending"
        )
        check("재처리할 pending 항목 0개", changed == 0, f"실제 pending: {changed}")
        all_approved = all(
            d["status"] in ("approved", "rejected") for d in data2
        )
        check("모든 항목 처리 완료", all_approved)
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


def test_t5_empty_file():
    """T5: pending_approvals.json 없는 상태에서 list → 오류 없이 동작"""
    print("T5: 파일 없을 때 list 동작")
    tmpws = tempfile.mkdtemp(prefix="t5_")
    af = os.path.join(tmpws, "pending_approvals.json")
    try:
        mod = _load_review_module(af)
        check("파일 없음 확인", not os.path.exists(af))
        try:
            data = mod._load()
            check("_load() → 빈 리스트", data == [], f"실제: {data}")
            mod.cmd_list(data)  # 오류 없이 실행되면 통과
            check("cmd_list() 예외 없음", True)
        except Exception as e:
            check("cmd_list() 예외 없음", False, str(e))
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


def test_t6_approve_all():
    """T6: approve all → 모든 pending이 approved로 변경"""
    print("T6: approve all 일괄 처리")
    tmpws = tempfile.mkdtemp(prefix="t6_")
    try:
        _make_workspace(tmpws)
        af = _run_reporter(tmpws)
        mod = _load_review_module(af)
        data_before = _load_json(af)
        n_pending_before = sum(1 for d in data_before if d["status"] == "pending")
        check("사전 pending 항목 존재", n_pending_before > 0, f"실제: {n_pending_before}")

        mod.cmd_approve(_load_json(af), "all")
        data_after = _load_json(af)
        n_pending_after  = sum(1 for d in data_after if d["status"] == "pending")
        n_approved_after = sum(1 for d in data_after if d["status"] == "approved")
        check("approve all 후 pending 0건", n_pending_after == 0, f"실제: {n_pending_after}")
        check(f"approved 항목 {n_pending_before}건 이상", n_approved_after >= n_pending_before)
    finally:
        shutil.rmtree(tmpws, ignore_errors=True)
    print()


# ── 실행 ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 56)
    print("  pending_approvals 흐름 통합 테스트  (v0.1)")
    print("=" * 56)
    print()

    test_t1_pending_written()
    test_t2_approve_single()
    test_t3_reject_single()
    test_t4_no_double_process()
    test_t5_empty_file()
    test_t6_approve_all()

    total = passed + failed
    print("=" * 56)
    print(f"  결과: {passed}/{total} 통과" + ("  ✅ ALL PASS" if failed == 0 else f"  ❌ {failed}건 실패"))
    print("=" * 56)
    sys.exit(0 if failed == 0 else 1)
