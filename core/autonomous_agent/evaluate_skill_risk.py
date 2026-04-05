#!/usr/bin/env python3
"""
evaluate_skill_risk.py -- evaluate generated skill risk and recommended stage path
"""

import argparse
import os

from agent.risk_evaluator import build_risk_report


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate generated skill risk and stage skip recommendations"
    )
    parser.add_argument("skill_id", help="generated skill id")
    parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="reference path used to resolve runtime-data root",
    )
    args = parser.parse_args(argv)
    print(build_risk_report(args.skill_id, reference=args.reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
