#!/usr/bin/env python3
"""
review_generated_skill_decision.py -- read/write viewer for generated skill review decisions
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_review_decision_report,
    save_generated_skill_review_decision,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_review_decision_show_output(
    skill_id: str,
    *,
    reference: str | None = None,
) -> str:
    return build_generated_skill_review_decision_report(skill_id, reference=reference or DEFAULT_REFERENCE)


def _build_write_output(result: dict) -> str:
    review = result["review"]
    return "\n".join(
        [
            "generated skill review decision saved",
            f"- skill_id: {review['skill_id']}",
            f"- decision: {review['decision']}",
            f"- reviewer: {review['reviewer']}",
            f"- reviewed_at: {review['reviewed_at']}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record manual review decisions for generated skills")
    subparsers = parser.add_subparsers(dest="command")

    write_parser = subparsers.add_parser("write", help="write a generated skill review decision record")
    write_parser.add_argument("skill_id", help="generated skill id")
    write_parser.add_argument(
        "--decision",
        required=True,
        choices=[
            "approve_for_consideration",
            "rejected",
            "needs_followup",
        ],
        help="manual review decision",
    )
    write_parser.add_argument("--reviewer", required=True, help="reviewer name")
    write_parser.add_argument("--rationale", required=True, help="review rationale")
    write_parser.add_argument("--note", action="append", default=[], help="optional review note")
    write_parser.add_argument("--allow-replace", action="store_true", help="replace an existing review record")
    followup_group = write_parser.add_mutually_exclusive_group()
    followup_group.add_argument(
        "--followup-required",
        dest="followup_required",
        action="store_true",
        help="mark follow-up as required",
    )
    followup_group.add_argument(
        "--no-followup-required",
        dest="followup_required",
        action="store_false",
        help="mark follow-up as not required",
    )
    write_parser.set_defaults(followup_required=None)
    write_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show a generated skill review decision record")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "write":
        try:
            result = save_generated_skill_review_decision(
                args.skill_id,
                decision=args.decision,
                reviewer=args.reviewer,
                rationale=args.rationale,
                followup_required=args.followup_required,
                notes=args.note,
                allow_replace=args.allow_replace,
                reference=args.reference,
            )
        except ValueError as exc:
            print(str(exc))
            return 1
        print(_build_write_output(result))
        return 0

    if args.command == "show":
        print(build_generated_skill_review_decision_show_output(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
