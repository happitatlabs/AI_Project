#!/usr/bin/env python3
"""
run_maintenance.py — Maintenance Layer 진입점

사용법:
    python run_maintenance.py              # 전체 유지보수 실행
    python run_maintenance.py --task logs  # 로그 롤링만
    python run_maintenance.py --task cleanup  # 오래된 로그 정리만
    python run_maintenance.py --task skills   # 스킬 아카이브 + 중복제거
    python run_maintenance.py --task memory   # 메모리 트리밍만
    python run_maintenance.py --dry-run    # 실제 변경 없이 대상 파일만 출력

각 작업은 독립적으로 실행 가능 (--task 선택).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TASKS = {
    "logs":    "roll_logs",
    "cleanup": "cleanup_old_logs",
    "archive": "archive_old_skills",
    "dedup":   "deduplicate_skills",
    "memory":  "trim_memory",
    "skills":  None,   # archive + dedup 묶음
    "all":     None,   # run_all()
}


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="에이전트 유지보수 도구")
    parser.add_argument("--config",  default="config.json")
    parser.add_argument("--task",    default="all",
                        choices=list(TASKS.keys()),
                        help="실행할 유지보수 작업 (기본: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="변경 없이 대상 파일만 출력 (아직 미구현 — 안전 예비용)")
    args = parser.parse_args()

    config_path = os.path.join(BASE_DIR, args.config)
    config = load_config(config_path)

    from agent.maintenance import MaintenanceRunner
    maint = MaintenanceRunner(config=config, base_dir=BASE_DIR)

    if args.dry_run:
        print("[Maintenance] --dry-run 모드: 실제 파일 변경 없음")
        print(f"  대상 로그 : {maint.log_file}")
        print(f"  로그 보관 : {maint.log_retention_days}일")
        print(f"  스킬 디렉 : {maint.skills_dir}")
        print(f"  스킬 보관 : {maint.skills_archive_days}일")
        print(f"  메모리    : {maint.memory_file} (최대 {maint.memory_max_history}개)")
        return 0

    task = args.task

    if task == "all":
        results = maint.run_all()
    elif task == "skills":
        r1 = maint.archive_old_skills()
        r2 = maint.deduplicate_skills()
        results = {"archive_old_skills": r1, "deduplicate_skills": r2}
        for k, v in results.items():
            print(f"  {k}: {v}")
    else:
        method_name = TASKS[task]
        method = getattr(maint, method_name)
        result = method()
        results = {task: result}
        print(f"  {task}: {result}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
