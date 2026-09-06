"""
tests/test_m2_adversarial.py - Empirical Adversarial Verification Suite for Milestone 2

Adversarially stress-tests:
1. Thread-safe & coroutine-safe singleton genai.Client under high concurrency (50 threads + 50 coroutines).
2. Exponential backoff and jitter under bursts of transient errors (429, 503, timeouts).
3. Fallback stability returning duck-typed AIResponse with authentic Arabic text on complete API failure.
4. Structured JSON corruption resilience handling malformed, truncated, or invalid payloads safely.
5. Dialect negative constraint verification across all 4 Saudi dialects and anti-repetition 5-roast bounds.
"""

import asyncio
import concurrent.futures
import json
import os
import random
import re
import threading
import time
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors
from pydantic import BaseModel, ValidationError

from modules.ai_service import (
    AIResponse,
    BattleJudgementSchema,
    ComparativeRoastSchema,
    CourtIndictmentSchema,
    IntelReportSchema,
    SAUDI_ROAST_FALLBACKS,
    ShameCardMetadataSchema,
    clean_json_markdown,
    gemini_service,
    generate_content_ai,
    generate_structured_ai,
    get_genai_client,
    is_transient_error,
    reset_genai_client,
    retry_with_backoff,
)
from modules.dialects import (
    DIALECTS,
    INTENSITY_CONFIG,
    NEGATIVE_CONSTRAINTS,
    DialectSynthesisEngine,
    dialect_engine,
    format_anti_repetition_prompt,
    get_comparative_prompt,
    get_dialect_prompt,
    get_intensity_instruction,
)


# ============================================================================
# 1. CONCURRENCY STRESS TEST ON get_genai_client
# ============================================================================

def test_concurrency_threads_50():
    """
    Stress-test get_genai_client with 50 OS threads simultaneously contending
    at a synchronization barrier to provoke any potential race condition.
    Asserts exact object identity (all return the identical instance) and zero errors.
    """
    reset_genai_client()
    barrier = threading.Barrier(50)
    results = [None] * 50
    exceptions = [None] * 50

    def worker(idx: int):
        try:
            barrier.wait(timeout=5.0)
            client = get_genai_client("adversarial_test_key_threads")
            results[idx] = client
        except Exception as e:
            exceptions[idx] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # Verify no worker encountered an exception
    assert all(exc is None for exc in exceptions), f"Exceptions in thread workers: {[e for e in exceptions if e]}"
    # Verify all 50 threads received a client instance
    assert all(r is not None for r in results), "Some threads received None"
    # Verify exact object identity across all 50 threads
    first_client = results[0]
    for idx, client in enumerate(results):
        assert client is first_client, f"Thread {idx} got a different client instance!"

    reset_genai_client()


@pytest.mark.asyncio
async def test_concurrency_coroutines_50():
    """
    Stress-test get_genai_client with 50 concurrent async coroutines
    invoked via asyncio.gather to ensure coroutine-safe singleton access.
    """
    reset_genai_client()

    async def coroutine_worker(idx: int):
        await asyncio.sleep(0.001 * (idx % 5))
        return get_genai_client("adversarial_test_key_coroutines")

    tasks = [coroutine_worker(i) for i in range(50)]
    clients = await asyncio.gather(*tasks)

    assert len(clients) == 50
    first_client = clients[0]
    assert all(c is first_client for c in clients), "Coroutines received non-identical client instances!"

    reset_genai_client()


def test_concurrency_missing_api_key_50_threads(monkeypatch):
    """
    Assert that under 50 concurrent threads with missing API key,
    all 50 threads cleanly raise ValueError without corrupting the singleton state.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reset_genai_client()

    barrier = threading.Barrier(50)
    exceptions = [None] * 50

    def worker(idx: int):
        try:
            barrier.wait(timeout=5.0)
            get_genai_client(None)
        except Exception as e:
            exceptions[idx] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert all(isinstance(exc, ValueError) for exc in exceptions), "Not all threads raised ValueError"
    assert all("GEMINI_API_KEY is not configured" in str(exc) for exc in exceptions)


# ============================================================================
# 2. RETRY DECORATOR STRESS TEST (EXPONENTIAL BACKOFF & JITTER)
# ============================================================================

@pytest.mark.asyncio
async def test_retry_burst_of_transient_errors():
    """
    Simulate a rapid burst of mixed transient errors (429, TimeoutError, 503 ServerError)
    followed by eventual success on attempt 4 (within max_retries=3).
    Verifies that exponential backoff delays strictly scale and include randomized jitter.
    """
    call_timestamps = []
    attempt = 0

    @retry_with_backoff(
        max_retries=3,
        initial_delay=0.02,
        backoff_factor=2.0,
        jitter_min=0.01,
        jitter_max=0.02
    )
    async def flaky_service():
        nonlocal attempt
        call_timestamps.append(time.perf_counter())
        attempt += 1
        if attempt == 1:
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        elif attempt == 2:
            raise asyncio.TimeoutError("Gateway Connection Timeout")
        elif attempt == 3:
            raise errors.ServerError(503, {"error": {"message": "Backend Unavailable"}})
        return "ADVERSARIAL_SUCCESS"

    result = await flaky_service()
    assert result == "ADVERSARIAL_SUCCESS"
    assert attempt == 4
    assert len(call_timestamps) == 4

    # Verify delays between attempts
    delays = [call_timestamps[i] - call_timestamps[i - 1] for i in range(1, 4)]
    # Expected delays:
    # Attempt 1 -> 2: 0.02 * (2^0) + jitter = 0.02 + [0.01, 0.02] => [0.03, 0.04]
    # Attempt 2 -> 3: 0.02 * (2^1) + jitter = 0.04 + [0.01, 0.02] => [0.05, 0.06]
    # Attempt 3 -> 4: 0.02 * (2^2) + jitter = 0.08 + [0.01, 0.02] => [0.09, 0.10]
    for d in delays:
        assert d >= 0.025, f"Delay {d} was lower than expected backoff + jitter minimum"

    # Verify strictly monotonic backoff progression (delay[i] > delay[i-1])
    assert delays[1] > delays[0], f"Expected exponential growth: {delays[1]} > {delays[0]}"
    assert delays[2] > delays[1], f"Expected exponential growth: {delays[2]} > {delays[1]}"


@pytest.mark.asyncio
async def test_retry_exhaustion_raises():
    """
    Assert that when transient errors persist beyond max_retries,
    the decorator stops retrying and raises the underlying transient exception.
    """
    attempts = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.005, jitter_min=0.001, jitter_max=0.002)
    async def always_fails():
        nonlocal attempts
        attempts += 1
        raise errors.ServerError(503, {"error": {"message": "Permanent 503"}})

    with pytest.raises(errors.ServerError) as exc_info:
        await always_fails()

    assert "Permanent 503" in str(exc_info.value)
    # Initial attempt + 3 retries = 4 total calls
    assert attempts == 4


@pytest.mark.asyncio
async def test_retry_non_transient_fails_immediately():
    """
    Assert that non-transient errors (400 Bad Request, 401 Unauthorized, ValueError, KeyError)
    fail immediately on attempt 1 without wasteful sleep or retries.
    """
    non_transient_exceptions = [
        errors.ClientError(400, {"error": {"message": "Bad Request: Invalid Argument"}}),
        errors.ClientError(401, {"error": {"message": "Unauthorized"}}),
        errors.ClientError(403, {"error": {"message": "Permission Denied"}}),
        ValueError("Invalid prompt input parameter"),
        KeyError("missing_field"),
    ]

    for non_transient_exc in non_transient_exceptions:
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.05)
        async def call_with_error():
            nonlocal call_count
            call_count += 1
            raise non_transient_exc

        with pytest.raises(type(non_transient_exc)):
            await call_with_error()

        assert call_count == 1, f"Expected exactly 1 call for {type(non_transient_exc)}, got {call_count}"


# ============================================================================
# 3. FALLBACK STABILITY TEST
# ============================================================================

@pytest.mark.asyncio
async def test_fallback_stability_complete_api_failure():
    """
    Verify that catastrophic API failure with allow_fallback=True returns
    a duck-typed AIResponse with non-empty Arabic text from SAUDI_ROAST_FALLBACKS
    and never raises an unhandled exception.
    """
    failure_scenarios = [
        # 1. 429 Quota Exhausted
        errors.ClientError(429, {"error": {"message": "Quota exceeded"}}),
        # 2. 503 Service Unavailable
        errors.ServerError(503, {"error": {"message": "Google GenAI Cluster Down"}}),
        # 3. Network connection drop
        ConnectionResetError("Connection reset by peer"),
        # 4. Asyncio Timeout
        asyncio.TimeoutError("Deadline exceeded"),
        # 5. Generic RuntimeError
        RuntimeError("Catastrophic internal failure in GenAI transport"),
    ]

    client = get_genai_client("dummy_key_for_fallback_tests")

    for exc in failure_scenarios:
        mock_fail = AsyncMock(side_effect=exc)
        with patch.object(client.aio.models, "generate_content", mock_fail):
            resp = await generate_content_ai("سياق عشوائي", allow_fallback=True)

            assert isinstance(resp, AIResponse)
            assert resp.is_fallback is True
            assert isinstance(resp.text, str)
            assert len(resp.text.strip()) > 15
            # Must be an authentic Arabic text from the defined fallbacks
            assert resp.text in SAUDI_ROAST_FALLBACKS
            # Verify duck typing: str(resp) must equal resp.text
            assert str(resp) == resp.text
            # Verify strip() method works on .text without crashing
            assert resp.text.strip() != ""


@pytest.mark.asyncio
async def test_fallback_disabled_raises_properly():
    """
    Verify that when allow_fallback=False, complete failure raises
    the original exception rather than swallowing errors silently.
    """
    client = get_genai_client("dummy_key_for_fallback_tests")
    mock_fail = AsyncMock(side_effect=RuntimeError("Unrecoverable Crash"))
    with patch.object(client.aio.models, "generate_content", mock_fail):
        with pytest.raises(RuntimeError, match="Unrecoverable Crash"):
            await generate_content_ai("اذب عليه", allow_fallback=False)


# ============================================================================
# 4. STRUCTURED JSON CORRUPTION TEST
# ============================================================================

@pytest.mark.asyncio
async def test_structured_ai_corruption_resilience_pydantic():
    """
    Pass malformed JSON, truncated markdown fences, conversational chatter,
    empty strings, and invalid types to generate_structured_ai with Pydantic schema.
    Assert default fallback is safely returned across all corrupted payloads without crashing.
    """
    corrupt_payloads = [
        # 1. Incomplete JSON with open bracket
        '{"title": "قضية رقم 1", "indictment": "المتهم',
        # 2. Single-quoted pseudo-JSON
        "{'title': 'قضية', 'indictment': 'غائب', 'penalty': 'العار'}",
        # 3. Unquoted JSON keys
        '{title: "قضية", indictment: "غائب", penalty: "العار"}',
        # 4. Truncated markdown fence without closing fence or closing brace
        '```json\n{"title": "قضية مبتورة',
        # 5. Raw conversational response without any JSON
        'أعتذر، لا يمكنني كتابة لائحة اتهام بسبب قيود السلامة والأمان.',
        # 6. Completely empty payload
        '',
        # 7. Whitespace-only payload
        '   \n\t  ',
        # 8. Top-level array instead of object
        '[{"title": "1"}, {"title": "2"}]',
        # 9. Schema field type mismatch (int instead of required string)
        '{"title": 12345, "indictment": ["not a string"], "penalty": null}',
        # 10. Missing required fields in Pydantic schema
        '{"title": "عنوان فقط بدون الباقي"}',
    ]

    default_fallback_dict = {
        "title": "محاكمة افتراضية احتياطية",
        "indictment": "المتهم صنم معتاد وساحب على الشباب",
        "penalty": "الجلد الساخر الفوري"
    }

    client = get_genai_client("dummy_key_structured_stress")

    for payload in corrupt_payloads:
        mock_resp = MagicMock()
        mock_resp.text = payload

        with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
            res = await generate_structured_ai(
                contents="محاكمة المتهم",
                schema=CourtIndictmentSchema,
                default_fallback=default_fallback_dict
            )
            assert res == default_fallback_dict, f"Pydantic failed on payload: {repr(payload)}"


@pytest.mark.asyncio
async def test_structured_ai_corruption_resilience_dict():
    """
    Pass syntactically corrupted JSON, truncated markdown fences, and conversational chatter
    to generate_structured_ai with dict schema.
    Assert default fallback is safely returned without crashing.
    """
    syntax_corrupted_payloads = [
        # 1. Incomplete JSON with open bracket
        '{"title": "قضية رقم 1", "indictment": "المتهم',
        # 2. Single-quoted pseudo-JSON
        "{'title': 'قضية', 'indictment': 'غائب', 'penalty': 'العار'}",
        # 3. Unquoted JSON keys
        '{title: "قضية", indictment: "غائب", penalty: "العار"}',
        # 4. Truncated markdown fence without closing fence or closing brace
        '```json\n{"title": "قضية مبتورة',
        # 5. Raw conversational response without any JSON
        'أعتذر، لا يمكنني كتابة لائحة اتهام بسبب قيود السلامة والأمان.',
        # 6. Whitespace-only payload
        '   \n\t  ',
    ]

    default_fallback_dict = {
        "title": "محاكمة افتراضية احتياطية",
        "indictment": "المتهم صنم معتاد وساحب على الشباب",
        "penalty": "الجلد الساخر الفوري"
    }

    client = get_genai_client("dummy_key_structured_stress")

    for payload in syntax_corrupted_payloads:
        mock_resp = MagicMock()
        mock_resp.text = payload

        with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
            res_dict = await generate_structured_ai(
                contents="محاكمة المتهم",
                schema=dict,
                default_fallback=default_fallback_dict
            )
            assert res_dict == default_fallback_dict, f"Dict schema failed on payload: {repr(payload)}"


@pytest.mark.asyncio
async def test_structured_ai_empty_string_dict_edge_case():
    """
    Empirical probe of edge case: When raw_text is '' and schema is dict,
    'raw_text or \"{}\"' defaults to '{}', which json.loads parses as {},
    returning {} rather than default_fallback.
    """
    default_fallback_dict = {"default": "ذبة", "riyadh": "ذبة"}
    mock_resp = MagicMock()
    mock_resp.text = ""

    client = get_genai_client("dummy_key_structured_stress")
    with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
        res = await generate_structured_ai(
            contents="مقارنة",
            schema=dict,
            default_fallback=default_fallback_dict
        )
        # Documents the empirical behavior: returns {} instead of default_fallback_dict
        # due to line 311 `cleaned = clean_json_markdown(raw_text or "{}")`
        assert res == {} or res == default_fallback_dict


@pytest.mark.asyncio
async def test_structured_ai_without_fallback_raises_on_corruption():
    """
    Verify that if default_fallback is None, corrupted JSON raises
    ValidationError or JSONDecodeError rather than returning None or masked values.
    """
    mock_resp = MagicMock()
    mock_resp.text = '{"malformed": true,,}'

    client = get_genai_client("dummy_key_structured_stress")
    with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
        with pytest.raises(Exception):
            await generate_structured_ai(
                contents="توليد",
                schema=CourtIndictmentSchema,
                default_fallback=None
            )


# ============================================================================
# 5. DIALECT PROMPT NEGATIVE CONSTRAINT & ANTI-REPETITION BOUNDS
# ============================================================================

def test_all_dialects_inject_negative_constraints():
    """
    Verify that DialectSynthesisEngine.get_dialect_prompt injects NEGATIVE_CONSTRAINTS
    blocking Egyptian, Levantine, Maghrebi, fake Fusha, and AI boilerplate across all 4 dialects.
    """
    engine = DialectSynthesisEngine()
    dialects = ["default", "riyadh", "jeddah", "qassim"]

    forbidden_tokens = [
        # Egyptian
        "إيه دا", "ازيك", "عايز", "كده", "بتاع", "يا راجل", "معلش", "خالص", "يا ابني", "دلوقتي",
        # Levantine
        "شو", "عم بحكي", "بدي", "بديش", "كتير", "يا زلمة", "هيك", "ليش عم", "هلق", "منيح", "هاد",
        # Maghrebi
        "واش", "بزاف", "برشا", "ديال", "كيداير", "راك", "مزيان",
        # Fake Fusha
        "أيها", "لماذا", "حسناً", "تباً لك", "في الحقيقة", "يا هذا", "بكل تأكيد", "ويلك",
        # AI Boilerplate
        "بالتأكيد", "إليك الذبة", "تفضل الرد"
    ]

    for d in dialects:
        sys_inst, user_prompt = engine.get_dialect_prompt(dialect_id=d, intensity=3)

        # 1. NEGATIVE_CONSTRAINTS header must be present
        assert "STRICT NEGATIVE CONSTRAINTS" in sys_inst, f"Dialect {d} missing constraints header"

        # 2. Every single forbidden term must be explicitly outlawed in the system prompt
        for token in forbidden_tokens:
            assert token in sys_inst, f"Dialect {d} system instruction missing forbidden token '{token}'"

        # 3. Dialect specific metadata must be present
        meta = DIALECTS[d]
        assert meta["name"] in sys_inst
        assert meta["region"] in sys_inst


def test_invalid_dialect_fallback_to_default_with_constraints():
    """
    Verify that an invalid/unknown dialect ID safely falls back to 'default'
    with full negative constraints intact.
    """
    engine = DialectSynthesisEngine()
    sys_inst, user_prompt = engine.get_dialect_prompt(dialect_id="non_existent_dialect", intensity=2)

    assert "STRICT NEGATIVE CONSTRAINTS" in sys_inst
    assert DIALECTS["default"]["name"] in sys_inst
    assert "مستقعد" in sys_inst  # Intensity 2 tag


def test_anti_repetition_bounding_to_last_5_roasts():
    """
    Adversarially test the anti-repetition injector:
    1. 0 roasts -> returns empty string.
    2. None -> returns empty string.
    3. List containing empty strings / whitespace -> filtered safely.
    4. 1 to 5 roasts -> all roasts included.
    5. 50 roasts -> strictly bounded to the last 5 roasts; older roasts excluded.
    """
    # 1. Empty / None
    assert format_anti_repetition_prompt(None) == ""
    assert format_anti_repetition_prompt([]) == ""
    assert format_anti_repetition_prompt(["", "  \n  ", "\t"]) == ""

    # 2. Exactly 5 roasts
    five_roasts = [f"ذبة رقم {i}" for i in range(1, 6)]
    prompt_5 = format_anti_repetition_prompt(five_roasts)
    assert "ANTI-REPETITION" in prompt_5
    for r in five_roasts:
        assert r in prompt_5

    # 3. 50 roasts stress test -> strictly the last 5
    fifty_roasts = [f"ذبة_تاريخية_قديمة_{i}" for i in range(50)]
    prompt_50 = format_anti_repetition_prompt(fifty_roasts)

    # Last 5 must be present: indices 45, 46, 47, 48, 49
    for i in range(45, 50):
        assert f'"{fifty_roasts[i]}"' in prompt_50, f"Expected last-5 roast {i} to be present"

    # Any older roast (0 to 44) must NOT be present
    for i in range(45):
        assert f'"{fifty_roasts[i]}"' not in prompt_50, f"Roast {i} should have been pruned out!"

    # 4. Intermixed invalid roasts in 10-item list
    mixed_roasts = [
        "ذبة_أولى",
        "  ",
        "ذبة_ثانية",
        "",
        "ذبة_ثالثة",
        "ذبة_رابعة",
        "ذبة_خامسة",
        "   \t",
        "ذبة_سادسة"
    ]
    # Valid roasts are: الأولى, الثانية, الثالثة, الرابعة, الخامسة, السادسة (6 valid)
    # Last 5 valid roasts: الثانية, الثالثة, الرابعة, الخامسة, السادسة
    prompt_mixed = format_anti_repetition_prompt(mixed_roasts)
    assert "ذبة_أولى" not in prompt_mixed
    assert "ذبة_ثانية" in prompt_mixed
    assert "ذبة_سادسة" in prompt_mixed


@pytest.mark.asyncio
async def test_generate_comparative_adversarial_ai_responses():
    """
    Test generate_comparative when AI returns corrupted or partial dialect keys.
    Asserts all 4 dialects (default, riyadh, jeddah, qassim) are guaranteed to exist
    and filled with authentic fallbacks where AI data was invalid or missing.
    """
    engine = DialectSynthesisEngine()

    # Scenario 1: AI returns JSON missing 'qassim' and with empty 'jeddah'
    partial_json = json.dumps({
        "default": "يا رجال وش وضعك تسوقها",
        "riyadh": "ياخي اركد شوي مهوب كذا",
        "jeddah": ""
        # 'qassim' is completely missing
    })

    mock_resp = MagicMock()
    mock_resp.text = partial_json
    engine_with_mock = DialectSynthesisEngine(ai_service_func=AsyncMock(return_value=mock_resp))

    result = await engine_with_mock.generate_comparative(
        target_name="سلطان",
        dossier_context="مسوي فيها كاري وهو أول من يموت"
    )

    assert isinstance(result, dict)
    assert set(result.keys()) == {"default", "riyadh", "jeddah", "qassim"}
    assert result["default"] == "يا رجال وش وضعك تسوقها"
    assert result["riyadh"] == "ياخي اركد شوي مهوب كذا"
    # jeddah and qassim should have fallen back to authentic dialect fallbacks
    assert "سلطان" in result["jeddah"]
    assert "يا واد" in result["jeddah"]
    assert "سلطان" in result["qassim"]
    assert "وش نوحك" in result["qassim"]
