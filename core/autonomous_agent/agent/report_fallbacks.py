import logging
import os
from datetime import datetime

from .workspace_metrics import build_review_summary_lines

logger = logging.getLogger("report_fallbacks")


def headline_summary(message: str) -> str:
    summary = f"[Summary] {message}"
    logger.info(summary)
    return summary


def report_signature(state: dict, top_ext_text: str) -> str:
    return (
        f"files={state.get('total_files', 0)};"
        f"dirs={state.get('total_dirs', 0)};"
        f"size={state.get('total_size_bytes', 0)};"
        f"top={top_ext_text}"
    )


def summarize_top_extensions(files: list[str]) -> str:
    ext_counts: dict[str, int] = {}
    for path in files:
        ext = os.path.splitext(path)[1] or "(no ext)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    top_ext = sorted(ext_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    return ", ".join(f"`{ext}` {count}개" for ext, count in top_ext) if top_ext else "확장자 정보 없음"


def build_report_only_lines(state: dict, review_summary: dict | None = None) -> tuple[list[str], str]:
    top_ext_text = summarize_top_extensions(state.get("files", []))
    signature = report_signature(state, top_ext_text)
    files = state.get("files", [])[:8]
    lines = [
        "# 에이전트 핵심 상태 요약",
        f"생성 시각: {datetime.now().isoformat()}",
        f"<!-- report_signature: {signature} -->",
        "## 요약",
        (
            f"현재 워크스페이스는 파일 {state.get('total_files', 0)}개, 디렉토리 {state.get('total_dirs', 0)}개, "
            f"총 {state.get('total_size_bytes', 0):,} bytes 규모이며 주요 확장자는 {top_ext_text}이다."
        ),
        "",
        "## 핵심 상태",
        f"- 파일 수: {state.get('total_files', 0)}",
        f"- 디렉토리 수: {state.get('total_dirs', 0)}",
        f"- 총 크기: {state.get('total_size_bytes', 0):,} bytes",
        f"- 스캔 시각: {state.get('scanned_at', '')}",
        "",
        "## 참고 파일",
    ]
    summary_lines = build_review_summary_lines(review_summary)
    if summary_lines:
        lines[4:4] = summary_lines + [""]
    lines.extend([f"- {path}" for path in files] or ["- 참고 파일 없음"])
    return lines, signature


def build_change_summary_lines(current_state: dict, previous_state: dict) -> tuple[list[str], dict]:
    prev_files = set(previous_state.get("files", []))
    curr_files = set(current_state.get("files", []))
    added_files = sorted(curr_files - prev_files)[:10]
    removed_files = sorted(prev_files - curr_files)[:10]
    stats = {
        "added_count": len(curr_files - prev_files),
        "removed_count": len(prev_files - curr_files),
        "added_files": added_files,
        "removed_files": removed_files,
    }
    lines = [
        "# 최근 변화 요약",
        f"- 생성 시각: {datetime.now().isoformat()}",
        f"- 현재 파일 수: {current_state.get('total_files', 0)}",
        f"- 이전 파일 수: {len(previous_state.get('files', []))}",
        f"- 파일 변화량: {current_state.get('total_files', 0) - len(previous_state.get('files', []))}",
        "",
        "## 추가된 파일",
    ]
    lines.extend([f"- {path}" for path in added_files] or ["- 감지된 신규 파일 없음"])
    lines.extend(["", "## 제거된 파일"])
    lines.extend([f"- {path}" for path in removed_files] or ["- 감지된 제거 파일 없음"])
    return lines, stats


def _history_action_label(entry: dict) -> str:
    if "action_type" in entry or "skill_name" in entry or "fallback_name" in entry:
        if entry.get("event") == "skill":
            return entry.get("skill_name") or entry.get("action_type") or "unknown"
        if entry.get("event") == "fallback":
            return entry.get("fallback_name") or entry.get("action_type") or "fallback"
        return (
            entry.get("skill_name")
            or entry.get("fallback_name")
            or entry.get("action_type")
            or "unknown"
        )

    action = entry.get("action", {})
    action_type = action.get("type", "unknown")
    if action_type == "skill":
        return action.get("skill_name") or action_type
    if action.get("source") == "cooldown_fallback":
        return action.get("fallback_kind") or action_type
    return action_type


def _history_status(entry: dict) -> str:
    return entry.get("status") or entry.get("evaluation", {}).get("status", "unknown")


def build_memory_analysis_lines(history: list[dict], recent_actions: list[dict]) -> list[str]:
    action_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for entry in history:
        action_label = _history_action_label(entry)
        action_counts[action_label] = action_counts.get(action_label, 0) + 1
        status = _history_status(entry)
        status_counts[status] = status_counts.get(status, 0) + 1

    repeated = [name for name, count in action_counts.items() if count >= 2]
    dominant_action, dominant_count = max(action_counts.items(), key=lambda item: item[1], default=("unknown", 0))
    total_history = len(history)
    dominant_ratio = (dominant_count / total_history * 100) if total_history else 0
    recent_fallbacks = [entry.get("skill") for entry in recent_actions if entry.get("skill")]

    problems = []
    if repeated:
        repeated_text = ", ".join(repeated)
        cause = (
            "동일한 cooldown fallback 또는 유사 행동이 연속 선택되어 탐색 폭이 줄어든 것으로 보인다."
            if any(name in {"report_only", "change_summarizer", "memory_analyzer"} for name in repeated)
            else "성공 기준이 좁거나 목표 해석이 단일 패턴에 고정되어 반복 선택이 발생한 것으로 보인다."
        )
        problems.append(f"- 반복 패턴 원인: `{repeated_text}` 반복이 감지됨. 원인 추정: {cause}")
    if dominant_ratio >= 50:
        problems.append(
            f"- 행동 편향: 최근 행동의 {dominant_ratio:.0f}%가 `{dominant_action}`에 집중됨. "
            "분석/보고/생성 간 균형이 깨져 다른 대안을 검증하지 못하고 있다."
        )
    if status_counts.get("failure", 0) + status_counts.get("partial", 0) >= max(1, total_history // 2):
        problems.append(
            "- 성과 불안정: failure/partial 비중이 높아 동일 루프를 반복해도 개선 신호가 약하다. "
            "선택 근거와 종료 기준이 충분히 분리되지 않은 상태로 보인다."
        )
    if recent_fallbacks.count("report_only") >= 2:
        problems.append(
            "- fallback 의존: `report_only` 계열 기록이 반복되어 실제 변화 분석보다 상태 요약으로 회피하는 경향이 있다."
        )
    while len(problems) < 2:
        problems.append(
            "- 관찰 부족: 최근 행동 수가 적어 강한 패턴은 제한적이지만, 현재 기록만으로는 목표 대비 행동 다양성을 입증하기 어렵다."
        )

    suggestions = [
        "- 개선 제안 1: 반복된 행동이 2회 이상 감지되면 다른 fallback 또는 다른 action type에 가중치를 주어 탐색 폭을 강제로 넓힌다.",
        "- 개선 제안 2: dominant action 비율이 50%를 넘으면 다음 사이클에서 상반된 성격의 행동(예: report -> analyze/create)을 우선 검토한다.",
        "- 개선 제안 3: partial/failure가 누적되면 동일 행동 재시도 전 필요 입력이나 상태 차이를 먼저 점검하도록 조건을 추가한다.",
    ]

    lines = [
        "# 최근 행동 분석",
        f"- 생성 시각: {datetime.now().isoformat()}",
        f"- 분석 대상 행동 수: {len(history)}",
        "",
        "## 요약",
        (
            f"최근 {len(history)}개 행동 중 가장 자주 실행된 유형은 `{dominant_action}` "
            f"({dominant_count}회, {dominant_ratio:.0f}%)이며, "
            f"fallback 기록은 {', '.join(recent_fallbacks[-3:]) if recent_fallbacks else '없음'} 수준이다."
        ),
        "",
        "## 행동 분포",
    ]
    if action_counts:
        for name, count in sorted(action_counts.items()):
            lines.append(f"- {name}: {count}회")
    else:
        lines.append("- 최근 행동 이력이 부족합니다.")

    lines.extend(["", "## 문제점"])
    lines.extend(problems)
    lines.extend(["", "## 개선 제안"])
    lines.extend(suggestions)
    return lines
