import argparse
import json
from pathlib import Path

from agent.execution_mode import add_experimental_sandbox_flags, normalize_execution_flags
from agent.sandbox_task_loop import run_sandbox_task_once


def _load_mock_inputs(path: str | None) -> dict:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mock input file must contain a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single sandbox task selection/execution step",
    )
    parser.add_argument("--task", required=True, help="Task description for skill selection")
    parser.add_argument("--sandbox-root", required=True, help="Temp-dir sandbox root")
    parser.add_argument("--reference", help="Reference path for runtime-data resolution")
    parser.add_argument("--skills-dir", help="Optional builtin skills directory")
    parser.add_argument(
        "--mock-input-file",
        help="Optional JSON file used as sandbox mock_inputs",
    )
    return add_experimental_sandbox_flags(parser)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_sandbox_task_once(
        task_description=args.task,
        sandbox_root=args.sandbox_root,
        reference=args.reference,
        skills_dir=args.skills_dir,
        execution_flags=normalize_execution_flags(args),
        mock_inputs=_load_mock_inputs(args.mock_input_file),
    )

    proposal = result["proposal"]["proposal"]
    task_result = result["task_result"]["task_result"]
    print(json.dumps({
        "run_id": proposal.get("run_id"),
        "selected_skill": proposal.get("selection", {}).get("selected_skill"),
        "selection_confidence": proposal.get("selection", {}).get("confidence"),
        "risk_level": (proposal.get("risk_summary") or {}).get("risk_level"),
        "recommended_path": (proposal.get("risk_summary") or {}).get("recommended_path"),
        "risk_confidence": (proposal.get("risk_summary") or {}).get("confidence"),
        "sandbox_result": task_result.get("sandbox_result"),
        "result_summary": task_result.get("result_summary"),
        "proposal_path": result["proposal"].get("path"),
        "task_history_path": result["task_result"].get("path"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
