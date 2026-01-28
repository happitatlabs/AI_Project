# Troubleshooting Solutions & Technical Know-How

Created: 2026-01-22

Purpose: Document solutions to common issues to avoid repeating the same struggles after reinstallation or disconnection.

---

## 1. No Microphone Environment

### Problem
VTuber service expects microphone input but system has no microphone connected.
- VAD (Voice Activity Detection) blocks without audio input
- Frontend waits indefinitely for mic-audio-end signal
- Cannot trigger conversation without voice input

### Solution: Bypass VAD for Text-Only Input

**Key Insight:** When no microphone is available, you must bypass VAD and use text input directly.

#### Configuration (conf.yaml)
```yaml
vad_config:
  vad_model: null  # Disable VAD completely when no mic
```

#### Code Flow for Text Input
```
text-input message → websocket_handler.py → _handle_conversation_trigger
                                          → process_single_conversation (bypasses ASR)
```

**File:** `Open-LLM-VTuber/src/open_llm_vtuber/websocket_handler.py:90`
```python
"text-input": self._handle_conversation_trigger,
```

### Browser Security: Click Requirement

**Problem:** Browser security policies block audio autoplay without user interaction.

**Solution:** Frontend must have user click/interaction before:
1. Playing TTS audio
2. Accessing microphone (if available)
3. Starting WebSocket audio streams

**Implementation Notes:**
- Add a "Start" or "Connect" button that user must click
- Audio context must be created/resumed after user gesture
- First audio play must be triggered by user action

```javascript
// Example: Audio context requires user interaction
document.getElementById('startBtn').addEventListener('click', () => {
    audioContext = new AudioContext();
    audioContext.resume();  // Now audio can play
});
```

---

## 2. 404 Error Solutions

### Problem: Folders/Sessions API Returns 404

**Symptom:** `/folders` or `/chat/sessions` returns 404 for new users

**Root Cause:** User has no folders created yet in database

**Solution:** Auto-create default folders on first access

**File:** `mellow_link/main.py` - `/folders` endpoint

```python
# Auto-create folders if none exist (404 protection)
folders = ensure_user_has_folders(db, user.id, role=user.role)
```

**Key Function:** `mellow_link/infra/database.py`
```python
def ensure_user_has_folders(db, user_id, role):
    """Creates default folders if user has none"""
    # Check existing
    # If empty, create defaults
    # Return folder list
```

### Problem: Static Files 404

**Symptom:** `/static/index.html` or assets return 404

**Root Cause:** Static directory path resolution differs when running from different locations

**Solution:** Use environment variable for project root

**File:** `mellow_link/main.py:423-437`
```python
project_root = os.environ.get("MELLOW_LINK_PROJECT_ROOT") or os.environ.get("PROJECT_ROOT")

if project_root:
    static_dir = os.path.join(project_root, "mellow_link", "static")
else:
    # Fallback to current file location
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
```

**Launcher must set:**
```python
os.environ["MELLOW_LINK_PROJECT_ROOT"] = "D:\\AI_Project"
```

---

## 3. Broadcast / Relay Solutions

### Problem: LLM Response Not Reaching Avatar

**Symptom:** Chat works in Mellow-Link UI but avatar doesn't speak

**Root Cause:** VTuberRelayService not connected or message format incorrect

### Solution: Correct WebSocket Message Format

**Critical:** Open-LLM-VTuber expects `"speak"` type for direct TTS (bypassing its internal LLM)

**File:** `mellow_link/services/vtuber_relay.py:514-522`
```python
# CORRECT format - "speak" type bypasses LLM, goes straight to TTS
payload = {
    "type": "speak",      # <-- THIS IS CRITICAL
    "text": sentence.strip(),
    "emotion": message.emotion,
    "priority": message.priority,
    "metadata": message.metadata
}
```

**Handler in VTuber:** `conversation_handler.py:36-58`
```python
# [CRITICAL] Handle 'speak' type - Bypass LLM, go straight to TTS
if msg_type == "speak":
    text = data.get("text", "")
    # ... goes directly to process_speak_direct()
    # Does NOT go through Ollama again
```

### Problem: WebSocket Message Too Big

**Symptom:** Error "message too big" when sending long responses

**Solution:** Split text into sentences before sending

**File:** `vtuber_relay.py:360-477`
```python
def _split_into_sentences(self, text: str, max_length: int = 80) -> List[str]:
    """Split by sentence-ending punctuation (., !, ?)"""

def _split_long_sentence(self, sentence: str, max_length: int = 80) -> List[str]:
    """Split by commas, then by spaces if still too long"""
```

**Send with delay between sentences:**
```python
# Max 150 chars per message
# Max 5 sentences per response
# 2 second delay between sentences
if i < len(sentences) - 1:
    await asyncio.sleep(2.0)
```

### Problem: Relay Connection Drops

**Symptom:** Avatar works initially but stops responding

**Solution:** Auto-reconnection loop with heartbeat

**File:** `vtuber_relay.py:315-335`
```python
async def _reconnect_loop(self) -> None:
    """Background task for auto-reconnection."""
    while self._is_running:
        if self._status != VTuberConnectionStatus.CONNECTED:
            await self.connect()
        await asyncio.sleep(self.reconnect_interval)  # 5 seconds

async def _heartbeat_loop(self) -> None:
    """Background task for heartbeat pings."""
    while self._is_running:
        if self.is_connected and self._websocket:
            await self._websocket.ping()
        await asyncio.sleep(self.heartbeat_interval)  # 30 seconds
```

---

## 4. Text Cleaning for TTS

### Problem: TTS Reads Unwanted Characters

**Symptom:** Avatar says "[brackets]", "asterisks", or weird symbols

**Solution:** Clean text before sending to TTS

**File:** `mellow_link/main.py:1670-1710`
```python
import re

# Remove brackets and contents: [text] -> empty
cleaned_response = re.sub(r'\[.*?\]', '', cleaned_response)

# Remove markdown emphasis: **text** -> text
cleaned_response = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_response)
cleaned_response = re.sub(r'\*([^*]+)\*', r'\1', cleaned_response)

# Remove mechanical prefixes
prefix_patterns = [
    r'^(답변은|답변|AI|The answer is)[:：\s]+',
]
for pattern in prefix_patterns:
    cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.IGNORECASE)
```

---

## 5. Session Context Loss

### Problem: AI Forgets Previous Conversation When Session Reopens

**Symptom:** Clicking on old session shows messages but AI has no memory of them

**Root Cause:** LLM context not restored from database when session is loaded

**Solution:** Restore conversation history to LLM context on session load

**File:** `mellow_link/main.py:1506-1537`
```python
# [CRITICAL FIX] Load conversation history from DB when reopening session
if session:
    previous_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp.asc()).all()

    if previous_messages and llm_service:
        context = llm_service._get_context(context_id_str)
        context.messages.clear()

        # Restore all previous messages to LLM context
        for msg in previous_messages:
            context.add_message(msg.role, msg.content)
```

---

## Quick Checklist: After Reinstallation

1. [ ] Set `MELLOW_LINK_PROJECT_ROOT` environment variable
2. [ ] Verify `conf.yaml` VAD setting matches hardware (mic/no-mic)
3. [ ] Check WebSocket URL ends with `/client-ws`
4. [ ] Verify Ollama is running on port 11434
5. [ ] Check Open-LLM-VTuber is running on port 12393
6. [ ] Test with browser DevTools open to catch 404s
7. [ ] Click "Start" button before expecting audio (browser security)
