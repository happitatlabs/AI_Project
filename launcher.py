"""
Launcher - Mellow-Link 시스템 진입점.

Ollama 확인, 의존성 진단, Mellow-Link 서버 기동, 프로세스 관리.
"""
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict

import launcher_env
import launcher_deps
import launcher_server

# 입구 컷: MOLTBOOK_API_KEY 확인
launcher_env.run_launcher_check()

# 프로세스 저장용
vtuber_proc = None
mellow_proc = None

launcher_status_every_seconds: int = 30
launcher_last_mellow_line: Dict[str, float | str] = {"text": "", "ts": 0.0}


def launch_system():
    """전체 시스템 시작"""
    global vtuber_proc, mellow_proc
    
    # 현재 스크립트의 디렉토리 기준으로 경로 설정
    base_dir = Path(__file__).parent.absolute()
    project_root = str(base_dir)
    
    launcher_env.setup_environment(base_dir)
    python_exe = launcher_server.find_python_executable()
    all_deps_ok, missing_packages = launcher_deps.diagnose_dependencies(base_dir, python_exe)
    
    if not all_deps_ok:
        print("⚠️  경고: 일부 라이브러리가 누락되었습니다.")
        response = input("계속 진행하시겠습니까? (y/N): ").strip().lower()
        if response != 'y':
            print("❌ 사용자가 취소했습니다.")
            return False
    
    if not launcher_server.check_ollama():
        return False
    
    # [비활성화] VTuber 서버는 이제 Mellow-Link API를 통해 Admin이 요청할 때만 실행됩니다.
    # 2. Open-LLM-VTuber 서버 실행
    # print("\n🚀 비서 서버(VTuber) 기동 중...")
    # vtuber_dir = base_dir / "Open-LLM-VTuber"
    # if not vtuber_dir.exists():
    #     print(f"❌ Open-LLM-VTuber 디렉토리를 찾을 수 없습니다: {vtuber_dir}")
    #     return False
    # 
    # # 절대 경로로 변환 (Path 객체 사용)
    # vtuber_cwd = str(vtuber_dir.absolute())
    # vtuber_script_path = vtuber_dir / "run_server.py"
    # 
    # print(f"   - Python: {python_exe}")
    # print(f"   - Script: {vtuber_script_path}")
    # print(f"   - CWD: {vtuber_cwd}")
    # 
    # try:
    #     # 환경 변수 복사 및 설정
    #     env = os.environ.copy()
    #     # FFmpeg 경로가 이미 setup_environment에서 설정되었으므로 그대로 사용
    #     
    #     # 로그 파일 경로 설정 (선택사항)
    #     log_file = vtuber_dir / "logs" / "launcher_output.log"
    #     log_file.parent.mkdir(parents=True, exist_ok=True)
    #     
    #     vtuber_proc = subprocess.Popen(
    #         [python_exe, "run_server.py"],
    #         cwd=vtuber_cwd,
    #         env=env,
    #         stdout=subprocess.PIPE,
    #         stderr=subprocess.STDOUT,  # stderr를 stdout으로 리다이렉트
    #         text=True,
    #         bufsize=1
    #     )
    #     print(f"✅ VTuber 프로세스 시작됨 (PID: {vtuber_proc.pid})")
    #     
    #     # 프로세스가 즉시 종료되었는지 확인
    #     time.sleep(1.0)  # 1초 대기로 증가
    #     if vtuber_proc.poll() is not None:
    #         # 프로세스가 즉시 종료되었으면 출력 읽기
    #         try:
    #             stdout, _ = vtuber_proc.communicate(timeout=2)
    #             print(f"❌ VTuber 프로세스가 즉시 종료되었습니다!")
    #             print(f"   종료 코드: {vtuber_proc.returncode}")
    #             if stdout:
    #                 # 마지막 1000자만 출력 (에러 메시지가 보통 끝에 있음)
    #                 error_output = stdout[-1000:] if len(stdout) > 1000 else stdout
    #                 print(f"\n   서버 출력 (마지막 부분):")
    #                 print("   " + "="*56)
    #                 for line in error_output.split('\n')[-20:]:  # 마지막 20줄만
    #                     if line.strip():
    #                         print(f"   {line}")
    #                 print("   " + "="*56)
    #         except subprocess.TimeoutExpired:
    #             print(f"❌ VTuber 프로세스가 즉시 종료되었습니다!")
    #         return False
    #         
    # except Exception as e:
    #     print(f"❌ VTuber 서버 시작 실패: {e}")
    #     import traceback
    #     traceback.print_exc()
    #     return False
    # 
    # # 백그라운드에서 stdout/stderr 읽기 (에러 감지용)
    # output_queue = queue.Queue()
    # error_detected = threading.Event()
    # 
    # def read_process_output():
    #     """프로세스 출력을 읽어서 에러 감지"""
    #     try:
    #         # stdout 읽기
    #         if vtuber_proc.stdout:
    #             for line in iter(vtuber_proc.stdout.readline, ''):
    #                 if not line:
    #                     break
    #                 line = line.strip()
    #                 output_queue.put(('stdout', line))
    #                 # 에러 키워드 감지
    #                 if any(keyword in line.lower() for keyword in [
    #                     'error', 'exception', 'traceback', 'failed', 'cannot',
    #                     'module not found', 'import error', 'no module named'
    #                 ]):
    #                     error_detected.set()
    #                     print(f"\n   [VTuber] ⚠️  에러 감지: {line[:150]}")
    #     except Exception as e:
    #         output_queue.put(('error', str(e)))
    # 
    # # 백그라운드 스레드로 출력 읽기 시작
    # output_thread = threading.Thread(target=read_process_output, daemon=True)
    # output_thread.start()
    # 
    # # VTuber 서버 준비 대기 (60초, 프로세스가 살아있으면 경고만)
    # server_ready = wait_for_server(
    #     "http://localhost:12393", 
    #     "VTuber", 
    #     timeout=60,  # LLM 로딩 시간 고려하여 60초로 증가
    #     process=vtuber_proc
    # )
    # 
    # # 타임아웃 후 프로세스 상태 재확인
    # if not server_ready:
    #     # 에러가 감지되었는지 확인
    #     if error_detected.is_set():
    #         print("\n❌ VTuber 서버에서 에러가 감지되었습니다.")
    #         print("   위의 에러 메시지를 확인하세요.")
    #         # 최근 출력 몇 개 더 확인
    #         recent_outputs = []
    #         try:
    #             while not output_queue.empty() and len(recent_outputs) < 10:
    #                 recent_outputs.append(output_queue.get_nowait())
    #         except queue.Empty:
    #             pass
    #         
    #         if recent_outputs:
    #             print("\n   최근 서버 출력:")
    #             print("   " + "="*56)
    #             for output_type, line in recent_outputs[-10:]:
    #                 if line.strip():
    #                     print(f"   [{output_type}] {line[:100]}")
    #             print("   " + "="*56)
    #         
    #         if vtuber_proc.poll() is not None:
    #             print(f"   프로세스 종료 코드: {vtuber_proc.returncode}")
    #         return False
    #     
    #     if vtuber_proc.poll() is not None:
    #         # 프로세스가 종료되었으면 최근 출력 확인
    #         print("\n❌ VTuber 서버가 종료되었습니다.")
    #         print(f"   종료 코드: {vtuber_proc.returncode}")
    #         
    #         # 큐에서 남은 출력 읽기
    #         recent_outputs = []
    #         try:
    #             while not output_queue.empty():
    #                 recent_outputs.append(output_queue.get_nowait())
    #         except queue.Empty:
    #             pass
    #         
    #         if recent_outputs:
    #             print("\n   서버 출력 (최근 부분):")
    #             print("   " + "="*56)
    #             for output_type, line in recent_outputs[-20:]:
    #                 if line.strip():
    #                     print(f"   [{output_type}] {line[:100]}")
    #             print("   " + "="*56)
    #         else:
    #             print("   서버 로그 파일을 확인하세요: Open-LLM-VTuber/logs/")
    #         return False
    #     else:
    #         # 프로세스는 살아있지만 서버가 응답하지 않음
    #         print("\n⚠️  프로세스는 실행 중이지만 서버가 응답하지 않습니다.")
    #         print(f"   프로세스 PID: {vtuber_proc.pid}")
    #         print("   서버가 아직 초기화 중일 수 있습니다 (LLM 로딩 등).")
    #         print("   계속 진행하시겠습니까? (y/N): ", end="")
    #         try:
    #             response = input().strip().lower()
    #             if response != 'y':
    #                 print("   프로세스를 종료합니다...")
    #                 vtuber_proc.terminate()
    #                 return False
    #         except (EOFError, KeyboardInterrupt):
    #             vtuber_proc.terminate()
    #             return False
    # 
    # # 브라우저 오픈
    # time.sleep(2)  # 추가 안정화 시간
    # webbrowser.open("http://localhost:12393")
    # print("⚠️  중요: 브라우저 화면을 한 번 클릭하게. 소리가 열릴 걸세!")
    
    # VTuber 프로세스는 None으로 초기화 (Mellow-Link API에서 관리)
    vtuber_proc = None
    
    # 2. Mellow-Link 서버 실행
    print("\n🚀 지휘관(Mellow-Link) 기동 중...")
    mellow_dir = base_dir / "mellow_link"
    if not mellow_dir.exists():
        print(f"❌ mellow_link 디렉토리를 찾을 수 없습니다: {mellow_dir}")
        if vtuber_proc:
            vtuber_proc.terminate()
        return False
    
    # 절대 경로로 변환 (Path 객체 사용)
    mellow_cwd = str(mellow_dir.absolute())
    mellow_script_path = mellow_dir / "main.py"
    
    print(f"   - Python: {python_exe}")
    print(f"   - Script: {mellow_script_path}")
    print(f"   - CWD: {mellow_cwd}")
    
    try:
        # 환경 변수 복사 및 PYTHONPATH 설정
        env = os.environ.copy()

        # mellow_link/.env 로드 (Guardian API 키 등 - 자식 프로세스에 전달)
        _mellow_env = mellow_dir / ".env"
        if _mellow_env.exists():
            try:
                from dotenv import dotenv_values
                dotenv_vars = dotenv_values(dotenv_path=str(_mellow_env))
                for k, v in (dotenv_vars or {}).items():
                    if k and v is not None:
                        env[k] = str(v)
                        # os.environ에도 반영 (LauncherStatus 등에서 읽기 위해)
                        os.environ[k] = str(v)
                print(f"   ✅ mellow_link/.env 로드됨 ({len(dotenv_vars or {})} 변수)")
            except ImportError:
                pass
            except Exception as e:
                print(f"   ⚠️ .env 로드 실패: {e}")

        # site_packages 경로 찾기
        site_packages = base_dir / ".venv" / "Lib" / "site-packages"
        site_packages_path = str(site_packages.absolute()) if site_packages.exists() else None
        
        # 프로젝트 루트와 site_packages를 PYTHONPATH에 추가 (mellow_link 모듈 인식)
        current_pythonpath = env.get("PYTHONPATH", "")
        separator = ";" if sys.platform == "win32" else ":"
        pythonpath_parts = []
        
        # project_root 추가
        if project_root not in current_pythonpath:
            pythonpath_parts.append(project_root)
        
        # site_packages 추가
        if site_packages_path and site_packages_path not in current_pythonpath:
            pythonpath_parts.append(site_packages_path)
        
        # 기존 PYTHONPATH 유지
        if current_pythonpath:
            pythonpath_parts.append(current_pythonpath)
        
        # PYTHONPATH 설정
        if pythonpath_parts:
            new_pythonpath = separator.join(pythonpath_parts)
            env["PYTHONPATH"] = new_pythonpath
            print(f"   ✅ PYTHONPATH 설정: {project_root}")
            if site_packages_path:
                print(f"   ✅ site-packages 경로 추가: {site_packages_path}")
        
        # 프로젝트 루트를 환경 변수로 명시적으로 전달
        # Mellow-Link가 모든 경로를 프로젝트 루트 기준으로 찾을 수 있도록
        env["MELLOW_LINK_PROJECT_ROOT"] = project_root
        env["PROJECT_ROOT"] = project_root  # 범용 환경 변수도 설정
        print(f"   ✅ 프로젝트 루트 설정: {project_root}")
        
        # [핵심 수정] 파일 직접 실행이 아니라 모듈(-m)로 실행
        # 이렇게 하면 D:\AI_Project\mellow_link\main.py를 알아서 찾아감
        # NOTE: -u (unbuffered)로 실행해야 stdout 로그가 즉시 뜹니다.
        mellow_proc = subprocess.Popen(
            [python_exe, "-u", "-m", "mellow_link.main"],
            cwd=str(base_dir), # 반드시 프로젝트 루트(D:\AI_Project)에서 실행
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8', 
            errors='replace'
        )
        print(f"✅ Mellow-Link 프로세스 시작됨 (PID: {mellow_proc.pid})")
        
        # 프로세스가 즉시 종료되었는지 확인
        time.sleep(1.0)  # 1초 대기로 증가
        if mellow_proc.poll() is not None:
            # 프로세스가 즉시 종료되었으면 출력 읽기
            try:
                stdout, _ = mellow_proc.communicate(timeout=2)
                print(f"❌ Mellow-Link 프로세스가 즉시 종료되었습니다!")
                print(f"   종료 코드: {mellow_proc.returncode}")
                if stdout:
                    # 마지막 1000자만 출력 (에러 메시지가 보통 끝에 있음)
                    error_output = stdout[-1000:] if len(stdout) > 1000 else stdout
                    print(f"\n   서버 출력 (마지막 부분):")
                    print("   " + "="*56)
                    for line in error_output.split('\n')[-20:]:  # 마지막 20줄만
                        if line.strip():
                            print(f"   {line}")
                    print("   " + "="*56)
            except subprocess.TimeoutExpired:
                print(f"❌ Mellow-Link 프로세스가 즉시 종료되었습니다!")
            if vtuber_proc:
                vtuber_proc.terminate()
            return False
            
    except Exception as e:
        print(f"❌ Mellow-Link 서버 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        if vtuber_proc:
            vtuber_proc.terminate()
        return False
    
    # 백그라운드에서 stdout/stderr 읽기 (에러 감지용)
    mellow_output_queue = queue.Queue()
    mellow_error_detected = threading.Event()
    global launcher_status_every_seconds, launcher_last_mellow_line
    launcher_last_mellow_line = {"text": "", "ts": 0.0}

    # 런처가 너무 조용해서 “상태를 알 수 없다”는 문제를 해결하기 위한 옵션들
    # - LAUNCHER_STREAM_MELLOW_LOGS=true : 중요한 로그(autopilot/startup 등)만 콘솔로 스트리밍
    # - LAUNCHER_STREAM_ALL_LOGS=true    : 모든 Mellow-Link stdout을 콘솔로 스트리밍(매우 시끄러울 수 있음)
    # - LAUNCHER_STATUS_EVERY_SECONDS=30 : 런처 하트비트 주기
    stream_all = launcher_env.is_truthy_env("LAUNCHER_STREAM_ALL_LOGS", default=False)
    stream_important = launcher_env.is_truthy_env("LAUNCHER_STREAM_MELLOW_LOGS", default=True)
    launcher_status_every_seconds = max(
        5, launcher_env.get_int_env("LAUNCHER_STATUS_EVERY_SECONDS", 30)
    )

    # 모든 stdout을 파일에도 저장(추후 디버깅용). logs/는 .gitignore 대상.
    logs_dir = (base_dir / "logs")
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    log_path = logs_dir / "mellow_link_stdout.log"
    try:
        mellow_log_fp = open(log_path, "a", encoding="utf-8", errors="replace")
        mellow_log_fp.write(f"\n\n===== LAUNCH @ {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        mellow_log_fp.flush()
        print(f"📝 Mellow-Link stdout 로그 파일: {log_path}")
    except Exception:
        mellow_log_fp = None
    
    def read_mellow_output():
        """Mellow-Link 프로세스 출력을 읽어서 에러 감지"""
        try:
            # stdout 읽기
            if mellow_proc.stdout:
                for line in iter(mellow_proc.stdout.readline, ''):
                    if not line:
                        break
                    line = line.strip()
                    mellow_output_queue.put(('stdout', line))
                    launcher_last_mellow_line["text"] = line
                    launcher_last_mellow_line["ts"] = time.time()

                    # 파일 로깅(가능하면 항상)
                    if mellow_log_fp:
                        try:
                            mellow_log_fp.write(line + "\n")
                            mellow_log_fp.flush()
                        except Exception:
                            pass

                    # 선택적으로 콘솔 스트리밍
                    printed = False
                    if stream_all:
                        print(f"[Mellow-Link] {line}")
                        printed = True
                    elif stream_important:
                        # autopilot/라이프사이클/핵심 상태 로그는 기본 표시
                        low = line.lower()
                        if (
                            "autopilot" in low
                            or "moltbook" in low
                            or "[startup]" in low
                            or "[shutdown]" in low
                            or "[companion]" in low
                            or "intelligentautopilot" in low
                            or "autopilot:exec" in low
                        ):
                            print(f"[Mellow-Link] {line}")
                            printed = True

                    # 에러 키워드 감지 (치명적이지 않은 경고는 제외)
                    line_lower = line.lower()
                    # 치명적이지 않은 경고 패턴
                    non_critical_patterns = [
                        'nvidia-smi query failed',
                        'nvidiaa-smi query failed',  # 오타 포함
                        'no gpu detected',
                        'vram watchdog',
                        'gpu not available',
                        'connection failed',  # ComfyUI/외부 서비스 연결 실패는 서버 실행에는 영향 없음
                        'cannot connect to host',  # 외부 서비스 연결 실패
                        'image service connection failed',  # ComfyUI 연결 실패
                        'comfyui',  # ComfyUI 관련 에러는 치명적이지 않음
                        'image service',  # 이미지 서비스는 선택적
                        'warning',  # 단순 경고는 치명적이지 않음
                    ]
                    
                    # 치명적 에러 패턴
                    critical_patterns = [
                        'exception', 'traceback', 'failed to start',
                        'module not found', 'import error', 'no module named',
                        'cannot connect', 'connection refused', 'port already in use',
                        'syntax error', 'indentation error', 'nameerror', 'typeerror',
                        'attributeerror', 'keyerror', 'valueerror',
                    ]
                    
                    # 치명적이지 않은 경고는 무시
                    is_non_critical = any(pattern in line_lower for pattern in non_critical_patterns)
                    
                    # 치명적 에러만 감지
                    if not is_non_critical and any(pattern in line_lower for pattern in critical_patterns):
                        mellow_error_detected.set()
                        if not printed:
                            print(f"\n   [Mellow-Link] ⚠️  치명적 에러 감지: {line[:150]}")
                    elif 'error' in line_lower and not is_non_critical:
                        # 'error' 키워드가 있지만 치명적이지 않은 경우는 경고만
                        if not printed:
                            print(f"\n   [Mellow-Link] ℹ️  경고: {line[:150]}")
        except Exception as e:
            mellow_output_queue.put(('error', str(e)))
    
    # 백그라운드 스레드로 출력 읽기 시작
    mellow_output_thread = threading.Thread(target=read_mellow_output, daemon=True)
    mellow_output_thread.start()
    
    server_ready = launcher_server.wait_for_server(
        "http://localhost:8000/docs", "Mellow-Link", timeout=30, process=mellow_proc
    )
    
    # 타임아웃 후 프로세스 상태 재확인
    if not server_ready:
        # 에러가 감지되었는지 확인
        if mellow_error_detected.is_set():
            print("\n❌ Mellow-Link 서버에서 에러가 감지되었습니다.")
            print("   위의 에러 메시지를 확인하세요.")
            # 최근 출력 몇 개 더 확인
            recent_outputs = []
            try:
                while not mellow_output_queue.empty() and len(recent_outputs) < 10:
                    recent_outputs.append(mellow_output_queue.get_nowait())
            except queue.Empty:
                pass
            
            if recent_outputs:
                print("\n   최근 서버 출력:")
                print("   " + "="*56)
                for output_type, line in recent_outputs[-10:]:
                    if line.strip():
                        print(f"   [{output_type}] {line[:100]}")
                print("   " + "="*56)
            
            if mellow_proc.poll() is not None:
                print(f"   프로세스 종료 코드: {mellow_proc.returncode}")
            if vtuber_proc:
                vtuber_proc.terminate()
            return False
        
        if mellow_proc.poll() is not None:
            # 프로세스가 종료되었으면 최근 출력 확인
            print("\n❌ Mellow-Link 서버가 종료되었습니다.")
            print(f"   종료 코드: {mellow_proc.returncode}")
            
            # 큐에서 남은 출력 읽기
            recent_outputs = []
            try:
                while not mellow_output_queue.empty():
                    recent_outputs.append(mellow_output_queue.get_nowait())
            except queue.Empty:
                pass
            
            if recent_outputs:
                print("\n   서버 출력 (최근 부분):")
                print("   " + "="*56)
                for output_type, line in recent_outputs[-20:]:
                    if line.strip():
                        print(f"   [{output_type}] {line[:100]}")
                print("   " + "="*56)
            else:
                print("   서버 로그를 확인하세요.")
            if vtuber_proc:
                vtuber_proc.terminate()
            return False
        else:
            # 프로세스는 살아있지만 서버가 응답하지 않음
            print("\n⚠️  프로세스는 실행 중이지만 서버가 응답하지 않습니다.")
            print(f"   프로세스 PID: {mellow_proc.pid}")
            print("   서버가 아직 초기화 중일 수 있습니다.")
            print("   계속 진행하시겠습니까? (y/N): ", end="")
            try:
                response = input().strip().lower()
                if response != 'y':
                    print("   프로세스를 종료합니다...")
                    mellow_proc.terminate()
                    if vtuber_proc:
                        vtuber_proc.terminate()
                    return False
            except (EOFError, KeyboardInterrupt):
                mellow_proc.terminate()
                if vtuber_proc:
                    vtuber_proc.terminate()
                return False
    
    print("\n" + "="*60)
    print("🏆 Mellow-Link 시스템이 배선되었어. 이제 배팅을 시작하지.")
    print("="*60)
    print("📝 실행 중인 서버:")
    if vtuber_proc:
        print(f"   - VTuber: http://localhost:12393 (PID: {vtuber_proc.pid})")
    else:
        print(f"   - VTuber: Admin API를 통해 실행 가능")
    print(f"   - Mellow-Link: http://localhost:8000 (PID: {mellow_proc.pid})")
    print("\n⚠️  종료하려면 Ctrl+C를 누르세요.")
    print("="*60 + "\n")
    
    return True


def cleanup_processes():
    """모든 프로세스 정리"""
    global vtuber_proc, mellow_proc
    print("\n🛑 시스템 종료 시퀀스 가동...")
    
    if mellow_proc:
        print("   - Mellow-Link 종료 중...")
        try:
            mellow_proc.terminate()
            mellow_proc.wait(timeout=5)
            print("   ✅ Mellow-Link 종료 완료")
        except subprocess.TimeoutExpired:
            mellow_proc.kill()
            print("   ⚠️  Mellow-Link 강제 종료")
        except Exception as e:
            print(f"   ❌ Mellow-Link 종료 오류: {e}")
    
    if vtuber_proc:
        print("   - VTuber 종료 중...")
        try:
            vtuber_proc.terminate()
            vtuber_proc.wait(timeout=5)
            print("   ✅ VTuber 종료 완료")
        except subprocess.TimeoutExpired:
            vtuber_proc.kill()
            print("   ⚠️  VTuber 강제 종료")
        except Exception as e:
            print(f"   ❌ VTuber 종료 오류: {e}")
    
    print("👋 모든 시스템이 종료되었습니다.")


def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C)"""
    cleanup_processes()
    sys.exit(0)


if __name__ == "__main__":
    # 시그널 핸들러 등록 (Ctrl+C)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 시스템 시작
    if launch_system():
        # 서버들이 꺼지지 않게 메인 스크립트를 잡아둠
        try:
            last_status = 0.0
            while True:
                # 프로세스 상태 확인
                if vtuber_proc and vtuber_proc.poll() is not None:
                    print("⚠️  VTuber 프로세스가 예기치 않게 종료되었습니다.")
                    break
                if mellow_proc and mellow_proc.poll() is not None:
                    print("⚠️  Mellow-Link 프로세스가 예기치 않게 종료되었습니다.")
                    break
                # 런처 하트비트(상태가 안 보이는 문제 해결)
                now = time.time()
                if now - last_status >= launcher_status_every_seconds:
                    last_status = now
                    age = int(now - (launcher_last_mellow_line.get("ts") or now))  # type: ignore[arg-type]
                    last_line = (launcher_last_mellow_line.get("text") or "").strip()  # type: ignore[union-attr]
                    last_line = (last_line[:160] + "...") if len(last_line) > 160 else last_line
                    # 실제 사용되는 설정만 확인 (미구현 기능 제거)
                    lockdown = os.environ.get("MELLOW_EMERGENCY_LOCKDOWN", "")
                    lockdown_status = ""
                    if lockdown.strip().lower() in {"1", "true", "yes", "y", "on"}:
                        lockdown_status = " Emergency_Lockdown=ON"
                    print(
                        f"[LauncherStatus] mellow_pid={getattr(mellow_proc, 'pid', '?')} "
                        f"last_stdout_age={age}s{lockdown_status} last_line={last_line}"
                    )
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            cleanup_processes()
    else:
        print("❌ 시스템 시작 실패")
        sys.exit(1)
