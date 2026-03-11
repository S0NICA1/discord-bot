import logging
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TEMPERATURE, TONY_PERSONA

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

def generate_response(guild_id: int, user_id: int, user_name: str, text: str) -> str:
    """Gets a response from Gemini using the guild's history and Tony's Persona."""
    
    if not client:
        logger.error("Gemini client is not initialized.")
        return "والله ما وصلني الإنترنت، عيد عليّ"

    history = get_history(guild_id)
    
    # Format the user's prompt to include their name for awareness
    formatted_prompt = f"[{user_name} talking to you]: {text}"
    
    try:
        # Instead of using a stateful chat object which might be harder to manage across async voice streams,
        # we manually pass the history and system instruction to generate_content.
        
        contents = history.copy()
        contents.append({"role": "user", "parts": [{"text": formatted_prompt}]})
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=TONY_PERSONA,
                temperature=GEMINI_TEMPERATURE,
            )
        )
        
        reply_text = response.text
        if not reply_text:
            raise ValueError("Empty response from Gemini")
            
        update_history(guild_id, formatted_prompt, reply_text)
        return reply_text
        
    except Exception as e:
        logger.error(f"Gemini generation error: {e}")
        return "والله ما وصلني الإنترنت، عيد عليّ"
