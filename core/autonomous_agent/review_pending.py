#!/usr/bin/env python3
"""
review_pending.py — pending_approvals.json 승인/거절 CLI

사용법:
  python review_pending.py              # 대기 항목 목록 출력
  python review_pending.py list         # 위와 동일
  python review_pending.py approve 0    # 인덱스 0번 승인
  python review_pending.py approve all  # 전체 승인
  python review_pending.py reject 0     # 인덱스 0번 거절
  python review_pending.py reject all   # 전체 거절
  python review_pending.py show 0       # 인덱스 0번 상세 내용 출력

참고:
  pending_approvals.json 의 각 항목 status 를
  "approved" 또는 "rejected" 로 변경하면 daemon이 다음 사이클에 처리합니다.
"""

import json
import os
import sys
from datetime import datetime

from agent.workspace_metrics import (
    build_apply_precheck,
    build_apply_transaction,
    build_executor_spec,
    build_common_render_sections,
    build_apply_dry_run,
    load_proposal_by_review_id,
    load_staging_apply_plan,
    load_staging_executor_spec,
    load_staging_apply_transaction,
    load_staging_precheck,
    process_review_decision,
)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
APPROVAL_FILE = os.path.join(BASE_DIR, "pending_approvals.json")

# ANSI 색상 (터미널 미지원 시 공백 fallback)
_C_GREEN  = "\033[32m"
_C_RED    = "\033[31m"
_C_YELLOW = "\033[33m"
_C_CYAN   = "\033[36m"
_C_RESET  = "\033[0m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{_C_RESET}" if sys.stdout.isatty() else text


def _shorten(text: str, limit: int = 72) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def format_review_list_item(index: int, item: dict) -> str:
    bucket = item.get("priority_bucket", item.get("suggestion_severity", item.get("risk", "?")))
    cluster = item.get("top_risk_cluster_label") or "No cluster"
    headline = item.get("summary_headline") or item.get("top_suggestion") or item.get("suggestion", "")
    changed = (
        item.get("top_risk_cluster_has_content_change")
        or bool(item.get("content_changed_count", 0))
        or bool(item.get("top_content_change_hint"))
    )
    changed_suffix = " *changed" if changed else ""
    return f"[{index}] {_shorten(headline, limit=60)} | {cluster}{changed_suffix} | {bucket}"


def format_review_show(item: dict, index: int) -> list[str]:
    status = item.get("status", "?")
    lines = [f"── [{index}] {status.upper()} ──"]
    for section in build_common_render_sections(item):
        lines.extend(["", f"[{section.get('title', 'Section')}]"])
        lines.extend(f"- {value}" for value in section.get("lines", []))
    proposal = load_proposal_by_review_id(item.get("signature") or "", reference=APPROVAL_FILE)
    if proposal:
        lines.extend([
            "",
            "[Proposal]",
            f"- proposal_id: {proposal.get('proposal_id')}",
            f"- proposal_status: {proposal.get('status', 'pending')}",
            f"- proposal_summary: {proposal.get('summary', 'none')}",
        ])
        precheck = load_staging_precheck(proposal.get("proposal_id", ""), reference=APPROVAL_FILE) or build_apply_precheck(proposal)
        lines.extend([
            "",
            "[Apply Precheck]",
            f"- apply_mode: {precheck.get('apply_mode', 'blocked')}",
            f"- apply_possible: {precheck.get('apply_possible', False)}",
        ])
        if precheck.get("apply_blockers"):
            lines.append(f"- blockers: {', '.join(precheck.get('apply_blockers', []))}")
        if precheck.get("apply_warnings"):
            lines.append(f"- warnings: {', '.join(precheck.get('apply_warnings', []))}")
        if precheck.get("operator_steps"):
            lines.append(f"- operator_steps: {', '.join(precheck.get('operator_steps', []))}")
        apply_plan = load_staging_apply_plan(proposal.get("proposal_id", ""), reference=APPROVAL_FILE)
        dry_run = (apply_plan or {}).get("dry_run") or build_apply_dry_run(proposal)
        lines.extend([
            "",
            "[Apply Plan Preview]",
            f"- number_of_changes: {dry_run.get('change_count', 0)}",
            f"- affected_paths: {', '.join(dry_run.get('affected_paths', [])) or 'none'}",
            f"- dry_run_summary: {dry_run.get('dry_run_result', 'none')}",
        ])
        if dry_run.get("potential_conflicts"):
            lines.append(f"- potential_conflicts: {', '.join(dry_run.get('potential_conflicts', []))}")
        transaction = load_staging_apply_transaction(proposal.get("proposal_id", ""), reference=APPROVAL_FILE) or build_apply_transaction(proposal)
        atomicity = transaction.get("atomicity_policy", {})
        rollback = transaction.get("rollback_triggers", {})
        backup = transaction.get("backup_plan", {})
        failure_policy = transaction.get("failure_handling_policy", {})
        lines.extend([
            "",
            "[Apply Safety Boundary]",
            f"- atomicity_mode: {atomicity.get('atomicity_mode', 'all_or_nothing')}",
            f"- rollback_required: {rollback.get('recovery_mode', 'full_rollback_required')}",
            f"- backup_required: {backup.get('backup_required', True)}",
            f"- partial_apply_policy: {failure_policy.get('partial_apply_policy', 'forbidden')}",
            f"- recovery_mode: {rollback.get('recovery_mode', 'full_rollback_required')}",
        ])
        executor_spec = load_staging_executor_spec(proposal.get("proposal_id", ""), reference=APPROVAL_FILE) or build_executor_spec(proposal)
        atomic_write_contract = executor_spec.get("atomic_write_contract", {})
        rollback_contract = executor_spec.get("rollback_execution_contract", {})
        backup_contract = executor_spec.get("backup_materialization_contract", {})
        marker_contract = executor_spec.get("transaction_markers", {})
        lines.extend([
            "",
            "[Executor Specification]",
            f"- atomic_write_mode: {atomic_write_contract.get('atomic_write_mode', 'temp_then_rename')}",
            f"- rollback_mode: {rollback_contract.get('rollback_mode', 'full_only')}",
            f"- backup_strategy: {backup_contract.get('backup_strategy', 'copy_before_apply')}",
            f"- partial_write_policy: {atomic_write_contract.get('partial_write_policy', 'forbidden')}",
            f"- terminal_marker_rule: {marker_contract.get('terminal_marker_rule_summary', 'exactly one terminal marker required')}",
        ])
    return lines


# ── 파일 I/O ──────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(APPROVAL_FILE):
        return []
    try:
        with open(APPROVAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠  파일 읽기 실패: {e}", file=sys.stderr)
        return []


def _save(data: list) -> None:
    with open(APPROVAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 명령 처리 ─────────────────────────────────────────────

def cmd_list(data: list) -> None:
    pending = [(i, d) for i, d in enumerate(data) if d.get("status") == "pending"]
    done    = [(i, d) for i, d in enumerate(data) if d.get("status") != "pending"]

    if not pending and not done:
        print("⚡ pending_approvals.json 이 비어 있습니다.")
        return

    if pending:
        print(_color(f"대기 항목 {len(pending)}개:", _C_YELLOW))
        print("  빠른 훑기:")
        print("  " + "-" * 72)
        for i, d in pending:
            print(f"  {format_review_list_item(i, d)}")
        print()
        print(f"  승인: python review_pending.py approve <번호|all>")
        print(f"  거절: python review_pending.py reject  <번호|all>")

    if done:
        print()
        print(_color(f"처리 완료 항목 {len(done)}개:", _C_CYAN))
        for i, d in done:
            status = d.get("status", "?")
            color  = _C_GREEN if status == "approved" else _C_RED
            op     = d.get("action", {}).get("op", "?")
            text   = d.get("suggestion", "")[:45]
            ts     = d.get("requested_at", "")[:16].replace("T", " ")
            print(f"  {i:>3}  {_color(status, color):<20} {op:<18} {text}  ({ts})")


def cmd_show(data: list, target: str) -> None:
    try:
        idx = int(target)
        if idx < 0 or idx >= len(data):
            print(f"⚠  인덱스 {idx} 범위 초과 (총 {len(data)}개)")
            return
    except ValueError:
        print(f"⚠  잘못된 인덱스: {target!r}  (숫자 입력)")
        return

    d = data[idx]
    status = d.get("status", "?")
    color  = (_C_GREEN  if status == "approved"
              else _C_RED if status == "rejected"
              else _C_YELLOW)
    lines = format_review_show(d, idx)
    if lines:
        lines[0] = f"── [{idx}] {_color(status.upper(), color)} ──"
    for line in lines:
        print(line)


def cmd_approve(data: list, target: str) -> None:
    changed_entries = _update_status(data, target, "approved")
    if changed_entries:
        _save(data)
        for entry in changed_entries:
            process_review_decision(
                entry.get("signature", "unknown"),
                "approved",
                reference=APPROVAL_FILE,
                operator=os.getenv("USERNAME") or os.getenv("USER"),
            )
        print(_color(f"✅ {len(changed_entries)}개 항목 승인 완료", _C_GREEN))


def cmd_reject(data: list, target: str) -> None:
    changed_entries = _update_status(data, target, "rejected")
    if changed_entries:
        _save(data)
        for entry in changed_entries:
            process_review_decision(
                entry.get("signature", "unknown"),
                "rejected",
                reference=APPROVAL_FILE,
                operator=os.getenv("USERNAME") or os.getenv("USER"),
            )
        print(_color(f"❌ {len(changed_entries)}개 항목 거절 완료", _C_RED))


def _update_status(data: list, target: str, new_status: str) -> list[dict]:
    changed_entries: list[dict] = []
    if target == "all":
        for d in data:
            if d.get("status") == "pending":
                d["status"] = new_status
                changed_entries.append(d)
    else:
        try:
            idx = int(target)
            if 0 <= idx < len(data):
                if data[idx].get("status") == "pending":
                    data[idx]["status"] = new_status
                    changed_entries.append(data[idx])
                else:
                    print(f"⚠  [{idx}] 은 이미 '{data[idx].get('status')}' 상태입니다")
            else:
                print(f"⚠  인덱스 {idx} 범위 초과 (총 {len(data)}개)")
        except ValueError:
            print(f"⚠  잘못된 인덱스: {target!r}  (숫자 또는 'all' 입력)")
    return changed_entries


# ── 진입점 ───────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    data = _load()

    if not args or args[0] in ("list", "ls"):
        cmd_list(data)
    elif args[0] in ("show", "detail") and len(args) == 2:
        cmd_show(data, args[1])
    elif args[0] in ("approve", "ok") and len(args) == 2:
        cmd_approve(data, args[1])
    elif args[0] in ("reject", "no", "deny") and len(args) == 2:
        cmd_reject(data, args[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
