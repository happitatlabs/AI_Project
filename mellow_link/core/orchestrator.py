"""
Orchestrator - Core FSM Controller for Mellow-Link

This module implements the main orchestration logic using an async event loop
and finite state machine pattern. It coordinates GPU resource sharing between
LLM (Ollama) and Image Generation (ComfyUI) workloads.

Design Pattern:
    - Singleton pattern for single orchestrator instance
    - FSM for state management
    - Observer pattern for event distribution
    - Command pattern for task execution

Extracted from legacy:
    - state_machine.py: ChatStateMachine, StateContext
    - chat_api.py: mode routing, RAG integration, streaming
    - model_service.py: GPU lock pattern
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable, List, AsyncGenerator
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import time

from .states import SystemState, TaskPriority, TransitionResult
from .events import Event, TaskEvent, StateChangeEvent, EventType, VRAMEvent

logger = logging.getLogger(__name__)


# =============================================================================
# Chat Processing States (from legacy state_machine.py)
# =============================================================================

class ChatState:
    """Chat processing pipeline states."""
    IDLE = "idle"
    ANALYZING = "analyzing"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class IntentResult:
    """
    Result of intent classification.

    Attributes:
        intent: Classified intent type (simple_chat, image_request, document_qa)
        confidence: Confidence score (0.0 ~ 1.0)
        metadata: Additional metadata from classification
    """
    intent: str  # "simple_chat" | "image_request" | "document_qa"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatContext:
    """
    Context for chat processing pipeline.

    Migrated from legacy StateContext with enhancements for
    the new modular architecture.
    """
    # Input
    user_query: str
    system_prompt: str = ""
    use_rag: bool = False
    rag_collection_name: Optional[str] = None
    user_memories: List[str] = field(default_factory=list)
    session_history: List[Dict[str, str]] = field(default_factory=list)
    mode: str = "thinking"  # fast, thinking, research, auto

    # Processing state
    should_use_rag: bool = False
    rag_context: str = ""
    rag_sources: List[Dict] = field(default_factory=list)

    # Intent classification results
    intent_result: Optional[IntentResult] = None
    target_service: str = "llm"  # "llm" | "image" | "document"
    refined_prompt: str = ""  # Flux-optimized English prompt for image generation

    # Output
    final_answer: str = ""
    state_info: str = ""
    rag_used: bool = False

    # Metadata
    current_state: str = ChatState.IDLE
    error_message: str = ""
    processing_time: float = 0.0
    selected_mode: Optional[str] = None


# =============================================================================
# State Transition Matrix
# =============================================================================

# Valid state transitions: from_state -> set of valid to_states
VALID_TRANSITIONS: Dict[SystemState, set] = {
    SystemState.IDLE: {SystemState.TEXT, SystemState.IMAGE, SystemState.ERROR},
    SystemState.TEXT: {SystemState.IDLE, SystemState.IMAGE, SystemState.ERROR},
    SystemState.IMAGE: {SystemState.IDLE, SystemState.TEXT, SystemState.ERROR},
    SystemState.ERROR: {SystemState.IDLE},
}


# =============================================================================
# Orchestrator Class
# =============================================================================

class Orchestrator:
    """
    Central orchestrator managing the AI task pipeline.

    Responsibilities:
        1. Maintain FSM state (IDLE, TEXT, IMAGE, ERROR)
        2. Manage task queue with priority scheduling
        3. Coordinate GPU resource allocation
        4. Handle state transitions with cooldown periods
        5. Dispatch events to registered handlers

    Attributes:
        current_state: Current FSM state
        task_queue: Priority queue for pending tasks
        event_handlers: Registered event callbacks
        services: Dictionary of registered service instances

    Usage:
        orchestrator = Orchestrator()
        await orchestrator.initialize()
        await orchestrator.submit_task(task_event)
        await orchestrator.run()  # Start main event loop
    """

    # Class-level constants
    DEFAULT_COOLDOWN_SECONDS: float = 2.0  # GPU cooldown between state transitions
    MAX_QUEUE_SIZE: int = 100              # Maximum pending tasks
    QUEUE_TIMEOUT: float = 1.0             # Timeout for queue.get()

    # Singleton instance
    _instance: Optional['Orchestrator'] = None

    def __new__(cls):
        """Singleton pattern - ensure only one orchestrator exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize the Orchestrator.

        Sets up:
            - Initial state as IDLE
            - Empty task queue
            - Event handler registry
            - Service container
        """
        # Prevent re-initialization on singleton access
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.current_state: SystemState = SystemState.IDLE
        self._task_queue: Optional[asyncio.PriorityQueue] = None
        self._event_handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._services: Dict[str, Any] = {}
        self._is_running: bool = False
        self._last_transition_time: Optional[datetime] = None
        self._shutdown_event: Optional[asyncio.Event] = None

        # Metrics tracking
        self._metrics = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0.0,
            "state_transitions": defaultdict(int),
            "queue_high_water_mark": 0,
            "start_time": None,
            "last_error": None,
        }

        # GPU lock for exclusive access
        self._gpu_lock: Optional[asyncio.Lock] = None

        # Task tracking
        self._active_tasks: Dict[str, TaskEvent] = {}
        self._task_results: Dict[str, Any] = {}

        self._initialized = True
        logger.info("[Orchestrator] Instance created (singleton)")

    async def initialize(self) -> None:
        """
        Async initialization of orchestrator components.

        Steps:
            1. Initialize asyncio queues
            2. Connect to services (LLM, Image, Document)
            3. Start VRAM watchdog
            4. Verify all dependencies are available

        Raises:
            RuntimeError: If critical services fail to initialize
        """
        logger.info("[Orchestrator] Initializing...")

        # Initialize asyncio primitives
        self._task_queue = asyncio.PriorityQueue(maxsize=self.MAX_QUEUE_SIZE)
        self._shutdown_event = asyncio.Event()
        self._gpu_lock = asyncio.Lock()

        # Record start time
        self._metrics["start_time"] = datetime.now()

        # Try to connect to services
        await self._connect_services()

        # Emit initialization event
        await self.emit_event(Event(
            event_type=EventType.STATE_CHANGE,
            payload={"action": "initialize", "state": self.current_state.name},
            source="orchestrator"
        ))

        logger.info("[Orchestrator] Initialization complete")

    async def _connect_services(self) -> None:
        """Attempt to connect to registered services."""
        for name, service in self._services.items():
            try:
                if hasattr(service, 'connect'):
                    await service.connect()
                    logger.info(f"[Orchestrator] Service '{name}' connected")
                elif hasattr(service, 'initialize'):
                    await service.initialize()
                    logger.info(f"[Orchestrator] Service '{name}' initialized")
            except Exception as e:
                logger.warning(f"[Orchestrator] Service '{name}' connection failed: {e}")

    async def shutdown(self) -> None:
        """
        Graceful shutdown of the orchestrator.

        Steps:
            1. Stop accepting new tasks
            2. Wait for current task to complete (with timeout)
            3. Flush remaining queue (optional: save to disk)
            4. Disconnect all services
            5. Stop VRAM watchdog
        """
        logger.info("[Orchestrator] Initiating shutdown...")

        # Signal shutdown
        self._is_running = False
        if self._shutdown_event:
            self._shutdown_event.set()

        # Wait for current task with timeout
        shutdown_timeout = 30.0
        try:
            await asyncio.wait_for(self._perform_shutdown(), timeout=shutdown_timeout)
        except asyncio.TimeoutError:
            logger.error("[Orchestrator] Shutdown timed out!")
            
        # Disconnect services
        await self._disconnect_services()

    async def _perform_shutdown(self) -> None:
        """
        Perform the actual shutdown operations.

        - Wait for active tasks to complete
        - Drain the task queue
        """
        # Wait for active tasks to complete
        if self._active_tasks:
            logger.info(f"[Orchestrator] Waiting for {len(self._active_tasks)} active tasks to complete...")
            max_wait = 10.0  # seconds
            wait_interval = 0.5
            elapsed = 0.0
            while self._active_tasks and elapsed < max_wait:
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

            if self._active_tasks:
                logger.warning(f"[Orchestrator] {len(self._active_tasks)} tasks still active after timeout")

        # Drain remaining tasks from queue
        if self._task_queue:
            remaining = self._task_queue.qsize()
            if remaining > 0:
                logger.info(f"[Orchestrator] Draining {remaining} tasks from queue...")
                while not self._task_queue.empty():
                    try:
                        self._task_queue.get_nowait()
                        self._task_queue.task_done()
                    except asyncio.QueueEmpty:
                        break

        logger.info("[Orchestrator] Shutdown operations completed")

    async def _disconnect_services(self) -> None:
        """Disconnect all registered services."""
        for name, service in self._services.items():
            try:
                if hasattr(service, 'disconnect'):
                    await service.disconnect()
                elif hasattr(service, 'shutdown'):
                    await service.shutdown()
                logger.info(f"[Orchestrator] Service '{name}' disconnected")
            except Exception as e:
                logger.error(f"[Orchestrator] Error disconnecting service '{name}': {e}")

        # Emit shutdown event
        await self.emit_event(Event(
            event_type=EventType.SHUTDOWN,
            payload={"reason": "graceful_shutdown"},
            source="orchestrator"
        ))

        # Transition to IDLE
        self.current_state = SystemState.IDLE

        logger.info("[Orchestrator] Shutdown complete")

    # ==================== State Management ====================

    def get_state(self) -> SystemState:
        """
        Get the current FSM state.

        Returns:
            Current SystemState enum value
        """
        return self.current_state

    async def request_state_change(
        self,
        target_state: SystemState,
        reason: str = "",
        force: bool = False
    ) -> TransitionResult:
        """
        Request a state transition.

        Args:
            target_state: Desired new state
            reason: Human-readable reason for transition
            force: If True, skip cooldown check (use carefully)

        Returns:
            TransitionResult indicating success or failure reason

        State Transition Rules:
            - IDLE can transition to TEXT or IMAGE
            - TEXT can transition to IDLE or IMAGE (with cooldown)
            - IMAGE can transition to IDLE or TEXT (with cooldown)
            - Any state can transition to ERROR
            - ERROR can only transition to IDLE
        """
        previous_state = self.current_state

        # Validate transition
        if not self._is_valid_transition(previous_state, target_state):
            logger.warning(
                f"[Orchestrator] Invalid transition: {previous_state.name} -> {target_state.name}"
            )
            return TransitionResult.INVALID_TRANSITION

        # Check cooldown (unless forced or transitioning to/from ERROR)
        if not force and target_state != SystemState.ERROR and previous_state != SystemState.ERROR:
            cooldown_ok = await self._check_cooldown()
            if not cooldown_ok:
                logger.debug(
                    f"[Orchestrator] Cooldown active for {previous_state.name} -> {target_state.name}"
                )
                return TransitionResult.COOLDOWN_ACTIVE

        # Perform transition
        try:
            self.current_state = target_state
            self._last_transition_time = datetime.now()

            # Track metrics
            transition_key = f"{previous_state.name}_to_{target_state.name}"
            self._metrics["state_transitions"][transition_key] += 1

            # Emit state change event
            await self.emit_event(StateChangeEvent(
                event_type=EventType.STATE_CHANGE,
                previous_state=previous_state,
                new_state=target_state,
                transition_reason=reason,
                source="orchestrator"
            ))

            logger.info(
                f"[Orchestrator] State transition: {previous_state.name} -> {target_state.name} "
                f"(reason: {reason or 'none'})"
            )
            return TransitionResult.SUCCESS

        except Exception as e:
            logger.error(f"[Orchestrator] State transition error: {e}")
            self._metrics["last_error"] = str(e)
            return TransitionResult.ERROR

    def _is_valid_transition(
        self,
        from_state: SystemState,
        to_state: SystemState
    ) -> bool:
        """
        Validate if a state transition is allowed.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is valid according to FSM rules
        """
        if from_state == to_state:
            return True  # No-op transitions are valid

        valid_targets = VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid_targets

    async def _check_cooldown(self) -> bool:
        """
        Check if GPU cooldown period has elapsed.

        Returns:
            True if cooldown has passed, False if still waiting

        Note:
            Cooldown prevents rapid GPU context switching which
            can cause instability and memory fragmentation.
        """
        if self._last_transition_time is None:
            return True

        elapsed = datetime.now() - self._last_transition_time
        cooldown_delta = timedelta(seconds=self.DEFAULT_COOLDOWN_SECONDS)

        return elapsed >= cooldown_delta

    # ==================== Task Management ====================

    async def submit_task(self, task: TaskEvent) -> str:
        """
        Submit a new task to the processing queue.

        Args:
            task: TaskEvent containing task details

        Returns:
            Task ID for tracking

        Raises:
            QueueFullError: If queue is at maximum capacity
            InvalidTaskError: If task validation fails
        """
        if not self._task_queue:
            raise RuntimeError("Orchestrator not initialized")

        if self._task_queue.qsize() >= self.MAX_QUEUE_SIZE:
            raise RuntimeError(f"Task queue full (max: {self.MAX_QUEUE_SIZE})")

        # Set event type if not set
        if task.event_type is None:
            task.event_type = EventType.TASK_SUBMIT

        # Add to queue with priority (lower number = higher priority)
        priority_value = task.priority.value if task.priority else TaskPriority.NORMAL.value
        await self._task_queue.put((priority_value, task.timestamp, task))

        # Track active task
        self._active_tasks[task.task_id] = task

        # Update high water mark
        current_size = self._task_queue.qsize()
        if current_size > self._metrics["queue_high_water_mark"]:
            self._metrics["queue_high_water_mark"] = current_size

        # Emit submit event
        await self.emit_event(Event(
            event_type=EventType.TASK_SUBMIT,
            payload={"task_id": task.task_id, "task_type": task.task_type},
            source="orchestrator"
        ))

        logger.info(
            f"[Orchestrator] Task submitted: {task.task_id} "
            f"(type: {task.task_type}, priority: {task.priority.name})"
        )

        return task.task_id

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending or running task.

        Args:
            task_id: ID of task to cancel

        Returns:
            True if task was found and cancelled

        Note:
            Running tasks may not be immediately cancellable
            depending on the service implementation.
        """
        if task_id in self._active_tasks:
            task = self._active_tasks.pop(task_id)

            # Emit cancel event
            await self.emit_event(Event(
                event_type=EventType.TASK_CANCEL,
                payload={"task_id": task_id},
                source="orchestrator"
            ))

            logger.info(f"[Orchestrator] Task cancelled: {task_id}")
            return True

        return False

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a task.

        Args:
            task_id: ID of task to query

        Returns:
            Dict with task status, or None if not found
        """
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            return {
                "task_id": task_id,
                "status": "pending" if task_id not in self._task_results else "completed",
                "task_type": task.task_type,
                "priority": task.priority.name,
                "submitted_at": task.timestamp.isoformat(),
            }

        if task_id in self._task_results:
            return {
                "task_id": task_id,
                "status": "completed",
                "result": self._task_results[task_id],
            }

        return None

    async def _process_task(self, task: TaskEvent) -> None:
        """
        Process a single task through the appropriate service.

        Args:
            task: TaskEvent to process

        Flow:
            1. Determine required state for task type
            2. Request state transition
            3. Dispatch to appropriate service
            4. Wait for completion
            5. Emit completion event
            6. Transition back to IDLE
        """
        start_time = time.time()
        task_id = task.task_id

        try:
            # Emit start event
            await self.emit_event(Event(
                event_type=EventType.TASK_START,
                payload={"task_id": task_id, "task_type": task.task_type},
                source="orchestrator"
            ))

            # Determine target state based on task type
            target_state = self._get_state_for_task(task.task_type)

            # Request state transition
            if target_state != self.current_state:
                result = await self.request_state_change(
                    target_state,
                    reason=f"Processing task {task_id}"
                )
                if result != TransitionResult.SUCCESS:
                    raise RuntimeError(f"State transition failed: {result.name}")

            # Acquire GPU lock for GPU tasks
            if task.is_gpu_task():
                async with self._gpu_lock:
                    await self._execute_task(task)
            else:
                await self._execute_task(task)

            # Calculate processing time
            elapsed = time.time() - start_time
            self._metrics["tasks_processed"] += 1
            self._metrics["total_processing_time"] += elapsed

            # Store result
            self._task_results[task_id] = task.result_data

            # Emit completion event
            await self.emit_event(Event(
                event_type=EventType.TASK_COMPLETE,
                payload={
                    "task_id": task_id,
                    "processing_time": elapsed,
                    "result_preview": str(task.result_data)[:100] if task.result_data else None
                },
                source="orchestrator"
            ))

            logger.info(f"[Orchestrator] Task completed: {task_id} ({elapsed:.2f}s)")

        except Exception as e:
            self._metrics["tasks_failed"] += 1
            self._metrics["last_error"] = str(e)
            task.error_message = str(e)

            # Emit failure event
            await self.emit_event(Event(
                event_type=EventType.TASK_FAILED,
                payload={"task_id": task_id, "error": str(e)},
                source="orchestrator"
            ))

            logger.error(f"[Orchestrator] Task failed: {task_id} - {e}")

        finally:
            # Remove from active tasks
            self._active_tasks.pop(task_id, None)

            # Return to IDLE state
            if self.current_state != SystemState.IDLE:
                await self.request_state_change(
                    SystemState.IDLE,
                    reason=f"Task {task_id} completed"
                )

    def _get_state_for_task(self, task_type: str) -> SystemState:
        """Map task type to required system state."""
        mapping = {
            "llm": SystemState.TEXT,
            "chat": SystemState.TEXT,
            "text": SystemState.TEXT,
            "image": SystemState.IMAGE,
            "comfyui": SystemState.IMAGE,
            "document": SystemState.IDLE,  # CPU-based, no state change needed
        }
        return mapping.get(task_type.lower(), SystemState.IDLE)

    async def _execute_task(self, task: TaskEvent) -> None:
        """
        Execute task through the appropriate service.

        Args:
            task: TaskEvent to execute
        """
        service = self._services.get(task.task_type)

        if service is None:
            # Try generic service lookup
            service = self._services.get("default")

        if service is None:
            raise RuntimeError(f"No service registered for task type: {task.task_type}")

        # Execute through service
        if hasattr(service, 'execute'):
            task.result_data = await service.execute(task.request_data)
        elif hasattr(service, 'process'):
            task.result_data = await service.process(task.request_data)
        elif hasattr(service, 'generate'):
            task.result_data = await service.generate(**task.request_data)
        else:
            raise RuntimeError(f"Service '{task.task_type}' has no execute method")

    # ==================== Chat Processing Pipeline ====================

    async def process_chat(
        self,
        context: ChatContext,
        rag_search_fn: Optional[Callable] = None,
        llm_generate_fn: Optional[Callable] = None
    ) -> ChatContext:
        """
        Process a chat request through the full pipeline.

        This implements the legacy ChatStateMachine flow:
            ANALYZING -> RETRIEVING (optional) -> GENERATING -> COMPLETED

        Args:
            context: ChatContext with request data
            rag_search_fn: Function to search RAG documents
            llm_generate_fn: Function to generate LLM response

        Returns:
            Updated ChatContext with response
        """
        start_time = time.time()

        try:
            # ANALYZING: Determine if RAG should be used
            context.current_state = ChatState.ANALYZING
            context = await self._analyze_request(context)

            # RETRIEVING: Search documents if RAG is enabled
            if context.should_use_rag and rag_search_fn:
                context.current_state = ChatState.RETRIEVING
                context = await self._retrieve_documents(context, rag_search_fn)

            # GENERATING: Call LLM
            context.current_state = ChatState.GENERATING
            if llm_generate_fn:
                context = await self._generate_response(context, llm_generate_fn)

            context.current_state = ChatState.COMPLETED

        except Exception as e:
            logger.error(f"[Orchestrator] Chat processing error: {e}", exc_info=True)
            context.current_state = ChatState.ERROR
            context.error_message = str(e)
            context.state_info = "ERROR"

        context.processing_time = time.time() - start_time
        return context

    async def process_chat_stream(
        self,
        context: ChatContext,
        rag_search_fn: Optional[Callable] = None,
        llm_stream_fn: Optional[Callable] = None
    ) -> AsyncGenerator[str, None]:
        """
        Process chat with streaming response.

        Args:
            context: ChatContext with request data
            rag_search_fn: Function to search RAG documents
            llm_stream_fn: Async generator function for streaming LLM response

        Yields:
            Text chunks from LLM response
        """
        start_time = time.time()

        try:
            # ANALYZING
            context.current_state = ChatState.ANALYZING
            context = await self._analyze_request(context)

            # RETRIEVING
            if context.should_use_rag and rag_search_fn:
                context.current_state = ChatState.RETRIEVING
                context = await self._retrieve_documents(context, rag_search_fn)

            # GENERATING (streaming)
            context.current_state = ChatState.GENERATING

            if llm_stream_fn:
                # Build final prompt with RAG context
                final_prompt = self._build_final_prompt(context)

                # Acquire GPU lock and stream
                async with self._gpu_lock:
                    async for chunk in llm_stream_fn(
                        system_prompt=context.system_prompt,
                        user_prompt=final_prompt,
                        mode=context.selected_mode or context.mode
                    ):
                        context.final_answer += chunk
                        yield chunk

            context.current_state = ChatState.COMPLETED

        except Exception as e:
            logger.error(f"[Orchestrator] Stream error: {e}", exc_info=True)
            context.current_state = ChatState.ERROR
            context.error_message = str(e)
            yield f"\n[Error: {str(e)}]"

        context.processing_time = time.time() - start_time

    async def _analyze_request(self, context: ChatContext) -> ChatContext:
        """
        Analyze the user's question to classify intent.

        Intent Classification Flow:
            1. Keyword-based fast filtering (for speed)
            2. LLM-based precision analysis (for accuracy)
            3. Route to appropriate service based on intent

        Returns:
            Updated ChatContext with intent_result, target_service, and refined_prompt
        """
        user_query = context.user_query

        # =================================================================
        # Step 1: Keyword-based fast filtering (for speed)
        # =================================================================
        image_keywords_ko = [
            "그려", "그림", "이미지", "사진", "만들어", "생성",
            "일러스트", "그래픽", "캐릭터", "배경", "풍경",
            "포스터", "로고", "아이콘", "디자인"
        ]
        image_keywords_en = [
            "draw", "create", "generate", "image", "picture",
            "illustration", "artwork", "painting", "render"
        ]

        query_lower = user_query.lower()

        # Fast path: Clear image request keywords detected
        for kw in image_keywords_ko + image_keywords_en:
            if kw in query_lower:
                logger.info(f"[Orchestrator] Image keyword detected: '{kw}'")
                context.intent_result = IntentResult(
                    intent="image_request",
                    confidence=0.9,
                    metadata={"detected_keyword": kw}
                )
                context.target_service = "image"
                context.state_info = "IMAGE_REQUEST"

                # Generate Flux-optimized prompt
                context.refined_prompt = await self._expand_prompt_for_flux(user_query)
                return context

        # =================================================================
        # Step 2: LLM-based precision analysis (for ambiguous cases)
        # =================================================================
        llm_service = self._services.get("llm")

        if llm_service:
            try:
                analysis_prompt = f"""Analyze the following user input and classify its intent.

User Input: "{user_query}"

Classify into ONE of these categories (respond with keyword only):
1. simple_chat - casual conversation, greetings, small talk
2. image_request - request for picture, image, visual creation
3. document_qa - asking for specific knowledge, documents, data, information

Response (one word only):"""

                # Use fast mode for quick classification
                raw_intent = await llm_service.generate(
                    prompt=analysis_prompt,
                    max_tokens=10,
                    temperature=0.1
                )
                intent = raw_intent.strip().lower()
                logger.debug(f"[Orchestrator] LLM intent classification: {intent}")

                # Parse LLM response
                if "image" in intent:
                    context.intent_result = IntentResult(
                        intent="image_request",
                        confidence=0.95,
                        metadata={"source": "llm_analysis"}
                    )
                    context.target_service = "image"
                    context.state_info = "IMAGE_REQUEST"
                    context.refined_prompt = await self._expand_prompt_for_flux(user_query)

                elif "document" in intent:
                    context.intent_result = IntentResult(
                        intent="document_qa",
                        confidence=0.9,
                        metadata={"source": "llm_analysis"}
                    )
                    context.target_service = "document"
                    context.should_use_rag = True
                    context.state_info = "DOCUMENT_QA"

                else:
                    # Default to simple chat
                    context.intent_result = IntentResult(
                        intent="simple_chat",
                        confidence=1.0,
                        metadata={"source": "llm_analysis"}
                    )
                    context.target_service = "llm"
                    context.state_info = "SIMPLE_CHAT"

            except Exception as e:
                logger.warning(f"[Orchestrator] LLM intent classification failed: {e}")
                # Fallback to rule-based classification
                context = self._fallback_intent_classification(context)
        else:
            # No LLM service available, use fallback
            context = self._fallback_intent_classification(context)

        # =================================================================
        # Step 3: Mode selection for LLM-based responses
        # =================================================================
        if context.target_service in ("llm", "document"):
            if context.mode == "auto":
                context.selected_mode = self._select_mode_for_query(user_query)
            else:
                context.selected_mode = context.mode

        logger.info(
            f"[Orchestrator] Intent: {context.intent_result.intent if context.intent_result else 'unknown'}, "
            f"Target: {context.target_service}, Mode: {context.selected_mode}"
        )

        return context

    def _fallback_intent_classification(self, context: ChatContext) -> ChatContext:
        """
        Fallback intent classification using rule-based heuristics.

        Used when LLM service is unavailable.
        """
        user_query = context.user_query

        # Check for question patterns suggesting document lookup
        doc_patterns = [
            "뭐야", "뭔가요", "알려줘", "설명해", "어떻게",
            "what is", "explain", "how to", "tell me about"
        ]

        query_lower = user_query.lower()
        for pattern in doc_patterns:
            if pattern in query_lower and context.use_rag:
                context.intent_result = IntentResult(
                    intent="document_qa",
                    confidence=0.7,
                    metadata={"source": "fallback_rules"}
                )
                context.target_service = "document"
                context.should_use_rag = True
                context.state_info = "DOCUMENT_QA"
                return context

        # Default to simple chat
        context.intent_result = IntentResult(
            intent="simple_chat",
            confidence=0.8,
            metadata={"source": "fallback_rules"}
        )
        context.target_service = "llm"
        context.state_info = "SIMPLE_CHAT"
        return context

    async def _expand_prompt_for_flux(self, korean_prompt: str) -> str:
        """
        Expand Korean user request into Flux-optimized English prompt.

        Flux Model Prompt Guidelines:
            - Natural language description (not tag-based)
            - Rich detail for composition, lighting, style
            - Specify artistic style explicitly
            - Include quality modifiers

        Args:
            korean_prompt: Original Korean user request

        Returns:
            Flux-optimized English prompt
        """
        llm_service = self._services.get("llm")

        if not llm_service:
            # Basic translation fallback
            logger.warning("[Orchestrator] No LLM for prompt expansion, using original")
            return korean_prompt

        try:
            expansion_prompt = f"""You are an expert prompt engineer for the Flux image generation model.

Convert the following Korean image request into an optimized English prompt for Flux.

Korean Request: "{korean_prompt}"

Requirements:
1. Translate to natural, descriptive English
2. Add specific details: composition, lighting, atmosphere, colors
3. Include artistic style (photorealistic, digital art, oil painting, etc.)
4. Add quality modifiers (highly detailed, 8k, professional)
5. Keep the core intent but enhance visual description
6. Output ONLY the final prompt, no explanations

Optimized Flux Prompt:"""

            refined = await llm_service.generate(
                prompt=expansion_prompt,
                max_tokens=200,
                temperature=0.7
            )

            refined_prompt = refined.strip()

            # Ensure quality suffix if not present
            quality_keywords = ["detailed", "8k", "4k", "high quality", "professional"]
            if not any(kw in refined_prompt.lower() for kw in quality_keywords):
                refined_prompt += ", highly detailed, professional quality"

            logger.info(f"[Orchestrator] Prompt expanded: {refined_prompt[:100]}...")
            return refined_prompt

        except Exception as e:
            logger.error(f"[Orchestrator] Prompt expansion failed: {e}")
            return korean_prompt

    def _select_mode_for_query(self, query: str) -> str:
        """
        Select processing mode based on query analysis.

        Ported from legacy should_use_main_model() function.
        """
        import re

        # Keywords requiring deep thinking
        deep_keywords = [
            '분석', '리포트', '전망', '전략', '계획', '설계',
            '비교', '평가', '검토', '연구', '조사', '탐구',
            'analysis', 'report', 'strategy', 'plan', 'research',
            'compare', 'evaluate', 'review', 'investigate'
        ]

        query_lower = query.lower()
        for keyword in deep_keywords:
            if keyword in query_lower:
                logger.debug(f"[Orchestrator] Keyword '{keyword}' detected -> thinking mode")
                return "thinking"

        # Check for simple exclamations/emoticons
        hangul_consonants = re.findall(r'[ㅋㅎㄷㄱㅅㅈㅂㄴㅁㅇㄹ]+', query)
        consonant_ratio = sum(len(c) for c in hangul_consonants) / max(len(query), 1)

        if consonant_ratio > 0.5:
            logger.debug("[Orchestrator] Simple exclamation detected -> fast mode")
            return "fast"

        # Length-based selection
        if len(query) < 50:
            return "fast"
        else:
            return "thinking"

    async def _retrieve_documents(
        self,
        context: ChatContext,
        rag_search_fn: Callable
    ) -> ChatContext:
        """
        Retrieve relevant documents using RAG.
        """
        if not context.rag_collection_name:
            logger.warning("[Orchestrator] No RAG collection specified")
            context.should_use_rag = False
            return context

        try:
            # Build search query (context-aware for short queries)
            search_query = context.user_query
            if len(context.user_query) < 20 and context.session_history:
                last_user_msg = next(
                    (msg['content'] for msg in reversed(context.session_history)
                     if msg.get('role') == 'user'),
                    ''
                )
                if last_user_msg:
                    search_query = f"{last_user_msg} {context.user_query}"
                    logger.debug(f"[Orchestrator] Context-aware search: {search_query[:100]}...")

            # Execute search
            results = rag_search_fn(
                query=search_query,
                collection_name=context.rag_collection_name,
                k=5
            )

            if results and len(results) > 0:
                # Build context from results
                context_parts = []
                for i, hit in enumerate(results[:3], 1):
                    text = hit.get("text", "")
                    metadata = hit.get("metadata", {})
                    source = metadata.get("source_file", metadata.get("source", "Unknown"))
                    context_parts.append(f"[Document {i}] {source}\n{text}")

                    context.rag_sources.append({
                        "text": text[:200],
                        "source": source,
                        "score": hit.get("score", 0.0)
                    })

                context.rag_context = "\n\n".join(context_parts)
                context.rag_used = True
                context.state_info = "RAG_USED"
                logger.info(f"[Orchestrator] Retrieved {len(results)} documents")
            else:
                context.should_use_rag = False
                context.state_info = "RAG_NO_RESULTS"
                logger.info("[Orchestrator] No RAG results found")

        except Exception as e:
            logger.error(f"[Orchestrator] RAG retrieval error: {e}")
            context.should_use_rag = False
            context.state_info = "RAG_ERROR"

        return context

    async def _generate_response(
        self,
        context: ChatContext,
        llm_generate_fn: Callable
    ) -> ChatContext:
        """
        Generate LLM response.
        """
        final_prompt = self._build_final_prompt(context)

        try:
            async with self._gpu_lock:
                context.final_answer = await llm_generate_fn(
                    system_prompt=context.system_prompt,
                    user_prompt=final_prompt,
                    mode=context.selected_mode or context.mode
                )
            logger.info("[Orchestrator] LLM generation completed")
        except Exception as e:
            logger.error(f"[Orchestrator] LLM generation error: {e}")
            raise

        return context

    def _build_final_prompt(self, context: ChatContext) -> str:
        """
        Build the final user prompt with all context.
        """
        parts = []

        # Add user memories
        if context.user_memories:
            memory_text = "\n".join([f"- {mem}" for mem in context.user_memories[:3]])
            parts.append(f"=== User Preferences ===\n{memory_text}")

        # Add RAG context
        if context.rag_used and context.rag_context:
            parts.append(f"=== Reference Documents ===\n{context.rag_context}")

        # Add session history
        if context.session_history:
            history_parts = []
            for msg in context.session_history[-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")[:200]
                if role and content:
                    history_parts.append(f"{role.upper()}: {content}")
            if history_parts:
                parts.append("=== Recent Conversation ===\n" + "\n".join(history_parts))

        # Add current query
        parts.append(f"=== Current Question ===\n{context.user_query}")

        return "\n\n".join(parts)

    # ==================== Event System ====================

    def register_handler(
        self,
        event_type: EventType,
        handler: Callable[[Event], Any]
    ) -> None:
        """
        Register an event handler callback.

        Args:
            event_type: Type of events to handle
            handler: Async callable to invoke on event

        Note:
            Multiple handlers can be registered for same event type.
            Handlers are called in registration order.
        """
        self._event_handlers[event_type].append(handler)
        logger.debug(f"[Orchestrator] Handler registered for {event_type.name}")

    def unregister_handler(
        self,
        event_type: EventType,
        handler: Callable[[Event], Any]
    ) -> bool:
        """
        Remove a previously registered event handler.

        Args:
            event_type: Type of events
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        handlers = self._event_handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug(f"[Orchestrator] Handler unregistered for {event_type.name}")
            return True
        return False

    async def emit_event(self, event: Event) -> None:
        """
        Emit an event to all registered handlers.

        Args:
            event: Event to broadcast

        Note:
            Events are processed asynchronously.
            Handler exceptions are logged but don't stop propagation.
        """
        handlers = self._event_handlers.get(event.event_type, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"[Orchestrator] Event handler error for {event.event_type.name}: {e}"
                )

    # ==================== Service Management ====================

    def register_service(self, name: str, service: Any) -> None:
        """
        Register a service instance with the orchestrator.

        Args:
            name: Service identifier (e.g., 'llm', 'image', 'document')
            service: Service instance implementing required interface
        """
        self._services[name] = service
        logger.info(f"[Orchestrator] Service registered: {name}")

    def get_service(self, name: str) -> Optional[Any]:
        """
        Retrieve a registered service by name.

        Args:
            name: Service identifier

        Returns:
            Service instance or None if not found
        """
        return self._services.get(name)

    # ==================== Main Loop ====================

    async def run(self) -> None:
        """
        Main event loop for the orchestrator.

        This is the primary async loop that:
            1. Monitors the task queue
            2. Processes tasks according to priority
            3. Handles state transitions
            4. Responds to system events

        Should be run as the main coroutine:
            asyncio.run(orchestrator.run())
        """
        if not self._task_queue:
            await self.initialize()

        self._is_running = True
        logger.info("[Orchestrator] Main loop started")

        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("[Orchestrator] Main loop cancelled")
        except Exception as e:
            logger.error(f"[Orchestrator] Main loop error: {e}", exc_info=True)
            await self.request_state_change(SystemState.ERROR, reason=str(e))
        finally:
            await self.shutdown()

    async def _main_loop(self) -> None:
        """
        Internal main loop implementation.

        Separated from run() to allow for setup/teardown.

        Loop Steps:
            1. Check for shutdown signal
            2. Get next task from queue (with timeout)
            3. Process task if available
            4. Yield control to other coroutines
        """
        while self._is_running:
            # Check shutdown signal
            if self._shutdown_event and self._shutdown_event.is_set():
                break

            try:
                # Get next task with timeout
                priority, timestamp, task = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=self.QUEUE_TIMEOUT
                )

                # Process the task
                await self._process_task(task)

                # Mark task as done
                self._task_queue.task_done()

            except asyncio.TimeoutError:
                # No task available, yield control
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"[Orchestrator] Loop iteration error: {e}")
                await asyncio.sleep(0.1)

    # ==================== Health & Monitoring ====================

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform system health check.

        Returns:
            Dict containing:
                - state: Current FSM state
                - queue_size: Number of pending tasks
                - services_status: Health of each service
                - uptime: Time since initialization
                - last_error: Most recent error (if any)
        """
        # Calculate uptime
        uptime_seconds = 0
        if self._metrics["start_time"]:
            uptime_seconds = (datetime.now() - self._metrics["start_time"]).total_seconds()

        # Check services
        services_status = {}
        for name, service in self._services.items():
            try:
                if hasattr(service, 'health_check'):
                    services_status[name] = await service.health_check()
                elif hasattr(service, 'is_available'):
                    services_status[name] = {"available": service.is_available()}
                else:
                    services_status[name] = {"status": "unknown"}
            except Exception as e:
                services_status[name] = {"status": "error", "error": str(e)}

        return {
            "state": self.current_state.name,
            "is_running": self._is_running,
            "queue_size": self._task_queue.qsize() if self._task_queue else 0,
            "active_tasks": len(self._active_tasks),
            "services_status": services_status,
            "uptime_seconds": uptime_seconds,
            "last_error": self._metrics["last_error"],
            "gpu_lock_held": self._gpu_lock.locked() if self._gpu_lock else False,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get orchestrator performance metrics.

        Returns:
            Dict containing:
                - tasks_processed: Total tasks completed
                - tasks_failed: Total tasks failed
                - avg_processing_time: Average task duration
                - state_transitions: Count by transition type
                - queue_high_water_mark: Max queue size reached
        """
        total = self._metrics["tasks_processed"]
        avg_time = (
            self._metrics["total_processing_time"] / total
            if total > 0 else 0.0
        )

        return {
            "tasks_processed": total,
            "tasks_failed": self._metrics["tasks_failed"],
            "avg_processing_time": round(avg_time, 3),
            "state_transitions": dict(self._metrics["state_transitions"]),
            "queue_high_water_mark": self._metrics["queue_high_water_mark"],
        }


# =============================================================================
# Factory Function (compatibility with legacy create_state_machine)
# =============================================================================

def create_chat_context(
    user_query: str,
    system_prompt: str = "",
    use_rag: bool = False,
    rag_collection_name: Optional[str] = None,
    user_memories: Optional[List[str]] = None,
    session_history: Optional[List[Dict[str, str]]] = None,
    mode: str = "thinking"
) -> ChatContext:
    """
    Factory function to create ChatContext.

    Provides compatibility with legacy create_state_machine() API.

    Args:
        user_query: User's question
        system_prompt: System prompt for the folder/agent
        use_rag: Whether RAG is enabled
        rag_collection_name: Collection name for RAG search
        user_memories: List of user memory strings
        session_history: List of previous messages
        mode: Processing mode (fast, thinking, research, auto)

    Returns:
        ChatContext instance ready for processing
    """
    return ChatContext(
        user_query=user_query,
        system_prompt=system_prompt,
        use_rag=use_rag,
        rag_collection_name=rag_collection_name,
        user_memories=user_memories or [],
        session_history=session_history or [],
        mode=mode
    )


def get_orchestrator() -> Orchestrator:
    """
    Get the singleton Orchestrator instance.

    Returns:
        The global Orchestrator instance
    """
    return Orchestrator()
