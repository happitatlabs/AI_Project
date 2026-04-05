#!/usr/bin/env python3
"""
build_generated_skill_transform.py -- build/show generated skill manual transform templates
"""

import argparse
import os

from agent.generated_skill_sandbox import (
    build_generated_skill_transform_template_report,
    save_generated_skill_transform_template,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def build_generated_skill_transform_show_output(
    skill_id: str,
    *,
    reference: str | None = None,
) -> str:
    return build_generated_skill_transform_template_report(skill_id, reference=reference or DEFAULT_REFERENCE)


def _build_transform_build_output(result: dict) -> str:
    template = result["template"]
    return "\n".join(
        [
            "generated skill transform template saved",
            f"- skill_id: {template['skill_id']}",
            f"- build_warnings: {len(template.get('build_warnings', []))}",
            f"- path: {result['path']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or view generated skill manual transform templates")
    subparsers = parser.add_subparsers(dest="command")

    build_parser = subparsers.add_parser("build", help="build and save a generated skill transform template")
    build_parser.add_argument("skill_id", help="generated skill id")
    build_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    show_parser = subparsers.add_parser("show", help="show a saved generated skill transform template")
    show_parser.add_argument("skill_id", help="generated skill id")
    show_parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )

    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            result = save_generated_skill_transform_template(args.skill_id, reference=args.reference)
        except ValueError as exc:
            print(str(exc))
            return 1
        print(_build_transform_build_output(result))
        return 0

    if args.command == "show":
        print(build_generated_skill_transform_show_output(args.skill_id, reference=args.reference))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
