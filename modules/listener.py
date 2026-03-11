import logging
import time
import discord
import asyncio
import subprocess
import numpy as np
import io
import wave
import os
import gc
import random
from concurrent.futures import ThreadPoolExecutor

from discord.sinks import Sink
from modules.transcriber import transcribe_audio, contains_wake_word
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


def _convert_pcm_to_whisper_array(audio_bytes: bytes) -> np.ndarray:
    """Synchronous: Convert raw 48kHz Stereo 16-bit PCM to 16kHz Mono float32 for Whisper.
    Uses a temp WAV file + ffmpeg subprocess for maximum compatibility on Windows."""

    # Write input to a temp wav file
    import tempfile
    in_path = tempfile.mktemp(suffix=".wav")
    out_path = tempfile.mktemp(suffix=".wav")

    try:
        with wave.open(in_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframesraw(audio_bytes)

        # Use ffmpeg to convert to 16kHz mono 16-bit WAV
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out_path],
            capture_output=True, timeout=30
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg conversion failed: {result.stderr.decode(errors='ignore')[:500]}")
            return np.array([], dtype=np.float32)

        # Read the output WAV and convert to float32
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


class TonyAudioSink(Sink):
    """
    A custom Pycord audio sink that captures raw audio per user.
    It splits audio into chunks separated by a small period of silence.
    """
    def __init__(self, voice_client: discord.VoiceClient):
        super().__init__()
        self.vc = voice_client
        self.audio_data = {}   # {user_id: [bytearray_buffer, last_speak_time]}
        self.silence_threshold = 1.5  # seconds of silence to start processing
        self.user_cooldowns = {}  # {user_id: last_processed_time}
        self._running = True

    def write(self, data, user):
        """Called repeatedly when a user talks."""
        if user not in self.audio_data:
            self.audio_data[user] = [bytearray(), time.time()]

        # Append audio data and update the last time they spoke
        self.audio_data[user][0].extend(data)
        self.audio_data[user][1] = time.time()

    def cleanup(self):
        """Called by Pycord when recording stops."""
        self._running = False
        self.audio_data.clear()

    async def _process_loop(self):
        """Continuously checks if a user has stopped talking to process their chunk."""
        last_radio_time = time.time()

        while self._running:
            await asyncio.sleep(0.5)

            current_time = time.time()
            to_process = []

            for user, user_data in list(self.audio_data.items()):
                buffer, last_speak_time = user_data

                if current_time - last_speak_time > self.silence_threshold and len(buffer) > 0:
                    # Prevent processing empty noise (less than ~0.5 second)
                    if len(buffer) > 40000:
                        to_process.append((user, bytes(buffer)))

                    self.audio_data[user] = [bytearray(), current_time]
                    last_radio_time = current_time

            for user, buffer in to_process:
                asyncio.create_task(self._handle_user_audio(user, buffer))

            # Radio Tony: 10% chance every 5 minutes of total silence
            if current_time - last_radio_time > 300:
                last_radio_time = current_time
                try:
                    vc_members = [m for m in self.vc.channel.members if not m.bot]
                    if len(vc_members) > 0 and random.random() < 0.10:
                        logger.info("Triggering Radio Tony break-silence...")
                        guild = self.vc.guild
                        prompt = "الروم هدوء من فترة طويلة، افتح سالفة عشوائية، أو ذب على الهدوء، أو ارمِ نكتة."
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

    async def _handle_user_audio(self, user: int, audio_bytes: bytes):
        """Processes a chunk, checks cooldowns, and coordinates with brain/speaker."""

        current_time = time.time()
        last_processed = self.user_cooldowns.get(user, 0)
        if current_time - last_processed < 5.0:
            logger.debug(f"User {user} is on cooldown.")
            return

        guild = self.vc.guild
        member = guild.get_member(user)

        if not member or member.bot:
            return

        vc_members_count = len([m for m in self.vc.channel.members if not m.bot])
        afk_users = []
        try:
            afk_users = [m.display_name for m in self.vc.channel.members
                         if m.voice and (m.voice.self_mute or m.voice.self_deaf) and not m.bot]
        except:
            pass

        self.user_cooldowns[user] = current_time

        try:
            logger.info(f"Processing audio for {member.display_name} ({len(audio_bytes)} bytes)...")

            loop = asyncio.get_running_loop()

            # Convert audio in a thread so we don't block the event loop
            audio_np = await loop.run_in_executor(_executor, _convert_pcm_to_whisper_array, audio_bytes)

            if len(audio_np) == 0:
                logger.warning("Audio conversion returned empty array.")
                self.user_cooldowns[user] = 0
                return

            # Transcribe in a thread (already handled inside transcribe_audio)
            text = await transcribe_audio(audio_np)
            logger.info(f"Transcribed: '{text}'")

            # Horror Companion: Detect screams
            rms = float(np.sqrt(np.mean(audio_np ** 2))) if len(audio_np) > 0 else 0
            if rms > 0.35:
                logger.info("High volume detected (Horror Companion)!")
                text = f"[المرسل كان يصارخ بصوت عالي جداً أو منفجع] {text}"

            if text and contains_wake_word(text):
                logger.info(f"Wake word detected! Full text: {text}")

                # Run Gemini in a thread so it doesn't block the event loop
                response = await loop.run_in_executor(
                    _executor, generate_response,
                    guild.id, member.id, member.display_name, text, vc_members_count, afk_users
                )
                logger.info(f"Tony Response: {response}")

                await speak_text_to_discord(guild.id, response, self.vc)
            else:
                logger.debug(f"No wake word in: {text}")
                self.user_cooldowns[user] = 0

        except Exception as e:
            logger.error(f"Error handling user audio chunk: {e}", exc_info=True)
            self.user_cooldowns[user] = 0
        finally:
            gc.collect()


def start_listening(voice_client: discord.VoiceClient):
    """Attaches our custom TonySink to the voice client and starts processing loops."""
    sink = TonyAudioSink(voice_client)
    voice_client.start_recording(
        sink,
        callback=lambda *args: None
    )
    asyncio.create_task(sink._process_loop())
    logger.info("Tony is now listening to the voice channel!")


def stop_listening(voice_client: discord.VoiceClient):
    """Safely stop recording on a voice client."""
    try:
        voice_client.stop_recording()
    except Exception as e:
        logger.warning(f"Error stopping recording: {e}")
    logger.info("Tony stopped listening.")
