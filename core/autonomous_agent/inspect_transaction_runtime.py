#!/usr/bin/env python3
"""
inspect_transaction_runtime.py -- read-only runtime transaction state debug CLI
"""

import argparse
from pathlib import Path

from agent.transaction_runtime import (
    load_runtime_transaction_state_for_debug,
    summarize_runtime_transaction_state,
)


def build_runtime_state_report(transaction_id: str, *, reference: str | Path | None = None) -> str:
    runtime_state = load_runtime_transaction_state_for_debug(transaction_id, reference=reference)
    summary = summarize_runtime_transaction_state(transaction_id, reference=reference)

    if runtime_state is None or summary is None:
        return f"transaction runtime state not found: {transaction_id}"

    lines = [
        "[Transaction Runtime State]",
        f"- transaction_id: {runtime_state.get('transaction_id')}",
        f"- proposal_id: {runtime_state.get('proposal_id') or 'none'}",
        f"- execution_mode: {runtime_state.get('execution_mode') or 'operational'}",
        f"- state: {runtime_state.get('state') or 'unknown'}",
        f"- terminal_marker: {runtime_state.get('terminal_marker') or 'none'}",
        f"- last_updated_at: {runtime_state.get('last_updated_at') or 'unknown'}",
        "",
        "[Markers]",
    ]

    markers = runtime_state.get("markers", [])
    if markers:
        for marker in markers:
            lines.append(f"- {marker.get('marker', 'unknown')} @ {marker.get('recorded_at', 'unknown')}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "[Summary]",
            f"- transaction_id: {summary.get('transaction_id')}",
            f"- proposal_id: {summary.get('proposal_id') or 'none'}",
            f"- execution_mode: {summary.get('execution_mode') or 'operational'}",
            f"- state: {summary.get('state') or 'unknown'}",
            f"- marker_count: {summary.get('marker_count', 0)}",
            f"- last_marker: {summary.get('last_marker') or 'none'}",
            f"- terminal_marker: {summary.get('terminal_marker') or 'none'}",
            f"- note_count: {summary.get('note_count', 0)}",
            f"- last_updated_at: {summary.get('last_updated_at') or 'unknown'}",
        ]
    )

    notes = runtime_state.get("runtime_notes", [])
    if notes:
        lines.extend(["", "[Notes]"])
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect runtime transaction state")
    parser.add_argument("transaction_id", nargs="?", help="transaction id")
    parser.add_argument("--transaction-id", dest="transaction_id_flag", help="transaction id")
    parser.add_argument("--reference", help="reference path used to resolve runtime-data root")
    args = parser.parse_args(argv)

    transaction_id = args.transaction_id_flag or args.transaction_id
    if not transaction_id:
        parser.print_help()
        return 0

    print(build_runtime_state_report(transaction_id, reference=args.reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
