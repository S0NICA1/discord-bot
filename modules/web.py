import os
import logging
from aiohttp import web
import modules.config_sync as config_sync
from modules.brain import chat_history

logger = logging.getLogger(__name__)

bot_instance = None # This will be set from bot.py

async def handle_status(request):
    """API endpoint returning bot status."""
    if not bot_instance:
        return web.json_response({"error": "Bot not initialized"}, status=500)
    
    guilds = [{"id": str(g.id), "name": g.name, "members": g.member_count} for g in bot_instance.guilds]
    active_voices = [
        {"guild": vc.guild.name, "channel": vc.channel.name} 
        for vc in bot_instance.voice_clients
    ]
    
    return web.json_response({
        "status": "online",
        "ping": round(bot_instance.latency * 1000),
        "guild_count": len(bot_instance.guilds),
        "guilds": guilds,
        "active_voices": active_voices
    })

async def handle_config_get(request):
    """API endpoint to get the current Tony configuration."""
    return web.json_response({
        "persona": config_sync.get_persona(),
        "temperature": config_sync.get_temperature()
    })

async def handle_config_post(request):
    """API endpoint to update the Tony configuration dynamically."""
    try:
        data = await request.json()
        
        if "persona" in data:
            config_sync.set_persona(data["persona"])
            
        if "temperature" in data:
            temp = float(data["temperature"])
            config_sync.set_temperature(temp)
            
        logger.info("Configuration updated via web dashboard.")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return web.json_response({"error": str(e)}, status=400)

async def handle_memory(request):
    """API endpoint to view the latest conversation memory of each server."""
    
    # We serialize the chat history so it can be viewed on the web
    memory_export = {}
    for guild_id, history in chat_history.items():
        guild_name = "Unknown"
        if bot_instance:
            guild = bot_instance.get_guild(guild_id)
            if guild:
                guild_name = guild.name
                
        # Format for the frontend
        formatted_history = []
        for msg in history:
            role = "Tony" if msg["role"] == "model" else "User"
            text = msg["parts"][0]["text"]
            formatted_history.append({"role": role, "text": text})
            
        memory_export[str(guild_id)] = {
            "name": guild_name,
            "messages": formatted_history
        }
        
    return web.json_response(memory_export)

async def start_web_server(bot, port=None):
    """Starts the aiohttp web server concurrently with the bot."""
    global bot_instance
    bot_instance = bot
    
    if port is None:
        port = int(os.environ.get("PORT", 8080))
        
    app = web.Application()
    
    # API Routes
    app.router.add_get('/api/status', handle_status)
    app.router.add_get('/api/config', handle_config_get)
    app.router.add_post('/api/config', handle_config_post)
    app.router.add_get('/api/memory', handle_memory)
    
    # Static files serving (the frontend SPA)
    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web')
    
    # Serve index.html at root
    async def index_handler(request):
        return web.FileResponse(os.path.join(web_dir, 'index.html'))
        
    app.router.add_get('/', index_handler)
    app.router.add_static('/', web_dir)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    logger.info(f"Starting web dashboard on port {port}...")
    await site.start()
