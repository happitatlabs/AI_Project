"""
skill_executor.py — 스킬 steps를 순서대로 실행

설계 원칙:
- DSL 없음: step 키워드를 기존 Executor 메서드로 매핑
- 보안 게이트: risk_level 검사 후 dangerous는 즉시 차단
- 실패한 step은 건너뛰고 다음 step 진행 (부분 성공 허용)

step 키워드 → Executor 메서드 매핑:
  scan_workspace      → executor._do_analyze
  scan_code_files     → _step_scan_code
  classify_by_extension / group_by_type → executor._do_organize
  write_report / write_review / write_classification → executor._do_report
  extract_structure   → _step_extract_structure
  suggest_actions     → executor._do_organize
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .executor import Executor
from .report_retention import write_report_with_retention
from .skill_loader import load_skills
from .workspace_metrics import (
    build_operational_risk_signal,
    build_operational_signal,
    build_report_summary_payload,
    build_review_summary_lines,
)

logger = logging.getLogger("skill_executor")

# risk_level별 실행 허용 여부
RISK_POLICY = {
    "safe":       "allow",
    "approval":   "pending",    # daemon의 safety gate에서 처리
    "dangerous":  "deny",
}

# step 첫 단어(키워드) → 내부 메서드 이름
STEP_DISPATCH = {
    "scan_workspace":          "_step_analyze",
    "scan_code_files":         "_step_scan_code",
    "classify_by_extension":   "_step_organize",
    "group_by_type":           "_step_organize",
    "write_report":            "_step_report",
    "write_review":            "_step_report",
    "write_classification":    "_step_report",
    "extract_structure":       "_step_extract_structure",
    "suggest_actions":         "_step_organize",
}


class SkillExecutor:
    def __init__(self, executor: Executor):
        self.executor = executor  # 기존 Executor 재사용

    # ── 공개 API ────────────────────────────────────────

    def run(self, skill: dict) -> dict:
        """
        파싱된 skill 딕셔너리를 받아 steps를 순서대로 실행.

        반환:
        {
          "skill": "name",
          "success": bool,
          "blocked_reason": str | None,
          "steps_results": [...],
          "output_file": str | None,
        }
        """
        name       = skill.get("name", "unknown")
        risk_level = skill.get("risk_level", "safe")
        steps      = skill.get("steps", [])

        logger.info(f"[SkillExecutor] 시작: {name}  risk={risk_level}")

        # ── 보안 게이트 ──────────────────────────────────
        policy = RISK_POLICY.get(risk_level, "deny")
        if policy == "deny":
            reason = f"risk_level='{risk_level}' — 실행 차단됨"
            logger.warning(f"[SkillExecutor] 🚫 {name}: {reason}")
            return {
                "skill": name, "success": False,
                "blocked_reason": reason,
                "steps_results": [], "output_file": None,
            }
        if policy == "pending":
            reason = f"risk_level='{risk_level}' — 승인 필요 (daemon safety gate)"
            logger.warning(f"[SkillExecutor] ⏸  {name}: {reason}")
            return {
                "skill": name, "success": False,
                "blocked_reason": reason,
                "steps_results": [], "output_file": None,
            }

        # ── steps 순서대로 실행 ──────────────────────────
        steps_results = []
        output_file   = None
        ctx: dict     = {}   # step 간 공유 컨텍스트

        for step_str in steps:
            keyword = step_str.split(":")[0].strip().lower()
            method_name = STEP_DISPATCH.get(keyword, "_step_unknown")
            method = getattr(self, method_name, self._step_unknown)

            try:
                result = method(step_str, ctx, skill)
                steps_results.append({"step": step_str, "ok": True, **result})
                if "output_file" in result:
                    output_file = result["output_file"]
                    ctx["output_file"] = output_file
                ctx.update({k: v for k, v in result.items()
                            if k not in ("output", "output_file")})
            except Exception as e:
                logger.error(f"[SkillExecutor] step 실패: {step_str!r} — {e}")
                steps_results.append({"step": step_str, "ok": False, "error": str(e)})

        success = any(r["ok"] for r in steps_results)
        logger.info(f"[SkillExecutor] 완료: {name}  output={output_file}")
        return {
            "skill": name,
            "success": success,
            "blocked_reason": None,
            "steps_results": steps_results,
            "output_file": output_file,
        }

    # ── step 핸들러들 ────────────────────────────────────

    def _step_analyze(self, step: str, ctx: dict, skill: dict) -> dict:
        """scan_workspace → Executor._do_analyze"""
        result = self.executor._do_analyze({"type": "analyze", "goal": step})
        ctx["state"] = result.get("state_snapshot", {})
        ctx["ext_counts"] = result.get("ext_counts", {})
        return {"output": result["output"], "state": ctx["state"],
                "ext_counts": ctx["ext_counts"]}

    def _step_organize(self, step: str, ctx: dict, skill: dict) -> dict:
        """classify / group_by_type / suggest_actions → Executor._do_organize"""
        result = self.executor._do_organize({"type": "organize", "goal": step})
        ctx["suggestions"] = result.get("suggestions", [])
        return {"output": result["output"], "suggestions": ctx["suggestions"]}

    def _step_report(self, step: str, ctx: dict, skill: dict) -> dict:
        """write_report / write_review / write_classification → 커스텀 보고서"""
        skill_name = skill.get("name", "report")
        ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename   = f"{skill_name}_{ts}.md"

        if skill_name == "workspace_reporter":
            # 1. 보고서 본문 생성 → _report_workspace가 ctx["_ws_raw_suggestions"] 설정
            lines = self._build_report_lines(skill, ctx)

            # 2. 구조화된 제안 데이터로 실행 (parse 단계 없음)
            raw_sug  = ctx.pop("_ws_raw_suggestions", [])
            sug_list = [{"priority": p, "text": t} for p, t in raw_sug]
            summ     = self._execute_suggestion_list(sug_list)
            ctx["suggestion_summary"] = summ

            # 3. 실행 결과 섹션을 lines에 추가
            lines += _build_execution_result_section(summ)
            n_e = len(summ["auto_executed"])
            n_p = len(summ["pending"])
            n_l = len(summ["logged"])
        else:
            lines = self._build_report_lines(skill, ctx)

        saved = write_report_with_retention(self.executor.workspace, filename, lines)
        retention = saved["retention"]
        archived_text = f" | 보존정책 archive {retention['archived']}건" if retention["archived"] else ""

        if skill_name == "workspace_reporter":
            output_msg = (
                f"저장: {saved['report_file']} | "
                f"제안 — 자동실행 {n_e}건 / 승인대기 {n_p}건 / 기록 {n_l}건"
                f"{archived_text}"
            )
        else:
            output_msg = f"저장: {saved['report_file']}{archived_text}"

        return {"output": output_msg, "output_file": saved["report_file"]}

    def _step_scan_code(self, step: str, ctx: dict, skill: dict) -> dict:
        """scan_code_files: .py 파일 목록 수집"""
        py_files = []
        ws = self.executor.workspace
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                if f.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, f), ws)
                    py_files.append(rel)
        ctx["py_files"] = py_files
        return {"output": f".py 파일 {len(py_files)}개", "py_files": py_files}

    def _step_extract_structure(self, step: str, ctx: dict, skill: dict) -> dict:
        """각 .py 파일에서 def / class 이름 추출 (grep 방식)"""
        ws       = self.executor.workspace
        py_files = ctx.get("py_files", [])
        structs  = {}

        for rel in py_files:
            fpath  = os.path.join(ws, rel)
            defs   = []
            classes= []
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        m = re.match(r"^\s*(def|class)\s+(\w+)", line)
                        if m:
                            kind, name = m.group(1), m.group(2)
                            (defs if kind == "def" else classes).append(name)
            except OSError:
                pass
            total_lines = _count_lines(fpath)
            structs[rel] = {
                "functions": defs, "classes": classes, "lines": total_lines
            }

        ctx["structs"] = structs
        return {"output": f"구조 추출: {len(structs)}개 파일", "structs": structs}

    def _step_unknown(self, step: str, ctx: dict, skill: dict) -> dict:
        return {"output": f"(매핑 없는 step 건너뜀: {step!r})"}

    # ── 제안 실행 엔진 ────────────────────────────────────

    def execute_suggestions(
        self,
        report_lines: list[str],
        approval_file: str | None = None,
    ) -> dict:
        """
        외부 호환용 — 보고서 라인을 파싱 후 _execute_suggestion_list 위임.
        반환: {"auto_executed": [...], "pending": [...], "logged": [...]}
        """
        sug_list = _parse_suggestions(report_lines)
        return self._execute_suggestion_list(sug_list, approval_file)

    def _execute_suggestion_list(
        self,
        sug_list: list[dict],
        approval_file: str | None = None,
    ) -> dict:
        """
        구조화된 제안 목록(list[dict])으로 실행 — parse 단계 없이 직접 처리.

        우선순위 정책:
          [높음] + risk=safe     → 즉시 자동 실행
          [높음] + risk=approval → pending_approvals.json 기록
          [중간]                 → pending_approvals.json 기록
          [낮음]                 → 로그만 기록

        반환: {"auto_executed": [...], "pending": [...], "logged": [...]}
        """
        workspace = self.executor.workspace
        if approval_file is None:
            approval_file = os.path.join(workspace, "pending_approvals.json")

        auto_executed: list[dict] = []
        pending:       list[dict] = []
        logged:        list[dict] = []

        for sug in sug_list:
            priority = sug["priority"]
            text     = sug["text"]
            action   = _map_suggestion_to_action(sug, workspace)

            if action is None:
                logged.append({"suggestion": text, "reason": "수동/스케줄 필요"})
                logger.info(f"[SuggExec] 📝 기록: {text[:60]}")
                continue

            risk = action.get("risk", "safe")

            if priority == "높음" and risk == "safe":
                result = _execute_action(action, workspace)
                auto_executed.append({
                    "suggestion":  text,
                    "action":      action["op"],
                    "target_dir":  action.get("target_dir", ""),
                    "result":      result,
                })
                if result["ok"]:
                    logger.info(f"[SuggExec] ✅ 자동 실행: {result['message']}")
                else:
                    logger.warning(f"[SuggExec] ⚠ 실행 실패: {result['message']}")

            elif priority in ("높음", "중간"):
                _write_pending(approval_file, sug, action)
                pending.append({
                    "priority": priority,
                    "suggestion": text,
                    "action": action["op"],
                })
                logger.info(f"[SuggExec] ⏸  승인 대기({priority}): {text[:60]}")

            else:
                logged.append({"suggestion": text, "action": action.get("op", "N/A")})
                logger.info(f"[SuggExec] 📝 기록(낮음): {text[:60]}")

        logger.info(
            f"[SuggExec] 완료 — "
            f"자동실행:{len(auto_executed)} 승인대기:{len(pending)} 기록:{len(logged)}"
        )
        return {"auto_executed": auto_executed, "pending": pending, "logged": logged}

    # ── 보고서 빌더 ──────────────────────────────────────

    def _build_report_lines(self, skill: dict, ctx: dict) -> list[str]:
        """스킬별 5섹션(요약/주요발견/분석/문제점/제안) 보고서 생성."""
        name = skill.get("name", "skill")
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        header = [
            f"# {name} 결과 보고서",
            "",
            f"> 생성: {ts} | 스킬: `{name}`",
        ]
        if name == "workspace_reporter":
            header.append(
                "> ⚠ 이 보고서는 **실행 전 스냅샷 기준**입니다 "
                "— 실제 적용 내역은 맨 아래 '후속 실행 결과' 섹션을 확인하세요."
            )
        header += ["", "---", ""]

        if name == "workspace_reporter":
            body = self._report_workspace(ctx)
        elif name == "code_reviewer":
            body = self._report_code(ctx)
        elif name == "file_classifier":
            body = self._report_classifier(ctx)
        else:
            body = self._report_generic(ctx)

        return header + body

    def _build_workspace_review_summary(self, state: dict) -> dict:
        decision_files = state.get("decision_files", [])
        risk_signal = build_operational_risk_signal(self.executor.workspace, decision_files)
        skills_dir = os.path.join(self.executor.workspace, "skills")
        skills = load_skills(skills_dir) if os.path.isdir(skills_dir) else []
        operational_signal = build_operational_signal([], risk_signal=risk_signal, skills=skills)
        return build_report_summary_payload(operational_signal, risk_signal=risk_signal)

    # ── workspace_reporter 섹션 ──────────────────────────

    def _report_workspace(self, ctx: dict) -> list[str]:
        state      = ctx.get("state", {})
        ext_counts = ctx.get("ext_counts", {})
        review_summary = self._build_workspace_review_summary(state)
        ctx["review_summary"] = review_summary
        reports_dir = os.path.join(self.executor.workspace, "reports")
        reports_present = os.path.isdir(reports_dir)
        log_layout = _inspect_log_layout(Path(self.executor.workspace))
        report_file_cnt = 0
        if reports_present:
            try:
                report_file_cnt = sum(
                    1 for name in os.listdir(reports_dir)
                    if name.endswith(".md")
                )
            except OSError:
                report_file_cnt = 0

        total_files = state.get("total_files", 0)
        total_dirs  = state.get("total_dirs", 0)
        total_bytes = state.get("total_size_bytes", 0)
        total_kb    = total_bytes / 1024

        # 확장자 순위
        sorted_exts = sorted(ext_counts.items(), key=lambda x: -x[1])
        top_ext, top_cnt = (sorted_exts[0] if sorted_exts else ("없음", 0))

        # 카테고리 분류
        cat = _categorize_exts(ext_counts)
        code_cnt = cat["code"]
        doc_cnt  = cat["doc"]
        log_cnt  = cat["log"]
        other_cnt = cat["other"]

        # 규모 판단
        if total_files < 20:
            scale = "소규모"
        elif total_files < 100:
            scale = "중규모"
        else:
            scale = "대규모"

        # ── 요약
        lines = [
            "## 요약",
            "",
        ]
        lines.extend(build_review_summary_lines(review_summary))
        if review_summary.get("summary_headline"):
            lines.append("")
        lines.extend([
            (f"현재 워크스페이스는 총 **{total_files}개 파일**, "
             f"**{total_dirs}개 디렉토리**, **{total_kb:.1f} KB** 규모의 {scale} 프로젝트다. "
             f"가장 많은 확장자는 `{top_ext}` ({top_cnt}개)이며, "
             f"코드 {code_cnt}개 / 문서 {doc_cnt}개 / 로그 {log_cnt}개 / 기타 {other_cnt}개로 구성되는 **종합 상태 보고서**다."),
            "",
        ])

        # ── 주요 발견
        lines += ["## 주요 발견", ""]
        if sorted_exts:
            for ext, cnt in sorted_exts[:5]:
                pct = (cnt / total_files * 100) if total_files else 0
                lines.append(f"- `{ext}`: {cnt}개 ({pct:.0f}%) — {_ext_meaning(ext)}")
        if not sorted_exts:
            lines.append("- 파일 없음")
        lines.append("")

        # ── 분석
        code_ratio = (code_cnt / total_files * 100) if total_files else 0
        doc_ratio  = (doc_cnt  / total_files * 100) if total_files else 0
        log_ratio  = (log_cnt  / total_files * 100) if total_files else 0
        dominant   = "코드 중심" if code_ratio > 50 else ("문서 중심" if doc_cnt > code_cnt else "혼재형")
        size_note  = ("가볍고 이동이 용이한 수준" if total_kb < 1024
                      else f"{total_kb/1024:.1f} MB로 대형 파일 점검 필요")
        density    = total_files / max(total_dirs, 1)

        lines += ["## 분석", ""]

        # 차원 1: 현재 구조의 의미
        lines.append("**현재 구조의 의미:**")
        lines.append("")
        lines.append(
            f"코드 {code_ratio:.0f}% / 문서 {doc_ratio:.0f}% / 로그 {log_ratio:.0f}% 구성의 "
            f"**{dominant} 프로젝트**({size_note}). "
            f"디렉토리당 평균 {density:.0f}개 파일이 배치되어 있으며, "
            + ("단일 계층에 역할이 다른 파일들이 혼재하고 있다."
               if density > 8 else "현재 밀도는 적정 수준이다.")
        )
        lines.append("")

        # 차원 2: 시간에 따른 변화 예상
        lines.append("**시간이 지나면:**")
        lines.append("")
        time_preds = []
        if log_layout["assessment"] == "logs_dir_managed":
            time_preds.append(
                f"로그는 현재 `logs/` 아래에서 분리 관리되고 있으며 `.log` {log_layout['managed_log_count']}개가 보관 중이다"
            )
        elif log_layout["assessment"] == "root_logs_present":
            time_preds.append(
                f"루트에 `.log` {log_layout['root_log_count']}개가 있어 실행이 이어지면 작업 파일과 함께 증가할 수 있다"
            )
        elif log_layout["assessment"] == "mixed_log_layout":
            time_preds.append(
                f"`logs/`와 루트에 `.log`가 함께 존재한다 (`logs/` {log_layout['managed_log_count']}개, 루트 {log_layout['root_log_count']}개)"
            )
        else:
            time_preds.append("현재 관찰된 `.log`는 없어 로그 생성 위치 정책은 별도 확인이 필요하다")
        md_cnt = ext_counts.get(".md", 0)
        if report_file_cnt > 0:
            time_preds.append(
                f"스킬 실행 결과 보고서는 `reports/` 아래에 누적되며 현재 {report_file_cnt}개가 보관 중이다"
            )
        if density > 6:
            time_preds.append(
                f"파일 수 증가 시 디렉토리당 밀도 {density:.0f}→{density*1.5:.0f}개로 상승 예상 — 탐색 시간 비례 증가"
            )
        time_preds.append(
            "디렉토리 구조 없이 파일만 늘어나면 나중에 분리하는 비용이 지금의 수 배가 된다"
        )
        for pred in time_preds:
            lines.append(f"- {pred}")
        lines.append("")

        # 차원 3: 문제로 이어질 가능성
        lines.append("**이대로 두면:**")
        lines.append("")
        risks = []
        if log_layout["assessment"] == "root_logs_present":
            risks.append("루트 디렉토리가 자동 생성 파일로 잠식 — 소스 파일과 결과물의 경계가 사라진다")
        elif log_layout["assessment"] == "mixed_log_layout":
            risks.append("`logs/`와 루트에 로그가 함께 남아 있으면 정리 기준이 흔들려 운영 파일 경계가 모호해질 수 있다")
        elif log_layout["assessment"] == "logs_dir_managed":
            risks.append("`logs/` 보관량이 계속 증가하면 검색 비용이 커질 수 있으므로 회전·보존 정책을 유지해야 한다")
        if report_file_cnt > 3:
            risks.append("`reports/` 보관량이 계속 증가하면 검색 비용이 커지므로 retention/archive 정책을 유지해야 한다")
        risks.append(
            "`.gitignore` 미설정 시 자동 생성 보고서·로그가 버전 관리에 포함 — 저장소 히스토리 오염"
        )
        risks.append(
            "신규 스킬·기능 추가 시 문서·로그·보고서의 배치 기준이 약하면 운영 파일이 계속 늘어나 구조 판단 비용이 증가한다"
        )
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

        # ── 문제점
        problems = _ws_problems(total_files, total_dirs, log_cnt, sorted_exts, ext_counts, reports_present, report_file_cnt, log_layout)
        lines += ["## 문제점", ""]
        if problems:
            for p in problems:
                lines.append(f"- {p}")
        else:
            lines.append("- 식별된 문제 없음")
        lines.append("")

        # ── 제안
        suggestions = _ws_suggestions(problems, sorted_exts, log_cnt, ext_counts, reports_present, log_layout)
        ctx["_ws_raw_suggestions"] = suggestions   # _step_report가 실행에 재사용
        lines += ["## 제안", ""]
        for priority, action in suggestions:
            lines.append(f"- **[{priority}]** {action}")
        if not suggestions:
            lines.append("- 현재 구조 유지 권장")
        lines.append("")
        return lines

    # ── code_reviewer 섹션 ───────────────────────────────

    def _report_code(self, ctx: dict) -> list[str]:
        state = ctx.get("state", {})
        review_summary = ctx.get("review_summary") or self._build_workspace_review_summary(state)
        ctx["review_summary"] = review_summary
        structs   = ctx.get("structs", {})
        py_files  = list(structs.keys())

        total_lines = sum(v["lines"] for v in structs.values())
        total_funcs = sum(len(v["functions"]) for v in structs.values())
        total_cls   = sum(len(v["classes"])   for v in structs.values())
        n_files     = len(py_files)
        avg_lines   = (total_lines / n_files) if n_files else 0
        avg_funcs   = (total_funcs / n_files) if n_files else 0

        # 가장 큰 파일
        largest = max(structs.items(), key=lambda x: x[1]["lines"], default=(None, {}))
        most_funcs = max(structs.items(), key=lambda x: len(x[1]["functions"]), default=(None, {}))

        # ── 요약
        cls_note = f"클래스 {total_cls}개" if total_cls else "클래스 없음(함수형 구성)"
        lines = [
            "## 요약",
            "",
        ]
        lines.extend(build_review_summary_lines(review_summary))
        if review_summary.get("summary_headline"):
            lines.append("")
        lines.extend([
            (f"분석 대상 `.py` 파일 **{n_files}개**, 총 **{total_lines:,} 라인**, "
             f"함수 **{total_funcs}개**, {cls_note}. "
             f"파일당 평균 {avg_lines:.0f} 라인으로 "
             + ("적정 규모다." if avg_lines <= 200
                else "파일이 비대해 분리를 검토해야 한다.")),
            "",
        ])

        # ── 주요 발견
        lines += ["## 주요 발견", ""]
        if largest[0]:
            lines.append(f"- 가장 큰 파일: `{largest[0]}` ({largest[1]['lines']} 라인) "
                         + ("— 리팩토링 우선 검토 대상" if largest[1]["lines"] > 300 else "— 적정 수준"))
        if most_funcs[0]:
            fn_cnt = len(most_funcs[1]["functions"])
            lines.append(f"- 함수 최다 파일: `{most_funcs[0]}` ({fn_cnt}개) "
                         + ("— 책임 분산 필요" if fn_cnt > 15 else "— 적정 수준"))
        lines.append(f"- 클래스 설계: {'적용됨 (' + str(total_cls) + '개)' if total_cls else '미적용 — 함수 중심 구조'}")
        lines.append(f"- 전체 평균 함수/파일: {avg_funcs:.1f}개 "
                     + ("(적정)" if avg_funcs <= 12 else "(과다 — 모듈 분리 권장)"))
        lines.append("")

        # ── 분석
        if avg_funcs > 15:
            quality_main = f"파일당 평균 함수 {avg_funcs:.1f}개로 단일 책임 원칙(SRP) 위반 가능성이 높다."
        elif total_cls == 0:
            quality_main = "클래스가 전혀 없는 순수 함수형 구성이다. 지금은 동작하지만 공유 상태 증가 시 의존성 추적이 어려워진다."
        elif avg_lines > 200:
            quality_main = f"파일 평균 {avg_lines:.0f} 라인으로 비대한 경향이 있다. 기능 추가 시 같은 파일 내 충돌·리뷰 부담이 커진다."
        else:
            quality_main = "파일 크기와 함수 수가 균형을 이루고 있다."

        # 구조적 시사점 도출
        test_files   = [f for f in py_files if os.path.basename(f).startswith("test_")]
        has_test_dir = any("test" in os.path.dirname(f).lower() for f in py_files)
        implications = []
        if test_files and not has_test_dir:
            implications.append(f"테스트 파일 {len(test_files)}개가 소스 파일과 같은 계층에 혼재 — `tests/` 디렉토리 분리 시 가독성·CI 연동이 개선된다")
        cls_ratio = (total_cls / n_files * 100) if n_files else 0
        if cls_ratio < 40:
            implications.append(f"클래스화율 {cls_ratio:.0f}% — 함수 중심 구조로, 모듈 간 상태 공유가 늘어날수록 부작용 추적이 어려워진다")
        oversized_cnt = sum(1 for v in structs.values() if v["lines"] > 300)
        if oversized_cnt:
            implications.append(f"300줄 초과 파일 {oversized_cnt}개 — 파일 크기가 클수록 변경 영향 범위를 파악하기 어렵고 병렬 작업 시 충돌 위험이 높다")
        else:
            implications.append("파일 크기는 모두 300줄 이하로 적정 수준이나, 계속 기능을 추가하면 곧 경계에 도달할 수 있다")
        no_func_cnt = sum(1 for v in structs.values() if not v["functions"] and not v["classes"])
        if no_func_cnt:
            implications.append(f"함수/클래스가 없는 파일 {no_func_cnt}개 — 단순 상수·설정 파일이거나 미완성 모듈일 가능성이 있다")

        lines += ["## 분석", ""]
        lines.append(quality_main + " 이 구조가 의미하는 것:")
        lines.append("")
        for impl in implications:
            lines.append(f"- {impl}")
        lines.append("")

        # 파일별 구조 테이블
        lines.append("| 파일 | 라인 | 함수 | 클래스 | 평가 |")
        lines.append("|------|------|------|--------|------|")
        for fpath, info in sorted(structs.items(), key=lambda x: -x[1]["lines"]):
            fn  = len(info["functions"])
            cls = len(info["classes"])
            flag = "⚠ 과대" if info["lines"] > 300 or fn > 15 else "✓"
            lines.append(f"| `{fpath}` | {info['lines']} | {fn} | {cls} | {flag} |")
        lines.append("")

        # ── 문제점
        problems = _code_problems(structs, avg_lines, avg_funcs, total_cls)
        lines += ["## 문제점", ""]
        if problems:
            for p in problems:
                lines.append(f"- {p}")
        else:
            lines.append("- 식별된 문제 없음")
        lines.append("")

        # ── 제안
        suggestions = _code_suggestions(structs, problems, total_cls)
        lines += ["## 제안", ""]
        for priority, action in suggestions:
            lines.append(f"- **[{priority}]** {action}")
        if not suggestions:
            lines.append("- 현재 구조 유지 권장")
        lines.append("")
        return lines

    # ── file_classifier 섹션 ─────────────────────────────

    def _report_classifier(self, ctx: dict) -> list[str]:
        state      = ctx.get("state", {})
        review_summary = ctx.get("review_summary") or self._build_workspace_review_summary(state)
        ctx["review_summary"] = review_summary
        ext_counts = ctx.get("ext_counts", {})
        suggestions_raw = ctx.get("suggestions", [])

        total_files = state.get("total_files", 0)
        cat = _categorize_exts(ext_counts)

        # ── 요약
        dominant_cat = max(cat, key=cat.get)
        cat_kr = {"code": "코드", "doc": "문서", "log": "로그", "other": "기타"}
        lines = [
            "## 요약",
            "",
        ]
        lines.extend(build_review_summary_lines(review_summary))
        if review_summary.get("summary_headline"):
            lines.append("")
        lines.extend([
            (f"총 **{total_files}개 파일**이 코드 {cat['code']}개 / "
             f"문서 {cat['doc']}개 / 로그 {cat['log']}개 / 기타 {cat['other']}개로 분류된다. "
             f"가장 많은 카테고리는 **{cat_kr.get(dominant_cat, dominant_cat)}**({cat[dominant_cat]}개)이며, "
             + ("파일 구성이 비교적 단일하다." if len([v for v in cat.values() if v > 0]) <= 2
                else "여러 유형이 혼재해 있으며, 이 보고서는 구조 분류 관점만 다룬다.")),
            "",
        ])

        # ── 주요 발견
        sorted_exts = sorted(ext_counts.items(), key=lambda x: -x[1])
        lines += ["## 주요 발견", ""]
        for ext, cnt in sorted_exts[:6]:
            pct = (cnt / total_files * 100) if total_files else 0
            lines.append(f"- `{ext}` {cnt}개 ({pct:.0f}%) — {_ext_meaning(ext)}")
        if cat["other"] > total_files * 0.3:
            lines.append(f"- ⚠ '기타' 카테고리 비율이 {cat['other']/total_files*100:.0f}%로 높음 — 분류 불가 파일 과다")
        if total_files:
            lines.append(f"- 구조 분류 초점: 코드/문서/설정/기타 배치 기준이 명확한지 확인하는 용도이며, 종합 운영 평가는 `workspace_reporter`가 담당")
        lines.append("")

        # ── 분석
        mixed = sum(1 for v in cat.values() if v > 0)
        if mixed >= 4:
            org_level = "높음 — 즉시 정리 권장"
        elif mixed == 3:
            org_level = "중간 — 부분 정리 필요"
        else:
            org_level = "낮음 — 현재 수준 유지 가능"

        # 구조적 시사점 도출
        implications = []
        if cat["code"] > 0 and cat["doc"] > 0:
            implications.append("코드와 문서 파일이 함께 존재해, 파일 수가 늘어날수록 개발자가 '현재 무엇을 봐야 하는지'를 파악하기 어려워진다")
        if cat["other"] > total_files * 0.2 and total_files > 5:
            implications.append(f"'기타' 파일 비율 {cat['other']/total_files*100:.0f}% — 분류 기준이 없으면 프로젝트 성격을 파악하기 어렵고 신규 파일 배치 기준도 모호해진다")
        if mixed >= 3:
            implications.append("여러 유형이 워크스페이스 전반에 공존하는 구조는 초기에는 무해하지만, 팀 규모·파일 수 확장 시 관리 비용이 기하급수적으로 증가한다")
        else:
            implications.append("현재는 단순 구조로 관리 부담이 낮으며, 디렉토리별 역할만 명확히 유지하면 분류 체계를 안정적으로 유지할 수 있다")

        lines += ["## 분석", ""]
        lines.append(
            f"{mixed}개 카테고리(코드·문서·로그·기타) 혼재, 정리 필요 긴급도 **{org_level}**. "
            "이 구조가 의미하는 것:"
        )
        lines.append("")
        for impl in implications:
            lines.append(f"- {impl}")
        lines.append("")

        # ── 문제점
        problems = _clf_problems(cat, total_files, ext_counts)
        lines += ["## 문제점", ""]
        if problems:
            for p in problems:
                lines.append(f"- {p}")
        else:
            lines.append("- 식별된 문제 없음")
        lines.append("")

        # ── 제안
        suggestions = _clf_suggestions(problems, cat, ext_counts)
        lines += ["## 제안", ""]
        for priority, action in suggestions:
            lines.append(f"- **[{priority}]** {action}")
        if not suggestions:
            lines.append("- 현재 구조 유지 권장")
        lines.append("")
        return lines

    # ── 폴백 (미지원 스킬) ───────────────────────────────

    def _report_generic(self, ctx: dict) -> list[str]:
        lines = ["## 요약", "", "스킬 전용 보고서 형식이 없어 원시 데이터를 출력합니다.", ""]
        for key, val in ctx.items():
            if key == "output_file":
                continue
            lines += [f"## {key}", "", f"```", str(val)[:500], "```", ""]
        return lines


# ── 유틸리티 ─────────────────────────────────────────────

def _count_lines(filepath: str) -> int:
    try:
        with open(filepath, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _inspect_log_layout(workspace: Path) -> dict:
    logs_dir = workspace / "logs"
    root_log_count = 0
    managed_log_count = 0

    try:
        root_log_count = sum(1 for item in workspace.iterdir() if item.is_file() and item.suffix == ".log")
    except OSError:
        root_log_count = 0

    if logs_dir.is_dir():
        try:
            managed_log_count = sum(1 for item in logs_dir.rglob("*.log") if item.is_file())
        except OSError:
            managed_log_count = 0

    if managed_log_count > 0 and root_log_count > 0:
        assessment = "mixed_log_layout"
    elif managed_log_count > 0:
        assessment = "logs_dir_managed"
    elif root_log_count > 0:
        assessment = "root_logs_present"
    else:
        assessment = "no_logs_detected"

    return {
        "assessment": assessment,
        "has_logs_dir": logs_dir.is_dir(),
        "root_log_count": root_log_count,
        "managed_log_count": managed_log_count,
    }


# ── 보고서 분석 헬퍼 ─────────────────────────────────────

_CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
              ".rs", ".c", ".cpp", ".cs", ".rb", ".php", ".sh", ".bat"}
_DOC_EXTS  = {".md", ".txt", ".rst", ".pdf", ".docx", ".html", ".htm"}
_LOG_EXTS  = {".log", ".jsonl"}
_DATA_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".xml"}


def _categorize_exts(ext_counts: dict) -> dict:
    """확장자 카운트를 code/doc/log/other 카테고리로 분류."""
    cat = {"code": 0, "doc": 0, "log": 0, "other": 0}
    for ext, cnt in ext_counts.items():
        if ext in _CODE_EXTS:
            cat["code"] += cnt
        elif ext in _DOC_EXTS:
            cat["doc"] += cnt
        elif ext in _LOG_EXTS:
            cat["log"] += cnt
        else:
            cat["other"] += cnt
    return cat


def _ext_meaning(ext: str) -> str:
    """확장자의 역할을 한 줄로 설명."""
    meanings = {
        ".py": "Python 소스 코드",
        ".md": "Markdown 문서",
        ".json": "JSON 설정/데이터",
        ".jsonl": "JSONL 로그",
        ".log": "로그 파일",
        ".sh": "Shell 스크립트",
        ".bat": "Windows 배치 스크립트",
        ".txt": "텍스트 파일",
        ".yaml": "YAML 설정",
        ".yml": "YAML 설정",
        ".toml": "TOML 설정",
        ".html": "HTML 문서",
        ".csv": "CSV 데이터",
    }
    return meanings.get(ext, "기타 파일")


# ── workspace_reporter 분석 ───────────────────────────────

def _ws_problems(total_files, total_dirs, log_cnt, sorted_exts, ext_counts, reports_present=False, report_file_cnt=0, log_layout=None) -> list[str]:
    """
    카테고리별 문제를 1개씩 선정하여 최소 3개(목표 4개) 반환.
    각 문제는 서로 다른 카테고리: 구조 / 운영 / 유지보수 / 확장성
    """
    md_cnt    = ext_counts.get(".md", 0)
    json_cnt  = ext_counts.get(".json", 0)
    yaml_cnt  = ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0)
    other_cnt = ext_counts.get("", 0) + ext_counts.get(".tmp", 0)
    density   = total_files / max(total_dirs, 1)
    log_layout = log_layout or {"assessment": "no_logs_detected", "root_log_count": 0, "managed_log_count": 0}

    # ── [구조] 파일·디렉토리 배치 문제
    if md_cnt > 4:
        structural = (
            f"[구조] Markdown 문서(*.md {md_cnt}개)가 다수 존재 "
            "— 안내 문서·설계 메모·결과 요약의 구분 기준이 약하면 탐색 시 불필요한 노이즈가 발생한다"
        )
    elif density > 8:
        structural = (
            f"[구조] 디렉토리당 평균 {density:.0f}개 파일로 밀도가 높음 "
            "— 코드·설정·문서가 단일 계층에 배치되어 기능 변경 시 영향 파일 범위를 파악하는 데 시간이 걸린다"
        )
    else:
        structural = (
            f"[구조] 코드·문서·설정 파일이 동일 계층에 혼재({total_files}개) "
            "— 역할별 디렉토리 없이 파일 유형만 다른 파일들이 같은 위치에 있어 신규 기여자 진입 비용이 높다"
        )

    # ── [운영] 로그·자동 생성 파일 누적 문제
    if log_layout["assessment"] == "logs_dir_managed":
        operational = (
            f"[운영] `logs/` 아래 `.log` {log_layout['managed_log_count']}개가 분리 관리되고 있음 "
            "— 현재는 루트 혼잡 리스크가 낮지만, 회전·보존 정책이 없으면 운영 이력이 누적될 수 있다"
        )
    elif log_layout["assessment"] == "root_logs_present":
        operational = (
            f"[운영] 루트에 `.log` 파일 {log_layout['root_log_count']}개가 존재 "
            "— 에이전트 실행마다 1개씩 추가되는 구조로 정리 정책 없이는 실행 횟수에 비례해 루트가 오염된다"
        )
    elif log_layout["assessment"] == "mixed_log_layout":
        operational = (
            f"[운영] `logs/`와 루트에 `.log`가 함께 존재 (`logs/` {log_layout['managed_log_count']}개 / 루트 {log_layout['root_log_count']}개) "
            "— 분리 정책은 있으나 일부 로그가 루트에 남아 있어 관리 기준이 완전히 수렴되지 않았다"
        )
    elif reports_present and report_file_cnt > 2:
        operational = (
            f"[운영] 관찰된 `.log`는 없지만 자동 생성 보고서 파일 {report_file_cnt}개가 `reports/`에 누적 "
            "— 보고서 보관량은 retention 기준으로 계속 점검해야 한다"
        )
    else:
        operational = (
            "[운영] 관찰된 `.log`는 없어 현재 로그 배치 구조를 단정하기 어려움 "
            "— 로그가 생성된다면 위치·회전 정책을 별도로 확인해야 운영 파일 누적을 통제할 수 있다"
        )

    # ── [유지보수] 역할 혼재·가독성 문제
    config_cnt = json_cnt + yaml_cnt
    if config_cnt > 1:
        maintenance = (
            f"[유지보수] 설정 파일({config_cnt}개: .json/.yaml)이 소스 파일과 같은 위치에 산재 "
            "— 설정 변경 시 어떤 파일이 어떤 컴포넌트에 적용되는지 추적이 어렵고 오설정 위험이 있다"
        )
    elif other_cnt > 0:
        maintenance = (
            f"[유지보수] 확장자 불명확·임시 파일 {other_cnt}개 존재 "
            "— 삭제 기준이 없으면 영구 잔류하며, 신규 기여자가 이 파일들의 목적을 파악할 방법이 없다"
        )
    else:
        maintenance = (
            "[유지보수] 코드·문서·운영 파일 혼재로 온보딩 비용 발생 "
            "— 역할별 분리 없이 파일이 나열되어 있어 '지금 뭘 봐야 하는가'를 판단하는 데 불필요한 시간이 소요된다"
        )

    # ── [확장성] 미래 증가 시 위험
    if total_files > 30 and total_dirs < 4:
        scalability = (
            f"[확장성] 파일 {total_files}개가 {total_dirs}개 디렉토리에 집중 "
            "— 지금 구조를 유지한 채 기능을 추가하면 파일 수가 급증하여 나중에 분리하는 비용이 현재의 수 배가 된다"
        )
    else:
        scalability = (
            "[확장성] 현재 구조에서 스킬·기능 추가 시 자동 생성 파일 밀도 급증 예상 "
            "— 에이전트 1회 실행당 1~2개 파일 생성 패턴이 고착화되면 구조 개선 시점을 놓치게 된다"
        )

    return [structural, operational, maintenance, scalability]


def _ws_suggestions(problems, sorted_exts, log_cnt, ext_counts, reports_present=False, log_layout=None) -> list[tuple]:
    """
    중복 없는 제안 목록. 형식: [우선순위] 무엇을 → 어떻게 → 왜
    covered 집합으로 동일 대상 중복 방지. 최소 3개 보장.
    """
    covered     = set()
    suggestions = []

    def add(priority: str, target_key: str, action: str) -> None:
        if target_key not in covered:
            covered.add(target_key)
            suggestions.append((priority, action))

    md_cnt    = ext_counts.get(".md", 0)
    json_cnt  = ext_counts.get(".json", 0)
    yaml_cnt  = ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0)
    tmp_cnt   = ext_counts.get(".tmp", 0)
    config_cnt = json_cnt + yaml_cnt
    log_layout = log_layout or {"assessment": "no_logs_detected", "root_log_count": 0}

    # ── 높음: 즉각 실행 가능한 정리
    if log_layout["assessment"] in {"root_logs_present", "mixed_log_layout"}:
        root_log_count = log_layout.get("root_log_count", 0)
        add("높음", "logs",
            f"루트 `.log` 파일 {root_log_count}개를 → `logs/` 디렉토리 기준으로 정리 "
            f"→ 운영 파일과 소스 파일 분리, 루트 탐색 즉시 개선")

    if not reports_present and md_cnt > 3:
        add("높음", "reports",
            f"자동 생성 보고서 `.md` {md_cnt}개를 → `reports/` 디렉토리 생성 후 이동 "
            f"→ 수동 문서와 자동 결과물 구분, 보고서 이력 별도 관리 가능")

    if tmp_cnt:
        add("높음", "tmp",
            f"임시 파일 {tmp_cnt}개(`.tmp`)를 → 확인 후 삭제 "
            f"→ 불필요한 잔여 파일 제거, 루트 정리")

    # ── 중간: 구조적 개선
    if config_cnt > 1:
        add("중간", "config",
            f"설정 파일 {config_cnt}개(`.json`, `.yaml`)를 → `config/` 디렉토리 생성 후 통합 "
            f"→ 설정 변경 시 단일 위치 관리, 오설정 위험 감소")

    add("중간", "gitignore",
        "`.gitignore` 파일을 → 신규 작성 또는 업데이트 (`*.log`, `*.jsonl`, `reports/`, `archive/` 추가) "
        "→ 자동 생성 파일이 버전 관리에서 자동 제외, 저장소 오염 방지")

    # ── 낮음: 프로세스·자동화
    add("낮음", "schedule",
        "`run_maintenance.py --task all`을 → 주간 스케줄로 등록 "
        "→ 로그·보고서 자동 정리 자동화, 수동 개입 없이 워크스페이스 유지")

    add("낮음", "docs",
        "README·설계 문서를 → `docs/` 디렉토리 생성 후 이동 "
        "→ 코드와 문서 계층 분리, 신규 개발자 온보딩 시간 단축")

    # ── 최소 3개 미달 시 보충 (중복 대상 제외)
    _fallback = [
        ("중간", "retention_fb",
         "`reports/`·`archive/` retention 규칙을 주기 점검 → 보고서 보관량이 운영 범위를 넘지 않도록 유지"),
        ("중간", "gitignore_fb",
         "`.gitignore`를 → 작성(`*.log`, `reports/` 제외) → 저장소 오염 방지"),
        ("낮음", "structure_fb",
         "디렉토리 구조를 → `docs/STRUCTURE.md`에 문서화 → 신규 파일 배치 기준 명확화"),
    ]
    for priority, key, action in _fallback:
        if len(suggestions) >= 3:
            break
        add(priority, key, action)

    return suggestions


# ── code_reviewer 분석 ────────────────────────────────────

_CODE_FALLBACK_PROBLEMS = [
    "모듈별 docstring 작성 여부가 확인되지 않음 — 공개 함수·클래스에 docstring 없으면 IDE 지원 및 자동 문서화 불가",
    "타입 힌트(type hint) 적용 현황 미확인 — 동적 타입 언어 특성상 타입 힌트 없으면 리팩토링 시 오류 감지가 어렵다",
    "테스트 파일 존재 여부와 커버리지 목표가 확인되지 않음 — 자동화 에이전트 코드는 회귀 방지를 위해 테스트가 중요하다",
]

_CODE_FALLBACK_SUGGESTIONS = [
    ("중간", "모든 공개 함수에 docstring 추가 — 1줄 요약 + Args/Returns 형식으로 자동 문서화 활성화"),
    ("중간", "타입 힌트(type hint) 전면 적용 — mypy 또는 pyright 정적 분석으로 런타임 전 오류 조기 발견"),
    ("낮음", "테스트 파일을 `tests/` 디렉토리로 분리하고 pytest 실행 자동화 — CI/CD 연동 기반 마련"),
    ("낮음", "`__init__.py`에 공개 API(`__all__`) 명시 — 모듈 외부 인터페이스를 명확히 정의"),
]


def _code_problems(structs, avg_lines, avg_funcs, total_cls) -> list[str]:
    problems = []
    py_files = list(structs.keys())

    # 조건부 문제
    oversized = [f for f, v in structs.items() if v["lines"] > 300]
    if oversized:
        problems.append(
            f"과대 파일(300줄 초과): {', '.join(f'`{f}`' for f in oversized[:3])} "
            "— 변경 영향 범위가 넓어 리뷰·테스트 비용 증가"
        )
    heavy_funcs = [f for f, v in structs.items() if len(v["functions"]) > 15]
    if heavy_funcs:
        fn = len(structs[heavy_funcs[0]]["functions"])
        problems.append(
            f"함수 과다: `{heavy_funcs[0]}` ({fn}개) — 단일 파일이 너무 많은 책임 담당, 서브모듈 분리 필요"
        )
    test_files = [f for f in py_files if os.path.basename(f).startswith("test_")]
    src_has_test = any(not os.path.basename(f).startswith("test_") and
                       "test" not in os.path.dirname(f).lower() for f in py_files)
    if test_files and src_has_test:
        problems.append(
            f"테스트 파일 {len(test_files)}개가 소스 파일과 동일 계층 혼재 "
            "— `tests/` 분리 시 pytest 수집·CI 연동이 단순해진다"
        )
    if total_cls == 0 and len(structs) > 3:
        problems.append("클래스 미사용: 모든 파일이 함수형 구성 — 공유 상태 증가 시 전역 변수 남용 위험")
    no_func = [f for f, v in structs.items() if not v["functions"] and not v["classes"]]
    if no_func:
        problems.append(
            f"함수·클래스 없는 파일: {', '.join(f'`{f}`' for f in no_func[:3])} "
            "— 역할 불명확(상수 파일이거나 미완성 모듈)"
        )

    # ── 최소 2개 보장
    for p in _CODE_FALLBACK_PROBLEMS:
        if len(problems) >= 2:
            break
        if not any(p[:20] in existing for existing in problems):
            problems.append(p)
    return problems


def _code_suggestions(structs, problems, total_cls) -> list[tuple]:
    suggestions = []
    py_files = list(structs.keys())

    # 조건부 제안
    oversized = [f for f, v in structs.items() if v["lines"] > 300]
    for f in oversized[:2]:
        suggestions.append(("높음", f"`{f}` 기능 단위로 분리 — 목표: 파일당 300줄 이하, 단일 책임"))
    heavy_funcs = [f for f, v in structs.items() if len(v["functions"]) > 15]
    for f in heavy_funcs[:1]:
        cnt = len(structs[f]["functions"])
        suggestions.append(("높음", f"`{f}` 함수 {cnt}개 → 기능 그룹별 서브모듈 분리 (`utils/`, `handlers/` 등)"))
    if total_cls == 0 and len(structs) > 3:
        suggestions.append(("중간", "핵심 도메인에 클래스 도입 — 에이전트 루프·메모리·설정을 각각 클래스로 캡슐화"))
    test_files = [f for f in py_files if os.path.basename(f).startswith("test_")]
    if test_files:
        suggestions.append(("중간", f"테스트 파일 {len(test_files)}개를 `tests/` 디렉토리로 이동 — pytest 자동 수집 설정"))

    # ── 최소 3개 보장
    for priority, action in _CODE_FALLBACK_SUGGESTIONS:
        if len(suggestions) >= 3:
            break
        if not any(action[:25] in a for _, a in suggestions):
            suggestions.append((priority, action))
    return suggestions


# ── file_classifier 분석 ─────────────────────────────────

_CLF_FALLBACK_PROBLEMS = [
    "코드/문서/설정 파일의 디렉토리 경계가 약해 신규 파일 배치 기준이 흐려질 수 있다",
    "설정 파일(config.json, *.yaml)이 여러 위치에 분산되면 구조 분류 규칙을 유지하기 어렵다",
    "기타 카테고리 파일 비중이 커지면 구조 분류 체계 자체가 무력화된다",
]

_CLF_FALLBACK_SUGGESTIONS = [
    ("높음", "코드/문서/설정 파일의 목표 디렉토리를 정하고 동일 유형 파일을 한 계층으로 모은다 — 구조 분류 기준 고정"),
    ("중간", "`config/` 디렉토리 생성 후 `config.json`, `*.yaml` 등 설정 파일 통합 — 설정 변경 시 단일 지점 관리"),
    ("중간", "`docs/STRUCTURE.md`에 유형별 배치 기준을 문서화 — 신규 파일 추가 시 구조 규칙 유지"),
    ("낮음", "기타 파일 검토 목록을 별도로 유지해 분류 불가 파일을 주기적으로 재분류한다"),
]


def _clf_problems(cat, total_files, ext_counts) -> list[str]:
    problems = []

    # 조건부 문제
    if cat["other"] > total_files * 0.25 and total_files > 5:
        problems.append(
            f"'기타' 파일 비율 {cat['other']/total_files*100:.0f}%({cat['other']}개) "
            "— 분류 기준 부재로 신규 파일 배치 결정이 어렵다"
        )
    tmp_cnt = ext_counts.get(".tmp", 0) + ext_counts.get(".bak", 0)
    if tmp_cnt:
        problems.append(f"임시·백업 파일 {tmp_cnt}개(`.tmp`, `.bak`) — 삭제 후보, 방치 시 저장 공간 낭비")
    mixed = sum(1 for v in cat.values() if v > 0)
    if mixed >= 3 and total_files > 10:
        problems.append(
            f"{mixed}개 유형(코드/문서/로그/기타)이 동일 워크스페이스에 공존 "
            "— 프로젝트 규모 성장 시 탐색 비용 급증"
        )
    json_cnt = ext_counts.get(".json", 0) + ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0)
    if json_cnt > 2:
        problems.append(
            f"설정 계열 파일 {json_cnt}개가 분산 배치 "
            "— 구조 분류 관점에서 설정 파일의 고정 위치가 없으면 변경 영향 범위를 파악하기 어렵다"
        )

    # ── 최소 2개 보장
    for p in _CLF_FALLBACK_PROBLEMS:
        if len(problems) >= 2:
            break
        if not any(p[:20] in existing for existing in problems):
            problems.append(p)
    return problems


def _clf_suggestions(problems, cat, ext_counts) -> list[tuple]:
    suggestions = []

    # 조건부 제안
    if cat["code"] > 0 and cat["doc"] > 0:
        suggestions.append(("높음", "코드 파일과 문서 파일의 기본 디렉토리를 분리(`src/`, `docs/` 등) — 구조 분류 기준 명확화"))
    if cat["doc"] > 2:
        suggestions.append(("중간", f"문서 파일 {cat['doc']}개를 `docs/` 로 이동 — 코드와 분리, 검색 편의성 향상"))
    tmp_cnt = ext_counts.get(".tmp", 0) + ext_counts.get(".bak", 0)
    if tmp_cnt:
        suggestions.append(("높음", f"`.tmp`·`.bak` 파일 {tmp_cnt}개 삭제 — 즉시 실행 가능한 용량 확보"))
    json_cnt = ext_counts.get(".json", 0) + ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0)
    if json_cnt > 2:
        suggestions.append(("중간", f"설정 파일 {json_cnt}개를 `config/` 디렉토리로 통합 — 구조 분류 기준에서 설정 계층 고정"))

    # ── 최소 3개 보장
    for priority, action in _CLF_FALLBACK_SUGGESTIONS:
        if len(suggestions) >= 3:
            break
        if not any(action[:25] in a for _, a in suggestions):
            suggestions.append((priority, action))
    return suggestions


# ── 제안 파서 & 실행 엔진 ─────────────────────────────────

# **[높음]** / **[중간]** / **[낮음]** 패턴 매칭
_RE_SUGGESTION = re.compile(r"^- \*\*\[(높음|중간|낮음)\]\*\* (.+)")

# 자동 생성 보고서 파일명 패턴: {skill}_{YYYYMMDD}_{HHMMSS}.md
_RE_AUTOREPORT = re.compile(r"^.+_\d{8}_\d{6}\.md$")


def _parse_suggestions(report_lines: list[str]) -> list[dict]:
    """보고서 라인에서 **[높음/중간/낮음]** 제안 항목 파싱."""
    results = []
    for line in report_lines:
        m = _RE_SUGGESTION.match(line)
        if m:
            results.append({"priority": m.group(1), "text": m.group(2).strip()})
    return results


def _map_suggestion_to_action(suggestion: dict, workspace: str) -> dict | None:
    """
    제안 텍스트 → 파일시스템 액션 딕셔너리로 변환.

    반환 형태 (op 키 기준):
      mkdir_and_move  : {"op", "target_dir", "file_filter", "risk": "safe"}
      create_gitignore: {"op", "risk": "safe"}
      mkdir_only      : {"op", "target_dir", "risk": "safe"}
      delete_files    : {"op", "patterns", "risk": "approval"}
      None            : 실행 불가 (스케줄 등록, README 작성 등)
    """
    text = suggestion.get("text", "").lower()

    # .gitignore — 최우선 체크 (텍스트 안에 경로 예시 포함 가능하므로 먼저 걸러야 함)
    if "gitignore" in text and ("작성" in text or "신규" in text or "업데이트" in text or "설정" in text):
        return {"op": "create_gitignore", "risk": "safe"}

    # logs/ 이동
    if ("logs/" in text or "`logs`" in text) and ("이동" in text or "생성" in text):
        return {"op": "mkdir_and_move", "target_dir": "logs",
                "file_filter": "log", "risk": "safe"}

    # reports/ 이동 (타임스탬프 패턴 *.md)
    if ("reports/" in text or "`reports`" in text) and ("이동" in text or "생성" in text):
        return {"op": "mkdir_and_move", "target_dir": "reports",
                "file_filter": "autoreport", "risk": "safe"}

    # config/ 이동
    if ("config/" in text or "`config`" in text) and ("이동" in text or "통합" in text or "생성" in text):
        return {"op": "mkdir_and_move", "target_dir": "config",
                "file_filter": "config", "risk": "safe"}

    # docs/ 생성
    if ("docs/" in text or "`docs`" in text) and ("이동" in text or "생성" in text or "문서화" in text):
        return {"op": "mkdir_only", "target_dir": "docs", "risk": "safe"}

    # 삭제 (.tmp / .bak) — 항상 approval 경로
    if "삭제" in text and (".tmp" in text or ".bak" in text or "임시" in text):
        patterns = []
        if ".tmp" in text:
            patterns.append("*.tmp")
        if ".bak" in text:
            patterns.append("*.bak")
        return {"op": "delete_files", "patterns": patterns or ["*.tmp"], "risk": "approval"}

    return None  # 스케줄 등록, README 작성 등 → 수동 처리


def _execute_action(action: dict, workspace: str) -> dict:
    """
    단일 파일시스템 액션 실행.
    반환: {"ok": bool, "message": str, "files_affected": list}
    """
    op = action.get("op")

    if op == "mkdir_and_move":
        target_dir  = os.path.join(workspace, action["target_dir"])
        file_filter = action.get("file_filter", "")
        os.makedirs(target_dir, exist_ok=True)

        candidates = []
        try:
            for fname in os.listdir(workspace):
                fpath = os.path.join(workspace, fname)
                if not os.path.isfile(fpath):
                    continue
                if file_filter == "log" and fname.endswith((".log", ".jsonl")):
                    # agent.log 는 실행 중 활성 로그 — maintenance에서만 처리, 여기서 제외
                    if fname == "agent.log":
                        continue
                    candidates.append(fname)
                elif file_filter == "autoreport" and _RE_AUTOREPORT.match(fname):
                    candidates.append(fname)
                elif file_filter == "config" and fname.endswith((".json", ".yaml", ".yml")):
                    # 에이전트 주 설정 파일은 제외
                    if fname not in ("config.json",):
                        candidates.append(fname)
        except OSError as e:
            return {"ok": False, "message": f"디렉토리 탐색 실패: {e}", "files_affected": []}

        moved = []
        for fname in candidates:
            src  = os.path.join(workspace, fname)
            dest = os.path.join(target_dir, fname)
            if not os.path.exists(dest):
                try:
                    shutil.move(src, dest)
                    moved.append(fname)
                except OSError as e:
                    logger.warning(f"[SuggExec] 이동 실패: {fname} — {e}")

        return {
            "ok": True,
            "message": (
                f"`{action['target_dir']}/` 생성 + {len(moved)}개 이동"
                + (f": {moved[:5]}" if moved else " (이동 대상 없음)")
            ),
            "files_affected": moved,
        }

    elif op == "create_gitignore":
        gitignore_path = os.path.join(workspace, ".gitignore")
        entries = [
            "*.log", "*.jsonl", "reports/", "archive/",
            "logs/", "__pycache__/", "*.pyc", "*.pyo",
        ]
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            new_entries = [e for e in entries if e not in existing_content]
            if new_entries:
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write("\n# 에이전트 자동 추가\n" + "\n".join(new_entries) + "\n")
                return {"ok": True,
                        "message": f".gitignore 업데이트: {len(new_entries)}개 항목 추가",
                        "files_affected": [".gitignore"]}
            return {"ok": True,
                    "message": ".gitignore 이미 최신 상태",
                    "files_affected": []}
        else:
            content = "# 에이전트 자동 생성 파일 제외\n" + "\n".join(entries) + "\n"
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "message": ".gitignore 신규 생성", "files_affected": [".gitignore"]}

    elif op == "mkdir_only":
        target_dir = os.path.join(workspace, action["target_dir"])
        existed = os.path.exists(target_dir)
        os.makedirs(target_dir, exist_ok=True)
        return {
            "ok": True,
            "message": (f"`{action['target_dir']}/` 이미 존재"
                        if existed else f"`{action['target_dir']}/` 신규 생성"),
            "files_affected": [],
        }

    elif op == "delete_files":
        # 삭제는 항상 approval 경로를 통해야 함 — 여기서 직접 실행 안 함
        return {"ok": False,
                "message": "삭제 작업은 pending_approvals 승인 후 실행됩니다",
                "files_affected": []}

    return {"ok": False, "message": f"알 수 없는 op: {op}", "files_affected": []}


def _write_pending(
    approval_file: str,
    suggestion: dict,
    action: dict,
) -> None:
    """
    pending_approvals.json 에 승인 대기 항목 추가.
    기존 파일이 있으면 배열에 append, 없으면 신규 생성.
    """
    existing: list = []
    if os.path.exists(approval_file):
        try:
            with open(approval_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            existing = []

    entry = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "priority":     suggestion["priority"],
        "suggestion":   suggestion["text"],
        "action":       action,
        "status":       "pending",  # "approved" | "rejected" 로 변경하면 실행됨
        "type":         "suggestion",
        "source":       "suggestion_engine",
    }
    existing.append(entry)

    with open(approval_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _op_label(op: str, target_dir: str = "") -> str:
    """내부 op 이름 + target_dir → 사람이 읽기 쉬운 작업명."""
    _MAP = {
        ("mkdir_and_move", "logs"):    "logs/ 이동 적용",
        ("mkdir_and_move", "reports"): "reports/ 보고서 정리",
        ("mkdir_and_move", "config"):  "config/ 설정 파일 통합",
        ("mkdir_and_move", "docs"):    "docs/ 문서 이동",
        ("mkdir_only",     "docs"):    "docs/ 디렉토리 생성",
        ("create_gitignore", ""):      ".gitignore 생성/업데이트",
        ("delete_files",   ""):        "파일 삭제",
    }
    key = (op, target_dir)
    if key in _MAP:
        return _MAP[key]
    return f"{target_dir}/ 작업" if target_dir else op


def _trunc(text: str, maxlen: int = 120) -> str:
    """maxlen 초과 시 끝에 ... 명시. 전체 문장 보존 원칙."""
    return text if len(text) <= maxlen else text[: maxlen - 3] + "..."


def _build_execution_result_section(summ: dict) -> list[str]:
    """
    '후속 실행 결과' 섹션 — workspace_reporter 보고서 말미에 포함.
    _execute_suggestion_list() 반환값을 받아 Markdown 섹션으로 변환.
    항목이 없어도 각 소섹션은 반드시 출력된다.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    auto_executed = summ.get("auto_executed", [])
    pending       = summ.get("pending",       [])
    logged        = summ.get("logged",        [])

    n_ok   = sum(1 for e in auto_executed if e["result"]["ok"])
    n_fail = len(auto_executed) - n_ok
    summary_parts = [f"자동실행 {n_ok}건"]
    if n_fail:
        summary_parts.append(f"실패 {n_fail}건")
    summary_parts += [f"승인대기 {len(pending)}건", f"기록 {len(logged)}건"]

    lines = [
        "",
        "---",
        "",
        "## 후속 실행 결과",
        "",
        f"> 실행 시각: {ts} | {' · '.join(summary_parts)}",
        "",
    ]

    # ── 자동 실행
    lines.append("### 자동 실행된 항목")
    lines.append("")
    if auto_executed:
        for e in auto_executed:
            r      = e["result"]
            n      = len(r.get("files_affected", []))
            label  = _op_label(e["action"], e.get("target_dir", ""))
            if r["ok"]:
                lines.append(f"- [성공] {label} ({n}개 파일)")
                affected = r.get("files_affected", [])
                if affected:
                    preview = ", ".join(f"`{f}`" for f in affected[:6])
                    suffix  = f" 외 {len(affected) - 6}개" if len(affected) > 6 else ""
                    lines.append(f"  - 영향 파일: {preview}{suffix}")
            else:
                lines.append(f"- [실패] {label} — {r['message']}")
    else:
        lines.append(
            "- 추가 이동 대상 없음 "
            "— 워크스페이스가 이미 정리된 상태이거나 이동 대상 파일이 없습니다"
        )
    lines.append("")

    # ── 승인 대기
    lines.append("### 승인 대기 항목")
    lines.append("")
    if pending:
        for i, p in enumerate(pending):
            pri  = p.get("priority", "?")
            text = _trunc(p.get("suggestion", ""))
            lines.append(f"- [대기] ({i}) [{pri}] {text}")
        lines.append("")
        lines.append("> 승인: `python review_pending.py approve <번호|all>`")
        lines.append("> 거절: `python review_pending.py reject  <번호|all>`")
    else:
        lines.append("- 승인 대기 항목 없음")
    lines.append("")

    # ── 기록만
    lines.append("### 기록된 항목 (낮음 — 수동 처리)")
    lines.append("")
    if logged:
        for l in logged:
            text = _trunc(l.get("suggestion", ""))
            lines.append(f"- [기록] {text}")
    else:
        lines.append("- 없음")
    lines.append("")

    return lines
