import logging
import time
import discord
import asyncio
import os
import wave
import gc

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
        
    def write(self, data, user):
        """Called repeatedly when a user talks."""
        if user not in self.audio_data:
            self.audio_data[user] = [bytearray(), time.time()]
            
        # Append audio data and update the last time they spoke
        self.audio_data[user][0].extend(data)
        self.audio_data[user][1] = time.time()

    async def _process_loop(self):
        """Continuously checks if a user has stopped talking to process their chunk."""
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

            for user, buffer in to_process:
                # Fire off the transcription asynchronously so it doesn't block the loop
                asyncio.create_task(self._handle_user_audio(user, buffer))

    async def _handle_user_audio(self, user: int, audio_bytes: bytes):
        """Saves a chunk, transcribes it, and coordinates with brain and speaker."""
        
        # Only process if we can find the member object
        guild = self.vc.guild
        member = guild.get_member(user)
        
        if not member or member.bot:
            return

        file_path = f"tmp_audio_{user}_{int(time.time())}.wav"
        
        try:
            # We dump the PCM payload to a WAV file so Whisper can process it easily.
            with wave.open(file_path, "wb") as wav:
                wav.setnchannels(2)  # Discord gives us Pycord stereo PCM
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(48000) # Pycord framerate
                wav.writeframesraw(audio_bytes)
            
            logger.info(f"Processing audio for {member.display_name} ({len(audio_bytes)} bytes)...")
            
            text = await transcribe_audio(file_path)
            
            if text and contains_wake_word(text):
                logger.info(f"Wake word detected! Transcription: {text}")
                
                response = generate_response(guild.id, member.id, member.display_name, text)
                logger.info(f"Tony Response: {response}")
                
                await speak_text_to_discord(guild.id, response, self.vc)
            else:
                logger.debug(f"Ignored transcription: {text}")
                
        except Exception as e:
            logger.error(f"Error handling user audio chunk: {e}")
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
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
