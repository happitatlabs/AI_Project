#!/usr/bin/env python3
"""
inspect_storage.py — 현재 저장 구조 상태를 사람이 읽기 쉬운 형태로 출력
"""

import argparse
import json
import os
from pathlib import Path

from agent.skill_loader import (
    build_explicit_transition_report,
    build_explicit_transition_report_detail,
    build_skill_metadata_template,
    build_strict_behavior_preflight_summary,
    build_strict_behavior_readiness,
    get_behavior_class_diagnostics,
    load_skills,
    write_skill_metadata_template,
)
from agent.workspace_metrics import (
    build_common_render_sections,
    build_operational_gate_view_from_approvals,
    build_operational_risk_signal,
    load_pending_approvals,
    rank_reopen_candidates,
    scan_workspace,
    summarize_operational_approvals,
    summarize_workspace_risks,
    write_risk_snapshot,
    build_operational_signal,
)


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} B"


def _load_strict_behavior_class_setting(base: Path) -> bool:
    config_path = base / "config.json"
    if not config_path.exists():
        return False
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("skills", {}).get("strict_behavior_class", False))


def _load_effective_strict_behavior_class_setting(base: Path) -> bool:
    return _load_strict_behavior_class_setting(base)


def build_storage_report(base_dir: str) -> str:
    base = Path(base_dir)
    state_file = base / "agent_state.json"
    history_current = base / "history" / "history_current.jsonl"
    archive_dir = base / "archive" / "memory"

    if state_file.exists():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        recent_actions_count = len(state_data.get("recent_actions", []))
    else:
        state_data = {}
        recent_actions_count = 0

    archive_files = sorted(archive_dir.glob("*")) if archive_dir.exists() else []
    history_rotated = sorted((base / "history").glob("history_*.jsonl"))
    legacy_archives = [p for p in archive_files if p.name.startswith("legacy_agent_memory_")]
    metrics_state = scan_workspace(str(base))
    excluded_large_files = metrics_state.get("excluded_large_files", [])
    approval_file = base / "pending_approvals.json"
    approval_entries = load_pending_approvals(approval_file)
    gate_view = build_operational_gate_view_from_approvals(approval_entries)
    approval_summary = summarize_operational_approvals(approval_entries)
    workspace_risk_summary = summarize_workspace_risks(metrics_state.get("decision_files", []))
    skills = load_skills(str(base / "skills"))
    operational_risk_signal = build_operational_risk_signal(base, metrics_state.get("decision_files", []))
    operational_signal = build_operational_signal([], risk_signal=operational_risk_signal, skills=skills)
    risk_delta = operational_risk_signal["risk_delta"]
    action_signal = operational_risk_signal["action_signal"]
    configured_strict_behavior_class = _load_strict_behavior_class_setting(base)
    effective_strict_behavior_class = _load_effective_strict_behavior_class_setting(base)
    behavior_diagnostics = get_behavior_class_diagnostics(skills)
    strict_readiness = build_strict_behavior_readiness(behavior_diagnostics)
    transition_report = build_explicit_transition_report(skills)
    preflight_summary = build_strict_behavior_preflight_summary(skills, risk_signal=operational_risk_signal)
    reopen_candidates = rank_reopen_candidates(skills, operational_risk_signal, priority_order=["workspace_reporter", "file_classifier", "code_reviewer"])
    top_reopen = reopen_candidates[0] if reopen_candidates else {}
    top_suggestion = operational_signal.get("top_suggestion") or {}
    review_render_sections = build_common_render_sections(operational_signal)
    metadata_template = build_skill_metadata_template()
    template_preview = metadata_template.splitlines()[:12]

    lines = [
        "Storage Status",
        f"- state file path: {state_file}",
        f"- state file size: {_format_bytes(state_file.stat().st_size) if state_file.exists() else 'missing'}",
        f"- history current path: {history_current}",
        f"- history current size: {_format_bytes(history_current.stat().st_size) if history_current.exists() else 'missing'}",
        f"- archive/memory file count: {len(archive_files)}",
        f"- recent_actions count: {recent_actions_count}",
        f"- recent rotated file: {history_rotated[-1].name if history_rotated else 'none'}",
        f"- recent legacy archive: {legacy_archives[-1].name if legacy_archives else 'none'}",
        f"- excluded large files: {len(excluded_large_files)}",
        "Operational Gate",
        f"- gate_mode: {gate_view['gate_mode']}",
        f"- approval_status: {gate_view['approval_status']}",
        f"- target: {gate_view['target'] or 'none'}",
        f"- signature: {gate_view['signature'] or 'none'}",
        f"- recommended_action: {gate_view['recommended_action']}",
        f"- risk: {gate_view['risk'] or 'none'}",
        "Operational Approval Summary",
        f"- total_operational_approvals_count: {approval_summary['total_operational_approvals_count']}",
        f"- pending_operational_approvals_count: {approval_summary['pending_operational_approvals_count']}",
        f"- approved_count: {approval_summary['approved_count']}",
        f"- rejected_count: {approval_summary['rejected_count']}",
        f"- recent_targets: {', '.join(approval_summary['recent_targets']) if approval_summary['recent_targets'] else 'none'}",
        "Risk Overview",
        f"- high_risk_count: {workspace_risk_summary['high_risk_count']}",
        f"- medium_risk_count: {workspace_risk_summary['medium_risk_count']}",
        f"- low_risk_count: {workspace_risk_summary['low_risk_count']}",
        f"- primary_risky_path: {workspace_risk_summary['primary_risky_path'] or 'none'}",
        f"- highest_risk: {workspace_risk_summary['highest_risk']}",
        "Risk Baseline",
        f"- baseline_status: {operational_risk_signal['baseline_status']}",
        f"- baseline_reason: {operational_risk_signal.get('baseline_reason', 'none')}",
        f"- baseline_created_at: {operational_risk_signal['baseline_created_at'] or 'none'}",
        f"- baseline_age_seconds: {operational_risk_signal['baseline_age_seconds'] if operational_risk_signal['baseline_age_seconds'] is not None else 'none'}",
        "Risk Delta",
        f"- baseline_status: {risk_delta.get('baseline_status', 'missing')}",
        f"- baseline_reason: {risk_delta.get('baseline_reason', 'none')}",
        f"- high_risk_delta: {risk_delta['high_risk_delta']}",
        f"- new_high_risk_paths: {', '.join(risk_delta['new_high_risk_paths']) if risk_delta['new_high_risk_paths'] else 'none'}",
        f"- resolved_high_risks: {', '.join(risk_delta['resolved_high_risks']) if risk_delta['resolved_high_risks'] else 'none'}",
        "Content Changes",
        f"- content_changed_count: {risk_delta.get('content_changed_count', 0)}",
        f"- content_changed_paths: {', '.join(risk_delta.get('content_changed_paths', [])) if risk_delta.get('content_changed_paths') else 'none'}",
        f"- top_content_change_hint: {risk_delta.get('top_content_change_hint', 'none') or 'none'}",
        "Action Signal",
        f"- action: {action_signal['action']}",
        f"- reason: {action_signal['reason']}",
        f"- primary_path: {action_signal['primary_path'] or 'none'}",
        f"- certainty: {action_signal['certainty']}",
        "Operational Risk Signal",
        f"- risk_action: {action_signal['action']}",
        f"- risk_reason: {action_signal['reason']}",
        f"- risk_primary_path: {action_signal['primary_path'] or 'none'}",
        f"- risk_certainty: {action_signal['certainty']}",
        f"- blocker_candidate: {operational_risk_signal['blocker_candidate'] or 'none'}",
        f"- baseline_status: {operational_risk_signal['baseline_status']}",
        f"- baseline_reason: {operational_risk_signal.get('baseline_reason', 'none')}",
        "Reopen Priority",
        f"- reopen_candidate: {top_reopen.get('skill') or 'none'}",
        f"- reopen_priority: {top_reopen.get('reopen_priority', 0)}",
        f"- reopen_rank_reason: {top_reopen.get('reopen_rank_reason') or 'none'}",
        f"- skill_risk_profile: {top_reopen.get('skill_risk_profile') or 'none'}",
        f"- metadata_weight_applied: {top_reopen.get('metadata_weight_applied', False)}",
        "Suggestion Priority",
        f"- suggestion_priority: {top_suggestion.get('priority', 0)}",
        f"- suggestion_severity: {top_suggestion.get('severity', 'none')}",
        f"- suggestion_certainty: {top_suggestion.get('certainty', 'none')}",
        f"- suggestion_text: {top_suggestion.get('text', 'none')}",
        "Operator Guidance",
        f"- recommended_next_step: {operational_signal.get('recommended_next_step', 'none')}",
        f"- recommended_review_scope: {operational_signal.get('recommended_review_scope', 'none')}",
        f"- priority_bucket: {operational_signal.get('priority_bucket', 'normal')}",
        "Risk Clusters",
        f"- top_cluster: {operational_signal.get('top_risk_cluster_label', 'none')}",
        f"- cluster_severity: {operational_signal.get('top_risk_cluster_severity', 'none')}",
        f"- cluster_path_count: {operational_signal.get('top_risk_cluster_path_count', 0)}",
        f"- cluster_summary_reason: {operational_signal.get('top_risk_cluster_summary_reason', 'none')}",
        f"- cluster_content_changed_count: {operational_signal.get('top_risk_cluster_content_changed_count', 0)}",
        f"- cluster_top_content_changed_path: {operational_signal.get('top_risk_cluster_top_content_changed_path', 'none') or 'none'}",
        f"- cluster_top_content_change_hint: {operational_signal.get('top_risk_cluster_top_content_change_hint', 'none') or 'none'}",
        f"- secondary_cluster: {operational_signal.get('secondary_cluster_compact_line', 'none') or 'none'}",
        f"- additional_cluster_note: {operational_signal.get('additional_cluster_note', 'none') or 'none'}",
        "Review Summary",
    ]
    for section in review_render_sections:
        if section.get("title") == "Metadata / Hints":
            continue
        lines.append(f"- [{section.get('title', 'Section')}]")
        lines.extend(f"  - {value}" for value in section.get("lines", []))
    lines.extend([
        "Metadata Inference",
        f"- inferred_risk_metadata_used: {top_reopen.get('inferred_risk_metadata_used', False)}",
        f"- inferred_from: {top_reopen.get('inferred_from') or 'none'}",
        f"- metadata_mismatch_hint: {operational_signal.get('metadata_mismatch_hint') or 'none'}",
        "Strict Risk Integration",
        f"- risk_blocker_candidate: {preflight_summary['risk_blocker_candidate'] or 'none'}",
        f"- risk_blocker_score: {preflight_summary['risk_blocker_score']}",
        f"- risk_blocker_promoted: {preflight_summary['risk_blocker_promoted']}",
        "Behavior Class",
        f"- configured_strict_behavior_class: {'on' if configured_strict_behavior_class else 'off'}",
        f"- effective_strict_behavior_class: {'on' if effective_strict_behavior_class else 'off'}",
        f"- all_explicit: {behavior_diagnostics['all_explicit']}",
        f"- fallback_skills_count: {len(behavior_diagnostics['fallback_skills'])}",
        f"- explicit_transition_needed_count: {len(behavior_diagnostics['explicit_transition_needed'])}",
        f"- inconsistent_behavior_class_skills_count: {len(behavior_diagnostics['inconsistent_behavior_class_skills'])}",
        f"- consistency_warnings_count: {len(behavior_diagnostics['consistency_warnings'])}",
        "Strict Readiness",
        f"- strict_ready: {strict_readiness['strict_ready']}",
        f"- strict_readiness_mode: {strict_readiness['mode']}",
        f"- fallback_skill_count: {strict_readiness['fallback_skill_count']}",
        f"- explicit_transition_needed_count: {strict_readiness['explicit_transition_needed_count']}",
        f"- blockers: {', '.join(strict_readiness['blockers']) if strict_readiness['blockers'] else 'none'}",
        "Explicit Transition Report",
        f"- fallback_skills: {', '.join(transition_report['fallback_skills']) if transition_report['fallback_skills'] else 'none'}",
        f"- inconsistent_behavior_class_skills: {', '.join(transition_report['inconsistent_behavior_class_skills']) if transition_report['inconsistent_behavior_class_skills'] else 'none'}",
        f"- explicit_transition_needed: {', '.join(transition_report['explicit_transition_needed']) if transition_report['explicit_transition_needed'] else 'none'}",
        f"- strict_blockers: {', '.join(transition_report['strict_blockers']) if transition_report['strict_blockers'] else 'none'}",
        f"- suggested_behavior_class: {', '.join(f'{name}->{value}' for name, value in transition_report['suggested_behavior_class'].items()) if transition_report['suggested_behavior_class'] else 'none'}",
        "Strict Preflight Summary",
        f"- ready: {preflight_summary['ready']}",
        f"- fallback_blocker_count: {preflight_summary['fallback_blocker_count']}",
        f"- consistency_blocker_count: {preflight_summary['consistency_blocker_count']}",
        f"- primary_blocker: {preflight_summary['primary_blocker'] or 'none'}",
        "Skill Metadata Template",
    ])
    lines.extend(f"  {line}" for line in template_preview if line)
    if excluded_large_files:
        lines.append("- excluded large file list:")
        for item in excluded_large_files[:5]:
            lines.append(f"  - {item['path']} ({_format_bytes(item['size'])})")
    return "\n".join(lines)


def build_transition_detail_report(base_dir: str) -> str:
    base = Path(base_dir)
    skills = load_skills(str(base / "skills"))
    detail = build_explicit_transition_report_detail(skills)

    lines = [
        "Transition Detail",
        f"- fallback_skills: {', '.join(detail['fallback_skills']) if detail['fallback_skills'] else 'none'}",
        f"- inconsistent_behavior_class_skills: {', '.join(detail['inconsistent_behavior_class_skills']) if detail['inconsistent_behavior_class_skills'] else 'none'}",
        f"- explicit_transition_needed: {', '.join(detail['explicit_transition_needed']) if detail['explicit_transition_needed'] else 'none'}",
        f"- strict_blockers: {', '.join(detail['strict_blockers']) if detail['strict_blockers'] else 'none'}",
        "Skill Details",
    ]
    for skill in detail["skills"]:
        blocker_reason = ", ".join(skill["strict_blocker_reasons"]) if skill["strict_blocker_reasons"] else "none"
        suggested = skill["suggested_behavior_class"] or "none"
        lines.append(
            f"- {skill['name']}: class={skill['behavior_class']}, "
            f"source={skill['behavior_class_source']}, "
            f"suggested={suggested}, "
            f"strict_blocker={skill['strict_blocker']}, "
            f"reason={blocker_reason}"
        )
    return "\n".join(lines)


def write_skill_template_file(base_dir: str, target: str) -> str:
    base = Path(base_dir)
    result = write_skill_metadata_template(base / target)
    return (
        f"Skill Template\n"
        f"- created: {result['created']}\n"
        f"- path: {result['path']}\n"
        f"- reason: {result['reason']}\n"
        f"- suggested_behavior_class: {result.get('suggested_behavior_class', 'none')}"
    )


def export_transition_report_file(base_dir: str, target: str) -> str:
    base = Path(base_dir)
    export_path = base / target
    if export_path.exists():
        return (
            f"Transition Report Export\n"
            f"- exported: False\n"
            f"- path: {export_path}\n"
            f"- reason: exists"
        )

    export_path.parent.mkdir(parents=True, exist_ok=True)
    skills = load_skills(str(base / "skills"))
    payload = build_explicit_transition_report_detail(skills)
    export_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return (
        f"Transition Report Export\n"
        f"- exported: True\n"
        f"- path: {export_path}\n"
        f"- reason: created"
    )


def write_risk_snapshot_file(base_dir: str, target: str | None = None) -> str:
    base = Path(base_dir)
    metrics_state = scan_workspace(str(base))
    result = write_risk_snapshot(base, metrics_state.get("decision_files", []), target=target)
    return (
        f"Risk Snapshot\n"
        f"- saved: {result['saved']}\n"
        f"- path: {result['path']}\n"
        f"- requested_path: {result['requested_path']}\n"
        f"- entries: {result['entries']}"
    )


def write_baseline_file(base_dir: str, target: str | None = None) -> str:
    base = Path(base_dir)
    metrics_state = scan_workspace(str(base))
    result = write_risk_snapshot(
        base,
        metrics_state.get("decision_files", []),
        target=target,
        source="baseline",
    )
    return (
        f"Baseline Snapshot\n"
        f"- saved: {result['saved']}\n"
        f"- path: {result['path']}\n"
        f"- requested_path: {result['requested_path']}\n"
        f"- entries: {result['entries']}"
    )
    return (
        f"Transition Report Export\n"
        f"- exported: True\n"
        f"- path: {export_path}\n"
        f"- reason: created"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition-detail", action="store_true")
    parser.add_argument("--export-transition-report", dest="export_transition_report", help="Export transition report JSON safely")
    parser.add_argument("--write-risk-snapshot", dest="write_risk_snapshot", nargs="?", const="reports/risk_snapshot.json", help="Write current risk snapshot safely")
    parser.add_argument("--write-baseline", dest="write_baseline", nargs="?", const="reports/risk_snapshot.json", help="Write current state as baseline snapshot safely")
    parser.add_argument("--write-skill-template", dest="write_skill_template", help="Create a SKILL.md template safely")
    args = parser.parse_args()

    base_dir = os.getcwd()
    if args.transition_detail:
        print(build_transition_detail_report(base_dir))
        return 0
    if args.export_transition_report:
        print(export_transition_report_file(base_dir, args.export_transition_report))
        return 0
    if args.write_risk_snapshot is not None:
        print(write_risk_snapshot_file(base_dir, args.write_risk_snapshot))
        return 0
    if args.write_baseline is not None:
        print(write_baseline_file(base_dir, args.write_baseline))
        return 0
    if args.write_skill_template:
        print(write_skill_template_file(base_dir, args.write_skill_template))
        return 0

    print(build_storage_report(base_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
