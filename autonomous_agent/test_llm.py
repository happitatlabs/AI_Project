#!/usr/bin/env python3
"""
test_llm.py — Ollama LLM 연결 및 Planner 통합 테스트

사용법:
    python test_llm.py                   # 전체 테스트
    python test_llm.py --quick           # 연결 확인만
    python test_llm.py --config my.json  # 다른 설정 파일

테스트 항목:
  T1. Ollama 서버 ping
  T2. /api/tags 로 설치된 모델 목록 확인
  T3. /api/chat 으로 단순 응답 확인
  T4. JSON 구조화 응답 파싱 확인
  T5. Planner.analyze_gap LLM 경로 통합 테스트
  T6. Planner.pick_next_action LLM 경로 통합 테스트
"""

import argparse
import json
import sys
import os
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.llm_adapter import LLMAdapter
from agent.planner import Planner

# ── ANSI 색상 ────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

PASS = f"{GREEN}✅ PASS{RESET}"
FAIL = f"{RED}❌ FAIL{RESET}"
SKIP = f"{YELLOW}⏭  SKIP{RESET}"


def section(title: str) -> None:
    print(f"\n{CYAN}{'─' * 50}{RESET}")
    print(f"{CYAN}  {title}{RESET}")
    print(f"{CYAN}{'─' * 50}{RESET}")


def result_line(name: str, passed: bool | None, detail: str = "") -> None:
    icon = PASS if passed else (SKIP if passed is None else FAIL)
    detail_str = f"  → {detail}" if detail else ""
    print(f"  {icon}  {name}{detail_str}")


# ── T1: Ping ─────────────────────────────────────────
def test_ping(adapter: LLMAdapter) -> bool:
    section("T1: Ollama 서버 Ping")
    ok = adapter.is_available()
    result_line(
        "GET /api/tags",
        ok,
        f"{adapter.base_url}" if ok else f"실패: {adapter.get_last_error()}"
    )
    return ok


# ── T2: 모델 목록 ─────────────────────────────────────
def test_model_list(adapter: LLMAdapter) -> bool:
    section("T2: 설치된 모델 목록 확인")
    try:
        url = f"{adapter.base_url}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        print(f"  설치된 모델 ({len(models)}개): {models}")

        target = adapter.model
        found = any(m.startswith(target.split(":")[0]) for m in models)
        result_line(
            f"'{target}' 모델 확인",
            found,
            "설치됨" if found else f"미설치 → `ollama pull {target}` 실행 필요"
        )
        return found
    except Exception as e:
        result_line("모델 목록 조회", False, str(e))
        return False


# ── T3: 단순 chat ─────────────────────────────────────
def test_simple_chat(adapter: LLMAdapter) -> bool:
    section("T3: /api/chat 단순 응답 테스트")
    response = adapter.chat(
        prompt="1 + 1의 답을 숫자만 말해줘.",
        temperature=0.0,
    )
    if response is None:
        result_line("chat 응답", False, adapter.get_last_error())
        return False

    print(f"  응답 원문: {repr(response[:200])}")
    passed = len(response.strip()) > 0
    result_line("응답 수신", passed, f"{len(response)}자")
    return passed


# ── T4: JSON 응답 파싱 ────────────────────────────────
def test_json_response(adapter: LLMAdapter) -> bool:
    section("T4: JSON 구조화 응답 파싱 테스트")
    response = adapter.chat(
        prompt='다음 형식으로 응답해줘: {"status": "ok", "value": 42}',
        temperature=0.0,
    )
    if response is None:
        result_line("JSON 응답", False, adapter.get_last_error())
        return False

    print(f"  응답 원문: {repr(response[:300])}")
    parsed = adapter.parse_json_response(response)

    if parsed is None:
        result_line("JSON 파싱", False, "파싱 실패")
        return False

    result_line("JSON 파싱", True, json.dumps(parsed, ensure_ascii=False))
    return True


# ── T5: Planner.analyze_gap LLM ──────────────────────
def test_planner_gap(adapter: LLMAdapter) -> bool:
    section("T5: Planner.analyze_gap (LLM 경로)")
    planner = Planner(goal_file="agent_goal.md", llm=adapter)

    goals = [
        "현재 워크스페이스의 파일 구조를 분석한다",
        "분석 결과를 기반으로 상태 보고서를 생성한다",
    ]
    state = {
        "total_files": 12,
        "total_dirs": 3,
        "total_size_bytes": 48000,
        "files": ["run_agent.py", "config.json", "agent_goal.md"],
    }

    actions = planner.analyze_gap(goals, state)
    if not actions:
        result_line("행동 목록 생성", False, "빈 리스트")
        return False

    src = actions[0].get("source", "?")
    print(f"  행동 {len(actions)}개 (source: {src}):")
    for a in actions[:3]:
        print(f"    [{a['type']}] {a['description']}")
        if a.get("reason"):
            print(f"           이유: {a['reason']}")

    passed = src == "llm"
    result_line("LLM 경로 사용 확인", passed, f"source={src}")
    return passed


# ── T6: Planner.pick_next_action LLM ─────────────────
def test_planner_pick(adapter: LLMAdapter) -> bool:
    section("T6: Planner.pick_next_action (LLM 경로)")
    planner = Planner(goal_file="agent_goal.md", llm=adapter)

    actions = [
        {"type": "analyze",  "description": "파일 구조 분석",   "goal": "분석", "priority": 1, "reason": ""},
        {"type": "report",   "description": "보고서 생성",      "goal": "기록", "priority": 3, "reason": ""},
        {"type": "organize", "description": "빈 폴더 정리 제안", "goal": "정리", "priority": 2, "reason": ""},
    ]
    history = [
        {
            "action": {"type": "analyze", "description": "파일 구조 분석"},
            "evaluation": {"score": 70, "status": "success"},
        }
    ]

    picked = planner.pick_next_action(actions, history)
    if picked is None:
        result_line("행동 선택", False, "None 반환")
        return False

    src = picked.get("source", "?")
    print(f"  선택된 행동: [{picked['type']}] {picked['description']}")
    if picked.get("reason"):
        print(f"  이유: {picked['reason']}")
    print(f"  source: {src}")

    passed = src == "llm"
    result_line("LLM 경로 사용 확인", passed, f"source={src}")
    return passed


# ── 메인 ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="LLM 어댑터 테스트")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--quick",  action="store_true", help="T1만 실행")
    args = parser.parse_args()

    adapter = LLMAdapter.from_config(args.config)
    print(f"\n테스트 대상: {adapter.model} @ {adapter.base_url}")

    results = {}

    # T1은 항상 실행
    results["T1_ping"] = test_ping(adapter)

    if not results["T1_ping"]:
        print(f"\n{RED}Ollama 서버에 연결할 수 없습니다.{RESET}")
        print(f"  1. 터미널에서 `ollama serve` 실행")
        print(f"  2. `ollama pull {adapter.model}` 로 모델 다운로드")
        print(f"  3. 이 테스트를 다시 실행")
        _print_summary(results)
        return 1

    if args.quick:
        _print_summary(results)
        return 0

    results["T2_models"]      = test_model_list(adapter)
    results["T3_chat"]        = test_simple_chat(adapter)
    results["T4_json"]        = test_json_response(adapter)
    results["T5_planner_gap"] = test_planner_gap(adapter)
    results["T6_planner_pick"]= test_planner_pick(adapter)

    return 0 if _print_summary(results) else 1


def _print_summary(results: dict) -> bool:
    section("테스트 결과 요약")
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    total  = len(results)
    for name, ok in results.items():
        result_line(name, ok)
    print(f"\n  합계: {passed}/{total} 통과, {failed} 실패")
    all_ok = failed == 0
    status = f"{GREEN}ALL PASS{RESET}" if all_ok else f"{RED}SOME FAILED{RESET}"
    print(f"  상태: {status}\n")
    return all_ok


if __name__ == "__main__":
    sys.exit(main())
