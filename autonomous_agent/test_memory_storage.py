import json
import logging
import os
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
import pytest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from agent.memory import Memory
from agent.workspace_metrics import create_pending_approvals, annotate_changes, build_state_summary
from agent.loop import AgentLoop


def test_memory_saves_small_state_and_jsonl_history(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.increment_cycle()
    for idx in range(12):
        memory.record_action(
            "report_only" if idx % 2 == 0 else f"skill_{idx}",
            summary="x" * 200,
            report_path=f"reports/report_{idx}.md",
        )
    memory.add_history({
        "cycle": 1,
        "action": {"type": "skill", "skill_name": "workspace_reporter", "source": "planner"},
        "result": {"success": True, "output": "보고서 생성 완료 " + ("y" * 200), "report_file": "reports/workspace_reporter.md"},
        "evaluation": {"score": 88, "status": "success"},
    })
    memory.save()

    state = json.loads((tmp_path / "agent_state.json").read_text(encoding="utf-8"))
    history_lines = (tmp_path / "history" / "history_current.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert set(state.keys()) == {
        "current_cycle",
        "recent_actions",
        "recent_fallbacks",
        "recent_scores",
        "trend",
        "last_run_at",
        "last_success_at",
    }
    assert len(state["recent_actions"]) == 10
    assert len(state["recent_fallbacks"]) == 5
    assert len(history_lines) == 1
    event = json.loads(history_lines[0])
    assert len(event["summary"]) <= 120
    assert event["report_path"] == "reports/workspace_reporter.md"
    status_line = memory.format_storage_status(memory.get_storage_status())
    assert status_line.startswith("[Storage] state=")

def test_memory_rotates_history_and_writes_snapshot(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    memory = Memory(
        filepath=str(tmp_path / "agent_memory.json"),
        history_max_bytes=300,
    )
    memory.load()
    for idx in range(8):
        memory.add_history({
            "cycle": idx + 1,
            "action": {"type": "action", "source": "planner"},
            "result": {"success": True, "output": f"event {idx} " + ("z" * 80)},
            "evaluation": {"score": 60 + idx, "status": "success"},
        })

    rotated = list((tmp_path / "history").glob("history_*.jsonl"))
    snapshots = list((tmp_path / "archive" / "memory").glob("state_*.json"))

    assert rotated
    assert snapshots
    assert "history rotated ->" in caplog.text

def test_memory_migrates_small_legacy_json(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    legacy_path = tmp_path / "agent_memory.json"
    legacy_path.write_text(json.dumps({
        "goals": ["legacy"],
        "history": [
            {
                "cycle": 1,
                "action": {"type": "skill", "skill_name": "workspace_reporter", "source": "planner"},
                "result": {"success": True, "output": "legacy report", "report_file": "reports/legacy.md"},
                "evaluation": {"score": 77, "status": "success"},
                "timestamp": "2026-03-21T00:00:00Z",
            }
        ],
        "recent_actions": [{"skill": "workspace_reporter", "summary": "legacy", "executed_at": "2026-03-21T00:00:00Z"}],
        "last_state": {},
        "metadata": {"total_cycles": 3, "last_updated": "2026-03-21T00:00:00Z"},
    }, ensure_ascii=False), encoding="utf-8")

    memory = Memory(filepath=str(legacy_path))
    data = memory.load()

    assert data["current_cycle"] == 3
    assert (tmp_path / "agent_state.json").exists()
    assert list((tmp_path / "archive" / "memory").glob("legacy_agent_memory_*.json"))
    assert (tmp_path / "history" / "history_current.jsonl").exists()
    assert "legacy memory archived ->" in caplog.text


def test_memory_archives_large_legacy_without_parsing(tmp_path):
    legacy_path = tmp_path / "agent_memory.json"
    legacy_path.write_text("{" + ("a" * 200) + "}", encoding="utf-8")

    memory = Memory(
        filepath=str(legacy_path),
        legacy_import_max_bytes=10,
    )
    data = memory.load()

    assert data["current_cycle"] == 0
    assert list((tmp_path / "archive" / "memory").glob("legacy_agent_memory_*.json"))


def test_state_size_warning_log_emitted(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    memory = Memory(
        filepath=str(tmp_path / "agent_memory.json"),
        state_max_bytes=200,
    )
    memory.load()
    for idx in range(10):
        memory.record_action(f"skill_{idx}", summary="x" * 120, report_path=f"reports/{idx}.md")
    memory.save()

    assert "[Storage] warning: agent_state.json exceeds 256KB" in caplog.text


def test_inspect_storage_output_is_not_empty(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    (tmp_path / "agent_memory_broken_large.json").write_text("x" * (1024 * 1024 + 32), encoding="utf-8")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Storage Status" in completed.stdout
    assert "agent_memory_broken_large.json" in completed.stdout


def test_inspect_storage_outputs_operational_gate_view(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    changes = annotate_changes(["src/app.py"])
    summary = build_state_summary(changes)
    create_pending_approvals(changes, summary, tmp_path / "pending_approvals.json")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Operational Gate" in completed.stdout
    assert "- gate_mode: observe_only" in completed.stdout
    assert "- approval_status: pending" in completed.stdout
    assert "- target: src/app.py" in completed.stdout


def test_inspect_storage_outputs_operational_approval_summary(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    approval_file = tmp_path / "pending_approvals.json"

    first = create_pending_approvals(
        annotate_changes(["src/app.py"]),
        build_state_summary(annotate_changes(["src/app.py"])),
        approval_file,
    )["created"][0]
    create_pending_approvals(
        annotate_changes(["src/other.py"]),
        build_state_summary(annotate_changes(["src/other.py"])),
        approval_file,
    )
    from agent.workspace_metrics import update_pending_approval_status
    update_pending_approval_status(approval_file, first["signature"], "approved")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Operational Approval Summary" in completed.stdout
    assert "- total_operational_approvals_count: 2" in completed.stdout
    assert "- pending_operational_approvals_count: 1" in completed.stdout
    assert "- approved_count: 1" in completed.stdout
    assert "- rejected_count: 0" in completed.stdout
    assert "- recent_targets: src/other.py, src/app.py" in completed.stdout


def test_inspect_storage_outputs_risk_overview(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    src_dir = tmp_path / "src"
    config_dir = tmp_path / "config"
    docs_dir = tmp_path / "docs"
    src_dir.mkdir()
    config_dir.mkdir()
    docs_dir.mkdir()
    (src_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (config_dir / "settings.yaml").write_text("debug: false\n", encoding="utf-8")
    (docs_dir / "guide.md").write_text("# guide\n", encoding="utf-8")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Risk Overview" in completed.stdout
    assert "- high_risk_count: 2" in completed.stdout
    assert "- medium_risk_count: 0" in completed.stdout
    assert "- low_risk_count: 1" in completed.stdout
    assert "- highest_risk: HIGH" in completed.stdout
    assert "- primary_risky_path:" in completed.stdout
    assert "- primary_risky_path: none" not in completed.stdout


def test_inspect_storage_outputs_risk_delta_and_action_signal(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "risk_snapshot.json").write_text(json.dumps({
        "entries": [
            {"path": "scripts/old_runner.py", "severity": "HIGH"},
            {"path": "src/core/engine.py", "severity": "HIGH"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    src_dir = tmp_path / "src" / "core"
    config_dir = tmp_path / "config"
    src_dir.mkdir(parents=True)
    config_dir.mkdir()
    (src_dir / "engine.py").write_text("print('ok')\n", encoding="utf-8")
    (config_dir / "prod.yaml").write_text("mode: prod\n", encoding="utf-8")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Risk Baseline" in completed.stdout
    assert "- baseline_status: fresh" in completed.stdout
    assert "- baseline_reason: fresh_snapshot" in completed.stdout
    assert "Risk Delta" in completed.stdout
    assert "- baseline_status: fresh" in completed.stdout
    assert "- baseline_reason: fresh_snapshot" in completed.stdout
    assert "- high_risk_delta: 0" in completed.stdout
    assert "- new_high_risk_paths: config/prod.yaml" in completed.stdout
    assert "- resolved_high_risks: scripts/old_runner.py" in completed.stdout
    assert "Action Signal" in completed.stdout
    assert "- action: REVIEW_REQUIRED" in completed.stdout
    assert "- reason: new HIGH risk detected" in completed.stdout
    assert "- primary_path: config/prod.yaml" in completed.stdout
    assert "- certainty: HIGH" in completed.stdout
    assert "Operational Risk Signal" in completed.stdout
    assert "- risk_action: REVIEW_REQUIRED" in completed.stdout
    assert "- risk_primary_path: config/prod.yaml" in completed.stdout
    assert "- risk_certainty: HIGH" in completed.stdout
    assert "- baseline_reason: fresh_snapshot" in completed.stdout
    assert "- blocker_candidate: risk:REVIEW_REQUIRED(config/prod.yaml)" in completed.stdout
    assert "Reopen Priority" in completed.stdout
    assert "- reopen_candidate:" in completed.stdout
    assert "- reopen_priority:" in completed.stdout
    assert "- reopen_rank_reason:" in completed.stdout
    assert "- skill_risk_profile:" in completed.stdout
    assert "- metadata_weight_applied:" in completed.stdout
    assert "Suggestion Priority" in completed.stdout
    assert "- suggestion_priority:" in completed.stdout
    assert "- suggestion_severity: critical" in completed.stdout
    assert "- suggestion_certainty: HIGH" in completed.stdout
    assert "- suggestion_text:" in completed.stdout
    assert "Operator Guidance" in completed.stdout
    assert "- recommended_next_step: review config change before reopen" in completed.stdout
    assert "- recommended_review_scope: configuration boundary" in completed.stdout
    assert "- priority_bucket: critical" in completed.stdout
    assert "Risk Clusters" in completed.stdout
    assert "- top_cluster: Config Risk Cluster" in completed.stdout
    assert "- cluster_severity: HIGH" in completed.stdout
    assert "- cluster_path_count:" in completed.stdout
    assert "- cluster_summary_reason:" in completed.stdout
    assert "- cluster_content_changed_count: 0" in completed.stdout
    assert "- cluster_top_content_changed_path: none" in completed.stdout
    assert "Review Summary" in completed.stdout
    assert "- [Headline]" in completed.stdout
    assert "  - review immediately: config/prod.yaml" in completed.stdout
    assert "- [Action]" in completed.stdout
    assert "  - next: review config risk cluster before reopen" in completed.stdout
    assert "- [Priority / Certainty]" in completed.stdout
    assert "  - bucket: critical" in completed.stdout
    assert "  - certainty: HIGH" in completed.stdout
    assert "- [Top Cluster]" in completed.stdout
    assert "  - Top cluster: Config Risk Cluster" in completed.stdout
    assert completed.stdout.index("- [Headline]") < completed.stdout.index("- [Action]")
    assert completed.stdout.index("- [Action]") < completed.stdout.index("- [Priority / Certainty]")
    assert completed.stdout.index("- [Priority / Certainty]") < completed.stdout.index("- [Top Cluster]")
    assert "Metadata Inference" in completed.stdout
    assert "- inferred_risk_metadata_used:" in completed.stdout
    assert "- inferred_from:" in completed.stdout
    assert "- metadata_mismatch_hint:" in completed.stdout
    assert "Strict Risk Integration" in completed.stdout
    assert "- risk_blocker_candidate: risk:REVIEW_REQUIRED(config/prod.yaml)" in completed.stdout
    assert "- risk_blocker_promoted: True" in completed.stdout


def test_inspect_storage_outputs_content_changes_for_existing_risk_path(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    file_path = config_dir / "prod.yaml"
    file_path.write_text("mode: prod\n", encoding="utf-8")

    from agent.workspace_metrics import write_risk_snapshot
    write_risk_snapshot(tmp_path, ["config/prod.yaml"], source="baseline")

    file_path.write_text("mode: prod\nfeature_flag: true\n", encoding="utf-8")

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Content Changes" in completed.stdout
    assert "- content_changed_count: 1" in completed.stdout
    assert "- content_changed_paths: config/prod.yaml" in completed.stdout
    assert "- top_content_change_hint: config/prod.yaml: line count changed" in completed.stdout
    assert "- cluster_content_changed_count: 1" in completed.stdout
    assert "- cluster_top_content_changed_path: config/prod.yaml" in completed.stdout
    assert "- cluster_top_content_change_hint: config/prod.yaml: line count changed" in completed.stdout


def test_review_pending_show_reuses_operational_summary_wording(tmp_path):
    import review_pending as review_pending_module
    from agent.workspace_metrics import create_proposal

    approval_payload = [{
        "signature": "config/prod.yaml|HIGH|review",
        "status": "pending",
        "summary_headline": "review immediately: config/prod.yaml | High-risk Config Risk Cluster",
        "summary_priority": 90,
        "summary_certainty": "HIGH",
        "summary_next_step": "review config risk cluster before reopen",
        "summary_review_scope": "config files (1 paths, 1 new high-risk)",
        "recommended_next_step": "review config change before reopen (confirm baseline before interpreting changes)",
        "recommended_review_scope": "configuration boundary",
        "priority_bucket": "critical",
        "top_risk_cluster_label": "Config Risk Cluster",
        "top_risk_cluster_severity": "HIGH",
        "top_risk_cluster_path_count": 1,
        "top_risk_cluster_has_content_change": True,
        "top_risk_cluster_top_content_change_hint": "config/prod.yaml: json keys changed",
        "cluster_recommended_next_step": "review config risk cluster before reopen",
        "secondary_cluster_compact_line": "Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)",
        "additional_cluster_note": "Additional cluster: Docs Risk Cluster (LOW, 1 paths) | confirm against baseline",
        "metadata_mismatch_hint": "selected skill may not fully cover config-sensitive cluster",
        "action": {"op": "review"},
        "priority": 90,
        "requested_at": "2026-03-23T00:00:00Z",
        "suggestion": "review immediately: config/prod.yaml",
    }]
    approval_file = tmp_path / "pending_approvals.json"
    approval_file.write_text(json.dumps(approval_payload, ensure_ascii=False), encoding="utf-8")
    create_proposal(approval_payload[0], reference=approval_file)

    previous_path = review_pending_module.APPROVAL_FILE
    review_pending_module.APPROVAL_FILE = str(approval_file)
    try:
        data = review_pending_module._load()
        stdout = StringIO()
        with redirect_stdout(stdout):
            review_pending_module.cmd_show(data, "0")
    finally:
        review_pending_module.APPROVAL_FILE = previous_path

    output = stdout.getvalue()
    assert "[Headline]" in output
    assert "- review immediately: config/prod.yaml | High-risk Config Risk Cluster" in output
    assert "[Action]" in output
    assert "- next: review config risk cluster before reopen" in output
    assert "- scope: config files (1 paths, 1 new high-risk)" in output
    assert "[Priority / Certainty]" in output
    assert "- bucket: critical" in output
    assert "- priority: 90" in output
    assert "- certainty: HIGH" in output
    assert "[Top Cluster]" in output
    assert "- Top cluster: Config Risk Cluster (1 paths, HIGH)" in output
    assert "- Content changes detected in top cluster" in output
    assert "- Change hint: config/prod.yaml: json keys changed" in output
    assert "[Secondary / Additional]" in output
    assert "- Secondary cluster: Runtime Risk Cluster (MEDIUM, 2 paths)" in output
    assert "- Additional cluster: Docs Risk Cluster (LOW, 1 paths) | confirm against baseline" in output
    assert "[Baseline Note]" in output
    assert "- confirm baseline first" in output
    assert "[Metadata / Hints]" in output
    assert "- selected skill may not fully cover config-sensitive cluster" in output
    assert "[Proposal]" in output
    assert "- proposal_id: proposal_" in output
    assert "- proposal_status: pending" in output
    assert "- proposal_summary: review immediately: config/prod.yaml | High-risk Config Risk Cluster" in output
    assert "[Apply Precheck]" in output
    assert "- apply_mode: blocked" in output or "- apply_mode: dry_run_only" in output
    assert "- apply_possible: False" in output
    assert "- blockers:" in output
    assert "- operator_steps:" in output
    assert "[Apply Plan Preview]" in output
    assert "- number_of_changes:" in output
    assert "- affected_paths:" in output
    assert "- dry_run_summary: no workspace changes performed" in output
    assert "[Apply Safety Boundary]" in output
    assert "- atomicity_mode: all_or_nothing" in output or "- atomicity_mode:" in output
    assert "- rollback_required: full_rollback_required" in output or "- rollback_required:" in output
    assert "- backup_required: True" in output
    assert "- partial_apply_policy: forbidden" in output
    assert "- recovery_mode: full_rollback_required" in output
    assert "[Executor Specification]" in output
    assert "- atomic_write_mode: temp_then_rename" in output
    assert "- rollback_mode: full_only" in output
    assert "- backup_strategy: copy_before_apply" in output
    assert "- partial_write_policy: forbidden" in output
    assert "- terminal_marker_rule: exactly one terminal marker required" in output
    assert output.index("[Headline]") < output.index("[Action]")
    assert output.index("[Action]") < output.index("[Priority / Certainty]")
    assert output.index("[Priority / Certainty]") < output.index("[Top Cluster]")
    assert output.index("[Top Cluster]") < output.index("[Secondary / Additional]")
    assert output.index("[Secondary / Additional]") < output.index("[Baseline Note]")
    assert output.index("[Baseline Note]") < output.index("[Metadata / Hints]")
    assert output.index("[Proposal]") < output.index("[Apply Precheck]")
    assert output.index("[Apply Precheck]") < output.index("[Apply Plan Preview]")
    assert output.index("[Apply Plan Preview]") < output.index("[Apply Safety Boundary]")
    assert output.index("[Apply Safety Boundary]") < output.index("[Executor Specification]")


def test_review_pending_list_uses_compact_lines(tmp_path):
    import review_pending as review_pending_module

    approval_payload = [{
        "status": "pending",
        "summary_headline": "review immediately: config/prod.yaml | High-risk Config Risk Cluster",
        "priority_bucket": "critical",
        "top_risk_cluster_label": "Config Risk Cluster",
        "top_risk_cluster_has_content_change": True,
        "action": {"op": "review"},
    }]
    approval_file = tmp_path / "pending_approvals.json"
    approval_file.write_text(json.dumps(approval_payload, ensure_ascii=False), encoding="utf-8")

    previous_path = review_pending_module.APPROVAL_FILE
    review_pending_module.APPROVAL_FILE = str(approval_file)
    try:
        data = review_pending_module._load()
        stdout = StringIO()
        with redirect_stdout(stdout):
            review_pending_module.cmd_list(data)
    finally:
        review_pending_module.APPROVAL_FILE = previous_path

    output = stdout.getvalue()
    assert "빠른 훑기:" in output
    assert "[0] review immediately: config/prod.yaml" in output
    assert "| Config Risk Cluster *changed | critical" in output
    assert "review immediately: config/prod.yaml" in output


def test_inspect_storage_outputs_strict_mode_and_readiness(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "skills": {"strict_behavior_class": True},
    }, ensure_ascii=False), encoding="utf-8")
    explicit_skill_dir = tmp_path / "skills" / "workspace_reporter"
    fallback_skill_dir = tmp_path / "skills" / "custom_audit"
    explicit_skill_dir.mkdir(parents=True)
    fallback_skill_dir.mkdir(parents=True)
    (explicit_skill_dir / "SKILL.md").write_text(
        "# explicit\n## name\nworkspace_reporter\n## behavior_class\nreport\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    (fallback_skill_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Behavior Class" in completed.stdout
    assert "- configured_strict_behavior_class: on" in completed.stdout
    assert "- effective_strict_behavior_class: on" in completed.stdout
    assert "- all_explicit: False" in completed.stdout
    assert "- fallback_skills_count: 1" in completed.stdout
    assert "- explicit_transition_needed_count: 1" in completed.stdout
    assert "- inconsistent_behavior_class_skills_count: 0" in completed.stdout
    assert "- consistency_warnings_count: 0" in completed.stdout
    assert "Strict Readiness" in completed.stdout
    assert "- strict_ready: False" in completed.stdout
    assert "- strict_readiness_mode: missing_only" in completed.stdout
    assert "- fallback_skill_count: 1" in completed.stdout
    assert "- explicit_transition_needed_count: 1" in completed.stdout
    assert "- blockers: custom_audit" in completed.stdout
    assert "Explicit Transition Report" in completed.stdout
    assert "- fallback_skills: custom_audit" in completed.stdout
    assert "- inconsistent_behavior_class_skills: none" in completed.stdout
    assert "- explicit_transition_needed: custom_audit" in completed.stdout
    assert "- strict_blockers: custom_audit" in completed.stdout
    assert "- suggested_behavior_class: custom_audit->report" in completed.stdout
    assert "Strict Preflight Summary" in completed.stdout
    assert "- fallback_blocker_count: 1" in completed.stdout
    assert "- consistency_blocker_count: 0" in completed.stdout
    assert "- primary_blocker: custom_audit" in completed.stdout
    assert "Skill Metadata Template" in completed.stdout
    assert "  ## name" in completed.stdout
    assert "  ## behavior_class" in completed.stdout
    assert "  ## description" in completed.stdout


def test_inspect_storage_transition_detail_cli_outputs_full_transition_data(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    explicit_skill_dir = tmp_path / "skills" / "custom_reporter"
    fallback_skill_dir = tmp_path / "skills" / "custom_audit"
    explicit_skill_dir.mkdir(parents=True)
    fallback_skill_dir.mkdir(parents=True)
    (explicit_skill_dir / "SKILL.md").write_text(
        "# explicit\n## name\ncustom_reporter\n## behavior_class\nobserve\n## description\n상태 보고서를 생성한다\n## when_to_use\n보고가 필요할 때\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    (fallback_skill_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## description\n워크스페이스 점검\n## when_to_use\n점검이 필요할 때\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    completed = subprocess.run(
        [sys.executable, script_path, "--transition-detail"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Transition Detail" in completed.stdout
    assert "- fallback_skills: custom_audit" in completed.stdout
    assert "- inconsistent_behavior_class_skills: custom_reporter" in completed.stdout
    assert "- strict_blockers: custom_audit, custom_reporter" in completed.stdout
    assert "- custom_reporter: class=observe, source=explicit, suggested=report, strict_blocker=True, reason=inconsistent_behavior_class" in completed.stdout
    assert "- custom_audit: class=report, source=fallback, suggested=report, strict_blocker=True, reason=missing_behavior_class" in completed.stdout


def test_inspect_storage_write_skill_template_cli_creates_file_safely(tmp_path):
    script_path = os.path.join(BASE_DIR, "inspect_storage.py")

    first = subprocess.run(
        [sys.executable, script_path, "--write-skill-template", "skills/custom_reporter"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, script_path, "--write-skill-template", "skills/custom_reporter"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert "- created: True" in first.stdout
    assert "- reason: created" in first.stdout
    assert "- suggested_behavior_class: report" in first.stdout
    assert "- created: False" in second.stdout
    assert "- reason: exists" in second.stdout
    created_file = tmp_path / "skills" / "custom_reporter" / "SKILL.md"
    assert created_file.exists()
    assert "## behavior_class\nreport" in created_file.read_text(encoding="utf-8")


def test_inspect_storage_write_risk_snapshot_cli_creates_timestamped_snapshot(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    script_path = os.path.join(BASE_DIR, "inspect_storage.py")

    first = subprocess.run(
        [sys.executable, script_path, "--write-risk-snapshot"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, script_path, "--write-risk-snapshot"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    snapshots = sorted((tmp_path / "reports").glob("risk_snapshot*.json"))
    assert first.returncode == 0
    assert second.returncode == 0
    assert len(snapshots) == 2
    assert "- saved: True" in first.stdout
    assert "- saved: True" in second.stdout
    assert "- requested_path:" in first.stdout


def test_inspect_storage_write_baseline_cli_resolves_missing_baseline(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    config_dir = tmp_path / "config"
    src_dir = tmp_path / "src"
    config_dir.mkdir()
    src_dir.mkdir()
    (config_dir / "prod.yaml").write_text("mode: prod\n", encoding="utf-8")
    (src_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")
    script_path = os.path.join(BASE_DIR, "inspect_storage.py")

    baseline_write = subprocess.run(
        [sys.executable, script_path, "--write-baseline"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    inspect_run = subprocess.run(
        [sys.executable, script_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert baseline_write.returncode == 0
    assert inspect_run.returncode == 0
    assert "Baseline Snapshot" in baseline_write.stdout
    assert "- saved: True" in baseline_write.stdout
    assert "- baseline_status: fresh" in inspect_run.stdout
    assert "- baseline_reason: fresh_snapshot" in inspect_run.stdout
    assert "- new_high_risk_paths: none" in inspect_run.stdout


def test_inspect_storage_export_transition_report_cli_writes_json_safely(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()
    memory.save()
    explicit_skill_dir = tmp_path / "skills" / "custom_reporter"
    fallback_skill_dir = tmp_path / "skills" / "custom_audit"
    explicit_skill_dir.mkdir(parents=True)
    fallback_skill_dir.mkdir(parents=True)
    (explicit_skill_dir / "SKILL.md").write_text(
        "# explicit\n## name\ncustom_reporter\n## behavior_class\nobserve\n## description\n상태 보고서를 생성한다\n## when_to_use\n보고가 필요할 때\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    (fallback_skill_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## description\n워크스페이스 점검\n## when_to_use\n점검이 필요할 때\n## steps\n1. scan\n",
        encoding="utf-8",
    )

    script_path = os.path.join(BASE_DIR, "inspect_storage.py")
    export_path = "reports/transition_report.json"
    first = subprocess.run(
        [sys.executable, script_path, "--export-transition-report", export_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, script_path, "--export-transition-report", export_path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    exported_file = tmp_path / "reports" / "transition_report.json"
    assert first.returncode == 0
    assert second.returncode == 0
    assert "- exported: True" in first.stdout
    assert "- reason: created" in first.stdout
    assert "- exported: False" in second.stdout
    assert "- reason: exists" in second.stdout
    payload = json.loads(exported_file.read_text(encoding="utf-8"))
    assert payload["fallback_skills"] == ["custom_audit"]
    assert payload["inconsistent_behavior_class_skills"] == ["custom_reporter"]


def test_loop_reads_strict_behavior_class_setting_off_and_keeps_fallback_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_NO_LLM", "1")
    skills_dir = tmp_path / "skills" / "custom_audit"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "agent": {"workspace": str(tmp_path), "memory_file": str(tmp_path / "agent_memory.json"), "max_cycles": 1},
        "skills": {"strict_behavior_class": False},
    }, ensure_ascii=False), encoding="utf-8")

    loop = AgentLoop(config_file=str(config_path))

    assert loop.strict_behavior_class is False
    assert [skill["name"] for skill in loop.skills] == ["custom_audit"]
    assert loop.skill_loader_diagnostics["fallback_skills"] == ["custom_audit"]


def test_loop_reads_strict_behavior_class_setting_on_and_fails_for_missing_behavior_class(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_NO_LLM", "1")
    skills_dir = tmp_path / "skills" / "custom_audit"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "# fallback\n## name\ncustom_audit\n## steps\n1. scan\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "agent": {"workspace": str(tmp_path), "memory_file": str(tmp_path / "agent_memory.json"), "max_cycles": 1},
        "skills": {"strict_behavior_class": True},
    }, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="strict behavior_class preflight failed"):
        AgentLoop(config_file=str(config_path))


def test_recent_scores_persist_and_trend_is_computed(tmp_path):
    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    memory.load()

    for idx, score in enumerate([70, 80, 90], start=1):
        memory.add_history({
            "cycle": idx,
            "action": {"type": "skill", "skill_name": f"skill_{idx}", "source": "planner"},
            "result": {"success": True, "output": f"event {idx}"},
            "evaluation": {"score": score, "status": "success"},
        })

    memory.save()

    state = json.loads((tmp_path / "agent_state.json").read_text(encoding="utf-8"))

    assert len(memory.data["recent_scores"]) == 3
    assert state["recent_scores"] == [70, 80, 90]
    assert state["trend"]["avg_score"] == 80.0
    assert state["trend"]["recent_scores"] == [70, 80, 90]
    assert state["trend"]["trend"] == "improving"


def test_load_recomputes_trend_from_recent_scores(tmp_path):
    state_path = tmp_path / "agent_state.json"
    state_path.write_text(json.dumps({
        "current_cycle": 3,
        "recent_actions": [],
        "recent_fallbacks": [],
        "recent_scores": [65, 70, 75],
        "trend": {"trend": "no_data", "avg_score": 0, "samples": 0},
        "last_run_at": "2026-03-21T00:00:00Z",
        "last_success_at": "2026-03-21T00:00:00Z",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "history").mkdir(exist_ok=True)
    (tmp_path / "history" / "history_current.jsonl").write_text("", encoding="utf-8")

    memory = Memory(filepath=str(tmp_path / "agent_memory.json"))
    data = memory.load()
    trend = memory.get_score_trend()

    assert data["recent_scores"] == [65, 70, 75]
    assert trend["avg_score"] == 70.0
    assert trend["recent_scores"] == [65, 70, 75]
    assert trend["trend"] != "no_data"
