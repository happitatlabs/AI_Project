#!/usr/bin/env python3
"""
approve_generated_skill.py -- record/view generated skill approval records
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_approval_report,
    save_generated_skill_approval_record,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_approval_show_output(
    skill_id: str,
    *,
    approval_type: str | None = None,
    reference: str | None = None,
) -> str:
    return build_generated_skill_approval_report(
        skill_id,
        approval_type=approval_type,
        reference=reference or DEFAULT_REFERENCE,
    )


def _build_write_output(result: dict) -> str:
    approval = result["approval"]
    return "\n".join(
        [
            "generated skill approval record saved",
            f"- skill_id: {approval['skill_id']}",
            f"- approval_type: {approval['approval_type']}",
            f"- decision: {approval['decision']}",
            f"- approver: {approval['approver']}",
            f"- approved_at: {approval['approved_at']}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or view generated skill approval records")
    subparsers = parser.add_subparsers(dest="command")

    write_parser = subparsers.add_parser("write", help="write a generated skill approval record")
    write_parser.add_argument("skill_id", help="generated skill id")
    write_parser.add_argument(
        "--approval-type",
        required=True,
        choices=["promotion_approval", "transform_approval"],
        help="approval record type",
    )
    write_parser.add_argument(
        "--decision",
        required=True,
        choices=["approved", "rejected", "needs_followup"],
        help="approval decision",
    )
    write_parser.add_argument("--approver", required=True, help="approver name")
    write_parser.add_argument("--rationale", required=True, help="approval rationale")
    write_parser.add_argument("--note", action="append", default=[], help="optional approval note")
    write_parser.add_argument("--final-target-name", help="approved candidate target name")
    write_parser.add_argument("--final-target-path", help="approved candidate target path")
    write_parser.add_argument("--rollback-reference", help="optional rollback reference")
    write_parser.add_argument("--allow-replace", action="store_true", help="replace an existing approval record of the same type")
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

    show_parser = subparsers.add_parser("show", help="show generated skill approval records")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--approval-type",
        choices=["promotion_approval", "transform_approval"],
        help="optional approval record type filter",
    )
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "write":
        try:
            result = save_generated_skill_approval_record(
                args.skill_id,
                approval_type=args.approval_type,
                decision=args.decision,
                approver=args.approver,
                rationale=args.rationale,
                followup_required=args.followup_required,
                notes=args.note,
                final_target_name=args.final_target_name,
                final_target_path=args.final_target_path,
                rollback_reference=args.rollback_reference,
                allow_replace=args.allow_replace,
                reference=args.reference,
            )
        except ValueError as exc:
            print(str(exc))
            return 1
        print(_build_write_output(result))
        return 0

    if args.command == "show":
        print(
            build_generated_skill_approval_show_output(
                args.skill_id,
                approval_type=args.approval_type,
                reference=args.reference,
            )
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
