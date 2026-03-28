#!/usr/bin/env python3

import argparse
import json
import os

from agent.skill_selection import (
    build_skill_selection_report,
    collect_available_skills,
    select_skill_for_task,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.join(BASE_DIR, "pending_approvals.json")
DEFAULT_SKILLS_DIR = os.path.join(BASE_DIR, "skills")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select one builtin or generated skill for a task")
    parser.add_argument("--task", required=True, help="task description")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE, help="reference path used to resolve runtime-data root")
    parser.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR, help="builtin skills directory")
    args = parser.parse_args(argv)

    available_skills = collect_available_skills(
        reference=args.reference,
        skills_dir=args.skills_dir,
    )
    selection = select_skill_for_task(
        task_description=args.task,
        available_skills=available_skills,
        reference=args.reference,
        skills_dir=args.skills_dir,
    )
    print(json.dumps(build_skill_selection_report(selection), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
