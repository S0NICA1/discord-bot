import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient
import logging
import asyncio
from config import DISCORD_TOKEN
from modules.listener import start_listening, stop_listening
from modules.transcriber import load_model as load_whisper
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord, reset_guild_audio
from modules.web import start_web_server

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TonyBot")
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Sync slash commands globally
    try:
        synced = await tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Clean up any stale voice connections from previous runs
    for vc in list(bot.voice_clients):
        try:
            logger.info(f"Cleaning up stale voice connection in {vc.guild.name}...")
            await vc.disconnect(force=True)
        except Exception as e:
            logger.warning(f"Error cleaning up stale VC: {e}")

    # Start web dashboard
    bot.loop.create_task(start_web_server(bot))

    # Pre-load Whisper
    load_whisper()

    logger.info("Tony is ready!")


@tree.command(name="join", description="Tony joins your current voice channel.")
async def join(interaction: discord.Interaction):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("لازم تكون في روم صوتي عشان أدخل معاك!")
        return

    voice_channel = interaction.user.voice.channel
    guild = interaction.guild

    # Force-disconnect any existing stale voice client
    vc_existing = guild.voice_client
    if vc_existing:
        try:
            stop_listening(vc_existing)
        except:
            pass
        try:
            await vc_existing.disconnect(force=True)
        except:
            pass
        await asyncio.sleep(2)

    # Connect using VoiceRecvClient which supports DAVE E2EE via davey
    try:
        vc = await voice_channel.connect(cls=VoiceRecvClient, reconnect=True, timeout=20.0)
    except Exception as e:
        logger.error(f"Failed to connect to voice: {e}", exc_info=True)
        await interaction.followup.send(f"ما قدرت أدخل الروم: {e}")
        return

    # Wait for voice to be fully connected
    for _ in range(40):  # up to 20 seconds
        if vc.is_connected():
            break
        await asyncio.sleep(0.5)

    if not vc.is_connected():
        await interaction.followup.send("ما قدرت أتصل بالروم الصوتي، جرب مرة ثانية!")
        try:
            await vc.disconnect(force=True)
        except:
            pass
        return

    # Let internals settle
    await asyncio.sleep(1.5)

    # Reset any stale audio worker for this guild
    reset_guild_audio(interaction.guild.id)
    await asyncio.sleep(0.5)

    try:
        start_listening(vc)
        await interaction.followup.send(
            f"دخلت روم **{voice_channel.name}**! نادني بـ (يا توني) أو (Tony) و أنا بالخدمة. 🎙️"
        )
        logger.info(f"Successfully joined and started listening in {voice_channel.name}")
    except Exception as e:
        logger.error(f"Failed to start listening: {e}", exc_info=True)
        await interaction.followup.send(f"دخلت الروم بس ما قدرت أبدأ أسمع: {e}")


@tree.command(name="leave", description="Tony leaves the voice channel.")
async def leave(interaction: discord.Interaction):
    await interaction.response.defer()

    vc = interaction.guild.voice_client
    if vc:
        try:
            stop_listening(vc)
        except:
            pass
        await vc.disconnect(force=True)
        await interaction.followup.send("يلا فمان الله 👋")
    else:
        await interaction.followup.send("أنا مو بأي روم صوتي أصلاً!")


@tree.command(name="ask", description="Ask Tony a text question and he will reply with voice in VC.")
@app_commands.describe(question="السؤال اللي تبي تسأله")
async def ask(interaction: discord.Interaction, question: str):
    # Defer FIRST before anything else to beat the 3-second timeout
    await interaction.response.defer()

    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.followup.send("لازم أكون متصل بالروم أول شيء! استخدم `/join`.")
        return

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, generate_response,
            interaction.guild.id, interaction.user.id, interaction.user.display_name, question
        )
        await speak_text_to_discord(interaction.guild.id, response, vc)
        await interaction.followup.send(
            f"سألت توني: **{question}**\n(توني بيرد عليك بالصوت بالروم 🎙️)"
        )
    except Exception as e:
        logger.error(f"Error handling /ask command: {e}", exc_info=True)
        await interaction.followup.send("صار في مشكلة، معليش.")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
