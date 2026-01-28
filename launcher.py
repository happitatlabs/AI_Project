import subprocess
import time
import webbrowser
import requests
import os
import sys
import signal
import re
import threading
import queue
import json
from pathlib import Path
from typing import List, Tuple, Dict, Set ,Optional

# 프로세스 저장용
vtuber_proc = None
mellow_proc = None


def setup_environment(base_dir: Path):
    """
    런처 실행 시 환경 변수를 설정합니다.
    - FFmpeg 경로를 시스템 PATH에 추가 (프로세스 내 임시 등록)
    """
    vtuber_dir = base_dir / "Open-LLM-VTuber"
    ffmpeg_dir = str(vtuber_dir.absolute())
    
    # 현재 PATH 가져오기
    current_path = os.environ.get("PATH", "")
    
    # FFmpeg 디렉토리가 PATH에 없으면 추가
    if ffmpeg_dir not in current_path:
        # Windows에서는 세미콜론으로 구분
        separator = ";" if sys.platform == "win32" else ":"
        new_path = f"{ffmpeg_dir}{separator}{current_path}"
        os.environ["PATH"] = new_path
        print(f"✅ FFmpeg 경로 추가됨: {ffmpeg_dir}")
    else:
        print(f"ℹ️  FFmpeg 경로가 이미 설정되어 있습니다.")


def parse_requirements_file(requirements_path: Path) -> List[str]:
    """
    requirements.txt 파일을 파싱하여 패키지 이름 목록 추출.
    
    형식 지원:
    - package==1.0.0
    - package>=1.0.0
    - package~=1.0.0
    - package ; python_version < '3.11'
    - # 주석
    """
    packages = []
    if not requirements_path.exists():
        return packages
    
    try:
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 주석이나 빈 줄 건너뛰기
                if not line or line.startswith('#'):
                    continue
                
                # 조건부 의존성 처리 (; 이후 제거)
                if ';' in line:
                    line = line.split(';')[0].strip()
                
                # 패키지 이름 추출 (버전 정보 제거)
                # 예: "fastapi==0.118.0" -> "fastapi"
                # 예: "fastapi[standard]>=0.115.8" -> "fastapi"
                match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                if match:
                    package_name = match.group(1)
                    packages.append(package_name.lower())
    except Exception as e:
        print(f"⚠️  requirements.txt 파싱 오류 ({requirements_path}): {e}")
    
    return packages

def normalize_name(name: str) -> str:
    """
    [Core Patch] 패키지 이름에서 점(.), 하이픈(-), 언더바(_)를 모두 제거하고 소문자로 만듭니다.
    예: 'Ruamel.YAML' -> 'ruamelyaml', 'pdfminer-six' -> 'pdfminersix'
    이것이 바로 '변장술'을 꿰뚫어 보는 아키텍트의 눈이지.
    """
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

def get_installed_packages_fast(python_exe: str) -> Set[str]:
    """[Optimized] 설치된 패키지 명단을 '알맹이'만 남겨서 가져옵니다."""
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            return set()
        
        data = json.loads(result.stdout)
        # 모든 특수문자 제거 후 저장
        return {normalize_name(pkg['name']) for pkg in data}
    except Exception:
        return set()

def diagnose_dependencies(base_dir: Path, python_exe: str) -> Tuple[bool, Dict[str, List[str]]]:
    """[고속 진단] 이름 불일치 문제를 해결한 최종 버전."""
    print("\n" + "="*60 + "\n⚡ 시스템 정밀 점검: 이름표 떼고 알맹이만 확인 중...\n" + "="*60)
    
    installed_set = get_installed_packages_fast(python_exe)
    if not installed_set:
        print("⚠️  패키지 목록 로드 실패. 일단 통과합니다.")
        return True, {}

    missing = {"vtuber": [], "mellow_link": []}
    
    check_targets = [
        ("vtuber", base_dir / "Open-LLM-VTuber" / "requirements.txt"),
        ("mellow_link", base_dir / "requirements.txt") 
    ]

    for key, req_path in check_targets:
        if not req_path.exists() and key == "mellow_link":
             req_path = base_dir / "mellow_link" / "requirements.txt"

        packages = parse_requirements_file(req_path)
        if packages:
            print(f"📦 {key.upper()} 검문 중... ({len(packages)}개)")
            for pkg in packages:
                # 요구사항 파일의 이름도 똑같이 '알맹이'만 남겨서 비교
                pkg_normalized = normalize_name(pkg.split('[')[0])
                
                # 예외 처리
                if pkg_normalized in {'precommit', 'ruff', 'setuptools', 'wheel'}: continue
                
                if pkg_normalized not in installed_set:
                    missing[key].append(pkg)
            
            if not missing[key]:
                print(f"   ✅ 전원 통과")
            else:
                print(f"   ⚠️  {len(missing[key])}개 불일치 ({', '.join(missing[key][:3])}...)")

    all_ok = not missing["vtuber"] and not missing["mellow_link"]
    
    if not all_ok:
        print("\n❌ 여전히 감지되지 않는 패키지가 있습니다.")
        # 하지만 실행은 막지 않도록 유도
        print("💡 팁: 'y'를 눌러 무시하고 실행해도 괜찮을 확률이 99%입니다.")
    else:
        print("✅ 모든 시스템 준비 완료.\n" + "="*60 + "\n")

    return all_ok, missing

def check_ollama():
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


def wait_for_server(url, name, timeout=30, process=None):
    """
    서버가 준비될 때까지 대기.
    
    Args:
        url: 확인할 서버 URL
        name: 서버 이름
        timeout: 최대 대기 시간 (초)
        process: 프로세스 객체 (타임아웃 시에도 살아있는지 확인)
    """
    print(f"⏳ {name} 서버 시작 대기 중... (최대 {timeout}초)")
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < timeout:
        check_count += 1
        
        # 프로세스 상태 확인 (매 5초마다)
        if process and check_count % 5 == 0:
            if process.poll() is not None:
                # 프로세스가 종료되었으면 즉시 실패 반환
                elapsed = time.time() - start_time
                print(f"\n❌ {name} 프로세스가 종료되었습니다! (경과 시간: {elapsed:.1f}초)")
                return False
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                elapsed = time.time() - start_time
                print(f"✅ {name} 서버: Ready (대기 시간: {elapsed:.1f}초)")
                return True
        except requests.RequestException:
            # 5초마다 진행 상황 출력
            if check_count % 5 == 0:
                elapsed = time.time() - start_time
                process_status = "실행 중" if (process and process.poll() is None) else "종료됨"
                print(f"   ... {name} 서버 대기 중 ({elapsed:.1f}초 경과, 프로세스: {process_status})")
            time.sleep(1)
    
    elapsed = time.time() - start_time
    print(f"\n⚠️  {name} 서버 시작 타임아웃 ({elapsed:.1f}초 경과)")
    print(f"   URL: {url}")
    
    # 프로세스 상태 확인
    if process:
        if process.poll() is None:
            # 프로세스가 살아있으면 경고만 표시하고 계속 진행
            print(f"   ⚠️  프로세스는 여전히 실행 중입니다 (PID: {process.pid})")
            print(f"   서버가 로딩 중일 수 있으므로 계속 진행합니다...")
            return True  # 프로세스가 살아있으면 True 반환
        else:
            # 프로세스가 종료되었으면 실패
            print(f"   ❌ 프로세스가 종료되었습니다 (종료 코드: {process.returncode})")
            return False
    
    print(f"   서버 로그를 확인하세요.")
    return False


def find_python_executable():
    """
    가상환경의 Python 실행 파일을 찾습니다.
    
    우선순위:
    1. 현재 디렉토리의 .venv/Scripts/python.exe (Windows)
    2. 현재 디렉토리의 .venv/bin/python (Linux/Mac)
    3. 현재 실행 중인 Python (sys.executable)
    """
    base_dir = Path(__file__).parent.absolute()
    
    # Windows 가상환경 경로
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        print(f"✅ 가상환경 Python 발견: {venv_python}")
        return str(venv_python.absolute())
    
    # Linux/Mac 가상환경 경로
    venv_python = base_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        print(f"✅ 가상환경 Python 발견: {venv_python}")
        return str(venv_python.absolute())
    
    # 가상환경을 찾지 못하면 현재 실행 중인 Python 사용
    python_exe = sys.executable
    print(f"⚠️  가상환경을 찾지 못해 현재 Python 사용: {python_exe}")
    return python_exe


def launch_system():
    """전체 시스템 시작"""
    global vtuber_proc, mellow_proc
    
    # 현재 스크립트의 디렉토리 기준으로 경로 설정
    base_dir = Path(__file__).parent.absolute()
    project_root = str(base_dir)
    
    # 환경 설정 (FFmpeg 경로 등)
    setup_environment(base_dir)
    
    # Python 실행 파일 찾기
    python_exe = find_python_executable()
    
    # 0. 자가 진단: 필수 라이브러리 확인
    all_deps_ok, missing_packages = diagnose_dependencies(base_dir, python_exe)
    
    if not all_deps_ok:
        print("⚠️  경고: 일부 라이브러리가 누락되었습니다.")
        response = input("계속 진행하시겠습니까? (y/N): ").strip().lower()
        if response != 'y':
            print("❌ 사용자가 취소했습니다.")
            return False
    
    # 1. Ollama 확인
    if not check_ollama():
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
        mellow_proc = subprocess.Popen(
            [python_exe, "-m", "mellow_link.main"], 
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
                        print(f"\n   [Mellow-Link] ⚠️  치명적 에러 감지: {line[:150]}")
                    elif 'error' in line_lower and not is_non_critical:
                        # 'error' 키워드가 있지만 치명적이지 않은 경우는 경고만
                        print(f"\n   [Mellow-Link] ℹ️  경고: {line[:150]}")
        except Exception as e:
            mellow_output_queue.put(('error', str(e)))
    
    # 백그라운드 스레드로 출력 읽기 시작
    mellow_output_thread = threading.Thread(target=read_mellow_output, daemon=True)
    mellow_output_thread.start()
    
    # Mellow-Link 서버 준비 대기
    server_ready = wait_for_server("http://localhost:8000/docs", "Mellow-Link", timeout=30, process=mellow_proc)
    
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
            while True:
                # 프로세스 상태 확인
                if vtuber_proc and vtuber_proc.poll() is not None:
                    print("⚠️  VTuber 프로세스가 예기치 않게 종료되었습니다.")
                    break
                if mellow_proc and mellow_proc.poll() is not None:
                    print("⚠️  Mellow-Link 프로세스가 예기치 않게 종료되었습니다.")
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            cleanup_processes()
    else:
        print("❌ 시스템 시작 실패")
        sys.exit(1)
