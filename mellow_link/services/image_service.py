"""
Image Service - ComfyUI Integration

This module provides integration with ComfyUI for local image generation.
Supports workflow execution, queue management, and result retrieval.

CRITICAL: The generate() method waits for WebSocket "execution_success"
message before returning. This ensures the Orchestrator GPU lock is held
for the entire duration of image generation.

Connection:
    - Default: http://localhost:8188
    - Uses ComfyUI WebSocket API for real-time updates
    - REST API for workflow submission
"""

import asyncio
import aiohttp
import json
import logging
import uuid
import time
from mellow_link.core.schemas import ImageRequest
from mellow_link.config.settings import settings    
from typing import Optional, Dict, Any, List, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from datetime import datetime, date
import random

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class ImageStatus(Enum):
    """Image service status."""

    DISCONNECTED = auto()  # Not connected to ComfyUI
    CONNECTED = auto()     # Connected, ready for requests
    GENERATING = auto()    # Currently generating image
    QUEUED = auto()        # Request in ComfyUI queue
    ERROR = auto()         # Error state


@dataclass
class ImageRequest:
    """
    Request structure for image generation.

    Attributes:
        prompt: Positive prompt for generation
        negative_prompt: Negative prompt (what to avoid)
        workflow: ComfyUI workflow name or dict
        width: Output image width
        height: Output image height
        steps: Number of diffusion steps
        cfg_scale: Classifier-free guidance scale
        seed: Random seed (-1 for random)
        batch_size: Number of images to generate
    """

    prompt: str
    negative_prompt: str = ""
    workflow: str = "default"
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg_scale: float = 7.0
    seed: int = -1
    batch_size: int = 1
    sampler_name: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    model: str = ""  # Checkpoint model name
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageResult:
    """
    Result structure from image generation.

    Attributes:
        images: List of generated image paths
        prompt_id: ComfyUI prompt ID
        generation_time_ms: Total generation time
        seed_used: Actual seed used (if random)
        workflow_used: Workflow that was executed
    """

    images: List[Path]
    prompt_id: str
    generation_time_ms: float = 0.0
    seed_used: int = 0
    workflow_used: str = ""
    node_outputs: Dict[str, Any] = field(default_factory=dict)


class ImageGenerationError(Exception):
    """Exception for image generation failures."""
    pass


# =============================================================================
# Progress Callback Types
# =============================================================================

ProgressCallback = Union[
    Callable[[float, str], None],
    Callable[[float, str], Awaitable[None]]
]


# =============================================================================
# Image Service Class
# =============================================================================

class ImageService:
    """
    Service for image generation via ComfyUI.

    CRITICAL DESIGN:
        - The generate() method WAITS for "execution_success" WebSocket message
        - This ensures GPU lock is held for the entire generation duration
        - Hot-swap scenarios are handled by the Orchestrator, not here

    Handles:
        - WebSocket connection for real-time updates
        - Workflow loading and execution
        - Queue management
        - Result retrieval and caching
        - Progress callbacks

    Usage:
        service = ImageService()
        await service.connect()
        result = await service.generate(request)  # Blocks until complete
        await service.disconnect()
    """

    DEFAULT_HOST: str = "localhost"
    DEFAULT_PORT: int = 8188
    DEFAULT_TIMEOUT: float = 600.0  # 10 minutes for complex generations

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        output_dir: Optional[Path] = None
    ):
        """
        Initialize Image Service.

        Args:
            host: ComfyUI server hostname
            port: ComfyUI server port
            timeout: Request timeout in seconds
            output_dir: Directory to save generated images
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.output_dir = output_dir or Path("./outputs/images")

        self._status: ImageStatus = ImageStatus.DISCONNECTED
        self._base_url: str = f"http://{host}:{port}"
        self._ws_url: str = f"ws://{host}:{port}/ws"

        # Client ID for WebSocket
        self._client_id: str = str(uuid.uuid4())

        # Connections
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

        # Workflow storage
        self._workflows: Dict[str, Dict] = {}

        # Progress callbacks
        self._progress_callbacks: List[Callable] = []

        # Execution tracking
        self._current_prompt_id: Optional[str] = None
        self._execution_complete: asyncio.Event = asyncio.Event()
        self._execution_error: Optional[str] = None
        self._execution_outputs: Dict[str, Any] = {}

        # WebSocket listener task
        self._ws_listener_task: Optional[asyncio.Task] = None

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ==================== Connection Management ====================

    async def connect(self) -> bool:
        """
        Establish connection to ComfyUI server.

        Sets up both REST API and WebSocket connections.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If ComfyUI server is unreachable
        """
        try:
            logger.info(f"[ImageService] Connecting to ComfyUI at {self._base_url}")

            # Create HTTP session
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

            # Test connection with system stats
            async with self._session.get(f"{self._base_url}/system_stats") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"ComfyUI returned status {resp.status}")
                stats = await resp.json()
                logger.info(f"[ImageService] ComfyUI connected: {stats.get('system', {})}")

            # Establish WebSocket connection
            ws_url = f"{self._ws_url}?clientId={self._client_id}"
            self._ws = await self._session.ws_connect(ws_url)

            # Start WebSocket listener
            self._ws_listener_task = asyncio.create_task(self._ws_listener())

            self._status = ImageStatus.CONNECTED
            logger.info(f"[ImageService] Connected successfully (client_id: {self._client_id})")
            return True

        except aiohttp.ClientError as e:
            logger.error(f"[ImageService] Connection failed: {e}")
            self._status = ImageStatus.ERROR
            raise ConnectionError(f"Failed to connect to ComfyUI: {e}")
        except Exception as e:
            logger.error(f"[ImageService] Unexpected connection error: {e}")
            self._status = ImageStatus.ERROR
            raise

    async def disconnect(self) -> None:
        """
        Close connection to ComfyUI server.

        Closes WebSocket and cleans up state.
        """
        logger.info("[ImageService] Disconnecting...")

        # Cancel WebSocket listener
        if self._ws_listener_task:
            self._ws_listener_task.cancel()
            try:
                await self._ws_listener_task
            except asyncio.CancelledError:
                pass
            self._ws_listener_task = None

        # Close WebSocket
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        self._status = ImageStatus.DISCONNECTED
        logger.info("[ImageService] Disconnected")

    async def health_check(self) -> bool:
        """
        Check if ComfyUI server is healthy.

        Returns:
            True if server responds
        """
        if not self._session:
            return False

        try:
            async with self._session.get(
                f"{self._base_url}/system_stats",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_status(self) -> ImageStatus:
        """Get current service status."""
        return self._status

    def is_ready(self) -> bool:
        """Check if service is ready to accept requests."""
        return self._status == ImageStatus.CONNECTED

    def is_available(self) -> bool:
        """Check if service is available (alias for orchestrator compatibility)."""
        return self._status in (ImageStatus.CONNECTED, ImageStatus.GENERATING)

    # ==================== WebSocket Listener ====================

    async def _ws_listener(self) -> None:
        """
        Background task to listen for WebSocket messages.

        Processes:
            - execution_start: Generation started
            - executing: Node being executed
            - progress: Step progress
            - executed: Node completed
            - execution_success: Full workflow completed
            - execution_error: Generation failed
            - execution_cached: Using cached results
        """
        logger.debug("[ImageService] WebSocket listener started")

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"[ImageService] Invalid JSON: {msg.data[:100]}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[ImageService] WebSocket error: {self._ws.exception()}")
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("[ImageService] WebSocket closed")
                    break

        except asyncio.CancelledError:
            logger.debug("[ImageService] WebSocket listener cancelled")
        except Exception as e:
            logger.error(f"[ImageService] WebSocket listener error: {e}")

        logger.debug("[ImageService] WebSocket listener stopped")

    async def _handle_ws_message(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming WebSocket message.

        CRITICAL: Sets _execution_complete event on success/error.

        Args:
            message: Parsed WebSocket message
        """
        msg_type = message.get("type", "")
        data = message.get("data", {})

        # Filter messages for our prompt
        prompt_id = data.get("prompt_id")
        if prompt_id and self._current_prompt_id and prompt_id != self._current_prompt_id:
            return  # Not our prompt

        if msg_type == "execution_start":
            logger.info(f"[ImageService] Execution started: {data.get('prompt_id')}")
            self._status = ImageStatus.GENERATING

        elif msg_type == "executing":
            node = data.get("node")
            if node:
                logger.debug(f"[ImageService] Executing node: {node}")
            else:
                # node=None means execution finished for this prompt
                logger.debug("[ImageService] Execution phase complete")

        elif msg_type == "progress":
            value = data.get("value", 0)
            max_value = data.get("max", 1)
            progress = (value / max_value) * 100 if max_value > 0 else 0

            # Invoke progress callbacks
            for callback in self._progress_callbacks:
                try:
                    result = callback(self._current_prompt_id, progress, f"Step {value}/{max_value}")
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"[ImageService] Progress callback error: {e}")

        elif msg_type == "executed":
            node = data.get("node")
            output = data.get("output", {})
            if node and output:
                self._execution_outputs[node] = output
                logger.debug(f"[ImageService] Node {node} executed with output")

        elif msg_type == "execution_success":
            # CRITICAL: This signals generation is complete
            logger.info(f"[ImageService] Execution SUCCESS: {data.get('prompt_id')}")
            self._execution_error = None
            self._execution_complete.set()

        elif msg_type == "execution_error":
            # CRITICAL: This signals generation failed
            error_msg = data.get("exception_message", "Unknown error")
            logger.error(f"[ImageService] Execution ERROR: {error_msg}")
            self._execution_error = error_msg
            self._execution_complete.set()

        elif msg_type == "execution_cached":
            # Cached nodes were used
            nodes = data.get("nodes", [])
            logger.debug(f"[ImageService] Cached nodes: {nodes}")

        elif msg_type == "status":
            # Queue status update
            queue = data.get("status", {}).get("exec_info", {})
            queue_remaining = queue.get("queue_remaining", 0)
            if queue_remaining > 0:
                self._status = ImageStatus.QUEUED
                logger.debug(f"[ImageService] Queue remaining: {queue_remaining}")

    # ==================== Workflow Management ====================

    async def load_workflow(self, workflow_path: Path) -> str:
        """
        Load a workflow from JSON file.

        Args:
            workflow_path: Path to workflow JSON

        Returns:
            Workflow name/ID
        """
        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_path}")

        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)

        name = workflow_path.stem
        self._workflows[name] = workflow
        logger.info(f"[ImageService] Loaded workflow: {name}")
        return name

    async def list_workflows(self) -> List[str]:
        """List available workflows."""
        return list(self._workflows.keys())

    def get_workflow(self, name: str) -> Optional[Dict]:
        """Get a loaded workflow by name."""
        return self._workflows.get(name)

    async def get_object_info(self) -> Dict[str, Any]:
        """Get available nodes and their info from ComfyUI."""
        if not self._session:
            raise ConnectionError("Not connected to ComfyUI")

        async with self._session.get(f"{self._base_url}/object_info") as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Failed to get object info: {resp.status}")
            return await resp.json()

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get ComfyUI system stats.

        Returns:
            Dict with VRAM, queue status, etc.
        """
        if not self._session:
            raise ConnectionError("Not connected to ComfyUI")

        async with self._session.get(f"{self._base_url}/system_stats") as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Failed to get system stats: {resp.status}")
            return await resp.json()

    # ==================== Image Generation ====================

    async def generate(self, request: ImageRequest, on_progress: Optional[ProgressCallback] = None) -> ImageResult:
        """
        [디버깅 모드] 에러가 발생하면 무조건 터미널에 내용을 출력합니다.
        """
        import traceback # 범인 추적용 도구
        
        # [안전 장치] 임포트가 꼬였을까 봐 여기서 다시 한번 확실하게 부름
        from datetime import datetime
        import random

        # [해결책] 요청이 없으면(None) 무조건 'flux_dev_api.json'을 쓴다! (강제 고정)
        workflow_file = request.workflow or "flux_dev_api.json"

        print("\n" + "="*50)
        print(">>> [DEBUG] generate 함수 진입 성공!")
        print(f">>> [DEBUG] 요청 받은 워크플로우: {getattr(request, 'workflow', '없음')}")
        logger.info(f">>> [DEBUG] 최종 결정된 워크플로우: {workflow_file}")  # <-- 여기가 None이 나오면 안 돼!
        print("="*50 + "\n")

        try:
            # 1. 워크플로우 강제 지정 (여기가 핵심이야!)
            # 요청이 없으면 무조건 'flux_dev_api.json'을 쓰도록 못 박아버려.
            if not request.workflow:
                workflow_file = "flux_dev_api.json"
            else:
                workflow_file = request.workflow

            start_time = time.time()
            self._execution_complete.clear()
            self._execution_error = None
            self._execution_outputs = {}

            if on_progress:
                self._progress_callbacks.append(lambda pid, prog, msg: on_progress(prog, msg))

            # ----------------------------------------------------------------
            # 1. 워크플로우 파일 로드 시도
            # ----------------------------------------------------------------
            prompt = None

            if workflow_file:
                print(f">>> [DEBUG] 파일 모드 진입: {workflow_file}")
                
                # 경로 생성
                workflow_path = Path("mellow_link/data/workflows") / workflow_file
                print(f">>> [DEBUG] 파일 경로 확인: {workflow_path}")
                # [확인용 로그] 터미널에 주소가 어떻게 찍히는지 보자.
                print(f">>> [DEBUG] 수정된 경로: {workflow_path.absolute()}")
                if not workflow_path.exists():
                    print(f">>> [ERROR] 파일이 없습니다!")
                    raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
                
                # 로드 (deep copy로 원본 보호)
                import copy
                workflow_name = await self.load_workflow(workflow_path)
                prompt = copy.deepcopy(self._workflows[workflow_name])
                
                # 프롬프트 내용 치환
                print(">>> [DEBUG] 프롬프트 치환 시작")
                negative_text = getattr(request, 'negative_prompt', '') or ''

                for key, value in prompt.items():
                    if "inputs" not in value:
                        continue

                    class_type = value.get("class_type", "")
                    meta_title = value.get("_meta", {}).get("title", "")

                    # ====== Flux 스타일: CLIPTextEncodeFlux ======
                    if class_type == "CLIPTextEncodeFlux":
                        if "Positive" in meta_title:
                            # Positive 프롬프트 주입
                            value["inputs"]["clip_l"] = request.prompt
                            value["inputs"]["t5xxl"] = request.prompt
                            print(f">>> [DEBUG] Flux Positive 주입: {request.prompt[:50]}...")
                        elif "Negative" in meta_title:
                            # Negative 프롬프트 주입
                            value["inputs"]["clip_l"] = negative_text
                            value["inputs"]["t5xxl"] = negative_text
                            print(f">>> [DEBUG] Flux Negative 주입: {negative_text[:50] if negative_text else '(empty)'}...")

                    # ====== SD 스타일: CLIPTextEncode (호환성 유지) ======
                    elif class_type == "CLIPTextEncode":
                        if "Positive" in meta_title or meta_title == "CLIP Text Encode (Prompt)":
                            value["inputs"]["text"] = request.prompt
                            print(f">>> [DEBUG] SD Positive 주입: {request.prompt[:50]}...")
                        elif "Negative" in meta_title:
                            value["inputs"]["text"] = negative_text
                            print(f">>> [DEBUG] SD Negative 주입: {negative_text[:50] if negative_text else '(empty)'}...")

                    # ====== 시드 치환 ======
                    if class_type == "KSampler":
                        if request.seed == -1:
                            seed_val = random.randint(0, 2**32 - 1)
                            value["inputs"]["seed"] = seed_val
                            print(f">>> [DEBUG] 랜덤 시드 생성: {seed_val}")
                        else:
                            value["inputs"]["seed"] = request.seed
            
            # ----------------------------------------------------------------
            # 2. 코드 모드 (Fallback)
            # ----------------------------------------------------------------
            else:
                print(">>> [DEBUG] 코드 생성 모드 진입 (_build_prompt)")
                prompt = self._build_prompt(request)

            # ----------------------------------------------------------------
            # 3. 실행 요청
            # ----------------------------------------------------------------
            print(">>> [DEBUG] ComfyUI에 큐 전송 시도...")
            prompt_id = await self._queue_prompt(prompt)
            self._current_prompt_id = prompt_id
            print(f">>> [DEBUG] 큐 전송 성공! ID: {prompt_id}")

            # 대기
            await asyncio.wait_for(self._execution_complete.wait(), timeout=self.timeout)

            if self._execution_error:
                raise ImageGenerationError(self._execution_error)

            images = await self._get_generated_images(prompt_id)
            generation_time_ms = (time.time() - start_time) * 1000

            result = ImageResult(
                images=images,
                prompt_id=prompt_id,
                generation_time_ms=generation_time_ms,
                seed_used=request.seed,
                workflow_used=getattr(request, "workflow", "code"),
                node_outputs=self._execution_outputs,
            )
            
            self._status = ImageStatus.CONNECTED
            return result

        except Exception as e:
            # 여기가 핵심이야! 에러가 나면 여기서 다 토해냄
            print("\n" + "!"*50)
            print("!!! [CRITICAL ERROR] 함수 실행 중 사망 !!!")
            print(f"!!! 에러 타입: {type(e).__name__}")
            print(f"!!! 에러 메시지: {str(e)}")
            print("!!! 상세 추적(Traceback):")
            traceback.print_exc()
            print("!"*50 + "\n")
            raise e # 500 에러를 던지지만, 위에서 로그는 이미 찍혔음

        finally:
            self._current_prompt_id = None
            if on_progress and on_progress in self._progress_callbacks:
                self._progress_callbacks.remove(on_progress)

    async def generate_from_workflow(
        self,
        workflow: Dict[str, Any],
        on_progress: Optional[ProgressCallback] = None
    ) -> ImageResult:
        """
        Execute a raw ComfyUI workflow.

        Args:
            workflow: Complete ComfyUI workflow dict
            on_progress: Optional progress callback

        Returns:
            ImageResult with generated images
        """
        if not self.is_ready():
            raise ImageGenerationError("ImageService not connected")

        start_time = time.time()

        # Reset execution state
        self._execution_complete.clear()
        self._execution_error = None
        self._execution_outputs = {}

        if on_progress:
            self._progress_callbacks.append(
                lambda pid, prog, msg: on_progress(prog, msg)
            )

        try:
            # Submit raw workflow
            prompt_id = await self._queue_prompt(workflow)
            self._current_prompt_id = prompt_id

            logger.info(f"[ImageService] Queued raw workflow: {prompt_id}")

            # Wait for completion
            try:
                await asyncio.wait_for(
                    self._execution_complete.wait(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                await self.interrupt()
                raise TimeoutError(f"Workflow execution timed out")

            if self._execution_error:
                raise ImageGenerationError(self._execution_error)

            images = await self._get_generated_images(prompt_id)
            generation_time_ms = (time.time() - start_time) * 1000

            result = ImageResult(
                images=images,
                prompt_id=prompt_id,
                generation_time_ms=generation_time_ms,
                workflow_used="raw",
                node_outputs=self._execution_outputs,
            )

            self._status = ImageStatus.CONNECTED
            return result

        finally:
            self._current_prompt_id = None
            if on_progress and on_progress in self._progress_callbacks:
                self._progress_callbacks.remove(on_progress)

    async def _queue_prompt(self, prompt: Dict[str, Any]) -> str:
        """
        Submit prompt to ComfyUI queue.

        Args:
            prompt: ComfyUI prompt/workflow dict

        Returns:
            Prompt ID
        """
        if not self._session:
            raise ConnectionError("Not connected to ComfyUI")

        payload = {
            "prompt": prompt,
            "client_id": self._client_id
        }

        async with self._session.post(
            f"{self._base_url}/prompt",
            json=payload
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise ImageGenerationError(f"Failed to queue prompt: {error_text}")

            result = await resp.json()
            return result.get("prompt_id", "")

    async def _get_generated_images(self, prompt_id: str) -> List[Path]:
        """
        Retrieve generated images from ComfyUI history.

        Args:
            prompt_id: The prompt ID to get images for

        Returns:
            List of local paths to downloaded images
        """
        if not self._session:
            return []

        # Get history for this prompt
        async with self._session.get(f"{self._base_url}/history/{prompt_id}") as resp:
            if resp.status != 200:
                logger.warning(f"[ImageService] Failed to get history: {resp.status}")
                return []

            history = await resp.json()

        images = []
        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})

        # Find all image outputs
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img_info in node_output["images"]:
                    filename = img_info.get("filename", "")
                    subfolder = img_info.get("subfolder", "")
                    img_type = img_info.get("type", "output")

                    if filename:
                        # Download image
                        local_path = await self._download_image(
                            filename, subfolder, img_type
                        )
                        if local_path:
                            images.append(local_path)

        return images

    async def _download_image(
        self,
        filename: str,
        subfolder: str = "",
        img_type: str = "output"
    ) -> Optional[Path]:
        """
        Download an image from ComfyUI.

        Args:
            filename: Image filename
            subfolder: Subfolder in ComfyUI
            img_type: Type (output, temp, input)

        Returns:
            Local path to downloaded image
        """
        if not self._session:
            return None

        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": img_type
        }

        try:
            async with self._session.get(
                f"{self._base_url}/view",
                params=params
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[ImageService] Failed to download {filename}")
                    return None

                # Save to output directory
                local_path = self.output_dir / filename
                content = await resp.read()

                with open(local_path, 'wb') as f:
                    f.write(content)

                logger.debug(f"[ImageService] Downloaded: {local_path}")
                return local_path

        except Exception as e:
            logger.error(f"[ImageService] Download error: {e}")
            return None

    async def cancel_generation(self, prompt_id: Optional[str] = None) -> bool:
        """
        Cancel ongoing or queued generation.

        Args:
            prompt_id: Specific prompt to cancel (None for current)

        Returns:
            True if cancellation successful
        """
        target_id = prompt_id or self._current_prompt_id
        if not target_id:
            return False

        if not self._session:
            return False

        try:
            # Delete from queue
            async with self._session.post(
                f"{self._base_url}/queue",
                json={"delete": [target_id]}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"[ImageService] Cancelled: {target_id}")
                    return True
        except Exception as e:
            logger.error(f"[ImageService] Cancel error: {e}")

        return False

    # ==================== Queue Management ====================

    async def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current ComfyUI queue status.

        Returns:
            Dict with queue_remaining, currently_running, etc.
        """
        if not self._session:
            return {"error": "Not connected"}

        async with self._session.get(f"{self._base_url}/queue") as resp:
            if resp.status != 200:
                return {"error": f"Status {resp.status}"}
            return await resp.json()

    async def clear_queue(self) -> bool:
        """Clear all pending items from queue."""
        if not self._session:
            return False

        try:
            async with self._session.post(
                f"{self._base_url}/queue",
                json={"clear": True}
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def get_history(
        self,
        prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get generation history.

        Args:
            prompt_id: Specific prompt ID (None for all)

        Returns:
            History dict from ComfyUI
        """
        if not self._session:
            return {}

        url = f"{self._base_url}/history"
        if prompt_id:
            url = f"{url}/{prompt_id}"

        async with self._session.get(url) as resp:
            if resp.status != 200:
                return {}
            return await resp.json()

    # ==================== Progress & Events ====================

    def on_progress(
        self,
        callback: Callable[[str, float, str], None]
    ) -> None:
        """
        Register progress callback.

        Args:
            callback: Function(prompt_id, progress, message)
        """
        self._progress_callbacks.append(callback)

    # ==================== Utilities ====================

    async def interrupt(self) -> bool:
        """
        Send interrupt signal to ComfyUI.

        Stops current generation immediately.

        Returns:
            True if interrupt sent
        """
        if not self._session:
            return False

        try:
            async with self._session.post(f"{self._base_url}/interrupt") as resp:
                if resp.status == 200:
                    logger.info("[ImageService] Interrupt sent")
                    # Signal completion to unblock waiting
                    self._execution_error = "Interrupted by user"
                    self._execution_complete.set()
                    return True
        except Exception as e:
            logger.error(f"[ImageService] Interrupt error: {e}")

        return False

    async def unload_model(self) -> bool:
        """
        Unload all models from VRAM to free memory for LLM.

        CRITICAL: This method must be called before the Orchestrator
        transitions from IMAGE -> TEXT state to ensure VRAM is available
        for Ollama/LLM inference.

        Uses ComfyUI's /free endpoint to:
            - Unload all loaded checkpoint models
            - Free cached tensors and embeddings
            - Release VRAM back to the system

        Returns:
            True if models were successfully unloaded

        Note:
            This may take a few seconds as ComfyUI garbage collects
            and releases GPU memory. The next image generation will
            need to reload models, adding latency.
        """
        if not self._session:
            logger.warning("[ImageService] Cannot unload models: not connected")
            return False

        try:
            logger.info("[ImageService] Unloading models to free VRAM...")

            # ComfyUI /free endpoint releases VRAM
            # unload_models: Unload checkpoint/unet/clip/vae models
            # free_memory: Force garbage collection and CUDA cache clear
            payload = {
                "unload_models": True,
                "free_memory": True
            }

            async with self._session.post(
                f"{self._base_url}/free",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    logger.info("[ImageService] Models unloaded, VRAM freed")
                    return True
                else:
                    # Some ComfyUI versions may not have /free endpoint
                    # Fall back to alternative approach
                    logger.warning(
                        f"[ImageService] /free endpoint returned {resp.status}, "
                        "trying alternative unload method"
                    )

            # Alternative: Queue a minimal no-op to trigger cleanup
            # Some ComfyUI setups respond to empty prompt differently
            return await self._force_vram_cleanup()

        except aiohttp.ClientError as e:
            logger.error(f"[ImageService] Failed to unload models: {e}")
            # Try alternative cleanup method
            return await self._force_vram_cleanup()
        except Exception as e:
            logger.error(f"[ImageService] Unexpected error during unload: {e}")
            return False

    async def _force_vram_cleanup(self) -> bool:
        """
        Force VRAM cleanup using alternative methods.

        Called when /free endpoint is unavailable or fails.
        Attempts to trigger garbage collection through the API.

        Returns:
            True if cleanup was attempted
        """
        if not self._session:
            return False

        try:
            # Method 1: Clear queue (releases any cached items)
            await self.clear_queue()

            # Method 2: Request system stats to trigger internal cleanup
            async with self._session.get(
                f"{self._base_url}/system_stats",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    stats = await resp.json()
                    devices = stats.get("devices", [])
                    if devices:
                        vram_info = devices[0]
                        free_mb = vram_info.get("vram_free", 0) / (1024 * 1024)
                        total_mb = vram_info.get("vram_total", 0) / (1024 * 1024)
                        logger.info(
                            f"[ImageService] VRAM after cleanup: "
                            f"{free_mb:.0f}MB free / {total_mb:.0f}MB total"
                        )

            logger.info("[ImageService] Alternative VRAM cleanup completed")
            return True

        except Exception as e:
            logger.error(f"[ImageService] Force cleanup failed: {e}")
            return False

    async def get_vram_usage(self) -> Dict[str, Any]:
        """
        Get current VRAM usage from ComfyUI.

        Returns:
            Dict with vram_free, vram_total, vram_used (in bytes)
        """
        if not self._session:
            return {"error": "Not connected"}

        try:
            async with self._session.get(
                f"{self._base_url}/system_stats",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return {"error": f"Status {resp.status}"}

                stats = await resp.json()
                devices = stats.get("devices", [])

                if not devices:
                    return {"error": "No GPU devices found"}

                device = devices[0]
                return {
                    "vram_free": device.get("vram_free", 0),
                    "vram_total": device.get("vram_total", 0),
                    "vram_used": device.get("vram_total", 0) - device.get("vram_free", 0),
                    "device_name": device.get("name", "Unknown"),
                    "device_type": device.get("type", "Unknown"),
                }

        except Exception as e:
            logger.error(f"[ImageService] Failed to get VRAM usage: {e}")
            return {"error": str(e)}

    async def get_image(self, filename: str, subfolder: str = "") -> bytes:
        """
        Retrieve generated image from ComfyUI.

        Args:
            filename: Image filename
            subfolder: Optional subfolder

        Returns:
            Image bytes
        """
        if not self._session:
            raise ConnectionError("Not connected")

        params = {"filename": filename, "subfolder": subfolder, "type": "output"}

        async with self._session.get(f"{self._base_url}/view", params=params) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Failed to get image: {resp.status}")
            return await resp.read()

    async def upload_image(
        self,
        image_path: Path,
        overwrite: bool = False
    ) -> str:
        """
        Upload image to ComfyUI for use in workflows.

        Args:
            image_path: Path to image file
            overwrite: Whether to overwrite existing

        Returns:
            Filename in ComfyUI
        """
        if not self._session:
            raise ConnectionError("Not connected")

        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        data = aiohttp.FormData()
        data.add_field(
            'image',
            open(image_path, 'rb'),
            filename=image_path.name,
            content_type='image/png'
        )
        data.add_field('overwrite', str(overwrite).lower())

        async with self._session.post(
            f"{self._base_url}/upload/image",
            data=data
        ) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Upload failed: {resp.status}")
            result = await resp.json()
            return result.get("name", "")

    def _build_prompt(self, request: ImageRequest) -> Dict[str, Any]:
        """
        Build ComfyUI prompt from request.

        Creates a basic txt2img workflow.

        Args:
            request: ImageRequest to convert

        Returns:
            ComfyUI-compatible prompt dict
        """
        # Generate seed if random
        seed = request.seed
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)

        # Basic txt2img workflow
        prompt = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": request.steps,
                    "cfg": request.cfg_scale,
                    "sampler_name": request.sampler_name,
                    "scheduler": request.scheduler,
                    "denoise": request.denoise,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": request.model or "flux1-dev-fp8.safetensors"
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": request.width,
                    "height": request.height,
                    "batch_size": request.batch_size
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": request.prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": request.negative_prompt or "",
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"mellow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "images": ["8", 0]
                }
            }
        }

        return prompt

    async def execute(self, request_data: Dict[str, Any]) -> ImageResult:
        """
        Execute method for orchestrator compatibility.

        Args:
            request_data: Dict with generation parameters

        Returns:
            ImageResult
        """
        request = ImageRequest(
            prompt=request_data.get("prompt", ""),
            negative_prompt=request_data.get("negative_prompt", ""),
            width=request_data.get("width", 512),
            height=request_data.get("height", 512),
            steps=request_data.get("steps", 20),
            cfg_scale=request_data.get("cfg_scale", 7.0),
            seed=request_data.get("seed", -1),
            batch_size=request_data.get("batch_size", 1),
            model=request_data.get("model", ""),
        )
        return await self.generate(request)


# =============================================================================
# Factory Function
# =============================================================================

def create_image_service(
    host: str = "localhost",
    port: int = 8188,
    timeout: float = 600.0,
    output_dir: Optional[Path] = None
) -> ImageService:
    """
    Factory function to create ImageService.

    Args:
        host: ComfyUI hostname
        port: ComfyUI port
        timeout: Request timeout
        output_dir: Output directory for images

    Returns:
        Configured ImageService instance
    """
    return ImageService(
        host=host,
        port=port,
        timeout=timeout,
        output_dir=output_dir
    )
