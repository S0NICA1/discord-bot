"""
voice_chat.py – محادثة صوتية تفاعلية لبوت مستر ذبات
مبني على الكود الرسمي من Google:
https://ai.google.dev/gemini-api/docs/live?example=mic-stream
"""
import asyncio
import audioop
import io
import os
import re
import time
import threading
import traceback
import discord
from google import genai
from google.genai import types

try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    print("⚠️ discord-ext-voice-recv not installed – voice chat disabled")

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


# ─── Streaming Audio Source لديسكورد ──────────────────────────────────
class StreamingSource(discord.AudioSource):
    """
    مصدر صوتي مستمر – ديسكورد يسحب منه frames بشكل مستمر.
    نغذّيه بالصوت من Gemini و هو يشغله فوراً بدون فجوات.
    """
    FRAME_SIZE = 3840  # 20ms @ 48kHz stereo 16-bit

    def __init__(self):
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._finished = False

    def write(self, pcm_48k_stereo: bytes):
        """أضف صوت للـ buffer (thread-safe)."""
        with self._lock:
            self._buffer.extend(pcm_48k_stereo)

    def read(self) -> bytes:
        """ديسكورد يسحب 20ms كل مرة."""
        with self._lock:
            if len(self._buffer) >= self.FRAME_SIZE:
                frame = bytes(self._buffer[:self.FRAME_SIZE])
                del self._buffer[:self.FRAME_SIZE]
                return frame
        # سكوت – صفر
        return b'\x00' * self.FRAME_SIZE

    def has_data(self):
        with self._lock:
            return len(self._buffer) > 0

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def is_opus(self):
        return False

    def cleanup(self):
        self._finished = True


# ─── جلسة المحادثة الصوتية ────────────────────────────────────────────
class VoiceChatSession:
    """جلسة محادثة صوتية – مبنية على المثال الرسمي من Google."""

    def __init__(self, bot, guild_id, voice_channel, text_channel, requester):
        self.bot = bot
        self.guild_id = guild_id
        self.voice_channel = voice_channel
        self.text_channel = text_channel
        self.requester = requester

        self.voice_client = None
        self.session = None
        self.running = False
        self.last_activity = time.time()
        self.start_time = time.time()
        self._loop = None
        self._tasks = []

        # Queues – مطابقة للمثال الرسمي
        self.audio_queue_output = asyncio.Queue()  # صوت من Gemini
        self.audio_queue_mic = asyncio.Queue(maxsize=5)  # صوت من المستخدم

        # Streaming source لديسكورد
        self._streaming_source = None
        self._is_playing = False

        # تحكم بالمتحدث
        self._active_speaker_id = None
        self._active_speaker = None
        self._speaker_silence = 0

        # تتبع
        self.messages_exchanged = 0
        self.participants = set()

        # Debug
        self.debug_log = []
        self._audio_recv_count = 0
        self._audio_send_count = 0
        self._gemini_recv_count = 0

    def _dbg(self, event, detail=""):
        entry = {
            "t": round(time.time(), 3),
            "elapsed": round(time.time() - self.start_time, 2),
            "event": event,
            "detail": str(detail)[:200],
        }
        self.debug_log.append(entry)
        if len(self.debug_log) > 200:
            self.debug_log = self.debug_log[-200:]
        print(f"[VoiceChat] {entry['elapsed']}s | {event}: {detail}")

    def get_debug_info(self):
        return {
            "running": self.running,
            "channel": self.voice_channel.name if self.voice_channel else "",
            "active_speaker": self._active_speaker.display_name if self._active_speaker else None,
            "is_playing": self._is_playing,
            "mic_queue_size": self.audio_queue_mic.qsize() if self.audio_queue_mic else 0,
            "output_queue_size": self.audio_queue_output.qsize() if self.audio_queue_output else 0,
            "audio_recv_count": self._audio_recv_count,
            "audio_send_count": self._audio_send_count,
            "gemini_recv_count": self._gemini_recv_count,
            "messages_exchanged": self.messages_exchanged,
            "participants": list(self.participants),
            "uptime_sec": round(time.time() - self.start_time, 1),
            "last_activity_ago": round(time.time() - self.last_activity, 1),
            "log": self.debug_log[-50:],
        }

    # ─── System Prompt ────────────────────────────────────────────────

    def _build_system(self):
        mode = getattr(self.bot, "voice_ai_mode", "helper")
        persona = getattr(self.bot, "current_persona", "troll")

        if getattr(self.bot, "current_persona_custom", None):
            txt = f"أنت 'مستر ذبات'، {self.bot.current_persona_custom}"
        elif mode == "helper":
            txt = "أنت مساعد صوتي ذكي ودود اسمه 'مستر ذبات'. تتكلم عربي سعودي عامي."
        elif mode == "dj":
            txt = "أنت DJ وشاعر اسمه 'مستر ذبات'. تغني وتنشد بأسلوب سعودي."
        else:
            personas = {
                "troll": "شاب سعودي Gen Z طقطوقي. ذباتك قوية.",
                "boomer": "شايب سعودي معصب. تذب عليهم أنهم جيل ضايع.",
                "tryhard": "لاعب إيسبورتس متعالي تتكلم عربي مكسر.",
                "psycho": "شخصية غامضة مخيفة. ذباتك هادية بس مرعبة.",
            }
            txt = f"أنت 'مستر ذبات'، {personas.get(persona, personas['troll'])}"

        members = self._get_channel_members()
        txt += (
            "\n\nقواعد:"
            "\n- ردودك قصيرة (جملة أو جملتين)."
            "\n- خلك طبيعي وعفوي."
            "\n\n=== أوامر ==="
            "\n- 'اطرد [اسم]' → رد ثم أضف: [CMD:KICK:الاسم]"
            "\n- 'بوت اطلع' أو 'روح' → رد وداع ثم أضف: [CMD:LEAVE]"
            f"\n\nالموجودين: {members}"
        )

        mem = getattr(self.bot, "voice_conversation_memory", {})
        user_mem = mem.get(self.requester.id, [])
        if user_mem:
            txt += f"\n\nتعرف هذا الشخص. سوالفكم: {', '.join(user_mem[-5:])}"
        return txt

    def _get_channel_members(self):
        try:
            return "، ".join(m.display_name for m in self.voice_channel.members if not m.bot) or "ما حد"
        except:
            return "غير معروف"

    # ─── Start ────────────────────────────────────────────────────────

    async def start(self):
        self._loop = asyncio.get_running_loop()
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=True)
                await asyncio.sleep(1)

            if HAS_VOICE_RECV:
                try:
                    self.voice_client = await asyncio.wait_for(
                        self.voice_channel.connect(cls=voice_recv.VoiceRecvClient), timeout=30
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    print("[VoiceChat] VoiceRecvClient timeout, fallback...")
                    guild = self.bot.get_guild(self.guild_id)
                    if guild and guild.voice_client:
                        await guild.voice_client.disconnect(force=True)
                    self.voice_client = await self.voice_channel.connect()
            else:
                self.voice_client = await self.voice_channel.connect()

            self.running = True
            self._connection_task = asyncio.create_task(self._run())

        except Exception as e:
            traceback.print_exc()
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            try:
                await self.text_channel.send(f"❌ ما قدرت أدخل الفويس: {e}")
            except:
                pass

    # ─── Main Session ─────────────────────────────────────────────────

    async def _run(self):
        try:
            print("[VoiceChat] _run() started")
            voice_name = getattr(self.bot, "current_voice", "Kore")

            # Config كـ dict – مطابق للمثال الرسمي
            config = {
                "response_modalities": ["AUDIO"],
                "system_instruction": self._build_system(),
                "speech_config": types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                ),
            }

            print(f"[VoiceChat] Connecting to {LIVE_MODEL}...")
            client = _get_client()

            async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
                self.session = session
                print("[VoiceChat] ✅ Gemini session connected!")

                # بدء الاستماع
                if HAS_VOICE_RECV and hasattr(self.voice_client, "listen"):
                    self.voice_client.listen(voice_recv.BasicSink(self._on_voice_data))
                    print("[VoiceChat] ✅ Voice listening started")

                # بدء Streaming Source لديسكورد (play مرة واحدة فقط!)
                self._streaming_source = StreamingSource()
                if self.voice_client and self.voice_client.is_connected():
                    self.voice_client.play(self._streaming_source)
                    print("[VoiceChat] ✅ Streaming source playing")

                self._tasks = [
                    asyncio.create_task(self._send_realtime()),
                    asyncio.create_task(self._receive_audio()),
                    asyncio.create_task(self._feed_streaming()),
                    asyncio.create_task(self._speaker_manager()),
                    asyncio.create_task(self._silence_watch()),
                ]

                self._dbg("SESSION_START", f"Connected to '{self.voice_channel.name}'")
                try:
                    await self.text_channel.send(
                        "🎤 دخلت الروم! تكلموا معي.\n"
                        "📢 أوامر: **اطرد [اسم]** | **بوت اطلع**"
                    )
                except:
                    pass
                self._log("active")

                while self.running:
                    await asyncio.sleep(1)

        except Exception as e:
            traceback.print_exc()
            self._dbg("SESSION_ERROR", str(e))
        finally:
            self.running = False
            for t in self._tasks:
                t.cancel()
            if self.voice_client and self.voice_client.is_connected():
                try:
                    if self.voice_client.is_playing():
                        self.voice_client.stop()
                    if hasattr(self.voice_client, "stop_listening"):
                        self.voice_client.stop_listening()
                    await self.voice_client.disconnect(force=True)
                except:
                    pass
            self.bot.voice_sessions.pop(self.guild_id, None)

    # ─── Voice Data from Discord (sync callback) ──────────────────────

    def _on_voice_data(self, user, data):
        """Sync callback من thread الفويس."""
        if not self.running or user.bot:
            return
        
        # 🎙️ ميزة Barge-in (المقاطعة):
        # تفعيل السماح بمقاطعة البوت وهو يتكلم.
        if self._streaming_source and self._streaming_source.has_data():
            # تفريغ الصوت المتبقي لإيقاف كلام البوت فوراً
            self._streaming_source.clear()
            # مسح الطابور المتبقي
            while not self.audio_queue_output.empty():
                try: self.audio_queue_output.get_nowait()
                except: pass

        if user.id in getattr(self.bot, "voice_ignored_users", set()):
            return

        now = time.time()

        # إذا قاطع شخص جديد፣ نقبل المقاطعة ونغير المتحدث
        if self._active_speaker_id is not None and user.id != self._active_speaker_id:
            # يمكن للعضو الجديد سرقة المايك والمقاطعة
            self._active_speaker_id = user.id
            self._active_speaker = user
        elif self._active_speaker_id is None:
            self._active_speaker_id = user.id
            self._active_speaker = user

        self._speaker_silence = now
        self.participants.add(user.display_name)
        self.last_activity = now
        self._audio_recv_count += 1

        try:
            raw = data.pcm if hasattr(data, "pcm") else bytes(data)
            pcm_mono = audioop.tomono(raw, 2, 1, 1)
            pcm_16k, _ = audioop.ratecv(pcm_mono, 2, 1, 48000, 16000, None)
            msg = {"data": pcm_16k, "mime_type": "audio/pcm"}
            # ⭐ thread-safe: schedule على event loop
            if self._loop and self.audio_queue_mic:
                self._loop.call_soon_threadsafe(self.audio_queue_mic.put_nowait, msg)
        except asyncio.QueueFull:
            pass  # تجاهل لو الطابور ممتلئ
        except Exception:
            pass

    # ─── Send to Gemini (مطابق للمثال الرسمي) ────────────────────────

    async def _send_realtime(self):
        """send_realtime_input – نفس المثال الرسمي بالضبط."""
        while self.running:
            try:
                msg = await self.audio_queue_mic.get()
                if self.session is not None:
                    await self.session.send_realtime_input(audio=msg)
                    self._audio_send_count += 1
            except Exception as e:
                if self.running:
                    self._dbg("SEND_ERROR", str(e))

    # ─── Receive from Gemini (مطابق للمثال الرسمي) ───────────────────

    async def _receive_audio(self):
        """نفس receive_audio بالمثال الرسمي بالضبط."""
        while self.running:
            try:
                if self.session is not None:
                    turn = self.session.receive()
                    text_parts = ""
                    async for response in turn:
                        if not self.running:
                            return
                        # استخلاص الصوت – مطابق للمثال الرسمي
                        if (response.server_content and response.server_content.model_turn):
                            for part in response.server_content.model_turn.parts:
                                if part.inline_data and isinstance(part.inline_data.data, bytes):
                                    self.audio_queue_output.put_nowait(part.inline_data.data)
                                    self._gemini_recv_count += 1
                                if hasattr(part, "text") and part.text:
                                    text_parts += part.text

                    # Turn complete – انتظر StreamingSource يخلص
                    await asyncio.sleep(0.3)  # انتظر آخر chunks تتحول
                    while self._streaming_source and self._streaming_source.has_data():
                        await asyncio.sleep(0.2)

                    # الحين فكّ القفل – أي شخص ثاني يقدر يتكلم
                    old_speaker = self._active_speaker.display_name if self._active_speaker else "?"
                    self._active_speaker_id = None
                    self._active_speaker = None
                    self._dbg("SPEAKER_UNLOCK", f"Released from {old_speaker}")

                    self.messages_exchanged += 1
                    self.last_activity = time.time()
                    self._dbg("TURN_COMPLETE", f"text: '{text_parts[:100]}'")

                    if text_parts:
                        await self._handle_voice_commands(text_parts)

            except Exception as e:
                if self.running:
                    self._dbg("RECV_ERROR", str(e))
                await asyncio.sleep(0.5)

    # ─── Feed Streaming Source (يحوّل ويغذّي الـ source فوراً) ────────

    async def _feed_streaming(self):
        """يأخذ chunks من audio_queue_output ويحولها ويغذّي الـ StreamingSource."""
        while self.running:
            try:
                # انتظر chunk صوتي من Gemini (24kHz mono)
                chunk_24k = await asyncio.wait_for(self.audio_queue_output.get(), timeout=1.0)

                # تحويل 24kHz mono → 48kHz stereo
                pcm_48k, _ = audioop.ratecv(chunk_24k, 2, 1, 24000, 48000, None)
                pcm_stereo = audioop.tostereo(pcm_48k, 2, 1, 1)

                # غذّي الـ streaming source – يتشغل فوراً!
                if self._streaming_source:
                    self._streaming_source.write(pcm_stereo)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.running:
                    self._dbg("FEED_ERROR", str(e))

    # ─── Speaker Manager ──────────────────────────────────────────────

    async def _speaker_manager(self):
        """فقط safety net – لو البوت علق ما يرد، يفك القفل بعد 30 ثانية."""
        while self.running:
            await asyncio.sleep(2)
            if self._active_speaker_id:
                # safety: لو مافي نشاط لمدة 30 ثانية، فك القفل
                if time.time() - self.last_activity > 30:
                    self._active_speaker_id = None
                    self._active_speaker = None
                    self._dbg("SPEAKER_TIMEOUT", "30s safety release")

    # ─── Silence Watch ────────────────────────────────────────────────

    async def _silence_watch(self):
        leave_sec = getattr(self.bot, "voice_auto_leave_sec", 120)
        while self.running:
            await asyncio.sleep(10)
            if time.time() - self.last_activity > leave_sec:
                try:
                    await self.text_channel.send("🔇 ما حد يتكلم.. أنا طالع! 👋")
                except:
                    pass
                await self.stop(reason="سكوت")
                break

    # ─── Voice Commands ───────────────────────────────────────────────

    async def _handle_voice_commands(self, text):
        if "[CMD:LEAVE]" in text:
            await self.stop(reason="أمر صوتي")
            return
        kick = re.search(r"\[CMD:KICK:(.+?)\]", text)
        if kick:
            name = kick.group(1).strip()
            try:
                for m in self.voice_channel.members:
                    if name.lower() in m.display_name.lower():
                        await m.move_to(None)
                        try: await self.text_channel.send(f"👢 {m.display_name} انطرد!")
                        except: pass
                        return
            except Exception as e:
                self._dbg("KICK_ERROR", str(e))

    # ─── Stop ─────────────────────────────────────────────────────────

    async def stop(self, reason="يدوي"):
        if not self.running:
            return
        self.running = False

        for t in self._tasks:
            t.cancel()
        if hasattr(self, "_connection_task"):
            self._connection_task.cancel()

        if self.voice_client and self.voice_client.is_connected():
            try:
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                if hasattr(self.voice_client, "stop_listening"):
                    self.voice_client.stop_listening()
                await self.voice_client.disconnect(force=True)
            except:
                pass

        dur = max(1, int((time.time() - self.start_time) / 60))
        parts = "، ".join(self.participants) if self.participants else "ما حد"
        try:
            await self.text_channel.send(
                f"📝 **ملخص الجلسة:**\n"
                f"⏱️ {dur} دقيقة | 👥 {parts}\n"
                f"💬 {self.messages_exchanged} ردود | 📌 {reason}"
            )
        except:
            pass

        mem = self.bot.voice_conversation_memory
        for name in self.participants:
            for guild in self.bot.guilds:
                for m in guild.members:
                    if m.display_name == name:
                        mem.setdefault(m.id, []).append(f"محادثة صوتية ({dur}د)")
                        mem[m.id] = mem[m.id][-10:]

        if self.bot.voice_session_log:
            self.bot.voice_session_log[-1].update({
                "end": time.time(), "messages": self.messages_exchanged,
                "status": "ended", "participants": list(self.participants), "reason": reason,
            })
        self.bot.voice_sessions.pop(self.guild_id, None)
        self._dbg("SESSION_END", reason)

    # ─── Log ──────────────────────────────────────────────────────────

    def _log(self, status):
        self.bot.voice_session_log.append({
            "start": time.time(), "requester": self.requester.display_name,
            "channel": self.voice_channel.name, "end": None,
            "messages": 0, "status": status,
        })
        self.bot.voice_session_log = self.bot.voice_session_log[-30:]
