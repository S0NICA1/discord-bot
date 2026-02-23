"""
voice_chat.py – محادثة صوتية تفاعلية لبوت مستر ذبات
وضع Walkie-Talkie: يستمع → يرد → يستمع
مع أوامر صوتية للتحكم بالفويس
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

# محاولة تحميل مكتبة استقبال الصوت
try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    print("⚠️ discord-ext-voice-recv not installed – voice chat disabled")

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
LISTEN_DURATION = 15  # مدة الاستماع بالثواني
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


class VoiceChatSession:
    """جلسة محادثة صوتية – وضع Walkie-Talkie."""

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

        # Audio buffers
        self._input_buffer = bytearray()  # صوت المستخدمين
        self._is_playing = False
        self._is_listening = True

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

        # أوامر التحكم بالفويس
        members_list = self._get_channel_members()

        txt += (
            "\n\nقواعد مهمة:"
            "\n- ردودك قصيرة (جملة إلى ثلاث جمل) لأنك بمحادثة صوتية."
            "\n- لا تقل 'طيب' أو 'حسناً' كثير، خلك طبيعي."
            "\n- إذا ما سمعت شيء واضح قل 'وش قلت؟' أو 'ما فهمت عليك'."
            "\n\n=== أوامر التحكم بالفويس ==="
            "\nإذا أحد قال لك أي شيء من هذي الأوامر، نفذها بالضبط:"
            "\n- 'اطرد [اسم]' أو 'طرد [اسم]' أو 'kick [اسم]' → رد عادي ثم أضف في نهاية ردك: [CMD:KICK:الاسم]"
            "\n- 'بوت اطلع' أو 'اطلع' أو 'روح' → رد وداع ثم أضف: [CMD:LEAVE]"
            "\n- 'اسكت [اسم]' أو 'سكت [اسم]' أو 'mute [اسم]' → رد عادي ثم أضف: [CMD:MUTE:الاسم]"
            "\n- مهم: الأمر [CMD:...] لازم يكون آخر شيء بالرد وبالضبط بهذا الشكل."
            f"\n\nالأعضاء الموجودين بالروم حالياً: {members_list}"
        )

        # ذاكرة المحادثة
        mem = getattr(self.bot, "voice_conversation_memory", {})
        user_mem = mem.get(self.requester.id, [])
        if user_mem:
            txt += f"\n\nتعرف هذا الشخص من قبل. آخر سوالفكم: {', '.join(user_mem[-5:])}"

        return txt

    def _get_channel_members(self):
        """أسماء الأعضاء بالروم الصوتي."""
        try:
            names = [m.display_name for m in self.voice_channel.members if not m.bot]
            return "، ".join(names) if names else "ما حد"
        except:
            return "غير معروف"

    # ─── بدء الجلسة ───────────────────────────────────────────────────

    async def start(self):
        self._loop = asyncio.get_running_loop()
        try:
            guild = self.bot.get_guild(self.guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=True)

            if HAS_VOICE_RECV:
                try:
                    self.voice_client = await asyncio.wait_for(
                        self.voice_channel.connect(cls=voice_recv.VoiceRecvClient),
                        timeout=30
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    print("[VoiceChat] VoiceRecvClient timeout, retrying...")
                    try:
                        guild = self.bot.get_guild(self.guild_id)
                        if guild and guild.voice_client:
                            await guild.voice_client.disconnect(force=True)
                        self.voice_client = await asyncio.wait_for(
                            self.voice_channel.connect(cls=voice_recv.VoiceRecvClient),
                            timeout=30
                        )
                    except (TimeoutError, asyncio.TimeoutError):
                        print("[VoiceChat] Fallback to normal VoiceClient")
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

    # ─── الحلقة الرئيسية (Walkie-Talkie) ─────────────────────────────

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
            async with client.aio.live.connect(
                model=LIVE_MODEL, config=config
            ) as session:
                self.live_session = session
                self.last_activity = time.time()

                # بدء الاستماع
                if HAS_VOICE_RECV and hasattr(self.voice_client, "listen"):
                    self.voice_client.listen(voice_recv.BasicSink(self._on_voice_data))

                try:
                    await self.text_channel.send(
                        "🎤 دخلت الروم! بسمع لكم وأرد.\n"
                        "📢 أوامر صوتية: **اطرد [اسم]** | **بوت اطلع**"
                    )
                except:
                    pass

                self._log("active")
                print(f"[VoiceChat] Started in '{self.voice_channel.name}' by {self.requester}")

                # ─── دورة Walkie-Talkie ───
                while self.running:
                    # 1️⃣ مرحلة الاستماع
                    self._is_listening = True
                    self._is_playing = False
                    self._input_buffer.clear()

                    # انتظر صوت أو timeout
                    listen_start = time.time()
                    has_audio = False

                    while self.running and (time.time() - listen_start) < LISTEN_DURATION:
                        await asyncio.sleep(0.3)
                        if len(self._input_buffer) > 0:
                            has_audio = True
                            # بعد ما يبدأ الصوت، كمّل سماع لحد ما يسكت أو ينتهي الوقت
                            silence_start = None
                            while self.running and (time.time() - listen_start) < LISTEN_DURATION:
                                await asyncio.sleep(0.2)
                                buf_len = len(self._input_buffer)
                                # إذا توقف الصوت لـ 2 ثانية، خلاص فهمنا
                                if buf_len == getattr(self, "_last_buf_len", 0):
                                    if silence_start is None:
                                        silence_start = time.time()
                                    elif time.time() - silence_start > 2.0:
                                        break
                                else:
                                    silence_start = None
                                self._last_buf_len = buf_len
                            break

                    if not self.running:
                        break

                    # إذا ما في صوت، تحقق من timeout السكوت
                    if not has_audio:
                        leave_sec = getattr(self.bot, "voice_auto_leave_sec", 120)
                        if time.time() - self.last_activity > leave_sec:
                            try:
                                await self.text_channel.send("🔇 ما حد يتكلم.. أنا طالع! 👋")
                            except:
                                pass
                            await self.stop(reason="سكوت")
                            return
                        continue

                    # 2️⃣ إرسال الصوت المجمّع لـ Gemini
                    self._is_listening = False
                    audio_data = bytes(self._input_buffer)
                    self._input_buffer.clear()

                    if len(audio_data) < 640:  # أقل من 20ms – تجاهل
                        continue

                    try:
                        await session.send_realtime_input(
                            audio={"data": audio_data, "mime_type": "audio/pcm;rate=16000"}
                        )
                    except Exception as e:
                        print(f"[VoiceChat] Send error: {e}")
                        continue

                    # 3️⃣ استقبال الرد الكامل
                    self._is_playing = True
                    audio_response = bytearray()
                    text_response = ""

                    try:
                        turn = session.receive()
                        async for response in turn:
                            if not self.running:
                                break

                            sc = getattr(response, "server_content", None)

                            # مقاطعة
                            if sc and getattr(sc, "interrupted", False):
                                audio_response.clear()
                                break

                            # استخلاص الصوت
                            if sc and sc.model_turn:
                                for part in sc.model_turn.parts:
                                    idata = getattr(part, "inline_data", None)
                                    if idata and isinstance(idata.data, bytes):
                                        audio_response.extend(idata.data)
                                    # استخلاص النص (للأوامر)
                                    if hasattr(part, "text") and part.text:
                                        text_response += part.text

                    except Exception as e:
                        print(f"[VoiceChat] Recv error: {e}")

                    # 4️⃣ تشغيل الرد
                    if audio_response and self.running:
                        try:
                            pcm_48k, _ = audioop.ratecv(
                                bytes(audio_response), 2, 1, 24000, 48000, None
                            )
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
                    self.messages_exchanged += 1
                    self.last_activity = time.time()

                    # 5️⃣ تنفيذ الأوامر الصوتية
                    if text_response:
                        await self._handle_voice_commands(text_response)

        except Exception as e:
            traceback.print_exc()
        finally:
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
        """يُنادى من thread آخر."""
        if not self.running or user.bot or not self._is_listening or self._is_playing:
            return
        if user.id in getattr(self.bot, "voice_ignored_users", set()):
            return

        self.participants.add(user.display_name)
        self.last_activity = time.time()

        try:
            raw = data.pcm if hasattr(data, "pcm") else bytes(data)
            pcm_mono = audioop.tomono(raw, 2, 1, 1)
            pcm_16k, _ = audioop.ratecv(pcm_mono, 2, 1, 48000, 16000, None)
            self._input_buffer.extend(pcm_16k)
        except Exception:
            pass

    # ─── تنفيذ أوامر الفويس ──────────────────────────────────────────

    async def _handle_voice_commands(self, text):
        """تحليل رد Gemini وتنفيذ الأوامر."""
        # أمر الخروج
        if "[CMD:LEAVE]" in text:
            await self.stop(reason="أمر صوتي")
            return

        # أمر الطرد
        kick_match = re.search(r"\[CMD:KICK:(.+?)\]", text)
        if kick_match:
            target_name = kick_match.group(1).strip()
            await self._kick_member(target_name)

        # أمر السكوت
        mute_match = re.search(r"\[CMD:MUTE:(.+?)\]", text)
        if mute_match:
            target_name = mute_match.group(1).strip()
            await self._mute_member(target_name)

    async def _kick_member(self, name):
        """طرد عضو من الفويس بالاسم."""
        try:
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                return
            for member in self.voice_channel.members:
                if name.lower() in member.display_name.lower():
                    await member.move_to(None)
                    try:
                        await self.text_channel.send(f"👢 {member.display_name} انطرد من الفويس!")
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
        """سكوت عضو بالفويس."""
        try:
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                return
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

    # ─── إيقاف الجلسة ────────────────────────────────────────────────

    async def stop(self, reason="يدوي"):
        if not self.running:
            return
        self.running = False

        if hasattr(self, "_connection_task"):
            self._connection_task.cancel()

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
