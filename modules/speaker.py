import logging
import asyncio
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
    logger.info("ElevenLabs client initialized OK")
except Exception as e:
    logger.error(f"Failed to initialize ElevenLabs Client: {e}")
    el_client = None

# Per-guild queues — reset on each new session
_speech_queues: dict[int, asyncio.Queue] = {}
_worker_tasks: dict[int, asyncio.Task] = {}


def reset_guild_audio(guild_id: int):
    """Call this before each /join to clear stale queue + worker."""
    if guild_id in _worker_tasks:
        try:
            _worker_tasks[guild_id].cancel()
        except:
            pass
        del _worker_tasks[guild_id]
    if guild_id in _speech_queues:
        del _speech_queues[guild_id]


async def speak_text_to_discord(guild_id: int, text: str, voice_client: discord.VoiceClient):
    """Adds text to the audio queue for the guild. Creates worker if needed."""
    if not text or not text.strip():
        return

    logger.info(f"[Speaker] Queueing text for guild {guild_id}: {text[:60]}...")

    # Re-create queue/worker if missing or worker died
    if guild_id not in _speech_queues or guild_id not in _worker_tasks or _worker_tasks[guild_id].done():
        _speech_queues[guild_id] = asyncio.Queue(maxsize=5)
        _worker_tasks[guild_id] = asyncio.create_task(
            _guild_audio_worker(guild_id, voice_client)
        )
        logger.info(f"[Speaker] Started new audio worker for guild {guild_id}")

    if _speech_queues[guild_id].full():
        logger.warning(f"[Speaker] Queue full for guild {guild_id}, dropping message.")
        return

    await _speech_queues[guild_id].put((text, voice_client))


async def _guild_audio_worker(guild_id: int, initial_vc: discord.VoiceClient):
    """Background worker that processes TTS audio sequentially for a guild."""
    logger.info(f"[Speaker Worker] Started for guild {guild_id}")
    while True:
        try:
            text, voice_client = await asyncio.wait_for(
                _speech_queues[guild_id].get(), timeout=300
            )

            if not voice_client or not voice_client.is_connected():
                logger.warning(f"[Speaker Worker] Voice client disconnected, skipping.")
                _speech_queues[guild_id].task_done()
                continue

            # Wait for any current playback to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.3)

            logger.info(f"[Speaker Worker] Synthesizing: {text[:60]}...")
            file_path = await synthesize_audio(text)
            if not file_path:
                logger.error("[Speaker Worker] synthesize_audio returned None!")
                _speech_queues[guild_id].task_done()
                continue

            logger.info(f"[Speaker Worker] Playing audio file: {file_path}")

            done_event = asyncio.Event()

            def after_play(error):
                if error:
                    logger.error(f"[Speaker Worker] Error during playback: {error}")
                try:
                    os.remove(file_path)
                except:
                    pass
                _speech_queues[guild_id].task_done()
                voice_client.loop.call_soon_threadsafe(done_event.set)

            voice_client.play(
                discord.FFmpegPCMAudio(file_path),
                after=after_play
            )

            # Wait for playback to finish
            try:
                await asyncio.wait_for(done_event.wait(), timeout=120)
                logger.info("[Speaker Worker] Playback complete.")
            except asyncio.TimeoutError:
                logger.warning("[Speaker Worker] Playback timed out.")

        except asyncio.TimeoutError:
            logger.info(f"[Speaker Worker] No audio for 5 minutes, exiting guild {guild_id} worker.")
            break
        except asyncio.CancelledError:
            logger.info(f"[Speaker Worker] Worker cancelled for guild {guild_id}")
            break
        except Exception as e:
            logger.error(f"[Speaker Worker] Unexpected error: {e}", exc_info=True)
            await asyncio.sleep(1)

    logger.info(f"[Speaker Worker] Worker stopped for guild {guild_id}")


async def synthesize_audio(text: str) -> str | None:
    """Synthesizes text to an MP3 file using ElevenLabs (or gTTS fallback)."""
    loop = asyncio.get_running_loop()

    # Try ElevenLabs first
    if el_client and ELEVENLABS_VOICE_ID:
        try:
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
            logger.info(f"[Synth] ElevenLabs OK → {tmp_file.name}")
            return tmp_file.name

        except Exception as e:
            logger.error(f"[Synth] ElevenLabs failed, falling back to gTTS: {e}")

    # gTTS fallback
    try:
        def _gtts_generate():
            tts = gTTS(text=text, lang='ar')
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts.save(tmp.name)
            return tmp.name

        path = await loop.run_in_executor(None, _gtts_generate)
        logger.info(f"[Synth] gTTS OK → {path}")
        return path

    except Exception as e:
        logger.error(f"[Synth] gTTS also failed: {e}", exc_info=True)
        return None
