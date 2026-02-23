"""
voice_chat.py – محادثة صوتية تفاعلية لبوت مستر ذبات
نظام: Streaming مع تركيز على متحدث واحد
"""
import asyncio
import audioop
import io
import os
import re
import time
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


class VoiceChatSession:
    """جلسة محادثة صوتية – تركيز على متحدث واحد."""

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
        self._loop = None
        self._tasks = []

        # تحكم بالمتحدث
        self._active_speaker = None       # المتحدث الحالي (user object)
        self._active_speaker_id = None    # ID المتحدث الحالي
        self._speaker_lock_time = 0       # متى بدأ يتكلم
        self._speaker_silence = 0         # آخر مرة سمعنا صوته
        self._is_playing = False          # هل البوت يتكلم الآن

        # تجميع الصوت
        self._input_buffer = bytearray()

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
                "troll": "شاب سعودي Gen Z طقطوقي مبدع. ذباتك قوية تكسر الجبهة.",
                "boomer": "شايب سعودي معصب يعتبر الديسكورد تضييع وقت.",
                "tryhard": "لاعب إيسبورتس أجنبي متعالي تتكلم عربي مكسر.",
                "psycho": "شخصية غامضة مخيفة. ذباتك هادية بس مرعبة.",
            }
            txt = f"أنت 'مستر ذبات'، {personas.get(persona, personas['troll'])}"

        members_list = self._get_channel_members()
        txt += (
            "\n\nقواعد مهمة:"
            "\n- ردودك قصيرة (جملة أو جملتين)."
            "\n- خلك طبيعي وعفوي."
            "\n- إذا ما سمعت شيء واضح قل 'وش قلت؟'"
            "\n\n=== أوامر التحكم ==="
            "\n- 'اطرد [اسم]' → رد ثم أضف: [CMD:KICK:الاسم]"
            "\n- 'بوت اطلع' أو 'روح' → رد وداع ثم أضف: [CMD:LEAVE]"
            "\n- 'اسكت [اسم]' → رد ثم أضف: [CMD:MUTE:الاسم]"
            f"\n\nالموجودين بالروم: {members_list}"
        )

        mem = getattr(self.bot, "voice_conversation_memory", {})
        user_mem = mem.get(self.requester.id, [])
        if user_mem:
            txt += f"\n\nتعرف هذا الشخص. آخر سوالفكم: {', '.join(user_mem[-5:])}"

        return txt

    def _get_channel_members(self):
        try:
            return "، ".join(m.display_name for m in self.voice_channel.members if not m.bot) or "ما حد"
        except:
            return "غير معروف"

    # ─── بدء الجلسة ───────────────────────────────────────────────────

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
                    print("[VoiceChat] VoiceRecvClient timeout, trying normal...")
                    guild = self.bot.get_guild(self.guild_id)
                    if guild and guild.voice_client:
                        await guild.voice_client.disconnect(force=True)
                    self.voice_client = await self.voice_channel.connect()
            else:
                self.voice_client = await self.voice_channel.connect()

            self.running = True
            self._connection_task = asyncio.create_task(self._run_session())

        except Exception as e:
            traceback.print_exc()
            self.running = False
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            try:
                await self.text_channel.send(f"❌ ما قدرت أدخل الفويس: {e}")
            except:
                pass

    # ─── الجلسة الرئيسية ──────────────────────────────────────────────

    async def _run_session(self):
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
            async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
                self.live_session = session
                self.last_activity = time.time()

                if HAS_VOICE_RECV and hasattr(self.voice_client, "listen"):
                    self.voice_client.listen(voice_recv.BasicSink(self._on_voice_data))

                self._tasks = [
                    asyncio.create_task(self._send_audio_loop()),
                    asyncio.create_task(self._recv_audio_loop()),
                    asyncio.create_task(self._play_audio_loop()),
                    asyncio.create_task(self._speaker_manager()),
                    asyncio.create_task(self._silence_watch()),
                ]

                try:
                    await self.text_channel.send(
                        "🎤 دخلت الروم! تكلموا واحد واحد وأنا أرد عليكم.\n"
                        "📢 أوامر: **اطرد [اسم]** | **بوت اطلع**"
                    )
                except:
                    pass
                self._log("active")
                print(f"[VoiceChat] Started in '{self.voice_channel.name}'")

                while self.running:
                    await asyncio.sleep(1)

        except Exception as e:
            traceback.print_exc()
        finally:
            self.running = False
            for t in self._tasks:
                t.cancel()
            if self.voice_client and self.voice_client.is_connected():
                try:
                    if hasattr(self.voice_client, "stop_listening"):
                        self.voice_client.stop_listening()
                    await self.voice_client.disconnect(force=True)
                except:
                    pass
            self.bot.voice_sessions.pop(self.guild_id, None)

    # ─── استقبال صوت الأعضاء ──────────────────────────────────────────

    def _on_voice_data(self, user, data):
        """Sync callback – يقبل صوت المتحدث النشط فقط."""
        if not self.running or user.bot or self._is_playing:
            return
        if user.id in getattr(self.bot, "voice_ignored_users", set()):
            return

        now = time.time()

        # إذا ما في متحدث نشط، هذا يصير المتحدث
        if self._active_speaker_id is None:
            self._active_speaker_id = user.id
            self._active_speaker = user
            self._speaker_lock_time = now
            print(f"[VoiceChat] 🔒 Locked to: {user.display_name}")

        # فقط المتحدث النشط يسمعه البوت
        if user.id != self._active_speaker_id:
            return

        self._speaker_silence = now
        self.participants.add(user.display_name)
        self.last_activity = now

        try:
            raw = data.pcm if hasattr(data, "pcm") else bytes(data)
            pcm_mono = audioop.tomono(raw, 2, 1, 1)
            pcm_16k, _ = audioop.ratecv(pcm_mono, 2, 1, 48000, 16000, None)
            self._input_buffer.extend(pcm_16k)
        except Exception:
            pass

    # ─── إدارة المتحدث النشط ──────────────────────────────────────────

    async def _speaker_manager(self):
        """يراقب المتحدث – إذا سكت 3 ثواني يفتح لغيره."""
        while self.running:
            await asyncio.sleep(0.5)
            if self._active_speaker_id and not self._is_playing:
                silence = time.time() - self._speaker_silence
                if silence > 3.0:  # سكت 3 ثواني
                    old = self._active_speaker.display_name if self._active_speaker else "?"
                    self._active_speaker_id = None
                    self._active_speaker = None
                    print(f"[VoiceChat] 🔓 Released from: {old}")

    # ─── إرسال الصوت لـ Gemini ────────────────────────────────────────

    async def _send_audio_loop(self):
        """تجميع وإرسال صوت المتحدث كل 250ms."""
        while self.running:
            await asyncio.sleep(0.25)
            if not self._input_buffer or not self.live_session or self._is_playing:
                continue

            batch = bytes(self._input_buffer)
            self._input_buffer.clear()

            try:
                await self.live_session.send_realtime_input(
                    audio={"data": batch, "mime_type": "audio/pcm;rate=16000"}
                )
            except Exception as e:
                print(f"[VoiceChat] Send error: {e}")

    # ─── استقبال ردود Gemini ──────────────────────────────────────────

    _output_queue = None

    async def _recv_audio_loop(self):
        """استقبال الصوت من Gemini وتمريره للتشغيل."""
        self._output_queue = asyncio.Queue()
        try:
            while self.running:
                try:
                    turn = self.live_session.receive()
                    turn_audio = bytearray()
                    text_parts = ""

                    async for response in turn:
                        if not self.running:
                            return

                        sc = getattr(response, "server_content", None)

                        # مقاطعة
                        if sc and getattr(sc, "interrupted", False):
                            turn_audio.clear()
                            if self.voice_client and self.voice_client.is_playing():
                                self.voice_client.stop()
                            while not self._output_queue.empty():
                                try: self._output_queue.get_nowait()
                                except: pass
                            continue

                        # استخلاص الصوت والنص
                        if sc and sc.model_turn:
                            for part in sc.model_turn.parts:
                                idata = getattr(part, "inline_data", None)
                                if idata and isinstance(idata.data, bytes):
                                    turn_audio.extend(idata.data)
                                if hasattr(part, "text") and part.text:
                                    text_parts += part.text

                    # رد كامل جاهز
                    if turn_audio:
                        self._output_queue.put_nowait(
                            {"audio": bytes(turn_audio), "text": text_parts}
                        )
                        self.messages_exchanged += 1
                        self.last_activity = time.time()

                except Exception as e:
                    if self.running:
                        print(f"[VoiceChat] Recv error: {e}")
                    await asyncio.sleep(0.5)

        except Exception as e:
            if self.running:
                print(f"[VoiceChat] Recv loop error: {e}")

    # ─── تشغيل الصوت ─────────────────────────────────────────────────

    async def _play_audio_loop(self):
        """تشغيل ردود Gemini بالفويس."""
        while self.running:
            try:
                if self._output_queue is None:
                    await asyncio.sleep(0.2)
                    continue

                item = await asyncio.wait_for(self._output_queue.get(), timeout=1.0)
                audio_data = item["audio"]
                text_data = item.get("text", "")

                self._is_playing = True
                # مسح buffer الإدخال عشان ما يتراكم صوت أثناء الرد
                self._input_buffer.clear()

                try:
                    pcm_48k, _ = audioop.ratecv(audio_data, 2, 1, 24000, 48000, None)
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
                        await asyncio.wait_for(finished.wait(), timeout=120)
                except Exception as e:
                    print(f"[VoiceChat] Play error: {e}")

                self._is_playing = False
                # بعد ما يخلص الرد، يفتح لأي شخص يتكلم
                self._active_speaker_id = None
                self._active_speaker = None

                # تنفيذ أوامر صوتية
                if text_data:
                    await self._handle_voice_commands(text_data)

            except asyncio.TimeoutError:
                pass
            except Exception as e:
                self._is_playing = False
                if self.running:
                    print(f"[VoiceChat] Play loop error: {e}")

    # ─── مراقبة السكوت ───────────────────────────────────────────────

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

    # ─── أوامر صوتية ─────────────────────────────────────────────────

    async def _handle_voice_commands(self, text):
        if "[CMD:LEAVE]" in text:
            await self.stop(reason="أمر صوتي")
            return

        kick_match = re.search(r"\[CMD:KICK:(.+?)\]", text)
        if kick_match:
            name = kick_match.group(1).strip()
            await self._kick_member(name)

        mute_match = re.search(r"\[CMD:MUTE:(.+?)\]", text)
        if mute_match:
            name = mute_match.group(1).strip()
            await self._mute_member(name)

    async def _kick_member(self, name):
        try:
            for member in self.voice_channel.members:
                if name.lower() in member.display_name.lower():
                    await member.move_to(None)
                    try:
                        await self.text_channel.send(f"👢 {member.display_name} انطرد!")
                    except:
                        pass
                    return
            try:
                await self.text_channel.send(f"❓ ما لقيت '{name}' بالروم.")
            except:
                pass
        except Exception as e:
            print(f"[VoiceChat] Kick error: {e}")

    async def _mute_member(self, name):
        try:
            for member in self.voice_channel.members:
                if name.lower() in member.display_name.lower():
                    await member.edit(mute=True)
                    try:
                        await self.text_channel.send(f"🔇 {member.display_name} انسكت!")
                    except:
                        pass
                    return
        except Exception as e:
            print(f"[VoiceChat] Mute error: {e}")

    # ─── إيقاف ────────────────────────────────────────────────────────

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
            except:
                pass

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
        print(f"[VoiceChat] Ended: {reason}")

    # ─── سجل ──────────────────────────────────────────────────────────

    def _log(self, status):
        self.bot.voice_session_log.append({
            "start": time.time(), "requester": self.requester.display_name,
            "channel": self.voice_channel.name, "end": None,
            "messages": 0, "status": status,
        })
        self.bot.voice_session_log = self.bot.voice_session_log[-30:]
