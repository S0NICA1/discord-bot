import whisper
import logging
import asyncio
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

def transcribe_audio_sync(file_path: str) -> str:
    """Sync function to run transcription."""
    if _model is None:
        load_model()
    
    try:
        # Forced Arabic transcription to prevent auto-detect failures
        result = _model.transcribe(file_path, language=WHISPER_LANGUAGE, fp16=False)
        text = result.get("text", "").strip()
        logger.debug(f"Transcribed Text: {text}")
        return text
    except Exception as e:
        logger.error(f"Whisper Transcription error: {e}")
        return ""

async def transcribe_audio(file_path: str) -> str:
    """Async wrapper around the transcription to prevent blocking the bot."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, transcribe_audio_sync, file_path)

def contains_wake_word(text: str) -> bool:
    """Checks if the transcribed text contains the wake word to activate Tony."""
    # Remove punctuation for easier matching
    clean_text = ''.join(char for char in text.lower() if char.isalnum() or char.isspace())
    
    wake_words = ["يا توني", "tony", "توني"]
    for word in wake_words:
        # Check if the text starts with or strongly features the wake word
        # (Whisper might precede it with a small artifact)
        if word in clean_text:
            # We want to respond only if they called him
            return True
            
    return False
