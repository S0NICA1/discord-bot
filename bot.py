import discord
import logging
from config import DISCORD_TOKEN
from modules.listener import start_listening, stop_listening
from modules.transcriber import load_model as load_whisper
from modules.brain import generate_response
from modules.speaker import speak_text_to_discord

# Basic logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TonyBot")

# Intents configuration required by Pycord
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Pre-load Whisper model into memory on startup
    load_whisper()
    
    logger.info("Tony is ready!")

@bot.slash_command(name="join", description="Tony joins your current voice channel.")
async def join(ctx: discord.ApplicationContext):
    
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond(" لازم تكون في روم صوتي عشان أدخل معاك!", ephemeral=True)
        return
        
    voice_channel = ctx.author.voice.channel
    
    # Check if Tony is already in a VC in this guild
    if ctx.voice_client:
        if ctx.voice_client.channel.id == voice_channel.id:
            await ctx.respond("أنا معك بالروم أصلاً يا ذكي!", ephemeral=True)
            return
        else:
            await ctx.voice_client.move_to(voice_channel)
    else:
        try:
            # Connect to the voice channel
            await voice_channel.connect()
        except Exception as e:
            logger.error(f"Failed to connect to voice: {e}")
            await ctx.respond(f"ما قدرت أدخل الروم: {e}", ephemeral=True)
            return

    await ctx.respond(f"دخلت روم **{voice_channel.name}**! نادني بـ (يا توني) أو (Tony) و أنا بالخدمة.")
    
    # Start the custom audio sink
    if ctx.voice_client:
        start_listening(ctx.voice_client)

@bot.slash_command(name="leave", description="Tony leaves the voice channel.")
async def leave(ctx: discord.ApplicationContext):
    if ctx.voice_client:
        # Stop listening gracefully
        stop_listening(ctx.voice_client)
        await ctx.voice_client.disconnect()
        await ctx.respond("يلا فمان الله 👋")
    else:
        await ctx.respond("أنا مو بأي روم صوتي أصلاً!", ephemeral=True)

@bot.slash_command(name="ask", description="Ask Tony a text question and he will reply with voice in VC.")
async def ask(ctx: discord.ApplicationContext, question: str):
    
    if not ctx.voice_client:
        await ctx.respond("لازم أكون متصل بالروم أول شيء! استخدم `/join`.", ephemeral=True)
        return
        
    # Preemptively acknowledge the command so Discord doesn't timeout
    await ctx.defer()
    
    try:
        # Send text straight to brain
        response = generate_response(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            user_name=ctx.author.display_name,
            text=question
        )
        
        # Tony speaks the text in the VC
        await speak_text_to_discord(ctx.guild.id, response, ctx.voice_client)
        
        # Follow up on original text interaction
        await ctx.followup.send(f"سألت توني: **{question}**\n(توني بيرد عليك بالصوت بالروم 🎙️)")
        
    except Exception as e:
        logger.error(f"Error handling /ask command: {e}")
        await ctx.followup.send("صار في مشكلة، معليش.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
