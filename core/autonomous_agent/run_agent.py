#!/usr/bin/env python3
"""
run_agent.py — 자율 발전 에이전트 MVP 진입점

사용법:
    python run_agent.py                          # config.json 기반 실행
    python run_agent.py --cycles 10              # 사이클 수 오버라이드
    python run_agent.py --config my_config.json  # 다른 설정 파일 사용
    python run_agent.py --no-llm                 # LLM 비활성화 (규칙 기반)

모듈 구조:
    agent/
    ├── __init__.py     패키지 초기화
    ├── llm_adapter.py  Ollama /api/chat 호출 추상화
    ├── memory.py       상태 영속화 (agent_memory.json)
    ├── planner.py      LLM 기반 목표→행동 계획 + 규칙 fallback
    ├── executor.py     행동 실행 (분석/생성/정리/보고)
    ├── evaluator.py    결과 평가 및 추세 분석
    └── loop.py         메인 루프 (config 로드 + 사이클 관리)
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.loop import AgentLoop


def main():
    parser = argparse.ArgumentParser(description="자율 발전 에이전트 MVP")
    parser.add_argument("--config",    type=str,   default="config.json",
                        help="설정 파일 경로 (기본: config.json)")
    parser.add_argument("--cycles",    type=int,   default=None,
                        help="최대 사이클 수 (config.json의 agent.max_cycles 오버라이드)")
    parser.add_argument("--workspace", type=str,   default=None,
                        help="분석 대상 워크스페이스 (config 오버라이드)")
    parser.add_argument("--delay",     type=float, default=None,
                        help="사이클 간 지연(초) (config 오버라이드)")
    parser.add_argument("--no-llm",    action="store_true",
                        help="LLM 비활성화 → 규칙 기반으로만 실행")
    args = parser.parse_args()

    # --no-llm: 환경변수로 loop.py에 신호 전달 (config 파일 불변)
    if args.no_llm:
        os.environ["AGENT_NO_LLM"] = "1"

    try:
        agent = AgentLoop(
            config_file=args.config,
            workspace=args.workspace,
            max_cycles=args.cycles,
            cycle_delay=args.delay,
        )
        result = agent.run()

        print(f"\n📊 최종 요약:")
        print(f"  LLM 모드: {'ON' if result['llm_mode'] else 'OFF (fallback)'}")
        print(f"  사이클 수: {result['total_cycles']}")
        print(f"  평균 점수: {result['trend']['avg_score']}")
        print(f"  추세: {result['trend']['trend']}")
        print(f"  최근 점수: {result['trend'].get('recent_scores', [])}")
    except RuntimeError as e:
        print(f"\n❌ 에이전트 시작 실패: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
