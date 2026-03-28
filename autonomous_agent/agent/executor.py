"""
executor.py — 행동 실행기

역할:
- planner가 결정한 action을 실제로 실행
- fallback 리포트/retention/metrics는 전용 모듈에 위임
- 실행 결과를 구조화하여 반환
"""

import os
import time
from datetime import datetime

from .report_fallbacks import (
    build_change_summary_lines,
    build_memory_analysis_lines,
    build_report_only_lines,
    headline_summary,
)
from .report_retention import read_latest_signature, write_report_with_retention
from .skill_loader import load_skills
from .workspace_metrics import (
    build_operational_risk_signal,
    build_operational_signal,
    build_report_summary_payload,
    compute_state_diff,
    scan_workspace,
)


class Executor:
    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    def execute(self, action: dict) -> dict:
        """action 딕셔너리를 받아 실행하고 결과를 반환."""
        action_type = action.get("type", "unknown")
        print(f"[Executor] 실행: {action['description']}")

        dispatch = {
            "analyze": self._do_analyze,
            "organize": self._do_organize,
            "create": self._do_create,
            "report": self._do_report,
            "change_summarizer": self._do_change_summarizer,
            "memory_analyzer": self._do_memory_analyzer,
            "noop": self._do_noop,
            "wait": self._do_wait,
        }

        handler = dispatch.get(action_type, self._do_unknown)
        start = time.time()

        try:
            result = handler(action)
            result["success"] = True
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "output": f"실행 실패: {e}",
            }

        result["elapsed_seconds"] = round(time.time() - start, 3)
        result["executed_at"] = datetime.now().isoformat()
        return result

    def scan_workspace(self) -> dict:
        """워크스페이스의 현재 상태를 스캔하여 반환."""
        return scan_workspace(self.workspace)

    @staticmethod
    def _empty_state_diff() -> dict:
        return {
            "full_changed": False,
            "decision_changed": False,
            "self_artifact_changed": False,
            "external_changed": False,
            "added_paths": [],
            "removed_paths": [],
            "added_self_artifacts": [],
            "removed_self_artifacts": [],
            "added_external_paths": [],
            "removed_external_paths": [],
        }

    def _build_result_meta(
        self,
        action: dict,
        current_state: dict | None = None,
        *,
        output_created: bool = False,
        new_insight: bool = False,
        specific_findings: bool = False,
        is_skip_or_noop: bool = False,
        work_type: str | None = None,
    ) -> dict:
        previous_state = action.get("previous_state_snapshot") or {}
        if current_state and current_state.get("state_diff"):
            state_diff = dict(current_state["state_diff"])
        elif current_state or previous_state:
            state_diff = compute_state_diff(previous_state, current_state)
        else:
            state_diff = self._empty_state_diff()

        action_source = action.get("action_source")
        if not action_source:
            action_source = "fallback" if action.get("source") == "cooldown_fallback" else "normal"

        recent_history = action.get("recent_history", [])[-2:]
        previous_work_types = [
            entry.get("work_type")
            or entry.get("action", {}).get("skill_name")
            or entry.get("action", {}).get("fallback_kind")
            or entry.get("action", {}).get("type")
            for entry in recent_history
        ]
        target_work_type = work_type or action.get("fallback_kind") or action.get("skill_name") or action.get("type")

        return {
            "action_source": action_source,
            "is_normal_skill": action_source in {"normal", "cooldown_reopen"} and action.get("type") == "skill",
            "output_created": output_created,
            "new_insight": new_insight,
            "specific_findings": specific_findings,
            "decision_changed": state_diff["decision_changed"],
            "self_artifact_changed": state_diff["self_artifact_changed"],
            "external_changed": state_diff["external_changed"],
            "is_skip_or_noop": is_skip_or_noop,
            "work_type": target_work_type,
            "work_type_changed": bool(target_work_type) and target_work_type not in previous_work_types,
            "recent_fallback_count": sum(
                1 for entry in recent_history
                if entry.get("event") == "fallback"
                or entry.get("action", {}).get("source") == "cooldown_fallback"
                or entry.get("action_source") == "fallback"
            ),
            "state_diff": state_diff,
        }

    def _do_analyze(self, action: dict) -> dict:
        """워크스페이스 분석을 수행."""
        state = self.scan_workspace()
        summary = (
            f"파일 {state['total_files']}개, "
            f"디렉토리 {state['total_dirs']}개, "
            f"총 {state['total_size_bytes']:,} bytes"
        )
        return {
            "output": summary,
            "ext_counts": state.get("ext_counts", {}),
            "state_snapshot": state,
            "meta": self._build_result_meta(
                action,
                state,
                output_created=False,
                new_insight=bool(state.get("ext_counts")),
                specific_findings=bool(state.get("files")),
                work_type=action.get("type", "analyze"),
            ),
        }

    def _do_organize(self, action: dict) -> dict:
        """워크스페이스 정리 — 빈 디렉토리 탐지, 구조 제안."""
        state = self.scan_workspace()
        empty_dirs = []

        for d in state["dirs"]:
            full = os.path.join(self.workspace, d)
            if os.path.isdir(full) and not os.listdir(full):
                empty_dirs.append(d)

        suggestions = []
        if empty_dirs:
            suggestions.append(f"빈 디렉토리 발견: {empty_dirs}")

        return {
            "output": f"정리 분석 완료. 제안 {len(suggestions)}건",
            "empty_dirs": empty_dirs,
            "suggestions": suggestions,
            "state_snapshot": state,
            "meta": self._build_result_meta(
                action,
                state,
                output_created=False,
                new_insight=bool(suggestions),
                specific_findings=bool(empty_dirs),
                work_type=action.get("type", "organize"),
            ),
        }

    def _do_create(self, action: dict) -> dict:
        """목표에 기반한 파일 생성."""
        goal = action.get("goal", "")
        state = self.scan_workspace()
        filename = f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = os.path.join(self.workspace, filename)
        top_files = state["files"][:5]

        summary_line = (
            f"현재 워크스페이스에는 파일 {state['total_files']}개, "
            f"디렉토리 {state['total_dirs']}개가 있으며 "
            f"목표는 '{goal or '미지정'}' 입니다."
        )
        next_actions = [
            "목표에 직접 연결되는 스킬 cooldown 해제 여부를 확인한다.",
            "필요하면 상태 보고서(report) 또는 분석(analyze) 행동으로 현재 정보를 보강한다.",
            "생성된 초안을 기반으로 사용자가 원하는 산출물 형식으로 구체화한다.",
        ]
        if top_files:
            next_actions[1] = f"관련 파일 우선 검토: {', '.join(top_files[:3])}"

        lines = [
            "# Auto-generated",
            "",
            "## 요약",
            summary_line,
            "",
            "## 현재 상태",
            f"- 목표: {goal or '미지정'}",
            f"- 생성 시각: {datetime.now().isoformat()}",
            f"- 파일 수: {state['total_files']}",
            f"- 디렉토리 수: {state['total_dirs']}",
            f"- 총 크기: {state['total_size_bytes']:,} bytes",
            "",
        ]
        if top_files:
            lines.append("### 참고 파일")
            for path in top_files:
                lines.append(f"- {path}")
            lines.append("")

        lines += [
            "## 다음 액션 제안",
            f"1. {next_actions[0]}",
            f"2. {next_actions[1]}",
            f"3. {next_actions[2]}",
            "",
        ]

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return {
            "output": f"파일 생성: {filename}",
            "created_file": filename,
            "state_snapshot": state,
            "meta": self._build_result_meta(
                action,
                state,
                output_created=True,
                new_insight=False,
                specific_findings=bool(top_files),
                work_type=action.get("type", "create"),
            ),
        }

    def _do_report(self, action: dict) -> dict:
        """현재 상태 기반 핵심 요약 보고서 생성."""
        state = self.scan_workspace()
        skills_dir = os.path.join(self.workspace, "skills")
        skills = load_skills(skills_dir) if os.path.isdir(skills_dir) else []
        risk_signal = build_operational_risk_signal(self.workspace, state.get("decision_files", []))
        operational_signal = build_operational_signal([], risk_signal=risk_signal, skills=skills)
        review_summary = build_report_summary_payload(operational_signal, risk_signal=risk_signal)
        lines, signature = build_report_only_lines(state, review_summary=review_summary)
        previous_signature = read_latest_signature(self.workspace, "report_")

        if previous_signature == signature:
            return {
                "output": headline_summary("no change -> report skipped"),
                "report_skipped": True,
                "state_snapshot": state,
                "review_summary": review_summary,
                "meta": self._build_result_meta(
                    action,
                    state,
                    output_created=False,
                    new_insight=False,
                    specific_findings=False,
                    is_skip_or_noop=True,
                    work_type="report_only",
                ),
            }

        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        saved = write_report_with_retention(self.workspace, filename, lines)
        retention = saved["retention"]
        return {
            "output": headline_summary(
                f"state changed -> report generated ({saved['report_file']})"
                + (f", archived {retention['archived']} old file(s)" if retention["archived"] else "")
            ),
            "report_file": saved["report_file"],
            "state_snapshot": state,
            "review_summary": review_summary,
            "meta": self._build_result_meta(
                action,
                state,
                output_created=True,
                new_insight=bool(state.get("state_diff", {}).get("external_changed")),
                specific_findings=bool(state.get("state_diff", {}).get("added_external_paths")),
                work_type="report_only",
            ),
        }

    def _do_change_summarizer(self, action: dict) -> dict:
        """최근 상태 변화 요약 보고서 생성."""
        current_state = action.get("current_state_snapshot") or self.scan_workspace()
        previous_state = action.get("previous_state_snapshot") or {}
        lines, stats = build_change_summary_lines(current_state, previous_state)
        total_changes = stats["added_count"] + stats["removed_count"]

        if total_changes < 1:
            return {
                "output": headline_summary("no change -> change summary skipped"),
                "report_skipped": True,
                "state_snapshot": current_state,
                "meta": self._build_result_meta(
                    action,
                    current_state,
                    output_created=False,
                    new_insight=False,
                    specific_findings=False,
                    is_skip_or_noop=True,
                    work_type="change_summarizer",
                ),
            }

        filename = f"change_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        saved = write_report_with_retention(self.workspace, filename, lines)
        retention = saved["retention"]
        return {
            "output": headline_summary(
                f"{stats['added_count']} added, {stats['removed_count']} removed -> change summary generated ({saved['report_file']})"
                + (f", archived {retention['archived']} old file(s)" if retention["archived"] else "")
            ),
            "report_file": saved["report_file"],
            "state_snapshot": current_state,
            "meta": self._build_result_meta(
                action,
                current_state,
                output_created=True,
                new_insight=bool(current_state.get("state_diff", {}).get("external_changed")),
                specific_findings=bool(current_state.get("state_diff", {}).get("added_external_paths")),
                work_type="change_summarizer",
            ),
        }

    def _do_memory_analyzer(self, action: dict) -> dict:
        """최근 행동/반복 패턴 분석 보고서 생성."""
        history = action.get("recent_history", [])
        recent_actions = action.get("recent_actions", [])
        if len(recent_actions) < 5:
            return {
                "output": headline_summary("recent_actions < 5 -> memory analysis skipped"),
                "report_skipped": True,
                "meta": self._build_result_meta(
                    action,
                    output_created=False,
                    new_insight=False,
                    specific_findings=False,
                    is_skip_or_noop=True,
                    work_type="memory_analyzer",
                ),
            }

        filename = f"memory_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        lines = build_memory_analysis_lines(history, recent_actions)
        saved = write_report_with_retention(self.workspace, filename, lines)
        retention = saved["retention"]
        return {
            "output": headline_summary(
                f"{len(history)} history entries analyzed -> memory analysis generated ({saved['report_file']})"
                + (f", archived {retention['archived']} old file(s)" if retention["archived"] else "")
            ),
            "report_file": saved["report_file"],
            "meta": self._build_result_meta(
                action,
                output_created=True,
                new_insight=True,
                specific_findings=True,
                work_type="memory_analyzer",
            ),
        }

    def _do_unknown(self, action: dict) -> dict:
        return {
            "output": f"알 수 없는 행동 유형: {action.get('type')}",
            "meta": self._build_result_meta(action, is_skip_or_noop=True, work_type=action.get("type", "unknown")),
        }

    def _do_noop(self, action: dict) -> dict:
        return {
            "output": action.get("reason") or "실행 가능한 스킬이 없어 이번 사이클을 생략합니다.",
            "meta": self._build_result_meta(action, is_skip_or_noop=True, work_type="noop"),
        }

    def _do_wait(self, action: dict) -> dict:
        return {
            "output": action.get("reason") or "모든 스킬이 cooldown 상태라 다음 사이클까지 대기합니다.",
            "meta": self._build_result_meta(action, is_skip_or_noop=True, work_type="wait"),
        }
