"""
VTuber Relay Service for Mellow-Link

Handles WebSocket communication with the Open-LLM-VTuber avatar service.
Relays conversation messages to the VTuber for speech synthesis and animation.
"""

import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class VTuberConnectionStatus(Enum):
    """Connection status for VTuber service."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class VTuberMessage:
    """Message to send to VTuber avatar."""
    text: str
    emotion: str = "neutral"  # neutral, happy, sad, surprised, angry
    priority: int = 1  # 1=normal, 2=high, 3=urgent
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VTuberStatus:
    """Status response from VTuber service."""
    connected: bool = False
    speaking: bool = False
    current_emotion: str = "neutral"
    queue_size: int = 0
    last_heartbeat: Optional[datetime] = None


class VTuberRelayService:
    """
    Service for relaying messages to VTuber avatar via WebSocket.

    The VTuber service runs on port 12393 and accepts WebSocket connections
    for text-to-speech and animation control.
    """

    def __init__(
        self,
        ws_url: str = "ws://localhost:12393/client-ws",
        reconnect_interval: float = 5.0,
        heartbeat_interval: float = 30.0
    ):
        """
        Initialize VTuber relay service.

        Args:
            ws_url: WebSocket URL of the VTuber service
            reconnect_interval: Seconds between reconnection attempts
            heartbeat_interval: Seconds between heartbeat pings
        """
        self.ws_url = ws_url
        self.reconnect_interval = reconnect_interval
        self.heartbeat_interval = heartbeat_interval

        self._websocket = None
        self._status = VTuberConnectionStatus.DISCONNECTED
        self._is_running = False
        self._message_queue: asyncio.Queue = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._send_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_status_change: Optional[Callable] = None
        self._on_message_sent: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # Status tracking
        self._last_heartbeat: Optional[datetime] = None
        self._vtuber_status = VTuberStatus()

        logger.info(f"[VTuberRelay] Initialized with URL: {ws_url}")

    @property
    def status(self) -> VTuberConnectionStatus:
        """Get current connection status."""
        return self._status

    @property
    def is_connected(self) -> bool:
        """Check if connected to VTuber service."""
        return self._status == VTuberConnectionStatus.CONNECTED

    def get_status(self) -> Dict[str, Any]:
        """Get detailed status information."""
        return {
            "connected": self.is_connected,
            "status": self._status.value,
            "ws_url": self.ws_url,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "vtuber": {
                "speaking": self._vtuber_status.speaking,
                "emotion": self._vtuber_status.current_emotion,
                "queue_size": self._vtuber_status.queue_size
            }
        }

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to VTuber service.

        Returns:
            True if connection successful, False otherwise.
        """
        if self._status == VTuberConnectionStatus.CONNECTED:
            logger.debug("[VTuberRelay] Already connected")
            return True

        self._status = VTuberConnectionStatus.CONNECTING
        logger.info(f"[VTuberRelay] ========================================")
        logger.info(f"[VTuberRelay] Attempting connection to: {self.ws_url}")
        logger.info(f"[VTuberRelay] ========================================")

        try:
            import websockets
            self._websocket = await asyncio.wait_for(
                websockets.connect(self.ws_url),
                timeout=10.0
            )
            self._status = VTuberConnectionStatus.CONNECTED
            self._last_heartbeat = datetime.now()

            logger.info("[VTuberRelay] ✅ CONNECTED SUCCESSFULLY!")
            logger.info(f"[VTuberRelay] WebSocket state: {self._websocket.state if hasattr(self._websocket, 'state') else 'active'}")

            if self._on_status_change:
                await self._on_status_change(self._status)

            return True

        except ImportError:
            logger.error("[VTuberRelay] ❌ websockets library not installed!")
            logger.error("[VTuberRelay] Run: pip install websockets")
            self._status = VTuberConnectionStatus.ERROR
            return False
        except asyncio.TimeoutError:
            logger.warning("[VTuberRelay] ❌ Connection timeout (10s)")
            logger.warning("[VTuberRelay] Is Open-LLM-VTuber running on port 12393?")
            self._status = VTuberConnectionStatus.DISCONNECTED
            return False
        except Exception as e:
            logger.debug(f"[VTuberRelay] 💤 VTuber 서버 대기 중... (연결 시도 중): {e}")
            logger.debug(f"[VTuberRelay] Target: {self.ws_url}")
            self._status = VTuberConnectionStatus.ERROR
            #if self._on_error:
            #   await self._on_error(e)
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._is_running = False

        # Cancel background tasks
        for task in [self._reconnect_task, self._heartbeat_task, self._send_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.debug(f"[VTuberRelay] Error closing websocket: {e}")

        self._websocket = None
        self._status = VTuberConnectionStatus.DISCONNECTED
        logger.info("[VTuberRelay] Disconnected")

    async def start(self) -> None:
        """Start the relay service with auto-reconnection."""
        if self._is_running:
            return

        self._is_running = True
        self._message_queue = asyncio.Queue()

        # Start background tasks
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._send_task = asyncio.create_task(self._send_loop())

        logger.info("[VTuberRelay] Service started")

    async def stop(self) -> None:
        """Stop the relay service."""
        await self.disconnect()
        logger.info("[VTuberRelay] Service stopped")

    async def send_message(self, message: VTuberMessage) -> bool:
        """
        Queue a message to be sent to VTuber.

        Args:
            message: VTuberMessage to send

        Returns:
            True if queued successfully
        """
        if not self._message_queue:
            logger.warning("[VTuberRelay] Service not started, cannot queue message")
            return False

        await self._message_queue.put(message)
        logger.debug(f"[VTuberRelay] Message queued: {message.text[:50]}...")
        return True

    async def send_text(
        self,
        text: str,
        emotion: str = "neutral",
        priority: int = 1
    ) -> bool:
        """
        Convenience method to send text to VTuber.

        Args:
            text: Text for VTuber to speak
            emotion: Emotion state (neutral, happy, sad, surprised, angry)
            priority: Message priority (1=normal, 2=high, 3=urgent)

        Returns:
            True if queued successfully
        """
        message = VTuberMessage(text=text, emotion=emotion, priority=priority)
        return await self.send_message(message)

    async def relay_llm_response(
        self,
        response_text: str,
        session_id: Optional[int] = None,
        folder_name: Optional[str] = None
    ) -> bool:
        """
        Relay an LLM response to VTuber for speech.

        This is the main method for integrating with the chat system.
        It automatically detects emotion from text and relays to VTuber.

        Args:
            response_text: The LLM response text
            session_id: Optional session ID for context
            folder_name: Optional folder name (e.g., "Secretary")

        Returns:
            True if relayed successfully
        """
        if not self.is_connected:
            logger.debug("[VTuberRelay] Not connected, skipping relay")
            return False

        # Detect emotion from text (simple heuristic)
        emotion = self._detect_emotion(response_text)

        # Higher priority for Secretary folder
        priority = 2 if folder_name and "Secretary" in folder_name else 1

        message = VTuberMessage(
            text=response_text,
            emotion=emotion,
            priority=priority,
            metadata={
                "session_id": session_id,
                "folder_name": folder_name,
                "source": "llm_response"
            }
        )

        return await self.send_message(message)

    def _detect_emotion(self, text: str) -> str:
        """Simple emotion detection from text."""
        text_lower = text.lower()

        # Happy indicators
        happy_words = ["기쁘", "좋아", "축하", "행복", "웃", "ㅎㅎ", "^^", ":)", "happy", "great", "wonderful"]
        if any(word in text_lower for word in happy_words):
            return "happy"

        # Sad indicators
        sad_words = ["슬프", "안타깝", "아쉽", "눈물", "ㅠㅠ", ":(", "sad", "sorry", "unfortunately"]
        if any(word in text_lower for word in sad_words):
            return "sad"

        # Surprised indicators
        surprised_words = ["놀랍", "대박", "와!", "오!", "!!", "wow", "amazing", "incredible"]
        if any(word in text_lower for word in surprised_words):
            return "surprised"

        return "neutral"

    async def _reconnect_loop(self) -> None:
        """Background task for auto-reconnection."""
        while self._is_running:
            if self._status != VTuberConnectionStatus.CONNECTED:
                await self.connect()

            await asyncio.sleep(self.reconnect_interval)

    async def _heartbeat_loop(self) -> None:
        """Background task for heartbeat pings."""
        while self._is_running:
            if self.is_connected and self._websocket:
                try:
                    # Send ping
                    await self._websocket.ping()
                    self._last_heartbeat = datetime.now()
                except Exception as e:
                    logger.warning(f"[VTuberRelay] Heartbeat failed: {e}")
                    self._status = VTuberConnectionStatus.DISCONNECTED

            await asyncio.sleep(self.heartbeat_interval)

    async def _send_loop(self) -> None:
        """Background task for sending queued messages."""
        while self._is_running:
            try:
                # Get message from queue with timeout
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )

                if self.is_connected and self._websocket:
                    await self._send_to_vtuber(message)
                else:
                    # Re-queue if not connected
                    await self._message_queue.put(message)
                    await asyncio.sleep(1.0)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[VTuberRelay] Send loop error: {e}")
                await asyncio.sleep(2.0)

    def _split_into_sentences(self, text: str, max_length: int = 80) -> List[str]:
        """
        Split text into sentences based on sentence-ending punctuation.
        
        Args:
            text: Text to split
            max_length: Maximum length for a sentence before additional splitting
            
        Returns:
            List of sentence strings
        """
        if not text or not text.strip():
            return []
        
        # Normalize line breaks to \n
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Split by sentence-ending punctuation (., !, ?) and line breaks
        # Pattern: matches sentence-ending punctuation followed by optional whitespace, or line breaks
        sentence_pattern = r'([.!?]+\s*|\n+)'
        parts = re.split(sentence_pattern, text)
        
        sentences = []
        current_sentence = ""
        
        for part in parts:
            if not part:
                continue
            
            current_sentence += part
            
            # Check if this part is sentence-ending punctuation or contains line breaks
            if re.match(r'^[.!?]+\s*$', part) or '\n' in part:
                sentence = current_sentence.strip()
                if sentence:
                    # Remove line breaks and extra whitespace
                    sentence = re.sub(r'\n+', ' ', sentence)
                    sentence = re.sub(r'\s+', ' ', sentence).strip()
                    
                    if sentence:
                        # If sentence is too long, split it further
                        if len(sentence) > max_length:
                            sentences.extend(self._split_long_sentence(sentence, max_length))
                        else:
                            sentences.append(sentence)
                current_sentence = ""
        
        # Handle remaining text (if any)
        remaining = current_sentence.strip()
        if remaining:
            # Clean up remaining text
            remaining = re.sub(r'\n+', ' ', remaining)
            remaining = re.sub(r'\s+', ' ', remaining).strip()
            if remaining:
                if len(remaining) > max_length:
                    sentences.extend(self._split_long_sentence(remaining, max_length))
                else:
                    sentences.append(remaining)
        
        # Filter out empty sentences
        return [s for s in sentences if s.strip()]
    
    def _split_long_sentence(self, sentence: str, max_length: int = 80) -> List[str]:
        """
        Split a long sentence by commas or spaces.
        
        Args:
            sentence: Long sentence to split
            max_length: Maximum length for each chunk
            
        Returns:
            List of sentence chunks
        """
        if len(sentence) <= max_length:
            return [sentence]
        
        chunks = []
        current_chunk = ""
        
        # First try splitting by comma
        comma_parts = sentence.split(',')
        
        for part in comma_parts:
            part = part.strip()
            if not part:
                continue
            
            # If adding this part would exceed max_length, finalize current chunk
            if current_chunk and len(current_chunk + ', ' + part) > max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = part
            else:
                if current_chunk:
                    current_chunk += ', ' + part
                else:
                    current_chunk = part
        
        # If we still have a chunk that's too long, split by spaces
        if current_chunk and len(current_chunk) > max_length:
            words = current_chunk.split()
            temp_chunk = ""
            for word in words:
                if temp_chunk and len(temp_chunk + ' ' + word) > max_length:
                    if temp_chunk:
                        chunks.append(temp_chunk)
                    temp_chunk = word
                else:
                    if temp_chunk:
                        temp_chunk += ' ' + word
                    else:
                        temp_chunk = word
            if temp_chunk:
                chunks.append(temp_chunk)
        elif current_chunk:
            chunks.append(current_chunk)
        
        return chunks if chunks else [sentence]

    async def _send_to_vtuber(self, message: VTuberMessage) -> bool:
        """
        Send a message to VTuber via WebSocket.
        Splits long text to avoid WebSocket frame size limits.
        """
        try:
            text = message.text.strip()
            if not text:
                return False

            # Split into chunks of max 150 characters to avoid "message too big" error
            max_chunk_size = 150
            if len(text) <= max_chunk_size:
                sentences = [text]
            else:
                # Split by sentences first, then by size
                sentences = self._split_into_sentences(text, max_length=max_chunk_size)
            
            if not sentences:
                logger.warning("[VTuberRelay] No sentences to send after splitting")
                return False
            
            # Limit to max 5 sentences to avoid overwhelming the server
            if len(sentences) > 5:
                logger.warning(f"[VTuberRelay] Too many sentences ({len(sentences)}), truncating to 5")
                sentences = sentences[:5]

            logger.info(f"[VTuberRelay] Sending {len(sentences)} chunks (total length: {len(message.text)})")
            
            # Send each sentence sequentially
            for i, sentence in enumerate(sentences):
                if not self.is_connected or not self._websocket:
                    logger.warning(f"[VTuberRelay] Connection lost while sending sentence {i+1}/{len(sentences)}")
                    return False
                
                # Prepare JSON payload in speak format (Direct TTS without LLM)
                # Include emotion, priority, and metadata for avatar service compatibility
                payload = {
                    "type": "speak",
                    "text": sentence.strip(),
                    "emotion": message.emotion,  # Preserve emotion detection
                    "priority": message.priority,  # Preserve priority level
                    "metadata": message.metadata  # Preserve session/folder context
                }
                
                try:
                    await self._websocket.send(json.dumps(payload))
                    logger.debug(f"[VTuberRelay] Sent sentence {i+1}/{len(sentences)}: {sentence[:50]}...")
                    
                    # Wait between sentences to prevent server overload
                    if i < len(sentences) - 1:
                        await asyncio.sleep(2.0)  # 2초 대기
                        
                except Exception as e:
                    logger.error(f"[VTuberRelay] Error sending sentence {i+1}: {e}")
                    self._status = VTuberConnectionStatus.DISCONNECTED
                    return False
            
            # Callback after all sentences are sent
            if self._on_message_sent:
                await self._on_message_sent(message)
            
            logger.debug(f"[VTuberRelay] Successfully sent all {len(sentences)} sentences")
            return True

        except Exception as e:
            logger.error(f"[VTuberRelay] Send error: {e}")
            self._status = VTuberConnectionStatus.DISCONNECTED
            return False

    # Callback setters
    def on_status_change(self, callback: Callable) -> None:
        """Register callback for status changes."""
        self._on_status_change = callback

    def on_message_sent(self, callback: Callable) -> None:
        """Register callback for successful message sends."""
        self._on_message_sent = callback

    def on_error(self, callback: Callable) -> None:
        """Register callback for errors."""
        self._on_error = callback


# =============================================================================
# Factory Function
# =============================================================================

def create_vtuber_relay(
    ws_url: str = "ws://localhost:12393/client-ws",
    reconnect_interval: float = 5.0
) -> VTuberRelayService:
    """
    Factory function to create VTuber relay service.

    Args:
        ws_url: WebSocket URL (default: ws://localhost:12393/client-ws)
        reconnect_interval: Reconnection interval in seconds

    Returns:
        VTuberRelayService instance
    """
    return VTuberRelayService(
        ws_url=ws_url,
        reconnect_interval=reconnect_interval
    )


# =============================================================================
# Global Instance (Singleton pattern)
# =============================================================================

_vtuber_relay: Optional[VTuberRelayService] = None


def get_vtuber_relay() -> Optional[VTuberRelayService]:
    """Get the global VTuber relay instance."""
    return _vtuber_relay


def set_vtuber_relay(relay: VTuberRelayService) -> None:
    """Set the global VTuber relay instance."""
    global _vtuber_relay
    _vtuber_relay = relay
