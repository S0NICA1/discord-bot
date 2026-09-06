"""
tests/test_ai_service.py - Comprehensive Unit Tests for Resilient Gemini Flash High Thinking AI Service
Covers:
1. Thread-safe Client Singleton & reset
2. Exponential Backoff & Jitter on HTTP 429
3. Transient 503 Recovery
4. Quota Exhaustion Fallback (Saudi dialect text)
5. Missing API Key Fallback
6. Structured Pydantic Generation
7. Structured AI Fallback on Failure
8. Markdown Fence Stripping
9. GeminiService Contract 2 Verification
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors
from pydantic import BaseModel

from modules.ai_service import (
    AIResponse,
    BattleJudgementSchema,
    ComparativeRoastSchema,
    CourtIndictmentSchema,
    GeminiService,
    IntelReportSchema,
    SAUDI_ROAST_FALLBACKS,
    ShameCardMetadataSchema,
    clean_json_markdown,
    generate_content_ai,
    generate_structured_ai,
    gemini_service,
    get_genai_client,
    is_transient_error,
    reset_genai_client,
    retry_with_backoff,
)


# ─── 1. Singleton Client & Reset ──────────────────────────────────────────────

def test_singleton_client_lifecycle():
    """Verify get_genai_client returns the identical singleton instance until reset."""
    reset_genai_client()
    try:
        c1 = get_genai_client("dummy_test_key_1")
        c2 = get_genai_client("dummy_test_key_2")
        assert c1 is c2

        reset_genai_client()
        c3 = get_genai_client("dummy_test_key_3")
        assert c3 is not c1
    finally:
        reset_genai_client()


# ─── 2. Exponential Backoff & Jitter on 429 ───────────────────────────────────

@pytest.mark.asyncio
async def test_retry_backoff_on_429():
    """Verify @retry_with_backoff retries transient 429 ClientError and recovers."""
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01, jitter_min=0.001, jitter_max=0.005)
    async def simulated_api():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        return "SUCCESS"

    result = await simulated_api()
    assert result == "SUCCESS"
    assert call_count == 3


# ─── 3. Transient 503 Server Error Recovery ───────────────────────────────────

@pytest.mark.asyncio
async def test_transient_503_server_recovery():
    """Verify @retry_with_backoff handles 503 ServerError and succeeds on next attempt."""
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01, jitter_min=0.001, jitter_max=0.005)
    async def simulated_server_call():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise errors.ServerError(503, {"error": {"message": "Service Unavailable"}})
        return "RECOVERED"

    result = await simulated_server_call()
    assert result == "RECOVERED"
    assert call_count == 2


# ─── 4. Quota Exhaustion Fallback ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_exhaustion_fallback():
    """Verify persistent errors return authentic Saudi fallback without crashing."""
    client = get_genai_client()
    mock_fail = AsyncMock(side_effect=errors.ClientError(429, {"error": {"message": "Quota Exhausted"}}))
    with patch.object(client.aio.models, "generate_content", mock_fail):
        resp = await generate_content_ai("اذب عليه", allow_fallback=True)
        assert isinstance(resp, AIResponse)
        assert resp.is_fallback is True
        assert any(fallback in resp.text for fallback in SAUDI_ROAST_FALLBACKS)


# ─── 5. Missing API Key Fallback ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_api_key_fallback(monkeypatch):
    """Verify missing GEMINI_API_KEY returns Saudi fallback gracefully."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    resp = await generate_content_ai("وين الذبة؟", allow_fallback=True)
    assert isinstance(resp, AIResponse)
    assert resp.is_fallback is True
    assert any(fb in resp.text for fb in SAUDI_ROAST_FALLBACKS)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        await generate_content_ai("وين الذبة؟", allow_fallback=False)


# ─── 6. Structured Generation with Pydantic ───────────────────────────────────

@pytest.mark.asyncio
async def test_structured_pydantic_generation():
    """Verify generate_structured_ai returns a validated Pydantic model instance."""
    mock_payload = {
        "title": "قضية رقم 404 - جناية الصنم الأبدي",
        "indictment": "المتهم مسوي ميوت وساحب على الشباب",
        "penalty": "الجلد الساخر الفوري"
    }

    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_payload, ensure_ascii=False)

    client = get_genai_client()
    with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
        result = await generate_structured_ai(
            contents="صغ لائحة اتهام",
            schema=CourtIndictmentSchema,
            model_name="gemini-flash-latest"
        )
        assert isinstance(result, CourtIndictmentSchema)
        assert result.title == mock_payload["title"]
        assert result.indictment == mock_payload["indictment"]
        assert result.penalty == mock_payload["penalty"]


# ─── 7. Structured AI Fallback on Failure ─────────────────────────────────────

@pytest.mark.asyncio
async def test_structured_ai_fallback_on_failure():
    """Verify structured generation returns default_fallback if API call fails."""
    default_court = {
        "title": "محاكمة طوارئ",
        "indictment": "المتهم غائب ومتخاذل",
        "penalty": "العار الأبدي"
    }

    client = get_genai_client()
    with patch.object(client.aio.models, "generate_content", AsyncMock(side_effect=RuntimeError("API Timeout"))):
        fallback_res = await generate_structured_ai(
            contents="محاكمة",
            schema=CourtIndictmentSchema,
            default_fallback=default_court
        )
        assert fallback_res == default_court


# ─── 8. Markdown Fence Stripping ──────────────────────────────────────────────

def test_markdown_fence_stripping():
    """Verify clean_json_markdown strips json fences, raw fences, and surrounding whitespace."""
    raw_json = '```json\n{"default": "ذبة عامية", "riyadh": "ذبة نجدية"}\n```'
    cleaned = clean_json_markdown(raw_json)
    assert cleaned == '{"default": "ذبة عامية", "riyadh": "ذبة نجدية"}'

    raw_plain = '```\n{"ok": true}\n```'
    assert clean_json_markdown(raw_plain) == '{"ok": true}'

    already_clean = '{"status": "ok"}'
    assert clean_json_markdown(already_clean) == '{"status": "ok"}'


# ─── 9. GeminiService Contract 2 Verification ─────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_service_contract():
    """Verify GeminiService satisfies Interface Contract 2 in PROJECT.md."""
    service = GeminiService(model_name="gemini-flash-latest")

    # 1. generate_roast with context
    mock_resp = MagicMock()
    mock_resp.text = "يا رجال وش وضعك تسوقها؟"
    with patch("modules.ai_service.generate_content_ai", AsyncMock(return_value=mock_resp)):
        roast = await service.generate_roast(
            prompt="اجلده",
            system_instruction="كن ساخراً",
            context={"crime": "AFK", "minutes": 40}
        )
        assert roast == "يا رجال وش وضعك تسوقها؟"

    # 2. generate_structured
    mock_dict = {"default": "ذبة 1", "riyadh": "ذبة 2", "jeddah": "ذبة 3", "qassim": "ذبة 4"}
    with patch("modules.ai_service.generate_structured_ai", AsyncMock(return_value=mock_dict)):
        structured = await service.generate_structured(
            prompt="مقارنة",
            schema=ComparativeRoastSchema
        )
        assert structured["default"] == "ذبة 1"
        assert structured["riyadh"] == "ذبة 2"
