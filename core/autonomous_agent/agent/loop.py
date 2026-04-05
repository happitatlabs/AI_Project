"""
loop.py — 메인 실행 루프

역할:
- config.json에서 설정을 로드
- LLMAdapter를 생성하여 Planner에 주입
- 에이전트 사이클 관리 (Sense → Plan → Act → Evaluate → Record)
- memory, planner, executor, evaluator를 조합하여 자율 실행
"""

import json
import logging
import os
import time

from .llm_adapter import LLMAdapter
from .memory import Memory, is_skill_on_cooldown
from .planner import Planner
from .executor import Executor
from .evaluator import Evaluator
from .skill_loader import build_strict_behavior_preflight_summary, get_behavior_class_diagnostics, load_skills
from .skill_executor import SkillExecutor
from .workspace_metrics import compute_state_diff
from .workspace_metrics import (
    annotate_changes,
    build_operational_risk_signal,
    build_operational_gate_view,
    build_operational_signal,
    create_pending_approvals,
    load_pending_approvals,
    resolve_operational_gate,
)

logger = logging.getLogger("loop")


def _load_config(config_path: str) -> dict:
    """config.json 로드. 없으면 기본값 반환."""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class AgentLoop:
    def __init__(
        self,
        config_file: str = "config.json",
        # 아래 인자들은 config.json보다 우선 적용 (CLI 오버라이드용)
        workspace: str | None = None,
        memory_file: str | None = None,
        goal_file: str | None = None,
        max_cycles: int | None = None,
        cycle_delay: float | None = None,
        pre_execute_hook: "Callable[[dict], bool] | None" = None,
    ):
        cfg = _load_config(config_file)
        agent_cfg = cfg.get("agent", {})
        log_cfg = cfg.get("logging", {})
        planner_cfg = cfg.get("planner", {})
        daemon_cfg = cfg.get("daemon", {})
        skills_cfg = cfg.get("skills", {})

        # 로깅 설정
        self._setup_logging(log_cfg)

        # 설정값 결정: CLI 인자 > config.json > 하드코딩 기본값
        self.workspace   = workspace   or agent_cfg.get("workspace", ".")
        self.memory_file = memory_file or agent_cfg.get("memory_file", "agent_memory.json")
        self.goal_file   = goal_file   or agent_cfg.get("goal_file", "agent_goal.md")
        self.max_cycles  = max_cycles  or agent_cfg.get("max_cycles", 5)
        self.cycle_delay = cycle_delay if cycle_delay is not None else agent_cfg.get("cycle_delay", 1.0)
        self.approval_file = os.path.join(
            os.path.dirname(os.path.abspath(config_file)) or os.getcwd(),
            daemon_cfg.get("approval_file", "pending_approvals.json"),
        )

        # LLMAdapter 생성 및 가용성 체크
        llm_cfg = cfg.get("llm", {})
        fallback = llm_cfg.get("fallback_to_rules", True)
        self.llm = LLMAdapter(
            provider=llm_cfg.get("provider", "ollama"),
            base_url=llm_cfg.get("base_url", "http://localhost:11434"),
            model=llm_cfg.get("model", "qwen3.5:9b"),
            timeout=llm_cfg.get("timeout", 60),
        )

        # --no-llm 플래그 지원 (환경변수로 전달됨)
        if os.environ.get("AGENT_NO_LLM") == "1":
            print(f"[Loop] ⚠️  --no-llm 플래그 → LLM 비활성화, 규칙 기반으로 실행")
            self.llm = None
        elif self.llm.is_available():
            print(f"[Loop] ✅ LLM 연결 확인 — {self.llm.model} @ {self.llm.base_url}")
        else:
            msg = (
                f"[Loop] ⚠️  Ollama 미연결 ({self.llm.get_last_error()})\n"
                f"       모델: {self.llm.model}\n"
                f"       실행: ollama serve && ollama pull {self.llm.model}"
            )
            if fallback:
                print(msg + "\n       → 규칙 기반 fallback으로 계속 실행합니다.")
                self.llm = None  # Planner에 None 주입 → fallback 경로로 실행
            else:
                raise RuntimeError(
                    f"Ollama 연결 필수. {msg}\n"
                    "config.json의 llm.fallback_to_rules를 true로 설정하면 "
                    "오프라인에서도 실행됩니다."
                )

        # 모듈 초기화
        self.memory             = Memory(filepath=self.memory_file)
        self.planner            = Planner(
            goal_file=self.goal_file,
            llm=self.llm,
            skill_cooldowns=planner_cfg.get("skill_cooldowns"),
            same_skill_block_cycles=planner_cfg.get("same_skill_block_cycles", 1),
        )
        self.executor           = Executor(workspace=self.workspace)
        self.evaluator          = Evaluator()
        self.pre_execute_hook   = pre_execute_hook  # (action) -> bool | None
        self.strict_behavior_class = bool(skills_cfg.get("strict_behavior_class", False))
        # 스킬 시스템
        skills_dir              = os.path.join(os.path.dirname(config_file), "skills") \
                                  if config_file != "config.json" \
                                  else os.path.join(os.getcwd(), "skills")
        self.skills             = load_skills(
            skills_dir,
            strict_behavior_class=self.strict_behavior_class,
        )
        self.skill_loader_diagnostics = get_behavior_class_diagnostics(self.skills)
        self.skill_executor     = SkillExecutor(self.executor)
        if self.skills:
            logger.info(f"[Loop] 스킬 {len(self.skills)}개 로드: "
                        f"{[s['name'] for s in self.skills]}")
            logger.info(
                "[Loop] behavior_class strict=%s fallback_skills=%s",
                self.strict_behavior_class,
                self.skill_loader_diagnostics.get("fallback_skills", []),
            )

    # ── 로깅 설정 ──────────────────────────────────────

    @staticmethod
    def _setup_logging(cfg: dict) -> None:
        level_str = cfg.get("level", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)
        log_file = cfg.get("log_file")

        handlers: list[logging.Handler] = [logging.StreamHandler()]
        if log_file:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            handlers=handlers,
            force=True,
        )

    # ── 메인 루프 ──────────────────────────────────────

    def run(self) -> dict:
        """메인 에이전트 루프를 실행."""
        mode = f"LLM ({self.llm.model})" if self.llm else "규칙 기반 (fallback)"
        print("=" * 60)
        print(f"  자율 발전 에이전트 MVP")
        print(f"  모드: {mode}")
        print("=" * 60)

        self.memory.load()

        goals = self.planner.load_goals()
        self.memory.set_goals(goals)
        print(f"\n[Loop] 목표 {len(goals)}개 로드됨:")
        for i, g in enumerate(goals, 1):
            print(f"  {i}. {g}")
        print(f"[Loop] behavior_class strict mode: {'on' if self.strict_behavior_class else 'off'}")

        cycle_results = []

        for cycle in range(1, self.max_cycles + 1):
            cycle_num = self.memory.increment_cycle()
            print(f"\n{'─' * 50}")
            print(f"  사이클 #{cycle_num}  [{mode}]")
            print(f"{'─' * 50}")

            # Step 1: Sense
            print("\n[1/5] 상태 스캔 중...")
            previous_state = self.memory.data.get("last_state", {})
            current_state = self.executor.scan_workspace()
            state_diff = compute_state_diff(previous_state, current_state)
            current_state["state_diff"] = state_diff
            changed_paths = state_diff.get("added_paths", []) + state_diff.get("removed_paths", [])
            change_annotations = annotate_changes(changed_paths)
            operational_risk_signal = build_operational_risk_signal(
                self.workspace,
                current_state.get("decision_files", []),
            )
            approval_entries = load_pending_approvals(self.approval_file)
            operational_signal = build_operational_signal(
                change_annotations,
                approval_entries=approval_entries,
                recent_paths=changed_paths,
                risk_signal=operational_risk_signal,
                skills=self.skills,
            )
            if operational_signal["approval"]["status"] == "review_needed":
                created = create_pending_approvals(
                    change_annotations,
                    operational_signal["summary"],
                    self.approval_file,
                    operational_signal=operational_signal,
                )
                approval_entries = created["entries"]
                operational_signal = build_operational_signal(
                    change_annotations,
                    approval_entries=approval_entries,
                    recent_paths=changed_paths,
                    risk_signal=operational_risk_signal,
                    skills=self.skills,
                )
            operational_gate = resolve_operational_gate(operational_signal)
            operational_gate_view = build_operational_gate_view(
                operational_signal,
                operational_gate,
            )
            current_state["change_annotations"] = change_annotations
            current_state["operational_risk_signal"] = operational_risk_signal
            current_state["operational_signal"] = operational_signal
            current_state["operational_gate"] = operational_gate
            current_state["operational_gate_view"] = operational_gate_view
            current_state["skill_loader"] = {
                "strict_behavior_class": self.strict_behavior_class,
                **self.skill_loader_diagnostics,
                "strict_preflight": build_strict_behavior_preflight_summary(
                    self.skills,
                    risk_signal=operational_risk_signal,
                ),
            }
            self.memory.set_state(current_state)
            print(f"  → 파일 {current_state['total_files']}개, "
                  f"디렉토리 {current_state['total_dirs']}개")
            if operational_gate["mode"] != "ignore":
                gate_target = operational_gate_view.get("target") or "-"
                print(
                    f"  → 운영 게이트: {operational_gate_view['gate_mode']} "
                    f"({operational_gate_view['approval_status']}, "
                    f"target={gate_target}, "
                    f"action={operational_gate_view['recommended_action']})"
                )

            # Step 2: Plan — gap 분석
            print("[2/5] Gap 분석 중...")
            actions = self.planner.analyze_gap(goals, current_state)
            src_tag = actions[0].get("source", "?") if actions else "?"
            print(f"  → {len(actions)}개 행동 도출 (source: {src_tag})")

            # Step 3: Plan — 스킬 선택 or 기존 행동 선택
            print("[3/5] 다음 행동 선택 중...")
            recent_history = self.memory.get_recent_history(10)
            current_state["recent_history"] = recent_history[-5:]
            used_skill     = None   # 이번 사이클에 실행한 스킬 (없으면 None)
            planned_action = None

            # ── 스킬 시스템이 있으면 먼저 시도 ──
            if self.skills:
                recent_actions = self.memory.get_recent_actions(skill_cooldowns=self.planner.skill_cooldowns)
                skill_choice = self.planner.pick_skill(
                    goals, current_state, self.skills,
                    recent_actions=recent_actions,
                )
                if skill_choice:
                    sname = skill_choice.get("skill")
                    sreason = skill_choice.get("reason", "")

                    if sname:
                        # 반복 방지 hard-gate: planner와 동일 기준으로 최종 검증
                        if self.planner.is_skill_blocked(sname, recent_actions, self.skills, source=skill_choice.get("source", "normal")):
                            logger.info(f"[Loop] {sname}: planner/loop 공통 기준으로 차단")
                            print(f"  → [SKIP] {sname}: 최근 실행됨 또는 same-skill 규칙으로 제외")
                            skill_choice = None
                    elif skill_choice.get("action"):
                        planned_action = skill_choice["action"]
                        planned_action["recent_history"] = recent_history[-5:]
                        planned_action["recent_actions"] = recent_actions[-5:]
                        planned_action["current_state_snapshot"] = current_state
                        planned_action["previous_state_snapshot"] = previous_state
                        planned_action["current_state_diff"] = state_diff
                        fallback_name = skill_choice.get("fallback", planned_action.get("type", "fallback"))
                        print(f"  → [FALLBACK:{fallback_name}] {planned_action['description']}")

                if skill_choice and skill_choice.get("skill"):
                    sname  = skill_choice["skill"]
                    sreason= skill_choice.get("reason", "")
                    skill_def = next(
                        (s for s in self.skills if s["name"] == sname), None
                    )
                    if skill_def:
                        print(f"  → [SKILL] {sname}  ({sreason})")
                        used_skill = sname
                        # Step 4: 스킬 실행
                        print("[4/5] 스킬 실행 중...")
                        skill_result = self.skill_executor.run(skill_def)
                        if skill_result["blocked_reason"]:
                            output_text = f"스킬 차단: {skill_result['blocked_reason']}"
                            result = {"success": False, "output": output_text,
                                      "elapsed_seconds": 0}
                        else:
                            steps_ok = sum(1 for r in skill_result["steps_results"] if r["ok"])
                            output_text = (
                                f"스킬 '{sname}' 완료 "
                                f"({steps_ok}/{len(skill_result['steps_results'])} steps) "
                                + (f"→ {skill_result['output_file']}"
                                   if skill_result["output_file"] else "")
                            )
                            result = {
                                "success": skill_result["success"],
                                "output": output_text,
                                "elapsed_seconds": 0,
                                "report_file": skill_result.get("output_file"),
                                "meta": {
                                    "action_source": skill_choice.get("source", "normal"),
                                    "is_normal_skill": skill_choice.get("source", "normal") in {"normal", "cooldown_reopen"},
                                    "output_created": bool(skill_result.get("output_file")),
                                    "new_insight": bool(state_diff.get("external_changed")),
                                    "specific_findings": sname in {"workspace_reporter", "file_classifier", "code_reviewer"},
                                    "decision_changed": state_diff["decision_changed"],
                                    "self_artifact_changed": state_diff["self_artifact_changed"],
                                    "external_changed": state_diff["external_changed"],
                                    "is_skip_or_noop": False,
                                    "work_type": sname,
                                    "work_type_changed": sname not in {
                                        entry.get("skill_name") or entry.get("fallback_name") or entry.get("action_type")
                                        for entry in recent_history[-2:]
                                    },
                                    "recent_fallback_count": sum(1 for entry in recent_history[-2:] if entry.get("event") == "fallback"),
                                    "state_diff": state_diff,
                                },
                            }
                        print(f"  → {result['output']}")
                        # 성공 실행 시 recent_actions에 기록 (반복 방지)
                        if skill_result["success"]:
                            self.memory.record_action(sname, summary=output_text)

                        # 스킬 실행 기록용 action 객체
                        action = {
                            "type": "skill",
                            "description": f"스킬 실행: {sname}",
                            "goal": sreason,
                            "skill_name": sname,
                            "source": skill_choice.get("source", "planner"),
                            "action_source": skill_choice.get("source", "normal"),
                            "recent_history": recent_history[-5:],
                            "current_state_snapshot": current_state,
                            "previous_state_snapshot": previous_state,
                        }
                        # Step 5로 바로 점프
                        evaluation = self.evaluator.evaluate(action, result, previous_state)
                        print(f"[5/5] 평가: {evaluation['score']}/100 ({evaluation['status']})")
                        self.memory.add_history({
                            "cycle": cycle_num, "action": action,
                            "result": {"success": result["success"],
                                       "output": result["output"],
                                       "elapsed_seconds": 0,
                                       "report_file": result.get("report_file"),
                                       "meta": result.get("meta", {})},
                            "evaluation": evaluation,
                            "llm_mode": self.llm is not None,
                        })
                        self.memory.save()
                        print(self.memory.log_storage_status())
                        cycle_results.append({
                            "cycle": cycle_num, "action": action,
                            "result": result, "evaluation": evaluation,
                        })
                        if cycle < self.max_cycles:
                            time.sleep(self.cycle_delay)
                        continue  # 다음 사이클로

            # ── 스킬 없거나 선택 실패(noop) → 기존 executor 경로 ──
            if self.skills and used_skill is None and planned_action is None:
                print("  → [NOOP] 적합 스킬 없음 — executor 기본 행동 실행")
            action = planned_action or self.planner.pick_next_action(actions, recent_history)

            if action is None:
                print("  → 수행할 행동 없음. 루프 종료.")
                break

            action.setdefault("recent_history", recent_history[-5:])
            action.setdefault("current_state_snapshot", current_state)
            action.setdefault("previous_state_snapshot", previous_state)
            action.setdefault("current_state_diff", state_diff)
            action.setdefault(
                "action_source",
                "fallback" if action.get("source") == "cooldown_fallback" else "normal",
            )

            src = action.get("source", "?")
            reason = action.get("reason", "")
            print(f"  → [{action['type']}] {action['description']}")
            if reason:
                print(f"     이유: {reason}  (source: {src})")

            # Step 4: Act (안전장치 훅 먼저 실행)
            print("[4/5] 행동 실행 중...")
            if self.pre_execute_hook is not None:
                allowed = self.pre_execute_hook(action)
                if not allowed:
                    print("  → [SafetyGate] 실행 거부/타임아웃 — 이번 사이클 스킵")
                    continue
            result = self.executor.execute(action)
            print(f"  → 결과: {result['output']}")
            if result.get("success") and action.get("source") == "cooldown_fallback":
                fallback_name = action.get("fallback_kind", action.get("type", "fallback"))
                self.memory.record_action(fallback_name, summary=result["output"])

            # Step 5: Evaluate
            print("[5/5] 결과 평가 중...")
            evaluation = self.evaluator.evaluate(action, result, previous_state)
            print(f"  → 점수: {evaluation['score']}/100 "
                  f"({evaluation['status']}) — {evaluation['reason']}")

            history_entry = {
                "cycle": cycle_num,
                "action": action,
                "result": {
                    "success": result["success"],
                    "output": result["output"],
                    "elapsed_seconds": result["elapsed_seconds"],
                    "report_file": result.get("report_file"),
                    "created_file": result.get("created_file"),
                    "meta": result.get("meta", {}),
                },
                "evaluation": evaluation,
                "llm_mode": self.llm is not None,
            }
            self.memory.add_history(history_entry)
            self.memory.save()
            print(self.memory.log_storage_status())
            cycle_results.append(history_entry)

            if cycle < self.max_cycles:
                time.sleep(self.cycle_delay)

        trend = self.memory.get_score_trend()
        print(f"\n{'=' * 60}")
        print(f"  실행 완료")
        print(f"  총 사이클: {len(cycle_results)} | "
              f"평균 점수: {trend['avg_score']} | "
              f"추세: {trend['trend']}")
        print(f"{'=' * 60}")

        self.memory.save()

        return {
            "total_cycles": len(cycle_results),
            "cycle_results": cycle_results,
            "trend": trend,
            "final_state": self.memory.data["last_state"],
            "llm_mode": self.llm is not None,
        }
