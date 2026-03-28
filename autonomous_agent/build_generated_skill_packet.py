#!/usr/bin/env python3
"""
build_generated_skill_packet.py -- build/show generated skill promotion packets
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_promotion_packet_report,
    save_generated_skill_promotion_packet,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_packet_show_output(
    skill_id: str,
    *,
    reference: str | None = None,
) -> str:
    return build_generated_skill_promotion_packet_report(skill_id, reference=reference or DEFAULT_REFERENCE)


def _build_packet_build_output(result: dict) -> str:
    packet = result["packet"]
    assessment = packet["promotion_assessment"]
    return "\n".join(
        [
            "generated skill promotion packet saved",
            f"- skill_id: {packet['skill_id']}",
            f"- criteria_check_passed: {assessment['criteria_check_passed']}",
            f"- blockers: {len(assessment['blockers'])}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or view generated skill promotion packets")
    subparsers = parser.add_subparsers(dest="command")

    build_parser = subparsers.add_parser("build", help="build and save a generated skill promotion packet")
    build_parser.add_argument("skill_id", help="generated skill id")
    build_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show a saved generated skill promotion packet")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            result = save_generated_skill_promotion_packet(args.skill_id, reference=args.reference)
        except ValueError as exc:
            print(str(exc))
            return 1
        print(_build_packet_build_output(result))
        return 0

    if args.command == "show":
        print(build_generated_skill_packet_show_output(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
