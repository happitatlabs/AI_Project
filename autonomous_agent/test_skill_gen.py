#!/usr/bin/env python3
"""
test_skill_gen.py — LLM 기반 스킬 생성 검증 테스트

검증 항목:
  1) LLM 호출 주체가 로컬 Ollama(localhost)인지 확인
  2) 생성된 스킬 파일이 디스크에 실제 저장되는지 확인
  3) agent_trace.jsonl에 추적 로그 기록

출력:
  - generated_skills/skill_<timestamp>.md  : 생성된 스킬 파일
  - agent_trace.jsonl                       : 단계별 추적 로그
  - 최종 보고서 (stdout)
"""

import json
import os
import sys
import socket
import urllib.request
import urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.llm_adapter import LLMAdapter

# ── 경로 설정 ─────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE     = os.path.join(BASE_DIR, "config.json")
SIGNATURE_FILE  = os.path.join(BASE_DIR, "local_signature.txt")
TRACE_FILE      = os.path.join(BASE_DIR, "agent_trace.jsonl")
SKILLS_DIR      = os.path.join(BASE_DIR, "generated_skills")

os.makedirs(SKILLS_DIR, exist_ok=True)

# ── ANSI ──────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; E = "\033[0m"


# ════════════════════════════════════════════════════════
# 추적 로그 기록
# ════════════════════════════════════════════════════════
def trace(step: str, status: str, llm_provider: str = "", model: str = "",
          output_file: str = "", detail: str = "") -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "status": status,
        "llm_provider": llm_provider,
        "model": model,
        "output_file": output_file,
        "detail": detail,
    }
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ════════════════════════════════════════════════════════
# T1: Ollama 로컬 여부 확인
# ════════════════════════════════════════════════════════
def verify_local_ollama(adapter: LLMAdapter) -> dict:
    """
    Ollama가 실제로 localhost에서 실행 중인지 다층 검증.
    반환: {"is_local": bool, "method": str, "detail": str}
    """
    url = adapter.base_url
    hostname = url.split("://")[-1].split(":")[0]

    # 계층 1: base_url이 localhost/127.x 계열인지
    is_localhost_url = hostname in ("localhost", "127.0.0.1", "::1") or \
                       hostname.startswith("127.")

    # 계층 2: DNS 해석 결과가 루프백인지
    try:
        resolved = socket.gethostbyname(hostname)
        is_loopback_dns = resolved.startswith("127.") or resolved == "::1"
    except socket.gaierror:
        resolved = "해석 불가"
        is_loopback_dns = False

    # 계층 3: 실제 TCP 연결 시도 (포트 체크)
    port = int(url.split(":")[-1]) if ":" in url.split("://")[-1] else 11434
    try:
        sock = socket.create_connection((hostname, port), timeout=2)
        sock.close()
        tcp_reachable = True
    except (socket.timeout, ConnectionRefusedError, OSError):
        tcp_reachable = False

    # 계층 4: /api/tags HTTP 응답
    http_ok = adapter.is_available()

    detail = (
        f"url={url}, hostname={hostname}, resolved={resolved}, "
        f"is_localhost_url={is_localhost_url}, is_loopback_dns={is_loopback_dns}, "
        f"tcp_reachable={tcp_reachable}, http_ok={http_ok}"
    )

    is_local = is_localhost_url and is_loopback_dns
    method = "URL+DNS+TCP+HTTP 4계층 검증"

    return {
        "is_local": is_local,
        "is_running": tcp_reachable and http_ok,
        "method": method,
        "detail": detail,
        "hostname": hostname,
        "resolved": resolved,
        "tcp_reachable": tcp_reachable,
        "http_ok": http_ok,
    }


# ════════════════════════════════════════════════════════
# T2: 로컬 서명 파일 읽기
# ════════════════════════════════════════════════════════
def read_local_signature() -> str:
    if not os.path.exists(SIGNATURE_FILE):
        return "[local_signature.txt 없음]"
    with open(SIGNATURE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


# ════════════════════════════════════════════════════════
# T3: LLM으로 스킬 내용 생성
# ════════════════════════════════════════════════════════
SKILL_SYSTEM_PROMPT = """You are a skill generator for an autonomous agent system.
Generate a concise skill description in Korean.
Respond ONLY with a JSON object — no markdown, no explanation.

Schema:
{
  "skill_name": "스킬 이름 (영문, snake_case)",
  "description": "이 스킬이 하는 일 (한국어, 2-3 문장)",
  "trigger_keywords": ["트리거 키워드1", "키워드2"],
  "steps": ["단계1", "단계2", "단계3"]
}"""

SKILL_USER_PROMPT = """다음 목적의 스킬을 생성해줘:
목적: 워크스페이스의 파일을 유형별로 분류하고 요약 보고서를 작성하는 스킬
대상 에이전트: 자율 발전 에이전트 MVP
언어: 한국어로 설명 작성"""


def generate_skill_with_llm(adapter: LLMAdapter) -> dict:
    """LLM을 호출하여 스킬 정의 JSON을 생성."""
    response = adapter.chat(
        prompt=SKILL_USER_PROMPT,
        system=SKILL_SYSTEM_PROMPT,
        temperature=0.3,
    )

    if response is None:
        return {
            "success": False,
            "source": "llm_failed",
            "content": None,
            "raw": None,
            "error": adapter.get_last_error(),
        }

    parsed = adapter.parse_json_response(response)
    if parsed and isinstance(parsed, dict):
        return {
            "success": True,
            "source": "llm",
            "content": parsed,
            "raw": response,
        }

    # 파싱 실패 시 raw 텍스트로 저장
    return {
        "success": True,
        "source": "llm_raw",
        "content": {"description": response},
        "raw": response,
    }


def generate_skill_fallback() -> dict:
    """LLM 없을 때 사용하는 로컬 규칙 기반 스킬 생성."""
    return {
        "success": True,
        "source": "rules_fallback",
        "content": {
            "skill_name": "file_classifier",
            "description": (
                "워크스페이스의 파일을 확장자별로 분류하고 요약 보고서를 생성하는 스킬. "
                "파일 수, 총 크기, 유형별 분포를 분석하여 Markdown 형식으로 저장한다."
            ),
            "trigger_keywords": ["분류", "classify", "파일 정리", "요약"],
            "steps": [
                "워크스페이스를 재귀적으로 스캔한다",
                "확장자별로 파일을 그룹화한다",
                "각 그룹의 파일 수와 총 크기를 계산한다",
                "결과를 Markdown 보고서로 저장한다",
            ],
        },
        "raw": None,
    }


# ════════════════════════════════════════════════════════
# T4: 스킬 파일 디스크에 저장
# ════════════════════════════════════════════════════════
def save_skill_file(
    skill_data: dict,
    adapter: LLMAdapter,
    signature: str,
    llm_info: dict,
) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"skill_{ts}.md"
    filepath = os.path.join(SKILLS_DIR, filename)

    content = skill_data.get("content", {})
    source  = skill_data.get("source", "unknown")

    lines = [
        "# 자동 생성 스킬",
        "",
        "## 메타데이터",
        "```json",
        json.dumps({
            "generated_by": "test_skill_gen.py",
            "model":        adapter.model,
            "endpoint":     adapter.base_url,
            "llm_source":   source,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "is_local_llm": llm_info.get("is_local", False),
            "llm_running":  llm_info.get("is_running", False),
        }, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 스킬 정의",
        "",
    ]

    if isinstance(content, dict):
        if "skill_name" in content:
            lines.append(f"**이름:** `{content['skill_name']}`")
            lines.append("")
        if "description" in content:
            lines.append(f"**설명:** {content['description']}")
            lines.append("")
        if "trigger_keywords" in content:
            kws = ", ".join(f"`{k}`" for k in content["trigger_keywords"])
            lines.append(f"**트리거 키워드:** {kws}")
            lines.append("")
        if "steps" in content:
            lines.append("**실행 단계:**")
            for i, step in enumerate(content["steps"], 1):
                lines.append(f"{i}. {step}")
            lines.append("")
    else:
        lines.append(str(content))
        lines.append("")

    lines += [
        "---",
        "",
        "## 로컬 서명 (local_signature.txt)",
        "```",
        signature,
        "```",
        "",
        "## 생성 원본 (raw LLM output)",
        "```",
        skill_data.get("raw") or "(규칙 기반 생성 — LLM 미호출)",
        "```",
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ════════════════════════════════════════════════════════
# 추론 환경 판정
# ════════════════════════════════════════════════════════
def detect_inference_env(adapter: LLMAdapter, llm_info: dict) -> dict:
    """
    현재 추론이 로컬인지 클라우드인지 판정.

    판정 기준:
    - Ollama base_url이 localhost → LLM은 로컬
    - ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY 환경변수 → 오케스트레이션은 클라우드
    - 이 스크립트 자체는 Cowork VM(Linux)에서 실행됨
    """
    anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "")
    anthropic_key  = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    cowork_model   = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL", "")

    ollama_is_local   = llm_info.get("is_local", False)
    ollama_is_running = llm_info.get("is_running", False)

    if ollama_is_local and ollama_is_running:
        llm_verdict = "LOCAL (Ollama on localhost)"
    elif ollama_is_local and not ollama_is_running:
        llm_verdict = "LOCAL_CONFIGURED_BUT_OFFLINE (Ollama not running)"
    else:
        llm_verdict = "REMOTE (non-localhost endpoint)"

    orchestrator_verdict = (
        "CLOUD_COWORK (Anthropic API + Cowork VM)"
        if anthropic_base or cowork_model
        else "UNKNOWN"
    )

    return {
        "llm_inference":           llm_verdict,
        "orchestrator_inference":  orchestrator_verdict,
        "anthropic_base_url":      anthropic_base or "(not set)",
        "anthropic_key_present":   anthropic_key,
        "cowork_subagent_model":   cowork_model or "(not set)",
        "script_runtime":          "Cowork Linux VM (sandbox)",
    }


# ════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════
def main():
    print(f"\n{B}{C}{'═'*60}{E}")
    print(f"{B}{C}  LLM 스킬 생성 검증 테스트{E}")
    print(f"{B}{C}{'═'*60}{E}\n")

    # 기존 trace 초기화 (테스트 재실행 구분을 위해 구분자 추가)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "step": "TEST_START", "status": "ok",
                            "llm_provider": "", "model": "", "output_file": "",
                            "detail": "=== 새 테스트 실행 ==="}) + "\n")

    adapter = LLMAdapter.from_config(CONFIG_FILE)

    # ── STEP 1: Ollama 로컬 여부 검증 ──
    print(f"{C}[STEP 1] Ollama 로컬 여부 검증{E}")
    llm_info = verify_local_ollama(adapter)

    local_icon = f"{G}✅ 로컬{E}" if llm_info["is_local"] else f"{Y}⚠️  비로컬{E}"
    run_icon   = f"{G}✅ 실행 중{E}" if llm_info["is_running"] else f"{R}❌ 미실행{E}"
    print(f"  호스트 종류 : {local_icon}")
    print(f"  서버 상태   : {run_icon}")
    print(f"  hostname    : {llm_info['hostname']}  →  resolved: {llm_info['resolved']}")
    print(f"  TCP 연결    : {llm_info['tcp_reachable']}  |  HTTP /api/tags: {llm_info['http_ok']}")

    trace("verify_local_ollama",
          "local_running" if llm_info["is_running"] else
          ("local_offline" if llm_info["is_local"] else "remote"),
          llm_provider=adapter.provider,
          model=adapter.model,
          detail=llm_info["detail"])

    # ── STEP 2: 서명 파일 읽기 ──
    print(f"\n{C}[STEP 2] local_signature.txt 읽기{E}")
    signature = read_local_signature()
    sig_ok = "[local_signature.txt 없음]" not in signature
    sig_icon = f"{G}✅{E}" if sig_ok else f"{R}❌{E}"
    print(f"  {sig_icon}  {SIGNATURE_FILE}")
    if sig_ok:
        for line in signature.splitlines()[:3]:
            print(f"      {line}")

    trace("read_local_signature",
          "ok" if sig_ok else "missing",
          detail=f"path={SIGNATURE_FILE}, found={sig_ok}")

    # ── STEP 3: LLM 호출 or fallback ──
    print(f"\n{C}[STEP 3] 스킬 생성 (LLM or fallback){E}")

    if llm_info["is_running"]:
        print(f"  → {G}Ollama 연결됨{E}: {adapter.model} 호출 시도...")
        skill_data = generate_skill_with_llm(adapter)
    else:
        print(f"  → {Y}Ollama 미실행{E}: 규칙 기반 fallback으로 생성")
        skill_data = generate_skill_fallback()

    src_icon = f"{G}llm{E}" if skill_data["source"] == "llm" else f"{Y}{skill_data['source']}{E}"
    print(f"  source : {src_icon}")
    if skill_data["success"] and isinstance(skill_data["content"], dict):
        print(f"  이름   : {skill_data['content'].get('skill_name', '?')}")
        print(f"  설명   : {skill_data['content'].get('description', '')[:60]}...")

    trace("generate_skill",
          "llm_success" if (skill_data["success"] and skill_data["source"] == "llm")
          else ("fallback" if skill_data["success"] else "failed"),
          llm_provider=adapter.provider if skill_data["source"] == "llm" else "rules",
          model=adapter.model if skill_data["source"] == "llm" else "N/A",
          detail=f"source={skill_data['source']}, "
                 f"error={skill_data.get('error', '')}")

    # ── STEP 4: 스킬 파일 저장 ──
    print(f"\n{C}[STEP 4] 스킬 파일 디스크 저장{E}")
    skill_path = save_skill_file(skill_data, adapter, signature, llm_info)
    file_exists = os.path.exists(skill_path)
    file_size   = os.path.getsize(skill_path) if file_exists else 0

    save_icon = f"{G}✅{E}" if file_exists else f"{R}❌{E}"
    print(f"  {save_icon}  저장됨: {skill_path}")
    print(f"       크기: {file_size:,} bytes")

    trace("save_skill_file",
          "ok" if file_exists else "failed",
          llm_provider=adapter.provider,
          model=adapter.model,
          output_file=skill_path,
          detail=f"size={file_size}")

    # ── STEP 5: 추론 환경 판정 ──
    print(f"\n{C}[STEP 5] 추론 환경 판정{E}")
    env = detect_inference_env(adapter, llm_info)
    print(f"  LLM 추론      : {env['llm_inference']}")
    print(f"  오케스트레이터 : {env['orchestrator_inference']}")
    print(f"  스크립트 런타임: {env['script_runtime']}")
    print(f"  ANTHROPIC_BASE : {env['anthropic_base_url']}")
    print(f"  Cowork 모델    : {env['cowork_subagent_model']}")

    trace("detect_inference_env",
          "ok",
          detail=json.dumps(env, ensure_ascii=False))

    # ── 최종 보고서 ──
    print(f"\n{B}{C}{'═'*60}{E}")
    print(f"{B}  최종 보고서{E}")
    print(f"{B}{C}{'═'*60}{E}")
    print(f"\n  1) 생성 파일 경로:")
    print(f"     {skill_path}")
    print(f"\n  2) 로그 파일 경로:")
    print(f"     {TRACE_FILE}")
    print(f"\n  3) 로컬 LLM 호출 여부 확인 방법:")
    if llm_info["is_running"]:
        print(f"     {G}✅ Ollama가 localhost에서 실행 중이며 실제 호출됨{E}")
        print(f"        모델 : {adapter.model}")
        print(f"        확인 : `ollama ps` 로 현재 로딩된 모델 조회 가능")
        print(f"        확인 : agent_trace.jsonl의 llm_provider=ollama 항목 참조")
    else:
        print(f"     {Y}⚠️  Ollama 미실행 → 실제 LLM 호출 없음 (fallback 사용){E}")
        print(f"        Ollama 시작 후 다시 실행: ollama serve && python test_skill_gen.py")
    print(f"\n  4) 추론 환경 판정 결과:")
    print(f"     LLM(생성) : {env['llm_inference']}")
    print(f"     오케스트레이터: {env['orchestrator_inference']}")
    print(f"\n     → 이 에이전트는 {B}Cowork 클라우드 추론{E}으로 조율되며,")
    print(f"       스킬 생성 LLM은 {B}로컬 Ollama (localhost){E}를 사용하도록 설정됨.")
    print(f"       현재 Ollama 실행 상태: {'실행 중' if llm_info['is_running'] else '미실행'}\n")

    return 0 if file_exists else 1


if __name__ == "__main__":
    sys.exit(main())
