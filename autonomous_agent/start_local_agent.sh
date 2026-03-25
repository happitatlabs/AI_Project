#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# start_local_agent.sh — 로컬 에이전트 통합 실행 스크립트
#
# 사용법:
#   ./start_local_agent.sh daemon      # 상시 실행 데몬 시작
#   ./start_local_agent.sh daemon-once # 1사이클만 실행
#   ./start_local_agent.sh status      # 데몬 실행 여부 확인
#   ./start_local_agent.sh stop        # 데몬 중지 (SIGTERM)
#   ./start_local_agent.sh maintenance # 유지보수 전체 실행
#   ./start_local_agent.sh test        # LLM 연결 테스트
#   ./start_local_agent.sh run         # 레거시: run_agent.py 직접 실행
#   ./start_local_agent.sh run --cycles 10  # 사이클 수 지정
# ══════════════════════════════════════════════════════════════

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; B='\033[1m'; NC='\033[0m'

banner() {
    echo -e "${C}══════════════════════════════════════════════════════${NC}"
    echo -e "${C}  자율 발전 에이전트 — 통합 실행 스크립트${NC}"
    echo -e "${C}══════════════════════════════════════════════════════${NC}"
}

# ── Python 확인 ──────────────────────────────────────────────
detect_python() {
    for py in python3 python; do
        if command -v "$py" &>/dev/null; then
            echo "$py"; return
        fi
    done
    echo -e "${R}❌ Python을 찾을 수 없습니다.${NC}" >&2; exit 1
}
PYTHON=$(detect_python)

# ── Ollama 상태 출력 (경고만, 중단하지 않음) ────────────────
check_ollama() {
    MODEL=$(${PYTHON} -c "import json; print(json.load(open('config.json'))['llm']['model'])" 2>/dev/null || echo "qwen3.5:9b")
    URL=$(${PYTHON} -c "import json; print(json.load(open('config.json'))['llm']['base_url'])" 2>/dev/null || echo "http://localhost:11434")
    if curl -sf "${URL}/api/tags" -o /dev/null 2>/dev/null; then
        echo -e "${G}✅ Ollama OK${NC} — ${MODEL} @ ${URL}"
    else
        echo -e "${Y}⚠️  Ollama 미응답${NC} (${URL}) — fallback 모드로 실행됩니다"
    fi
}

CMD="${1:-help}"
shift || true   # 나머지 인자를 스크립트로 전달

banner
echo -e "Python: $(${PYTHON} --version 2>&1)"
check_ollama
echo ""

case "$CMD" in
    daemon)
        echo -e "${C}[모드] Daemon — 상시 실행 (Ctrl+C로 중지)${NC}"
        exec ${PYTHON} run_daemon.py "$@"
        ;;
    daemon-once|once)
        echo -e "${C}[모드] 1사이클 실행${NC}"
        ${PYTHON} run_daemon.py --once "$@"
        ;;
    status)
        ${PYTHON} run_daemon.py --status
        ;;
    stop)
        PID_FILE="agent.pid"
        if [ ! -f "$PID_FILE" ]; then
            echo -e "${Y}PID 파일 없음 — 데몬이 실행 중이 아닐 수 있습니다.${NC}"
            exit 0
        fi
        PID=$(cat "$PID_FILE")
        echo -e "데몬 중지 중... (PID ${PID})"
        kill -TERM "$PID" 2>/dev/null && echo -e "${G}✅ SIGTERM 전송 완료${NC}" || \
            echo -e "${Y}프로세스 없음 (이미 종료됨?)${NC}"
        ;;
    maintenance|maint)
        echo -e "${C}[모드] 유지보수 전체 실행${NC}"
        ${PYTHON} run_maintenance.py "$@"
        ;;
    test)
        echo -e "${C}[모드] LLM 연결 테스트${NC}"
        ${PYTHON} test_llm.py "$@"
        ;;
    run)
        echo -e "${C}[모드] 에이전트 직접 실행 (run_agent.py)${NC}"
        ${PYTHON} run_agent.py "$@"
        ;;
    help|--help|-h|*)
        echo "사용법:"
        echo "  ./start_local_agent.sh daemon          # 상시 실행 데몬"
        echo "  ./start_local_agent.sh daemon-once     # 1사이클 후 종료"
        echo "  ./start_local_agent.sh status          # 데몬 실행 여부"
        echo "  ./start_local_agent.sh stop            # 데몬 중지"
        echo "  ./start_local_agent.sh maintenance     # 유지보수 실행"
        echo "  ./start_local_agent.sh test            # LLM 연결 테스트"
        echo "  ./start_local_agent.sh run [--cycles N]# 직접 실행"
        ;;
esac
