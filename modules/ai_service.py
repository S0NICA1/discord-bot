"""
modules/ai_service.py - Resilient Gemini Flash High Thinking AI Service (R2)
Decoupled from bot lifecycle and web presentation layers.
Implements:
1. Thread-safe genai.Client singleton with reset capability.
2. Exponential backoff retry with randomized jitter for 429/503/network transients.
3. ThinkingConfig(thinking_level="HIGH") with automatic search-to-thinking fallback.
4. Authentic Saudi dialect comedic fallback repository & duck-typed AIResponse.
5. Pydantic structured schemas & schema-enforced generation with markdown fence stripping.
6. GeminiService class matching Interface Contract 2 in PROJECT.md.
"""

import asyncio
import json
import logging
import os
import random
import re
import threading
from typing import Any, Callable, Optional, Type, Union

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

logger = logging.getLogger("mr_roast.ai_service")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
MODEL_NAME = DEFAULT_MODEL  # Backward compatibility alias

_client_lock = threading.Lock()
_client_instance: Optional[genai.Client] = None


# ──────────────────────────────────────────────────────────────────────────────
# 1. Thread-Safe Client Singleton
# ──────────────────────────────────────────────────────────────────────────────

def get_genai_client(api_key: Optional[str] = None) -> genai.Client:
    """Thread-safe singleton factory for google.genai.Client."""
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                key = api_key or os.getenv("GEMINI_API_KEY")
                if not key:
                    logger.warning("GEMINI_API_KEY is not configured.")
                    raise ValueError("GEMINI_API_KEY is not configured")
                _client_instance = genai.Client(api_key=key)
    return _client_instance


def reset_genai_client() -> None:
    """Resets the singleton client instance (used for hermetic tests & credential rotation)."""
    global _client_instance
    with _client_lock:
        _client_instance = None


# ──────────────────────────────────────────────────────────────────────────────
# 2. Exponential Backoff & Jitter Error Handling
# ──────────────────────────────────────────────────────────────────────────────

def is_transient_error(exc: Exception) -> bool:
    """Identifies transient HTTP 429 (Resource Exhausted), 503/5xx (Server Error), or network disconnects."""
    if isinstance(exc, errors.ClientError):
        code = getattr(exc, "code", None)
        return code == 429 or "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
    if isinstance(exc, errors.ServerError):
        return True  # Any 5xx error is transient
    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        return code in (429, 500, 502, 503, 504) or "429" in str(exc) or "503" in str(exc)

    transient_types = (
        asyncio.TimeoutError,
        TimeoutError,
        ConnectionError,
        ConnectionResetError,
    )
    if isinstance(exc, transient_types):
        return True

    exc_name = type(exc).__name__
    if "ClientError" in exc_name or "HTTPError" in exc_name or "Timeout" in exc_name:
        return True
    return False


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter_min: float = 0.1,
    jitter_max: float = 0.5,
):
    """
    Decorator for async coroutines providing exponential backoff with jitter on transient errors.
    Delays:
      Attempt 1: 1.0s + jitter
      Attempt 2: 2.0s + jitter
      Attempt 3: 4.0s + jitter
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    if not is_transient_error(exc) or retries >= max_retries:
                        logger.error(f"Execution failed after {retries} retries with error: {exc}")
                        raise
                    delay = (initial_delay * (backoff_factor ** retries)) + random.uniform(jitter_min, jitter_max)
                    retries += 1
                    logger.warning(
                        f"Transient error ({exc}). Retrying attempt {retries}/{max_retries} in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# 3. Saudi Dialect Comedic Fallback Repository & Duck-Typed Response
# ──────────────────────────────────────────────────────────────────────────────

SAUDI_ROAST_FALLBACKS = [
    "متكي بالروم وصنم كأنك بطارية ريموت مخلصة من سنتين.. لا حس ولا خبر وش جوك بالله؟",
    "مسوي فيها مركز وثقيل وآخرتها كل ما دخلت قيم طلعت بنتيجة تفشل.. روقنا وعط الماوس لغيرك!",
    "والله من كثر ما سواليفك كيس حتى النت بغى يفصل من الصدمة.. خف علينا شوي يا كابتن!",
    "داخل الفويس وساكت كأنك حارس أمن في بنك مقفل.. سولف وفكنا من الغموض اللي ماله داعي!",
    "متحمس ومسوي فيها محترف وكل لقطاتك عبارة عن انبطاح باللوبي.. ودنا نشوف فوز واحد بس للذكرى!"
]


class AIResponse:
    """Duck-typed response object matching google-genai response interface."""
    def __init__(self, text: str, is_fallback: bool = False, raw: Any = None):
        self._text = text
        self.is_fallback = is_fallback
        self.raw = raw

    @property
    def text(self) -> str:
        return self._text

    def __str__(self) -> str:
        return self._text


# ──────────────────────────────────────────────────────────────────────────────
# 4. Pydantic Structured Schemas
# ──────────────────────────────────────────────────────────────────────────────

class CourtIndictmentSchema(BaseModel):
    title: str
    indictment: str
    penalty: str


class BattleJudgementSchema(BaseModel):
    score1: float
    score2: float
    winner: str
    commentary: str
    knockout_punch: str


class ComparativeRoastSchema(BaseModel):
    default: str
    riyadh: str
    jeddah: str
    qassim: str


class ShameCardMetadataSchema(BaseModel):
    title: str
    crime: str
    top_excuse: str
    excuses_pct: int = 99
    aim_pct: int = 5
    choke_pct: int = 95
    sleep_hours: int = 1
    roast: str


class IntelReportSchema(BaseModel):
    title: str
    toxic_user: str
    quiet_user: str
    summary: str
    advice: str


# ──────────────────────────────────────────────────────────────────────────────
# 5. Core Generation Functions
# ──────────────────────────────────────────────────────────────────────────────

def clean_json_markdown(text: str) -> str:
    """Removes ```json ... ``` markdown fences and trims whitespace."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


async def generate_content_ai(
    contents: Any,
    system_instruction: Optional[str] = None,
    allow_fallback: bool = True,
    model_name: Optional[str] = None
) -> AIResponse:
    """
    Robust generation using Gemini Flash with High Thinking and retry backoff.
    Gracefully falls back to Saudi dialect excuses if API key is missing or calls fail.
    """
    model = model_name or DEFAULT_MODEL
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is missing. Providing authentic Saudi fallback.")
        if allow_fallback:
            return AIResponse(random.choice(SAUDI_ROAST_FALLBACKS), is_fallback=True)
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        client = get_genai_client(api_key)
    except Exception as e:
        logger.error(f"Failed to get genai client: {e}")
        if allow_fallback:
            return AIResponse(random.choice(SAUDI_ROAST_FALLBACKS), is_fallback=True)
        raise

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    async def _execute_call():
        # First attempt: High thinking + Google Search grounding tool
        try:
            cfg = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction=system_instruction,
            )
            return await client.aio.models.generate_content(
                model=model, contents=contents, config=cfg
            )
        except Exception as e:
            logger.info(f"Tool generation failed ({e}), falling back to pure thinking mode...")
            cfg_thinking_only = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                system_instruction=system_instruction,
            )
            return await client.aio.models.generate_content(
                model=model, contents=contents, config=cfg_thinking_only
            )

    try:
        res = await _execute_call()
        text = res.text if hasattr(res, "text") else str(res)
        return AIResponse(text or "", is_fallback=False, raw=res)
    except Exception as exc:
        logger.error(f"All AI generation attempts failed: {exc}")
        if allow_fallback:
            return AIResponse(random.choice(SAUDI_ROAST_FALLBACKS), is_fallback=True)
        raise


async def generate_structured_ai(
    contents: Any,
    schema: Union[Type[BaseModel], dict],
    system_instruction: Optional[str] = None,
    default_fallback: Optional[Union[dict, BaseModel]] = None,
    model_name: Optional[str] = None
) -> Any:
    """
    Executes JSON schema-enforced generation using Gemini Flash High Thinking.
    Validates output against Pydantic schema or returns clean fallback.
    """
    model = model_name or DEFAULT_MODEL
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        if default_fallback is not None:
            return default_fallback
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        client = get_genai_client(api_key)
    except Exception as e:
        logger.error(f"Failed to get genai client: {e}")
        if default_fallback is not None:
            return default_fallback
        raise

    is_pydantic = isinstance(schema, type) and issubclass(schema, BaseModel)
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema if is_pydantic else None,
        thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        system_instruction=system_instruction,
    )

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    async def _execute_structured():
        return await client.aio.models.generate_content(
            model=model, contents=contents, config=cfg
        )

    try:
        res = await _execute_structured()
        raw_text = res.text if hasattr(res, "text") else str(res)
        if (not raw_text or not raw_text.strip()) and default_fallback is not None:
            return default_fallback

        cleaned = clean_json_markdown(raw_text or "{}")
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        if is_pydantic:
            return schema.model_validate_json(cleaned)
        return json.loads(cleaned)
    except Exception as e:
        logger.error(f"Structured AI generation error ({e}). Returning fallback...")
        if default_fallback is not None:
            return default_fallback
        raise


# ──────────────────────────────────────────────────────────────────────────────
# 6. Interface Contract 2: GeminiService
# ──────────────────────────────────────────────────────────────────────────────

class GeminiService:
    """Unified Gemini Flash High Thinking service instance matching PROJECT.md Contract 2."""
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    async def generate_roast(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        context: Optional[dict] = None
    ) -> str:
        full_prompt = prompt
        if context:
            ctx_items = [f"- {k}: {v}" for k, v in context.items() if v]
            if ctx_items:
                full_prompt = "سياق الضحية:\n" + "\n".join(ctx_items) + f"\n\n{prompt}"
        resp = await generate_content_ai(
            contents=full_prompt,
            system_instruction=system_instruction,
            model_name=self.model_name
        )
        return resp.text.strip()

    async def generate_structured(
        self,
        prompt: str,
        schema: Union[Type[BaseModel], dict],
        default_fallback: Optional[Any] = None
    ) -> Any:
        return await generate_structured_ai(
            contents=prompt,
            schema=schema,
            default_fallback=default_fallback,
            model_name=self.model_name
        )


gemini_service = GeminiService()
