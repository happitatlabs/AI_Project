import os
import re
import json
import logging
import hashlib
import requests
import urllib.parse
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

_DEFAULT_MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"

def _is_emergency_lockdown() -> bool:
    v = os.getenv("MELLOW_EMERGENCY_LOCKDOWN")
    if not isinstance(v, str):
        return False
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_moltbook_api_base(raw: str) -> str:
    """
    Moltbook API base URL 정규화.
    - moltbook.com → www.moltbook.com (리다이렉트/Authorization 헤더 드롭 회피)
    - 흔한 오타 보정
    - /api/v1 누락 시 자동 보정
    """
    s = (raw or "").strip()
    if not s:
        return _DEFAULT_MOLTBOOK_API_BASE

    s = s.replace("moltboook.com", "moltbook.com")
    s = s.replace("moltbook.ccom", "moltbook.com")

    if "://" not in s:
        s = "https://" + s

    s = s.rstrip("/")

    try:
        parsed = urllib.parse.urlsplit(s)
        netloc = parsed.netloc
        if netloc == "moltbook.com":
            parsed = parsed._replace(netloc="www.moltbook.com")
            s = urllib.parse.urlunsplit(parsed).rstrip("/")
    except Exception:
        pass

    # /api/v1 보정
    if not s.endswith("/api/v1"):
        if s.endswith("/api"):
            s = s + "/v1"
        else:
            s = s + "/api/v1"

    return s


class SecurityAuditor:
    """
    API 응답 데이터에서 악성 스크립트/패턴을 탐지하는 방어적 보안 감사 모듈.

    탐지 대상:
      - 코드 인젝션 패턴 (eval, exec, subprocess, os.system 등)
      - 스크립트 태그 및 XSS 벡터
      - 인코딩 난독화 (base64, hex escape 등)
      - 쉘 커맨드 인젝션 패턴
      - 의심스러운 URL/네트워크 접근 패턴
      - 파일시스템 탈출 시도 (path traversal)
    """

    # --- 탐지 규칙 정의 ---

    CODE_INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r'\b(eval|exec|compile)\s*\(', re.IGNORECASE),
        re.compile(r'\b(subprocess|os\.system|os\.popen|commands\.getoutput)\s*\(', re.IGNORECASE),
        re.compile(r'__import__\s*\('),
        re.compile(r'\bimport\s+(os|sys|subprocess|shutil|ctypes|socket)\b'),
        re.compile(r'getattr\s*\(.+?,\s*["\']__'),  # getattr(obj, '__class__') 등
        re.compile(r'\bopen\s*\(\s*["\']/(etc|proc|dev|tmp)', re.IGNORECASE),
    ]

    SCRIPT_INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r'<\s*script[\s>]', re.IGNORECASE),
        re.compile(r'javascript\s*:', re.IGNORECASE),
        re.compile(r'on(load|error|click|mouseover)\s*=', re.IGNORECASE),
        re.compile(r'<\s*iframe[\s>]', re.IGNORECASE),
        re.compile(r'document\.(cookie|location|write)', re.IGNORECASE),
    ]

    OBFUSCATION_PATTERNS: List[re.Pattern] = [
        re.compile(r'\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){3,}'),  # 연속 hex escape
        re.compile(r'base64\.(b64decode|decodebytes)\s*\(', re.IGNORECASE),
        re.compile(r'codecs\.(decode|encode)\s*\('),
        re.compile(r'atob\s*\(', re.IGNORECASE),
        re.compile(r'String\.fromCharCode\s*\(', re.IGNORECASE),
    ]

    SHELL_PATTERNS: List[re.Pattern] = [
        re.compile(r';\s*(rm|curl|wget|chmod|sh|bash|powershell|cmd)\b', re.IGNORECASE),
        re.compile(r'\|\s*(sh|bash|zsh|cmd)\b', re.IGNORECASE),
        re.compile(r'`[^`]*(rm|curl|wget|nc|ncat)[^`]*`'),
        re.compile(r'\$\([^)]*(rm|curl|wget|nc)[^)]*\)'),
    ]

    NETWORK_PATTERNS: List[re.Pattern] = [
        re.compile(r'(urllib|requests|http\.client|socket)\.(get|post|urlopen|connect)\s*\(', re.IGNORECASE),
        re.compile(r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),  # raw IP URL
    ]

    PATH_TRAVERSAL_PATTERNS: List[re.Pattern] = [
        re.compile(r'\.\.[/\\]'),
        re.compile(r'[/\\](etc|proc|sys|dev|tmp|var)[/\\]', re.IGNORECASE),
        re.compile(r'%2e%2e[%2f/\\]', re.IGNORECASE),  # URL-encoded traversal
    ]

    SEVERITY_CRITICAL = "CRITICAL"
    SEVERITY_HIGH = "HIGH"
    SEVERITY_MEDIUM = "MEDIUM"

    RULE_GROUPS = [
        ("code_injection",   CODE_INJECTION_PATTERNS,   SEVERITY_CRITICAL),
        ("script_injection", SCRIPT_INJECTION_PATTERNS,  SEVERITY_HIGH),
        ("obfuscation",      OBFUSCATION_PATTERNS,       SEVERITY_HIGH),
        ("shell_injection",  SHELL_PATTERNS,             SEVERITY_CRITICAL),
        ("network_access",   NETWORK_PATTERNS,           SEVERITY_MEDIUM),
        ("path_traversal",   PATH_TRAVERSAL_PATTERNS,    SEVERITY_HIGH),
    ]

    def __init__(self, *, block_on_critical: bool = True):
        """
        Args:
            block_on_critical: True이면 CRITICAL 탐지 시 데이터 저장을 차단.
        """
        self.block_on_critical = block_on_critical

    # --- 핵심 스캔 로직 ---

    def scan(self, data: Any) -> "AuditReport":
        """
        임의의 데이터(dict, list, str 등)를 재귀적으로 순회하며 악성 패턴을 탐지.
        Returns: AuditReport with all findings.
        """
        findings: List[Dict[str, str]] = []
        self._scan_recursive(data, path="$", findings=findings)
        return AuditReport(findings=findings)

    def _scan_recursive(self, data: Any, path: str, findings: List[Dict]) -> None:
        if isinstance(data, str):
            self._scan_string(data, path, findings)
        elif isinstance(data, dict):
            for key, value in data.items():
                child_path = f"{path}.{key}"
                # 키 자체도 검사 (키에 악성 코드를 숨기는 경우 대비)
                self._scan_string(str(key), f"{child_path}[key]", findings)
                self._scan_recursive(value, child_path, findings)
        elif isinstance(data, (list, tuple)):
            for i, item in enumerate(data):
                self._scan_recursive(item, f"{path}[{i}]", findings)
        elif data is not None:
            self._scan_string(str(data), path, findings)

    def _scan_string(self, text: str, path: str, findings: List[Dict]) -> None:
        for group_name, patterns, severity in self.RULE_GROUPS:
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    snippet = text[max(0, match.start() - 30):match.end() + 30]
                    findings.append({
                        "rule": group_name,
                        "severity": severity,
                        "path": path,
                        "matched": match.group(),
                        "context": snippet.strip(),
                    })

    def is_safe(self, data: Any) -> bool:
        """빠른 안전 여부 확인. CRITICAL이 없으면 True."""
        report = self.scan(data)
        return not report.has_critical()


class AuditReport:
    """SecurityAuditor 스캔 결과를 담는 보고서 객체."""

    def __init__(self, findings: List[Dict[str, str]]):
        self.findings = findings

    def has_critical(self) -> bool:
        return any(f["severity"] == SecurityAuditor.SEVERITY_CRITICAL for f in self.findings)

    def has_any(self) -> bool:
        return len(self.findings) > 0

    def by_severity(self, severity: str) -> List[Dict]:
        return [f for f in self.findings if f["severity"] == severity]

    def summary(self) -> str:
        if not self.findings:
            return "CLEAN - no threats detected."
        lines = [f"ALERT - {len(self.findings)} finding(s):"]
        for f in self.findings:
            lines.append(
                f"  [{f['severity']}] {f['rule']} at {f['path']} "
                f"-> matched: {f['matched']!r}"
            )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"AuditReport(findings={len(self.findings)})"


class MoltbookAdapter:
    """
    Mellow's Local Agent -> Moltbook API Bridge
    SecurityAuditor 통합 버전.
    """

    def __init__(self, api_key: str, base_url: str, workspace_path: str):
        if _is_emergency_lockdown():
            raise RuntimeError("Emergency_Lockdown=ON: MoltbookAdapter 네트워크 호출이 차단되었습니다.")
        self.api_key = api_key
        self.base_url = _normalize_moltbook_api_base(base_url)
        self.workspace = os.path.abspath(workspace_path)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mellow-Link/1.0 (+https://moltbook.com)",
        }
        # 프록시 환경변수 오염 이슈 회피
        self.session = requests.Session()
        self.session.trust_env = False
        self.auditor = SecurityAuditor(block_on_critical=True)

    def _verify_path(self, file_name: str) -> str:
        """sandbox escape 방지"""
        target_path = os.path.abspath(os.path.join(self.workspace, file_name))
        if not target_path.startswith(self.workspace):
            raise PermissionError("access denied: Sandbox escape detected.")
        return target_path

    def post_thought(self, content: str) -> Dict:
        """에이전트의 생각을 Moltbook에 포스팅"""
        endpoint = f"{self.base_url}/posts"
        payload = {"content": content, "persona": "Aventurine"}

        response = self.session.post(endpoint, headers=self.headers, json=payload, timeout=25)
        data = response.json()

        # 응답도 감사 (서버 응답에 injection이 올 수 있음)
        report = self.auditor.scan(data)
        if report.has_any():
            logger.warning("post_thought response audit:\n%s", report.summary())

        return data

    def fetch_latest_skills(self) -> list:
        """Moltbook에서 새로운 skill 패턴 수집 (보안 감사 적용)"""
        endpoint = f"{self.base_url}/skills/trending"
        response = self.session.get(endpoint, headers=self.headers, timeout=25)
        data = response.json()

        # --- 핵심: 저장 전 보안 감사 ---
        report = self.auditor.scan(data)

        if report.has_critical():
            logger.critical(
                "BLOCKED: malicious payload detected in skills response.\n%s",
                report.summary(),
            )
            self._quarantine(data, "skills_quarantined.json", report)
            raise SecurityError(
                f"Malicious content blocked. {len(report.findings)} finding(s). "
                "Data quarantined instead of saved."
            )

        if report.has_any():
            logger.warning(
                "Non-critical findings in skills response:\n%s",
                report.summary(),
            )

        self._save_to_lab(data, "raw_skills.json")
        return data

    def _save_to_lab(self, data: Any, file_name: str) -> None:
        """격리 폴더에 데이터 저장"""
        safe_path = self._verify_path(file_name)
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _quarantine(self, data: Any, file_name: str, report: AuditReport) -> None:
        """악성 데이터를 격리 폴더에 감사 보고서와 함께 저장"""
        safe_path = self._verify_path(file_name)
        envelope = {
            "quarantine_reason": report.summary(),
            "data_hash": hashlib.sha256(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest(),
            "raw_data": data,
        }
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=4)
        logger.info("Quarantined malicious data to %s", safe_path)


class SecurityError(Exception):
    """악성 콘텐츠 탐지 시 발생하는 예외."""
