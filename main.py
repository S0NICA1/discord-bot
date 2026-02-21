import discord
from discord.ext import commands, tasks
import os
import asyncio
import io
import struct
import tempfile
import wave
import time
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv
from dashboard_ui import DashboardView
from web_dashboard import start_web_server

# Load environment variables
load_dotenv()

DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
ADMIN_USER_ID   = int(os.getenv("ADMIN_USER_ID", 0))
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", 0))

# Gemini clients
client         = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME     = "gemini-3-flash-preview"   # نموذج توليد النص
TTS_MODEL_NAME = "gemini-2.5-flash-preview-tts"  # نموذج الصوت

# Configure Intents
intents = discord.Intents.default()
intents.voice_states  = True
intents.members       = True
intents.guilds        = True
intents.presences     = True
intents.message_content = True


class RoastBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.vc_join_times    = {}   # {user_id: join_timestamp}
        self.last_roasted_user = None
        self.user_game_history = {}  # {user_id: set of game names}
        self.daily_stats       = {}  # {user_id: total_minutes_today}
        self.roast_log         = []  # [(timestamp, member_name, roast_text)]  – kept for web dashboard

    # ─── Setup ────────────────────────────────────────────────────────────────

    async def setup_hook(self):
        await self.tree.sync()
        self.roast_loop.start()
        self.daily_report_loop.start()

    async def on_ready(self):
        print(f"Logged in as {self.user.name} ({self.user.id})")
        for guild in self.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self.vc_join_times[member.id] = time.time() - 1800

    # ─── Voice / Presence tracking ────────────────────────────────────────────

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            self.vc_join_times[member.id]    = time.time()
            self.user_game_history[member.id] = set()
        elif before.channel is not None and after.channel is None:
            join_time = self.vc_join_times.pop(member.id, None)
            self.user_game_history.pop(member.id, None)
            if join_time:
                mins = int((time.time() - join_time) / 60)
                self.daily_stats[member.id] = self.daily_stats.get(member.id, 0) + mins

    async def on_presence_update(self, before, after):
        if after.bot:
            return
        if after.id in self.vc_join_times:
            self.user_game_history.setdefault(after.id, set())
            for activity in after.activities:
                if activity.type == discord.ActivityType.playing:
                    self.user_game_history[after.id].add(activity.name)

    # ─── TTS helpers ──────────────────────────────────────────────────────────

    async def generate_tts_audio(self, text: str) -> tuple[bytes, str] | None:
        """توليد صوت بنموذج Gemini TTS. يرجع (bytes, mime_type) أو None."""
        try:
            response = await client.aio.models.generate_content(
                model=TTS_MODEL_NAME,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Kore"
                            )
                        )
                    )
                )
            )
            part      = response.candidates[0].content.parts[0]
            audio_data = part.inline_data.data
            mime_type  = part.inline_data.mime_type
            print(f"TTS: {len(audio_data)} bytes | mime: {mime_type}")
            return audio_data, mime_type
        except Exception as e:
            print(f"TTS generation error: {e}")
            return None

    async def play_tts_in_voice(self, member: discord.Member, text: str):
        """البوت يدخل الفويس يذب بالصوت وبعدين يطلع."""
        if not member.voice or not member.voice.channel:
            return

        vc_channel = member.voice.channel
        result = await self.generate_tts_audio(text)
        if not result:
            print("TTS: لا يوجد صوت، تخطي دخول الفويس")
            return
        audio_bytes, mime_type = result
        print(f"TTS: {len(audio_bytes)} bytes | {mime_type}")

        # لو البوت موصول بفويس ثاني نقطعه أول
        if member.guild.voice_client:
            await member.guild.voice_client.disconnect(force=True)

        voice_client = None
        try:
            import re, audioop

            # استخراج sample rate من mime_type (مثلاً audio/L16;rate=24000)
            rate_m = re.search(r'rate=(\d+)', mime_type)
            src_rate = int(rate_m.group(1)) if rate_m else 24000

            # Discord يحتاج 48000Hz 16-bit stereo
            if src_rate != 48000:
                pcm_48k, _ = audioop.ratecv(audio_bytes, 2, 1, src_rate, 48000, None)
            else:
                pcm_48k = audio_bytes

            # تحويل mono → stereo
            pcm_stereo = audioop.tostereo(pcm_48k, 2, 1, 1)

            # تشغيل الصوت بدون ffmpeg!
            audio_io     = io.BytesIO(pcm_stereo)
            audio_source = discord.PCMAudio(audio_io)

            print(f"TTS: اتصال بالروم '{vc_channel.name}'")
            voice_client = await vc_channel.connect()

            loop     = asyncio.get_event_loop()
            finished = asyncio.Event()

            def after_play(error):
                if error:
                    print(f"Voice playback error: {error}")
                loop.call_soon_threadsafe(finished.set)

            voice_client.play(audio_source, after=after_play)
            print("TTS: شغّل الصوت — ينتظر يخلص")
            await asyncio.wait_for(finished.wait(), timeout=60)
            print("TTS: خلص الصوت ✅")

        except asyncio.TimeoutError:
            print("TTS: تجاوز الوقت (60 ثانية)")
        except Exception as e:
            print(f"Voice/TTS Error: {e}")
        finally:
            try:
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect(force=True)
            except Exception:
                pass



    # ─── Roast generation ─────────────────────────────────────────────────────

    async def generate_roast_for_member(self, member: discord.Member, channel: discord.TextChannel = None):
        if not channel:
            channel = (
                self.get_channel(MAIN_CHANNEL_ID)
                or member.guild.system_channel
                or (member.guild.text_channels[0] if member.guild.text_channels else None)
            )
        if not channel:
            print("No text channel found.")
            return

        # ─ حساب وقت الجلوس
        join_time    = self.vc_join_times.get(member.id, time.time() - 1800)
        minutes_in_vc = int((time.time() - join_time) / 60)

        if minutes_in_vc >= 60:
            h  = minutes_in_vc // 60
            m  = minutes_in_vc % 60
            lbl = {1: "ساعة", 2: "ساعتين"}.get(h, f"{h} ساعات")
            time_str = f"{lbl} و {m} دقيقة" if m else lbl
        else:
            time_str = f"{minutes_in_vc} دقيقة"

        # ─ الوقت بتوقيت السعودية
        current_hour = (time.gmtime().tm_hour + 3) % 24
        if 2 <= current_hour <= 5:
            time_context = "آخر الليل / الفجر، المفروض نايم."
        elif 6 <= current_hour <= 11:
            time_context = "الصبح بدري، الناس تداوم وهو مبلط بالديسكورد."
        else:
            time_context = "نص اليوم."

        # ─ الألعاب والحالة
        current_game  = None
        custom_status = None
        for act in member.activities:
            if act.type == discord.ActivityType.playing:
                current_game = act.name
                self.user_game_history.setdefault(member.id, set()).add(act.name)
            elif act.type == discord.ActivityType.custom:
                custom_status = getattr(act, 'name', None) or getattr(act, 'state', None)

        played_games = self.user_game_history.get(member.id, set())
        if current_game:
            game_info = f"يلعب الآن {current_game}."
        elif len(played_games) > 1:
            game_info = f"غيّر ألعابه من دخل (لعب {', '.join(played_games)}) وما استقر على شيء."
        else:
            game_info = "ما يلعب شيء، مسنتر على الفاضي."

        contradiction = (
            f"كاتب بحالته '{custom_status}' بس يلعب {current_game}! تناقض واضح."
            if custom_status and current_game else ""
        )

        # ─ الصوت والبث
        mute_info = stream_info = alone_info = ""
        vs = member.voice
        vc_ch = vs.channel if vs else None

        if vc_ch and len([m for m in vc_ch.members if not m.bot]) == 1:
            alone_info = "جالس بالروم لحاله! ما معاه أحد."

        if vs:
            if vs.self_stream:
                stream_info = "فاتح بث (Stream)!"
                if vc_ch and len([m for m in vc_ch.members if not m.bot]) == 1:
                    stream_info += " وبالروم ما فيه أحد يتابعه، يبث للجن!"
            if vs.self_deaf or vs.deaf:
                if minutes_in_vc >= 120 and not current_game:
                    mute_info = "مسوي دفن أكثر من ساعتين ولا يلعب شيء، نايم على الكيبورد؟"
                else:
                    mute_info = "مسوي دفن (Deafen)، وضعية الصنم."
            elif vs.self_mute or vs.mute:
                mute_info = "مسوي ميوت (Mute)، مكمبر ما يتكلم."

        prompt = (
            f"أنت بوت ديسكورد 'مستر ذبات'، شخصيتك شاب سعودي Gen Z ذباته قوية تضحك وتكسر الجبهة.\n"
            f"الضحية: '{member.display_name}'\n\n"
            f"--- معلومات ---\n"
            f"مدة الجلوس: {time_str}\n"
            f"الوقت: {time_context}\n"
            f"الألعاب: {game_info}\n"
            f"التناقض بالحالة: {contradiction}\n"
            f"الصوت: {mute_info}\n"
            f"البث: {stream_info}\n"
            f"لحاله؟: {alone_info}\n"
            f"----------------\n\n"
            "المطلوب: ذبة واحدة أو سطرين، عامية سعودية تيك توكر/تويتس، تفطس وتستفز وتقهر. "
            "بدون مقدمات أو شرح، فقط الذبة اللكمة!"
        )

        try:
            response = await client.aio.models.generate_content(
                model=MODEL_NAME, contents=prompt
            )
            roast_text = response.text.strip()

            await channel.send(f"<@{member.id}> {roast_text}")
            self.last_roasted_user = member.id

            # سجّل آخر 20 ذبة للداشبورد
            self.roast_log.append((time.time(), member.display_name, roast_text))
            self.roast_log = self.roast_log[-20:]

            # شغّل الصوت بالفويس
            if member.voice and member.voice.channel:
                asyncio.create_task(self.play_tts_in_voice(member, roast_text))

        except Exception as e:
            print(f"Roast error: {e}")

    # ─── Force random roast ───────────────────────────────────────────────────

    async def force_random_roast(self, channel: discord.TextChannel = None):
        eligible = []
        for guild in self.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue
                    tch = (
                        channel
                        or self.get_channel(MAIN_CHANNEL_ID)
                        or guild.system_channel
                        or (guild.text_channels[0] if guild.text_channels else None)
                    )
                    if tch:
                        eligible.append((member, tch))

        if not eligible:
            if channel:
                await channel.send("ما فيه أحد بالفويس عشان أذب عليه!")
            return

        if len(eligible) > 1:
            no_spam = [m for m in eligible if m[0].id != self.last_roasted_user]
            if no_spam:
                eligible = no_spam

        member, tch = random.choice(eligible)
        await self.generate_roast_for_member(member, tch)

    # ─── Toggle roast loop ────────────────────────────────────────────────────

    async def toggle_roast_loop(self):
        if self.roast_loop.is_running():
            self.roast_loop.cancel()
            return False
        else:
            self.roast_loop.start()
            return True

    # ─── Auto-roast loop ──────────────────────────────────────────────────────

    @tasks.loop(minutes=30)
    async def roast_loop(self):
        self.roast_loop.change_interval(minutes=random.randint(10, 60))
        await self.force_random_roast()

    @roast_loop.before_loop
    async def before_roast_loop(self):
        await self.wait_until_ready()

    # ─── Daily report loop (4am Saudi = 1am UTC) ─────────────────────────────

    @tasks.loop(minutes=60)
    async def daily_report_loop(self):
        current_utc_hour = time.gmtime().tm_hour
        if current_utc_hour != 1:   # 1am UTC = 4am Saudi
            return

        channel = self.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return

        # اجمع إحصائيات الناس اللي سهروا
        lines = []
        for guild in self.guilds:
            # أعضاء لسا بالفويس
            for uid, jt in self.vc_join_times.items():
                m = guild.get_member(uid)
                if m:
                    mins = self.daily_stats.get(uid, 0) + int((time.time() - jt) / 60)
                    lines.append(f"{m.display_name}: {mins} دقيقة")
            # أعضاء طلعوا
            for uid, mins in self.daily_stats.items():
                if uid not in self.vc_join_times:
                    m = guild.get_member(uid)
                    if m:
                        lines.append(f"{m.display_name}: {mins} دقيقة طلع من زمان")

        stats_text = "\n".join(lines) if lines else "الكل نام بدري الليلة!"

        report_prompt = (
            f"أنت مستر ذبات. اكتب تقرير يومي كوميدي بعامية سعودية عن هؤلاء السهرانين:\n"
            f"{stats_text}\n\n"
            "التقرير: طقطقة بدون رحمة، يذكر كل شخص، أسلوب تيك توك/تويتر، 3-5 أسطر، بدون مقدمات."
        )

        try:
            response = await client.aio.models.generate_content(
                model=MODEL_NAME, contents=report_prompt
            )
            await channel.send(f"📊 **تقرير مستر ذبات اليومي 🌙**\n\n{response.text.strip()}")
        except Exception as e:
            print(f"Daily report error: {e}")

        # إعادة تعيين الإحصائيات اليومية
        self.daily_stats.clear()

    @daily_report_loop.before_loop
    async def before_daily_report(self):
        await self.wait_until_ready()


# ─── Bot instance ─────────────────────────────────────────────────────────────

bot = RoastBot()


@bot.tree.command(name="dashboard", description="Admin control panel for Mr. Dhabat")
async def dashboard(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("غير مصرح لك.", ephemeral=True)
        return

    view = DashboardView(
        bot=bot,
        toggle_loop_callback=bot.toggle_roast_loop,
        force_roast_callback=bot.force_random_roast,
        generate_roast_callback=bot.generate_roast_for_member
    )
    await interaction.response.send_message("🕹️ **لوحة تحكم مستر ذبات**", view=view, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN or not GEMINI_API_KEY:
        print("Please set your DISCORD_TOKEN and GEMINI_API_KEY in the .env file")
    else:
        async def main():
            await asyncio.gather(
                start_web_server(bot),
                bot.start(DISCORD_TOKEN)
            )
        asyncio.run(main())
