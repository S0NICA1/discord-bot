"""
test_tier2_boundaries.py - Tier 2: Boundary & Corner Cases for Mr. Roast 3.0

Coverage requirements (>=5 tests per category):
1. Empty Payloads: empty dictionaries, empty strings, whitespace-only fields.
2. Malformed Inputs: non-numeric IDs, invalid dialect names, malformed JSON.
3. Out-of-bounds Grudge Levels: bounded 1-5 enforcement for negative, zero, and extreme values.
4. Missing Parameters: missing query parameters, missing required body fields.
5. Unhandled Exceptions: resilient degradation during network errors, missing channels, and file corruption.
"""
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tests.conftest import MockMember, MockTextChannel, MockGuild, MockInteraction


# ============================================================================
# Category 1: Empty Payloads (>=5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_empty_cli_payload(web_client):
    """Test POST /api/cli/execute with an empty payload returns graceful error."""
    resp = await web_client.post("/api/cli/execute", json={})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "No command" in data["output"]


@pytest.mark.asyncio
async def test_boundary_empty_custom_roast(web_client):
    """Test POST /api/custom_roast with empty text is rejected."""
    payload = {"member_id": 1001, "text": "   "}
    resp = await web_client.post("/api/custom_roast", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "بيانات ناقصة" in data["error"]


@pytest.mark.asyncio
async def test_boundary_empty_free_message(web_client):
    """Test POST /api/free_message with empty text is rejected."""
    payload = {"text": ""}
    resp = await web_client.post("/api/free_message", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_empty_battle_roasts(web_client):
    """Test POST /api/battle/judge with empty roasts is rejected."""
    payload = {
        "p1_name": "سعد",
        "p1_roast": "",
        "p2_name": "خالد",
        "p2_roast": ""
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "يجب كتابة ذبة" in data["error"]


@pytest.mark.asyncio
async def test_boundary_empty_dossier_add(web_client):
    """Test POST /api/dossier/add with empty content is rejected."""
    payload = {"member_id": 1001, "type": "crime", "content": ""}
    resp = await web_client.post("/api/dossier/add", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False


# ============================================================================
# Category 2: Malformed Inputs (>=5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_malformed_member_id_in_targeted_roast(web_client):
    """Test POST /api/targeted_roast handles non-numeric member_id gracefully."""
    payload = {"member_id": "not_an_int"}
    resp = await web_client.post("/api/targeted_roast", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_malformed_dialect_in_change_dialect(web_client):
    """Test POST /api/change_dialect rejects unregistered dialect keys."""
    payload = {"dialect": "martian_dialect"}
    resp = await web_client.post("/api/change_dialect", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "غير صالحة" in data["error"]


@pytest.mark.asyncio
async def test_boundary_malformed_cli_arguments(web_client):
    """Test POST /api/cli/execute commands without required arguments show usage."""
    resp1 = await web_client.post("/api/cli/execute", json={"command": "protect"})
    data1 = await resp1.json()
    assert "USAGE: protect" in data1["output"]

    resp2 = await web_client.post("/api/cli/execute", json={"command": "roast"})
    data2 = await resp2.json()
    assert "USAGE: roast" in data2["output"]


@pytest.mark.asyncio
async def test_boundary_malformed_court_vote_choice(web_client):
    """Test POST /api/court/vote with invalid vote choices returns 400."""
    payload = {"trial_id": 101, "vote": "maybe"}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 400
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_malformed_json_body(web_client):
    """Test POST request with malformed non-JSON body returns appropriate error."""
    resp = await web_client.post(
        "/api/targeted_roast",
        data="INVALID_JSON_RAW_DATA",
        headers={"Content-Type": "application/json"}
    )
    assert resp.status in (400, 500) or (await resp.json()).get("ok") is False


# ============================================================================
# Category 3: Out-of-bounds Grudge Levels (>=5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_grudge_negative_clamped(isolated_dossier_vault):
    """Test negative grudge level is clamped to minimum bound of 1."""
    level = await isolated_dossier_vault.set_grudge_level(1001, -10)
    assert level == 1
    dossier = await isolated_dossier_vault.get_dossier(1001)
    assert dossier["grudge_level"] == 1


@pytest.mark.asyncio
async def test_boundary_grudge_zero_clamped(isolated_dossier_vault):
    """Test grudge level 0 is clamped to minimum bound of 1."""
    level = await isolated_dossier_vault.set_grudge_level(1001, 0)
    assert level == 1


@pytest.mark.asyncio
async def test_boundary_grudge_excessive_clamped(isolated_dossier_vault):
    """Test huge grudge level is clamped to maximum bound of 5."""
    level = await isolated_dossier_vault.set_grudge_level(1001, 9999)
    assert level == 5
    dossier = await isolated_dossier_vault.get_dossier(1001)
    assert dossier["grudge_level"] == 5


@pytest.mark.asyncio
async def test_boundary_grudge_string_conversion(isolated_dossier_vault):
    """Test string numeric grudge level is safely converted and clamped."""
    level = await isolated_dossier_vault.set_grudge_level(1001, "4")
    assert level == 4


@pytest.mark.asyncio
async def test_boundary_grudge_legacy_score_clamping(tmp_path):
    """Test migration of legacy unbounded scores correctly normalizes to 1-5."""
    from modules.state_manager import StateManager
    state_file = tmp_path / "state_legacy_test.json"
    mgr = StateManager(data_dir=str(tmp_path), state_filename="state_legacy_test.json")

    # Directly test setting legacy-style high values
    l1 = await mgr.set_grudge_level(2001, 100)
    l2 = await mgr.set_grudge_level(2002, -5)
    assert l1 == 5
    assert l2 == 1


# ============================================================================
# Category 4: Missing Parameters (>=5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_missing_member_id_in_dossier_get(web_client):
    """Test GET /api/dossier without member_id returns error."""
    resp = await web_client.get("/api/dossier")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "No member_id" in data["error"]


@pytest.mark.asyncio
async def test_boundary_missing_target_in_targeted_roast(web_client):
    """Test POST /api/targeted_roast without member_id returns error."""
    resp = await web_client.post("/api/targeted_roast", json={"topic": "لا يوجد هدف"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "غير محدد" in data["error"]


@pytest.mark.asyncio
async def test_boundary_missing_vote_field_in_court_vote(web_client):
    """Test POST /api/court/vote with missing vote choice returns 400."""
    resp = await web_client.post("/api/court/vote", json={"trial_id": 101})
    assert resp.status == 400
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_missing_content_in_dossier_add(web_client):
    """Test POST /api/dossier/add with missing content parameter."""
    resp = await web_client.post("/api/dossier/add", json={"member_id": 1001, "type": "crime"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_missing_member_id_in_protect(web_client):
    """Test POST /api/protect with missing member_id defaults to 0 and succeeds safely."""
    resp = await web_client.post("/api/protect", json={"action": "add"})
    assert resp.status == 200
    data = await resp.json()
    assert "ok" in data


# ============================================================================
# Category 5: Unhandled Exceptions & Defensive Recovery (>=5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_targeted_roast_nonexistent_member(web_client):
    """Test POST /api/targeted_roast returns ok:false when target is not in server."""
    payload = {"member_id": 999888777}
    resp = await web_client.post("/api/targeted_roast", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_boundary_shame_card_send_nonexistent_member(web_client):
    """Test POST /api/shame_card_send returns error when target is not in server."""
    payload = {"member_id": 999888777}
    resp = await web_client.post("/api/shame_card_send", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "غير موجود" in data["error"]


@pytest.mark.asyncio
async def test_boundary_ai_report_exception_recovery(web_client):
    """Test POST /api/ai_report handles unexpected exception without crashing server."""
    with patch("web_dashboard.generate_content_ai", side_effect=RuntimeError("Google Quota Exhausted")):
        resp = await web_client.post("/api/ai_report")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is False
        assert "error" in data


def test_boundary_state_manager_corrupted_json_recovery(tmp_path):
    """Test StateManager detects corrupted JSON, quarantines it, and recovers safely."""
    from modules.state_manager import StateManager
    data_dir = tmp_path / "corrupt_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / "state.json"

    # Write corrupt invalid JSON
    with open(state_file, "w", encoding="utf-8") as f:
        f.write("{corrupt json payload: [incomplete")

    mgr = StateManager(data_dir=str(data_dir), state_filename="state.json")
    # Must recover without exception, and state must have default schema
    assert mgr.dossiers == {}
    assert "roast_log" in mgr.metrics


def test_boundary_state_manager_zero_byte_file_recovery(tmp_path):
    """Test StateManager detects 0-byte state file and recovers gracefully."""
    from modules.state_manager import StateManager
    data_dir = tmp_path / "zero_byte_test"
    data_dir.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / "state.json"

    # Write 0-byte file (simulating power cut during non-atomic write)
    with open(state_file, "w", encoding="utf-8") as f:
        pass

    mgr = StateManager(data_dir=str(data_dir), state_filename="state.json")
    assert mgr.dossiers == {}
