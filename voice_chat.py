"""
voice_chat.py – محادثة صوتية تفاعلية لبوت مستر ذبات
يستخدم Gemini Live API (gemini-2.5-flash-native-audio-preview-12-2025)
لمحادثات صوت-لصوت في فويس ديسكورد.
"""
import asyncio
import audioop
import io
import os
import time
import discord
from google import genai
from google.genai import types
import base64

# محاولة تحميل مكتبة استقبال الصوت
try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    print("⚠️ discord-ext-voice-recv not installed – voice chat disabled")

NATIVE_AUDIO_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class VoiceChatSession:
    """جلسة محادثة صوتية واحدة بين روم ديسكورد و Gemini Live."""

    def __init__(self, bot, guild_id, voice_channel, text_channel, requester):
        self.bot = bot
        self.guild_id = guild_id
        self.voice_channel = voice_channel
        self.text_channel = text_channel
        self.requester = requester

        self.voice_client = None
        self.live_session = None
        self.running = False
        self.last_activity = time.time()
        self.start_time = time.time()
        self._tasks = []
        self._output_queue = asyncio.Queue()
        self._is_playing = False

        # تتبع
        self.messages_exchanged = 0
        self.participants = set()

    # ─── بناء البرومبت ─────────────────────────────────────────────────

    def _build_system(self):
        mode = getattr(self.bot, "voice_ai_mode", "helper")
        persona = getattr(self.bot, "current_persona", "troll")

        if mode == "helper":
            txt = (
                "أنت مساعد صوتي ذكي ودود اسمه 'مستر ذبات'. "
                "تتكلم عربي سعودي عامي، ترد بوضوح وبأسلوب صديق."
            )
        elif mode == "dj":
            txt = (
                "أنت DJ وشاعر ومغني اسمه 'مستر ذبات'. "
                "إذا طلبوا أغنية غنِّها، وإذا طلبوا شعر انشده. "
                "تطقطق وتنشد بأسلوب سعودي."
            )
        else:
            personas = {
                "troll": "شاب سعودي Gen Z طقطوقي مبدع. ذباتك قوية تكسر الجبهة. لغة جيمنج معربة.",
                "boomer": "شايب سعودي معصب يعتبر الديسكورد تضييع وقت. تذب عليهم أنهم جيل ضايع.",
                "tryhard": "لاعب إيسبورتس أجنبي متعالي تتكلم عربي مكسر وتحتقر لعبهم.",
                "psycho": "شخصية غامضة مخيفة. ذباتك هادية بس مرعبة ومستفزة.",
            }
            txt = f"أنت 'مستر ذبات'، {personas.get(persona, personas['troll'])}"

        txt += (
            "\n\nقواعد مهمة:"
            "\n- ردودك قصيرة جداً (جملة أو جملتين) لأنك بمحادثة صوتية حية."
            "\n- لا تقل 'طيب' أو 'حسناً' كثير، خلك طبيعي."
            "\n- إذا ما سمعت شيء واضح قل 'وش قلت؟'"
        )

        # ذاكرة المحادثة
        mem = getattr(self.bot, "voice_conversation_memory", {})
        user_mem = mem.get(self.requester.id, [])
        if user_mem:
            txt += f"\n\nتعرف هذا الشخص من قبل. آخر سوالفكم: {', '.join(user_mem[-5:])}"

        return txt

    # ─── بدء الجلسة ───────────────────────────────────────────────────

    async def start(self):
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=True)

            if HAS_VOICE_RECV:
                self.voice_client = await self.voice_channel.connect(cls=voice_recv.VoiceRecvClient)
            else:
                self.voice_client = await self.voice_channel.connect()

            self.running = True
            self._connection_task = asyncio.create_task(self._gemini_connection_loop())

        except Exception as e:
            import traceback; traceback.print_exc()
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            await self.text_channel.send(f"❌ ما قدرت أدخل الفويس: {e}")

    async def _gemini_connection_loop(self):
        try:
            voice_name = getattr(self.bot, "current_voice", "Kore")
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=self._build_system(),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                ),
            )

            async with _client.aio.live.connect(model=NATIVE_AUDIO_MODEL, config=config) as session:
                self.live_session = session
                self.last_activity = time.time()

                if HAS_VOICE_RECV and hasattr(self.voice_client, "listen"):
                    self.voice_client.listen(voice_recv.BasicSink(self._on_voice))

                self._tasks = [
                    asyncio.create_task(self._recv_gemini()),
                    asyncio.create_task(self._play_loop()),
                    asyncio.create_task(self._silence_watch()),
                ]

                try:
                    await self.text_channel.send("🎤 دخلت الروم! تكلموا معي.. اكتبوا **بوت روح** عشان أطلع.")
                except: pass
                
                self._log("active")
                print(f"Voice chat started in '{self.voice_channel.name}' by {self.requester}")

                while self.running:
                    await asyncio.sleep(1)

        except Exception as e:
            import traceback; traceback.print_exc()
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            try:
                await self.text_channel.send(f"❌ خطأ بالاتصال مع الذكاء الاصطناعي: {e}")
            except: pass

    # ─── استقبال صوت الأعضاء ──────────────────────────────────────────

    def _on_voice(self, user, data):
        if not self.running or user.bot or self._is_playing:
            return
        if user.id in getattr(self.bot, "voice_ignored_users", set()):
            return

        self.participants.add(user.display_name)
        self.last_activity = time.time()

        try:
            pcm_mono = audioop.tomono(data.pcm, 2, 1, 1)
            pcm_16k, _ = audioop.ratecv(pcm_mono, 2, 1, 48000, 16000, None)
            asyncio.get_event_loop().create_task(self._send_chunk(pcm_16k))
        except Exception:
            pass

    async def _send_chunk(self, pcm):
        if self.live_session and self.running:
            try:
                # إرسال بيانات الصوت بصيغة pcm 16kHz كـ base64 أو bytes حسب قبول المكتبة
                # نستخدم types.Part في genai
                part = types.Part.from_bytes(data=pcm, mime_type="audio/pcm;rate=16000")
                await self.live_session.send(input=part, end_of_turn=False)
            except Exception as e:
                print(f"Send chunk error: {e}")

    # ─── استقبال رد Gemini ────────────────────────────────────────────

    async def _recv_gemini(self):
        try:
            async for resp in self.live_session.receive():
                if not self.running:
                    break
                
                sc = resp.server_content
                if not sc:
                    continue

                audio_buf = bytearray()
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and isinstance(part.inline_data.data, bytes):
                            audio_buf.extend(part.inline_data.data)
                
                if getattr(sc, "interrupted", False):
                    if self.voice_client and self.voice_client.is_playing():
                        self.voice_client.stop()
                    # Clear any pending output
                    while not self._output_queue.empty():
                        try: self._output_queue.get_nowait()
                        except: pass

                if audio_buf:
                    self._output_queue.put_nowait(bytes(audio_buf))
                    self.messages_exchanged += 1
                    self.last_activity = time.time()
                    
        except Exception as e:
            if self.running:
                print(f"Gemini recv error: {e}")

    # ─── تشغيل الصوت ─────────────────────────────────────────────────

    async def _play_loop(self):
        while self.running:
            try:
                data = await asyncio.wait_for(self._output_queue.get(), timeout=1.0)
                self._is_playing = True

                pcm_48k, _ = audioop.ratecv(data, 2, 1, 24000, 48000, None)
                pcm_stereo = audioop.tostereo(pcm_48k, 2, 1, 1)

                if self.voice_client and self.voice_client.is_connected():
                    src = discord.PCMAudio(io.BytesIO(pcm_stereo))
                    if self.voice_client.is_playing():
                        self.voice_client.stop()
                    finished = asyncio.Event()
                    loop = asyncio.get_event_loop()
                    self.voice_client.play(src, after=lambda e: loop.call_soon_threadsafe(finished.set))
                    await asyncio.wait_for(finished.wait(), timeout=60)

                self._is_playing = False
            except asyncio.TimeoutError:
                self._is_playing = False
            except Exception as e:
                self._is_playing = False
                if self.running:
                    print(f"Play error: {e}")

    # ─── مراقبة السكوت ───────────────────────────────────────────────

    async def _silence_watch(self):
        leave_sec = getattr(self.bot, "voice_auto_leave_sec", 120)
        while self.running:
            await asyncio.sleep(5)
            if time.time() - self.last_activity > leave_sec:
                await self.text_channel.send("🔇 ما حد يتكلم.. أنا طالع! 👋")
                await self.stop(reason="سكوت")
                break

    # ─── إيقاف الجلسة ────────────────────────────────────────────────

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
                if hasattr(self.voice_client, "stop_listening"):
                    self.voice_client.stop_listening()
                await self.voice_client.disconnect(force=True)
            except: pass

        # ملخص
        dur = int((time.time() - self.start_time) / 60)
        parts = "، ".join(self.participants) if self.participants else "ما حد"
        summary = (
            f"📝 **ملخص الجلسة:**\n"
            f"⏱️ المدة: {dur} دقيقة | 👥 المشاركين: {parts}\n"
            f"💬 عدد الردود: {self.messages_exchanged} | 📌 سبب الخروج: {reason}"
        )
        try:
            await self.text_channel.send(summary)
        except: pass

        # حفظ الذاكرة
        mem = self.bot.voice_conversation_memory
        for uid_name in self.participants:
            for guild in self.bot.guilds:
                for m in guild.members:
                    if m.display_name == uid_name:
                        mem.setdefault(m.id, []).append(f"محادثة صوتية ({dur}د)")
                        mem[m.id] = mem[m.id][-10:]

        # تحديث السجل
        if self.bot.voice_session_log:
            self.bot.voice_session_log[-1].update({
                "end": time.time(), "messages": self.messages_exchanged,
                "status": "ended", "participants": list(self.participants), "reason": reason
            })

        self.bot.voice_sessions.pop(self.guild_id, None)
        print(f"Voice chat ended: {reason}")

    # ─── سجل ────────────────────────────────────────────────────────

    def _log(self, status):
        self.bot.voice_session_log.append({
            "start": time.time(), "requester": self.requester.display_name,
            "channel": self.voice_channel.name, "end": None,
            "messages": 0, "status": status
        })
        self.bot.voice_session_log = self.bot.voice_session_log[-30:]
