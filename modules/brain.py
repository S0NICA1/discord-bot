import logging
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_LEVEL, GEMINI_TOOLS
from modules.dialects import get_dialect_prompt
import modules.config_sync as config_sync

logger = logging.getLogger(__name__)

# Initialize Gemini Client
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Gemini Client: {e}")
    client = None

# In-memory storage for guild conversations
# Format: { guild_id: [ {"role": "user", "parts": [...]}, {"role": "model", "parts": [...]} ] }
chat_history = {}

# Black Book for roasts and quotes
black_book = {}

def get_history(guild_id: int):
    """Retrieve history for a guild, ensuring it doesn't exceed 20 messages."""
    if guild_id not in chat_history:
        # Initialize with the system prompt implicitly by starting empty.
        # The prompt will be injected as `system_instruction` in the generate call
        chat_history[guild_id] = []
    return chat_history[guild_id]

def update_history(guild_id: int, user_text: str, model_text: str):
    """Appends the latest interaction to the guild's memory."""
    history = get_history(guild_id)
    history.append({"role": "user", "parts": [{"text": user_text}]})
    history.append({"role": "model", "parts": [{"text": model_text}]})
    
    # Keep only the last 20 messages (each interaction is 2 messages, so keep last 10 pairs)
    if len(history) > 20:
        chat_history[guild_id] = history[-20:]

def generate_response(guild_id: int, user_id: int, user_name: str, text: str, vc_members_count: int = 1, afk_users: list = None, dialect: str = "default") -> str:
    """Gets a response from Gemini using the guild's history, Tony's Persona, and the chosen dialect."""
    
    if not afk_users:
        afk_users = []
        
    if not client:
        logger.error("Gemini client is not initialized.")
        return "والله ما وصلني الإنترنت، عيد عليّ"

    history = get_history(guild_id)
    config_sync.track_interaction(user_id)
    friendship_status = config_sync.get_friendship_status(user_id)
    
    import re
    
    # Calculate Riyadh Time (UTC+3)
    riyadh_time = datetime.utcnow() + timedelta(hours=3)
    time_str = riyadh_time.strftime("%I:%M %p")
    
    afk_str = f" | AFK Users: {', '.join(afk_users)}" if afk_users else ""
    
    # Add Black book context
    guild_quotes = black_book.get(guild_id, [])
    black_book_str = ""
    if guild_quotes:
        black_book_str = f" | Your Black Book of saved quotes to roast people: {'; '.join(guild_quotes)}"
    
    # Format the user's prompt to include context for spatial/temporal awareness
    formatted_prompt = f"[System Context -> Time: {time_str} | Users in Room: {vc_members_count}{afk_str}{black_book_str} | Friendship Hint: {friendship_status}] {user_name} says: {text}"
    
    dialect_instruction = get_dialect_prompt(dialect)
    full_persona = f"{config_sync.get_persona()}\n\n[تعليمات اللهجة الإجبارية: {dialect_instruction}]"

    try:
        contents = history.copy()
        contents.append({"role": "user", "parts": [{"text": formatted_prompt}]})
        
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=full_persona,
                    temperature=config_sync.get_temperature(),
                    thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                )
            )
        except Exception as search_err:
            logger.warning(f"Generation with search tool failed ({search_err}), retrying without search: {search_err}")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=full_persona,
                    temperature=config_sync.get_temperature(),
                    thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                )
            )
        
        reply_text = response.text
        if not reply_text:
            raise ValueError("Empty response from Gemini")
            
        # Parse for Black Book saves
        match = re.search(r"\[SAVE_QUOTE:\s*(.*?)\]", reply_text, flags=re.IGNORECASE)
        if match:
            quote = match.group(1).strip()
            if guild_id not in black_book:
                black_book[guild_id] = []
            black_book[guild_id].append(quote)
            # Remove the tag so Tony doesn't say it out loud
            reply_text = re.sub(r"\[SAVE_QUOTE:\s*.*?\]", "", reply_text, flags=re.IGNORECASE).strip()
            logger.info(f"Saved to Black Book: {quote}")
            
        update_history(guild_id, formatted_prompt, reply_text)
        return reply_text
        
    except Exception as e:
        logger.error(f"Gemini generation error: {e}")
        return "والله ما وصلني الإنترنت، عيد عليّ"
