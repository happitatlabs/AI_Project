"""
런처 서버 유틸: Ollama 확인, 서버 대기, Python 실행 파일 탐색.
"""
import sys
import time
from pathlib import Path
from typing import Optional

import requests


def check_ollama() -> bool:
    """Ollama 서버가 실행 중인지 확인"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("✅ Ollama: Online")
            return True
    except requests.RequestException:
        pass
    print("❌ Ollama가 꺼져 있군. 먼저 켜주게!")
    return False


def wait_for_server(
    url: str,
    name: str,
    timeout: int = 30,
    process: Optional[object] = None,
) -> bool:
    """
    서버가 준비될 때까지 대기.

    Args:
        url: 확인할 서버 URL
        name: 서버 이름
        timeout: 최대 대기 시간 (초)
        process: 프로세스 객체 (타임아웃 시에도 살아있는지 확인)

    Returns:
        True if server is ready, False otherwise
    """
    print(f"⏳ {name} 서버 시작 대기 중... (최대 {timeout}초)")
    start_time = time.time()
    check_count = 0

    while time.time() - start_time < timeout:
        check_count += 1

        if process and check_count % 5 == 0:
            if process.poll() is not None:
                elapsed = time.time() - start_time
                print(
                    f"\n❌ {name} 프로세스가 종료되었습니다! (경과 시간: {elapsed:.1f}초)"
                )
                return False

        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                elapsed = time.time() - start_time
                print(f"✅ {name} 서버: Ready (대기 시간: {elapsed:.1f}초)")
                return True
        except requests.RequestException:
            if check_count % 5 == 0:
                elapsed = time.time() - start_time
                process_status = (
                    "실행 중"
                    if (process and process.poll() is None)
                    else "종료됨"
                )
                print(
                    f"   ... {name} 서버 대기 중 ({elapsed:.1f}초 경과, 프로세스: {process_status})"
                )
            time.sleep(1)

    elapsed = time.time() - start_time
    print(f"\n⚠️  {name} 서버 시작 타임아웃 ({elapsed:.1f}초 경과)")
    print(f"   URL: {url}")

    if process:
        if process.poll() is None:
            print(f"   ⚠️  프로세스는 여전히 실행 중입니다 (PID: {process.pid})")
            print(f"   서버가 로딩 중일 수 있으므로 계속 진행합니다...")
            return True
        else:
            print(f"   ❌ 프로세스가 종료되었습니다 (종료 코드: {process.returncode})")
            return False

    print(f"   서버 로그를 확인하세요.")
    return False


def find_python_executable() -> str:
    """
    가상환경의 Python 실행 파일을 찾습니다.

    우선순위:
    1. 현재 디렉토리의 .venv/Scripts/python.exe (Windows)
    2. 현재 디렉토리의 .venv/bin/python (Linux/Mac)
    3. 현재 실행 중인 Python (sys.executable)
    """
    base_dir = Path(__file__).parent.absolute()

    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        print(f"✅ 가상환경 Python 발견: {venv_python}")
        return str(venv_python.absolute())

    venv_python = base_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        print(f"✅ 가상환경 Python 발견: {venv_python}")
        return str(venv_python.absolute())

    python_exe = sys.executable
    print(f"⚠️  가상환경을 찾지 못해 현재 Python 사용: {python_exe}")
    return python_exe
