"""
daemon.py — Runtime/Daemon Layer

역할:
- AgentLoop를 감싸서 상시 실행 프로세스로 관리
- 예외 발생 시 자동 재시작 (지수 백오프)
- Ollama 헬스체크 (주기적)
- 위험 행동 발생 전 승인 대기 (pending_approvals.json)
- PID 파일 관리 (중복 실행 방지)
- SIGTERM / SIGINT / KeyboardInterrupt 우아한 종료

기존 구조 변경 없음: loop.py에 pre_execute_hook 콜백만 주입
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger("daemon")


class DaemonRunner:
    """
    AgentLoop를 무한 실행하는 데몬.

    실행 흐름:
      run_forever()
        └─ [health_check → run 1 cycle → sleep interval] × ∞
               ↑ 예외 시 restart_delay 후 재시작 (최대 max_restart_attempts)
    """

    def __init__(self, config: dict, base_dir: str = "."):
        self.base_dir   = base_dir
        self.cfg        = config.get("daemon", {})

        self.interval        = self.cfg.get("interval_seconds", 300)
        self.max_restarts    = self.cfg.get("max_restart_attempts", 5)
        self.restart_delay   = self.cfg.get("restart_delay_seconds", 30)
        self.health_interval = self.cfg.get("health_check_interval_seconds", 60)
        self.pid_file        = os.path.join(base_dir, self.cfg.get("pid_file", "agent.pid"))
        self.dangerous_types = set(self.cfg.get("dangerous_action_types", []))
        self.approval_file   = os.path.join(base_dir, self.cfg.get("approval_file", "pending_approvals.json"))
        self.approval_timeout= self.cfg.get("approval_timeout_seconds", 120)

        self._running        = False
        self._restart_count  = 0
        self._last_health_at = 0.0
        self._full_config    = config   # LLMAdapter 생성에 필요

    # ══════════════════════════════════════════════════
    # 공개 API
    # ══════════════════════════════════════════════════

    def run_forever(self) -> None:
        """상시 실행 루프 시작."""
        self._setup_signals()
        self._write_pid()
        self._running = True
        self._restart_count = 0

        logger.info("=" * 58)
        logger.info("  Daemon 시작 — 상시 자율 에이전트")
        logger.info(f"  PID: {os.getpid()}  |  interval: {self.interval}s")
        logger.info("=" * 58)
        print(f"\n[Daemon] PID {os.getpid()} — 실행 중 (Ctrl+C로 중지)\n")

        try:
            while self._running:
                self._tick()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def run_once(self) -> dict:
        """사이클 1회 실행 후 결과 반환 (테스트 용도)."""
        return self._run_agent_cycle()

    # ══════════════════════════════════════════════════
    # 내부 — 메인 틱
    # ══════════════════════════════════════════════════

    def _tick(self) -> None:
        """한 번의 실행 주기: 헬스체크 → 에이전트 사이클 → 슬립."""
        # 헬스체크 (interval마다)
        now = time.time()
        if now - self._last_health_at >= self.health_interval:
            self._health_check()
            self._last_health_at = time.time()

        # 에이전트 1사이클 실행
        try:
            result = self._run_agent_cycle()
            self._restart_count = 0  # 성공 시 카운터 초기화
            logger.info(
                f"[Daemon] 사이클 완료 — "
                f"점수: {result.get('trend', {}).get('avg_score', '?')} "
                f"| 추세: {result.get('trend', {}).get('trend', '?')}"
            )
        except Exception as e:
            self._handle_crash(e)
            return

        # 다음 실행까지 대기 (sleep을 짧게 쪼개서 SIGTERM에 반응)
        self._interruptible_sleep(self.interval)

    def _run_agent_cycle(self) -> dict:
        """AgentLoop를 1사이클 실행. pre_execute_hook 주입."""
        # 여기서 import — 순환 방지 및 재시작마다 fresh 인스턴스
        from .loop import AgentLoop
        config_path = os.path.join(self.base_dir, "config.json")
        agent = AgentLoop(
            config_file=config_path,
            max_cycles=1,
            pre_execute_hook=self._safety_gate,
        )
        return agent.run()

    # ══════════════════════════════════════════════════
    # 안전장치 (Safety Gate)
    # ══════════════════════════════════════════════════

    def _safety_gate(self, action: dict) -> bool:
        """
        위험 행동 전 승인을 요청한다.
        반환: True = 실행 허용, False = 이번 사이클 스킵
        """
        action_type = action.get("type", "")
        if action_type not in self.dangerous_types:
            return True  # 안전 행동 → 즉시 허용

        # ── 승인 요청 파일 기록 ──
        pending = {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": "pending",  # "approved" | "rejected" 로 변경하면 진행
            "timeout_seconds": self.approval_timeout,
        }
        with open(self.approval_file, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)

        logger.warning(
            f"[SafetyGate] ⚠️  위험 행동 감지: [{action_type}] {action.get('description')}\n"
            f"  승인 대기 중... ({self.approval_file} 에서 status를 'approved'로 변경)\n"
            f"  타임아웃: {self.approval_timeout}초"
        )
        print(f"\n⚠️  [SafetyGate] 위험 행동 승인 필요: [{action_type}]")
        print(f"   파일 수정으로 승인: {self.approval_file}")
        print(f"   → status 를 'approved' 로 변경하면 실행됩니다.\n")

        # ── 타임아웃까지 폴링 ──
        deadline = time.time() + self.approval_timeout
        while time.time() < deadline:
            time.sleep(3)
            try:
                with open(self.approval_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                status = data.get("status", "pending")
                if status == "approved":
                    logger.info(f"[SafetyGate] ✅ 승인됨: {action.get('description')}")
                    os.remove(self.approval_file)
                    return True
                elif status == "rejected":
                    logger.info(f"[SafetyGate] ❌ 거부됨: {action.get('description')}")
                    os.remove(self.approval_file)
                    return False
            except (json.JSONDecodeError, FileNotFoundError):
                continue

        logger.warning(f"[SafetyGate] ⏰ 타임아웃 — 행동 스킵: {action.get('description')}")
        return False

    # ══════════════════════════════════════════════════
    # 헬스체크
    # ══════════════════════════════════════════════════

    def _health_check(self) -> bool:
        """Ollama 서버 가용성 확인 후 로그."""
        import urllib.request, urllib.error
        llm_cfg  = self._full_config.get("llm", {})
        base_url = llm_cfg.get("base_url", "http://localhost:11434")
        model    = llm_cfg.get("model", "qwen3.5:9b")
        try:
            urllib.request.urlopen(f"{base_url}/api/tags", timeout=5)
            logger.info(f"[HealthCheck] ✅ Ollama OK — {model} @ {base_url}")
            return True
        except Exception as e:
            logger.warning(f"[HealthCheck] ⚠️  Ollama 미응답: {e}")
            return False

    # ══════════════════════════════════════════════════
    # 자동 재시작
    # ══════════════════════════════════════════════════

    def _handle_crash(self, exc: Exception) -> None:
        """예외 발생 시 재시작 로직 (지수 백오프)."""
        self._restart_count += 1
        delay = min(self.restart_delay * (2 ** (self._restart_count - 1)), 300)

        logger.error(
            f"[Daemon] 💥 예외 발생 (재시작 {self._restart_count}/{self.max_restarts})\n"
            f"  오류: {type(exc).__name__}: {exc}\n"
            f"  재시작 대기: {delay}초"
        )
        print(f"\n💥 [Daemon] 오류: {exc}  → {delay}초 후 재시작 "
              f"({self._restart_count}/{self.max_restarts})\n")

        if self._restart_count >= self.max_restarts:
            logger.critical(
                f"[Daemon] 최대 재시작 횟수 초과 ({self.max_restarts}회) — 중지"
            )
            print(f"\n❌ [Daemon] 재시작 한도 초과 — 에이전트 종료")
            self._running = False
            return

        self._interruptible_sleep(delay)

    # ══════════════════════════════════════════════════
    # PID / 시그널 / 종료
    # ══════════════════════════════════════════════════

    def _write_pid(self) -> None:
        """PID 파일 기록. 이미 존재하면 중복 실행 경고."""
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file) as f:
                    old_pid = int(f.read().strip())
                # 프로세스가 실제 살아있는지 확인 (Unix)
                if sys.platform != "win32":
                    try:
                        os.kill(old_pid, 0)
                        logger.warning(
                            f"[Daemon] ⚠️  이미 실행 중인 인스턴스 감지 (PID {old_pid}). "
                            "계속 진행합니다."
                        )
                    except (ProcessLookupError, PermissionError):
                        pass  # 죽은 PID → 무시
            except (ValueError, IOError):
                pass
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _setup_signals(self) -> None:
        """Unix 시그널 핸들러 등록 (Windows는 건너뜀)."""
        if sys.platform == "win32":
            return
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGHUP, self._on_signal)

    def _on_signal(self, signum: int, frame) -> None:
        logger.info(f"[Daemon] 시그널 수신: {signum} — 종료 중...")
        self._running = False

    def _shutdown(self) -> None:
        logger.info("[Daemon] 종료 완료.")
        print("\n[Daemon] 정상 종료.")
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    def _interruptible_sleep(self, seconds: float) -> None:
        """sleep을 잘게 쪼개서 _running 플래그 변경에 즉시 반응."""
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(min(1.0, end - time.time()))
