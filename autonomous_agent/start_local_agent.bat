@echo off
REM ══════════════════════════════════════════════════════
REM start_local_agent.bat — 로컬 에이전트 실행 스크립트 (Windows)
REM
REM 실행 전 확인:
REM   1) Ollama 실행 중: 별도 터미널에서 'ollama serve'
REM   2) 모델 설치:      'ollama pull qwen3.5:9b'
REM   3) Python 3.10+:   https://python.org
REM
REM 사용법:
REM   start_local_agent.bat             -- 기본 실행
REM   start_local_agent.bat --test      -- LLM 연결 테스트만
REM   start_local_agent.bat --forever   -- 무한 반복 (Ctrl+C로 중지)
REM   start_local_agent.bat --cycles 10 -- 10사이클 실행
REM ══════════════════════════════════════════════════════

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ======================================================
echo   자율 발전 에이전트 -- 로컬 실행 스크립트 (Windows)
echo ======================================================
echo.

REM ── Python 확인 ──────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python을 찾을 수 없습니다. Python 3.10+ 설치 필요
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

REM ── Ollama 확인 (curl 사용) ──────────────────────────
echo.
echo [점검] Ollama 서버 확인 중...
curl -sf http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [경고] Ollama 서버 미응답 ^(localhost:11434^)
    echo        Ollama 시작: 새 터미널에서 'ollama serve' 실행
    echo        fallback_to_rules=true 이므로 규칙 기반으로 계속 실행합니다.
) else (
    echo [OK] Ollama 서버 응답 확인
)

echo.

REM ── --test 모드 ──────────────────────────────────────
if "%1"=="--test" (
    echo [모드] LLM 연결 테스트
    python test_llm.py
    goto :end
)

REM ── --forever 모드 ────────────────────────────────────
if "%1"=="--forever" (
    echo [모드] 무한 반복 ^(Ctrl+C로 중지^)
    set RUN=0
    :forever_loop
    set /a RUN+=1
    echo.
    echo [실행 #!RUN!]
    python run_agent.py --cycles 1
    timeout /t 2 /nobreak >nul
    goto forever_loop
)

REM ── 기본 실행 ─────────────────────────────────────────
python run_agent.py %*

:end
if errorlevel 1 (
    echo.
    echo [오류] 에이전트 비정상 종료
) else (
    echo.
    echo [완료] 에이전트 정상 종료
)
pause
endlocal
