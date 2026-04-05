#!/usr/bin/env python3
"""
suggest_auto_promotion.py -- show safe auto-promotion rule suggestions for a generated skill
"""

import argparse
import os

from agent.auto_promotion_rules import build_auto_promotion_report


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Suggest safe auto-review and checklist hints for a generated skill"
    )
    parser.add_argument("skill_id", help="generated skill id")
    parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )
    args = parser.parse_args(argv)
    print(build_auto_promotion_report(args.skill_id, reference=args.reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
