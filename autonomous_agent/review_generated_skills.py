#!/usr/bin/env python3
"""
review_generated_skills.py -- read-only viewer for generated skill manual review queue
"""

import argparse
import os

from agent.auto_promotion_rules import build_auto_promotion_report, evaluate_auto_promotion_rules
from agent.generated_skill_sandbox import (
    build_generated_skill_queue_report,
    build_generated_skill_queue_summary,
    load_generated_skill_queue_record,
    list_generated_skill_queue,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_queue_list_output(*, reference: str | None = None) -> str:
    entries = list_generated_skill_queue(reference=reference or DEFAULT_REFERENCE)
    if not entries:
        return "generated skill manual review queue is empty"
    lines = []
    for index, entry in enumerate(entries):
        summary = build_generated_skill_queue_summary(entry, index=index)
        auto = evaluate_auto_promotion_rules(
            str(entry.get("skill_id") or ""),
            reference=reference or DEFAULT_REFERENCE,
        )
        if auto["auto_applicable"]:
            summary += " | auto: 추천 가능"
        lines.append(summary)
    return "\n".join(lines)


def build_generated_skill_queue_show_output(
    target: str,
    *,
    reference: str | None = None,
) -> str:
    resolved_reference = reference or DEFAULT_REFERENCE
    base = build_generated_skill_queue_report(target, reference=resolved_reference)
    record = load_generated_skill_queue_record(target, reference=resolved_reference)
    if record is None:
        return base
    auto = build_auto_promotion_report(str(record.get("skill_id") or target), reference=resolved_reference)
    return "\n\n".join([base, auto])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review generated skill manual promotion queue")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "show"], help="viewer command")
    parser.add_argument("target", nargs="?", help="skill_id or queue filename stem for show")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE, help="reference path used to resolve runtime-data root")
    args = parser.parse_args(argv)

    if args.command == "list":
        print(build_generated_skill_queue_list_output(reference=args.reference))
        return 0

    if not args.target:
        parser.print_help()
        return 0

    print(build_generated_skill_queue_show_output(args.target, reference=args.reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
