#!/usr/bin/env python3
"""
record_generated_skill_checklist.py -- record/view generated skill candidate readiness checklists
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_candidate_checklist_report,
    save_generated_skill_candidate_checklist,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def _parse_yes_no(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    raise argparse.ArgumentTypeError("value must be yes or no")


def build_generated_skill_checklist_show_output(
    skill_id: str,
    *,
    reference: str | None = None,
) -> str:
    return build_generated_skill_candidate_checklist_report(
        skill_id,
        reference=reference or DEFAULT_REFERENCE,
    )


def _build_write_output(result: dict) -> str:
    checklist = result["checklist"]
    return "\n".join(
        [
            "generated skill candidate checklist saved",
            f"- skill_id: {checklist['skill_id']}",
            f"- operator: {checklist['operator']}",
            f"- all_checks_passed: {checklist['all_checks_passed']}",
            f"- checked_at: {checklist['checked_at']}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or view generated skill candidate checklists")
    subparsers = parser.add_subparsers(dest="command")

    write_parser = subparsers.add_parser("write", help="write a generated skill candidate checklist")
    write_parser.add_argument("skill_id", help="generated skill id")
    write_parser.add_argument("--operator", required=True, help="operator name")
    write_parser.add_argument("--review-decision-exists", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--approval-record-exists", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--validation-passed", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--sandbox-passed", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--sandbox-only-confirmed", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--promotion-required-confirmed", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--generated-only-fields-removed", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--target-name-manually-chosen", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--naming-collision-resolved", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--core-skill-overwrite-absent", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--rollback-reference-prepared", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--direct-move-not-used", required=True, type=_parse_yes_no, metavar="yes|no")
    write_parser.add_argument("--target-name", required=True, help="manually chosen candidate target name")
    write_parser.add_argument("--target-path", required=True, help="candidate target path")
    write_parser.add_argument("--note", action="append", default=[], help="optional checklist note")
    write_parser.add_argument("--allow-replace", action="store_true", help="replace an existing checklist record")
    write_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show a generated skill candidate checklist")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "write":
        try:
            result = save_generated_skill_candidate_checklist(
                args.skill_id,
                operator=args.operator,
                review_decision_exists=args.review_decision_exists,
                approval_record_exists=args.approval_record_exists,
                validation_passed=args.validation_passed,
                sandbox_passed=args.sandbox_passed,
                sandbox_only_confirmed=args.sandbox_only_confirmed,
                promotion_required_confirmed=args.promotion_required_confirmed,
                generated_only_fields_removed=args.generated_only_fields_removed,
                target_name_manually_chosen=args.target_name_manually_chosen,
                naming_collision_resolved=args.naming_collision_resolved,
                core_skill_overwrite_absent=args.core_skill_overwrite_absent,
                rollback_reference_prepared=args.rollback_reference_prepared,
                direct_move_not_used=args.direct_move_not_used,
                target_name=args.target_name,
                target_path=args.target_path,
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
        print(build_generated_skill_checklist_show_output(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
