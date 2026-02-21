import discord
from discord.ext import commands, tasks
import os
from google import genai
from dotenv import load_dotenv
import random
import time
from dashboard_ui import DashboardView

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", 0))

# Configure Gemini
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3-flash-preview"
            
# Configure Intents
intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.presences = True
intents.message_content = True

class RoastBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.vc_join_times = {}  # Map user_id to join_timestamp
        self.last_roasted_user = None
        self.user_game_history = {} # Map user_id to set of played games

    async def setup_hook(self):
        await self.tree.sync()
        self.roast_loop.start()

    async def on_ready(self):
        print(f"Logged in as {self.user.name} ({self.user.id})")
        # Initialize join times for users already in VC when bot starts
        for guild in self.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        # افتراض إن الشخص جالس 30 دقيقة لو ما نعرف وقت دخوله
                        self.vc_join_times[member.id] = time.time() - 1800

    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        
        # Joined a voice channel
        if before.channel is None and after.channel is not None:
            self.vc_join_times[member.id] = time.time()
            self.user_game_history[member.id] = set()
        # Left a voice channel
        elif before.channel is not None and after.channel is None:
            if member.id in self.vc_join_times:
                del self.vc_join_times[member.id]
            if member.id in self.user_game_history:
                del self.user_game_history[member.id]

    async def on_presence_update(self, before, after):
        if after.bot: return
        if after.id in self.vc_join_times:
            if after.id not in self.user_game_history:
                self.user_game_history[after.id] = set()
            for activity in after.activities:
                if activity.type == discord.ActivityType.playing:
                    self.user_game_history[after.id].add(activity.name)

    async def generate_roast_for_member(self, member: discord.Member, channel: discord.TextChannel = None):
        if not channel:
            if MAIN_CHANNEL_ID:
                channel = self.get_channel(MAIN_CHANNEL_ID)
            else:
                channel = member.guild.system_channel
                if not channel and member.guild.text_channels:
                    channel = member.guild.text_channels[0]
                    
        if not channel:
            print("No text channel found to send the roast.")
            return

        join_time = self.vc_join_times.get(member.id, time.time() - 1800)
        minutes_in_vc = int((time.time() - join_time) / 60)
        
        if minutes_in_vc >= 60:
            hours = minutes_in_vc // 60
            mins = minutes_in_vc % 60
            if hours == 1:
                time_str = f"ساعة و {mins} دقيقة" if mins > 0 else "ساعة كاملة"
            elif hours == 2:
                time_str = f"ساعتين و {mins} دقيقة" if mins > 0 else "ساعتين كاملة"
            else:
                time_str = f"{hours} ساعات و {mins} دقيقة" if mins > 0 else f"{hours} ساعات"
        else:
            time_str = f"{minutes_in_vc} دقيقة"
        
        
        # 1. تحليل الوقت الفعلي (بتوقيت السعودية UTC+3)
        current_hour = (time.gmtime().tm_hour + 3) % 24
        time_context = ""
        if 2 <= current_hour <= 5:
            time_context = "الوقت الآن آخر الليل الفجر، المفروض نايم ووراه دوام أو مدرسة بس سهران زي البومة."
        elif 6 <= current_hour <= 11:
            time_context = "الوقت الآن الصبح بدري، الناس تداوم وتفطر وهو مبلط بالديسكورد."
        else:
            time_context = "جالس في نص اليوم."

        # 2. تحليل الألعاب وحالة التناقض
        current_game = None
        custom_status = None
        for activity in member.activities:
            if activity.type == discord.ActivityType.playing:
                current_game = activity.name
                if member.id in self.user_game_history:
                    self.user_game_history[member.id].add(activity.name)
            elif activity.type == discord.ActivityType.custom:
                custom_status = activity.name

        game_info = ""
        played_games = self.user_game_history.get(member.id, set())
        if current_game:
            game_info = f"ويلعب الآن {current_game}."
        elif len(played_games) > 1:
            game_info = f"ما يلعب شيء حالياً، بس تراه من دخل وهو يغير ألعابه (لعب {', '.join(played_games)}) كأنه يفر بالريموت مو لاقي لعبة تضفه."
        else:
            game_info = "بدون لعبة، مسنتر على الفاضي."

        contradiction_info = ""
        if custom_status and current_game:
            contradiction_info = f"تخيل إنه كاتب بحالته (Status) '{custom_status}'، ومع ذلك جالس يطقطق على {current_game}! تناقض غريب."

        # 3. تحليل الدفن والميوت والبث والروم كم فيه شخص
        mute_info = ""
        stream_info = ""
        alone_info = ""
        
        voice_state = member.voice
        vc_channel = voice_state.channel if voice_state else None
        
        if vc_channel and len(vc_channel.members) == 1:
            alone_info = "الأدهى والأمر إنه جالس بالروم لحـالـه! ماعنده أخويا أو محد معطيه وجه."

        if voice_state:
            if voice_state.self_stream:
                stream_info = "وفاتح بث (Stream) بالشاشة! "
                if vc_channel and len(vc_channel.members) == 1:
                    stream_info += "والمصيبة فاتح بث بالروم ومافي أي أحد يتابعه، يبث للجن المتابعينه!"
            
            if voice_state.self_deaf or voice_state.deaf:
                if minutes_in_vc >= 120 and not current_game:
                    mute_info = "يا ساتر! الرجال مسوي دفن (Deafen) للصوت والمايك له أكثر من سـاعتيـن ولا يلعب شيء! نايم على الكيبورد ولا متوفي؟"
                else:
                    mute_info = "ومسوي دفن (Deafen) للصوت والمايك، يعني وضعية الصنم والأصمخ."
            elif voice_state.self_mute or voice_state.mute:
                mute_info = "ومسوي ميوت (Mute) للمايك، مكمبر ما يتكلم."

        prompt = (
            f"أنت بوت ديسكورد واسمك 'مستر ذبات'، وشخصيتك شاب سعودي Gen Z (جيل زد) ذباته قوية وتضحك وتكسر الجبهة. "
            f"عندنا واحد بالديسكورد اسمه '{member.display_name}'.\n\n"
            f"--- معلومات الضحية ---\n"
            f"- مدة الجلوس: مبلط له {time_str}.\n"
            f"- الوقت الحالي للمستخدم: {time_context}\n"
            f"- الألعاب: {game_info}\n"
            f"- الحالة (Status): {contradiction_info}\n"
            f"- الصوت بالروم: {mute_info}\n"
            f"- البث: {stream_info}\n"
            f"- لحاله ولا معاه أحد؟: {alone_info}\n"
            f"----------------------\n\n"
            "المطلوب منك مستر ذبات:\n"
            "- امسح بكرامته الأرض بناءً على التناقضات اللي في حالته أو سهرانه العجيب أو جلسته لحاله أو البث الميت حقه.\n"
            "- استخدم مصطلحات الديسكورد والقيمنق السعودية (مثل: مكمبر، دفن، أصمخ، مسوي ميوت، طعس، سبك، يلعن أبو الجلوية، معرق، وضعية المزهرية، يبث للجدران).\n"
            "- الذبة لازم تكون سطر واحد أو سطرين بالكثير، عامية سعودية تيك توكر/تويتس بحتة تفطس وتستفز وتقهر.\n"
            "- لا تعطيه أي نصيحة، بس طقطق عليه.\n"
            "- لا تكتب أي مقدمات أو شرح (زي 'إليك الذبة' أو غيره)، فقط الذبة اللكمة بالصميم!"
        )
        
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )
            roast_text = response.text.strip()
            
            await channel.send(f"<@{member.id}> {roast_text}")
            self.last_roasted_user = member.id
            
        except Exception as e:
            print(f"Error generating roast via Gemini API: {e}")

    async def force_random_roast(self, channel: discord.TextChannel = None):
        eligible_members = []
        for guild in self.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        if channel:
                            target_channel = channel
                        elif MAIN_CHANNEL_ID:
                            target_channel = self.get_channel(MAIN_CHANNEL_ID)
                        else:
                            target_channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)
                        if target_channel:
                            eligible_members.append((member, target_channel))
        
        if not eligible_members:
            if channel:
                await channel.send("ما فيه أحد بالفويس عشان أذب عليه!")
            return
            
        # Anti-spam logic: exclude the last roasted user if possible
        if len(eligible_members) > 1:
            eligible_members_no_spam = [m for m in eligible_members if m[0].id != self.last_roasted_user]
            if eligible_members_no_spam:
                eligible_members = eligible_members_no_spam
            
        selected_member, target_channel = random.choice(eligible_members)
        await self.generate_roast_for_member(selected_member, target_channel)


    async def toggle_roast_loop(self):
        if self.roast_loop.is_running():
            self.roast_loop.cancel()
            return False
        else:
            self.roast_loop.start()
            return True

    @tasks.loop(minutes=30)
    async def roast_loop(self):
        # Random interval between 10 to 60 minutes for the next cycle
        self.roast_loop.change_interval(minutes=random.randint(10, 60))
        await self.force_random_roast()

    @roast_loop.before_loop
    async def before_roast_loop(self):
        await self.wait_until_ready()

bot = RoastBot()

@bot.tree.command(name="dashboard", description="Admin control panel for Mr. Dhabat")
async def dashboard(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
        
    # Generate the persistent UI View, passing our bot callbacks
    view = DashboardView(
        bot=bot, 
        toggle_loop_callback=bot.toggle_roast_loop, 
        force_roast_callback=bot.force_random_roast,
        generate_roast_callback=bot.generate_roast_for_member
    )
    
    await interaction.response.send_message("🕹️ **Mr. Dhabat Admin Control Panel**", view=view, ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GEMINI_API_KEY:
        print("Please set your DISCORD_TOKEN and GEMINI_API_KEY in the .env file")
    else:
        bot.run(DISCORD_TOKEN)
