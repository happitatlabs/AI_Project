"""
LLM Service - Ollama Integration

This module provides integration with Ollama for local LLM inference.
Supports streaming responses, context management, and multiple models.

Features:
    - Streaming and non-streaming generation
    - Context/history management
    - Multiple model support (fast/thinking modes)
    - GPU lock integration with Orchestrator

Connection:
    - Default: http://localhost:11434
    - Uses Ollama REST API
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class LLMStatus(Enum):
    """LLM service status."""

    DISCONNECTED = auto()  # Not connected to Ollama
    CONNECTED = auto()     # Connected, ready for requests
    GENERATING = auto()    # Currently generating response
    ERROR = auto()         # Error state


class ModelType(Enum):
    """Model type for different use cases."""

    FAST = "fast"           # Lightweight model for quick responses
    THINKING = "thinking"   # Main model for deep reasoning
    RESEARCH = "research"   # Model with web search capability


@dataclass
class ChatMessage:
    """
    Single message in conversation.

    Attributes:
        role: 'system', 'user', or 'assistant'
        content: Message content
        timestamp: When message was created
    """
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, str]:
        """Convert to Ollama message format."""
        return {"role": self.role, "content": self.content}


@dataclass
class ChatContext:
    """
    Conversation context for chat sessions.

    Attributes:
        system_prompt: System instructions
        messages: Conversation history
        max_history: Maximum messages to retain
    """
    system_prompt: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    max_history: int = 20

    def add_message(self, role: str, content: str) -> None:
        """Add message to history."""
        self.messages.append(ChatMessage(role=role, content=content))
        # Trim history if needed
        if len(self.messages) > self.max_history:
            # Keep system context intact, trim oldest user/assistant pairs
            self.messages = self.messages[-self.max_history:]

    def get_messages(self) -> List[Dict[str, str]]:
        """Get messages in Ollama format."""
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.extend([m.to_dict() for m in self.messages])
        return msgs

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages.clear()


@dataclass
class LLMRequest:
    """
    Request structure for LLM inference.

    Attributes:
        prompt: User prompt or message
        model: Model name (e.g., 'llama3', 'mistral')
        system_prompt: Optional system message
        context: Conversation context for multi-turn
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Maximum tokens to generate
        stream: Whether to stream response
    """

    prompt: str
    model: str = "llama3"
    system_prompt: Optional[str] = None
    context: Optional[List[int]] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True


@dataclass
class LLMResponse:
    """
    Response structure from LLM inference.

    Attributes:
        text: Generated text response
        model: Model that generated the response
        context: Updated context for multi-turn
        tokens_generated: Number of tokens generated
        generation_time_ms: Time to generate in milliseconds
        is_complete: Whether generation finished normally
    """

    text: str
    model: str
    context: Optional[List[int]] = None
    tokens_generated: int = 0
    generation_time_ms: float = 0.0
    is_complete: bool = True


@dataclass
class GenerationResult:
    """
    Result from LLM generation.

    Attributes:
        content: Generated text
        model: Model used
        total_duration_ms: Total time including loading
        eval_count: Number of tokens generated
        eval_duration_ms: Time spent generating
        prompt_eval_count: Number of prompt tokens
    """
    content: str
    model: str
    total_duration_ms: float = 0.0
    eval_count: int = 0
    eval_duration_ms: float = 0.0
    prompt_eval_count: int = 0
    done_reason: str = ""

    @property
    def tokens_per_second(self) -> float:
        """Calculate generation speed."""
        if self.eval_duration_ms > 0:
            return (self.eval_count / self.eval_duration_ms) * 1000
        return 0.0


class LLMServiceError(Exception):
    """Exception for LLM service failures."""
    pass


# =============================================================================
# LLM Service Class
# =============================================================================

class LLMService:
    """
    Service for LLM inference via Ollama.

    Handles:
        - Streaming and non-streaming generation
        - Multiple model management
        - Context/history tracking
        - GPU resource coordination

    Usage:
        service = LLMService()
        await service.connect()

        # Non-streaming
        result = await service.generate("Hello!")

        # Streaming
        async for chunk in service.generate_stream("Hello!"):
            print(chunk, end="")

        await service.disconnect()
    """

    DEFAULT_HOST: str = "localhost"
    DEFAULT_PORT: int = 11434
    DEFAULT_TIMEOUT: float = 300.0  # 5 minutes

    # Model configuration
    DEFAULT_MODELS = {
        ModelType.FAST: "qwen2.5:3b",
        ModelType.THINKING: "qwen2.5:14b",
        ModelType.RESEARCH: "qwen2.5:14b",
    }

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        models: Optional[Dict[ModelType, str]] = None
    ):
        """
        Initialize LLM Service.

        Args:
            host: Ollama server hostname
            port: Ollama server port
            timeout: Request timeout in seconds
            models: Model mapping for different types
        """
        self.host = host
        self.port = port
        self.timeout = timeout

        self._base_url: str = f"http://{host}:{port}"
        self._status: LLMStatus = LLMStatus.DISCONNECTED
        self._session: Optional[aiohttp.ClientSession] = None

        # Model configuration
        self._models = models or self.DEFAULT_MODELS.copy()
        self._current_model: Optional[str] = None

        # Context management
        self._contexts: Dict[str, ChatContext] = {}
        self._default_context: ChatContext = ChatContext()

        # Generation tracking
        self._is_generating: bool = False
        self._cancel_requested: bool = False

    # ==================== Connection Management ====================

    async def connect(self) -> bool:
        """
        Establish connection to Ollama server.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If Ollama server is unreachable
        """
        try:
            logger.info(f"[LLMService] Connecting to Ollama at {self._base_url}")

            # Create HTTP session
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

            # Test connection
            async with self._session.get(f"{self._base_url}/api/tags") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Ollama returned status {resp.status}")
                data = await resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                logger.info(f"[LLMService] Connected. Available models: {models}")

            self._status = LLMStatus.CONNECTED
            return True

        except aiohttp.ClientError as e:
            logger.error(f"[LLMService] Connection failed: {e}")
            self._status = LLMStatus.ERROR
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
        except Exception as e:
            logger.error(f"[LLMService] Unexpected connection error: {e}")
            self._status = LLMStatus.ERROR
            raise

    async def disconnect(self) -> None:
        """Close connection to Ollama server."""
        logger.info("[LLMService] Disconnecting...")

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        self._status = LLMStatus.DISCONNECTED
        logger.info("[LLMService] Disconnected")

    async def health_check(self) -> bool:
        """
        Check if Ollama server is healthy.

        Returns:
            True if server responds
        """
        if not self._session:
            return False

        try:
            async with self._session.get(
                f"{self._base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_status(self) -> LLMStatus:
        """Get current service status."""
        return self._status

    def is_ready(self) -> bool:
        """Check if service is ready to accept requests."""
        return self._status == LLMStatus.CONNECTED

    def is_available(self) -> bool:
        """Check if service is available (alias for orchestrator compatibility)."""
        return self._status in (LLMStatus.CONNECTED, LLMStatus.GENERATING)

    # ==================== Model Management ====================

    async def list_models(self) -> List[str]:
        """List available models on Ollama server."""
        if not self._session:
            return []

        try:
            async with self._session.get(f"{self._base_url}/api/tags") as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"[LLMService] Failed to list models: {e}")
            return []

    async def load_model(self, model_name: str) -> bool:
        """
        Pre-load a model into VRAM.

        Args:
            model_name: Name of model to load

        Returns:
            True if model loaded successfully
        """
        if not self._session:
            return False

        try:
            logger.info(f"[LLMService] Loading model: {model_name}")
            # Send a minimal generate request to load model
            async with self._session.post(
                f"{self._base_url}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": "5m"}
            ) as resp:
                if resp.status == 200:
                    self._current_model = model_name
                    logger.info(f"[LLMService] Model loaded: {model_name}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[LLMService] Failed to load model: {e}")
            return False

    async def unload_model(self) -> bool:
        """
        Unload current model from VRAM.

        Returns:
            True if model was unloaded
        """
        if not self._session or not self._current_model:
            return False

        try:
            logger.info(f"[LLMService] Unloading model: {self._current_model}")
            # Set keep_alive to 0 to unload immediately
            async with self._session.post(
                f"{self._base_url}/api/generate",
                json={"model": self._current_model, "prompt": "", "keep_alive": 0}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"[LLMService] Model unloaded: {self._current_model}")
                    self._current_model = None
                    return True
                return False
        except Exception as e:
            logger.error(f"[LLMService] Failed to unload model: {e}")
            return False

    async def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama registry.

        Args:
            model_name: Model to pull

        Returns:
            True if pull successful
        """
        if not self._session:
            return False

        try:
            logger.info(f"[LLMService] Pulling model: {model_name}")
            async with self._session.post(
                f"{self._base_url}/api/pull",
                json={"name": model_name}
            ) as resp:
                if resp.status != 200:
                    return False
                # Stream response to track progress
                async for line in resp.content:
                    if line:
                        data = json.loads(line)
                        status = data.get("status", "")
                        logger.debug(f"[LLMService] Pull status: {status}")
                return True
        except Exception as e:
            logger.error(f"[LLMService] Failed to pull model: {e}")
            return False

    def get_model_for_mode(self, mode: str) -> str:
        """
        Get model name for processing mode.

        Args:
            mode: 'fast', 'thinking', 'research', or 'auto'

        Returns:
            Model name string
        """
        mode_map = {
            "fast": ModelType.FAST,
            "thinking": ModelType.THINKING,
            "research": ModelType.RESEARCH,
        }
        model_type = mode_map.get(mode.lower(), ModelType.THINKING)
        return self._models.get(model_type, self._models[ModelType.THINKING])

    def set_model(self, model_type: ModelType, model_name: str) -> None:
        """
        Set model for a specific type.

        Args:
            model_type: Type of model to set
            model_name: Ollama model name
        """
        self._models[model_type] = model_name
        logger.info(f"[LLMService] Set {model_type.value} model to: {model_name}")

    def get_current_model(self) -> Optional[str]:
        """Get name of currently loaded model."""
        return self._current_model

    # ==================== Generation ====================

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        mode: str = "thinking",
        context_id: Optional[str] = None,
        **kwargs
    ) -> GenerationResult:
        """
        Generate response (non-streaming).

        Args:
            prompt: User prompt
            system_prompt: System instructions
            mode: Processing mode (fast/thinking/research)
            context_id: Context ID for history tracking
            **kwargs: Additional Ollama parameters

        Returns:
            GenerationResult with response

        Raises:
            LLMServiceError: If generation fails
        """
        if not self.is_ready():
            raise LLMServiceError("LLMService not connected")

        model = self.get_model_for_mode(mode)
        self._current_model = model
        self._status = LLMStatus.GENERATING
        self._is_generating = True

        start_time = time.time()

        try:
            # Get or create context
            context = self._get_context(context_id)
            if system_prompt:
                context.system_prompt = system_prompt

            # Build messages
            messages = context.get_messages()
            messages.append({"role": "user", "content": prompt})

            # Prepare request
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                **kwargs
            }

            logger.info(f"[LLMService] Generating with {model} (mode: {mode})")

            async with self._session.post(
                f"{self._base_url}/api/chat",
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise LLMServiceError(f"Generation failed: {error_text}")

                data = await resp.json()

            # Extract response
            content = data.get("message", {}).get("content", "")

            # Update context
            context.add_message("user", prompt)
            context.add_message("assistant", content)

            result = GenerationResult(
                content=content,
                model=model,
                total_duration_ms=data.get("total_duration", 0) / 1_000_000,
                eval_count=data.get("eval_count", 0),
                eval_duration_ms=data.get("eval_duration", 0) / 1_000_000,
                prompt_eval_count=data.get("prompt_eval_count", 0),
                done_reason=data.get("done_reason", ""),
            )

            logger.info(
                f"[LLMService] Generated {result.eval_count} tokens "
                f"in {result.total_duration_ms:.0f}ms "
                f"({result.tokens_per_second:.1f} t/s)"
            )

            return result

        finally:
            self._is_generating = False
            self._status = LLMStatus.CONNECTED

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        mode: str = "thinking",
        context_id: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Generate response with streaming.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            mode: Processing mode
            context_id: Context ID for history
            **kwargs: Additional Ollama parameters

        Yields:
            Text chunks as they're generated

        Raises:
            LLMServiceError: If generation fails
        """
        if not self.is_ready():
            raise LLMServiceError("LLMService not connected")

        model = self.get_model_for_mode(mode)
        self._current_model = model
        self._status = LLMStatus.GENERATING
        self._is_generating = True
        self._cancel_requested = False

        full_response = ""

        try:
            # Get or create context
            context = self._get_context(context_id)
            if system_prompt:
                context.system_prompt = system_prompt

            # Build messages
            messages = context.get_messages()
            messages.append({"role": "user", "content": prompt})

            # Prepare request
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                **kwargs
            }

            logger.info(f"[LLMService] Streaming with {model} (mode: {mode})")

            async with self._session.post(
                f"{self._base_url}/api/chat",
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise LLMServiceError(f"Generation failed: {error_text}")

                async for line in resp.content:
                    if self._cancel_requested:
                        logger.info("[LLMService] Generation cancelled")
                        break

                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                chunk = data["message"].get("content", "")
                                if chunk:
                                    full_response += chunk
                                    yield chunk

                            if data.get("done", False):
                                break

                        except json.JSONDecodeError:
                            continue

            # Update context with full response
            context.add_message("user", prompt)
            context.add_message("assistant", full_response)

            logger.info(f"[LLMService] Stream complete: {len(full_response)} chars")

        finally:
            self._is_generating = False
            self._status = LLMStatus.CONNECTED

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3",
        **kwargs
    ) -> LLMResponse:
        """
        Chat completion with message history.

        Args:
            messages: List of {"role": "user/assistant", "content": "..."}
            model: Model to use for chat
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse with assistant's reply
        """
        if not self.is_ready():
            raise LLMServiceError("LLMService not connected")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs
        }

        start_time = time.time()

        async with self._session.post(
            f"{self._base_url}/api/chat",
            json=payload
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise LLMServiceError(f"Chat failed: {error_text}")

            data = await resp.json()

        content = data.get("message", {}).get("content", "")
        generation_time = (time.time() - start_time) * 1000

        return LLMResponse(
            text=content,
            model=model,
            tokens_generated=data.get("eval_count", 0),
            generation_time_ms=generation_time,
            is_complete=True
        )

    async def execute(self, request_data: Dict[str, Any]) -> str:
        """
        Execute method for orchestrator compatibility.

        Args:
            request_data: Dict with generation parameters

        Returns:
            Generated text
        """
        result = await self.generate(
            prompt=request_data.get("prompt", ""),
            system_prompt=request_data.get("system_prompt", ""),
            mode=request_data.get("mode", "thinking"),
            context_id=request_data.get("context_id"),
        )
        return result.content

    # ==================== Context Management ====================

    def _get_context(self, context_id: Optional[str]) -> ChatContext:
        """Get or create context by ID."""
        if context_id is None:
            return self._default_context

        if context_id not in self._contexts:
            self._contexts[context_id] = ChatContext()

        return self._contexts[context_id]

    def create_context(
        self,
        context_id: str = None,
        system_prompt: str = "",
        max_history: int = 20
    ) -> ChatContext:
        """
        Create a new conversation context.

        Args:
            context_id: Unique context identifier
            system_prompt: System instructions
            max_history: Maximum messages to retain

        Returns:
            New ChatContext
        """
        context = ChatContext(
            system_prompt=system_prompt,
            max_history=max_history
        )
        if context_id:
            self._contexts[context_id] = context
        return context

    def get_context(self, context_id: str) -> Optional[ChatContext]:
        """Get existing context by ID."""
        return self._contexts.get(context_id)

    def clear_context(self, context_id: str) -> bool:
        """Clear a specific context."""
        if context_id in self._contexts:
            self._contexts[context_id].clear()
            return True
        return False

    def delete_context(self, context_id: str) -> bool:
        """Delete a context."""
        if context_id in self._contexts:
            del self._contexts[context_id]
            return True
        return False

    def list_contexts(self) -> List[str]:
        """List all context IDs."""
        return list(self._contexts.keys())

    # ==================== Utilities ====================

    def cancel_generation(self) -> bool:
        """Request cancellation of current generation."""
        if self._is_generating:
            self._cancel_requested = True
            logger.info("[LLMService] Cancellation requested")
            return True
        return False

    async def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific model.

        Args:
            model_name: Model to query

        Returns:
            Model information dict
        """
        if not self._session:
            return None

        try:
            async with self._session.post(
                f"{self._base_url}/api/show",
                json={"name": model_name}
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"[LLMService] Failed to get model info: {e}")
            return None

    async def embeddings(
        self,
        text: str,
        model: Optional[str] = None
    ) -> List[float]:
        """
        Generate embeddings for text.

        Args:
            text: Text to embed
            model: Model to use (defaults to current)

        Returns:
            Embedding vector
        """
        if not self._session:
            raise LLMServiceError("Not connected")

        model = model or self._current_model or self._models[ModelType.THINKING]

        try:
            async with self._session.post(
                f"{self._base_url}/api/embeddings",
                json={"model": model, "prompt": text}
            ) as resp:
                if resp.status != 200:
                    raise LLMServiceError(f"Embedding failed: {resp.status}")
                data = await resp.json()
                return data.get("embedding", [])
        except Exception as e:
            logger.error(f"[LLMService] Embedding error: {e}")
            raise

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Approximate token count (rough estimate: ~4 chars per token)
        """
        return len(text) // 4

    def to_dict(self) -> Dict[str, Any]:
        """Export service state as dictionary."""
        return {
            "status": self._status.name,
            "host": self.host,
            "port": self.port,
            "current_model": self._current_model,
            "is_generating": self._is_generating,
            "models": {k.value: v for k, v in self._models.items()},
            "active_contexts": len(self._contexts),
        }


# =============================================================================
# Factory Function
# =============================================================================

def create_llm_service(
    host: str = "localhost",
    port: int = 11434,
    timeout: float = 300.0,
    models: Optional[Dict[str, str]] = None
) -> LLMService:
    """
    Factory function to create LLMService.

    Args:
        host: Ollama hostname
        port: Ollama port
        timeout: Request timeout
        models: Model mapping (mode -> model_name)

    Returns:
        Configured LLMService instance
    """
    model_mapping = None
    if models:
        model_mapping = {
            ModelType.FAST: models.get("fast", LLMService.DEFAULT_MODELS[ModelType.FAST]),
            ModelType.THINKING: models.get("thinking", LLMService.DEFAULT_MODELS[ModelType.THINKING]),
            ModelType.RESEARCH: models.get("research", LLMService.DEFAULT_MODELS[ModelType.RESEARCH]),
        }

    return LLMService(
        host=host,
        port=port,
        timeout=timeout,
        models=model_mapping
    )
