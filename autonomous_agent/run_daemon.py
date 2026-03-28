#!/usr/bin/env python3
"""
run_daemon.py — Runtime/Daemon Layer 진입점

사용법:
    python run_daemon.py                  # 상시 실행 (daemon 모드)
    python run_daemon.py --once           # 1사이클만 실행 후 종료
    python run_daemon.py --config my.json # 다른 설정 파일
    python run_daemon.py --status         # PID 파일로 실행 여부 확인

daemon 모드 동작:
  1. Ollama 헬스체크 (60초마다)
  2. AgentLoop 1사이클 실행
  3. interval_seconds 대기
  4. 예외 시 restart_delay 후 자동 재시작 (최대 max_restart_attempts)
  5. SIGTERM / Ctrl+C → 우아한 종료 + PID 파일 정리
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_status(config: dict) -> int:
    """PID 파일 기반으로 데몬 실행 여부를 출력."""
    pid_file = os.path.join(
        BASE_DIR, config.get("daemon", {}).get("pid_file", "agent.pid")
    )
    if not os.path.exists(pid_file):
        print("❌ 데몬 미실행 (PID 파일 없음)")
        return 1
    with open(pid_file) as f:
        pid = f.read().strip()
    if sys.platform != "win32":
        try:
            import signal as _sig
            os.kill(int(pid), 0)
            print(f"✅ 데몬 실행 중 (PID {pid})")
            return 0
        except (ProcessLookupError, PermissionError):
            print(f"⚠️  PID 파일 존재 ({pid}) 하지만 프로세스 없음 — 비정상 종료됐을 수 있음")
            return 1
    else:
        print(f"ℹ️  PID 파일 존재: {pid}  (Windows — 프로세스 상태 직접 확인 필요)")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="자율 에이전트 Daemon")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once",   action="store_true", help="1사이클만 실행 후 종료")
    parser.add_argument("--status", action="store_true", help="데몬 실행 여부 확인")
    args = parser.parse_args()

    config_path = os.path.join(BASE_DIR, args.config)
    config = load_config(config_path)

    if args.status:
        return cmd_status(config)

    from agent.daemon import DaemonRunner
    runner = DaemonRunner(config=config, base_dir=BASE_DIR)

    if args.once:
        print("[run_daemon] --once 모드: 1사이클 실행")
        result = runner.run_once()
        print(f"[run_daemon] 완료 — 점수: {result.get('trend', {}).get('avg_score', '?')}")
        return 0

    # 상시 실행
    runner.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
