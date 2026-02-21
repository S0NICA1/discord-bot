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
MODEL_NAME = "gemini-3-pro-preview"

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
        # Left a voice channel
        elif before.channel is not None and after.channel is None:
            if member.id in self.vc_join_times:
                del self.vc_join_times[member.id]

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
        
        game_info = "بدون لعبة"
        for activity in member.activities:
            if activity.type == discord.ActivityType.playing:
                game_info = f"ويلعب الآن لعبة {activity.name}"
                break
                
        mute_info = ""
        voice_state = member.voice
        if voice_state:
            if voice_state.self_mute or voice_state.mute:
                mute_info = "ومسوي ميوت للصوت/المايك"
            if voice_state.self_deaf or voice_state.deaf:
                mute_info = "ومسوي ميوت وسماعة"

        prompt = (
            f"أنت خوينا في الديسكورد واسمك 'مستر ذبات'. اخويانا اسمه '{member.display_name}' "
            f"وقاعد في الروم الصوتي له {minutes_in_vc} دقيقة. {game_info}. {mute_info}. \n"
            "عطني ذبة أو طقطقة سعودية تضحك عليه وقصيرة جداً. ركز على اللعبة اللي يلعبها، أو إذا مسوي ميوت، "
            "أو قعدته الطويلة. مثال: 'داخل فويس ومسوي ميوت؟ وش تحرس بالضبط؟'. "
            "لا تكتب أي شيء غير الذبة نفسها، خلها عامية بحتة، تضحك وتمسح بكرامته الأرض."
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
