"""
Mellow-Link - Local AI Orchestration System

Main entry point for the FastAPI application.
Orchestrates GPU resource sharing between LLM (Ollama) and Image Generation (ComfyUI).

Usage:
    # Run with uvicorn
    uvicorn main:app --host 0.0.0.0 --port 8000

    # Or run directly
    python -m main
"""

import asyncio
import ctypes
import logging
import os
import signal
import json
import sys
import traceback
import subprocess
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request, Depends, HTTPException, status, Header, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse, JSONResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# =============================================================================
# Mellow-Link Internal Imports (Package-Level)
# =============================================================================

# Config
from mellow_link.config import get_settings, Settings

# Core - States, Events, Orchestrator, Schemas, Security
from mellow_link.core import (
    SystemState, TaskPriority, TransitionResult,
    TaskEvent, EventType,
    Orchestrator, ChatContext,
    ImageRequest,
    bootstrap_admin_account, is_admin_user,
)

# Infra - Watchdog, Event Logger, Database & Auth
from mellow_link.infra import (
    VRAMWatchdog, VRAMStatus, create_watchdog,
    log_event,
    get_db, User, UserRole, AgentFolder, ChatSession, GuestUsage,
    create_default_folders_for_user, ensure_user_has_folders, get_or_create_default_session,
    verify_password, get_password_hash, create_access_token, get_current_user,
    check_guest_limit, increment_guest_usage,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# Services - LLM, Image, Document, VTuber Relay, RAG
from mellow_link.services import (
    LLMService, create_llm_service,
    ImageService, create_image_service,
    DocumentService, DocumentRequest, DocumentType, create_document_service,
    VTuberRelayService, create_vtuber_relay, get_vtuber_relay, set_vtuber_relay,
    RAGService, RAGSearchResult, create_rag_service, get_rag_service, set_rag_service,
)

# Utils - System Control
from mellow_link.utils import (
    launch_avatar_service, get_avatar_status,
    is_port_active, DEFAULT_AVATAR_WS_PORT,
)


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exceptions for Authentication
# =============================================================================

class AuthenticationInterruptedError(Exception):
    """Raised when authentication process is cancelled or aborted."""
    pass


class AuthenticationCancelledError(AuthenticationInterruptedError):
    """Raised when authentication is cancelled (e.g., timeout, client disconnect)."""
    pass


# =============================================================================
# Global Service Instances
# =============================================================================

settings: Optional[Settings] = None
orchestrator: Optional[Orchestrator] = None
vram_watchdog: Optional[VRAMWatchdog] = None
llm_service: Optional[LLMService] = None
image_service: Optional[ImageService] = None
doc_service: Optional[DocumentService] = None
vtuber_relay: Optional[VTuberRelayService] = None
vtuber_proc: Optional[Any] = None  # VTuber 백엔드 프로세스 관리 (subprocess.Popen)
rag_service: Optional[RAGService] = None  # RAG 문서 검색 서비스

shutdown_event: asyncio.Event = asyncio.Event()


# =============================================================================
# VRAM Event Handlers
# =============================================================================

async def on_vram_warning(gpu_info) -> None:
    """Handle VRAM warning threshold crossing."""
    logger.warning(
        f"[VRAM WARNING] Usage: {gpu_info.usage_percent:.1f}% "
        f"({gpu_info.used_memory_mb:.0f}/{gpu_info.total_memory_mb:.0f} MB)"
    )


# 2. on_vram_critical 함수 교체
async def on_vram_critical(gpu_info) -> None:
    """
    [KILL SWITCH] Handle VRAM critical threshold.
    Logs the emergency and forces the Orchestrator to IDLE state.
    """
    msg = f"[VRAM CRITICAL] Usage: {gpu_info.usage_percent:.1f}% ({gpu_info.used_memory_mb}MB) - Triggering Kill Switch"
    logger.error(msg)
    
    # 1. 이벤트 로그 기록 (JSONL)
    log_event(
        event_type="system_alert",
        message=msg,
        context_metadata={
            "level": "critical", 
            "vram_usage": gpu_info.usage_percent,
            "action": "force_idle"
        }
    )

    # 2. 오케스트레이터 강제 초기화 (Kill Switch)
    if orchestrator:
        # 강제로 IDLE로 전환하여 현재 작업 중단 시도
        logger.critical("🚨 VRAM Critical! Forcing Orchestrator to IDLE state...")
        await orchestrator.request_state_change(
            SystemState.IDLE, 
            reason="VRAM_CRITICAL_KILL_SWITCH", 
            force=True
        )
        
        # (선택) 필요하다면 여기서 ComfyUI에 'unload' 요청을 추가로 보낼 수도 있음
        # await image_service.unload_model()


async def on_vram_recovery(gpu_info) -> None:
    """Handle VRAM returning to normal levels."""
    logger.info(f"[VRAM NORMAL] Usage back to {gpu_info.usage_percent:.1f}%")


# =============================================================================
# Lifecycle Management
# =============================================================================

async def startup() -> None:
    """
    Initialize all services and the orchestrator.

    Startup Sequence:
        1. Load settings (pydantic_settings)
        2. Setup logging
        3. Create output directories
        4. Initialize LLM Service (Ollama)
        5. Initialize Image Service (ComfyUI)
        6. Initialize Document Service (CPU)
        7. Start VRAM Watchdog
        8. Initialize Orchestrator and register services
    """
    global settings, orchestrator, vram_watchdog, llm_service, image_service, doc_service, rag_service

    # 1. Load settings
    settings = get_settings()

    # 2. Setup logging
    setup_logging(settings.log_level)

    logger.info("=" * 60)
    logger.info("Mellow-Link Starting...")
    logger.info("=" * 60)

    # 2.5. Bootstrap admin account (create if not exists)
    logger.info("[Startup] Checking admin account...")
    if bootstrap_admin_account():
        logger.info("[Startup] Admin account ready")
    else:
        logger.warning("[Startup] Admin bootstrapping failed - manual setup may be required")

    # 3. Create directories
    settings.ensure_directories()

    # 4. Initialize LLM Service (Ollama)
    logger.info(f"[Startup] Connecting to Ollama at {settings.ollama_url}...")
    llm_service = create_llm_service(
        host=settings.ollama_host,
        port=settings.ollama_port,
        timeout=settings.ollama_timeout,
        models={
            "fast": settings.fast_model,
            "thinking": settings.thinking_model,
            "research": settings.research_model,
        }
    )
    try:
        await llm_service.connect()
        logger.info("[Startup] LLM Service connected")
    except Exception as e:
        logger.warning(f"[Startup] LLM Service connection failed: {e}")

    # 5. Initialize Image Service (ComfyUI)
    logger.info(f"[Startup] Connecting to ComfyUI at {settings.comfyui_url}...")
    image_service = create_image_service(
        host=settings.comfyui_host,
        port=settings.comfyui_port,
        timeout=settings.comfyui_timeout,
        output_dir=settings.image_output_dir
    )
    try:
        await image_service.connect()
        logger.info("[Startup] Image Service connected")
    except Exception as e:
        logger.warning(f"[Startup] Image Service connection failed: {e}")

    # 6. Initialize Document Service (CPU)
    logger.info("[Startup] Initializing Document Service...")
    doc_service = create_document_service(
        output_dir=settings.document_output_dir,
        max_workers=settings.doc_max_workers
    )
    await doc_service.initialize()
    logger.info("[Startup] Document Service initialized")

    # 6.5. Initialize RAG Service
    logger.info("[Startup] Initializing RAG Service...")
    try:
        rag_service = await create_rag_service(
            embedding_model="nomic-embed-text",
            chunk_size=500,
            ollama_url=settings.ollama_url
        )
        set_rag_service(rag_service)
        if rag_service.is_available():
            logger.info("[Startup] RAG Service initialized")
            # Load existing embeddings from database
            loaded_count = await rag_service.load_chunks_from_db()
            if loaded_count > 0:
                logger.info(f"[Startup] Restored {loaded_count} RAG embeddings from database")
        else:
            logger.warning("[Startup] RAG Service initialized but Ollama embeddings unavailable")
    except Exception as e:
        logger.warning(f"[Startup] RAG Service initialization failed: {e}")
        rag_service = None

    # 7. Initialize VRAM Watchdog
    logger.info("[Startup] Initializing VRAM Watchdog...")
    vram_watchdog = create_watchdog(
        warning_threshold=settings.vram_warning_threshold,
        critical_threshold=settings.vram_critical_threshold,
        poll_interval=settings.vram_poll_interval,
        device_id=settings.gpu_device_id
    )
    vram_watchdog.on_warning(on_vram_warning)
    vram_watchdog.on_critical(on_vram_critical)
    vram_watchdog.on_recovery(on_vram_recovery)

    if VRAMWatchdog.is_gpu_available():
        await vram_watchdog.start()
        logger.info("[Startup] VRAM Watchdog started")
    else:
        logger.warning("[Startup] No GPU detected - VRAM Watchdog disabled")

    # 8. Initialize Orchestrator
    logger.info("[Startup] Initializing Orchestrator...")
    orchestrator = Orchestrator()
    await orchestrator.initialize()

    # Register services with orchestrator
    orchestrator.register_service("llm", llm_service)
    orchestrator.register_service("chat", llm_service)
    orchestrator.register_service("text", llm_service)
    orchestrator.register_service("image", image_service)
    orchestrator.register_service("comfyui", image_service)
    orchestrator.register_service("document", doc_service)

    # 9. Initialize VTuber Relay Service
    logger.info("[Startup] Initializing VTuber Relay Service...")
    # Force /client-ws path for VTuber WebSocket endpoint
    avatar_ws_url = settings.avatar_ws_url.rstrip('/')
    if not avatar_ws_url.endswith('/client-ws'):
        avatar_ws_url = f"{avatar_ws_url}/client-ws"

    vtuber_relay = create_vtuber_relay(
        ws_url=avatar_ws_url,
        reconnect_interval=5.0
    )
    set_vtuber_relay(vtuber_relay)

    # Start VTuber relay in background (non-blocking)
    try:
        await vtuber_relay.start()
        logger.info(f"[Startup] VTuber Relay started (target: {settings.avatar_ws_url})")
    except Exception as e:
        logger.warning(f"[Startup] VTuber Relay start failed (will retry): {e}")

    logger.info("=" * 60)
    logger.info("Mellow-Link Ready!")
    logger.info(f"  Ollama:   {settings.ollama_url}")
    logger.info(f"  ComfyUI:  {settings.comfyui_url}")
    logger.info(f"  VTuber:   {settings.avatar_ws_url}")
    logger.info(f"  API:      http://{settings.api_host}:{settings.api_port}")
    logger.info("=" * 60)


async def shutdown() -> None:
    """
    Gracefully shutdown all services.

    Shutdown Sequence:
        1. Signal shutdown
        2. Stop VRAM Watchdog
        3. Stop VTuber Relay
        4. Shutdown Orchestrator
        5. Disconnect all services
    """
    global orchestrator, vram_watchdog, llm_service, image_service, doc_service, vtuber_relay

    logger.info("=" * 60)
    logger.info("Mellow-Link Shutting Down...")
    logger.info("=" * 60)

    shutdown_event.set()

    # Stop VRAM watchdog
    if vram_watchdog and vram_watchdog.is_running():
        await vram_watchdog.stop()
        logger.info("[Shutdown] VRAM Watchdog stopped")

    # Stop VTuber relay
    vtuber_relay = get_vtuber_relay()
    if vtuber_relay:
        await vtuber_relay.stop()
        logger.info("[Shutdown] VTuber Relay stopped")

    # Shutdown orchestrator
    if orchestrator:
        await orchestrator.shutdown()
        logger.info("[Shutdown] Orchestrator shutdown")

    # Disconnect services
    if llm_service:
        await llm_service.disconnect()
        logger.info("[Shutdown] LLM Service disconnected")

    if image_service:
        await image_service.disconnect()
        logger.info("[Shutdown] Image Service disconnected")

    if doc_service:
        await doc_service.shutdown()
        logger.info("[Shutdown] Document Service shutdown")

    logger.info("=" * 60)
    logger.info("Mellow-Link Stopped")
    logger.info("=" * 60)


# =============================================================================
# FastAPI Application
# =============================================================================

if FASTAPI_AVAILABLE:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan - startup and shutdown events."""
        await startup()
        yield
        await shutdown()

    # Create FastAPI app
    app = FastAPI(
        title="Mellow-Link",
        description="Local AI Orchestration - GPU sharing between LLM and Image Generation",
        version="0.1.0",
        lifespan=lifespan
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        print("\n" + "!"*50)
        print("!!! [GLOBAL CATCH] 서버 전체 비상 에러 포착 !!!")
        print(f"!!! 에러 주소: {request.url}")
        print(f"!!! 에러 메시지: {str(exc)}") if 'exc' in locals() else str(exc)
        print("!!! 상세 추적(Traceback):")
        traceback.print_exc()  # 여기서 범인의 지문이 무조건 나옴
        print("!"*50 + "\n")
        return JSONResponse(
            status_code=500,
            content={"message": "서버 내부 오류 발생", "detail": str(exc)}
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. 정적 파일 마운트 (Static Mount)
    # 프로젝트 루트 기준으로 경로 설정 (launcher.py에서 전달된 환경 변수 사용)
    project_root = os.environ.get("MELLOW_LINK_PROJECT_ROOT") or os.environ.get("PROJECT_ROOT")
    
    if project_root:
        # launcher.py에서 프로젝트 루트를 환경 변수로 전달한 경우
        logger.info(f"[Startup] 프로젝트 루트 기준 경로 사용: {project_root}")
        base_dir = project_root
        mellow_link_dir = os.path.join(project_root, "mellow_link")
        static_dir = os.path.join(mellow_link_dir, "static")
        outputs_dir = os.path.join(mellow_link_dir, "outputs")
    else:
        # 환경 변수가 없으면 현재 파일 위치 기준 (fallback)
        logger.info(f"[Startup] 현재 파일 기준 경로 사용 (fallback)")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(base_dir, "static")
        outputs_dir = os.path.join(base_dir, "outputs")
    
    # static 폴더 마운트
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        logger.info(f"[Startup] Static files mounted from: {static_dir}")
    else:
        logger.warning(f"[Startup] Static directory not found at: {static_dir}")

    # 3. outputs 폴더 마운트 (이미지 서빙용)
    os.makedirs(outputs_dir, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")
    logger.info(f"[Startup] Outputs directory mounted from: {outputs_dir}")

    # ==================== Avatar Launch Helper ====================

    def _launch_avatar_on_admin_login(admin_username: str) -> None:
        """
        Background task to launch Electron avatar app when admin logs in.

        서버가 이미 실행 중이면 Electron 앱만 실행합니다.
        서버가 실행 중이 아니면 서버를 먼저 실행한 후 Electron 앱을 실행합니다.

        Args:
            admin_username: Username of the admin who logged in (for logging)
        """
        import tempfile

        try:
            avatar_port = settings.avatar_ws_port if settings else DEFAULT_AVATAR_WS_PORT

            logger.info(f"[Avatar] Triggered by admin login: {admin_username}")
            logger.info(f"[Avatar] Target port: {avatar_port}")

            # 1. 서버가 실행 중인지 확인
            server_running = is_port_active(avatar_port)
            if server_running:
                logger.info(f"[Avatar] Server already active on port {avatar_port}")
            else:
                # 서버가 안 켜져있으면 먼저 실행
                logger.info(f"[Avatar] Server not running, launching...")
                success = launch_avatar_service(port=avatar_port)
                if not success:
                    logger.warning("[Avatar] Failed to launch avatar server")
                    return

            # 2. Electron 앱 실행 (Pet Mode)
            # 고정 경로: C:\Users\Hyein\AppData\Local\Programs\open-llm-vtuber\open-llm-vtuber-electron.exe
            target_exe = Path(r"C:\Users\Hyein\AppData\Local\Programs\open-llm-vtuber\open-llm-vtuber-electron.exe")

            if not target_exe.exists():
                logger.warning(f"[Avatar] Electron app not found: {target_exe}")
                return

            logger.info(f"[Avatar] Launching Electron app: {target_exe}")

            # 좀비 프로세스 정리
            exe_name = "open-llm-vtuber-electron.exe"
            try:
                kill_result = subprocess.run(
                    ["taskkill", "/F", "/IM", exe_name],
                    capture_output=True,
                    timeout=5
                )
                if kill_result.returncode == 0:
                    logger.info(f"[Avatar] Killed existing Electron process")
                    time.sleep(1.0)
            except Exception:
                pass  # 무시

            # Batch 파일을 통한 완전 독립 실행
            electron_working_dir = str(target_exe.parent.absolute())
            electron_exe_name = target_exe.name

            bat_content = f'''@echo off
cd /d "{electron_working_dir}"
start "" "{electron_exe_name}"
exit
'''
            temp_dir = tempfile.gettempdir()
            bat_path = os.path.join(temp_dir, "launch_electron_avatar.bat")

            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            logger.info(f"[Avatar] Batch file created: {bat_path}")

            # CMD를 통해 .bat 파일 실행 (Python과 완전 분리)
            cmd_command = f'start /b cmd /c "{bat_path}"'
            exit_code = os.system(cmd_command)

            if exit_code == 0:
                logger.info(f"[Avatar] Electron app launched successfully")
            else:
                logger.warning(f"[Avatar] Electron launch exit_code: {exit_code}")

        except Exception as e:
            logger.error(f"[Avatar] Error launching avatar: {e}")
            import traceback
            traceback.print_exc()

    # ==================== Request/Response Models ====================

    class ChatRequest(BaseModel):
        """Chat request model."""
        message: str = Field(..., description="User message")
        system_prompt: str = Field("", description="System prompt")
        mode: str = Field("thinking", description="Mode: fast, thinking, research, auto")
        session_id: Optional[str] = Field(None, description="Session ID for context")
        stream: bool = Field(True, description="Enable streaming")

    class StatusResponse(BaseModel):
        """System status response."""
        state: str
        is_running: bool
        queue_size: int
        active_tasks: int
        services: Dict[str, str]
        vram: Optional[Dict[str, Any]] = None
        uptime_seconds: float

    # ==================== Endpoints ====================

    # ---------- Authentication Endpoints ----------

    class RegisterRequest(BaseModel):
        """User registration request model."""
        username: str = Field(..., min_length=2, max_length=50, description="Username")
        password: str = Field(..., min_length=4, max_length=72, description="Password (max 72 chars for bcrypt)")

    class GuestLoginRequest(BaseModel):
        """Guest login request model."""
        access_code: str = Field(..., description="Guest access code")

    class GuestLoginResponse(BaseModel):
        """Guest login response model."""
        access_token: str
        token_type: str = "bearer"
        user_id: str = "guest"
        role: str = "guest"
        expires_in: int

    @app.post("/auth/register", tags=["Auth"])
    def register(user_data: RegisterRequest, db: Session = Depends(get_db)):
        """Register a new user with 'user' role."""
        try:
            # 1. Username validation
            username = user_data.username.strip()
            if not username:
                raise HTTPException(status_code=400, detail="사용자명을 입력해주세요")

            # 2. Password validation - prevent double hashing
            plain_password = user_data.password

            # Check if password looks like an already-hashed value (bcrypt starts with $2)
            if plain_password.startswith('$2') and len(plain_password) > 50:
                raise HTTPException(
                    status_code=400,
                    detail="잘못된 비밀번호 형식입니다. 일반 비밀번호를 입력해주세요."
                )

            # Enforce bcrypt 72-byte limit (check BEFORE hashing)
            password_bytes = plain_password.encode('utf-8')
            if len(password_bytes) > 72:
                raise HTTPException(
                    status_code=400,
                    detail=f"비밀번호가 너무 깁니다 (현재: {len(password_bytes)}바이트, 최대: 72바이트)"
                )

            # 3. Check for existing user
            if db.query(User).filter(User.username == username).first():
                raise HTTPException(status_code=400, detail="이미 존재하는 사용자명입니다")

            # 4. Hash password ONCE with plain text (wrap in try-except to catch passlib errors)
            try:
                hashed_pw = get_password_hash(plain_password)
            except ValueError as e:
                # Handle bcrypt length errors
                if "72 bytes" in str(e).lower() or "longer" in str(e).lower():
                    raise HTTPException(
                        status_code=400,
                        detail=f"비밀번호가 너무 깁니다 (최대 72바이트): {str(e)}"
                    )
                raise HTTPException(
                    status_code=400,
                    detail=f"비밀번호 해싱 실패: {str(e)}"
                )
            except Exception as e:
                logger.error(f"[Auth] Password hashing error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="비밀번호 처리 중 오류가 발생했습니다."
                )

            # 5. Create user
            user = User(
                username=username,
                hashed_password=hashed_pw,
                role=UserRole.USER.value
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # 6. Create default folders (passing role for admin-specific folders)
            create_default_folders_for_user(db, user.id, role=user.role)

            # 7. Generate token
            access_token = create_access_token(
                data={"sub": user.username},
                expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                role=user.role
            )

            logger.info(f"[Auth] User registered: {username}")

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "role": user.role
            }

        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is

        except Exception as e:
            logger.error(f"[Auth] Registration error: {e}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="회원가입 중 오류가 발생했습니다. 다시 시도해주세요."
            )


    @app.post("/auth/token", tags=["Auth"])
    def login(
        form: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db),
        background_tasks: BackgroundTasks = None
    ):
        """
        Login and get access token (includes role in response).

        [Security] Cancel/Abort 시 인증되지 않은 내부 로직 진입 방지
        [Feature] Admin login triggers avatar service launch in background
        """
        try:
            # 입력값 검증 (Cancel로 인한 빈 값 방지)
            if not form.username or not form.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username and password are required"
                )

            user = db.query(User).filter(User.username == form.username).first()
            
            # Validate password length before verification (bcrypt 72-byte limit)
            if user:
                password_bytes = form.password.encode('utf-8')
                if len(password_bytes) > 72:
                    logger.warning(f"[Auth] Password too long ({len(password_bytes)} bytes, max 72)")
                    raise HTTPException(
                        status_code=400,
                        detail="Password cannot be longer than 72 bytes"
                    )
                
                # Check if password appears to be already hashed (prevent double hashing)
                if form.password.startswith('$2') and len(form.password) > 50:
                    logger.warning(f"[Auth] Password appears to be already hashed")
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid password format"
                    )
            
            if not user or not verify_password(form.password, user.hashed_password):
                raise HTTPException(status_code=401, detail="Bad credentials")

            access_token = create_access_token(
                data={"sub": user.username},
                expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                role=user.role
            )

            if not access_token:
                raise AuthenticationCancelledError("Token creation failed")

            # [Admin Hook] Launch avatar service on admin login
            if is_admin_user(user):
                logger.info(f"[Auth] Admin login detected: {user.username}")
                if background_tasks:
                    background_tasks.add_task(_launch_avatar_on_admin_login, user.username)
                else:
                    # Fallback: synchronous launch (non-blocking via subprocess)
                    _launch_avatar_on_admin_login(user.username)

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "role": user.role
            }

        except (KeyboardInterrupt, SystemExit):
            logger.warning("[Auth] Login aborted by user")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login aborted"
            )

        except SQLAlchemyError as e:
            logger.error(f"[Auth] DB error during login: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable"
            )

        except AuthenticationInterruptedError as e:
            logger.warning(f"[Auth] Login interrupted: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login was interrupted"
            )

        except HTTPException:
            raise  # Re-raise HTTPExceptions as-is

        except Exception as e:
            logger.error(f"[Auth] Unexpected login error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed unexpectedly"
            )


    @app.post("/auth/guest-login", response_model=GuestLoginResponse, tags=["Auth"])
    async def guest_login(
        request: GuestLoginRequest,
        req: Request,
        db: Session = Depends(get_db)
    ):
        """
        Guest login with access code.

        Validates the access code against the configured GUEST_ACCESS_CODE.
        Checks IP-based daily usage limit (LIMIT_GUEST from .env).
        Returns a simple token for guest access.
        """
        import secrets
        import time

        # Validate access code
        expected_code = settings.guest_access_code if settings else "lucky777"

        if request.access_code != expected_code:
            raise HTTPException(
                status_code=401,
                detail="유효하지 않은 초대권입니다"
            )

        # Get client IP address
        client_ip = req.client.host if req.client else "unknown"
        # Check for forwarded IP (behind proxy/load balancer)
        forwarded_for = req.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        # Check IP-based daily usage limit
        limit_guest = settings.limit_guest if settings else 3
        is_allowed, current_count = check_guest_limit(db, client_ip, limit_guest)

        if not is_allowed:
            logger.warning(f"[Auth] Guest IP {client_ip} exceeded daily limit ({current_count}/{limit_guest})")
            raise HTTPException(
                status_code=429,
                detail=f"오늘의 게스트 사용량({limit_guest}회)을 초과했습니다. 내일 다시 시도하거나 회원가입하세요."
            )

        # Increment usage count
        new_count = increment_guest_usage(db, client_ip)

        # Generate simple guest token (include IP hash for tracking)
        timestamp = int(time.time())
        token_data = f"guest_{timestamp}_{secrets.token_urlsafe(16)}"
        expires_in = (settings.guest_token_expire_hours if settings else 24) * 3600

        logger.info(f"[Auth] Guest login successful (IP: {client_ip}, usage: {new_count}/{limit_guest})")

        return GuestLoginResponse(
            access_token=token_data,
            token_type="bearer",
            user_id="guest",
            role="guest",
            expires_in=expires_in
        )

    @app.get("/auth/me", tags=["Auth"])
    async def get_current_user_info(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Get current user info by validating the token.

        Returns actual DB user info if token is valid JWT.
        Returns guest info if token is a guest token (guest_xxx format).
        Returns 401 if no token or invalid token.
        """
        from jose import jwt, JWTError
        from mellow_link.infra.database import SECRET_KEY, ALGORITHM, User

        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No authorization token provided"
            )

        # Extract token from "Bearer xxx" format
        token = authorization.replace("Bearer ", "").strip()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty token provided"
            )

        # Check if this is a guest token (format: guest_timestamp_randomstring)
        if token.startswith("guest_"):
            return {
                "id": "guest",
                "username": "Guest",
                "role": "guest"
            }

        # Try to decode as JWT for registered users
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            role: str = payload.get("role", "user")

            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )

            # Fetch user from DB to verify existence and get latest info
            user = db.query(User).filter(User.username == username).first()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )

            return {
                "id": user.id,
                "username": user.username,
                "role": user.role
            }

        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )

    # ---------- Folders & Sessions Endpoints (with Auto-initialization) ----------

    @app.get("/folders", tags=["Folders"])
    async def get_folders(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Get user's folders.

        - Auto-creates default folders if none exist (404 protection)
        - Admin users get Secretary folder at top
        - Returns session_count for each folder
        - Returns empty list for guests
        """
        if not authorization:
            return []

        token = authorization.replace("Bearer ", "").strip()

        # Guest users get empty list
        if token.startswith("guest_"):
            return []

        try:
            from jose import jwt, JWTError
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            role = payload.get("role", UserRole.USER.value)

            if not username:
                return []

            user = db.query(User).filter(User.username == username).first()
            if not user:
                return []

            # Auto-create folders if none exist (404 protection)
            folders = ensure_user_has_folders(db, user.id, role=user.role)

            # Build response with session counts
            result = []
            for f in folders:
                session_count = db.query(ChatSession).filter(
                    ChatSession.folder_id == f.id,
                    ChatSession.is_active == True
                ).count()

                result.append({
                    "id": f.id,
                    "name": f.name,
                    "icon": f.icon,
                    "system_prompt": f.system_prompt,
                    "use_rag": f.use_rag,
                    "is_creative": f.is_creative,
                    "session_count": session_count
                })

            return result
        except Exception as e:
            logger.error(f"[Folders] Error loading folders: {e}")
            return []

    @app.post("/folders", tags=["Folders"])
    async def create_folder(
        request: Request,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Create a new folder for the user."""
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "").strip()
        if token.startswith("guest_"):
            raise HTTPException(status_code=403, detail="Guests cannot create folders")

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            body = await request.json()
            folder = AgentFolder(
                user_id=user.id,
                name=body.get("name", "New Folder"),
                icon=body.get("icon", "📁"),
                system_prompt=body.get("system_prompt", ""),
                use_rag=body.get("use_rag", False),
                is_creative=body.get("is_creative", False),
                rag_collection_name=body.get("rag_collection_name") or f"user_{user.id}_{body.get('name', 'folder').lower().replace(' ', '_')}"
            )
            db.add(folder)
            db.commit()
            db.refresh(folder)

            logger.info(f"[Folders] Created folder '{folder.name}' for user {user.id}")
            return {"id": folder.id, "name": folder.name, "icon": folder.icon}

        except Exception as e:
            logger.error(f"[Folders] Create error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/folders/{folder_id}", tags=["Folders"])
    async def update_folder(
        folder_id: int,
        request: Request,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Update a folder's settings."""
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "").strip()

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            folder = db.query(AgentFolder).filter(
                AgentFolder.id == folder_id,
                AgentFolder.user_id == user.id
            ).first()

            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            body = await request.json()
            if "name" in body:
                folder.name = body["name"]
            if "system_prompt" in body:
                folder.system_prompt = body["system_prompt"]
            if "is_creative" in body:
                folder.is_creative = body["is_creative"]
            if "use_rag" in body:
                folder.use_rag = body["use_rag"]
            if "icon" in body:
                folder.icon = body["icon"]

            db.commit()
            return {"success": True}

        except Exception as e:
            logger.error(f"[Folders] Update error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/folders/{folder_id}", tags=["Folders"])
    async def delete_folder(
        folder_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Delete a folder and all its sessions."""
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "").strip()

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            folder = db.query(AgentFolder).filter(
                AgentFolder.id == folder_id,
                AgentFolder.user_id == user.id
            ).first()

            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            db.delete(folder)
            db.commit()

            logger.info(f"[Folders] Deleted folder {folder_id} for user {user.id}")
            return {"success": True}

        except Exception as e:
            logger.error(f"[Folders] Delete error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/folders/{folder_id}/sessions", tags=["Folders"])
    async def get_folder_sessions(
        folder_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Get all sessions in a folder."""
        if not authorization:
            return []

        token = authorization.replace("Bearer ", "").strip()
        if token.startswith("guest_"):
            return []

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                return []

            sessions = db.query(ChatSession).filter(
                ChatSession.folder_id == folder_id,
                ChatSession.user_id == user.id,
                ChatSession.is_active == True
            ).order_by(ChatSession.created_at.desc()).all()

            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "created_at": s.created_at.isoformat() if s.created_at else None
                }
                for s in sessions
            ]

        except Exception as e:
            logger.error(f"[Folders] Get sessions error: {e}")
            return []

    @app.get("/folders/{folder_id}/documents", tags=["Folders"])
    async def get_folder_documents(
        folder_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Get all documents in a folder's RAG collection."""
        if not authorization:
            return []

        from mellow_link.infra import FolderDocument

        try:
            docs = db.query(FolderDocument).filter(
                FolderDocument.folder_id == folder_id
            ).all()

            return [
                {
                    "id": doc.id,
                    "filename": doc.filename,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
                }
                for doc in docs
            ]
        except Exception as e:
            logger.error(f"[Folders] Get documents error: {e}")
            return []

    @app.post("/folders/{folder_id}/upload", tags=["Folders"])
    async def upload_folder_document(
        folder_id: int,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Upload a document to a folder's RAG collection.

        - Immediately returns 200 OK to prevent spinner hang
        - Processes document embedding in background
        - Supports: PDF, DOCX, TXT, MD, HTML
        """
        from mellow_link.infra import FolderDocument
        from pathlib import Path

        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        # Validate file
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="No file uploaded")

        try:
            # Read file content immediately (before returning response)
            content_bytes = await file.read()
            filename = file.filename

            if not content_bytes or len(content_bytes) == 0:
                raise HTTPException(status_code=400, detail="Empty file")

            logger.info(f"[RAG Upload] Received file: {filename} ({len(content_bytes)} bytes) for folder {folder_id}")

            # Create document record in DB
            doc_record = FolderDocument(
                folder_id=folder_id,
                filename=filename,
                file_path=f"memory://{folder_id}/{filename}"  # Virtual path for in-memory processing
            )
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)
            document_id = doc_record.id

            logger.info(f"[RAG Upload] Created document record: id={document_id}")

            # Background task function (sync wrapper for async processing)
            def process_document_background_sync(
                folder_id: int,
                document_id: int,
                filename: str,
                content_bytes: bytes
            ):
                """Background task to process document embeddings (sync wrapper)."""
                import asyncio

                async def _process():
                    rag = get_rag_service()
                    if not rag:
                        logger.error(f"[RAG Upload] RAG service not available for document {document_id}")
                        return

                    try:
                        success, chunk_count, message = await rag.process_document(
                            folder_id=folder_id,
                            document_id=document_id,
                            filename=filename,
                            content_bytes=content_bytes
                        )

                        if success:
                            logger.info(f"[RAG Upload] Document {document_id} processed: {chunk_count} chunks")
                        else:
                            logger.error(f"[RAG Upload] Document {document_id} processing failed: {message}")

                    except Exception as e:
                        logger.error(f"[RAG Upload] Background processing error: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

                # Run async function in new event loop for background thread
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_process())
                finally:
                    loop.close()

            # Schedule background processing using FastAPI BackgroundTasks
            background_tasks.add_task(
                process_document_background_sync,
                folder_id=folder_id,
                document_id=document_id,
                filename=filename,
                content_bytes=content_bytes
            )

            # Return immediately to prevent spinner hang
            return {
                "success": True,
                "message": f"Document '{filename}' uploaded. Processing embeddings...",
                "document_id": document_id,
                "filename": filename,
                "size_bytes": len(content_bytes)
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[RAG Upload] Upload error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # =========================================================================
    # Temporary (Ephemeral) File Upload for One-time Chat Context
    # =========================================================================

    @app.post("/chat/upload-temp", tags=["Chat"])
    async def upload_temp_document(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        session_id: str = Form(...),
    ):
        """
        Upload a document for temporary/ephemeral chat context.

        - Stored in MEMORY ONLY (not in database)
        - Lost on server restart
        - For one-time file context in chat sessions
        - Returns immediately; processing happens in background

        Supports: PDF, DOCX, TXT, MD, HTML
        """
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="No file uploaded")

        if not session_id or not session_id.strip():
            raise HTTPException(status_code=400, detail="session_id is required")

        try:
            # Read file content immediately
            content_bytes = await file.read()
            filename = file.filename

            if not content_bytes or len(content_bytes) == 0:
                raise HTTPException(status_code=400, detail="Empty file")

            logger.info(f"[RAG Temp] Received temp file: {filename} ({len(content_bytes)} bytes) for session {session_id}")

            # Background task function (sync wrapper for async processing)
            def process_temp_document_sync(
                session_id: str,
                filename: str,
                content_bytes: bytes
            ):
                """Background task to process temp document embeddings (sync wrapper)."""
                import asyncio

                async def _process():
                    rag = get_rag_service()
                    if not rag:
                        logger.error(f"[RAG Temp] RAG service not available for session {session_id}")
                        return

                    try:
                        success, chunk_count, message = await rag.process_temp_document(
                            session_id=session_id,
                            filename=filename,
                            content_bytes=content_bytes
                        )

                        if success:
                            logger.info(f"[RAG Temp] Temp document processed: {chunk_count} chunks for session {session_id}")
                        else:
                            logger.error(f"[RAG Temp] Temp document processing failed: {message}")

                    except Exception as e:
                        logger.error(f"[RAG Temp] Background processing error: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

                # Run async function in new event loop for background thread
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_process())
                finally:
                    loop.close()

            # Schedule background processing using FastAPI BackgroundTasks
            background_tasks.add_task(
                process_temp_document_sync,
                session_id=session_id,
                filename=filename,
                content_bytes=content_bytes
            )

            # Return immediately to prevent spinner hang
            return {
                "success": True,
                "message": f"Temp document '{filename}' uploaded. Processing embeddings...",
                "session_id": session_id,
                "filename": filename,
                "size_bytes": len(content_bytes)
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[RAG Temp] Upload error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Temp upload failed: {str(e)}")

    @app.delete("/chat/temp/{session_id}", tags=["Chat"])
    async def clear_temp_session(session_id: str):
        """
        Clear all temporary documents for a session.

        Use this to free memory after a chat session ends.
        """
        rag = get_rag_service()
        if not rag:
            raise HTTPException(status_code=503, detail="RAG service not available")

        try:
            stats_before = rag.get_temp_stats(session_id)
            rag.clear_temp_session(session_id)

            return {
                "success": True,
                "message": f"Cleared temp session {session_id}",
                "chunks_cleared": stats_before.get("chunk_count", 0)
            }
        except Exception as e:
            logger.error(f"[RAG Temp] Clear error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/chat/temp/{session_id}/stats", tags=["Chat"])
    async def get_temp_session_stats(session_id: str):
        """Get statistics about temporary documents for a session."""
        rag = get_rag_service()
        if not rag:
            raise HTTPException(status_code=503, detail="RAG service not available")

        return rag.get_temp_stats(session_id)

    @app.delete("/folders/{folder_id}/documents/{doc_id}", tags=["Folders"])
    async def delete_folder_document(
        folder_id: int,
        doc_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """Delete a document from a folder's RAG collection."""
        from mellow_link.infra import FolderDocument, DocumentChunk

        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        try:
            # Delete from database
            doc = db.query(FolderDocument).filter(
                FolderDocument.id == doc_id,
                FolderDocument.folder_id == folder_id
            ).first()

            if doc:
                # Delete associated chunks from DB first (for persistence)
                deleted_chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc_id
                ).delete()
                logger.info(f"[RAG Delete] Deleted {deleted_chunks} chunks from database")

                # Delete the document record
                db.delete(doc)
                db.commit()

                # Clear from RAG memory cache
                rag = get_rag_service()
                if rag:
                    rag.clear_document_from_cache(folder_id, doc_id)

                logger.info(f"[RAG Delete] Deleted document {doc_id} from folder {folder_id}")
                return {"success": True, "message": "Document deleted"}
            else:
                return {"success": False, "message": "Document not found"}

        except Exception as e:
            logger.error(f"[RAG Delete] Delete error: {e}")
            return {"success": False, "message": str(e)}

    @app.get("/chat/sessions", tags=["Chat"])
    async def get_chat_sessions(
        folder_id: Optional[int] = None,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Get user's chat sessions.
        Returns empty list for guests or when no sessions exist.
        Optionally filter by folder_id.
        """
        from mellow_link.infra.database import ChatSession

        if not authorization:
            return []

        token = authorization.replace("Bearer ", "").strip()

        # Guest users get empty list
        if token.startswith("guest_"):
            return []

        # Try to get user's sessions
        try:
            from jose import jwt, JWTError
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            if not username:
                return []

            user = db.query(User).filter(User.username == username).first()
            if not user:
                return []

            query = db.query(ChatSession).filter(
                ChatSession.user_id == user.id,
                ChatSession.is_active == True
            )

            if folder_id is not None:
                query = query.filter(ChatSession.folder_id == folder_id)

            sessions = query.order_by(ChatSession.created_at.desc()).limit(50).all()

            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "folder_id": s.folder_id,
                    "created_at": s.created_at.isoformat() if s.created_at else None
                }
                for s in sessions
            ]
        except Exception:
            return []

    @app.get("/chat/sessions/uncategorized", tags=["Chat"])
    async def get_uncategorized_sessions(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Get user's uncategorized chat sessions (sessions without a folder).
        Returns empty list for guests.
        """
        from mellow_link.infra.database import ChatSession

        if not authorization:
            return []

        token = authorization.replace("Bearer ", "").strip()

        # Guest users get empty list
        if token.startswith("guest_"):
            return []

        try:
            from jose import jwt, JWTError
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            if not username:
                return []

            user = db.query(User).filter(User.username == username).first()
            if not user:
                return []

            # Get sessions without folder (folder_id is None)
            sessions = db.query(ChatSession).filter(
                ChatSession.user_id == user.id,
                ChatSession.folder_id == None,
                ChatSession.is_active == True
            ).order_by(ChatSession.created_at.desc()).limit(50).all()

            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "folder_id": None,
                    "created_at": s.created_at.isoformat() if s.created_at else None
                }
                for s in sessions
            ]
        except Exception as e:
            logger.error(f"[Chat] Error getting uncategorized sessions: {e}")
            return []

    @app.get("/chat/sessions/{session_id}/messages", tags=["Chat"])
    async def get_session_messages(
        session_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Get all messages for a specific chat session.
        Returns messages sorted by created_at in ascending order.
        Only the session owner can access their messages.
        """
        from mellow_link.infra.database import ChatSession, ChatMessage

        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "").strip()

        if token.startswith("guest_"):
            raise HTTPException(status_code=403, detail="Guests cannot access messages")

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            if not username:
                raise HTTPException(status_code=401, detail="Invalid token")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Verify session belongs to user
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user.id
            ).first()

            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Get all messages for this session, sorted by timestamp (correct field name)
            messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id
            ).order_by(ChatMessage.timestamp.asc()).all()

            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.timestamp.isoformat() if msg.timestamp else None
                }
                for msg in messages
            ]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[Chat] Error getting session messages: {e}")
            logger.exception(f"[Chat] Full error traceback:")
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.delete("/chat/sessions/{session_id}", tags=["Chat"])
    async def delete_chat_session(
        session_id: int,
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Delete a chat session (soft delete - marks as inactive).
        Only the session owner can delete their session.
        """
        from mellow_link.infra.database import ChatSession

        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "").strip()

        if token.startswith("guest_"):
            raise HTTPException(status_code=403, detail="Guests cannot delete sessions")

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            if not username:
                raise HTTPException(status_code=401, detail="Invalid token")

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Find session owned by user
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user.id
            ).first()

            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Soft delete (mark as inactive)
            session.is_active = False
            db.commit()

            logger.info(f"[Chat] Session {session_id} deleted by user {user.id}")
            return {"success": True, "deleted_id": session_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[Chat] Error deleting session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(os.path.join(static_dir, "favicon.ico"))

    @app.get("/ui", include_in_schema=False)
    async def serve_ui() -> FileResponse:
        """Serve the main UI (index.html)."""
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/", tags=["System"], include_in_schema=False)
    async def root():
        """Root endpoint - redirect to /ui."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/ui")

    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint."""
        services_health = {}

        if llm_service:
            services_health["llm"] = await llm_service.health_check()
        if image_service:
            services_health["image"] = await image_service.health_check()
        if doc_service:
            services_health["document"] = await doc_service.health_check()
        if vram_watchdog:
            services_health["vram"] = await vram_watchdog.health_check()

        orchestrator_health = {}
        if orchestrator:
            orchestrator_health = await orchestrator.health_check()

        return {
            "healthy": all(
                s.get("healthy", False) if isinstance(s, dict) else s
                for s in services_health.values()
            ),
            "timestamp": datetime.now().isoformat(),
            "orchestrator": orchestrator_health,
            "services": services_health
        }

    @app.get("/status", response_model=StatusResponse, tags=["System"])
    async def get_status():
        """Get current system status including VRAM."""
        vram_info = None
        if vram_watchdog:
            gpu_info = vram_watchdog.get_last_info()
            if gpu_info:
                vram_info = gpu_info.to_dict()

        services = {}
        if llm_service:
            services["llm"] = llm_service.get_status().name
        if image_service:
            services["image"] = image_service.get_status().name
        if doc_service:
            services["document"] = doc_service.get_status().name

        health = await orchestrator.health_check() if orchestrator else {}

        return StatusResponse(
            state=orchestrator.get_state().name if orchestrator else "NOT_INITIALIZED",
            is_running=health.get("is_running", False),
            queue_size=health.get("queue_size", 0),
            active_tasks=health.get("active_tasks", 0),
            services=services,
            vram=vram_info,
            uptime_seconds=health.get("uptime_seconds", 0)
        )

    # ---------- Session-Aware Chat Endpoint (/chat/ask) ----------

    @app.post("/chat/ask", tags=["Chat"])
    async def chat_ask(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
    ):
        """
        Session-aware chat endpoint.

        - Auto-creates session if session_id is not provided
        - Saves messages to database
        - Streams response via SSE
        - Returns session metadata on completion
        """
        from mellow_link.infra.database import ChatMessage, ChatSession, AgentFolder

        body = await request.json()
        question = body.get("question", "").strip()
        session_id = body.get("session_id")
        folder_id = body.get("folder_id")
        mode = body.get("mode", "general")
        skip_user_message = body.get("skip_user_message", False)

        if not question:
            raise HTTPException(status_code=400, detail="Question is required")

        # Get user from authorization header
        auth_header = request.headers.get("Authorization", "")
        user = None
        user_id = None

        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
            if not token.startswith("guest_"):
                try:
                    from jose import jwt
                    from mellow_link.infra.database import SECRET_KEY, ALGORITHM
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    username = payload.get("sub")
                    if username:
                        user = db.query(User).filter(User.username == username).first()
                        user_id = user.id if user else None
                except Exception:
                    pass

        # Get or create session
        session = None
        system_prompt = "You are a helpful AI assistant."

        if session_id:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            
            # [CRITICAL FIX] Load conversation history from DB when reopening session
            # This ensures LLM context is restored and AI doesn't lose memory
            if session:
                logger.info(f"[ChatAsk] Loading conversation history for session {session_id}")
                context_id_str = str(session_id)
                
                # Load all previous messages from DB
                previous_messages = db.query(ChatMessage).filter(
                    ChatMessage.session_id == session_id
                ).order_by(ChatMessage.timestamp.asc()).all()
                
                # Restore LLM context from DB history
                if previous_messages and llm_service:
                    try:
                        # Get or create context for this session
                        context = llm_service._get_context(context_id_str)
                        
                        # Clear existing context and restore from DB
                        context.messages.clear()
                        
                        # Restore system prompt if session has folder
                        if session.folder_id:
                            folder = db.query(AgentFolder).filter(AgentFolder.id == session.folder_id).first()
                            if folder and folder.system_prompt:
                                context.system_prompt = folder.system_prompt
                        
                        # Restore all previous messages to LLM context
                        for msg in previous_messages:
                            context.add_message(msg.role, msg.content)
                        
                        logger.info(f"[ChatAsk] Restored {len(previous_messages)} messages to LLM context for session {session_id}")
                    except Exception as context_err:
                        logger.warning(f"[ChatAsk] Failed to restore LLM context: {context_err}")

        if not session and user_id:
            # Auto-create session
            if folder_id:
                folder = db.query(AgentFolder).filter(AgentFolder.id == folder_id).first()
                if folder:
                    system_prompt = folder.system_prompt or system_prompt
                    session = ChatSession(
                        user_id=user_id,
                        folder_id=folder_id,
                        title=question[:50] + "..." if len(question) > 50 else question,
                        is_active=True
                    )
            else:
                # Uncategorized session
                session = ChatSession(
                    user_id=user_id,
                    folder_id=None,
                    title=question[:50] + "..." if len(question) > 50 else question,
                    is_active=True
                )

            if session:
                db.add(session)
                db.commit()
                db.refresh(session)
                session_id = session.id
                logger.info(f"[ChatAsk] Auto-created session {session_id} for user {user_id}")

        # Get system prompt from folder if session exists
        if session and session.folder_id:
            folder = db.query(AgentFolder).filter(AgentFolder.id == session.folder_id).first()
            if folder and folder.system_prompt:
                system_prompt = folder.system_prompt

        # =====================================================================
        # [Mellow-Link Architect Patch] Section 6 & 2.4 Implementation
        # 1. 조건부 페르소나 (Conditional Persona)
        # 2. 언어 가드레일 (Language Guardrail)
        # =====================================================================

        # 1. VTuber 연결 상태 확인
        relay = get_vtuber_relay()
        is_vtuber_active = relay and relay.is_connected

        # 2. 페르소나 결정 (VTuber 연결 시 어벤츄린 강제 적용)
        selected_persona_content = ""

        if is_vtuber_active:
            # [Mode: Aventurine]
            persona_path = os.path.join("mellow_link", "prompts", "aventurine_persona_v1.txt")
            try:
                if os.path.exists(persona_path):
                    with open(persona_path, "r", encoding="utf-8") as f:
                        selected_persona_content = f.read().strip()
                else:
                    logger.warning(f"[Persona] File not found: {persona_path}")
                    selected_persona_content = "당신은 '어벤츄린'입니다. 반말을 사용하고, 능글맞은 도박사처럼 행동하세요."
            except Exception as e:
                logger.error(f"[Persona] Error loading persona: {e}")
        else:
            # [Mode: Default Assistant]
            # 폴더별 설정이 있으면 우선시하고, 없으면 기본값 사용
            if session and session.folder_id:
                folder = db.query(AgentFolder).filter(AgentFolder.id == session.folder_id).first()
                if folder and folder.system_prompt:
                    selected_persona_content = folder.system_prompt

            # 폴더 설정도 없으면 기본값
            if not selected_persona_content:
                selected_persona_content = "당신은 유능한 AI 조수입니다."

        # 3. 언어 가드레일 (Language Guardrail) - 강력한 한자/중국어 방어
        # Web과 VTuber 모두에게 적용되지만, 말투(해요체/반말)는 페르소나에 따라 달라짐
        mandatory_guardrail = (
            "IMPORTANT RULES:\n"
            "1. LANGUAGE: Korean (한글) ONLY. No English, No Chinese.\n"
            "2. NO HANJA: 한자(漢字) 및 중국어 표현을 절대 사용하지 마세요. (예: 確認 -> 확인)\n"
        )

        # =====================================================================
        # [RAG Context Injection] - 문서 기반 답변 최우선
        # =====================================================================
        rag_context_section = ""
        rag_used = False
        current_folder = None

        # Check if folder has RAG enabled
        if session and session.folder_id:
            current_folder = db.query(AgentFolder).filter(AgentFolder.id == session.folder_id).first()

        if current_folder and current_folder.use_rag:
            logger.info(f"[RAG] Folder {current_folder.id} has RAG enabled, searching documents...")

            rag = get_rag_service()
            if rag and rag.is_available():
                try:
                    # Search for relevant chunks
                    search_results = await rag.search(
                        query=question,
                        folder_id=current_folder.id,
                        top_k=3,
                        min_score=0.3
                    )

                    if search_results:
                        rag_used = True
                        context_parts = []
                        for i, result in enumerate(search_results, 1):
                            context_parts.append(
                                f"[Source {i}: {result.filename}]\n{result.content}"
                            )
                            logger.info(f"[RAG] Found chunk from {result.filename} (score={result.score:.3f})")

                        rag_context_section = (
                            "\n\n=== DOCUMENT CONTEXT (최우선 참조) ===\n"
                            + "\n\n".join(context_parts)
                            + "\n\n"
                            + "CRITICAL INSTRUCTION:\n"
                            + "1. 위 문서 내용에 기반하여 사실적으로 답변하세요.\n"
                            + "2. 문서에 없는 내용은 추측하거나 지어내지 마세요.\n"
                            + "3. 문서에서 찾을 수 없는 정보는 '문서에서 해당 정보를 찾을 수 없습니다'라고 답변하세요.\n"
                            + "4. 아래 페르소나는 '말투'로만 사용하고, 내용은 반드시 문서 기반으로 답변하세요.\n"
                            + "=== END OF DOCUMENT CONTEXT ===\n"
                        )
                        logger.info(f"[RAG] Injected {len(search_results)} chunks into system prompt")
                    else:
                        logger.info(f"[RAG] No relevant documents found for query")

                except Exception as rag_err:
                    logger.error(f"[RAG] Search error: {rag_err}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.warning(f"[RAG] RAG service not available")

        # 4. 최종 시스템 프롬프트 합성
        # 우선순위: 가드레일 > RAG Context > 페르소나(말투)
        if rag_context_section:
            # RAG가 활성화된 경우: 문서 내용 최우선, 페르소나는 말투로만 사용
            system_prompt = (
                f"{mandatory_guardrail}"
                f"{rag_context_section}"
                f"\n[Character/Tone (말투만 참조)]\n{selected_persona_content}"
            )
        else:
            # RAG가 비활성화된 경우: 기존 방식 (일반 대화)
            system_prompt = f"{mandatory_guardrail}\n\n[Character Context]\n{selected_persona_content}"

        logger.info(f"[System] Persona Active: {'Aventurine (VTuber)' if is_vtuber_active else 'Default (Web)'}, RAG Used: {rag_used}")

        # Save user message (if not skipped) - ensure DB save with error handling
        user_message_id = None
        if session and not skip_user_message:
            try:
                user_msg = ChatMessage(
                    session_id=session.id,
                    role="user",
                    content=question
                )
                db.add(user_msg)
                db.commit()
                db.refresh(user_msg)
                user_message_id = user_msg.id
                logger.info(f"[ChatAsk] Saved user message {user_message_id} to session {session.id}")
            except Exception as db_err:
                logger.error(f"[ChatAsk] Failed to save user message to DB: {db_err}")
                db.rollback()
                # Continue even if DB save fails

        # Check LLM availability
        if not llm_service or not llm_service.is_available():
            raise HTTPException(status_code=503, detail="LLM Service unavailable")

        # Request state transition
        if orchestrator:
            await orchestrator.request_state_change(
                SystemState.TEXT,
                reason=f"Chat ask (mode: {mode})"
            )

        import time
        start_time = time.time()

        async def stream_generator():
            full_response = ""
            try:
                # Convert session_id to string for LLM context (context_id expects str)
                context_id_str = str(session_id) if session_id else None
                
                async for chunk in llm_service.generate_stream(
                    prompt=question,
                    system_prompt=system_prompt,
                    mode=mode,
                    context_id=context_id_str
                ):
                    full_response += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"

                # Calculate processing time
                processing_time = time.time() - start_time

                # Save assistant message (ensure DB save with error handling)
                assistant_message_id = None
                if session:
                    try:
                        assistant_msg = ChatMessage(
                            session_id=session.id,
                            role="assistant",
                            content=full_response,
                            rag_used=rag_used  # Store RAG usage flag
                        )
                        db.add(assistant_msg)
                        db.commit()
                        db.refresh(assistant_msg)
                        assistant_message_id = assistant_msg.id
                        logger.info(f"[ChatAsk] Saved assistant message {assistant_message_id} to session {session.id} (rag_used={rag_used})")
                    except Exception as db_err:
                        logger.error(f"[ChatAsk] Failed to save assistant message to DB: {db_err}")
                        db.rollback()
                        # Continue even if DB save fails

                # Send completion metadata
                yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'message_id': assistant_message_id, 'processing_time': processing_time, 'rag_used': rag_used})}\n\n"

                # =====================================================
                # [CRITICAL FIX] Send response to Avatar for TTS/motion
                # =====================================================
                relay = get_vtuber_relay()
                if relay and relay.is_connected and full_response:
                    try:
                        # [STABILITY FIX] Clean text before sending to avatar
                        # Remove brackets [], special symbols, mechanical prefixes, and other TTS-breaking characters
                        import re
                        cleaned_response = full_response
                        
                        # [QUALITY FIX] Remove mechanical prefixes that AI adds unnecessarily
                        # Remove common prefixes like "답변은:", "답변:", "AI:", "The answer is:", etc.
                        prefix_patterns = [
                            r'^(답변은|답변|응답은|응답|다음과 같이|다음과|AI|The answer is|Answer:|답변드리면|답변드리겠습니다|말씀드리면|말씀드리겠습니다)[:：\s]+',
                            r'^(안녕하세요|Hello|Hi)[,，\s]+',
                        ]
                        for pattern in prefix_patterns:
                            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.IGNORECASE | re.MULTILINE)
                        
                        # Remove square brackets and their contents: [Hello, my name is...] -> (empty)
                        cleaned_response = re.sub(r'\[.*?\]', '', cleaned_response)
                        
                        # Remove parentheses content (optional, but can help): (text) -> (empty)
                        # Uncomment if needed: cleaned_response = re.sub(r'\(.*?\)', '', cleaned_response)
                        
                        # Remove multiple spaces and clean up
                        cleaned_response = re.sub(r'\s+', ' ', cleaned_response)
                        cleaned_response = cleaned_response.strip()
                        
                        # Remove other problematic characters that might break TTS
                        # Remove markdown-style emphasis: **text**, *text*, __text__, _text_
                        cleaned_response = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_response)
                        cleaned_response = re.sub(r'\*([^*]+)\*', r'\1', cleaned_response)
                        cleaned_response = re.sub(r'__([^_]+)__', r'\1', cleaned_response)
                        cleaned_response = re.sub(r'_([^_]+)_', r'\1', cleaned_response)
                        
                        # Remove leading/trailing special punctuation that might cause issues
                        cleaned_response = cleaned_response.strip('.,;:!?-')
                        
                        # Final cleanup: remove any remaining special characters that are problematic
                        # [STABILITY FIX] Removed '一-龯' range to strip all Hanja/Chinese characters
                        # Keep only letters, numbers, spaces, basic punctuation, and Korean/Japanese characters
                        cleaned_response = re.sub(r'[^\w\s가-힣.,!?;:()\-\'"]+', '', cleaned_response, flags=re.UNICODE)
                        
                        # Skip if cleaned response is empty
                        if not cleaned_response or len(cleaned_response.strip()) == 0:
                            logger.warning("[Avatar] Cleaned response is empty, skipping TTS")
                            cleaned_response = full_response  # Fallback to original
                        
                        # Get folder name for context (Secretary has higher priority)
                        folder_name = None
                        if session and session.folder_id:
                            folder = db.query(AgentFolder).filter(AgentFolder.id == session.folder_id).first()
                            if folder:
                                folder_name = folder.name

                        logger.info(f"[Avatar] Sending cleaned text to avatar: {cleaned_response[:100]}... (original length: {len(full_response)}, cleaned: {len(cleaned_response)})")
                        success = await relay.relay_llm_response(
                            response_text=cleaned_response,
                            session_id=session_id,
                            folder_name=folder_name
                        )
                        if success:
                            logger.info(f"[Avatar] Text sent successfully (length={len(full_response)})")
                        else:
                            logger.warning("[Avatar] Failed to queue message")
                    except Exception as avatar_err:
                        logger.error(f"[Avatar] Error sending to avatar: {avatar_err}")
                elif relay and not relay.is_connected:
                    logger.debug("[Avatar] Relay not connected, skipping TTS")

            except Exception as e:
                logger.error(f"[ChatAsk] Streaming error: {e}")
                yield f"data: {json.dumps({'error': True, 'message': str(e)})}\n\n"
            finally:
                if orchestrator:
                    await orchestrator.request_state_change(
                        SystemState.IDLE, reason="Chat ask complete"
                    )

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream"
        )

    # ---------- Chat Endpoint ----------

    @app.post("/chat", tags=["LLM"])
    async def chat(request: ChatRequest):
        """
        Chat with the LLM.

        Delegates to Orchestrator which manages GPU state transitions.
        Supports both streaming and non-streaming responses.
        """
        if not llm_service or not llm_service.is_available():
            raise HTTPException(status_code=503, detail="LLM Service unavailable")
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Orchestrator not initialized")

        # Request state transition to TEXT (LLM)
        result = await orchestrator.request_state_change(
            SystemState.TEXT,
            reason=f"Chat request (mode: {request.mode})"
        )

        if result == TransitionResult.INVALID_TRANSITION:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot chat: system in {orchestrator.get_state().name} state"
            )

        try:
            if request.stream:
                # Streaming response
                async def stream_generator():
                    try:
                        async for chunk in llm_service.generate_stream(
                            prompt=request.message,
                            system_prompt=request.system_prompt,
                            mode=request.mode,
                            context_id=request.session_id
                        ):
                            yield f"data: {chunk}\n\n"
                        yield "data: [DONE]\n\n"
                    finally:
                        await orchestrator.request_state_change(
                            SystemState.IDLE, reason="Chat stream complete"
                        )

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream"
                )
            else:
                # Non-streaming response
                gen_result = await llm_service.generate(
                    prompt=request.message,
                    system_prompt=request.system_prompt,
                    mode=request.mode,
                    context_id=request.session_id
                )

                return {
                    "response": gen_result.content,
                    "model": gen_result.model,
                    "mode": request.mode,
                    "tokens": gen_result.eval_count,
                    "duration_ms": gen_result.total_duration_ms
                }
        finally:
            if not request.stream:
                await orchestrator.request_state_change(
                    SystemState.IDLE, reason="Chat complete"
                )

    # ---------- Image Generation Endpoint ----------

    @app.post("/generate-image", tags=["Image"])
    async def generate_image(request: ImageRequest):
        """
        Generate an image using ComfyUI.

        Delegates to Orchestrator which manages GPU state transitions.
        Blocks until image generation is complete.
        """
        if not image_service or not image_service.is_available():
            raise HTTPException(status_code=503, detail="Image Service unavailable")
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Orchestrator not initialized")

        # Request state transition to IMAGE
        result = await orchestrator.request_state_change(
            SystemState.IMAGE,
            reason="Image generation request"
        )

        if result == TransitionResult.INVALID_TRANSITION:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot generate image: system in {orchestrator.get_state().name} state"
            )

        try:
            img_request = ImageRequest(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                width=request.width,
                height=request.height,
                steps=request.steps,
                cfg_scale=request.cfg_scale,
                seed=request.seed,
                model=request.model or (settings.default_checkpoint if settings else "")
            )

            # Generate (blocks until complete via WebSocket)
            img_result = await image_service.generate(img_request)

            return {
                "success": True,
                "images": [str(p) for p in img_result.images],
                "prompt_id": img_result.prompt_id,
                "seed": img_result.seed_used,
                "duration_ms": img_result.generation_time_ms
            }

        except TimeoutError as e:
            raise HTTPException(status_code=504, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            await orchestrator.request_state_change(
                SystemState.IDLE, reason="Image generation complete"
            )

    # ---------- Document Endpoint ----------

    @app.post("/generate-document", tags=["Document"])
    async def generate_document(
        content: str,
        output_type: str = "docx",
        title: str = "Document"
    ):
        """Generate a document (runs on CPU, does not affect GPU)."""
        if not doc_service or not doc_service.is_available():
            raise HTTPException(status_code=503, detail="Document Service unavailable")

        try:
            doc_type_map = {
                "pdf": DocumentType.PDF,
                "docx": DocumentType.DOCX,
                "html": DocumentType.HTML,
                "md": DocumentType.MARKDOWN,
            }

            doc_request = DocumentRequest(
                content=content,
                output_type=doc_type_map.get(output_type.lower(), DocumentType.DOCX),
                title=title
            )

            result = await doc_service.generate(doc_request)

            return {
                "success": True,
                "path": str(result.output_path),
                "type": result.output_type.value,
                "size_bytes": result.file_size_bytes,
                "duration_ms": result.generation_time_ms
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ---------- VRAM Endpoint ----------

    @app.get("/vram", tags=["System"])
    async def vram_status():
        """Get current VRAM status."""
        if not vram_watchdog:
            return {"available": False, "message": "VRAM Watchdog not initialized"}

        gpu_info = await vram_watchdog.force_check()
        if not gpu_info:
            return {"available": False, "message": "No GPU detected"}

        return {
            "available": True,
            "status": vram_watchdog.get_status().name,
            "gpu": gpu_info.to_dict(),
            "thresholds": {
                "warning": vram_watchdog.warning_threshold,
                "critical": vram_watchdog.critical_threshold
            }
        }

    @app.get("/vram-status", tags=["System"])
    async def vram_status_simple():
        """
        Get simplified VRAM status for frontend widget.

        Returns:
            { used: MB, total: MB, percent: 0-100 }
        """
        if not vram_watchdog:
            return {"used": 0, "total": 0, "percent": 0}

        gpu_info = await vram_watchdog.force_check()
        if not gpu_info:
            return {"used": 0, "total": 0, "percent": 0}

        return {
            "used": gpu_info.used_memory_mb,
            "total": gpu_info.total_memory_mb,
            "percent": gpu_info.usage_percent
        }

    # ---------- VTuber/Avatar Endpoints ----------

    @app.get("/avatar/status", tags=["Avatar"])
    async def get_avatar_status_endpoint():
        """
        Get VTuber avatar service status.

        Returns connection status, port info, and relay status.
        """
        avatar_status = get_avatar_status(port=settings.avatar_ws_port if settings else DEFAULT_AVATAR_WS_PORT)
        relay = get_vtuber_relay()

        return {
            "avatar_service": avatar_status,
            "relay": relay.get_status() if relay else {"connected": False, "status": "not_initialized"},
            "config": {
                "ws_port": settings.avatar_ws_port if settings else DEFAULT_AVATAR_WS_PORT,
                "ws_url": settings.avatar_ws_url if settings else "ws://localhost:12393"
            }
        }

    @app.post("/avatar/speak", tags=["Avatar"])
    async def avatar_speak(
        text: str,
        emotion: str = "neutral",
        authorization: str = Header(None)
    ):
        """
        Send text to VTuber avatar for speech synthesis.

        Only available for authenticated users (admin has priority).
        """
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")

        relay = get_vtuber_relay()
        if not relay:
            raise HTTPException(status_code=503, detail="VTuber relay not initialized")

        if not relay.is_connected:
            raise HTTPException(status_code=503, detail="VTuber not connected")

        success = await relay.send_text(text, emotion=emotion)
        return {"success": success, "text": text[:100], "emotion": emotion}

    # ---------- Admin Endpoints ----------

    @app.post("/admin/launch_avatar", tags=["Admin"])
    async def launch_avatar(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Admin 전용 아바타 런칭 시스템.
        
        VTuber 백엔드 서버를 실행하고, Electron 앱을 시작하며, 첫 인사를 전송합니다.
        """
        global vtuber_proc
        
        # 1. 권한 체크
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Guest 토큰 체크
        if token.startswith("guest_"):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # JWT 토큰 디코딩 및 사용자 확인
        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM
            
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            role = payload.get("role", UserRole.USER.value)
            
            if not username:
                raise HTTPException(status_code=401, detail="Invalid token payload")
            
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            # Admin 권한 체크
            if user.role != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Admin access required")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        # 2. 중복 실행 방지
        if vtuber_proc is not None and vtuber_proc.poll() is None:
            # 프로세스가 실행 중
            return {
                "success": False,
                "message": "VTuber 서버가 이미 실행 중입니다.",
                "pid": vtuber_proc.pid
            }
        
        # 포트 체크 (추가 안전장치)
        try:
            response = requests.get("http://localhost:12393", timeout=2)
            if response.status_code == 200:
                return {
                    "success": False,
                    "message": "VTuber 서버가 이미 실행 중입니다 (포트 12393 활성)."
                }
        except requests.RequestException:
            pass  # 서버가 실행 중이지 않음, 계속 진행
        
        # 3. 백엔드 실행
        project_root = os.environ.get("MELLOW_LINK_PROJECT_ROOT")
        if not project_root:
            raise HTTPException(status_code=500, detail="MELLOW_LINK_PROJECT_ROOT 환경 변수가 설정되지 않았습니다.")
        
        project_root_path = Path(project_root)
        vtuber_dir = project_root_path / "Open-LLM-VTuber"
        
        if not vtuber_dir.exists():
            raise HTTPException(status_code=404, detail=f"Open-LLM-VTuber 디렉토리를 찾을 수 없습니다: {vtuber_dir}")
        
        vtuber_cwd = str(vtuber_dir.absolute())
        vtuber_script_path = vtuber_dir / "run_server.py"
        
        if not vtuber_script_path.exists():
            raise HTTPException(status_code=404, detail=f"run_server.py를 찾을 수 없습니다: {vtuber_script_path}")
        
        try:
            # 환경 변수 설정
            env = os.environ.copy()
            
            # Python 실행 파일 (sys.executable 사용)
            python_exe = sys.executable
            
            logger.info(f"[Admin] VTuber 백엔드 실행 시작: {python_exe} {vtuber_script_path}")
            logger.info(f"[Admin] Working directory: {vtuber_cwd}")
            
            # 프로세스 실행
            vtuber_proc = subprocess.Popen(
                [python_exe, "run_server.py"],
                cwd=vtuber_cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            logger.info(f"[Admin] VTuber 프로세스 시작됨 (PID: {vtuber_proc.pid})")
            
            # 프로세스가 즉시 종료되었는지 확인
            time.sleep(1.0)
            if vtuber_proc.poll() is not None:
                stdout, _ = vtuber_proc.communicate(timeout=2)
                error_msg = stdout[-500:] if stdout else "Unknown error"
                logger.error(f"[Admin] VTuber 프로세스가 즉시 종료됨: {error_msg}")
                vtuber_proc = None
                raise HTTPException(
                    status_code=500,
                    detail=f"VTuber 서버 시작 실패: {error_msg[-200:]}"
                )
        
        except Exception as e:
            vtuber_proc = None
            logger.error(f"[Admin] VTuber 서버 시작 중 오류: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"VTuber 서버 시작 실패: {str(e)}")
        
        # 4. Health Check (최대 15초 대기)
        logger.info("[Admin] VTuber 서버 Health Check 시작...")
        max_wait_time = 15.0
        check_interval = 0.5
        start_time = time.time()
        server_ready = False
        
        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get("http://localhost:12393", timeout=2)
                if response.status_code == 200:
                    server_ready = True
                    logger.info(f"[Admin] VTuber 서버 준비 완료 (대기 시간: {time.time() - start_time:.1f}초)")
                    break
            except requests.RequestException:
                pass
            
            time.sleep(check_interval)
        
        if not server_ready:
            logger.warning("[Admin] VTuber 서버 Health Check 타임아웃 (15초)")
            # 프로세스는 실행 중이지만 서버가 응답하지 않음 - 경고만 표시하고 계속 진행
        
        # 5. Electron 앱 실행 (경로 탐색 + ShellExecuteW 사용)
        # electron_path = None
        # electron_launched = False

        # [수정] 경로 탐색 로직 제거 -> "지정 사격" 모드
        # Hyein님의 PC 환경에 맞춰 절대 경로를 고정합니다.
        
        # 1. 목표: C드라이브의 설치된 Electron 앱
        target_exe = r"C:\Users\Hyein\AppData\Local\Programs\open-llm-vtuber\open-llm-vtuber-electron.exe"
        electron_path = Path(target_exe)

        # 2. 파일이 진짜 있는지 확인
        if electron_path.exists():
            logger.info(f"[Admin] 🎯 타겟 확인됨: {electron_path}")

        # [Step 5-1] 좀비 프로세스 정리 (Cleanup)
        # 이미 실행 중인 Electron 프로세스가 있으면 강제 종료
        if electron_path:
            try:
                exe_name = "open-llm-vtuber-electron.exe"
                logger.info(f"[Admin] 좀비 프로세스 정리 시작: {exe_name}")

                kill_result = subprocess.run(
                    ["taskkill", "/F", "/IM", exe_name],
                    capture_output=True,
                    timeout=10
                )

                if kill_result.returncode == 0:
                    logger.info(f"[Admin] 기존 Electron 프로세스 종료됨")
                    time.sleep(1.0)
                else:
                    logger.info("[Admin] 종료할 Electron 프로세스 없음 (정상)")
            except subprocess.TimeoutExpired:
                logger.warning("[Admin] taskkill 타임아웃 - 계속 진행")
            except Exception as e:
                logger.warning(f"[Admin] 좀비 프로세스 정리 중 오류 (무시): {e}")

        # [Step 5-2] Batch 파일을 통한 완전 독립 실행
        # Python 환경에서 완전히 분리된 CMD 세션으로 실행
        # [최종 해결책] "환경 변수 세탁" 후 실행 (Detox Launch)
        if electron_path and electron_path.exists():
            try:
                logger.info(f"[Admin] 🧹 좀비 프로세스 정리 중...")
                subprocess.run("taskkill /F /IM open-llm-vtuber-electron.exe /T", 
                             shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                logger.info(f"[Admin] 🚀 앱 실행 시도 (Clean Env): {electron_path}")
                
                # 1. 현재 시스템 환경 변수 복사
                clean_env = os.environ.copy()
                
                # 2. Electron과 충돌할 수 있는 '파이썬의 독' 제거 (세탁 과정)
                # 이 변수들이 Electron에게 넘어가면 앱이 멍청해질 수 있음.
                pop_keys = ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "ELECTRON_RUN_AS_NODE"]
                for key in pop_keys:
                    if key in clean_env:
                        clean_env.pop(key)
                        logger.debug(f"   - 환경 변수 제거: {key}")

                # 3. 작업 경로 설정
                electron_working_dir = os.path.dirname(electron_path)
                
                # 4. 깨끗한 환경으로 실행 (subprocess.Popen)
                # shell=False로 해야 독립성이 더 보장될 때가 있음 (윈도우에선)
                # creationflags=subprocess.DETACHED_PROCESS (0x00000008) 사용
                DETACHED_PROCESS = 0x00000008
                
                subprocess.Popen(
                    [str(electron_path)],
                    cwd=electron_working_dir,
                    env=clean_env, # <--- 세탁된 환경 변수 전달!
                    creationflags=DETACHED_PROCESS | subprocess.CREATE_NEW_CONSOLE,
                    shell=False
                )
                
                electron_launched = True
                logger.info("[Admin] 실행 명령 전송 완료 (독립 프로세스)!")
                
            except Exception as e:
                logger.error(f"[Admin] ❌ 실행 중 에러 발생: {e}")
                import traceback
                traceback.print_exc()
        else:
             logger.warning("[Admin] Electron 경로를 찾지 못했습니다.")
        
        # 6. 첫 인사(TTS)
        if server_ready:
            try:
                tts_text = "판돈은 준비됐나? 내가 왔어, 친구."
                logger.info(f"[Admin] 첫 인사 TTS 전송: {tts_text}")
                
                tts_response = requests.post(
                    "http://localhost:12393/api/speak",
                    json={"text": tts_text},
                    timeout=5
                )
                
                if tts_response.status_code == 200:
                    logger.info("[Admin] 첫 인사 TTS 전송 성공")
                else:
                    logger.warning(f"[Admin] 첫 인사 TTS 전송 실패: {tts_response.status_code}")
            except Exception as e:
                logger.warning(f"[Admin] 첫 인사 TTS 전송 중 오류: {e}")
        
        return {
            "success": True,
            "message": "VTuber 아바타가 성공적으로 실행되었습니다.",
            "pid": vtuber_proc.pid,
            "server_ready": server_ready,
            "electron_launched": electron_launched
        }

    @app.get("/mellow-link/init", tags=["Mellow-Link"])
    async def mellow_link_init(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ):
        """
        Initialize Mellow-Link session structure for user.

        Returns:
        - folders: User's folders (auto-created if none exist)
        - avatar_status: VTuber connection status
        - is_admin: Whether user is admin (has Secretary folder)
        """
        if not authorization:
            return {
                "success": False,
                "folders": [],
                "avatar_status": {"connected": False},
                "is_admin": False
            }

        token = authorization.replace("Bearer ", "").strip()

        if token.startswith("guest_"):
            return {
                "success": True,
                "folders": [],
                "avatar_status": {"connected": False},
                "is_admin": False,
                "is_guest": True
            }

        try:
            from jose import jwt
            from mellow_link.infra.database import SECRET_KEY, ALGORITHM

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            role = payload.get("role", UserRole.USER.value)

            if not username:
                return {"success": False, "error": "Invalid token"}

            user = db.query(User).filter(User.username == username).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Ensure user has folders (auto-create if needed)
            folders = ensure_user_has_folders(db, user.id, role=user.role)

            # Build folder response with session counts
            folder_list = []
            for f in folders:
                session_count = db.query(ChatSession).filter(
                    ChatSession.folder_id == f.id,
                    ChatSession.is_active == True
                ).count()
                folder_list.append({
                    "id": f.id,
                    "name": f.name,
                    "icon": f.icon,
                    "system_prompt": f.system_prompt,
                    "use_rag": f.use_rag,
                    "is_creative": f.is_creative,
                    "session_count": session_count
                })

            # Get avatar status
            avatar_port = settings.avatar_ws_port if settings else DEFAULT_AVATAR_WS_PORT
            avatar_status = get_avatar_status(port=avatar_port)
            relay = get_vtuber_relay()

            is_admin = user.role == UserRole.ADMIN.value

            return {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role
                },
                "folders": folder_list,
                "avatar_status": {
                    "service": avatar_status,
                    "relay_connected": relay.is_connected if relay else False
                },
                "is_admin": is_admin,
                "is_guest": False
            }

        except Exception as e:
            logger.error(f"[MellowLink] Init error: {e}")
            return {"success": False, "error": str(e)}

    # ---------- Metrics Endpoint ----------

    @app.get("/metrics", tags=["System"])
    async def get_metrics():
        """Get orchestrator metrics."""
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Orchestrator not initialized")
        return orchestrator.get_metrics()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point for running the application."""
    if not FASTAPI_AVAILABLE:
        print("FastAPI not installed. Run: pip install fastapi uvicorn")
        sys.exit(1)

    import uvicorn

    # Load settings for CLI
    settings = get_settings()

    print(f"Starting Mellow-Link on {settings.api_host}:{settings.api_port}")

    uvicorn.run(
        "mellow_link.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info"
    )


if __name__ == "__main__":
    main()
