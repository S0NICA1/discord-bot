import logging
import time
import discord
import asyncio
import numpy as np
import ffmpeg
import gc
import random

from discord.sinks import Sink
from modules.transcriber import transcribe_audio, contains_wake_word
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord

logger = logging.getLogger(__name__)

class TonyAudioSink(Sink):
    """
    A custom Pycord audio sink that captures raw audio per user.
    It splits audio into chunks separated by a small period of silence.
    """
    def __init__(self, voice_client: discord.VoiceClient):
        super().__init__()
        self.vc = voice_client
        self.audio_data = {}  # {user_id: [bytearray_buffer, last_speak_time]}
        self.silence_threshold = 1.5  # seconds of silence to start processing
        self.user_cooldowns = {} # {user_id: last_processed_time}
        
    def write(self, data, user):
        """Called repeatedly when a user talks."""
        if user not in self.audio_data:
            self.audio_data[user] = [bytearray(), time.time()]
            
        # Append audio data and update the last time they spoke
        self.audio_data[user][0].extend(data)
        self.audio_data[user][1] = time.time()

    async def _process_loop(self):
        """Continuously checks if a user has stopped talking to process their chunk."""
        last_radio_time = time.time()
        
        while True:
            await asyncio.sleep(0.5)
            
            # Check users who have stopped talking
            current_time = time.time()
            to_process = []
            
            for user, user_data in list(self.audio_data.items()):
                buffer, last_speak_time = user_data
                
                # If they haven't spoken in the threshold but have audio saved
                if current_time - last_speak_time > self.silence_threshold and len(buffer) > 0:
                    
                    # Prevent processing empty noise (less than a second usually)
                    if len(buffer) > 40000:  
                        to_process.append((user, bytes(buffer)))
                        
                    # Clear their buffer
                    self.audio_data[user] = [bytearray(), current_time]
                    last_radio_time = current_time # Reset radio silence

            for user, buffer in to_process:
                # Fire off the transcription asynchronously so it doesn't block the loop
                asyncio.create_task(self._handle_user_audio(user, buffer))

            # Radio Tony Logic (10% chance to speak every 5 minutes of total silence)
            if current_time - last_radio_time > 300:
                last_radio_time = current_time
                vc_members = [m for m in self.vc.channel.members if not m.bot]
                
                if len(vc_members) > 0 and random.random() < 0.10:
                    logger.info("Triggering Radio Tony break-silence...")
                    prompt = "الروم هدوء من فترة طويلة، افتح سالفة عشوائية، أو ذب على الهدوء، أو ارمِ نكتة."
                    guild = self.vc.guild
                    
                    async def trigger_radio():
                        try:
                            response = generate_response(guild.id, getattr(self.vc, 'user', type('obj', (object,), {'id': 0})).id, "System", prompt, len(vc_members))
                            await speak_text_to_discord(guild.id, response, self.vc)
                        except Exception as e:
                            logger.error(f"Radio Tony failed: {e}")
                            
                    asyncio.create_task(trigger_radio())

    async def _handle_user_audio(self, user: int, audio_bytes: bytes):
        """Processes a chunk entirely in memory, checks cooldowns, and coordinates with brain/speaker."""
        
        # Spam Protection: Cooldown of 5 seconds per user
        current_time = time.time()
        last_processed = self.user_cooldowns.get(user, 0)
        if current_time - last_processed < 5.0:
            logger.debug(f"User {user} is on cooldown. Ignoring audio chunk.")
            return
            
        guild = self.vc.guild
        member = guild.get_member(user)
        
        if not member or member.bot:
            return

        # Count non-bot members sitting in this specific voice channel
        vc_members_count = len([m for m in self.vc.channel.members if not m.bot])
        
        # Detect members who are deafened or muted to let Tony roast them
        afk_users = [m.display_name for m in self.vc.channel.members if m.voice and (m.voice.self_mute or m.voice.self_deaf) and not m.bot]
        
        # Lock the user out for 5 seconds to prevent them spamming Tony while he thinks
        self.user_cooldowns[user] = current_time
        
        try:
            logger.info(f"Processing audio for {member.display_name} in-memory ({len(audio_bytes)} bytes)...")
            
            # In-memory conversion from 48kHz Stereo 16-bit PCM to 16kHz Mono Float32 using ffmpeg
            # This drastically reduces latency by avoiding disk I/O completely
            out, _ = (
                ffmpeg
                .input('pipe:', format='s16le', acodec='pcm_s16le', ac=2, ar='48k')
                .output('pipe:', format='f32le', acodec='pcm_f32le', ac=1, ar='16k')
                .run(input=audio_bytes, capture_stdout=True, capture_stderr=True)
            )
            
            audio_np = np.frombuffer(out, np.float32)
            
            text = await transcribe_audio(audio_np)
            
            # Horror Companion: Detect screams
            rms = np.sqrt(np.mean(audio_np**2)) if len(audio_np) > 0 else 0
            if rms > 0.35:
                logger.info("High volume detected (Horror Companion)!")
                text = f"[المرسل كان يصارخ بصوت عالي جداً أو منفجع] {text}"
            
            if text and contains_wake_word(text):
                logger.info(f"Wake word detected! Transcription: {text}")
                
                response = generate_response(guild.id, member.id, member.display_name, text, vc_members_count, afk_users)
                logger.info(f"Tony Response: {response}")
                
                await speak_text_to_discord(guild.id, response, self.vc)
            else:
                logger.debug(f"Ignored transcription: {text}")
                # Reset cooldown if they didn't actually call him, so they can try again quickly
                self.user_cooldowns[user] = 0 
                
        except Exception as e:
            logger.error(f"Error handling user audio chunk: {e}")
            self.user_cooldowns[user] = 0
        finally:
            gc.collect()

def start_listening(voice_client: discord.VoiceClient):
    """Attaches our custom TonySink to the voice client and starts processing loops."""
    sink = TonyAudioSink(voice_client)
    voice_client.start_recording(
        sink,
        callback=lambda *args: None # Custom callback handled inside Sink Loop
    )
    
    # We must tie the process loop to the same event loop in the bot background
    asyncio.create_task(sink._process_loop())
    logger.info("Tony is now listening to the voice channel!")

def stop_listening(voice_client: discord.VoiceClient):
    """Safely stop recording on a voice client."""
    voice_client.stop_recording()
    logger.info("Tony stopped listening.")
