"""
voice_chat.py – محادثة صوتية تفاعلية لبوت مستر ذبات
يستخدم Gemini Live API (gemini-2.5-flash-native-audio-preview)
لمحادثات صوت-لصوت في فويس ديسكورد.
"""
import asyncio
import audioop
import io
import os
import struct
import time
import traceback
import discord
from google import genai
from google.genai import types

# محاولة تحميل مكتبة استقبال الصوت
try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    print("⚠️ discord-ext-voice-recv not installed – voice chat disabled")

NATIVE_AUDIO_MODEL = "gemini-2.5-flash-native-audio-preview"
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


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
        self._loop = None  # سيتم تعيينه عند التشغيل

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
        else:  # roaster – يستخدم الشخصية الحالية
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
        self._loop = asyncio.get_running_loop()
        try:
            # فصل أي اتصال صوتي سابق
            guild = self.bot.get_guild(self.guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=True)

            # اتصال بالفويس
            if HAS_VOICE_RECV:
                self.voice_client = await self.voice_channel.connect(cls=voice_recv.VoiceRecvClient)
            else:
                self.voice_client = await self.voice_channel.connect()

            self.running = True
            self._connection_task = asyncio.create_task(self._run_gemini_session())

        except Exception as e:
            traceback.print_exc()
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            try:
                await self.text_channel.send(f"❌ ما قدرت أدخل الفويس: {e}")
            except:
                pass

    # ─── حلقة Gemini الرئيسية (async with) ──────────────────────────

    async def _run_gemini_session(self):
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

            client = _get_client()
            async with client.aio.live.connect(
                model=NATIVE_AUDIO_MODEL, config=config
            ) as session:
                self.live_session = session
                self.last_activity = time.time()

                # بدء الاستماع للأعضاء
                if HAS_VOICE_RECV and hasattr(self.voice_client, "listen"):
                    self.voice_client.listen(voice_recv.BasicSink(self._on_voice_data))

                # بدء المهام الفرعية
                self._tasks = [
                    asyncio.create_task(self._recv_loop()),
                    asyncio.create_task(self._play_loop()),
                    asyncio.create_task(self._silence_watch()),
                ]

                try:
                    await self.text_channel.send(
                        "🎤 دخلت الروم! تكلموا معي.. اكتبوا **بوت روح** عشان أطلع."
                    )
                except:
                    pass

                self._log("active")
                print(f"[VoiceChat] Started in '{self.voice_channel.name}' by {self.requester}")

                # ابقِ الجلسة مفتوحة
                while self.running:
                    await asyncio.sleep(1)

        except Exception as e:
            traceback.print_exc()
        finally:
            # تنظيف بعد خروج الـ context manager
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                try:
                    if hasattr(self.voice_client, "stop_listening"):
                        self.voice_client.stop_listening()
                    await self.voice_client.disconnect(force=True)
                except:
                    pass
            self.bot.voice_sessions.pop(self.guild_id, None)

    # ─── استقبال صوت الأعضاء (sync callback) ────────────────────────

    def _on_voice_data(self, user, data):
        """يُنادى من thread آخر. لا تستخدم await هنا."""
        if not self.running or user.bot or self._is_playing:
            return
        if user.id in getattr(self.bot, "voice_ignored_users", set()):
            return

        self.participants.add(user.display_name)
        self.last_activity = time.time()

        try:
            # data.pcm هو bytes بصيغة PCM 48kHz 16-bit stereo
            raw = data.pcm if hasattr(data, "pcm") else bytes(data)
            pcm_mono = audioop.tomono(raw, 2, 1, 1)
            pcm_16k, _ = audioop.ratecv(pcm_mono, 2, 1, 48000, 16000, None)
            # جدول الإرسال عبر event loop الرئيسي (thread-safe)
            asyncio.run_coroutine_threadsafe(self._send_audio(pcm_16k), self._loop)
        except Exception as e:
            pass  # تجاهل أي خطأ بالتحويل

    # ─── إرسال الصوت لـ Gemini ────────────────────────────────────────

    async def _send_audio(self, pcm_bytes):
        """إرسال chunk صوتي لـ Gemini Live API."""
        if not self.live_session or not self.running:
            return
        try:
            await self.live_session.send_realtime_input(
                audio={"data": pcm_bytes, "mime_type": "audio/pcm;rate=16000"}
            )
        except Exception as e:
            print(f"[VoiceChat] Send error: {e}")

    # ─── استقبال ردود Gemini ──────────────────────────────────────────

    async def _recv_loop(self):
        """حلقة استقبال مستمرة لردود Gemini الصوتية."""
        try:
            while self.running:
                try:
                    turn = self.live_session.receive()
                    async for response in turn:
                        if not self.running:
                            return

                        # استخلاص الصوت
                        if response.data is not None:
                            self._output_queue.put_nowait(response.data)
                            self.messages_exchanged += 1
                            self.last_activity = time.time()
                            continue

                        # طريقة بديلة: server_content
                        sc = getattr(response, "server_content", None)
                        if sc and sc.model_turn:
                            audio_buf = bytearray()
                            for part in sc.model_turn.parts:
                                if hasattr(part, "inline_data") and part.inline_data:
                                    if isinstance(part.inline_data.data, bytes):
                                        audio_buf.extend(part.inline_data.data)
                            if audio_buf:
                                self._output_queue.put_nowait(bytes(audio_buf))
                                self.messages_exchanged += 1
                                self.last_activity = time.time()

                        # هل تم المقاطعة؟
                        if sc and getattr(sc, "interrupted", False):
                            if self.voice_client and self.voice_client.is_playing():
                                self.voice_client.stop()
                            while not self._output_queue.empty():
                                try:
                                    self._output_queue.get_nowait()
                                except:
                                    pass

                except Exception as inner_e:
                    if self.running:
                        print(f"[VoiceChat] Recv turn error: {inner_e}")
                    await asyncio.sleep(0.5)

        except Exception as e:
            if self.running:
                print(f"[VoiceChat] Recv loop error: {e}")

    # ─── تشغيل الصوت بالديسكورد ──────────────────────────────────────

    async def _play_loop(self):
        """تشغيل أجزاء الصوت المستقبلة من Gemini في الفويس."""
        while self.running:
            try:
                data = await asyncio.wait_for(self._output_queue.get(), timeout=1.0)
                self._is_playing = True

                # Gemini يرسل 24kHz mono → نحول لـ 48kHz stereo لديسكورد
                pcm_48k, _ = audioop.ratecv(data, 2, 1, 24000, 48000, None)
                pcm_stereo = audioop.tostereo(pcm_48k, 2, 1, 1)

                if self.voice_client and self.voice_client.is_connected():
                    src = discord.PCMAudio(io.BytesIO(pcm_stereo))
                    if self.voice_client.is_playing():
                        self.voice_client.stop()
                    finished = asyncio.Event()
                    self.voice_client.play(
                        src,
                        after=lambda e: self._loop.call_soon_threadsafe(finished.set),
                    )
                    await asyncio.wait_for(finished.wait(), timeout=60)

                self._is_playing = False
            except asyncio.TimeoutError:
                self._is_playing = False
            except Exception as e:
                self._is_playing = False
                if self.running:
                    print(f"[VoiceChat] Play error: {e}")

    # ─── مراقبة السكوت ───────────────────────────────────────────────

    async def _silence_watch(self):
        leave_sec = getattr(self.bot, "voice_auto_leave_sec", 120)
        while self.running:
            await asyncio.sleep(5)
            if time.time() - self.last_activity > leave_sec:
                try:
                    await self.text_channel.send("🔇 ما حد يتكلم.. أنا طالع! 👋")
                except:
                    pass
                await self.stop(reason="سكوت")
                break

    # ─── إيقاف الجلسة ────────────────────────────────────────────────

    async def stop(self, reason="يدوي"):
        if not self.running:
            return
        self.running = False

        # إلغاء المهام الفرعية
        for t in self._tasks:
            t.cancel()
        if hasattr(self, "_connection_task"):
            self._connection_task.cancel()

        # فصل الفويس
        if self.voice_client and self.voice_client.is_connected():
            try:
                if hasattr(self.voice_client, "stop_listening"):
                    self.voice_client.stop_listening()
                await self.voice_client.disconnect(force=True)
            except:
                pass

        # ملخص
        dur = max(1, int((time.time() - self.start_time) / 60))
        parts = "، ".join(self.participants) if self.participants else "ما حد"
        summary = (
            f"📝 **ملخص الجلسة:**\n"
            f"⏱️ المدة: {dur} دقيقة | 👥 المشاركين: {parts}\n"
            f"💬 عدد الردود: {self.messages_exchanged} | 📌 سبب الخروج: {reason}"
        )
        try:
            await self.text_channel.send(summary)
        except:
            pass

        # حفظ الذاكرة
        mem = self.bot.voice_conversation_memory
        for name in self.participants:
            for guild in self.bot.guilds:
                for m in guild.members:
                    if m.display_name == name:
                        mem.setdefault(m.id, []).append(f"محادثة صوتية ({dur}د)")
                        mem[m.id] = mem[m.id][-10:]

        # تحديث السجل
        if self.bot.voice_session_log:
            self.bot.voice_session_log[-1].update({
                "end": time.time(),
                "messages": self.messages_exchanged,
                "status": "ended",
                "participants": list(self.participants),
                "reason": reason,
            })

        self.bot.voice_sessions.pop(self.guild_id, None)
        print(f"[VoiceChat] Session ended: {reason}")

    # ─── سجل ────────────────────────────────────────────────────────

    def _log(self, status):
        self.bot.voice_session_log.append({
            "start": time.time(),
            "requester": self.requester.display_name,
            "channel": self.voice_channel.name,
            "end": None,
            "messages": 0,
            "status": status,
        })
        self.bot.voice_session_log = self.bot.voice_session_log[-30:]
