import whisper
import logging
import asyncio
import numpy as np
import re
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

from config import WHISPER_MODEL, WHISPER_LANGUAGE

_model = None
# Ensure thread execution so the main async event loop doesn't block during heavy transcription
_executor = ThreadPoolExecutor(max_workers=2)

def load_model():
    """Loads the Whisper model into RAM."""
    global _model
    if _model is None:
        logger.info(f"Loading Whisper model '{WHISPER_MODEL}'...")
        # device="cuda" can be added here if available, but omitting it handles both CPU/GPU gracefully 
        _model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper model loaded successfully.")

def transcribe_audio_sync(audio_input) -> str:
    """Sync function to run transcription on a numpy array or file path."""
    if _model is None:
        load_model()
    
    try:
        # Forced Arabic transcription to prevent auto-detect failures
        # initial_prompt guides Whisper to expect Gulf Arabic and the wake word
        result = _model.transcribe(
            audio_input, 
            language=WHISPER_LANGUAGE, 
            fp16=False,
            initial_prompt="هذا تسجيل صوتي عفوي باللهجة السعودية الخليجية. يا توني، اسمعني."
        )
        text = result.get("text", "").strip()
        logger.debug(f"Transcribed Text: {text}")
        return text
    except Exception as e:
        logger.error(f"Whisper Transcription error: {e}")
        return ""

async def transcribe_audio(audio_input) -> str:
    """Async wrapper around the transcription to prevent blocking the bot."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, transcribe_audio_sync, audio_input)

def contains_wake_word(text: str) -> bool:
    """Checks if the transcribed text contains the wake word using fuzzy matching."""
    clean_text = ''.join(char for char in text.lower() if char.isalnum() or char.isspace())
    
    # Regex for flexible matching:
    # Matches "يا توني", "ياتوني", "توني", "تونى", "يا... توني", "tony"
    pattern = r"(يا\s*تون[يى]|تون[يى]|tony)"
    
    if re.search(pattern, clean_text):
        return True
        
    return False
