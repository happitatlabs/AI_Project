#!/usr/bin/env python3
"""
promote_generated_skill.py -- preview/execute/show manual generated skill promotion records
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_manual_promotion_preview_report,
    build_generated_skill_promotion_record_report,
    execute_generated_skill_manual_promotion,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def _build_execute_output(result: dict) -> str:
    candidate = result["candidate"]
    promotion = result["promotion"]
    return "\n".join(
        [
            "generated skill manual promotion executed",
            f"- skill_id: {result['skill_id']}",
            f"- candidate_path: {candidate['path']}",
            f"- promotion_path: {promotion['path']}",
            f"- final_target_name: {candidate['candidate']['target_name']}",
            f"- final_target_path: {candidate['candidate']['target_path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or execute manual generated skill promotion")
    subparsers = parser.add_subparsers(dest="command")

    preview_parser = subparsers.add_parser("preview", help="preview manual promotion readiness")
    preview_parser.add_argument("skill_id", help="generated skill id")
    preview_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    execute_parser = subparsers.add_parser("execute", help="execute manual promotion after explicit confirmation")
    execute_parser.add_argument("skill_id", help="generated skill id")
    execute_parser.add_argument("--operator", required=True, help="operator name")
    execute_parser.add_argument("--note", action="append", default=[], help="optional execution note")
    execute_parser.add_argument("--confirm-promotion", action="store_true", help="required explicit confirmation flag")
    execute_parser.add_argument("--allow-replace", action="store_true", help="replace existing candidate/promotion artifacts")
    execute_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show manual promotion record")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "preview":
        print(build_generated_skill_manual_promotion_preview_report(args.skill_id, reference=args.reference))
        return 0

    if args.command == "execute":
        if not args.confirm_promotion:
            print("manual promotion execution requires --confirm-promotion")
            return 1
        try:
            result = execute_generated_skill_manual_promotion(
                args.skill_id,
                operator=args.operator,
                confirm_promotion=True,
                notes=args.note,
                allow_replace=args.allow_replace,
                reference=args.reference,
            )
        except ValueError as exc:
            print(str(exc))
            return 1
        print(_build_execute_output(result))
        return 0

    if args.command == "show":
        print(build_generated_skill_promotion_record_report(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
