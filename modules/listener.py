import logging
import time
import discord
import asyncio
import subprocess
import numpy as np
import wave
import os
import gc
import random
from concurrent.futures import ThreadPoolExecutor
from discord.ext.voice_recv import VoiceRecvClient, AudioSink, BasicSink

from modules.transcriber import transcribe_audio, contains_wake_word
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


def _convert_pcm_to_whisper_array(audio_bytes: bytes) -> np.ndarray:
    """Synchronous: Convert raw 48kHz Stereo 16-bit PCM to 16kHz Mono float32 for Whisper."""
    import tempfile
    in_path = tempfile.mktemp(suffix=".wav")
    out_path = tempfile.mktemp(suffix=".wav")

    try:
        with wave.open(in_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframesraw(audio_bytes)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out_path],
            capture_output=True, timeout=30
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg conversion failed: {result.stderr.decode(errors='ignore')[:500]}")
            return np.array([], dtype=np.float32)

        with wave.open(out_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_np

    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return np.array([], dtype=np.float32)
    finally:
        for p in [in_path, out_path]:
            try:
                os.remove(p)
            except:
                pass


class TonyAudioSink(AudioSink):
    """
    Audio sink using discord-ext-voice-recv (supports DAVE E2EE via davey library).
    Buffers audio per user and processes after silence is detected.
    """

    def __init__(self, voice_client):
        super().__init__()
        self.vc = voice_client
        self.audio_buffers = {}   # {user_id: [bytearray, last_speak_time]}
        self.silence_threshold = 1.5
        self.user_cooldowns = {}
        self._running = True

    def wants_opus(self) -> bool:
        return False  # We want decoded PCM

    def write(self, user, data):
        """Called by discord-ext-voice-recv for each audio packet."""
        if user is None:
            return

        user_id = user.id if hasattr(user, 'id') else user

        if user_id not in self.audio_buffers:
            self.audio_buffers[user_id] = [bytearray(), time.time()]

        self.audio_buffers[user_id][0].extend(data.pcm)
        self.audio_buffers[user_id][1] = time.time()

    def cleanup(self):
        """Called when recording stops."""
        self._running = False
        self.audio_buffers.clear()

    async def _process_loop(self):
        """Background loop that detects silence and processes audio chunks."""
        last_radio_time = time.time()

        while self._running:
            await asyncio.sleep(0.5)
            current_time = time.time()
            to_process = []

            for user_id, (buffer, last_speak_time) in list(self.audio_buffers.items()):
                if current_time - last_speak_time > self.silence_threshold and len(buffer) > 0:
                    if len(buffer) > 40000:  # >~0.4 seconds of audio
                        to_process.append((user_id, bytes(buffer)))
                    self.audio_buffers[user_id] = [bytearray(), current_time]
                    last_radio_time = current_time

            for user_id, buffer in to_process:
                asyncio.create_task(self._handle_user_audio(user_id, buffer))

            # Radio Tony: break silence after 5 minutes
            if current_time - last_radio_time > 300:
                last_radio_time = current_time
                try:
                    vc_members = [m for m in self.vc.channel.members if not m.bot]
                    if vc_members and random.random() < 0.10:
                        guild = self.vc.guild
                        prompt = "الروم هدوء من فترة طويلة، افتح سالفة عشوائية أو رمِ نكتة."
                        asyncio.create_task(self._radio_speak(guild, prompt, len(vc_members)))
                except Exception as e:
                    logger.error(f"Radio Tony error: {e}")

    async def _radio_speak(self, guild, prompt, member_count):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                _executor, generate_response, guild.id, 0, "System", prompt, member_count, []
            )
            await speak_text_to_discord(guild.id, response, self.vc)
        except Exception as e:
            logger.error(f"Radio Tony speak failed: {e}")

    async def _handle_user_audio(self, user_id: int, audio_bytes: bytes):
        """Processes a captured audio chunk — transcribes, detects wake word, responds."""
        current_time = time.time()
        if current_time - self.user_cooldowns.get(user_id, 0) < 5.0:
            return

        guild = self.vc.guild
        member = guild.get_member(user_id)
        if not member or member.bot:
            return

        vc_members_count = len([m for m in self.vc.channel.members if not m.bot])
        afk_users = []
        try:
            afk_users = [
                m.display_name for m in self.vc.channel.members
                if m.voice and (m.voice.self_mute or m.voice.self_deaf) and not m.bot
            ]
        except:
            pass

        self.user_cooldowns[user_id] = current_time

        try:
            logger.info(f"Processing audio for {member.display_name} ({len(audio_bytes)} bytes)...")
            loop = asyncio.get_running_loop()

            # Convert in thread
            audio_np = await loop.run_in_executor(_executor, _convert_pcm_to_whisper_array, audio_bytes)
            if len(audio_np) == 0:
                logger.warning("Audio conversion returned empty array.")
                self.user_cooldowns[user_id] = 0
                return

            # Transcribe in thread
            text = await transcribe_audio(audio_np)
            logger.info(f"Transcribed: '{text}'")

            # Horror companion: detect screams
            rms = float(np.sqrt(np.mean(audio_np ** 2))) if len(audio_np) > 0 else 0
            if rms > 0.35:
                logger.info("High volume detected (Horror Companion)!")
                text = f"[المرسل كان يصارخ بصوت عالي جداً] {text}"

            if text and contains_wake_word(text):
                logger.info(f"Wake word detected! Full text: {text}")
                response = await loop.run_in_executor(
                    _executor, generate_response,
                    guild.id, member.id, member.display_name, text, vc_members_count, afk_users
                )
                logger.info(f"Tony Response: {response}")
                await speak_text_to_discord(guild.id, response, self.vc)
            else:
                logger.debug(f"No wake word in: {text}")
                self.user_cooldowns[user_id] = 0

        except Exception as e:
            logger.error(f"Error handling user audio: {e}", exc_info=True)
            self.user_cooldowns[user_id] = 0
        finally:
            gc.collect()


def start_listening(voice_client: discord.VoiceClient):
    """Attaches TonyAudioSink to voice client and starts the processing loop."""
    sink = TonyAudioSink(voice_client)

    # discord-ext-voice-recv uses listen() instead of start_recording()
    voice_client.listen(sink)

    asyncio.create_task(sink._process_loop())
    logger.info("Tony is now listening!")


def stop_listening(voice_client: discord.VoiceClient):
    """Stop listening."""
    try:
        voice_client.stop_listening()
    except AttributeError:
        # Fallback for standard VoiceClient
        try:
            voice_client.stop_recording()
        except:
            pass
    except Exception as e:
        logger.warning(f"Error stopping listening: {e}")
    logger.info("Tony stopped listening.")
