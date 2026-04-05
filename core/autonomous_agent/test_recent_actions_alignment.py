import os
import sys
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from agent.executor import Executor
from agent.evaluator import Evaluator
from agent.memory import is_skill_on_cooldown, summarize_recent_actions
from agent.planner import Planner


def _utc_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_recent_actions_are_normalized_to_utc_z():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {
            "skill": "workspace_reporter",
            "executed_at": (now - timedelta(minutes=10)).isoformat(),
        }
    ]

    summary = summarize_recent_actions(recent_actions)

    assert summary[0]["executed_at"].endswith("Z")
    assert summary[0]["cooldown_until"].endswith("Z")
    assert summary[0]["on_cooldown"] is True


def test_planner_and_loop_share_same_cooldown_rule():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {
            "skill": "workspace_reporter",
            "executed_at": _utc_z(now - timedelta(minutes=5)),
        }
    ]
    skills = [
        {
            "name": "workspace_reporter",
            "description": "워크스페이스 상태 보고서를 생성한다",
            "when_to_use": "상태 보고서가 필요할 때",
        },
        {
            "name": "file_classifier",
            "description": "파일을 분류하고 요약 보고서를 만든다",
            "when_to_use": "분류 보고서가 필요할 때",
        },
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 상태 보고서를 생성한다"],
        current_state={"total_files": 3, "total_dirs": 1},
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert is_skill_on_cooldown("workspace_reporter", recent_actions) is True
    assert picked["skill"] == "file_classifier"


def test_all_cooldown_skills_choose_report_only_fallback():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=8))},
    ]
    skills = [
        {
            "name": "workspace_reporter",
            "description": "워크스페이스 상태 보고서를 생성한다",
            "when_to_use": "상태 보고서가 필요할 때",
        },
        {
            "name": "file_classifier",
            "description": "파일을 분류하고 정리 보고서를 만든다",
            "when_to_use": "분류 또는 정리 보고서가 필요할 때",
        },
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 워크스페이스 상태를 요약 보고서로 기록한다"],
        current_state={"total_files": 12, "total_dirs": 4},
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] is None
    assert picked["fallback"] == "report_only"
    assert picked["action"]["type"] == "report"


def test_fallback_diversity_avoids_repeating_report_only():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=8))},
        {"skill": "report_only", "executed_at": _utc_z(now - timedelta(minutes=2))},
    ]
    skills = [
        {
            "name": "workspace_reporter",
            "description": "워크스페이스 상태 보고서를 생성한다",
            "when_to_use": "상태 보고서가 필요할 때",
        },
        {
            "name": "file_classifier",
            "description": "파일을 분류하고 정리 보고서를 만든다",
            "when_to_use": "분류 또는 정리 보고서가 필요할 때",
        },
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 워크스페이스 상태를 요약 보고서로 기록한다"],
        current_state={"total_files": 12, "total_dirs": 4},
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] is None
    assert picked["fallback"] != "report_only"
    assert picked["fallback"] in {"change_summarizer", "memory_analyzer", "create", "wait", "noop"}


def test_create_output_contains_required_sections(tmp_path):
    (tmp_path / "notes.txt").write_text("sample", encoding="utf-8")
    executor = Executor(workspace=str(tmp_path))

    result = executor.execute({
        "type": "create",
        "description": "기본 초안 생성",
        "goal": "현재 상태를 바탕으로 초안을 만든다",
    })

    created_path = tmp_path / result["created_file"]
    content = created_path.read_text(encoding="utf-8")

    assert "## 요약" in content
    assert "## 현재 상태" in content
    assert "## 다음 액션 제안" in content


def test_memory_analyzer_contains_problems_and_improvements(tmp_path):
    executor = Executor(workspace=str(tmp_path))
    now = datetime.now(timezone.utc)

    result = executor.execute({
        "type": "memory_analyzer",
        "description": "최근 행동 분석 생성",
        "recent_history": [
            {
                "action": {"type": "report", "description": "상태 보고"},
                "evaluation": {"status": "partial"},
            },
            {
                "action": {"type": "report", "description": "상태 보고"},
                "evaluation": {"status": "failure"},
            },
            {
                "action": {"type": "create", "description": "초안 생성"},
                "evaluation": {"status": "success"},
            },
        ],
        "recent_actions": [
            {"skill": "report_only", "executed_at": _utc_z(now - timedelta(minutes=1))},
            {"skill": "report_only", "executed_at": _utc_z(now - timedelta(minutes=2))},
            {"skill": "change_summarizer", "executed_at": _utc_z(now - timedelta(minutes=3))},
            {"skill": "memory_analyzer", "executed_at": _utc_z(now - timedelta(minutes=4))},
            {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        ],
    })

    content = (tmp_path / result["report_file"]).read_text(encoding="utf-8")

    assert "## 문제점" in content
    assert "## 개선 제안" in content
    assert content.count("- ") >= 5


def test_change_summarizer_skips_when_no_file_change(tmp_path):
    executor = Executor(workspace=str(tmp_path))
    state = {"files": ["a.txt"], "total_files": 1, "total_dirs": 0, "total_size_bytes": 1}

    result = executor.execute({
        "type": "change_summarizer",
        "description": "변화 요약 생성",
        "current_state_snapshot": state,
        "previous_state_snapshot": state,
    })

    assert result["report_skipped"] is True
    assert "skipped" in result["output"]


def test_report_only_keeps_latest_single_report(tmp_path):
    executor = Executor(workspace=str(tmp_path))

    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    first = executor.execute({"type": "report", "description": "상태 요약 생성"})
    assert "generated" in first["output"]

    (tmp_path / "b.txt").write_text("v2", encoding="utf-8")
    second = executor.execute({"type": "report", "description": "상태 요약 생성"})
    assert "generated" in second["output"]

    reports = list((tmp_path / "reports").glob("report_*.md"))
    assert len(reports) == 1


def test_memory_analyzer_skips_when_recent_actions_under_threshold(tmp_path):
    executor = Executor(workspace=str(tmp_path))

    result = executor.execute({
        "type": "memory_analyzer",
        "description": "최근 행동 분석 생성",
        "recent_history": [],
        "recent_actions": [{"skill": "report_only", "executed_at": _utc_z(datetime.now(timezone.utc))}],
    })

    assert result["report_skipped"] is True
    assert "skipped" in result["output"]


def test_planner_reopens_one_skill_when_all_cooldown_and_external_change_exists():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "code_reviewer", "executed_at": _utc_z(now - timedelta(minutes=5))},
    ]
    skills = [
        {"name": "workspace_reporter", "description": "워크스페이스 상태 보고", "when_to_use": "상태 보고"},
        {"name": "file_classifier", "description": "파일 분류", "when_to_use": "파일 분류"},
        {"name": "code_reviewer", "description": "코드 리뷰", "when_to_use": "코드 리뷰"},
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 상태를 다시 점검한다"],
        current_state={
            "total_files": 10,
            "total_dirs": 2,
            "state_diff": {"external_changed": True, "self_artifact_changed": False},
            "recent_history": [{"event": "fallback"}],
        },
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] == "workspace_reporter"
    assert picked["source"] == "cooldown_reopen"
    assert "reopen_score=" in picked["reason"]


def test_planner_blocks_same_skill_even_when_cooldown_expired():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=30))},
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=11))},
    ]
    skills = [
        {"name": "workspace_reporter", "description": "워크스페이스 상태 보고서를 생성한다", "when_to_use": "상태 보고서가 필요할 때"},
        {"name": "file_classifier", "description": "파일을 분류한다", "when_to_use": "분류가 필요할 때"},
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 파일을 분류한다"],
        current_state={"total_files": 3, "total_dirs": 1, "state_diff": {}, "recent_history": []},
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] == "file_classifier"


def test_planner_does_not_reopen_without_signal():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "code_reviewer", "executed_at": _utc_z(now - timedelta(minutes=5))},
    ]
    skills = [
        {"name": "workspace_reporter", "description": "워크스페이스 상태 보고", "when_to_use": "상태 보고"},
        {"name": "file_classifier", "description": "파일 분류", "when_to_use": "파일 분류"},
        {"name": "code_reviewer", "description": "코드 리뷰", "when_to_use": "코드 리뷰"},
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["현재 워크스페이스 상태를 요약 보고서로 기록한다"],
        current_state={
            "total_files": 12,
            "total_dirs": 4,
            "state_diff": {"external_changed": False, "self_artifact_changed": False},
            "recent_history": [],
        },
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] is None
    assert picked["source"] == "fallback"


def test_planner_reopens_when_high_certainty_risk_requires_review():
    now = datetime.now(timezone.utc)
    recent_actions = [
        {"skill": "workspace_reporter", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "file_classifier", "executed_at": _utc_z(now - timedelta(minutes=5))},
        {"skill": "code_reviewer", "executed_at": _utc_z(now - timedelta(minutes=5))},
    ]
    skills = [
        {"name": "workspace_reporter", "description": "워크스페이스 상태 보고", "when_to_use": "상태 보고"},
        {"name": "file_classifier", "description": "파일 분류", "when_to_use": "파일 분류"},
        {"name": "code_reviewer", "description": "코드 리뷰", "when_to_use": "코드 리뷰"},
    ]
    planner = Planner(llm=None)

    picked = planner.pick_skill(
        goals=["위험한 변경을 다시 점검한다"],
        current_state={
            "total_files": 10,
            "total_dirs": 2,
            "state_diff": {"external_changed": False, "self_artifact_changed": False},
            "recent_history": [],
            "operational_signal": {
                "risk_action": "REVIEW_REQUIRED",
                "risk_certainty": "HIGH",
                "baseline_status": "fresh",
                "baseline_reason": "fresh_snapshot",
                "blocker_candidate": "risk:REVIEW_REQUIRED(config/prod.yaml)",
            },
        },
        available_skills=skills,
        recent_actions=recent_actions,
    )

    assert picked["skill"] == "workspace_reporter"
    assert picked["source"] == "cooldown_reopen"


def test_evaluator_rewards_external_change_and_normal_skill():
    evaluator = Evaluator()

    evaluation = evaluator.evaluate(
        {"type": "skill", "skill_name": "workspace_reporter", "action_source": "normal"},
        {
            "success": True,
            "output": "새 분석 결과와 구체 경로를 포함한 보고서",
            "elapsed_seconds": 0.2,
            "meta": {
                "action_source": "normal",
                "is_normal_skill": True,
                "output_created": True,
                "new_insight": True,
                "specific_findings": True,
                "external_changed": True,
                "decision_changed": True,
                "self_artifact_changed": False,
                "work_type": "workspace_reporter",
                "work_type_changed": True,
                "recent_fallback_count": 0,
            },
        },
        {},
    )

    assert evaluation["score"] >= 75
    assert evaluation["grade"] in {"high-value success", "useful success"}


def test_evaluator_penalizes_self_artifact_only_output():
    evaluator = Evaluator()

    evaluation = evaluator.evaluate(
        {"type": "report", "fallback_kind": "report_only", "action_source": "fallback"},
        {
            "success": True,
            "output": "report generated",
            "elapsed_seconds": 0.2,
            "meta": {
                "action_source": "fallback",
                "is_normal_skill": False,
                "output_created": True,
                "new_insight": False,
                "specific_findings": False,
                "external_changed": False,
                "decision_changed": False,
                "self_artifact_changed": True,
                "work_type": "report_only",
                "work_type_changed": False,
                "recent_fallback_count": 2,
            },
        },
        {},
    )

    assert evaluation["score"] < 70


def test_evaluator_penalizes_skipped_results():
    evaluator = Evaluator()

    evaluation = evaluator.evaluate(
        {"type": "change_summarizer", "action_source": "fallback"},
        {
            "success": True,
            "output": "no change -> skipped",
            "elapsed_seconds": 0.1,
            "report_skipped": True,
            "meta": {
                "action_source": "fallback",
                "is_skip_or_noop": True,
                "output_created": False,
                "new_insight": False,
                "specific_findings": False,
                "external_changed": False,
                "decision_changed": False,
                "self_artifact_changed": False,
                "work_type": "change_summarizer",
                "work_type_changed": False,
                "recent_fallback_count": 2,
            },
        },
        {},
    )

    assert evaluation["score"] < 55


def test_evaluator_penalizes_repeated_fallback_more_than_normal_skill():
    evaluator = Evaluator()

    fallback_eval = evaluator.evaluate(
        {"type": "report", "fallback_kind": "report_only", "action_source": "fallback"},
        {
            "success": True,
            "output": "fallback report",
            "elapsed_seconds": 0.1,
            "meta": {
                "action_source": "fallback",
                "output_created": True,
                "new_insight": False,
                "specific_findings": False,
                "external_changed": False,
                "decision_changed": False,
                "self_artifact_changed": True,
                "work_type": "report_only",
                "work_type_changed": False,
                "recent_fallback_count": 2,
            },
        },
        {},
    )
    skill_eval = evaluator.evaluate(
        {"type": "skill", "skill_name": "file_classifier", "action_source": "normal"},
        {
            "success": True,
            "output": "file classifier report",
            "elapsed_seconds": 0.1,
            "meta": {
                "action_source": "normal",
                "is_normal_skill": True,
                "output_created": True,
                "new_insight": True,
                "specific_findings": True,
                "external_changed": False,
                "decision_changed": False,
                "self_artifact_changed": False,
                "work_type": "file_classifier",
                "work_type_changed": True,
                "recent_fallback_count": 0,
            },
        },
        {},
    )

    assert fallback_eval["score"] < skill_eval["score"]


def test_planner_operational_gate_filters_by_behavior_class():
    planner = Planner(llm=None)
    skills = [
        {
            "name": "workspace_reporter",
            "description": "워크스페이스 상태 보고",
            "when_to_use": "상태 보고",
            "behavior_class": "observe",
        },
        {
            "name": "code_reviewer",
            "description": "코드 리뷰",
            "when_to_use": "위험 파일 검토",
            "behavior_class": "review",
        },
        {
            "name": "script_writer",
            "description": "스크립트 작성",
            "when_to_use": "자동 수정",
            "behavior_class": "write",
        },
        {
            "name": "command_runner",
            "description": "명령 실행",
            "when_to_use": "실행 검증",
            "behavior_class": "execute",
        },
    ]

    observe_only = planner.apply_operational_gate(skills, {"operational_gate": {"mode": "observe_only"}})
    blocked = planner.apply_operational_gate(skills, {"operational_gate": {"mode": "blocked"}})
    review_allowed = planner.apply_operational_gate(skills, {"operational_gate": {"mode": "review_allowed"}})
    ignore_mode = planner.apply_operational_gate(skills, {"operational_gate": {"mode": "ignore"}})

    assert [skill["name"] for skill in observe_only] == ["workspace_reporter"]
    assert [skill["name"] for skill in blocked] == ["workspace_reporter"]
    assert [skill["name"] for skill in review_allowed] == ["workspace_reporter", "code_reviewer"]
    assert [skill["name"] for skill in ignore_mode] == ["workspace_reporter"]
