"""
main.py - بوت مستر ذبات 3.0 (Roast Lab & The Ambush Engine)
تركيز 100% على الذبات، المحاكمات، حلبات الـ 1v1، وبطاقات العار البصرية بدون أي تبعيات صوتية.
"""
import asyncio
import io
import json
import logging
import os
import random
import signal
import sys
import time
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from modules.dialects import DIALECTS, get_dialect_prompt
from modules.state_manager import state_mgr
from modules.roast_engine import roast_engine
from modules.ai_service import generate_content_ai
from modules.court import CourtVoteView
from web_dashboard import start_web_server, create_web_app

logger = logging.getLogger("mr_roast.core")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Load environment variables
load_dotenv()

DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
ADMIN_USER_ID   = int(os.getenv("ADMIN_USER_ID", 0))
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", 0))
AFK_CHANNEL_ID  = 782986605148635166  # روم AFK - يتجاهل الأعضاء فيه

# Configure Intents
intents = discord.Intents.default()
intents.voice_states    = True
intents.members         = True
intents.guilds          = True
intents.presences       = True
intents.message_content = True


class RoastBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.vc_join_times        = {}   # {user_id: join_timestamp}
        self.last_roasted_user    = None
        self.user_game_history    = {}   # {user_id: set of game names}
        self.daily_stats          = {}   # {user_id: total_minutes_today}
        self.roast_log            = []   # [(timestamp, member_name, roast_text)]

        self.roast_count_per_user = {}  # {user_id: count}
        self.daily_roast_counts   = {}   # {"YYYY-MM-DD": count}
        self.hourly_vc_activity   = [0]*24
        self.game_popularity      = {}   # {game_name: play_count}
        self.grudge_levels        = {}   # {user_id: score}

        self.state_mgr            = state_mgr
        self.dossier_mgr          = state_mgr
        self.load_data()

        self.protected_users      = set()
        self.last_roast_time      = None
        self.roast_interval_min   = 120
        self.roast_interval_max   = 240
        self.current_persona      = "troll"
        self.current_persona_custom = None
        self.current_dialect      = "default"
        self.roast_engine         = roast_engine
        self.server_memory        = {}
        self.user_speak_history   = {}
        self._start_time          = time.time()

    def load_data(self):
        try:
            m = self.state_mgr.metrics
            self.roast_log = m.get("roast_log", [])[-100:]
            self.roast_count_per_user = {int(k): v for k, v in m.get("roast_count_per_user", {}).items() if str(k).isdigit()}
            self.daily_roast_counts = m.get("daily_roast_counts", {})
            self.hourly_vc_activity = m.get("hourly_vc_activity", [0]*24)
            self.game_popularity = m.get("game_popularity", {})
            self.grudge_levels = {int(k): v for k, v in m.get("grudge_levels", {}).items() if str(k).isdigit()}
            self.current_dialect = m.get("current_dialect", "default")
        except Exception as e:
            logger.error(f"Data load error: {e}")

    def save_data(self):
        try:
            m = self.state_mgr.metrics
            m["roast_log"] = self.roast_log[-100:]
            m["roast_count_per_user"] = {str(k): v for k, v in self.roast_count_per_user.items()}
            m["daily_roast_counts"] = self.daily_roast_counts
            m["hourly_vc_activity"] = self.hourly_vc_activity
            m["game_popularity"] = self.game_popularity
            m["grudge_levels"] = {str(k): v for k, v in self.grudge_levels.items()}
            m["current_dialect"] = self.current_dialect
            self.state_mgr._sync_save_state_atomic()
        except Exception as e:
            logger.error(f"Data save error: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        self.daily_report_loop.start()
        print("Slash commands synced successfully.")

    async def on_ready(self):
        print(f"Logged in as {self.user.name} ({self.user.id}) - Mr. Roast 3.0 Ready!")
        for guild in self.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self.vc_join_times[member.id] = time.time() - 1800

    # ─── Presence & Activity Tracking ─────────────────────────────────────────

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            if after.channel.id == AFK_CHANNEL_ID:
                return
            self.vc_join_times[member.id] = time.time()
            self.user_game_history[member.id] = set()
            saudi_hour = (time.gmtime().tm_hour + 3) % 24
            self.hourly_vc_activity[saudi_hour] += 1
            self.user_speak_history[member.id] = {"unmuted_sec": 0, "last_unmute": 0}

        elif before.channel is not None and after.channel is None:
            join_time = self.vc_join_times.pop(member.id, None)
            self.user_speak_history.pop(member.id, None)
            self.user_game_history.pop(member.id, None)
            if join_time:
                mins = int((time.time() - join_time) / 60)
                self.daily_stats[member.id] = self.daily_stats.get(member.id, 0) + mins

        # تتبع الميوت والسكوت
        if before.channel == after.channel and before.channel is not None:
            spk = self.user_speak_history.setdefault(member.id, {"unmuted_sec": 0, "last_unmute": 0})
            was_muted = getattr(before, 'self_mute', False) or getattr(before, 'mute', False)
            is_muted = getattr(after, 'self_mute', False) or getattr(after, 'mute', False)
            if was_muted and not is_muted:
                spk["last_unmute"] = time.time()
            elif not was_muted and is_muted:
                if spk["last_unmute"] > 0:
                    spk["unmuted_sec"] += (time.time() - spk["last_unmute"])
                    spk["last_unmute"] = 0

        self.save_data()

    async def on_presence_update(self, before, after):
        if after.bot:
            return
        if after.id in self.vc_join_times:
            self.user_game_history.setdefault(after.id, set())
            for activity in after.activities:
                if activity.type == discord.ActivityType.playing:
                    self.user_game_history[after.id].add(activity.name)
                    self.game_popularity[activity.name] = self.game_popularity.get(activity.name, 0) + 1
                    self.save_data()

    # ─── Roast Generation Core ────────────────────────────────────────────────

    async def generate_roast_for_member(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        custom_topic: str = None,
        custom_intensity: int = None,
        custom_dialect: str = None
    ):
        """توليد ذبة ذكية لشخص بناءً على سوابقه ونشاطه ولهجته المختارة."""
        join_time = self.vc_join_times.get(member.id, time.time())
        minutes_in_vc = int((time.time() - join_time) / 60)

        # تجهيز السياق
        hours = minutes_in_vc // 60
        mins = minutes_in_vc % 60
        time_str = f"{hours} ساعة و {mins} دقيقة" if hours > 0 else f"{mins} دقيقة"

        games = list(self.user_game_history.get(member.id, []))
        game_info = f"يلعب: {', '.join(games)}" if games else "ما يلعب شيء (صنم)"

        mute_info = ""
        if member.voice:
            if member.voice.self_deaf or member.voice.deaf:
                mute_info = "مسوي دفن (Deafened) ولا يسمع أحد"
            elif member.voice.self_mute or member.voice.mute:
                mute_info = "مسوي ميوت (صامت)"
            else:
                mute_info = "المايك مفتوح"

        # تناقض الحالة
        contradiction = ""
        for act in member.activities:
            if act.type == discord.ActivityType.custom and act.name:
                low = act.name.lower()
                if any(w in low for w in ["sleep", "نايم", "نوم", "study", "مذاكرة", "busy", "مشغول"]):
                    contradiction = f"كاتب في حالته: '{act.name}' وهو متواجد ومسهر!"

        # اللهجة والشخصية
        active_dialect = custom_dialect or self.current_dialect
        dialect_instruction = get_dialect_prompt(active_dialect)
        
        intensity_map = {
            1: "مداعبة خفيفة وحنونة ولطيفة جداً بدون أي تجريح",
            2: "طقطقة خفيفة ومرحة وودية",
            3: "ذبة متوازنة وذكية وسريعة ومحرجة بذكاء",
            4: "قوية وحارة وقصف جبهة لاذع ومستفز",
            5: "قصف نووي مدمر بدون أي رحمة وإحراج تام وكشف المستور"
        }
        intensity_desc = intensity_map.get(custom_intensity or 3, intensity_map[3])

        dossier_context = self.dossier_mgr.format_context_for_roast(member.id)
        grudge_score = self.grudge_levels.get(member.id, 0)
        grudge_info = f"مستوى الحقد المتراكم عليه: {grudge_score}." if grudge_score > 10 else ""

        topic_instruction = f"الموضوع المستهدف للذب: [{custom_topic}]" if custom_topic else "اختر أدق زلة أو تناقض في وضعه الحالي واجلده به."

        prompt = f"""
أنت 'مستر ذبات 3.0'، أذكى وأقوى بوت طقطقة وسخرية في الديسكورد السعودي.
الضحية المستهدفة: '{member.display_name}'
اللهجة الإجبارية: [{dialect_instruction}]
مستوى القوة: [{intensity_desc}]

--- ملف وبيانات الضحية الآن ---
- المدة بالفويس: {time_str}
- النشاط والألعاب: {game_info}
- وضع المايك: {mute_info}
- {contradiction}
{dossier_context}
{grudge_info}
-------------------------------
{topic_instruction}

التعليمات:
1. التزم بنسبة 100% باللهجة المطلوبة ومصطلحاتها الأصيلة. ممنوع الفصحى نهائياً!
2. سطرين بالكثير، ذبة لاذعة ومضحكة ومفاجئة تجلد الضحية في مقتل بدون أي مقدمات أو ترحيب.
"""
        try:
            resp = await generate_content_ai(contents=prompt)
            roast_text = resp.text.strip()

            await channel.send(f"<@{member.id}> {roast_text}")
            self.last_roasted_user = member.id

            self.roast_log.append((time.time(), member.display_name, roast_text))
            self.roast_log = self.roast_log[-100:]

            self.roast_count_per_user[member.id] = self.roast_count_per_user.get(member.id, 0) + 1
            import datetime
            today = datetime.date.today().isoformat()
            self.daily_roast_counts[today] = self.daily_roast_counts.get(today, 0) + 1
            self.last_roast_time = time.time()
            self.grudge_levels[member.id] = self.grudge_levels.get(member.id, 0) + random.randint(2, 5)
            self.save_data()
            return roast_text
        except Exception as e:
            print(f"Roast error: {e}")
            return None

    # ─── Force & Targeted Commands ────────────────────────────────────────────

    async def force_random_roast(self, channel: discord.TextChannel = None):
        eligible = []
        for guild in self.guilds:
            for vc in guild.voice_channels:
                if vc.id == AFK_CHANNEL_ID: continue
                for m in vc.members:
                    if not m.bot and m.id not in self.protected_users:
                        tch = channel or self.get_channel(MAIN_CHANNEL_ID) or guild.system_channel
                        if tch:
                            eligible.append((m, tch))

        if not eligible:
            # ابحث في المتواجدين بالسيرفر عموماً
            for guild in self.guilds:
                for m in guild.members:
                    if not m.bot and m.status != discord.Status.offline and m.id not in self.protected_users:
                        tch = channel or self.get_channel(MAIN_CHANNEL_ID) or guild.system_channel
                        if tch:
                            eligible.append((m, tch))
                            break

        if eligible:
            m, tch = random.choice(eligible)
            await self.generate_roast_for_member(m, tch)

    async def targeted_roast(self, member_id: int, topic: str = None, intensity: int = None, dialect: str = None, play_audio: bool = False):
        for guild in self.guilds:
            member = guild.get_member(member_id)
            if member:
                ch = self.get_channel(MAIN_CHANNEL_ID) or guild.system_channel or guild.text_channels[0]
                if ch:
                    await self.generate_roast_for_member(member, ch, custom_topic=topic, custom_intensity=intensity, custom_dialect=dialect)
                    return True
        return False

    async def send_custom_roast(self, member_id: int, text: str):
        ch = self.get_channel(MAIN_CHANNEL_ID)
        if not ch and self.guilds:
            ch = self.guilds[0].system_channel
        if not ch: return False
        try:
            await ch.send(f"<@{member_id}> {text}")
            member_name = str(member_id)
            for g in self.guilds:
                m = g.get_member(member_id)
                if m: member_name = m.display_name; break
            self.roast_log.append((time.time(), member_name, text))
            self.roast_count_per_user[member_id] = self.roast_count_per_user.get(member_id, 0) + 1
            self.last_roast_time = time.time()
            self.save_data()
            return True
        except Exception as e:
            print(f"Custom roast error: {e}")
            return False

    async def send_free_message(self, text: str):
        ch = self.get_channel(MAIN_CHANNEL_ID)
        if not ch and self.guilds:
            ch = self.guilds[0].system_channel
        if not ch: return False
        try:
            await ch.send(text)
            return True
        except Exception as e:
            return False

    def change_interval(self, min_minutes: int, max_minutes: int):
        self.roast_interval_min = max(30, min(min_minutes, 600))
        self.roast_interval_max = max(self.roast_interval_min, min(max_minutes, 720))
        return self.roast_interval_min, self.roast_interval_max

    async def toggle_roast_loop(self):
        if self.roast_loop.is_running():
            self.roast_loop.cancel()
            return False
        else:
            self.roast_loop.start()
            return True

    @tasks.loop(hours=2)
    async def roast_loop(self):
        await self.force_random_roast()

    @tasks.loop(minutes=60)
    async def daily_report_loop(self):
        current_utc_hour = time.gmtime().tm_hour
        if current_utc_hour != 1:  # 4am Saudi
            return
        ch = self.get_channel(MAIN_CHANNEL_ID)
        if not ch and self.guilds:
            ch = self.guilds[0].system_channel
        if not ch: return

        lines = []
        for uid, mins in self.daily_stats.items():
            for g in self.guilds:
                m = g.get_member(uid)
                if m:
                    lines.append(f"{m.display_name}: {mins} دقيقة سهر")
                    break

        stats_text = "\n".join(lines) if lines else "الكل نايم بدري ومسوي صحي!"
        prompt = f"أنت مستر ذبات. اكتب تقرير مسائي ساخر جداً بعامية سعودية شبابية عن هؤلاء السهرانين:\n{stats_text}\n3 أسطر، طقطقة بدون رحمة."
        try:
            resp = await generate_content_ai(contents=prompt)
            await ch.send(f"📊 **تقرير الفضائح الليلي 🌙**\n\n{resp.text.strip()}")
        except Exception as e:
            print(f"Report error: {e}")
        self.daily_stats.clear()

    # ─── On Message (Images & Chat) ───────────────────────────────────────────

    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content.strip()

        if message.guild:
            self.server_memory.setdefault(message.guild.id, [])
            self.server_memory[message.guild.id].append(f"{message.author.display_name}: {content}")
            self.server_memory[message.guild.id] = self.server_memory[message.guild.id][-40:]

        # ذبات الصور (Vision)
        mentioned = self.user in message.mentions
        starts_with_look = content.startswith("!شوف") or content.startswith("بوت شوف")
        if message.attachments and (mentioned or starts_with_look):
            for att in message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    prompt = (
                        "أنت 'مستر ذبات'، شخصيتك طقطوقي سعودي لاذع. "
                        "قام المستخدم برفع هذه الصورة لك لتعلق عليها. "
                        "حلل تفاصيل الصورة بدقة واقصف جبهة صاحبها بأسلوب سعودي مضحك جداً وبدون مقدمات."
                    )
                    try:
                        img_bytes = await att.read()
                        part = types.Part.from_bytes(data=img_bytes, mime_type=att.content_type)
                        async with message.channel.typing():
                            resp = await generate_content_ai(contents=[prompt, part])
                            roast_text = resp.text.strip()
                            await message.reply(roast_text)
                            self.roast_log.append((time.time(), message.author.display_name, roast_text))
                            self.roast_count_per_user[message.author.id] = self.roast_count_per_user.get(message.author.id, 0) + 1
                            self.save_data()
                    except Exception as e:
                        await message.reply("ما قدرت أشوف الصورة زين، شكلها مصورة بكاميرا ساهر!")
                    return

        await self.process_commands(message)


# ─── Bot Instance ─────────────────────────────────────────────────────────────

bot = RoastBot()


# ─── Discord Slash Commands ───────────────────────────────────────────────────

@bot.tree.command(name="roast", description="🎯 إطلاق ذبة ذكية موجهة على عضو")
@app_commands.describe(
    member="العضو المستهدف للجلد",
    topic="موضوع الذبة أو سبب القصف (اختياري)",
    dialect="اختر اللهجة المطلوبة للذبة",
    intensity="مستوى القوة من 1 (خفيف) إلى 5 (إبادة نووية)"
)
@app_commands.choices(dialect=[
    app_commands.Choice(name="⚡ عامية سعودية معاصرة", value="default"),
    app_commands.Choice(name="🇸🇦 لهجة الرياض / نجدية", value="riyadh"),
    app_commands.Choice(name="🌴 لهجة جدة / حجازية", value="jeddah"),
    app_commands.Choice(name="🌾 لهجة القصيم", value="qassim")
])
@app_commands.choices(intensity=[
    app_commands.Choice(name="1 - مداعبة خفيفة 😊", value=1),
    app_commands.Choice(name="2 - طقطقة ودية 😉", value=2),
    app_commands.Choice(name="3 - متوازنة وذكية 🎯", value=3),
    app_commands.Choice(name="4 - قوية وحارة 🔥", value=4),
    app_commands.Choice(name="5 - قصف نووي بدون رحمة 💥💀", value=5)
])
async def cmd_roast(
    interaction: discord.Interaction,
    member: discord.Member,
    topic: str = None,
    dialect: app_commands.Choice[str] = None,
    intensity: app_commands.Choice[int] = None
):
    await interaction.response.defer()
    d_val = dialect.value if dialect else bot.current_dialect
    i_val = intensity.value if intensity else 3

    roast = await bot.generate_roast_for_member(
        member,
        interaction.channel,
        custom_topic=topic,
        custom_intensity=i_val,
        custom_dialect=d_val
    )
    if roast:
        await interaction.followup.send(f"🚀 تم إطلاق الذبة على {member.mention} بنجاح!", ephemeral=True)
    else:
        await interaction.followup.send("❌ حدث خطأ أثناء تجهيز الذبة.", ephemeral=True)


@bot.tree.command(name="court", description="⚖️ فتح جلسة محاكمة علنية طارئة ضد عضو مع تصويت الأعضاء")
@app_commands.describe(
    defendant="المتهم المراد محاكمته",
    charge="التهمة الموجهة له (مثلاً: الصنم الأبدي، تخريب الرانك، ادعاء النوم)",
    dialect="اللهجة التي سيحكم بها رئيس المحكمة"
)
@app_commands.choices(dialect=[
    app_commands.Choice(name="⚡ عامية سعودية", value="default"),
    app_commands.Choice(name="🇸🇦 نجدية / الرياض", value="riyadh"),
    app_commands.Choice(name="🌴 حجازية / جدة", value="jeddah"),
    app_commands.Choice(name="🌾 قصيمية", value="qassim")
])
async def cmd_court(
    interaction: discord.Interaction,
    defendant: discord.Member,
    charge: str,
    dialect: app_commands.Choice[str] = None
):
    await interaction.response.defer()
    d_val = dialect.value if dialect else bot.current_dialect

    indictment_data = await bot.roast_engine.generate_trial_indictment(defendant.display_name, charge, dialect=d_val)
    
    embed = discord.Embed(
        title=f"⚖️ {indictment_data.get('title', 'محكمة السيرفر العليا')}",
        description=f"**المتهم في قفص الاتهام:** {defendant.mention}\n**التهمة المنسوبة إليه:** {charge}\n\n📜 **لائحة الادعاء:**\n{indictment_data.get('indictment', '')}\n\n⚖️ **العقوبة المقترحة:**\n{indictment_data.get('penalty', '')}",
        color=0xff2a5f
    )
    embed.set_thumbnail(url=defendant.display_avatar.url)
    embed.set_footer(text="التصويت مفتوح لمدة 90 ثانية • صوت بالأزرار بالأسفل")

    view = CourtVoteView(defendant.id, defendant.display_name, charge, bot)
    await interaction.followup.send(content=f"🚨 **محاكمة علنية طارئة ضد {defendant.mention}!**", embed=embed, view=view)


@bot.tree.command(name="shamecard", description="🎴 إصدار بطاقة العار الرسمية الرقمية لعضو")
@app_commands.describe(
    member="العضو المطلوب إصدار بطاقة العار له",
    dialect="اللهجة المكتوبة بها بطاقة العار"
)
async def cmd_shamecard(interaction: discord.Interaction, member: discord.Member, dialect: str = "default"):
    await interaction.response.defer()
    card_data = bot.dossier_mgr.get_shame_card_data(member.id, member.display_name, str(member.display_avatar.url))
    
    # توليد الذبة لبطاقة العار
    roast_prompt = f"أنت مستr ذبات. اكتب ذبة لبطاقة العار الرسمية للعضو '{member.display_name}' عن جريمته '{card_data.get('crime')}'. سطر واحد قوي جداً بلهجة {dialect}."
    try:
        resp = await generate_content_ai(contents=roast_prompt)
        roast_txt = resp.text.strip()
    except Exception:
        roast_txt = f"أشهر تصريفاته: {card_data.get('top_excuse')}"

    svg_code = bot.roast_engine.generate_shame_card_svg(card_data, roast_txt, DIALECTS.get(dialect, DIALECTS['default'])['badge'])
    file_bytes = io.BytesIO(svg_code.encode("utf-8"))
    discord_file = discord.File(file_bytes, filename=f"shame_card_{member.id}.svg")

    embed = discord.Embed(
        title=f"🎴 بطاقة العار الرسمية: {member.display_name}",
        description=f"**اللقب:** {card_data.get('title')}\n**التهمة:** {card_data.get('crime')}\n\n**الإحصائيات الساخرة:**\n• نسبة التصريف: `{card_data['stats']['excuses']}%`\n• دقة الإيم: `{card_data['stats']['aim']}%`\n• معدل النكبة: `{card_data['stats']['choke']}%`\n• ساعات النوم: `{card_data['stats']['sleep']} ساعة`\n\n🎯 **الحكم:**\n\"{roast_txt}\"",
        color=0xa855f7
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.followup.send(file=discord_file, embed=embed)


@bot.tree.command(name="battle", description="⚔️ بدء حلبة تحدي ذبات بين عضوين مع تحكيم الذكاء الاصطناعي")
@app_commands.describe(
    opponent1="المتحدي الأول",
    opponent2="المتحدي الثاني",
    topic="موضوع المعركة (اختياري)"
)
async def cmd_battle(interaction: discord.Interaction, opponent1: discord.Member, opponent2: discord.Member, topic: str = "تحدي حر"):
    await interaction.response.defer()
    prompt = f"""
أنت حكم حلبة الذبات الأسطوري.
اكتب جولة افتتاحية مستفزة وحماسية لمعركة ذبات بين:
1. {opponent1.display_name}
2. {opponent2.display_name}
موضوع النزاع: {topic}
أسلوب معلق مصارعة سعودي فكاهي ومولع، سطرين. اطلب من كل واحد يرمي ذبته الآن!
"""
    resp = await generate_content_ai(contents=prompt)
    await interaction.followup.send(f"⚔️ **حلبة مصارعة الذبات 1v1** ⚔️\n\n**{opponent1.mention} ضد {opponent2.mention}**\nالموضوع: {topic}\n\n{resp.text.strip()}\n\n🔔 كل متسابق يكتب ذبته في الشات الآن والحكم بيفصل بينكم!")


@bot.tree.command(name="dialect", description="🗣️ تغيير اللهجة التلقائية للبوت")
@app_commands.describe(dialect="اختر اللهجة الجديدة")
@app_commands.choices(dialect=[
    app_commands.Choice(name="⚡ عامية سعودية عامة (Default)", value="default"),
    app_commands.Choice(name="🇸🇦 لهجة الرياض / نجدية", value="riyadh"),
    app_commands.Choice(name="🌴 لهجة جدة / حجازية", value="jeddah"),
    app_commands.Choice(name="🌾 لهجة القصيم", value="qassim")
])
async def cmd_dialect(interaction: discord.Interaction, dialect: app_commands.Choice[str]):
    bot.current_dialect = dialect.value
    bot.save_data()
    d_name = DIALECTS[dialect.value]["name"]
    await interaction.response.send_message(f"✅ تم تحويل لهجة مستر ذبات الرسمية إلى: **{d_name}** 🗣️")


# ─── Decoupled Lifecycle & Supervisor ─────────────────────────────────────────

async def run_discord_bot(bot_instance, token: str, shutdown_event: asyncio.Event):
    """
    Supervised Discord bot runner with automatic reconnection,
    exponential backoff, and shielded exception handling.
    Keeps the Discord client lifecycle isolated from the web server.
    """
    if not token:
        logger.warning("DISCORD_TOKEN is missing. Bot disabled; running in Web Command Center degraded mode.")
        return

    reconnect_delay = 5
    max_reconnect_delay = 60

    while not shutdown_event.is_set():
        try:
            logger.info("Initiating connection to Discord Gateway...")
            await bot_instance.start(token)
            # Normal shutdown if start returns cleanly
            break
        except discord.errors.LoginFailure as e:
            logger.critical(f"Fatal Discord login failure (invalid token): {e}. Bot disabled; web server remains active.")
            break
        except (discord.errors.PrivilegedIntentsRequired, discord.errors.GatewayNotFound) as e:
            logger.critical(f"Fatal Discord gateway/intent configuration error: {e}. Bot disabled; web server remains active.")
            break
        except (discord.DiscordException, aiohttp.ClientError, asyncio.TimeoutError, ConnectionError, OSError) as e:
            if shutdown_event.is_set():
                break
            logger.warning(f"Discord connection dropped ({type(e).__name__}: {e}). Reconnecting in {reconnect_delay}s...")
            try:
                await bot_instance.close()
            except Exception:
                pass
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
        except asyncio.CancelledError:
            logger.info("Discord bot task cancelled.")
            break
        except Exception as e:
            if shutdown_event.is_set():
                break
            logger.error(f"Unexpected exception in Discord bot task: {e}. Retrying in {reconnect_delay}s...", exc_info=True)
            try:
                await bot_instance.close()
            except Exception:
                pass
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


async def main():
    """
    Primary decoupled application entry point.
    Guarantees web server availability regardless of Discord Gateway status.
    """
    shutdown_event = asyncio.Event()

    # 1. Setup OS Signal Handlers (SIGINT / SIGTERM)
    loop = asyncio.get_running_loop()
    def _signal_handler():
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, AttributeError):
            try:
                signal.signal(sig, lambda s, f: _signal_handler())
            except Exception:
                pass

    # 2. Launch Web Server (Resilient Background Server)
    runner, site, bound_port = await start_web_server(bot)
    if bound_port:
        logger.info(f"Web Command Center active on port {bound_port} (Health routes: /health, /api/health)")
    else:
        logger.warning("Web server failed to bind; running in headless mode.")

    # 3. Launch Discord Bot Supervisor Task
    bot_task = asyncio.create_task(
        run_discord_bot(bot, DISCORD_TOKEN, shutdown_event),
        name="DiscordBotSupervisor"
    )

    # 4. Await Shutdown Signal
    try:
        await shutdown_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Manual termination requested.")
    finally:
        logger.info("Commencing graceful teardown sequence...")

        # Cancel and close bot
        if not bot_task.done():
            bot_task.cancel()
            try:
                await asyncio.wait_for(bot_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if not bot.is_closed():
            try:
                await asyncio.wait_for(bot.close(), timeout=5.0)
            except Exception as e:
                logger.warning(f"Error closing Discord bot: {e}")

        # Cleanup web server
        if runner:
            try:
                await asyncio.wait_for(runner.cleanup(), timeout=5.0)
                logger.info("Web server runner cleaned up successfully.")
            except Exception as e:
                logger.warning(f"Error cleaning up web runner: {e}")

        logger.info("Mr. Roast 3.0 shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass