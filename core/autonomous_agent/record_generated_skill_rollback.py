#!/usr/bin/env python3
"""
record_generated_skill_rollback.py -- record/view generated skill rollback records
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_rollback_report,
    save_generated_skill_rollback_record,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_rollback_show_output(
    skill_id: str,
    *,
    reference: str | None = None,
) -> str:
    return build_generated_skill_rollback_report(
        skill_id,
        reference=reference or DEFAULT_REFERENCE,
    )


def _build_write_output(result: dict) -> str:
    rollback = result["rollback"]
    return "\n".join(
        [
            "generated skill rollback record saved",
            f"- skill_id: {rollback['skill_id']}",
            f"- operator: {rollback['operator']}",
            f"- rolled_back_at: {rollback['rolled_back_at']}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or view generated skill rollback records")
    subparsers = parser.add_subparsers(dest="command")

    write_parser = subparsers.add_parser("write", help="write a generated skill rollback record")
    write_parser.add_argument("skill_id", help="generated skill id")
    write_parser.add_argument("--operator", required=True, help="operator name")
    write_parser.add_argument("--reason", required=True, help="rollback reason")
    write_parser.add_argument("--production-artifact-ref", required=True, help="production artifact reference")
    write_parser.add_argument("--candidate-artifact-ref", required=True, help="candidate artifact reference")
    write_parser.add_argument("--rollback-reference", help="optional rollback reference")
    write_parser.add_argument("--note", action="append", default=[], help="optional rollback note")
    write_parser.add_argument("--allow-replace", action="store_true", help="replace an existing rollback record")
    write_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show a generated skill rollback record")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "write":
        try:
            result = save_generated_skill_rollback_record(
                args.skill_id,
                operator=args.operator,
                reason=args.reason,
                production_artifact_ref=args.production_artifact_ref,
                candidate_artifact_ref=args.candidate_artifact_ref,
                rollback_reference=args.rollback_reference,
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
        print(build_generated_skill_rollback_show_output(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
