@echo off
REM ══════════════════════════════════════════════════════════════
REM setup_windows_task.bat — Windows 작업 스케줄러 자동 등록
REM
REM 실행 방법:
REM   1. 이 파일을 "관리자 권한으로 실행"
REM   2. 옵션 선택 후 Enter
REM
REM 등록되는 작업:
REM   - AgentDaemon     : 로그인 시 자동 시작 (백그라운드)
REM   - AgentMaintenance: 매일 오전 3시 유지보수 실행
REM ══════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo =========================================================
echo   Windows 작업 스케줄러 설정 — 자율 에이전트
echo =========================================================
echo.
echo [1] 데몬 자동 시작 등록  (로그인 시 백그라운드 실행)
echo [2] 유지보수 일정 등록   (매일 오전 3시)
echo [3] 두 작업 모두 등록
echo [4] 등록된 작업 확인
echo [5] 작업 삭제
echo [6] 종료
echo.
set /p CHOICE="선택 (1-6): "

REM ── Python 경로 자동 탐지 ────────────────────────────────
for /f "tokens=*" %%p in ('where python 2^>nul') do (
    set PYTHON_PATH=%%p
    goto :python_found
)
echo [오류] Python을 찾을 수 없습니다.
pause & exit /b 1
:python_found
set AGENT_DIR=%~dp0
set AGENT_DIR=%AGENT_DIR:~0,-1%

echo.
echo Python: %PYTHON_PATH%
echo 작업 디렉토리: %AGENT_DIR%
echo.

if "%CHOICE%"=="1" goto :register_daemon
if "%CHOICE%"=="2" goto :register_maintenance
if "%CHOICE%"=="3" goto :register_both
if "%CHOICE%"=="4" goto :check_tasks
if "%CHOICE%"=="5" goto :delete_tasks
if "%CHOICE%"=="6" exit /b 0

:register_daemon
echo [등록] AgentDaemon — 로그인 시 자동 시작...
schtasks /create /tn "AgentDaemon" ^
  /tr "\"%PYTHON_PATH%\" \"%AGENT_DIR%\run_daemon.py\"" ^
  /sc ONLOGON ^
  /ru "%USERNAME%" ^
  /f ^
  /rl HIGHEST
if errorlevel 1 (
    echo [오류] 작업 등록 실패. 관리자 권한으로 실행했는지 확인하세요.
) else (
    echo [완료] AgentDaemon 등록 완료.
    echo        지금 바로 시작하려면: schtasks /run /tn "AgentDaemon"
)
goto :end

:register_maintenance
echo [등록] AgentMaintenance — 매일 오전 3시...
schtasks /create /tn "AgentMaintenance" ^
  /tr "\"%PYTHON_PATH%\" \"%AGENT_DIR%\run_maintenance.py\"" ^
  /sc DAILY ^
  /st 03:00 ^
  /ru "%USERNAME%" ^
  /f
if errorlevel 1 (
    echo [오류] 작업 등록 실패.
) else (
    echo [완료] AgentMaintenance 등록 완료.
)
goto :end

:register_both
call :register_daemon_fn
call :register_maintenance_fn
goto :end

:register_daemon_fn
schtasks /create /tn "AgentDaemon" ^
  /tr "\"%PYTHON_PATH%\" \"%AGENT_DIR%\run_daemon.py\"" ^
  /sc ONLOGON /ru "%USERNAME%" /f /rl HIGHEST >nul 2>&1 && ^
  echo [OK] AgentDaemon 등록 || echo [오류] AgentDaemon 등록 실패
exit /b

:register_maintenance_fn
schtasks /create /tn "AgentMaintenance" ^
  /tr "\"%PYTHON_PATH%\" \"%AGENT_DIR%\run_maintenance.py\"" ^
  /sc DAILY /st 03:00 /ru "%USERNAME%" /f >nul 2>&1 && ^
  echo [OK] AgentMaintenance 등록 || echo [오류] AgentMaintenance 등록 실패
exit /b

:check_tasks
echo.
echo ── 등록된 에이전트 작업 ──
schtasks /query /tn "AgentDaemon"      2>nul || echo AgentDaemon: 미등록
echo.
schtasks /query /tn "AgentMaintenance" 2>nul || echo AgentMaintenance: 미등록
goto :end

:delete_tasks
echo [삭제] 에이전트 작업 제거 중...
schtasks /delete /tn "AgentDaemon"      /f 2>nul && echo [OK] AgentDaemon 삭제 || echo AgentDaemon: 없음
schtasks /delete /tn "AgentMaintenance" /f 2>nul && echo [OK] AgentMaintenance 삭제 || echo AgentMaintenance: 없음
goto :end

:end
echo.
echo ── 현재 등록된 작업 요약 ──
schtasks /query /fo LIST /tn "AgentDaemon"      2>nul | findstr "작업 이름\|상태\|Task Name\|Status"
schtasks /query /fo LIST /tn "AgentMaintenance" 2>nul | findstr "작업 이름\|상태\|Task Name\|Status"
echo.
pause
endlocal
