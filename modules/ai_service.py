"""
modules/ai_service.py - Unified AI Generation Service
Decoupled from bot lifecycle and web presentation layers.
"""
import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("mr_roast.ai_service")

MODEL_NAME = "gemini-flash-latest"


def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)


async def generate_content_ai(contents, system_instruction=None):
    """
    Generate content using Gemini Flash with High Thinking and Google Search tool,
    falling back to thinking-only mode if search fails.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is missing. AI generation unavailable.")
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = get_genai_client()
    try:
        cfg = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction=system_instruction,
        )
        return await client.aio.models.generate_content(
            model=MODEL_NAME, contents=contents, config=cfg
        )
    except Exception as e:
        logger.warning(f"Generation with search tool failed ({e}), retrying with thinking only...")
        cfg_fallback = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
            system_instruction=system_instruction,
        )
        return await client.aio.models.generate_content(
            model=MODEL_NAME, contents=contents, config=cfg_fallback
        )
