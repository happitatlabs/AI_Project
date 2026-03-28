import json
import os
import sys
from pathlib import Path

import pytest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def _parse_timestamp_for_test(value: str):
    from datetime import datetime, timezone
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

from agent.executor import Executor
from agent.report_fallbacks import build_memory_analysis_lines
from agent.report_fallbacks import build_report_only_lines
from agent.report_retention import write_report_with_retention
from agent.skill_executor import SkillExecutor, _inspect_log_layout
from agent.skill_loader import (
    build_explicit_transition_report,
    build_explicit_transition_report_detail,
    build_skill_metadata_template,
    build_strict_behavior_preflight,
    build_strict_risk_integration,
    build_strict_behavior_preflight_summary,
    build_strict_behavior_readiness,
    get_behavior_class_diagnostics,
    get_behavior_class_consistency_diagnostics,
    list_behavior_class_fallback_skills,
    suggest_behavior_class,
    load_skills,
    write_skill_metadata_template,
)
from agent.workspace_metrics import (
    annotate_changes,
    attach_content_summary_to_clusters,
    build_action_signal,
    build_atomicity_policy,
    build_atomic_write_contract,
    build_apply_abort_conditions,
    build_apply_precheck,
    build_real_apply_gate,
    build_apply_state_machine,
    build_apply_transaction,
    build_apply_dry_run,
    build_apply_plan,
    build_backup_plan,
    build_backup_materialization_contract,
    build_executor_spec,
    build_failure_handling_policy,
    build_rollback_plan,
    build_rollback_execution_contract,
    build_rollback_triggers,
    build_multi_cluster_compact_summary,
    build_diff_hint,
    build_dry_run_payload,
    build_clustered_guidance,
    build_content_metadata,
    build_content_signature,
    build_operator_guidance,
    build_operational_gate_view,
    build_operational_gate_view_from_approvals,
    build_operational_risk_signal,
    build_operational_signal,
    build_risk_clusters,
    build_risk_suggestions,
    build_risk_snapshot,
    build_review_summary_lines,
    build_review_summary_payload,
    build_summary_wording,
    score_risk_decision_signal,
    build_state_summary,
    build_warning_signatures,
    collect_self_artifact_candidates,
    compute_risk_delta,
    compute_state_diff,
    create_pending_approvals,
    create_proposal,
    evaluate_snapshot_freshness,
    is_self_artifact,
    load_staging_executor_spec,
    load_latest_risk_snapshot,
    load_pending_approvals,
    load_proposal_by_review_id,
    load_staging_apply_plan,
    load_staging_apply_transaction,
    load_staging_precheck,
    process_review_decision,
    build_post_apply_validation,
    build_pre_apply_validation,
    build_target_resolution_contract,
    build_transaction_markers,
    build_transaction_state_contract,
    validate_apply_plan,
    rank_reopen_candidates,
    resolve_operational_gate,
    scan_workspace,
    should_suppress_warning,
    summarize_operational_approvals,
    summarize_risk_changes,
    summarize_workspace_risks,
    update_pending_approval_status,
    write_risk_snapshot,
)


def test_main_report_retention_archives_old_files(tmp_path):
    for idx in range(4):
        write_report_with_retention(
            str(tmp_path),
            f"workspace_reporter_20260321_19060{idx}.md",
            [f"# report {idx}"],
        )

    reports = list((tmp_path / "reports").glob("workspace_reporter_*.md"))
    archived = list((tmp_path / "archive" / "reports").glob("workspace_reporter_*.md"))

    assert len(reports) == 3
    assert len(archived) == 1


def test_fallback_retention_does_not_conflict_with_main_reports(tmp_path):
    for idx in range(4):
        write_report_with_retention(
            str(tmp_path),
            f"change_summary_20260321_19100{idx}.md",
            [f"# change {idx}"],
        )
        write_report_with_retention(
            str(tmp_path),
            f"file_classifier_20260321_19110{idx}.md",
            [f"# classifier {idx}"],
        )

    change_reports = list((tmp_path / "reports").glob("change_summary_*.md"))
    classifier_reports = list((tmp_path / "reports").glob("file_classifier_*.md"))
    archived_changes = list((tmp_path / "archive" / "reports").glob("change_summary_*.md"))
    archived_classifier = list((tmp_path / "archive" / "reports").glob("file_classifier_*.md"))

    assert len(change_reports) == 3
    assert len(classifier_reports) == 3
    assert len(archived_changes) == 1
    assert len(archived_classifier) == 1


def test_workspace_metrics_sum_small_files_and_subdirs(tmp_path):
    (tmp_path / "a.txt").write_text("aa", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bbb", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "c.txt").write_text("cccc", encoding="utf-8")

    state = scan_workspace(str(tmp_path))

    assert state["total_files"] == 3
    assert state["total_size_bytes"] == 9


def test_workspace_metrics_full_snapshot_includes_reports_but_decision_excludes_them(tmp_path):
    (tmp_path / "a.txt").write_text("1234", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "r.md").write_text("123456", encoding="utf-8")

    state = scan_workspace(str(tmp_path))

    assert state["total_size_bytes"] == 10
    assert state["decision_total_size_bytes"] == 4
    assert any(path.replace("\\", "/") == "reports/r.md" for path in state["files"])
    assert all(path.replace("\\", "/") != "reports/r.md" for path in state["decision_files"])


def test_workspace_metrics_avoids_double_counting_hardlinks(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("12345", encoding="utf-8")
    linked = tmp_path / "linked.txt"
    try:
        os.link(source, linked)
    except OSError:
        pytest.skip("hard link not supported in this environment")

    state = scan_workspace(str(tmp_path))

    assert state["total_files"] == 1
    assert state["total_size_bytes"] == 5


def test_workspace_metrics_excludes_broken_memory_files(tmp_path):
    (tmp_path / "small.txt").write_text("1234", encoding="utf-8")
    (tmp_path / "agent_memory_broken_large.json").write_text("x" * 4096, encoding="utf-8")

    state = scan_workspace(str(tmp_path))

    assert state["total_files"] == 1
    assert state["total_size_bytes"] == 4
    assert any(item["path"] == "agent_memory_broken_large.json" for item in state["excluded_files"])


def test_workspace_metrics_marks_self_artifact_and_external_diffs(tmp_path):
    before = scan_workspace(str(tmp_path))

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "report_20260322_010101.md").write_text("report", encoding="utf-8")
    after_report = scan_workspace(str(tmp_path))
    report_diff = compute_state_diff(before, after_report)

    assert report_diff["full_changed"] is True
    assert report_diff["decision_changed"] is False
    assert report_diff["self_artifact_changed"] is True
    assert report_diff["external_changed"] is False

    (tmp_path / "run.log").write_text("log", encoding="utf-8")
    after_log = scan_workspace(str(tmp_path))
    log_diff = compute_state_diff(after_report, after_log)

    assert log_diff["decision_changed"] is False
    assert is_self_artifact("run.log") is True

    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    after_code = scan_workspace(str(tmp_path))
    code_diff = compute_state_diff(after_log, after_code)

    assert code_diff["decision_changed"] is True
    assert code_diff["external_changed"] is True


def test_workspace_metrics_detects_mixed_self_artifact_and_external_changes(tmp_path):
    before = scan_workspace(str(tmp_path))
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "report_20260322_010101.md").write_text("report", encoding="utf-8")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["full_changed"] is True
    assert diff["decision_changed"] is True
    assert diff["self_artifact_changed"] is True
    assert diff["external_changed"] is True


def test_workspace_metrics_treats_agent_state_json_as_self_artifact_only(tmp_path):
    before = scan_workspace(str(tmp_path))
    (tmp_path / "agent_state.json").write_text("{}", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["full_changed"] is True
    assert diff["decision_changed"] is False
    assert diff["external_changed"] is False
    assert "agent_state.json" in diff["added_self_artifacts"]
    assert diff["added_external_paths"] == []
    assert diff["removed_external_paths"] == []


def test_workspace_metrics_treats_pending_approvals_json_as_self_artifact_only(tmp_path):
    before = scan_workspace(str(tmp_path))
    (tmp_path / "pending_approvals.json").write_text("{}", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["full_changed"] is True
    assert diff["decision_changed"] is False
    assert diff["external_changed"] is False
    assert "pending_approvals.json" in diff["added_self_artifacts"]
    assert diff["added_external_paths"] == []


def test_workspace_metrics_treats_agent_pid_as_self_artifact_only(tmp_path):
    before = scan_workspace(str(tmp_path))
    (tmp_path / "agent.pid").write_text("1234", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["full_changed"] is True
    assert diff["decision_changed"] is False
    assert diff["external_changed"] is False
    assert "agent.pid" in diff["added_self_artifacts"]
    assert diff["added_external_paths"] == []


def test_workspace_metrics_detects_external_plus_agent_state_mixed_change(tmp_path):
    before = scan_workspace(str(tmp_path))
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "agent_state.json").write_text("{}", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["decision_changed"] is True
    assert diff["external_changed"] is True
    assert any(path.replace("\\", "/") == "src/app.py" for path in diff["added_external_paths"])
    assert "agent_state.json" in diff["added_self_artifacts"]


def test_workspace_metrics_treats_runtime_support_files_as_self_artifacts(tmp_path):
    before = scan_workspace(str(tmp_path))
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "history_20260322_01.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "runtime_trace.tmpdata").write_text("trace", encoding="utf-8")
    (tmp_path / "service.pid.lock").write_text("1", encoding="utf-8")

    after = scan_workspace(str(tmp_path))
    diff = compute_state_diff(before, after)

    assert diff["decision_changed"] is False
    assert diff["external_changed"] is False
    assert any(path.replace("\\", "/") == "history/history_20260322_01.jsonl" for path in diff["added_self_artifacts"])
    assert "runtime_trace.tmpdata" in diff["added_self_artifacts"]
    assert "service.pid.lock" in diff["added_self_artifacts"]
    assert diff["added_external_paths"] == []


def test_build_state_summary_for_self_artifact_only_change():
    changes = annotate_changes(["agent_state.json", "reports/report_20260322_010101.md"])
    summary = build_state_summary(changes)

    assert all(change["self_artifact"] is True for change in changes)
    assert summary == {
        "external_change": False,
        "risky_change": False,
        "self_artifact_only": True,
        "recommended_action": "ignore",
    }


def test_build_state_summary_for_low_risk_external_change():
    changes = annotate_changes(["docs/guide.md"])
    summary = build_state_summary(changes)

    assert changes[0]["self_artifact"] is False
    assert changes[0]["risk"] == "LOW"
    assert summary == {
        "external_change": True,
        "risky_change": False,
        "self_artifact_only": False,
        "recommended_action": "observe",
    }


def test_build_state_summary_for_high_risk_external_change():
    changes = annotate_changes(["src/app.py", "agent_state.json"])
    summary = build_state_summary(changes)

    assert any(change["path"] == "src/app.py" and change["risk"] == "HIGH" for change in changes)
    assert any(change["path"] == "agent_state.json" and change["self_artifact"] is True for change in changes)
    assert summary == {
        "external_change": True,
        "risky_change": True,
        "self_artifact_only": False,
        "recommended_action": "review_file",
    }


def test_classify_risk_marks_runtime_temp_as_ignore_and_configs_as_high():
    changes = annotate_changes([
        "src/app.py",
        "config/settings.yaml",
        "runtime_trace.tmpdata",
        "docs/guide.md",
        "notes/cache.tmp",
    ])

    assert any(change["path"] == "src/app.py" and change["risk"] == "HIGH" for change in changes)
    assert any(change["path"] == "config/settings.yaml" and change["risk"] == "HIGH" for change in changes)
    assert any(change["path"] == "runtime_trace.tmpdata" and change["risk"] == "IGNORE" for change in changes)
    assert any(change["path"] == "docs/guide.md" and change["risk"] == "LOW" for change in changes)
    assert any(change["path"] == "notes/cache.tmp" and change["risk"] == "LOW" for change in changes)


def test_summarize_risk_changes_highlights_primary_risky_path():
    summary = summarize_risk_changes(annotate_changes([
        "src/app.py",
        "config/settings.yaml",
        "docs/guide.md",
        "runtime_trace.tmpdata",
    ]))

    assert summary["high_risk_count"] == 2
    assert summary["low_risk_count"] == 1
    assert summary["ignored_count"] == 1
    assert summary["highest_risk"] == "HIGH"
    assert summary["primary_risky_path"] == "src/app.py"


def test_summarize_workspace_risks_uses_decision_files_only():
    summary = summarize_workspace_risks([
        "src/app.py",
        "config/settings.json",
        "docs/readme.md",
        "agent_state.json",
    ])

    assert summary["high_risk_count"] == 2
    assert summary["low_risk_count"] == 1
    assert summary["ignored_count"] == 1
    assert summary["primary_risky_path"] == "src/app.py"


def test_write_risk_snapshot_saves_minimal_entries_and_avoids_overwrite(tmp_path):
    result_one = write_risk_snapshot(
        tmp_path,
        ["src/app.py", "config/settings.yaml", "agent_state.json"],
    )
    result_two = write_risk_snapshot(
        tmp_path,
        ["src/app.py", "config/settings.yaml", "agent_state.json"],
    )

    assert result_one["saved"] is True
    assert result_two["saved"] is True
    assert result_one["path"] != result_two["path"]
    payload = json.loads(Path(result_one["path"]).read_text(encoding="utf-8"))
    assert payload["entries"] == [
        {"path": "config/settings.yaml", "severity": "HIGH"},
        {"path": "src/app.py", "severity": "HIGH"},
    ]


def test_load_latest_risk_snapshot_returns_newest_file(tmp_path):
    first = write_risk_snapshot(tmp_path, ["src/app.py"])
    second = write_risk_snapshot(tmp_path, ["config/settings.yaml"])

    latest = load_latest_risk_snapshot(tmp_path)

    assert latest["path"] == second["path"]
    assert latest["entries"] == [{"path": "config/settings.yaml", "severity": "HIGH"}]
    assert latest["source"] == "inspect"


def test_evaluate_snapshot_freshness_handles_fresh_stale_and_missing():
    fresh = evaluate_snapshot_freshness({
        "created_at": "2026-03-22T10:00:00Z",
        "entries": [{"path": "src/app.py", "severity": "HIGH"}],
    }, now=_parse_timestamp_for_test("2026-03-22T12:00:00Z"))
    stale = evaluate_snapshot_freshness({
        "created_at": "2026-03-20T10:00:00Z",
        "entries": [{"path": "src/app.py", "severity": "HIGH"}],
    }, now=_parse_timestamp_for_test("2026-03-22T12:00:00Z"))
    missing = evaluate_snapshot_freshness({}, now=_parse_timestamp_for_test("2026-03-22T12:00:00Z"))

    assert fresh["baseline_status"] == "fresh"
    assert fresh["baseline_stale"] is False
    assert fresh["baseline_reason"] == "fresh_snapshot"
    assert stale["baseline_status"] == "stale"
    assert stale["baseline_stale"] is True
    assert stale["baseline_reason"] == "stale_snapshot"
    assert missing["baseline_status"] == "missing"
    assert missing["baseline_age_seconds"] is None
    assert missing["baseline_reason"] == "initial_scan"


def test_legacy_risk_snapshot_without_created_at_uses_mtime_fallback(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    legacy_path = reports_dir / "risk_snapshot.json"
    legacy_path.write_text(json.dumps({
        "entries": [{"path": "src/app.py", "severity": "HIGH"}],
    }, ensure_ascii=False), encoding="utf-8")

    snapshot = load_latest_risk_snapshot(tmp_path)
    freshness = evaluate_snapshot_freshness(snapshot)

    assert snapshot["source"] == "legacy"
    assert freshness["baseline_status"] in {"fresh", "stale"}
    assert freshness["baseline_created_at"] is not None


def test_evaluate_snapshot_freshness_preserves_missing_snapshot_reason():
    freshness = evaluate_snapshot_freshness({
        "path": "reports/risk_snapshot.json",
        "entries": [],
        "baseline_reason": "missing_snapshot",
    })

    assert freshness["baseline_status"] == "missing"
    assert freshness["baseline_reason"] == "missing_snapshot"


def test_compute_risk_delta_tracks_high_risk_changes_by_path():
    previous = build_risk_snapshot([
        "src/core/engine.py",
        "scripts/old_runner.py",
        "docs/guide.md",
    ])
    current = build_risk_snapshot([
        "src/core/engine.py",
        "config/prod.yaml",
        "docs/guide.md",
        "notes/readme.txt",
    ])

    delta = compute_risk_delta(previous, current)

    assert delta == {
        "high_risk_delta": 0,
        "medium_risk_delta": 0,
        "low_risk_delta": 1,
        "new_high_risk_paths": ["config/prod.yaml"],
        "resolved_high_risks": ["scripts/old_runner.py"],
        "persistent_high_risks": ["src/core/engine.py"],
    }


def test_compute_risk_delta_includes_baseline_meta():
    previous = build_risk_snapshot(["src/core/engine.py"])
    current = build_risk_snapshot(["src/core/engine.py", "config/prod.yaml"])

    delta = compute_risk_delta(previous, current, baseline_meta={
        "baseline_status": "stale",
        "baseline_created_at": "2026-03-20T00:00:00Z",
        "baseline_age_seconds": 200000,
        "baseline_stale": True,
        "baseline_reason": "stale_snapshot",
    })

    assert delta["baseline_status"] == "stale"
    assert delta["baseline_created_at"] == "2026-03-20T00:00:00Z"
    assert delta["baseline_age_seconds"] == 200000
    assert delta["baseline_stale"] is True
    assert delta["baseline_reason"] == "stale_snapshot"


def test_build_content_signature_ignores_json_key_order_and_trailing_whitespace(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{\n  "b": 2,\n  "a": 1\n}\n', encoding="utf-8")
    first = build_content_signature({"path": "config.json"}, workspace=tmp_path)

    config_path.write_text('{"a":1,"b":2}   \n\n', encoding="utf-8")
    second = build_content_signature({"path": "config.json"}, workspace=tmp_path)

    assert first == second


def test_build_diff_hint_detects_json_key_changes(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"a": 1}\n', encoding="utf-8")
    previous = {
        "path": "config.json",
        "severity": "HIGH",
        "content_meta": build_content_metadata({"path": "config.json"}, workspace=tmp_path),
    }

    config_path.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
    current = {
        "path": "config.json",
        "severity": "HIGH",
        "content_meta": build_content_metadata({"path": "config.json"}, workspace=tmp_path),
    }

    hint = build_diff_hint(previous, current)

    assert hint["type"] == "json_keys_changed"
    assert hint["text"] == "config.json: json keys changed"


def test_build_diff_hint_uses_generic_text_hint_for_plain_text_changes(tmp_path):
    note_path = tmp_path / "rules.txt"
    note_path.write_text("alpha\nbeta\n", encoding="utf-8")
    previous = {
        "path": "rules.txt",
        "severity": "MEDIUM",
        "content_meta": build_content_metadata({"path": "rules.txt"}, workspace=tmp_path),
    }

    note_path.write_text("gamma\ndelta\n", encoding="utf-8")
    current = {
        "path": "rules.txt",
        "severity": "MEDIUM",
        "content_meta": build_content_metadata({"path": "rules.txt"}, workspace=tmp_path),
    }

    hint = build_diff_hint(previous, current)

    assert hint["type"] == "text_modified"
    assert hint["text"] == "rules.txt: text modified"


def test_compute_risk_delta_marks_same_path_same_severity_same_content_as_unchanged(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file_path = src_dir / "app.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    previous = build_risk_snapshot(["src/app.py"], workspace=tmp_path)
    current = build_risk_snapshot(["src/app.py"], workspace=tmp_path)

    delta = compute_risk_delta(previous, current)

    assert delta["content_changed"] is False
    assert delta["content_change_type"] == "same"
    assert delta["comparison_basis"] == "path+severity+content"
    assert delta["content_changed_count"] == 0
    assert delta["content_changed_paths"] == []
    assert delta["persistent_same_paths"] == ["src/app.py"]
    assert delta["persistent_content_changed_paths"] == []
    assert delta["content_change_hints"] == {}


def test_compute_risk_delta_marks_same_path_same_severity_changed_content(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    file_path = config_dir / "prod.yaml"
    file_path.write_text("mode: prod\n", encoding="utf-8")
    previous = build_risk_snapshot(["config/prod.yaml"], workspace=tmp_path)

    file_path.write_text("mode: prod\nfeature_flag: true\n", encoding="utf-8")
    current = build_risk_snapshot(["config/prod.yaml"], workspace=tmp_path)

    delta = compute_risk_delta(previous, current)

    assert delta["high_risk_delta"] == 0
    assert delta["new_high_risk_paths"] == []
    assert delta["persistent_high_risks"] == ["config/prod.yaml"]
    assert delta["content_changed"] is True
    assert delta["content_change_type"] == "modified"
    assert delta["content_changed_count"] == 1
    assert delta["content_changed_paths"] == ["config/prod.yaml"]
    assert delta["top_content_changed_path"] == "config/prod.yaml"
    assert delta["content_change_hint_types"]["config/prod.yaml"] == "line_count_changed"
    assert delta["top_content_change_hint"] == "config/prod.yaml: line count changed"
    assert delta["persistent_content_changed_paths"] == ["config/prod.yaml"]


def test_compute_risk_delta_keeps_severity_change_separate_from_content():
    previous = {
        "entries": [{
            "path": "config/prod.yaml",
            "severity": "MEDIUM",
            "content_signature": "before",
        }]
    }
    current = {
        "entries": [{
            "path": "config/prod.yaml",
            "severity": "HIGH",
            "content_signature": "after",
        }]
    }

    delta = compute_risk_delta(previous, current)

    assert delta["high_risk_delta"] == 1
    assert delta["new_high_risk_paths"] == ["config/prod.yaml"]
    assert delta["content_changed"] is False
    assert delta["severity_changed_paths"] == ["config/prod.yaml"]
    assert delta["content_changed_paths"] == []


def test_compute_risk_delta_does_not_force_content_change_for_missing_or_legacy_baseline(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")

    current = build_risk_snapshot(["src/app.py"], workspace=tmp_path)
    delta = compute_risk_delta({"entries": []}, current, baseline_meta={"baseline_status": "missing"})

    assert delta["high_risk_delta"] == 1
    assert delta["new_high_risk_paths"] == ["src/app.py"]
    assert delta["content_changed"] is False
    assert delta["content_changed_paths"] == []


def test_compute_risk_delta_ignores_trivial_whitespace_only_changes(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file_path = src_dir / "app.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")
    previous = build_risk_snapshot(["src/app.py"], workspace=tmp_path)

    file_path.write_text("print('ok')   \n\n", encoding="utf-8")
    current = build_risk_snapshot(["src/app.py"], workspace=tmp_path)
    delta = compute_risk_delta(previous, current)

    assert delta["content_changed"] is False
    assert delta["content_change_hints"] == {}


def test_compute_risk_delta_falls_back_to_generic_hint_for_ambiguous_text_change(tmp_path):
    file_path = tmp_path / "rules.yaml"
    file_path.write_text("foo: one\nbar: two\n", encoding="utf-8")
    previous = build_risk_snapshot(["rules.yaml"], workspace=tmp_path)

    file_path.write_text("baz: one\nqux: two\n", encoding="utf-8")
    current = build_risk_snapshot(["rules.yaml"], workspace=tmp_path)
    delta = compute_risk_delta(previous, current)

    assert delta["content_changed"] is True
    assert delta["content_change_hint_types"]["rules.yaml"] == "text_modified"
    assert delta["top_content_change_hint"] == "rules.yaml: text modified"


def test_build_action_signal_uses_conservative_risk_rules():
    review_signal = build_action_signal(
        {
            "baseline_status": "fresh",
            "high_risk_delta": 1,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": ["config/prod.yaml"],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 1, "primary_risky_path": "config/prod.yaml"},
    )
    monitor_signal = build_action_signal(
        {
            "baseline_status": "fresh",
            "high_risk_delta": 0,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": [],
            "resolved_high_risks": [],
            "persistent_high_risks": ["src/core/engine.py"],
        },
        {"high_risk_count": 1, "primary_risky_path": "src/core/engine.py"},
    )
    safe_signal = build_action_signal(
        {
            "baseline_status": "fresh",
            "high_risk_delta": -1,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": [],
            "resolved_high_risks": ["src/core/engine.py"],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 0, "primary_risky_path": None},
    )

    assert review_signal == {
        "action": "REVIEW_REQUIRED",
        "reason": "new HIGH risk detected",
        "primary_path": "config/prod.yaml",
        "certainty": "HIGH",
        "baseline_reason": "fresh_snapshot",
    }
    assert monitor_signal == {
        "action": "MONITOR",
        "reason": "HIGH risk persists",
        "primary_path": "src/core/engine.py",
        "certainty": "MEDIUM",
        "baseline_reason": "fresh_snapshot",
    }
    assert safe_signal == {
        "action": "SAFE",
        "reason": "no HIGH risk detected",
        "primary_path": None,
        "certainty": "HIGH",
        "baseline_reason": "fresh_snapshot",
    }


def test_build_action_signal_handles_medium_surge_and_baseline_uncertainty():
    recommended_signal = build_action_signal(
        {
            "baseline_status": "fresh",
            "high_risk_delta": 0,
            "medium_risk_delta": 5,
            "low_risk_delta": 0,
            "new_high_risk_paths": [],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 0, "primary_risky_path": "config/feature_flags.yaml"},
    )
    stale_signal = build_action_signal(
        {
            "baseline_status": "stale",
            "high_risk_delta": 0,
            "medium_risk_delta": 5,
            "low_risk_delta": 0,
            "new_high_risk_paths": [],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 0, "primary_risky_path": "config/feature_flags.yaml"},
    )
    missing_signal = build_action_signal(
        {
            "baseline_status": "missing",
            "high_risk_delta": 0,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": [],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 0, "primary_risky_path": "config/feature_flags.yaml"},
    )

    assert recommended_signal == {
        "action": "REVIEW_RECOMMENDED",
        "reason": "medium risk increased sharply",
        "primary_path": "config/feature_flags.yaml",
        "certainty": "MEDIUM",
        "baseline_reason": "fresh_snapshot",
    }
    assert stale_signal == {
        "action": "REVIEW_RECOMMENDED",
        "reason": "baseline stale; medium risk increased sharply",
        "primary_path": "config/feature_flags.yaml",
        "certainty": "LOW",
        "baseline_reason": "stale_snapshot",
    }
    assert missing_signal == {
        "action": "MONITOR",
        "reason": "baseline missing; monitor current risk state",
        "primary_path": "config/feature_flags.yaml",
        "certainty": "LOW",
        "baseline_reason": "missing_snapshot",
    }


def test_build_action_signal_uses_three_level_certainty_and_missing_high_is_review_required():
    stale_review = build_action_signal(
        {
            "baseline_status": "stale",
            "baseline_reason": "stale_snapshot",
            "high_risk_delta": 1,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": ["config/prod.yaml"],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 1, "primary_risky_path": "config/prod.yaml"},
    )
    missing_high = build_action_signal(
        {
            "baseline_status": "missing",
            "baseline_reason": "initial_scan",
            "high_risk_delta": 1,
            "medium_risk_delta": 0,
            "low_risk_delta": 0,
            "new_high_risk_paths": ["config/prod.yaml"],
            "resolved_high_risks": [],
            "persistent_high_risks": [],
        },
        {"high_risk_count": 1, "primary_risky_path": "config/prod.yaml"},
    )

    assert stale_review["certainty"] == "MEDIUM"
    assert stale_review["baseline_reason"] == "stale_snapshot"
    assert missing_high == {
        "action": "REVIEW_REQUIRED",
        "reason": "baseline missing; HIGH risk present in current snapshot",
        "primary_path": "config/prod.yaml",
        "certainty": "LOW",
        "baseline_reason": "initial_scan",
    }


def test_score_risk_decision_signal_weights_reopen_suggestion_and_blocker_conservatively():
    strong = score_risk_decision_signal({
        "action_signal": {
            "action": "REVIEW_REQUIRED",
            "certainty": "HIGH",
        },
        "baseline_status": "fresh",
        "baseline_reason": "fresh_snapshot",
        "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
    })
    weak = score_risk_decision_signal({
        "action_signal": {
            "action": "MONITOR",
            "certainty": "LOW",
        },
        "baseline_status": "missing",
        "baseline_reason": "initial_scan",
        "blocker_candidate": "risk:MONITOR(config/prod.yaml)",
    })

    assert strong["reopen_score"] > weak["reopen_score"]
    assert strong["suggestion_priority"] > weak["suggestion_priority"]
    assert strong["blocker_promoted"] is True
    assert weak["blocker_promoted"] is False


def test_rank_reopen_candidates_prefers_new_high_over_persistent_high():
    skills = [
        {"name": "workspace_reporter", "behavior_class": "observe"},
        {"name": "file_classifier", "behavior_class": "report"},
        {"name": "code_reviewer", "behavior_class": "review"},
    ]

    new_high_ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": ["config/prod.yaml"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 5},
        },
        priority_order=["workspace_reporter", "file_classifier", "code_reviewer"],
    )
    persistent_ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "MONITOR", "certainty": "HIGH", "primary_path": "src/core/engine.py"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": [], "persistent_high_risks": ["src/core/engine.py"]},
            "decision_weighting": {"reopen_score": 2},
        },
        priority_order=["workspace_reporter", "file_classifier", "code_reviewer"],
    )

    assert new_high_ranked[0]["skill"] == "code_reviewer"
    assert new_high_ranked[0]["reopen_priority"] > persistent_ranked[0]["reopen_priority"]


def test_rank_reopen_candidates_prefers_high_certainty_and_fresh_baseline():
    skills = [
        {"name": "workspace_reporter", "behavior_class": "observe"},
        {"name": "code_reviewer", "behavior_class": "review"},
    ]

    high_fresh = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "scripts/run.ps1"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": ["scripts/run.ps1"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 5},
        },
        priority_order=["workspace_reporter", "code_reviewer"],
    )
    low_stale = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "LOW", "primary_path": "scripts/run.ps1"},
            "baseline_status": "stale",
            "baseline_reason": "stale_snapshot",
            "risk_delta": {"new_high_risk_paths": ["scripts/run.ps1"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 1},
        },
        priority_order=["workspace_reporter", "code_reviewer"],
    )

    assert high_fresh[0]["reopen_priority"] > low_stale[0]["reopen_priority"]
    assert "baseline=fresh" in high_fresh[0]["reopen_rank_reason"]


def test_metadata_free_skill_ranking_keeps_existing_ordering_bias():
    skills = [
        {"name": "workspace_reporter", "behavior_class": "observe"},
        {"name": "code_reviewer", "behavior_class": "review"},
    ]

    ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": ["config/prod.yaml"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 5},
        },
        priority_order=["workspace_reporter", "code_reviewer"],
    )

    assert ranked[0]["skill"] == "code_reviewer"


def test_runtime_sensitive_skill_gets_bonus_for_runtime_risk():
    skills = [
        {
            "name": "runtime_guard",
            "behavior_class": "review",
            "risk_profile": "runtime_sensitive",
            "handles_runtime_changes": True,
            "handles_config_changes": False,
            "prefers_reopen_on_high_risk": True,
            "review_cost": "high",
            "suggestion_bias": "action",
        },
        {
            "name": "plain_reporter",
            "behavior_class": "report",
            "risk_profile": "monitoring",
        },
    ]

    ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "src/runtime/engine.py"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": ["src/runtime/engine.py"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 5},
        },
    )

    assert ranked[0]["skill"] == "runtime_guard"
    assert "runtime_sensitive_bonus" in ranked[0]["reopen_rank_reason"]
    assert ranked[0]["metadata_weight_applied"] is True


def test_monitoring_skill_is_not_over_promoted_on_low_certainty_high_risk():
    skills = [
        {
            "name": "monitoring_reporter",
            "behavior_class": "report",
            "risk_profile": "monitoring",
            "review_cost": "low",
        },
        {
            "name": "runtime_guard",
            "behavior_class": "review",
            "risk_profile": "runtime_sensitive",
            "handles_runtime_changes": True,
            "review_cost": "high",
        },
    ]

    ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "LOW", "primary_path": "src/core/engine.py"},
            "baseline_status": "missing",
            "baseline_reason": "initial_scan",
            "risk_delta": {"new_high_risk_paths": ["src/core/engine.py"], "persistent_high_risks": []},
            "decision_weighting": {"reopen_score": 1},
        },
    )

    assert ranked[0]["skill"] == "runtime_guard"
    assert any("monitoring_penalty" in item["reopen_rank_reason"] for item in ranked if item["skill"] == "monitoring_reporter")


def test_prefers_reopen_on_high_risk_metadata_affects_ordering():
    skills = [
        {
            "name": "action_reporter",
            "behavior_class": "report",
            "prefers_reopen_on_high_risk": True,
            "suggestion_bias": "action",
        },
        {
            "name": "neutral_reporter",
            "behavior_class": "report",
        },
    ]

    ranked = rank_reopen_candidates(
        skills,
        {
            "action_signal": {"action": "ALERT", "certainty": "MEDIUM", "primary_path": "config/app.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "risk_delta": {"new_high_risk_paths": [], "persistent_high_risks": ["config/app.yaml"]},
            "decision_weighting": {"reopen_score": 3},
        },
    )

    assert ranked[0]["skill"] == "action_reporter"
    assert "prefers_reopen_on_high_risk" in ranked[0]["reopen_rank_reason"]


def test_build_risk_suggestions_prioritizes_and_softens_low_certainty_language():
    strong = build_risk_suggestions({
        "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
        "baseline_status": "fresh",
        "baseline_reason": "fresh_snapshot",
        "decision_weighting": {"suggestion_priority": 90, "suggestion_severity": "critical"},
    })
    weak = build_risk_suggestions({
        "action_signal": {"action": "ALERT", "certainty": "LOW", "primary_path": "src/core/engine.py"},
        "baseline_status": "missing",
        "baseline_reason": "initial_scan",
        "decision_weighting": {"suggestion_priority": 20, "suggestion_severity": "high"},
    })

    assert strong[0]["priority"] > weak[0]["priority"]
    assert strong[0]["severity"] == "critical"
    assert "review immediately" in strong[0]["text"]
    assert "monitor and verify" in weak[0]["text"]
    assert "baseline incomplete" in weak[0]["text"]


def test_build_risk_suggestions_uses_changed_path_wording_for_content_changes():
    suggestions = build_risk_suggestions({
        "action_signal": {"action": "MONITOR", "certainty": "MEDIUM", "primary_path": "config/prod.yaml"},
        "baseline_status": "fresh",
        "baseline_reason": "fresh_snapshot",
        "risk_delta": {
            "new_high_risk_paths": [],
            "content_changed_paths": ["config/prod.yaml"],
            "persistent_high_risks": ["config/prod.yaml"],
        },
        "decision_weighting": {"suggestion_priority": 35, "suggestion_severity": "low"},
    })

    assert "verify recent changes" in suggestions[0]["text"]
    assert "review immediately" not in suggestions[0]["text"]


def test_build_risk_suggestions_keeps_monitor_wording_for_persistent_same_paths():
    suggestions = build_risk_suggestions({
        "action_signal": {"action": "MONITOR", "certainty": "MEDIUM", "primary_path": "src/core/engine.py"},
        "baseline_status": "fresh",
        "baseline_reason": "fresh_snapshot",
        "risk_delta": {
            "new_high_risk_paths": [],
            "content_changed_paths": [],
            "persistent_high_risks": ["src/core/engine.py"],
        },
        "decision_weighting": {"suggestion_priority": 35, "suggestion_severity": "low"},
    })

    assert "monitor and verify" in suggestions[0]["text"]


def test_suggestion_bias_changes_wording_and_priority():
    action_suggestion = build_risk_suggestions(
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "MEDIUM", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {"suggestion_priority": 60, "suggestion_severity": "critical"},
        },
        ranked_candidates=[{
            "skill": "runtime_guard",
            "suggestion_bias": "action",
            "skill_risk_profile": "runtime_sensitive",
            "metadata_weight_applied": True,
        }],
    )
    explain_suggestion = build_risk_suggestions(
        {
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "MEDIUM", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {"suggestion_priority": 60, "suggestion_severity": "critical"},
        },
        ranked_candidates=[{
            "skill": "workspace_reporter",
            "suggestion_bias": "explain",
            "skill_risk_profile": "monitoring",
            "metadata_weight_applied": True,
        }],
    )

    assert action_suggestion[0]["priority"] > explain_suggestion[0]["priority"]
    assert "review recommended" in action_suggestion[0]["text"]
    assert "review and explain impact" in explain_suggestion[0]["text"]


def test_build_operator_guidance_changes_by_risk_action_and_path():
    config_guidance = build_operator_guidance({
        "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
        "risk_delta": {"medium_risk_delta": 0},
    })
    runtime_guidance = build_operator_guidance({
        "action_signal": {"action": "ALERT", "certainty": "MEDIUM", "primary_path": "src/runtime/engine.py"},
        "risk_delta": {"medium_risk_delta": 0},
    })
    surge_guidance = build_operator_guidance({
        "action_signal": {"action": "REVIEW_RECOMMENDED", "certainty": "MEDIUM", "primary_path": "config/feature_flags.yaml"},
        "risk_delta": {"medium_risk_delta": 7},
    })

    assert config_guidance["recommended_next_step"] == "review config change before reopen"
    assert config_guidance["priority_bucket"] == "critical"
    assert runtime_guidance["recommended_review_scope"] == "runtime execution path"
    assert surge_guidance["recommended_next_step"] == "inspect medium-risk file cluster"


def test_build_operator_guidance_refines_wording_for_content_changed_and_persistent_paths():
    changed_guidance = build_operator_guidance({
        "action_signal": {"action": "MONITOR", "certainty": "MEDIUM", "primary_path": "config/prod.yaml"},
        "risk_delta": {
            "content_changed_paths": ["config/prod.yaml"],
            "persistent_high_risks": ["config/prod.yaml"],
        },
    })
    persistent_guidance = build_operator_guidance({
        "action_signal": {"action": "MONITOR", "certainty": "MEDIUM", "primary_path": "src/core/engine.py"},
        "risk_delta": {
            "content_changed_paths": [],
            "persistent_high_risks": ["src/core/engine.py"],
        },
    })

    assert changed_guidance["recommended_next_step"] == "review changed config risk paths before reopening broader analysis"
    assert changed_guidance["recommended_review_scope"] == "changed config risk paths"
    assert persistent_guidance["recommended_next_step"] == "monitor persistent risk paths before escalating"
    assert persistent_guidance["recommended_review_scope"] == "persistent risky files"


def test_build_summary_wording_varies_by_certainty_and_risk_mode():
    strong = build_summary_wording(
        primary_path="config/prod.yaml",
        certainty="HIGH",
        baseline_reason="fresh_snapshot",
        cluster_label="Config Risk Cluster",
        cluster_severity="HIGH",
        guidance_mode="new_high",
    )
    medium = build_summary_wording(
        primary_path="config/prod.yaml",
        certainty="MEDIUM",
        baseline_reason="fresh_snapshot",
        cluster_label="Config Risk Cluster",
        cluster_severity="HIGH",
        guidance_mode="content_changed",
    )
    low = build_summary_wording(
        primary_path="src/core/engine.py",
        certainty="LOW",
        baseline_reason="fresh_snapshot",
        cluster_label="Core Source Risk Cluster",
        cluster_severity="HIGH",
        guidance_mode="persistent_same",
    )

    assert strong["summary_headline"].startswith("review immediately: config/prod.yaml")
    assert "High-risk Config Risk Cluster" in strong["summary_headline"]
    assert medium["summary_headline"].startswith("verify recent changes: config/prod.yaml")
    assert low["summary_headline"].startswith("confirm persistent risk if expected: src/core/engine.py")


def test_build_operational_risk_signal_and_operational_signal_expose_risk_fields(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "risk_snapshot.json").write_text(json.dumps({
        "created_at": "2026-03-20T00:00:00Z",
        "source": "inspect",
        "entries": [{"path": "src/core/engine.py", "severity": "HIGH"}],
    }, ensure_ascii=False), encoding="utf-8")

    risk_signal = build_operational_risk_signal(
        tmp_path,
        ["src/core/engine.py", "config/prod.yaml"],
        now=_parse_timestamp_for_test("2026-03-22T12:00:00Z"),
    )
    operational_signal = build_operational_signal(
        annotate_changes(["config/prod.yaml"]),
        risk_signal=risk_signal,
        skills=[
            {
                "name": "runtime_guard",
                "behavior_class": "review",
                "risk_profile": "runtime_sensitive",
                "handles_config_changes": True,
                "handles_runtime_changes": True,
                "prefers_reopen_on_high_risk": True,
                "suggestion_bias": "action",
                "review_cost": "high",
            }
        ],
    )

    assert risk_signal["baseline_status"] == "stale"
    assert risk_signal["baseline_reason"] == "stale_snapshot"
    assert risk_signal["action_signal"]["action"] == "REVIEW_REQUIRED"
    assert risk_signal["action_signal"]["certainty"] == "MEDIUM"
    assert risk_signal["blocker_candidate"] == "risk:REVIEW_REQUIRED(config/prod.yaml)"
    assert operational_signal["risk_action"] == "REVIEW_REQUIRED"
    assert operational_signal["risk_reason"] == "baseline stale; new HIGH risk detected"
    assert operational_signal["baseline_status"] == "stale"
    assert operational_signal["baseline_reason"] == "stale_snapshot"
    assert operational_signal["risk_primary_path"] == "config/prod.yaml"
    assert operational_signal["risk_certainty"] == "MEDIUM"
    assert operational_signal["risk_suggestion_priority"] >= 60
    assert operational_signal["risk_suggestion_severity"] == "critical"
    assert operational_signal["risk_blocker_candidate"] == "risk:REVIEW_REQUIRED(config/prod.yaml)"
    assert operational_signal["risk_blocker_promoted"] is False
    assert operational_signal["top_suggestion"]["source"] == "risk_signal"
    assert operational_signal["top_suggestion"]["severity"] == "critical"
    assert operational_signal["reopen_candidate"] == "runtime_guard"
    assert operational_signal["skill_risk_profile"] == "runtime_sensitive"
    assert operational_signal["metadata_weight_applied"] is True
    assert operational_signal["recommended_next_step"] == "review config change before reopen"
    assert operational_signal["recommended_review_scope"] == "configuration boundary"
    assert operational_signal["priority_bucket"] == "high"
    assert operational_signal["blocker_candidate"] == "risk:REVIEW_REQUIRED(config/prod.yaml)"


def test_suppresses_repeated_same_high_risk_warning():
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    recent_signatures = build_warning_signatures(changes, summary)

    assert should_suppress_warning(changes, summary, recent_signatures=recent_signatures) is True


def test_does_not_suppress_different_file_or_risk():
    base_changes = annotate_changes(["src/app.py"])
    base_summary = build_state_summary(base_changes)
    recent_signatures = build_warning_signatures(base_changes, base_summary)

    other_file_changes = annotate_changes(["src/other.py"])
    low_risk_changes = annotate_changes(["docs/guide.md"])

    assert should_suppress_warning(other_file_changes, build_state_summary(other_file_changes), recent_signatures=recent_signatures) is False
    assert should_suppress_warning(low_risk_changes, build_state_summary(low_risk_changes), recent_signatures=recent_signatures) is False


def test_build_operational_signal_exposes_approval_state():
    changes = annotate_changes(["src/app.py"])

    signal = build_operational_signal(changes)

    assert signal["summary"]["recommended_action"] == "review_file"
    assert signal["approval"] == {"required": True, "status": "review_needed"}
    assert signal["suppressed"] is False


def test_collects_repeated_medium_risk_self_artifact_candidates():
    candidates = collect_self_artifact_candidates([
        "analysis_snapshot.data",
        "analysis_snapshot.data",
        "docs/guide.md",
        "docs/guide.md",
    ])

    assert candidates == [{
        "path": "analysis_snapshot.data",
        "normalized_path": "analysis_snapshot.data",
        "occurrences": 2,
        "status": "review_needed",
        "reason": "repeated_unclassified_change",
    }]


def test_pending_approval_creation_sets_pending_status(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)

    result = create_pending_approvals(changes, summary, approval_file)
    entries = load_pending_approvals(approval_file)

    assert len(result["created"]) == 1
    assert len(entries) == 1
    assert entries[0]["status"] == "pending"
    assert entries[0]["risk"] == "HIGH"
    assert entries[0]["recommended_action"] == "review_file"


def test_pending_approval_duplicate_signature_is_suppressed(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)

    first = create_pending_approvals(changes, summary, approval_file)
    second = create_pending_approvals(changes, summary, approval_file)
    entries = load_pending_approvals(approval_file)

    assert len(first["created"]) == 1
    assert len(second["created"]) == 0
    assert len(entries) == 1


def test_pending_approval_status_can_be_updated(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    created = create_pending_approvals(changes, summary, approval_file)["created"][0]

    approved = update_pending_approval_status(approval_file, created["signature"], "approved")
    assert approved is not None
    assert approved["status"] == "approved"

    rejected = update_pending_approval_status(approval_file, created["signature"], "rejected")
    assert rejected is not None
    assert rejected["status"] == "rejected"


def test_operational_signal_reflects_existing_approval_status(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    created = create_pending_approvals(changes, summary, approval_file)
    signature = created["created"][0]["signature"]
    update_pending_approval_status(approval_file, signature, "approved")

    signal = build_operational_signal(
        changes,
        approval_entries=load_pending_approvals(approval_file),
    )

    assert signal["approval"]["status"] == "approved"


def test_pending_operational_approval_keeps_observe_only_mode(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    create_pending_approvals(changes, summary, approval_file)

    signal = build_operational_signal(changes, approval_entries=load_pending_approvals(approval_file))
    gate = resolve_operational_gate(signal)

    assert signal["approval"]["status"] == "pending"
    assert gate["mode"] == "observe_only"


def test_approved_operational_approval_enables_review_allowed_mode(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    created = create_pending_approvals(changes, summary, approval_file)["created"][0]
    update_pending_approval_status(approval_file, created["signature"], "approved")

    signal = build_operational_signal(changes, approval_entries=load_pending_approvals(approval_file))
    gate = resolve_operational_gate(signal)

    assert signal["approval"]["status"] == "approved"
    assert gate["mode"] == "review_allowed"


def test_rejected_operational_approval_keeps_blocked_mode(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    created = create_pending_approvals(changes, summary, approval_file)["created"][0]
    update_pending_approval_status(approval_file, created["signature"], "rejected")

    signal = build_operational_signal(changes, approval_entries=load_pending_approvals(approval_file))
    gate = resolve_operational_gate(signal)

    assert signal["approval"]["status"] == "rejected"
    assert gate["mode"] == "blocked"


def test_operational_approval_entries_store_type_and_source(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)

    created = create_pending_approvals(changes, summary, approval_file)["created"][0]

    assert created["type"] == "operational_risk"
    assert created["source"] == "operational_signal"


def test_operational_gate_view_exposes_gate_and_approval_state(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    create_pending_approvals(changes, summary, approval_file)

    signal = build_operational_signal(
        changes,
        approval_entries=load_pending_approvals(approval_file),
    )
    gate = resolve_operational_gate(signal)
    view = build_operational_gate_view(signal, gate)

    assert view == {
        "gate_mode": "observe_only",
        "approval_status": "pending",
        "target": "src/app.py",
        "signature": "src/app.py|HIGH|review_file",
        "recommended_action": "review_file",
        "risk": "HIGH",
    }


def test_behavior_class_fallback_skills_are_reported_and_warned(tmp_path, caplog):
    caplog.set_level("WARNING")
    skills_dir = tmp_path / "skills"
    explicit_dir = skills_dir / "explicit_skill"
    fallback_dir = skills_dir / "fallback_skill"
    explicit_dir.mkdir(parents=True)
    fallback_dir.mkdir(parents=True)
    (explicit_dir / "SKILL.md").write_text(
        "# explicit\n## name\nworkspace_reporter\n## behavior_class\nobserve\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    (fallback_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    skills = load_skills(str(skills_dir))
    diagnostics = get_behavior_class_diagnostics(skills)

    assert list_behavior_class_fallback_skills(skills) == ["custom_audit"]
    assert diagnostics["explicit_skills"] == ["workspace_reporter"]
    assert diagnostics["fallback_skills"] == ["custom_audit"]
    assert diagnostics["explicit_transition_needed"] == ["custom_audit"]
    assert diagnostics["all_explicit"] is False
    assert "behavior_class fallback 사용 중: custom_audit" in caplog.text


def test_strict_behavior_class_rejects_fallback_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    fallback_dir = skills_dir / "fallback_skill"
    fallback_dir.mkdir(parents=True)
    (fallback_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="strict behavior_class preflight failed"):
        load_skills(str(skills_dir), strict_behavior_class=True)


def test_operational_gate_view_from_approvals_exposes_latest_state(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    created = create_pending_approvals(changes, summary, approval_file)["created"][0]
    update_pending_approval_status(approval_file, created["signature"], "approved")

    view = build_operational_gate_view_from_approvals(load_pending_approvals(approval_file))

    assert view == {
        "gate_mode": "review_allowed",
        "approval_status": "approved",
        "target": "src/app.py",
        "signature": "src/app.py|HIGH|review_file",
        "recommended_action": "review_file",
        "risk": "HIGH",
    }


def test_operational_approval_summary_counts_multiple_statuses(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"

    first = create_pending_approvals(
        annotate_changes(["src/app.py"]),
        build_state_summary(annotate_changes(["src/app.py"])),
        approval_file,
    )["created"][0]
    second = create_pending_approvals(
        annotate_changes(["src/other.py"]),
        build_state_summary(annotate_changes(["src/other.py"])),
        approval_file,
    )["created"][0]
    third = create_pending_approvals(
        annotate_changes(["config/settings.json"]),
        build_state_summary(annotate_changes(["config/settings.json"])),
        approval_file,
    )["created"][0]

    update_pending_approval_status(approval_file, second["signature"], "approved")
    update_pending_approval_status(approval_file, third["signature"], "rejected")
    summary = summarize_operational_approvals(load_pending_approvals(approval_file))

    assert summary["total_operational_approvals_count"] == 3
    assert summary["pending_operational_approvals_count"] == 1
    assert summary["approved_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["recent_targets"] == ["config/settings.json", "src/other.py", "src/app.py"]


def test_strict_behavior_readiness_reports_ready_when_all_explicit():
    diagnostics = {
        "explicit_skills": ["workspace_reporter", "code_reviewer"],
        "fallback_skills": [],
        "missing_behavior_class": [],
        "explicit_transition_needed": [],
        "all_explicit": True,
        "inconsistent_behavior_class_skills": [],
        "consistency_warnings": [],
    }

    readiness = build_strict_behavior_readiness(diagnostics)

    assert readiness == {
        "strict_ready": True,
        "fallback_skill_count": 0,
        "explicit_transition_needed_count": 0,
        "blockers": [],
        "mode": "missing_only",
    }


def test_strict_behavior_readiness_reports_blockers_for_fallback_skills():
    diagnostics = {
        "explicit_skills": ["workspace_reporter"],
        "fallback_skills": ["custom_audit", "file_classifier"],
        "missing_behavior_class": ["custom_audit", "file_classifier"],
        "explicit_transition_needed": ["custom_audit", "file_classifier"],
        "all_explicit": False,
        "inconsistent_behavior_class_skills": ["workspace_reporter"],
        "consistency_warnings": ["workspace_reporter: reporter 계열로 보이나 behavior_class=observe"],
    }

    readiness = build_strict_behavior_readiness(diagnostics)

    assert readiness["strict_ready"] is False
    assert readiness["fallback_skill_count"] == 2
    assert readiness["explicit_transition_needed_count"] == 2
    assert readiness["blockers"] == ["custom_audit", "file_classifier"]
    assert readiness["mode"] == "missing_only"


def test_behavior_class_consistency_diagnostics_detects_obvious_mismatch():
    diagnostics = get_behavior_class_consistency_diagnostics([
        {
            "name": "code_reviewer",
            "description": "코드 리뷰를 수행한다",
            "when_to_use": "위험 파일 검토가 필요할 때",
            "behavior_class": "observe",
        },
        {
            "name": "workspace_reporter",
            "description": "워크스페이스 보고서를 생성한다",
            "when_to_use": "상태 보고가 필요할 때",
            "behavior_class": "report",
        },
    ])

    assert diagnostics["inconsistent_behavior_class_skills"] == ["code_reviewer"]
    assert diagnostics["consistency_warnings"] == [
        "code_reviewer: reviewer 계열로 보이나 behavior_class=observe"
    ]


def test_strict_behavior_readiness_can_include_consistency_blockers():
    diagnostics = {
        "explicit_skills": ["workspace_reporter"],
        "fallback_skills": [],
        "missing_behavior_class": [],
        "explicit_transition_needed": [],
        "all_explicit": True,
        "inconsistent_behavior_class_skills": ["code_reviewer"],
        "consistency_warnings": ["code_reviewer: reviewer 계열로 보이나 behavior_class=observe"],
    }

    readiness = build_strict_behavior_readiness(diagnostics, mode="include_consistency")

    assert readiness["strict_ready"] is False
    assert readiness["fallback_skill_count"] == 0
    assert readiness["explicit_transition_needed_count"] == 1
    assert readiness["blockers"] == ["code_reviewer"]
    assert readiness["mode"] == "include_consistency"


def test_explicit_transition_report_classifies_fallback_inconsistency_and_blockers():
    skills = [
        {
            "name": "custom_reporter",
            "description": "상태 보고서를 생성한다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "observe",
            "behavior_class_source": "explicit",
        },
        {
            "name": "custom_audit",
            "description": "워크스페이스 점검",
            "when_to_use": "점검이 필요할 때",
            "behavior_class": "report",
            "behavior_class_source": "fallback",
        },
    ]

    report = build_explicit_transition_report(skills)

    assert report["fallback_skills"] == ["custom_audit"]
    assert report["inconsistent_behavior_class_skills"] == ["custom_reporter"]
    assert report["explicit_transition_needed"] == ["custom_audit"]
    assert report["strict_blockers"] == ["custom_audit", "custom_reporter"]
    assert report["suggested_behavior_class"] == {
        "custom_audit": "report",
        "custom_reporter": "report",
    }


def test_explicit_transition_report_detail_exposes_full_skill_metadata():
    skills = [
        {
            "name": "custom_reporter",
            "description": "상태 보고서를 생성한다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "observe",
            "behavior_class_source": "explicit",
        },
        {
            "name": "custom_audit",
            "description": "워크스페이스 점검",
            "when_to_use": "점검이 필요할 때",
            "behavior_class": "report",
            "behavior_class_source": "fallback",
        },
    ]

    detail = build_explicit_transition_report_detail(skills)

    assert detail["strict_blockers"] == ["custom_audit", "custom_reporter"]
    assert detail["skills"] == [
        {
            "name": "custom_reporter",
            "behavior_class": "observe",
            "behavior_class_source": "explicit",
            "suggested_behavior_class": "report",
            "strict_blocker": True,
            "strict_blocker_reasons": ["inconsistent_behavior_class"],
        },
        {
            "name": "custom_audit",
            "behavior_class": "report",
            "behavior_class_source": "fallback",
            "suggested_behavior_class": "report",
            "strict_blocker": True,
            "strict_blocker_reasons": ["missing_behavior_class"],
        },
    ]


def test_suggested_behavior_class_handles_obvious_cases():
    assert suggest_behavior_class({
        "name": "code_reviewer",
        "description": "코드 리뷰를 수행한다",
        "when_to_use": "위험 파일 검토",
    }) == "review"
    assert suggest_behavior_class({
        "name": "workspace_reporter",
        "description": "상태 보고서를 생성한다",
        "when_to_use": "보고가 필요할 때",
    }) == "report"
    assert suggest_behavior_class({
        "name": "command_runner",
        "description": "명령을 실행한다",
        "when_to_use": "실행 검증",
    }) == "execute"


def test_strict_preflight_reports_fallback_and_inconsistency_separately():
    skills = [
        {
            "name": "custom_reporter",
            "description": "상태 보고서를 생성한다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "observe",
            "behavior_class_source": "explicit",
        },
        {
            "name": "custom_audit",
            "description": "점검 보고서를 만든다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "report",
            "behavior_class_source": "fallback",
        },
    ]

    preflight = build_strict_behavior_preflight(skills)

    assert preflight["ready"] is False
    assert preflight["fallback_blockers"] == ["custom_audit"]
    assert preflight["consistency_blockers"] == ["custom_reporter"]
    assert "fallback=['custom_audit']" in preflight["message"]
    assert "inconsistent=['custom_reporter']" in preflight["message"]


def test_strict_preflight_logs_operational_summary_before_failure(tmp_path, caplog):
    caplog.set_level("ERROR")
    skills_dir = tmp_path / "skills"
    fallback_dir = skills_dir / "fallback_skill"
    fallback_dir.mkdir(parents=True)
    (fallback_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="strict behavior_class preflight failed"):
        load_skills(str(skills_dir), strict_behavior_class=True)

    assert "strict preflight: fallback_blockers=1 consistency_blockers=0 primary_blocker=custom_audit risk_blocker_score=0" in caplog.text


def test_strict_preflight_summary_exposes_counts_and_primary_blocker():
    skills = [
        {
            "name": "custom_reporter",
            "description": "상태 보고서를 생성한다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "observe",
            "behavior_class_source": "explicit",
        },
        {
            "name": "custom_audit",
            "description": "점검 보고서를 만든다",
            "when_to_use": "보고가 필요할 때",
            "behavior_class": "report",
            "behavior_class_source": "fallback",
        },
    ]

    summary = build_strict_behavior_preflight_summary(skills)

    assert summary["ready"] is False
    assert summary["fallback_blocker_count"] == 1
    assert summary["consistency_blocker_count"] == 1
    assert summary["primary_blocker"] == "custom_audit"
    assert summary["risk_blocker_candidate"] is None
    assert summary["risk_blocker_promoted"] is False


def test_strict_risk_integration_exposes_candidate_without_over_promoting_low_certainty():
    integration = build_strict_risk_integration({
        "action_signal": {
            "action": "REVIEW_REQUIRED",
            "certainty": "LOW",
        },
        "baseline_status": "missing",
        "baseline_reason": "initial_scan",
        "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
    })

    assert integration["risk_blocker_candidate"] == "risk:REVIEW_REQUIRED(config/prod.yaml)"
    assert integration["risk_blocker_score"] > 0
    assert integration["risk_blocker_promoted"] is False


def test_strict_preflight_summary_can_include_promoted_risk_blocker():
    summary = build_strict_behavior_preflight_summary(
        [],
        risk_signal={
            "action_signal": {
                "action": "REVIEW_REQUIRED",
                "certainty": "HIGH",
            },
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
        },
    )

    assert summary["ready"] is False
    assert summary["primary_blocker"] == "risk:REVIEW_REQUIRED(config/prod.yaml)"
    assert summary["risk_blocker_promoted"] is True


def test_skill_metadata_template_exposes_minimum_fields():
    template = build_skill_metadata_template()

    assert "## name" in template
    assert "## behavior_class" in template
    assert "## description" in template
    assert "## risk_profile" in template
    assert "## handles_config_changes" in template
    assert "## suggestion_bias" in template


def test_write_skill_metadata_template_creates_once_and_does_not_overwrite(tmp_path):
    first = write_skill_metadata_template(tmp_path / "skills" / "custom_reporter")
    second = write_skill_metadata_template(tmp_path / "skills" / "custom_reporter")

    assert first["created"] is True
    assert first["reason"] == "created"
    assert first["suggested_behavior_class"] == "report"
    assert second["created"] is False
    assert second["reason"] == "exists"
    created_file = tmp_path / "skills" / "custom_reporter" / "SKILL.md"
    assert created_file.exists()
    assert "## behavior_class\nreport" in created_file.read_text(encoding="utf-8")
    assert "## risk_profile" in created_file.read_text(encoding="utf-8")


def test_create_pending_approvals_captures_top_suggestion_and_guidance_payload(tmp_path):
    changes = annotate_changes(["config/prod.yaml"])
    summary = build_state_summary(changes)
    operational_signal = build_operational_signal(
        changes,
        risk_signal={
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {
                "suggestion_priority": 90,
                "suggestion_severity": "critical",
                "reopen_score": 5,
                "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
                "blocker_score": 95,
                "blocker_promoted": True,
            },
            "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
        },
        skills=[{
            "name": "runtime_guard",
            "behavior_class": "review",
            "risk_profile": "runtime_sensitive",
            "handles_config_changes": True,
            "prefers_reopen_on_high_risk": True,
            "suggestion_bias": "action",
            "review_cost": "high",
        }],
    )

    created = create_pending_approvals(
        changes,
        summary,
        tmp_path / "pending_approvals.json",
        operational_signal=operational_signal,
    )["created"][0]

    assert created["top_suggestion"] == operational_signal["top_suggestion_text"]
    assert created["suggestion_priority"] == operational_signal["top_suggestion_priority"]
    assert created["suggestion_severity"] == operational_signal["top_suggestion_severity"]
    assert created["suggestion_certainty"] == operational_signal["top_suggestion_certainty"]
    assert created["recommended_next_step"] == operational_signal["recommended_next_step"]
    assert created["recommended_review_scope"] == operational_signal["recommended_review_scope"]
    assert created["priority_bucket"] == operational_signal["priority_bucket"]
    assert created["summary_headline"] == operational_signal["summary_headline"]
    assert created["summary_priority"] == operational_signal["summary_priority"]
    assert created["summary_certainty"] == operational_signal["summary_certainty"]
    assert created["summary_next_step"] == operational_signal["summary_next_step"]
    assert created["summary_review_scope"] == operational_signal["summary_review_scope"]
    assert created["top_risk_cluster_label"] == operational_signal["top_risk_cluster_label"]
    assert created["top_risk_cluster_severity"] == operational_signal["top_risk_cluster_severity"]
    assert created["cluster_recommended_next_step"] == operational_signal["cluster_recommended_next_step"]


def test_create_pending_approvals_creates_runtime_data_proposal(tmp_path):
    changes = annotate_changes(["config/prod.yaml"])
    summary = build_state_summary(changes)
    approval_file = tmp_path / "pending_approvals.json"

    created = create_pending_approvals(changes, summary, approval_file)["created"][0]
    proposal = load_proposal_by_review_id(created["signature"], reference=approval_file)

    assert proposal is not None
    assert proposal["source_review_id"] == created["signature"]
    assert proposal["target_paths"] == ["config/prod.yaml"]
    assert proposal["status"] == "pending"
    assert (tmp_path / "runtime-data" / "proposals" / f"{proposal['proposal_id']}.json").exists()


def test_process_review_decision_records_decision_and_moves_approved_proposal(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "config/prod.yaml|HIGH|review",
        "target": "config/prod.yaml",
        "summary_headline": "review immediately: config/prod.yaml",
        "top_risk_cluster_label": "Config Risk Cluster",
        "top_risk_cluster_severity": "HIGH",
        "top_risk_cluster_has_content_change": True,
        "top_content_change_hint": "config/prod.yaml: values changed",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)

    result = process_review_decision(review_entry["signature"], "approved", reference=approval_file)

    assert created["proposal"]["proposal_id"] == result["proposal"]["proposal_id"]
    assert result["proposal"]["status"] == "approved"
    assert result["decision"]["decision"] == "approved"
    assert Path(result["decision"]["path"]).exists()
    assert result["staged"] is not None
    assert Path(result["staged"]["path"]).exists()


def test_process_review_decision_rejected_does_not_stage_proposal(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "src/core/engine.py|HIGH|review",
        "target": "src/core/engine.py",
        "summary_headline": "review changed risk paths: src/core/engine.py",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)

    result = process_review_decision(review_entry["signature"], "rejected", reference=approval_file)

    assert created["proposal"]["proposal_id"] == result["proposal"]["proposal_id"]
    assert result["proposal"]["status"] == "rejected"
    assert result["decision"]["decision"] == "rejected"
    assert result["staged"] is None
    assert not (tmp_path / "runtime-data" / "staging" / f"{created['proposal']['proposal_id']}.json").exists()


def test_apply_precheck_is_deny_by_default_for_basic_proposal():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_empty",
        "target_paths": [],
        "change_type": "unknown",
        "summary": "none",
        "risk_context": {"severity": "LOW", "content_changed": False},
    })

    assert precheck["apply_possible"] is False
    assert precheck["apply_mode"] == "blocked"


def test_apply_precheck_allows_only_dry_run_for_safe_config_proposal():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review recommended: config/prod.yaml",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert precheck["apply_possible"] is False
    assert precheck["apply_mode"] == "dry_run_only"
    assert "workspace write not enabled" in precheck["apply_blockers"]


def test_apply_precheck_blocks_code_change():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_test",
        "target_paths": ["src/core/engine.py"],
        "change_type": "code_change",
        "summary": "review changed risk paths: src/core/engine.py",
        "risk_context": {"severity": "HIGH", "content_changed": True},
    })

    assert precheck["apply_mode"] == "blocked"
    assert "code_change requires manual operator validation" in precheck["apply_blockers"]
    assert precheck["blocked_target_paths"] == ["src/core/engine.py"]


def test_apply_precheck_blocks_unknown_change_type():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_test",
        "target_paths": ["misc/custom.data"],
        "change_type": "unknown",
        "summary": "monitor and verify",
        "risk_context": {"severity": "LOW", "content_changed": False},
    })

    assert precheck["apply_mode"] == "blocked"
    assert "unknown change_type remains blocked" in precheck["apply_blockers"]


def test_apply_precheck_splits_allowed_and_blocked_paths():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml", "src/core/engine.py", "docs/guide.md"],
        "change_type": "config_change",
        "summary": "review recommended",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert precheck["allowed_target_paths"] == ["config/prod.yaml", "docs/guide.md"]
    assert precheck["blocked_target_paths"] == ["src/core/engine.py"]
    assert "target path outside safe apply allowlist" in precheck["apply_blockers"]


def test_apply_precheck_reflects_baseline_warning_from_summary():
    precheck = build_apply_precheck({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review recommended | verify against stale baseline",
        "risk_context": {"severity": "HIGH", "content_changed": True},
    })

    assert "stale baseline verification recommended" in precheck["apply_warnings"]
    assert "baseline verification required before apply consideration" in precheck["apply_blockers"]


def test_move_to_staging_writes_precheck_payload(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "config/prod.yaml|HIGH|review",
        "target": "config/prod.yaml",
        "summary_headline": "review immediately: config/prod.yaml",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)
    process_review_decision(review_entry["signature"], "approved", reference=approval_file)

    precheck = load_staging_precheck(created["proposal"]["proposal_id"], reference=approval_file)
    assert precheck is not None
    assert precheck["proposal_id"] == created["proposal"]["proposal_id"]
    assert precheck["apply_mode"] == "dry_run_only"
    assert "review proposal content" in precheck["operator_steps"]


def test_build_apply_plan_does_not_modify_workspace_files(tmp_path):
    target = tmp_path / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    plan = build_apply_plan({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert plan["apply_mode"] == "dry_run_only"
    assert target.read_text(encoding="utf-8") == before


def test_blocked_apply_plan_has_no_actions():
    plan = build_apply_plan({
        "proposal_id": "proposal_test",
        "target_paths": ["src/core/engine.py"],
        "change_type": "code_change",
        "summary": "review changed risk paths",
        "status": "approved",
        "risk_context": {"severity": "HIGH", "content_changed": True},
    })

    assert plan["apply_mode"] == "blocked"
    assert plan["apply_plan"] == []


def test_build_apply_dry_run_exposes_affected_paths_without_execution():
    dry_run = build_apply_dry_run({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert dry_run["apply_mode"] == "dry_run_only"
    assert dry_run["affected_paths"] == ["config/prod.yaml"]
    assert dry_run["dry_run_result"] == "no workspace changes performed"


def test_build_rollback_plan_exposes_backup_metadata():
    rollback = build_rollback_plan({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml", "docs/guide.md"],
        "change_type": "config_change",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert rollback["backup_required"] is True
    assert rollback["backup_targets"] == ["config/prod.yaml", "docs/guide.md"]
    assert rollback["restore_strategy"] in {"full", "partial"}


def test_validate_apply_plan_reports_readiness_checks():
    validation = validate_apply_plan({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    })

    assert validation["apply_ready"] is False
    assert any(check["name"] == "proposal approved" and check["passed"] is True for check in validation["checks"])
    assert any(check["name"] == "critical blockers absent" and check["passed"] is False for check in validation["checks"])


def test_move_to_staging_writes_apply_plan_payload(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "config/prod.yaml|HIGH|review",
        "target": "config/prod.yaml",
        "summary_headline": "review immediately: config/prod.yaml",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)
    process_review_decision(review_entry["signature"], "approved", reference=approval_file)

    apply_plan = load_staging_apply_plan(created["proposal"]["proposal_id"], reference=approval_file)
    assert apply_plan is not None
    assert apply_plan["proposal_id"] == created["proposal"]["proposal_id"]
    assert apply_plan["dry_run"]["dry_run_result"] == "no workspace changes performed"
    assert "rollback_plan" in apply_plan


def test_atomicity_policy_is_metadata_only(tmp_path):
    target = tmp_path / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    policy = build_atomicity_policy({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
        "risk_context": {"severity": "HIGH", "content_changed": True},
    })

    assert policy["atomicity_mode"] == "all_or_nothing"
    assert "all backups available before apply" in policy["atomicity_requirements"]
    assert target.read_text(encoding="utf-8") == before


def test_rollback_triggers_define_full_recovery_mode():
    triggers = build_rollback_triggers({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    assert triggers["rollback_required"] is True
    assert "partial_apply_detected" in triggers["rollback_triggers"]
    assert triggers["recovery_mode"] == "full_rollback_required"


def test_backup_plan_is_metadata_only():
    backup = build_backup_plan({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    assert backup["backup_required"] is True
    assert backup["backup_format"] == "copy_before_apply"
    assert "all target paths resolvable" in backup["backup_preconditions"]


def test_pre_and_post_apply_validation_structures_are_built():
    proposal = {
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "summary": "review config proposal",
        "status": "approved",
        "risk_context": {"severity": "MEDIUM", "content_changed": False},
    }

    pre_validation = build_pre_apply_validation(proposal)
    post_validation = build_post_apply_validation(proposal)

    assert any(check["name"] == "proposal approved" for check in pre_validation["checks"])
    assert any(check["name"] == "target count matches expected" for check in post_validation["checks"])


def test_failure_handling_policy_forbids_partial_apply():
    policy = build_failure_handling_policy()

    assert policy["partial_apply_policy"] == "forbidden"
    assert policy["on_partial_apply"] == "require_full_rollback"
    assert policy["on_unknown_state"] == "halt_and_require_manual_review"


def test_move_to_staging_writes_transaction_sidecar(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "config/prod.yaml|HIGH|review",
        "target": "config/prod.yaml",
        "summary_headline": "review immediately: config/prod.yaml",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)
    process_review_decision(review_entry["signature"], "approved", reference=approval_file)

    transaction = load_staging_apply_transaction(created["proposal"]["proposal_id"], reference=approval_file)
    assert transaction is not None
    assert transaction["proposal_id"] == created["proposal"]["proposal_id"]
    assert transaction["atomicity_policy"]["atomicity_mode"] == "all_or_nothing"
    assert transaction["failure_handling_policy"]["partial_apply_policy"] == "forbidden"
    assert transaction["rollback_triggers"]["recovery_mode"] == "full_rollback_required"


def test_apply_state_machine_contract_is_metadata_only(tmp_path):
    target = tmp_path / "config" / "prod.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mode: prod\n", encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    state_machine = build_apply_state_machine()

    assert state_machine["state_machine_version"] == "v1"
    assert "staged" in state_machine["allowed_transitions"]
    assert "prechecked" in state_machine["allowed_transitions"]["staged"]
    assert target.read_text(encoding="utf-8") == before


def test_target_resolution_contract_rejects_absolute_and_parent_traversal():
    contract = build_target_resolution_contract({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml", "../secret.txt", "C:/temp/x.py"],
        "change_type": "config_change",
    })

    assert contract["path_resolution_mode"] == "strict"
    assert "reject_parent_traversal" in contract["path_rules"]
    assert "reject_absolute_paths" in contract["path_rules"]
    assert "deduplicate_targets_before_apply" in contract["path_rules"]
    assert "target_count_mismatch" in contract["abort_conditions"]


def test_atomic_write_contract_forbids_partial_write():
    contract = build_atomic_write_contract({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
    })

    assert contract["atomic_write_mode"] == "temp_then_rename"
    assert contract["partial_write_policy"] == "forbidden"
    assert contract["failure_on_rename"] == "rollback_required"


def test_backup_materialization_contract_is_metadata_only():
    contract = build_backup_materialization_contract({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
    })

    assert contract["backup_strategy"] == "copy_before_apply"
    assert contract["backup_scope"] == "all_target_paths"
    assert "backup metadata recorded before apply" in contract["backup_requirements"]


def test_rollback_execution_contract_requires_full_rollback_only():
    contract = build_rollback_execution_contract({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
    })

    assert contract["rollback_mode"] == "full_only"
    assert contract["partial_rollback_policy"] == "forbidden"
    assert contract["on_rollback_failure"] == "halt_and_require_manual_review"


def test_apply_abort_conditions_are_structured():
    contract = build_apply_abort_conditions({
        "proposal_id": "proposal_test",
        "target_paths": ["src/core/engine.py"],
        "change_type": "code_change",
    })

    assert "blocked_apply_mode" in contract["abort_conditions"]
    assert "manual_review_required" in contract["halt_conditions"]
    assert "high_risk_change" in contract["manual_review_required_conditions"]


def test_transaction_markers_expose_terminal_rule_summary():
    markers = build_transaction_markers()

    assert "apply_started" in markers["markers"]
    assert markers["terminal_marker_rule_summary"] == "exactly one terminal marker required"


def test_transaction_state_contract_tracks_ordering_rules():
    contract = build_transaction_state_contract({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    assert contract["transaction_id_format"] == "uuid_v4"
    assert contract["transaction_id_generation_rule"] == "uuid_v4"
    assert contract["transaction_id_recording_order"] == "generated_before_transaction_state_recorded"
    assert "globally unique with very low collision probability" in contract["transaction_id_requirements"]
    assert "transaction state recorded before backup" in contract["required_ordering"]
    assert "exactly one terminal state required" in contract["terminal_state_rules"]


def test_build_executor_spec_is_metadata_only_and_versioned():
    spec = build_executor_spec({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    assert spec["executor_spec_version"] == "v1"
    assert spec["transaction_id_format"] == "uuid_v4"
    assert spec["atomic_write_contract"]["partial_write_policy"] == "forbidden"
    assert spec["transaction_markers"]["terminal_marker_rule_summary"] == "exactly one terminal marker required"
    assert spec["transaction_runtime_storage"]["path_pattern"] == "runtime-data/runtime/<transaction_id>.json"
    assert spec["transaction_runtime_storage"]["separation"] == "runtime_state_separate_from_staging"
    assert spec["idempotency_policy"]["mode"] == "strict"
    assert "no duplicate writes" in spec["idempotency_policy"]["rules"]
    assert "no duplicate markers" in spec["idempotency_policy"]["rules"]
    assert "no state mutation after terminal marker" in spec["idempotency_policy"]["rules"]
    assert spec["execution_prohibitions"]["notice"] == "This specification defines constraints for future execution and must not be interpreted as permission to execute apply."
    assert "no file writes are allowed" in spec["execution_prohibitions"]["rules"]


def test_atomicity_policy_uses_uuid_transaction_ids():
    import uuid

    policy = build_atomicity_policy({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    parsed = uuid.UUID(policy["transaction_id"])
    assert str(parsed) == policy["transaction_id"]


def test_move_to_staging_writes_executor_spec_sidecar(tmp_path):
    approval_file = tmp_path / "pending_approvals.json"
    review_entry = {
        "signature": "config/prod.yaml|HIGH|review",
        "target": "config/prod.yaml",
        "summary_headline": "review immediately: config/prod.yaml",
        "status": "pending",
    }
    created = create_proposal(review_entry, reference=approval_file)
    process_review_decision(review_entry["signature"], "approved", reference=approval_file)

    spec = load_staging_executor_spec(created["proposal"]["proposal_id"], reference=approval_file)
    assert spec is not None
    assert spec["proposal_id"] == created["proposal"]["proposal_id"]
    assert spec["executor_spec_version"] == "v1"
    assert spec["atomic_write_contract"]["atomic_write_mode"] == "temp_then_rename"
    assert spec["transaction_id_format"] == "uuid_v4"
    assert spec["transaction_runtime_storage"]["path_pattern"] == "runtime-data/runtime/<transaction_id>.json"
    assert spec["idempotency_policy"]["mode"] == "strict"
    assert "no automatic apply trigger" in spec["execution_prohibitions"]["rules"]


def test_real_apply_gate_is_blocked_by_default():
    gate = build_real_apply_gate({
        "proposal_id": "proposal_test",
        "target_paths": ["config/prod.yaml"],
        "change_type": "config_change",
        "status": "approved",
    })

    assert gate["real_apply_enabled"] is False
    assert gate["enable_mode"] == "blocked"
    assert "real apply feature flag not enabled" in gate["enable_blockers"]
    assert gate["required_flags"]["ENABLE_REAL_APPLY"] is False
    assert gate["required_flags"]["REQUIRE_MANUAL_CONFIRMATION"] is True


def test_real_apply_gate_blocks_without_manual_confirmation():
    gate = build_real_apply_gate(
        {
            "proposal_id": "proposal_test",
            "target_paths": ["config/prod.yaml"],
            "change_type": "config_change",
            "status": "approved",
        },
        flags={"ENABLE_REAL_APPLY": True, "REQUIRE_MANUAL_CONFIRMATION": True},
        manual_confirmation=False,
    )

    assert gate["real_apply_enabled"] is False
    assert "manual confirmation required for real apply" in gate["enable_blockers"]


def test_real_apply_gate_blocks_non_allowlisted_paths():
    gate = build_real_apply_gate(
        {
            "proposal_id": "proposal_test",
            "target_paths": ["config/prod.yaml", "src/core/engine.py"],
            "change_type": "config_change",
            "status": "approved",
        },
        flags={"ENABLE_REAL_APPLY": True, "REQUIRE_MANUAL_CONFIRMATION": True},
        manual_confirmation=True,
    )

    assert gate["real_apply_enabled"] is False
    assert gate["allowed_real_paths"] == ["config/prod.yaml"]
    assert gate["blocked_real_paths"] == ["src/core/engine.py"]
    assert "real apply target path outside live allowlist" in gate["enable_blockers"]


def test_real_apply_gate_exposes_manual_only_contract_and_backup_policy():
    gate = build_real_apply_gate(
        {
            "proposal_id": "proposal_test",
            "target_paths": ["config/prod.yaml"],
            "change_type": "config_change",
            "status": "approved",
        },
        flags={"ENABLE_REAL_APPLY": True, "REQUIRE_MANUAL_CONFIRMATION": True},
        manual_confirmation=True,
    )

    assert gate["real_apply_enabled"] is True
    assert gate["enable_mode"] == "manual_only"
    assert gate["manual_invocation_contract"]["required_confirmation_flag"] == "--confirm-real-apply"
    assert gate["live_backup_root"]["path_pattern"] == "runtime-data/live_backups/<transaction_id>/"
    assert "transaction_id" in gate["audit_logging_contract"]["required_fields"]
    assert "audit log recorded for every attempted real apply" in gate["required_conditions"]


def test_review_summary_payload_reflects_high_priority_wording_and_shared_fields():
    operational_signal = build_operational_signal(
        annotate_changes(["config/prod.yaml"]),
        risk_signal={
            "action_signal": {
                "action": "REVIEW_REQUIRED",
                "certainty": "HIGH",
                "primary_path": "config/prod.yaml",
            },
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {
                "suggestion_priority": 90,
                "suggestion_severity": "critical",
                "reopen_score": 5,
                "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
                "blocker_score": 95,
                "blocker_promoted": True,
            },
            "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
        },
        skills=[{
            "name": "runtime_guard",
            "behavior_class": "review",
            "risk_profile": "runtime_sensitive",
            "handles_config_changes": True,
            "handles_runtime_changes": True,
            "prefers_reopen_on_high_risk": True,
            "suggestion_bias": "action",
            "review_cost": "high",
        }],
    )

    payload = build_review_summary_payload(operational_signal)

    assert payload["summary_headline"].startswith("review immediately: config/prod.yaml")
    assert payload["summary_priority"] == operational_signal["top_suggestion_priority"]
    assert payload["summary_certainty"] == operational_signal["top_suggestion_certainty"]
    assert payload["summary_next_step"] == operational_signal["summary_next_step"]
    assert payload["summary_review_scope"] == operational_signal["summary_review_scope"]


def test_review_summary_payload_softens_wording_for_stale_or_missing_baseline():
    stale_signal = build_operational_signal(
        [],
        risk_signal={
            "action_signal": {
                "action": "REVIEW_RECOMMENDED",
                "certainty": "MEDIUM",
                "primary_path": "config/feature_flags.yaml",
            },
            "baseline_status": "stale",
            "baseline_reason": "stale_snapshot",
            "decision_weighting": {
                "suggestion_priority": 55,
                "suggestion_severity": "medium",
                "reopen_score": 1,
                "blocker_candidate": None,
                "blocker_score": 35,
                "blocker_promoted": False,
            },
        },
    )
    missing_signal = build_operational_signal(
        [],
        risk_signal={
            "action_signal": {
                "action": "MONITOR",
                "certainty": "LOW",
                "primary_path": "src/core/engine.py",
            },
            "baseline_status": "missing",
            "baseline_reason": "initial_scan",
            "decision_weighting": {
                "suggestion_priority": 25,
                "suggestion_severity": "low",
                "reopen_score": 0,
                "blocker_candidate": None,
                "blocker_score": 5,
                "blocker_promoted": False,
            },
        },
    )

    stale_payload = build_review_summary_payload(stale_signal)
    missing_payload = build_review_summary_payload(missing_signal)

    assert "verify against stale baseline" in stale_payload["summary_headline"]
    assert "confirm baseline first" in missing_payload["summary_headline"]
    assert stale_payload["summary_headline"] != missing_payload["summary_headline"]


def test_review_summary_payload_reuses_content_changed_wording_from_operational_signal():
    operational_signal = build_operational_signal(
        annotate_changes(["config/prod.yaml"]),
        risk_signal={
            "current_snapshot": {
                "entries": [{"path": "config/prod.yaml", "severity": "HIGH"}],
            },
            "risk_delta": {
                "new_high_risk_paths": [],
                "persistent_high_risks": ["config/prod.yaml"],
                "content_changed_paths": ["config/prod.yaml"],
                "content_changed_count": 1,
                "top_content_changed_path": "config/prod.yaml",
                "baseline_status": "fresh",
            },
            "action_signal": {"action": "MONITOR", "certainty": "MEDIUM", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {
                "suggestion_priority": 35,
                "suggestion_severity": "low",
                "reopen_score": 1,
                "blocker_candidate": None,
                "blocker_score": 20,
                "blocker_promoted": False,
            },
        },
    )

    payload = build_review_summary_payload(operational_signal)

    assert payload["summary_headline"].startswith("verify recent changes: config/prod.yaml")
    assert payload["summary_next_step"] == operational_signal["summary_next_step"]
    assert payload["summary_review_scope"] == operational_signal["summary_review_scope"]


def test_risk_clusters_group_config_runtime_and_docs_paths():
    cluster_model = build_risk_clusters(
        {
            "entries": [
                {"path": "config/prod.yaml", "severity": "HIGH"},
                {"path": "src/runtime/engine.py", "severity": "HIGH"},
                {"path": "docs/guide.md", "severity": "LOW"},
            ]
        },
        {
            "new_high_risk_paths": ["config/prod.yaml"],
            "persistent_high_risks": ["src/runtime/engine.py"],
            "baseline_status": "fresh",
        },
    )

    cluster_ids = [cluster["cluster_id"] for cluster in cluster_model["clusters"]]
    assert "config" in cluster_ids
    assert "runtime" in cluster_ids
    assert "docs" not in cluster_ids


def test_high_cluster_ranks_above_medium_cluster_and_new_high_counts():
    cluster_model = build_risk_clusters(
        {
            "entries": [
                {"path": "config/prod.yaml", "severity": "HIGH"},
                {"path": "config/feature_flags.yaml", "severity": "HIGH"},
                {"path": "mixed/notes.json", "severity": "MEDIUM"},
            ]
        },
        {
            "new_high_risk_paths": ["config/prod.yaml", "config/feature_flags.yaml"],
            "persistent_high_risks": [],
            "baseline_status": "fresh",
        },
    )

    top_cluster = cluster_model["clusters"][0]
    assert top_cluster["cluster_id"] == "config"
    assert top_cluster["cluster_rank"] == 1
    assert top_cluster["new_high_count"] == 2


def test_clustered_guidance_uses_top_cluster_and_is_conservative_on_stale_baseline():
    cluster_model = {
        "clusters": [{
            "cluster_id": "config",
            "label": "Config Risk Cluster",
            "severity": "HIGH",
            "path_count": 3,
            "new_high_count": 1,
            "persistent_high_count": 1,
            "summary_reason": "new high-risk config changes detected",
            "cluster_rank": 1,
            "cluster_rank_reason": "severity=HIGH",
            "cluster_sort_key": (-3, -1, -1, -2, 0, -3, "config"),
        }],
        "top_cluster_id": "config",
    }

    guidance = build_clustered_guidance(
        cluster_model,
        risk_signal={"baseline_reason": "stale_snapshot"},
    )

    assert guidance["top_risk_cluster_label"] == "Config Risk Cluster"
    assert guidance["cluster_recommended_next_step"].endswith("(verify stale baseline first)")
    assert guidance["cluster_priority_bucket"] == "critical"


def test_clustered_guidance_uses_changed_wording_for_top_cluster_content_changes():
    cluster_model = {
        "clusters": [{
            "cluster_id": "config",
            "label": "Config Risk Cluster",
            "severity": "HIGH",
            "path_count": 3,
            "new_high_count": 0,
            "persistent_high_count": 2,
            "cluster_content_changed_count": 1,
            "cluster_has_content_change": True,
            "top_content_changed_path_in_cluster": "config/prod.yaml",
            "summary_reason": "persistent high-risk config paths remain",
            "cluster_rank": 1,
            "cluster_rank_reason": "severity=HIGH",
            "cluster_sort_key": (-3, 0, -2, -2, 0, -3, "config"),
        }],
        "top_cluster_id": "config",
    }

    guidance = build_clustered_guidance(
        cluster_model,
        risk_signal={"baseline_reason": "fresh_snapshot"},
    )

    assert guidance["cluster_recommended_next_step"] == "review changed config risk paths before reopen"
    assert guidance["cluster_recommended_review_scope"] == "changed config files (1 paths)"


def test_multi_cluster_compact_summary_selects_secondary_high_medium_cluster():
    cluster_model = {
        "clusters": [
            {"cluster_id": "config", "label": "Config Risk Cluster", "severity": "HIGH", "path_count": 3, "cluster_has_content_change": False},
            {"cluster_id": "runtime", "label": "Runtime Risk Cluster", "severity": "HIGH", "path_count": 2, "cluster_has_content_change": True},
            {"cluster_id": "docs", "label": "Docs Risk Cluster", "severity": "LOW", "path_count": 4, "cluster_has_content_change": True},
        ],
        "top_cluster_id": "config",
    }

    summary = build_multi_cluster_compact_summary(cluster_model, baseline_reason="fresh_snapshot")

    assert summary["secondary_cluster_label"] == "Runtime Risk Cluster"
    assert summary["secondary_cluster_severity"] == "HIGH"
    assert summary["secondary_cluster_path_count"] == 2
    assert summary["secondary_cluster_compact_line"] == "Secondary cluster: Runtime Risk Cluster (HIGH, 2 paths), content changes detected"


def test_multi_cluster_compact_summary_keeps_length_compact_and_stale_tone():
    cluster_model = {
        "clusters": [
            {"cluster_id": "config", "label": "Config Risk Cluster", "severity": "HIGH", "path_count": 3, "cluster_has_content_change": False},
            {"cluster_id": "runtime", "label": "Runtime Risk Cluster", "severity": "MEDIUM", "path_count": 2, "cluster_has_content_change": True},
            {"cluster_id": "docs", "label": "Docs Risk Cluster", "severity": "LOW", "path_count": 1, "cluster_has_content_change": False},
        ],
        "top_cluster_id": "config",
    }

    summary = build_multi_cluster_compact_summary(cluster_model, baseline_reason="stale_snapshot")

    assert len(summary["compact_cluster_lines"]) <= 2
    assert "verify against stale baseline" in summary["secondary_cluster_compact_line"]


def test_attach_content_summary_to_clusters_maps_changed_paths_to_matching_cluster():
    cluster_model = build_risk_clusters(
        {
            "entries": [
                {"path": "config/prod.yaml", "severity": "HIGH"},
                {"path": "src/runtime/engine.py", "severity": "HIGH"},
                {"path": "docs/guide.md", "severity": "LOW"},
            ]
        },
        {
            "new_high_risk_paths": ["config/prod.yaml"],
            "persistent_high_risks": ["src/runtime/engine.py"],
            "baseline_status": "fresh",
        },
    )

    enriched = attach_content_summary_to_clusters(
        cluster_model,
        {"content_changed_paths": ["config/prod.yaml"]},
    )

    config_cluster = next(cluster for cluster in enriched["clusters"] if cluster["cluster_id"] == "config")
    runtime_cluster = next(cluster for cluster in enriched["clusters"] if cluster["cluster_id"] == "runtime")

    assert config_cluster["cluster_content_changed_count"] == 1
    assert config_cluster["cluster_content_changed_paths"] == ["config/prod.yaml"]
    assert config_cluster["cluster_has_content_change"] is True
    assert config_cluster["top_content_changed_path_in_cluster"] == "config/prod.yaml"
    assert runtime_cluster["cluster_content_changed_count"] == 0
    assert runtime_cluster["cluster_has_content_change"] is False


def test_cluster_content_summary_does_not_change_existing_cluster_ranking():
    cluster_model = build_risk_clusters(
        {
            "entries": [
                {"path": "config/prod.yaml", "severity": "HIGH"},
                {"path": "mixed/notes.json", "severity": "MEDIUM"},
            ]
        },
        {
            "new_high_risk_paths": ["config/prod.yaml"],
            "persistent_high_risks": [],
            "baseline_status": "fresh",
        },
    )

    base_ids = [cluster["cluster_id"] for cluster in cluster_model["clusters"]]
    enriched = attach_content_summary_to_clusters(cluster_model, {"content_changed_paths": ["mixed/notes.json"]})

    assert [cluster["cluster_id"] for cluster in enriched["clusters"]] == base_ids
    assert enriched["clusters"][0]["cluster_rank"] == 1


def test_report_only_lines_include_review_summary_at_top():
    state = {
        "total_files": 3,
        "total_dirs": 1,
        "total_size_bytes": 128,
        "files": ["config/prod.yaml", "src/app.py", "README.md"],
        "scanned_at": "2026-03-22T00:00:00Z",
    }
    review_summary = {
        "summary_headline": "review immediately: config/prod.yaml",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "summary_next_step": "review config change before reopen",
        "summary_review_scope": "configuration boundary",
        "summary_cluster_line": "Top cluster: Config Risk Cluster (2 paths, HIGH)",
    }

    lines, _ = build_report_only_lines(state, review_summary=review_summary)
    text = "\n".join(lines[:12])

    assert "- 운영 요약: review immediately: config/prod.yaml" in text
    assert "- 우선순위: 90 | 확실도: HIGH" in text
    assert "- Top cluster: Config Risk Cluster (2 paths, HIGH)" in text
    assert "- 다음 단계: review config change before reopen" in text


def test_review_summary_lines_include_content_change_hint():
    review_summary = {
        "summary_headline": "review immediately: config/prod.yaml",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "content_changed_count": 1,
        "top_content_changed_path": "config/prod.yaml",
        "top_content_change_hint": "config/prod.yaml: json keys changed",
    }

    lines = build_report_only_lines(
        {"total_files": 1, "total_dirs": 1, "total_size_bytes": 10, "files": ["config/prod.yaml"]},
        review_summary=review_summary,
    )[0]
    text = "\n".join(lines[:10])

    assert "Content changes detected in existing risk paths: config/prod.yaml" in text
    assert "Change hint: config/prod.yaml: json keys changed" in text


def test_review_summary_lines_include_top_cluster_content_hint():
    review_summary = {
        "summary_headline": "review immediately: config/prod.yaml",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "summary_cluster_line": "Top cluster: Config Risk Cluster (2 paths, HIGH)",
        "summary_cluster_content_line": "Content changes detected in top cluster: config/prod.yaml",
    }

    lines = build_report_only_lines(
        {"total_files": 1, "total_dirs": 1, "total_size_bytes": 10, "files": ["config/prod.yaml"]},
        review_summary=review_summary,
    )[0]
    text = "\n".join(lines[:10])

    assert "Content changes detected in top cluster: config/prod.yaml" in text


def test_review_summary_lines_include_secondary_cluster_compact_line():
    review_summary = {
        "summary_headline": "review immediately: config/prod.yaml",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "summary_cluster_line": "Top cluster: Config Risk Cluster (2 paths, HIGH)",
        "summary_secondary_cluster_line": "Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)",
        "summary_additional_cluster_note": "Additional cluster: Docs Risk Cluster (LOW, 1 paths) | confirm against baseline",
    }

    lines = build_report_only_lines(
        {"total_files": 1, "total_dirs": 1, "total_size_bytes": 10, "files": ["config/prod.yaml"]},
        review_summary=review_summary,
    )[0]
    text = "\n".join(lines[:12])

    assert "Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)" in text
    assert "Additional cluster: Docs Risk Cluster (LOW, 1 paths) | confirm against baseline" in text


def test_review_summary_lines_follow_common_render_order():
    lines = build_review_summary_lines({
        "summary_headline": "review immediately: config/prod.yaml",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "summary_next_step": "review config risk cluster before reopen",
        "summary_review_scope": "config files (1 paths, 1 new high-risk)",
        "summary_cluster_line": "Top cluster: Config Risk Cluster (1 paths, HIGH)",
        "summary_secondary_cluster_line": "Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)",
        "summary_additional_cluster_note": "Additional cluster: Docs Risk Cluster (LOW, 1 paths)",
        "content_changed_count": 1,
        "top_content_changed_path": "config/prod.yaml",
        "top_content_change_hint": "config/prod.yaml: values changed",
    })

    headline_index = lines.index("- 운영 요약: review immediately: config/prod.yaml")
    action_index = lines.index("- 다음 단계: review config risk cluster before reopen")
    priority_index = lines.index("- 우선순위: 90 | 확실도: HIGH")
    top_cluster_index = lines.index("- Top cluster: Config Risk Cluster (1 paths, HIGH)")
    secondary_index = lines.index("- Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)")

    assert headline_index < action_index < priority_index < top_cluster_index < secondary_index


def test_workspace_reporter_summary_surfaces_review_summary_before_general_summary(tmp_path):
    config_dir = tmp_path / "config"
    runtime_dir = tmp_path / "src" / "runtime"
    config_dir.mkdir()
    runtime_dir.mkdir(parents=True)
    (config_dir / "prod.yaml").write_text("mode: prod\n", encoding="utf-8")
    (runtime_dir / "engine.py").write_text("print('ok')\n", encoding="utf-8")

    executor = Executor(workspace=str(tmp_path))
    skill_executor = SkillExecutor(executor)
    ctx = {}
    ctx.update(skill_executor._step_analyze("scan_workspace", ctx, {"name": "workspace_reporter"}))

    lines = skill_executor._report_workspace(ctx)
    summary_index = lines.index("## 요약")
    summary_slice = lines[summary_index + 1:summary_index + 8]

    assert any("운영 요약:" in line for line in summary_slice)
    assert any("Top cluster:" in line for line in summary_slice)
    assert any("다음 단계:" in line for line in summary_slice)


def test_inferred_risk_metadata_is_exposed_for_metadata_free_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "custom_monitor"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# custom\n## name\ncustom_monitor\n## behavior_class\nobserve\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    loaded = load_skills(str(tmp_path / "skills"))

    assert loaded[0]["inferred_risk_metadata_used"] is True
    assert loaded[0]["inferred_from"] == "behavior_class"


def test_operational_signal_exposes_cluster_fields_and_metadata_hint():
    operational_signal = build_operational_signal(
        annotate_changes(["src/runtime/engine.py"]),
        risk_signal={
            "current_snapshot": {
                "entries": [{"path": "src/runtime/engine.py", "severity": "HIGH"}],
            },
            "risk_delta": {
                "new_high_risk_paths": ["src/runtime/engine.py"],
                "persistent_high_risks": [],
                "baseline_status": "fresh",
            },
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "src/runtime/engine.py"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {
                "suggestion_priority": 90,
                "suggestion_severity": "critical",
                "reopen_score": 5,
                "blocker_candidate": "risk:REVIEW_REQUIRED(src/runtime/engine.py)",
                "blocker_score": 95,
                "blocker_promoted": True,
            },
            "blocker_candidate": "risk:REVIEW_REQUIRED(src/runtime/engine.py)",
        },
        skills=[{
            "name": "workspace_reporter",
            "behavior_class": "observe",
            "risk_profile": "monitoring",
            "handles_config_changes": False,
            "handles_runtime_changes": False,
            "prefers_reopen_on_high_risk": False,
            "suggestion_bias": "monitor",
            "review_cost": "low",
        }],
    )

    assert operational_signal["top_risk_cluster_label"] == "Runtime Risk Cluster"
    assert operational_signal["top_risk_cluster_severity"] == "HIGH"
    assert operational_signal["top_risk_cluster_path_count"] == 1
    assert operational_signal["cluster_recommended_next_step"].startswith("review runtime-sensitive cluster")
    assert operational_signal["metadata_mismatch_hint"] == "selected skill may not be ideal for runtime-sensitive cluster"


def test_operational_signal_exposes_top_cluster_content_fields():
    operational_signal = build_operational_signal(
        annotate_changes(["config/prod.yaml", "src/runtime/engine.py"]),
        risk_signal={
            "current_snapshot": {
                "entries": [
                    {"path": "config/prod.yaml", "severity": "HIGH"},
                    {"path": "src/runtime/engine.py", "severity": "HIGH"},
                ],
            },
            "risk_delta": {
                "new_high_risk_paths": ["config/prod.yaml"],
                "persistent_high_risks": ["src/runtime/engine.py"],
                "content_changed_paths": ["config/prod.yaml"],
                "baseline_status": "fresh",
            },
            "action_signal": {"action": "REVIEW_REQUIRED", "certainty": "HIGH", "primary_path": "config/prod.yaml"},
            "baseline_status": "fresh",
            "baseline_reason": "fresh_snapshot",
            "decision_weighting": {
                "suggestion_priority": 90,
                "suggestion_severity": "critical",
                "reopen_score": 5,
                "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
                "blocker_score": 95,
                "blocker_promoted": True,
            },
            "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
        },
    )

    assert operational_signal["top_risk_cluster_label"] == "Config Risk Cluster"
    assert operational_signal["top_risk_cluster_content_changed_count"] == 1
    assert operational_signal["top_risk_cluster_has_content_change"] is True
    assert operational_signal["top_risk_cluster_top_content_changed_path"] == "config/prod.yaml"


def test_skill_metadata_template_explains_risk_hint_placeholders():
    template = build_skill_metadata_template()

    assert "monitoring  # monitoring | runtime_sensitive | config_sensitive" in template
    assert "false  # true면 config/settings 변경 대응에 적합한 스킬" in template
    assert "explain  # action | explain | monitor" in template


def test_builtin_skills_use_explicit_behavior_class_metadata():
    skills = load_skills(os.path.join(BASE_DIR, "skills"))
    diagnostics = get_behavior_class_diagnostics(skills)

    assert diagnostics["explicit_skills"] == ["code_reviewer", "file_classifier", "workspace_reporter"]
    assert diagnostics["fallback_skills"] == []
    assert diagnostics["explicit_transition_needed"] == []
    assert diagnostics["all_explicit"] is True


def test_builtin_skills_reduce_consistency_warnings_and_improve_readiness():
    skills = load_skills(os.path.join(BASE_DIR, "skills"))
    diagnostics = get_behavior_class_diagnostics(skills)
    readiness = build_strict_behavior_readiness(diagnostics, mode="include_consistency")

    assert diagnostics["inconsistent_behavior_class_skills"] == []
    assert diagnostics["consistency_warnings"] == []
    assert readiness["strict_ready"] is True
    assert readiness["fallback_skill_count"] == 0
    assert readiness["explicit_transition_needed_count"] == 0
    assert readiness["blockers"] == []


def test_skill_executor_saves_reports_directly_to_reports_dir(tmp_path):
    executor = Executor(workspace=str(tmp_path))
    skill_executor = SkillExecutor(executor)

    result = skill_executor._step_report(
        "write_report: test",
        {"structs": {}},
        {"name": "code_reviewer"},
    )

    assert result["output_file"].startswith("reports/")
    assert Path(tmp_path / result["output_file"]).exists()


def test_memory_analyzer_reads_compact_history_fields():
    lines = build_memory_analysis_lines(
        [
            {"event": "skill", "action_type": "skill", "skill_name": "workspace_reporter", "status": "success"},
            {"event": "fallback", "action_type": "report", "fallback_name": "report_only", "status": "success"},
            {"event": "fallback", "action_type": "report", "fallback_name": "report_only", "status": "partial"},
        ],
        [
            {"skill": "report_only"},
            {"skill": "memory_analyzer"},
        ],
    )

    text = "\n".join(lines)

    assert "unknown" not in text
    assert "workspace_reporter: 1회" in text
    assert "report_only: 2회" in text


def test_workspace_and_classifier_reports_reflect_existing_reports_dir(tmp_path):
    (tmp_path / "agent.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# doc\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "prod.yaml").write_text("mode: prod\n", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "workspace_reporter_20260322_010101.md").write_text("# report\n", encoding="utf-8")
    (reports_dir / "file_classifier_20260322_010102.md").write_text("# report\n", encoding="utf-8")

    executor = Executor(workspace=str(tmp_path))
    skill_executor = SkillExecutor(executor)
    ctx = {}
    ctx.update(skill_executor._step_analyze("scan_workspace", ctx, {"name": "workspace_reporter"}))

    workspace_text = "\n".join(skill_executor._report_workspace(ctx))
    classifier_text = "\n".join(skill_executor._report_classifier(ctx))

    assert "`reports/` 아래에 누적" in workspace_text
    assert "루트에 100개 이상 축적" not in workspace_text
    assert "자동 생성 보고서 `.md`" not in workspace_text
    assert "- 운영 요약:" in classifier_text
    assert "- 우선순위:" in classifier_text
    assert "- 다음 단계:" in classifier_text
    assert "코드와 문서 파일이 함께 존재해" in classifier_text
    assert "동일 계층 혼재" not in classifier_text


def test_code_reviewer_report_includes_review_summary_block(tmp_path):
    config_dir = tmp_path / "config"
    runtime_dir = tmp_path / "src" / "runtime"
    config_dir.mkdir()
    runtime_dir.mkdir(parents=True)
    (config_dir / "prod.yaml").write_text("mode: prod\n", encoding="utf-8")
    (runtime_dir / "engine.py").write_text(
        "def run():\n    return 'ok'\n",
        encoding="utf-8",
    )

    executor = Executor(workspace=str(tmp_path))
    skill_executor = SkillExecutor(executor)
    ctx = {}
    skill = {"name": "code_reviewer"}
    ctx.update(skill_executor._step_analyze("scan_workspace", ctx, skill))
    ctx.update(skill_executor._step_scan_code("scan_code_files", ctx, skill))
    ctx.update(skill_executor._step_extract_structure("extract_structure", ctx, skill))

    text = "\n".join(skill_executor._report_code(ctx))

    assert "- 운영 요약:" in text
    assert "- 우선순위:" in text
    assert "- 다음 단계:" in text
    assert "- 검토 범위:" in text


def test_inspect_log_layout_logs_dir_managed(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "agent.log").write_text("ok", encoding="utf-8")

    layout = _inspect_log_layout(tmp_path)

    assert layout["assessment"] == "logs_dir_managed"


def test_inspect_log_layout_root_logs_present(tmp_path):
    (tmp_path / "agent.log").write_text("ok", encoding="utf-8")

    layout = _inspect_log_layout(tmp_path)

    assert layout["assessment"] == "root_logs_present"


def test_inspect_log_layout_mixed_log_layout(tmp_path):
    (tmp_path / "agent.log").write_text("ok", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "runtime.log").write_text("ok", encoding="utf-8")

    layout = _inspect_log_layout(tmp_path)

    assert layout["assessment"] == "mixed_log_layout"


def test_inspect_log_layout_no_logs_detected(tmp_path):
    layout = _inspect_log_layout(tmp_path)

    assert layout["assessment"] == "no_logs_detected"
