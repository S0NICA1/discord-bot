import discord
import logging
import asyncio
from config import DISCORD_TOKEN
from modules.listener import start_listening, stop_listening
from modules.transcriber import load_model as load_whisper
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord
from modules.web import start_web_server

# Logging setup — INFO for normal use, DEBUG for troubleshooting
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TonyBot")
# Quiet down noisy loggers
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Intents configuration required by Pycord
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True  # Required for guild.get_member() to work

bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Start the web dashboard server
    bot.loop.create_task(start_web_server(bot))

    # Pre-load Whisper model into memory on startup
    load_whisper()

    logger.info("Tony is ready!")

@bot.slash_command(name="join", description="Tony joins your current voice channel.")
async def join(ctx: discord.ApplicationContext):

    # Defer the response immediately so Discord doesn't timeout
    await ctx.defer()

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.followup.send("لازم تكون في روم صوتي عشان أدخل معاك!")
        return

    voice_channel = ctx.author.voice.channel

    # If already connected to a different channel, move
    if ctx.voice_client:
        if ctx.voice_client.channel.id == voice_channel.id:
            # Already connected and in the same channel — just start listening if not already
            if not ctx.voice_client.recording:
                start_listening(ctx.voice_client)
            await ctx.followup.send("أنا معك بالروم أصلاً يا ذكي!")
            return
        else:
            # Stop any existing recording before moving
            try:
                stop_listening(ctx.voice_client)
            except:
                pass
            await ctx.voice_client.move_to(voice_channel)
    else:
        try:
            await voice_channel.connect()
        except Exception as e:
            logger.error(f"Failed to connect to voice: {e}")
            await ctx.followup.send(f"ما قدرت أدخل الروم: {e}")
            return

    # Wait for the voice connection to fully establish
    vc = ctx.voice_client
    if vc:
        # Wait up to 10 seconds for the voice client to be connected
        for i in range(20):
            if vc.is_connected():
                break
            await asyncio.sleep(0.5)

        if not vc.is_connected():
            await ctx.followup.send("ما قدرت أتصل بالروم الصوتي، جرب مرة ثانية!")
            return

        # Small extra delay to let Pycord's internal state settle
        await asyncio.sleep(1)

        try:
            start_listening(vc)
            await ctx.followup.send(f"دخلت روم **{voice_channel.name}**! نادني بـ (يا توني) أو (Tony) و أنا بالخدمة. 🎙️")
        except Exception as e:
            logger.error(f"Failed to start listening: {e}")
            await ctx.followup.send(f"دخلت الروم بس ما قدرت أبدأ أسمع: {e}")
    else:
        await ctx.followup.send("صار خطأ غريب، ما لقيت الاتصال!")

@bot.slash_command(name="leave", description="Tony leaves the voice channel.")
async def leave(ctx: discord.ApplicationContext):
    await ctx.defer()

    if ctx.voice_client:
        try:
            stop_listening(ctx.voice_client)
        except:
            pass
        await ctx.voice_client.disconnect()
        await ctx.followup.send("يلا فمان الله 👋")
    else:
        await ctx.followup.send("أنا مو بأي روم صوتي أصلاً!")

@bot.slash_command(name="ask", description="Ask Tony a text question and he will reply with voice in VC.")
async def ask(ctx: discord.ApplicationContext, question: str):

    if not ctx.voice_client:
        await ctx.respond("لازم أكون متصل بالروم أول شيء! استخدم `/join`.", ephemeral=True)
        return

    await ctx.defer()

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, generate_response,
            ctx.guild.id, ctx.author.id, ctx.author.display_name, question
        )

        await speak_text_to_discord(ctx.guild.id, response, ctx.voice_client)

        await ctx.followup.send(f"سألت توني: **{question}**\n(توني بيرد عليك بالصوت بالروم 🎙️)")

    except Exception as e:
        logger.error(f"Error handling /ask command: {e}", exc_info=True)
        await ctx.followup.send("صار في مشكلة، معليش.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
