"""
tests/test_challenger_verification.py - Empirical Challenger Verification Harness for M2 It2

Directly tests the specific adversarial challenges:
1. Empty response fallback in generate_structured_ai with empty string "" and whitespace "   ".
2. format_context_for_roast resilience with {"voice_stats": None, "grudge_level": None, "infractions": None}.
3. Concurrency stress test on _sync_save_state_atomic verifying zero PermissionError on Windows NTFS.
"""

import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from modules.ai_service import (
    CourtIndictmentSchema,
    generate_structured_ai,
    get_genai_client,
)
from modules.state_manager import GRUDGE_TITLES, StateManager


# ============================================================================
# 1. EMPTY RESPONSE FALLBACK IN generate_structured_ai ("" and "   ")
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("empty_payload", ["", "   ", "   \n\t  \r\n  ", "\t\t"])
@pytest.mark.parametrize("use_pydantic", [False, True])
async def test_structured_ai_empty_and_whitespace_fallback(empty_payload, use_pydantic):
    """
    Adversarially verify that when model returns an empty string or whitespace-only response,
    generate_structured_ai returns default_fallback directly (NOT {} or crashing).
    Tested across both dict schema and Pydantic schema.
    """
    fallback_payload = {
        "title": "محاكمة افتراضية للغياب",
        "indictment": "المتهم صنم معتاد وساحب على الشباب",
        "penalty": "الجلد الساخر الفوري"
    }

    mock_resp = MagicMock()
    mock_resp.text = empty_payload

    client = get_genai_client("dummy_key_challenger_test")
    schema_target = CourtIndictmentSchema if use_pydantic else dict

    with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
        result = await generate_structured_ai(
            contents="صغ لائحة اتهام",
            schema=schema_target,
            default_fallback=fallback_payload
        )

        assert result == fallback_payload, (
            f"Expected default_fallback {fallback_payload}, but got {result!r} "
            f"for empty_payload={empty_payload!r}, use_pydantic={use_pydantic}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_payload", ["", "   "])
async def test_structured_ai_empty_without_fallback_raises(empty_payload):
    """
    Verify that if default_fallback is None, empty string/whitespace raises an exception
    rather than silently returning None or {}.
    """
    mock_resp = MagicMock()
    mock_resp.text = empty_payload

    client = get_genai_client("dummy_key_challenger_test")

    with patch.object(client.aio.models, "generate_content", AsyncMock(return_value=mock_resp)):
        with pytest.raises(Exception):
            await generate_structured_ai(
                contents="توليد بدون احتياطي",
                schema=CourtIndictmentSchema,
                default_fallback=None
            )


# ============================================================================
# 2. format_context_for_roast WITH None VALUES
# ============================================================================

def test_format_context_for_roast_none_values_stress(tmp_path):
    """
    Verify format_context_for_roast when dossier contains:
    {"voice_stats": None, "grudge_level": None, "infractions": None}
    Asserts zero exceptions (no TypeError, no AttributeError), default grudge level 1,
    and safe fallback text.
    """
    mgr = StateManager(data_dir=str(tmp_path), state_filename="none_val_state.json")
    user_id = 999111

    # Exact payload requested in mission:
    mgr._state["dossiers"][str(user_id)] = {
        "user_id": user_id,
        "voice_stats": None,
        "grudge_level": None,
        "infractions": None,
    }

    # Format without live voice context (historical cumulative path)
    res_no_live = mgr.format_context_for_roast(user_id, live_voice_context=None)
    assert isinstance(res_no_live, str)
    assert "ملف سوابق واستخبارات الضحية" in res_no_live
    assert "[1/5]" in res_no_live
    assert GRUDGE_TITLES[1] in res_no_live
    assert "عضو تحت المراقبة" in res_no_live

    # Also format with completely None / empty live_voice_context
    res_with_empty_live = mgr.format_context_for_roast(user_id, live_voice_context={})
    assert isinstance(res_with_empty_live, str)
    assert "[1/5]" in res_with_empty_live

    # Format with live_voice_context containing None values
    live_none_context = {
        "channel_name": None,
        "minutes": None,
        "deafened": None,
        "muted": None,
        "games": None,
        "custom_status": None,
    }
    res_with_none_live = mgr.format_context_for_roast(user_id, live_voice_context=live_none_context)
    assert isinstance(res_with_none_live, str)
    assert "[1/5]" in res_with_none_live


def test_format_context_for_roast_fully_poisoned_dossier(tmp_path):
    """
    Adversarially poison every single dossier key with None and verify no unhandled crash.
    """
    mgr = StateManager(data_dir=str(tmp_path), state_filename="poisoned_state.json")
    user_id = 999222

    mgr._state["dossiers"][str(user_id)] = {
        "user_id": user_id,
        "username": None,
        "display_name": None,
        "grudge_level": None,
        "titles": None,
        "crimes": None,
        "infractions": None,
        "excuses": None,
        "embarrassing_moments": None,
        "voice_stats": None,
        "notes": None,
    }

    res = mgr.format_context_for_roast(user_id)
    assert isinstance(res, str)
    assert "[1/5]" in res
    assert "عضو تحت المراقبة" in res


# ============================================================================
# 3. CONCURRENCY STRESS TEST ON _sync_save_state_atomic (ZERO PermissionError)
# ============================================================================

def test_sync_save_state_atomic_concurrency_stress(tmp_path):
    """
    Stress-test _sync_save_state_atomic under aggressive multi-threaded contention
    on Windows NTFS. 50 OS threads simultaneously perform rapid writes.
    Asserts:
    1. Zero PermissionError or WinError 5 raised across all threads.
    2. Zero temporary files leaked in the directory.
    3. Final state file and backup file are intact, non-empty, and valid JSON.
    """
    state_file = tmp_path / "concurrent_state.json"
    mgr = StateManager(data_dir=str(tmp_path), state_filename="concurrent_state.json")

    num_threads = 50
    iterations_per_thread = 5  # Total 250 atomic disk replacements
    barrier = threading.Barrier(num_threads)
    exceptions = []
    thread_lock = threading.Lock()

    def stress_worker(worker_id: int):
        try:
            barrier.wait(timeout=10.0)
            for i in range(iterations_per_thread):
                # Mutate state safely under StateManager's internal thread lock
                with mgr._thread_lock:
                    uid = f"user_{worker_id}_{i}"
                    mgr._state["dossiers"][uid] = {
                        "user_id": worker_id * 1000 + i,
                        "worker_id": worker_id,
                        "iteration": i,
                        "timestamp": time.time(),
                    }
                # Directly call _sync_save_state_atomic to trigger disk write contention
                mgr._sync_save_state_atomic()
        except Exception as ex:
            with thread_lock:
                exceptions.append((worker_id, ex))

    threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)

    # 1. Zero exceptions / zero PermissionError
    assert len(exceptions) == 0, f"Encountered exceptions during atomic write stress: {exceptions}"

    # 2. File exists, non-empty, valid JSON
    assert os.path.exists(state_file)
    assert os.path.getsize(state_file) > 0
    with open(state_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert isinstance(loaded, dict)
    assert "dossiers" in loaded
    # Verify all 250 dossiers are present
    assert len(loaded["dossiers"]) == num_threads * iterations_per_thread

    # 3. Backup file exists and is valid JSON
    bak_file = tmp_path / "concurrent_state.json.bak"
    assert os.path.exists(bak_file)
    with open(bak_file, "r", encoding="utf-8") as f:
        loaded_bak = json.load(f)
    assert isinstance(loaded_bak, dict)

    # 4. Zero orphaned temp files
    remaining_files = os.listdir(tmp_path)
    temp_files = [f for f in remaining_files if f.startswith(".tmp_") or f.endswith(".tmp")]
    assert len(temp_files) == 0, f"Found orphaned temp files: {temp_files}"


@pytest.mark.asyncio
async def test_async_save_state_atomic_concurrency_stress(tmp_path):
    """
    Stress-test the coroutine entrypoint save_state_atomic() with 50 concurrent coroutines
    writing via asyncio.gather on Windows NTFS.
    """
    state_file = tmp_path / "concurrent_async_state.json"
    mgr = StateManager(data_dir=str(tmp_path), state_filename="concurrent_async_state.json")

    async def coroutine_worker(worker_id: int):
        for i in range(5):
            async with mgr._async_lock:
                mgr._state["dossiers"][f"async_{worker_id}_{i}"] = {
                    "worker_id": worker_id,
                    "iteration": i,
                }
            await mgr.save_state_atomic()

    tasks = [coroutine_worker(i) for i in range(50)]
    await asyncio.gather(*tasks)

    # Validate state file
    assert os.path.exists(state_file)
    with open(state_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded["dossiers"]) == 250
