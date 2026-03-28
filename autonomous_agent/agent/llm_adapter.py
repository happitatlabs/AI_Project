"""
llm_adapter.py — LLM 호출 추상화 레이어

역할:
- config.json에서 provider/model/url 설정을 읽음
- Ollama /api/chat 엔드포인트로 요청을 보내고 응답 반환
- 연결 실패 시 명확한 에러 로그와 함께 None 반환
- provider 교체가 필요하면 이 파일만 수정하면 됨

지원 provider:
  - "ollama"  : http://localhost:11434/api/chat
  - (확장 가능: openai, anthropic 등)
"""

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

# 코드블록 패턴: ```json ... ``` 또는 ``` ... ```
_RE_CODE_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```")
# 단일 깊이 JSON 객체 패턴 (복수 객체 → 배열 복구용)
_RE_FLAT_OBJECTS = re.compile(r"\{[^{}]*\}")

logger = logging.getLogger("llm_adapter")


class LLMAdapter:
    """
    단일 파일에서 LLM 호출을 책임지는 어댑터.

    사용 예:
        adapter = LLMAdapter.from_config("config.json")
        response = adapter.chat("다음 행동을 결정해줘: ...")
        if response is None:
            # Ollama 미연결 → fallback 처리
    """

    def __init__(
        self,
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:9b",
        timeout: int = 60,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._last_error: str | None = None

    # ── 생성자 팩토리 ──────────────────────────────────

    @classmethod
    def from_config(cls, config_path: str = "config.json") -> "LLMAdapter":
        """config.json에서 LLM 설정을 읽어 어댑터를 생성."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            llm_cfg = cfg.get("llm", {})
            adapter = cls(
                provider=llm_cfg.get("provider", "ollama"),
                base_url=llm_cfg.get("base_url", "http://localhost:11434"),
                model=llm_cfg.get("model", "qwen3.5:9b"),
                timeout=llm_cfg.get("timeout", 60),
            )
            logger.info(
                f"[LLMAdapter] 설정 로드 완료: provider={adapter.provider}, "
                f"model={adapter.model}, base_url={adapter.base_url}"
            )
            return adapter
        except FileNotFoundError:
            logger.warning(f"[LLMAdapter] {config_path} 없음 → 기본값 사용")
            return cls()
        except json.JSONDecodeError as e:
            logger.error(f"[LLMAdapter] config.json 파싱 오류: {e}")
            return cls()

    # ── 핵심 메서드 ────────────────────────────────────

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> str | None:
        """
        단일 텍스트 prompt를 LLM에 보내고 응답 문자열을 반환.

        반환값:
          - str  : LLM 응답 텍스트
          - None : 연결 실패 또는 오류 (로그에 상세 기록됨)
        """
        if self.provider == "ollama":
            return self._call_ollama(prompt, system, temperature)
        else:
            logger.error(f"[LLMAdapter] 지원하지 않는 provider: {self.provider}")
            return None

    def is_available(self) -> bool:
        """Ollama 서버가 응답하는지 간단히 ping으로 확인."""
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    def get_last_error(self) -> str | None:
        """마지막으로 발생한 에러 메시지 반환."""
        return self._last_error

    # ── Ollama 구현 ────────────────────────────────────

    def _call_ollama(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
    ) -> str | None:
        """Ollama /api/chat 엔드포인트를 호출."""
        url = f"{self.base_url}/api/chat"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        start = datetime.now()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                content = data["message"]["content"]
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(
                    f"[LLMAdapter] 응답 수신 ({elapsed:.2f}s, "
                    f"{len(content)}자)"
                )
                return content

        except urllib.error.URLError as e:
            self._last_error = str(e)
            logger.error(
                f"[LLMAdapter] ❌ Ollama 연결 실패\n"
                f"  URL    : {url}\n"
                f"  Model  : {self.model}\n"
                f"  원인   : {e}\n"
                f"  해결책 : `ollama serve` 실행 후 "
                f"`ollama pull {self.model}` 확인"
            )
            return None

        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            self._last_error = f"HTTP {e.code}: {body_text}"
            logger.error(
                f"[LLMAdapter] ❌ HTTP 오류 {e.code}\n"
                f"  URL    : {url}\n"
                f"  응답   : {body_text[:300]}\n"
                f"  모델 '{self.model}'이 설치되어 있는지 확인: "
                f"`ollama list`"
            )
            return None

        except (json.JSONDecodeError, KeyError) as e:
            self._last_error = str(e)
            logger.error(f"[LLMAdapter] ❌ 응답 파싱 실패: {e}")
            return None

        except TimeoutError:
            self._last_error = f"timeout after {self.timeout}s"
            logger.error(
                f"[LLMAdapter] ❌ 응답 타임아웃 ({self.timeout}초)\n"
                f"  config.json의 llm.timeout 값을 늘려보세요."
            )
            return None

    # ── 유틸리티 ───────────────────────────────────────

    def parse_json_response(self, text: str) -> Any:
        """
        LLM 응답에서 JSON을 느슨하게 파싱.

        복구 전략 (순서대로 시도):
          1) ```json / ``` 코드블록 제거
          2) [ vs { 중 먼저 나오는 것으로 경계 결정
             - '[' 우선: 마지막 ']' 까지 추출 → 배열 파싱
             - '{' 우선: 마지막 '}' 까지 추출 → 객체 파싱
          3) 파싱 실패 + 복수 객체 패턴({...}{...}) → [] 로 감싸 재시도
          4) 최종 실패 → 원문 150자 로그 후 None 반환

        반환: list | dict | None
        """
        original = text

        # ── Step 1: 코드블록 제거 ───────────────────────────
        cb = _RE_CODE_BLOCK.search(text)
        if cb:
            text = cb.group(1).strip()

        # ── Step 2: [ vs { 경계 탐색 ──────────────────────
        first_sq = text.find("[")
        first_cu = text.find("{")

        if first_sq != -1 and (first_cu == -1 or first_sq < first_cu):
            # 배열 경계 우선 — [ 가 { 보다 먼저 나옴
            last = text.rfind("]")
            if last > first_sq:
                text = text[first_sq : last + 1]
        elif first_cu != -1:
            # 객체 경계 — { 가 먼저 나옴
            last = text.rfind("}")
            if last > first_cu:
                text = text[first_cu : last + 1]
        else:
            logger.warning(
                f"[LLMAdapter] JSON 경계 없음  원문(150자): {original[:150]!r}"
            )
            return None

        # ── Step 3: 파싱 시도 ─────────────────────────────
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # ── Step 4: 복수 객체 → 배열로 감싸 재시도 ─────────
        #   e.g. {"a":1}\n{"b":2}  →  [{"a":1},{"b":2}]
        objs = _RE_FLAT_OBJECTS.findall(text)
        if len(objs) >= 2:
            try:
                return json.loads("[" + ",".join(objs) + "]")
            except json.JSONDecodeError:
                pass

        logger.warning(
            f"[LLMAdapter] JSON 파싱 최종 실패\n  원문(150자): {original[:150]!r}"
        )
        return None
