"""
tests/test_state_manager.py - Automated Verification Suite for StateManager
"""
import os
import json
import shutil
import asyncio
import pytest
from unittest.mock import patch
from modules.state_manager import StateManager


@pytest.fixture
def temp_mgr(tmp_path):
    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    yield mgr


@pytest.mark.asyncio
async def test_atomic_write_creates_valid_json(temp_mgr):
    """Verifies that atomic save writes clean JSON to disk."""
    await temp_mgr.set_grudge_level(101, 3)
    assert os.path.exists(temp_mgr.filepath)
    with open(temp_mgr.filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "101" in data["dossiers"]
    assert data["dossiers"]["101"]["grudge_level"] == 3


@pytest.mark.asyncio
async def test_bounded_grudge_scale(temp_mgr):
    """Verifies clamping strictly between 1 and 5."""
    assert await temp_mgr.set_grudge_level(102, 100) == 5
    assert await temp_mgr.set_grudge_level(102, -10) == 1
    assert await temp_mgr.set_grudge_level(102, 4) == 4


@pytest.mark.asyncio
async def test_structured_infractions_sync(temp_mgr):
    """Verifies dual structured infraction and readable crime string persistence."""
    await temp_mgr.add_infraction(103, "AFK_DEAFENED", "Deafened for 2h")
    d = await temp_mgr.get_dossier(103)
    assert len(d["infractions"]) == 1
    assert d["infractions"][0]["type"] == "AFK_DEAFENED"
    assert len(d["crimes"]) == 1
    assert "[AFK_DEAFENED]" in d["crimes"][0]


@pytest.mark.asyncio
async def test_roast_history_and_recent_anti_repetition(temp_mgr):
    """Verifies per-user roast history and get_recent_roasts slicing."""
    for i in range(8):
        await temp_mgr.record_roast(104, "Victim", f"Burn {i}", "jeddah", 3)
    recent = await temp_mgr.get_recent_roasts(104, limit=5)
    assert len(recent) == 5
    assert recent[0] == "Burn 3"
    assert recent[-1] == "Burn 7"


@pytest.mark.asyncio
async def test_concurrency_stress_50_coroutines(temp_mgr):
    """Verifies race condition freedom under 50 simultaneous asynchronous writers."""
    async def worker(idx):
        await temp_mgr.add_infraction(idx, "STRESS_TEST", f"Detail {idx}")
        await temp_mgr.set_grudge_level(idx, (idx % 5) + 1)

    tasks = [worker(i) for i in range(50)]
    await asyncio.gather(*tasks)

    all_d = await temp_mgr.get_all_dossiers()
    assert len(all_d) == 50
    with open(temp_mgr.filepath, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert len(disk_data["dossiers"]) == 50


def test_zero_byte_file_recovery(tmp_path):
    """Verifies that an interrupted write producing 0 bytes recovers via backup."""
    state_file = tmp_path / "state.json"
    bak_file = tmp_path / "state.json.bak"
    # Seed backup
    with open(bak_file, "w", encoding="utf-8") as f:
        json.dump({"_version": 1, "dossiers": {"999": {"grudge_level": 5}}, "metrics": {}}, f)
    # Zero-byte corrupted main file
    with open(state_file, "w", encoding="utf-8") as f:
        pass

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert "999" in mgr.dossiers
    assert mgr.dossiers["999"]["grudge_level"] == 5


def test_corrupt_json_quarantine_and_recovery(tmp_path):
    """Verifies that malformed JSON is quarantined and recovered from .bak."""
    state_file = tmp_path / "state.json"
    bak_file = tmp_path / "state.json.bak"
    with open(bak_file, "w", encoding="utf-8") as f:
        json.dump({"_version": 1, "dossiers": {"888": {"grudge_level": 4}}, "metrics": {}}, f)
    with open(state_file, "w", encoding="utf-8") as f:
        f.write("MALFORMED JSON {{{[[[")

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert "888" in mgr.dossiers
    corrupt_files = list(tmp_path.glob("state.json.corrupt.*"))
    assert len(corrupt_files) == 1


@pytest.mark.asyncio
async def test_simulated_crash_atomic_rollback(temp_mgr):
    """Verifies that if os.replace fails, original file remains intact."""
    await temp_mgr.set_grudge_level(777, 2)
    # Mock replace failure
    with patch("os.replace", side_effect=OSError("Simulated power failure")):
        with pytest.raises(OSError):
            await temp_mgr.save_state_atomic()
    # File must still be valid JSON
    with open(temp_mgr.filepath, "r", encoding="utf-8") as f:
        valid = json.load(f)
    assert valid["dossiers"]["777"]["grudge_level"] == 2


def test_legacy_migration_fidelity(tmp_path):
    """Verifies accurate non-destructive migration of user_dossiers.json and bot_data.json."""
    data_dir = tmp_path / "data"
    dossiers_path = tmp_path / "user_dossiers.json"
    bot_data_path = tmp_path / "bot_data.json"

    with open(dossiers_path, "w", encoding="utf-8") as f:
        json.dump({
            "555": {
                "titles": ["ملك الأعذار"],
                "excuses": ["الماوس علق"],
                "crimes": ["نكبة في الراوند"],
                "updated_at": 1000.0
            }
        }, f)

    with open(bot_data_path, "w", encoding="utf-8") as f:
        json.dump({
            "roast_log": [[1000.0, "User555", "ذبة"]],
            "roast_count_per_user": {"555": 3},
            "daily_roast_counts": {"2026-09-06": 3},
            "hourly_vc_activity": [0] * 24,
            "game_popularity": {"Valorant": 1},
            "grudge_levels": {"555": 42},
            "current_dialect": "jeddah"
        }, f)

    # Change working dir to tmp_path during initialization to find legacy files
    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        mgr = StateManager(data_dir="data", state_filename="state.json")
        dos = mgr.get_user_dossier(555)
        assert dos["titles"] == ["ملك الأعذار"]
        assert dos["grudge_level"] == 3  # 42 mapped to Level 3: (42 // 20) + 1 = 3
        assert len(dos["infractions"]) == 1
        assert mgr.metrics["current_dialect"] == "jeddah"
        assert mgr.metrics["roast_count_per_user"]["555"] == 3
    finally:
        os.chdir(orig_cwd)
