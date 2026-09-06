"""
tests/test_state_manager_adversarial.py - Empirical Adversarial Stress Suite
Authored by m1_challenger_1 for Milestone 1 Adversarial Verification.

Stress-tests:
1. High-concurrency race condition tests (120+ concurrent coroutines updating dossiers,
   adding infractions, setting grudge levels, recording roasts simultaneously; single-user contention).
2. Sudden crash and partial write simulations (0-byte file recovery, corrupted JSON quarantine,
   absence of backup fallback, atomic write rollback on simulated filesystem crash).
3. Grudge bounds stress testing (boundary matrix: -999, 0, 1, 5, 6, 99999, float, strings, invalid types).
4. Memory bloat and circular buffer bound enforcement (capping at 15 infractions/crimes/roasts).
"""
import os
import json
import time
import shutil
import asyncio
import pytest
from unittest.mock import patch
from modules.state_manager import StateManager


@pytest.fixture
def adv_mgr(tmp_path):
    """Provides a cleanly isolated StateManager instance in a temporary directory."""
    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    yield mgr


# ─────────────────────────────────────────────────────────────────────────────
# 1. High-Concurrency Race Condition Suite (100+ Concurrent Coroutines)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_high_concurrency_120_coroutines_mixed_operations(adv_mgr):
    """
    Simulates 120 concurrent asynchronous coroutines executing heterogeneous operations
    simultaneously across a shared and distinct user pool:
    - 30 coroutines updating dossiers with arbitrary fields
    - 30 coroutines adding infractions and crimes
    - 30 coroutines setting grudge levels (1-5 boundaries)
    - 30 coroutines recording roasts with anti-repetition tracking
    """
    total_coroutines = 120
    user_pool = [1000 + (i % 20) for i in range(total_coroutines)]

    async def worker_update(idx: int, uid: int):
        await adv_mgr.update_dossier(uid, {
            "display_name": f"Adversarial_{idx}",
            f"custom_field_{idx}": f"val_{idx}"
        })

    async def worker_infraction(idx: int, uid: int):
        await adv_mgr.add_infraction(uid, "HIGH_CONCURRENCY_CRIME", f"Infraction event #{idx}")

    async def worker_grudge(idx: int, uid: int):
        # Rotate through boundary and valid values
        val = [-999, 0, 1, 3, 5, 6, 99999][idx % 7]
        await adv_mgr.set_grudge_level(uid, val)

    async def worker_roast(idx: int, uid: int):
        dialects = ["default", "riyadh", "jeddah", "qassim"]
        dialect = dialects[idx % len(dialects)]
        await adv_mgr.record_roast(
            user_id=uid,
            username=f"Target_{uid}",
            roast_text=f"Concurrent Roast #{idx}",
            dialect=dialect,
            intensity=((idx % 5) + 1)
        )

    tasks = []
    for i in range(30):
        tasks.append(worker_update(i, user_pool[i]))
    for i in range(30, 60):
        tasks.append(worker_infraction(i, user_pool[i]))
    for i in range(60, 90):
        tasks.append(worker_grudge(i, user_pool[i]))
    for i in range(90, 120):
        tasks.append(worker_roast(i, user_pool[i]))

    # Execute all 120 coroutines concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Verify zero exceptions across all 120 tasks
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Encountered {len(exceptions)} exceptions: {exceptions}"

    # Verify disk persistence integrity
    assert os.path.exists(adv_mgr.filepath), "State file missing from disk after concurrent writes."
    with open(adv_mgr.filepath, "r", encoding="utf-8") as f:
        disk_data = json.load(f)

    assert "_version" in disk_data
    assert "dossiers" in disk_data
    assert "metrics" in disk_data

    # Verify all 20 active users exist in memory and on disk
    all_dossiers = await adv_mgr.get_all_dossiers()
    assert len(all_dossiers) >= 20
    assert len(disk_data["dossiers"]) == len(all_dossiers)

    # Verify that roast count metrics match the 30 roast operations executed
    total_roasts_recorded = len(disk_data["metrics"]["roast_log"])
    assert total_roasts_recorded == 30
    sum_user_roasts = sum(disk_data["metrics"]["roast_count_per_user"].values())
    assert sum_user_roasts == 30

    # Verify every dossier's grudge level on disk is strictly bounded [1, 5]
    for uid, d in disk_data["dossiers"].items():
        assert isinstance(d["grudge_level"], int)
        assert 1 <= d["grudge_level"] <= 5


@pytest.mark.asyncio
async def test_concurrency_shared_single_user_contention_100_coroutines(adv_mgr):
    """
    Adversarial Hot-Key Test: 100 concurrent coroutines all mutating the EXACT SAME user.
    Tests lock contention, serialization correctness, and array boundary capping.
    """
    target_user_id = 777000

    async def op_infraction(i):
        await adv_mgr.add_infraction(target_user_id, "CONTENTION_CRIME", f"Detail {i}")

    async def op_roast(i):
        await adv_mgr.record_roast(target_user_id, "HotTarget", f"Hot Roast {i}", "jeddah", 4)

    async def op_grudge(i):
        await adv_mgr.set_grudge_level(target_user_id, (i % 5) + 1)

    async def op_update(i):
        await adv_mgr.update_dossier(target_user_id, {"last_contender": i})

    tasks = []
    for i in range(25):
        tasks.append(op_infraction(i))
        tasks.append(op_roast(i))
        tasks.append(op_grudge(i))
        tasks.append(op_update(i))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Exceptions during single user contention: {exceptions}"

    # Verify bounds in memory and on disk
    dossier = await adv_mgr.get_dossier(target_user_id)
    assert len(dossier["infractions"]) <= 15, "Infractions list exceeded 15 item memory ceiling!"
    assert len(dossier["crimes"]) <= 15, "Crimes list exceeded 15 item memory ceiling!"
    assert len(dossier["roast_history"]) <= 15, "Roast history exceeded 15 item memory ceiling!"
    assert 1 <= dossier["grudge_level"] <= 5

    with open(adv_mgr.filepath, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    disk_dossier = disk_data["dossiers"][str(target_user_id)]
    assert len(disk_dossier["infractions"]) <= 15
    assert len(disk_dossier["crimes"]) <= 15
    assert len(disk_dossier["roast_history"]) <= 15


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sudden Crash / Partial Write / Corruption Recovery Suite
# ─────────────────────────────────────────────────────────────────────────────

def test_recovery_from_zero_byte_state_with_valid_backup(tmp_path):
    """
    Scenario: Sudden system power cut caused state.json to truncate to 0 bytes.
    StateManager must detect 0-byte state and recover automatically from state.json.bak.
    """
    state_file = tmp_path / "state.json"
    bak_file = tmp_path / "state.json.bak"

    # Valid backup state
    backup_content = {
        "_version": 1,
        "last_saved": 1000.0,
        "dossiers": {
            "404": {
                "user_id": 404,
                "username": "Survivor",
                "grudge_level": 4,
                "infractions": []
            }
        },
        "metrics": {"current_dialect": "qassim"}
    }
    with open(bak_file, "w", encoding="utf-8") as f:
        json.dump(backup_content, f)

    # Corrupted 0-byte primary file
    with open(state_file, "w", encoding="utf-8") as f:
        pass
    assert os.path.getsize(state_file) == 0

    # Initialize manager
    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert "404" in mgr.dossiers
    assert mgr.dossiers["404"]["username"] == "Survivor"
    assert mgr.dossiers["404"]["grudge_level"] == 4
    assert mgr.metrics["current_dialect"] == "qassim"


def test_recovery_from_zero_byte_state_without_backup(tmp_path):
    """
    Scenario: state.json is 0 bytes and NO backup exists.
    StateManager must safely fall back to DEFAULT_STATE without crashing or raising.
    """
    state_file = tmp_path / "state.json"
    with open(state_file, "w", encoding="utf-8") as f:
        pass
    assert os.path.getsize(state_file) == 0

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert mgr.dossiers == {}
    assert mgr.metrics["current_dialect"] == "default"
    assert isinstance(mgr.metrics["roast_log"], list)


def test_recovery_corrupt_json_quarantine_and_backup_restoration(tmp_path):
    """
    Scenario: state.json contains partial/corrupt JSON (e.g. abrupt termination mid-write).
    StateManager must quarantine the bad file and recover from state.json.bak.
    """
    state_file = tmp_path / "state.json"
    bak_file = tmp_path / "state.json.bak"

    with open(bak_file, "w", encoding="utf-8") as f:
        json.dump({
            "_version": 1,
            "dossiers": {"500": {"username": "RestoredUser", "grudge_level": 3}},
            "metrics": {}
        }, f)

    corrupted_text = '{"_version": 1, "dossiers": {"500": {"username": "Truncated'
    with open(state_file, "w", encoding="utf-8") as f:
        f.write(corrupted_text)

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert "500" in mgr.dossiers
    assert mgr.dossiers["500"]["username"] == "RestoredUser"

    # Check quarantine file was created
    quarantined = list(tmp_path.glob("state.json.corrupt.*"))
    assert len(quarantined) >= 1
    with open(quarantined[0], "r", encoding="utf-8") as f:
        assert f.read() == corrupted_text


def test_recovery_corrupt_json_without_backup_falls_back_cleanly(tmp_path):
    """
    Scenario: state.json contains corrupt bytes and no backup exists.
    StateManager must quarantine and cleanly fall back to default state without crash.
    """
    state_file = tmp_path / "state.json"
    with open(state_file, "wb") as f:
        f.write(b"\x00\x00\x01\xff\xfe\x00NON_JSON_CORRUPTION")

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert mgr.dossiers == {}
    quarantined = list(tmp_path.glob("state.json.corrupt.*"))
    assert len(quarantined) >= 1


@pytest.mark.asyncio
async def test_atomic_write_rollback_on_filesystem_failure(adv_mgr):
    """
    Simulates sudden filesystem error during atomic replace.
    Verifies that the original file remains uncorrupted and intact.
    """
    await adv_mgr.set_grudge_level(888, 5)
    orig_mtime = os.path.getmtime(adv_mgr.filepath)

    with patch("os.replace", side_effect=OSError("Disk write I/O failure")):
        with pytest.raises(OSError):
            await adv_mgr.save_state_atomic()

    # Verify original file was not corrupted
    with open(adv_mgr.filepath, "r", encoding="utf-8") as f:
        recovered = json.load(f)
    assert recovered["dossiers"]["888"]["grudge_level"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# 3. Grudge Bounds Adversarial Matrix (-999, 0, 1, 5, 6, 99999, float, strings)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("input_val,expected_level,expected_points", [
    (-999, 1, 0),
    (0, 1, 0),
    (1, 1, 0),
    (2, 2, 20),
    (3, 3, 40),
    (4, 4, 60),
    (5, 5, 80),
    (6, 5, 80),
    (99999, 5, 80),
    # Floating point inputs
    (-100.5, 1, 0),
    (0.1, 1, 0),
    (1.0, 1, 0),
    (2.9, 2, 20),
    (4.1, 4, 60),
    (5.0, 5, 80),
    (5.9, 5, 80),
    (9999.9, 5, 80),
    # Numeric strings
    ("-999", 1, 0),
    ("0", 1, 0),
    ("1", 1, 0),
    ("3", 3, 40),
    ("5", 5, 80),
    ("6", 5, 80),
    ("99999", 5, 80),
    ("  4  ", 4, 60),
])
async def test_grudge_bounds_comprehensive_matrix(adv_mgr, input_val, expected_level, expected_points):
    """
    Verifies strict 1-5 integer bounding across negative, boundary, out-of-bounds,
    floating point, and numeric string values.
    """
    user_id = 99001 + (hash(str(input_val)) % 1000)
    returned = await adv_mgr.set_grudge_level(user_id, input_val)

    # 1. Return value assertions
    assert returned == expected_level
    assert isinstance(returned, int)
    assert 1 <= returned <= 5

    # 2. In-memory dossier assertions
    dossier = await adv_mgr.get_dossier(user_id)
    assert dossier["grudge_level"] == expected_level
    assert isinstance(dossier["grudge_level"], int)
    assert dossier["grudge_points"] == expected_points

    # 3. Global metrics assertions
    assert adv_mgr.metrics["grudge_levels"][str(user_id)] == expected_level

    # 4. On-disk persistence assertions
    with open(adv_mgr.filepath, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["dossiers"][str(user_id)]["grudge_level"] == expected_level
    assert isinstance(disk_data["dossiers"][str(user_id)]["grudge_level"], int)
    assert disk_data["dossiers"][str(user_id)]["grudge_points"] == expected_points
    assert disk_data["metrics"]["grudge_levels"][str(user_id)] == expected_level


@pytest.mark.asyncio
async def test_grudge_bounds_invalid_non_numeric_types_fail_safe(adv_mgr):
    """
    Verifies that non-numeric types (strings like 'invalid', None, dict, list)
    raise ValueError/TypeError safely without corrupting existing state.
    """
    user_id = 66601
    await adv_mgr.set_grudge_level(user_id, 3)

    invalid_inputs = ["not_a_number", None, [1], {"level": 5}, complex(1, 2)]
    for inv in invalid_inputs:
        with pytest.raises((ValueError, TypeError)):
            await adv_mgr.set_grudge_level(user_id, inv)

    # Verify dossier state was not corrupted and remains 3
    dossier = await adv_mgr.get_dossier(user_id)
    assert dossier["grudge_level"] == 3
    assert adv_mgr.metrics["grudge_levels"][str(user_id)] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 4. Anti-Repetition & History Slicing Stress
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_roast_history_circular_buffer_capping_at_15(adv_mgr):
    """
    Pumps 50 roasts into a single user dossier.
    Verifies that roast_history is strictly capped at the last 15 entries.
    """
    user_id = 12345
    for i in range(50):
        await adv_mgr.record_roast(
            user_id=user_id,
            username="Victim123",
            roast_text=f"Roast #{i}",
            dialect="riyadh",
            intensity=3
        )

    d = await adv_mgr.get_dossier(user_id)
    assert len(d["roast_history"]) == 15
    assert d["roast_history"][0]["roast_text"] == "Roast #35"
    assert d["roast_history"][-1]["roast_text"] == "Roast #49"

    recent = await adv_mgr.get_recent_roasts(user_id, limit=5)
    assert len(recent) == 5
    assert recent == [f"Roast #{i}" for i in range(45, 50)]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hybrid Thread + Coroutine Concurrency & Double Corruption Stress
# ─────────────────────────────────────────────────────────────────────────────

def test_recovery_double_corruption_state_and_backup_both_malformed(tmp_path):
    """
    Scenario: Worst-case catastrophe where BOTH primary state.json AND backup
    state.json.bak contain malformed/corrupted data.
    StateManager must safely quarantine and recover to DEFAULT_STATE without crashing.
    """
    state_file = tmp_path / "state.json"
    bak_file = tmp_path / "state.json.bak"

    with open(state_file, "w", encoding="utf-8") as f:
        f.write("CORRUPTED_PRIMARY_DATA_!@#$%^")
    with open(bak_file, "w", encoding="utf-8") as f:
        f.write("CORRUPTED_BACKUP_DATA_!@#$%^")

    mgr = StateManager(data_dir=str(tmp_path), state_filename="state.json")
    assert mgr.dossiers == {}
    assert mgr.metrics["current_dialect"] == "default"
    assert len(list(tmp_path.glob("state.json.corrupt.*"))) >= 1


@pytest.mark.asyncio
async def test_hybrid_threads_and_coroutines_concurrency(adv_mgr):
    """
    Stress-tests concurrent access from both OS threads executing synchronous shims
    (_sync_save_state_atomic) AND asyncio event loop coroutines executing save_state_atomic.
    Verifies no deadlocks between asyncio.Lock and threading.RLock, and no file corruption.
    """
    import threading

    sync_thread_errors = []

    def sync_worker(thread_id: int):
        try:
            for i in range(15):
                uid = 8000 + (thread_id * 10) + (i % 5)
                adv_mgr.add_crime(uid, f"Thread {thread_id} Crime {i}")
                adv_mgr.add_title(uid, f"Title {thread_id}_{i}")
                adv_mgr.add_excuse(uid, f"Excuse {thread_id}_{i}")
                time.sleep(0.005)
        except Exception as e:
            sync_thread_errors.append(e)

    # Spawn 4 background OS threads
    threads = [threading.Thread(target=sync_worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()

    # Simultaneously execute 60 async coroutines in the main event loop
    async def async_worker(idx: int):
        uid = 9000 + (idx % 10)
        await adv_mgr.add_infraction(uid, "ASYNC_CRIME", f"Async detail {idx}")
        await adv_mgr.set_grudge_level(uid, (idx % 5) + 1)
        await adv_mgr.record_roast(uid, f"User_{uid}", f"Roast {idx}", "default", 2)

    await asyncio.gather(*[async_worker(i) for i in range(60)])

    # Join OS threads
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), "Sync worker thread deadlocked!"

    assert len(sync_thread_errors) == 0, f"Thread errors: {sync_thread_errors}"

    # Verify disk persistence readability
    with open(adv_mgr.filepath, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert len(disk_data["dossiers"]) > 0
    assert len(disk_data["metrics"]["roast_log"]) == 60


@pytest.mark.asyncio
async def test_asyncio_concurrent_dossier_growth_during_save_race(adv_mgr):
    """
    Stress-tests pure asyncio concurrency: one coroutine calls save_state_atomic()
    (offloading json.dump to a thread pool worker), while concurrent coroutines dynamically
    ingest new user dossiers into memory.
    Exposes RuntimeError: dictionary changed size during iteration when json.dump
    iterates over live un-snapshotted memory dictionary.
    """
    # Pre-populate state so json.dump takes multiple chunks and yields GIL during file I/O
    for i in range(400):
        adv_mgr._state["dossiers"][str(i)] = {"id": i, "payload": [x for x in range(30)]}

    async def writer():
        await adv_mgr.save_state_atomic()

    async def mutator():
        for i in range(50):
            await asyncio.sleep(0.0001)
            await adv_mgr.get_dossier(50000 + i)

    await asyncio.gather(writer(), mutator())


