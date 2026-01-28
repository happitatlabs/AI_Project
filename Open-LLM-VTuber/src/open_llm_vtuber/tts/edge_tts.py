import sys
import os
import asyncio
from typing import Optional

import edge_tts
from loguru import logger
from .tts_interface import TTSInterface

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)


# Check out doc at https://github.com/rany2/edge-tts
# Use `edge-tts --list-voices` to list all available voices


async def _save_audio_async(text: str, voice: str, rate: str, pitch: str, file_name: str) -> bool:
    """Async helper to generate and save audio using edge_tts stream."""
    try:
        logger.debug(f"[EdgeTTS Async] Starting audio generation for: {text[:30]}...")
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)

        bytes_written = 0
        with open(file_name, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                    bytes_written += len(chunk["data"])

        logger.debug(f"[EdgeTTS Async] Wrote {bytes_written} bytes to {file_name}")
        return bytes_written > 0
    except Exception as e:
        logger.error(f"[EdgeTTS Async] Error in async generation: {e}")
        logger.exception("[EdgeTTS Async] Full traceback:")
        return False


class TTSEngine(TTSInterface):
    def __init__(self, voice="ko-KR-InJoonNeural", rate: Optional[str] = None, pitch: Optional[str] = None, volume: Optional[str] = None):
        self.voice = voice
        self.rate = rate or "-10% \sim -15%"
        self.pitch = pitch or "-2Hz \sim +3Hz"
        self.volume = volume or "+10%"

        self.temp_audio_file = "temp"
        self.file_extension = "mp3"
        self.new_audio_dir = "cache"

        if not os.path.exists(self.new_audio_dir):
            os.makedirs(self.new_audio_dir)

        logger.info(f"[EdgeTTS] Initialized with voice={voice}, rate={self.rate}, pitch={self.pitch}")

    def generate_audio(self, text, file_name_no_ext=None):
        """
        Generate speech audio file using TTS.
        text: str
            the text to speak
        file_name_no_ext: str
            name of the file without extension


        Returns:
        str: the path to the generated audio file

        """
        if not text or not text.strip():
            logger.warning("[EdgeTTS] Empty text provided, skipping audio generation")
            return None

        file_name = self.generate_cache_file_name(file_name_no_ext, self.file_extension)

        try:
            logger.debug(f"[EdgeTTS] Generating audio for text (length={len(text)}): {text[:50]}...")
            logger.debug(f"[EdgeTTS] Using voice={self.voice}, rate={self.rate}, pitch={self.pitch}")

            # Run async function - handle both cases
            try:
                # Check if we're in an event loop
                loop = asyncio.get_running_loop()
                logger.debug("[EdgeTTS] Running inside event loop, using ThreadPoolExecutor")
                # Create a new loop in a separate thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(_save_audio_async(text, self.voice, self.rate, self.pitch, file_name))
                    )
                    result = future.result(timeout=30)
                    logger.debug(f"[EdgeTTS] ThreadPoolExecutor result: {result}")
            except RuntimeError as e:
                # No event loop running, safe to use asyncio.run()
                logger.debug(f"[EdgeTTS] No event loop running ({e}), using asyncio.run()")
                asyncio.run(_save_audio_async(text, self.voice, self.rate, self.pitch, file_name))
            
            # Verify file was created successfully
            if os.path.exists(file_name):
                file_size = os.path.getsize(file_name)
                if file_size > 0:
                    logger.debug(f"[EdgeTTS] Successfully generated audio: {file_name} ({file_size} bytes)")
                else:
                    logger.error(f"[EdgeTTS] Generated file is empty: {file_name}")
                    return None
            else:
                logger.error(f"[EdgeTTS] Generated file does not exist: {file_name}")
                return None
                
        except Exception as e:
            logger.critical(f"[EdgeTTS] Error: edge-tts unable to generate audio: {e}")
            logger.critical("[EdgeTTS] Possible causes:")
            logger.critical("  1. edge-tts is blocked in your region")
            logger.critical("  2. Network connectivity issues")
            logger.critical("  3. Invalid voice name or SSML format")
            logger.exception("[EdgeTTS] Full error traceback:")
            return None

        return file_name


# en-US-AvaMultilingualNeural
# en-US-EmmaMultilingualNeural
# en-US-JennyNeural
