import logging
import asyncio
import io
import os
import tempfile
import discord
from gtts import gTTS
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL

logger = logging.getLogger(__name__)

# Initialize ElevenLabs Client
try:
    from elevenlabs.client import ElevenLabs
    el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize ElevenLabs Client: {e}")
    el_client = None

# A background queue so Tony doesn't talk over himself
_speech_queues = {}

async def speak_text_to_discord(guild_id: int, text: str, voice_client: discord.VoiceClient):
    """Adds Tony's response to a guild queue so he doesn't speak over himself."""
    if guild_id not in _speech_queues:
        _speech_queues[guild_id] = asyncio.Queue()
        # Start the background worker for this guild
        asyncio.create_task(_guild_audio_worker(guild_id, voice_client))
        
    await _speech_queues[guild_id].put(text)

async def _guild_audio_worker(guild_id: int, voice_client: discord.VoiceClient):
    """Processes audio sequentially for a guild."""
    while True:
        try:
            text = await _speech_queues[guild_id].get()
            
            # Wait for bot to finish playing if it currently is
            while voice_client.is_playing():
                await asyncio.sleep(0.5)
                
            file_path = await synthesize_audio(text)
            if not file_path:
                continue
                
            audio_source = discord.FFmpegPCMAudio(file_path)
            
            def after_play(error):
                if error:
                    logger.error(f"Error playing audio: {error}")
                # Clean up the temp file after playing
                try:
                    os.remove(file_path)
                except Exception as e:
                    pass
                _speech_queues[guild_id].task_done()
                
            voice_client.play(audio_source, after=after_play)
            
        except discord.ClientException as e:
            logger.error(f"Discord Audio client error: {e}")
            _speech_queues[guild_id].task_done()
        except Exception as e:
            logger.error(f"Audio worker error: {e}")
            await asyncio.sleep(1)

async def synthesize_audio(text: str) -> str:
    """Uses ElevenLabs (or gTTS fallback) to generate an audio file. Returns path to the file."""
    
    # Run API calls in thread to not block AsyncIO
    loop = asyncio.get_running_loop()
    
    if el_client and ELEVENLABS_VOICE_ID:
        try:
            # We must use a tmp file as FFmpegPCMAudio reads directly from files best in Pycord
            def _el_generate():
                return el_client.generate(
                    text=text,
                    voice=ELEVENLABS_VOICE_ID,
                    model=ELEVENLABS_MODEL
                )
            
            audio_generator = await loop.run_in_executor(None, _el_generate)
            
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            for chunk in audio_generator:
                if chunk:
                    tmp_file.write(chunk)
            tmp_file.close()
            return tmp_file.name
            
        except Exception as e:
            logger.error(f"ElevenLabs TTS failed, falling back to gTTS: {e}")
            
    # Fallback to gTTS
    try:
        def _gtts_generate():
            tts = gTTS(text=text, lang='ar')
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts.save(tmp_file.name)
            return tmp_file.name
            
        return await loop.run_in_executor(None, _gtts_generate)
    except Exception as e:
        logger.error(f"gTTS fallback failed: {e}")
        return None
