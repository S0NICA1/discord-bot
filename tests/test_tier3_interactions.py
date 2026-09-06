"""
test_tier3_interactions.py - Tier 3: Cross-Feature Interaction Tests for Mr. Roast 3.0

Tests multi-step cross-feature workflows and state flows:
1. Dossier Persistence -> Holographic Shame Card Generation Pipeline.
2. Court Indictment -> Community Voting -> Conviction Sentencing & Grudge Escalation.
3. Real-Time Voice Intelligence & Status Contradiction -> Personalized Roast Synthesis.
4. Cyber CLI Execution -> System Telemetry Synchronization -> Autonomous Protection Rules.
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord import app_commands

from tests.conftest import MockMember, MockTextChannel, MockGuild, MockInteraction, MockActivity


# ============================================================================
# 1. Dossier Persistence -> Shame Card Generation Pipeline
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_dossier_accumulation_to_shame_card(web_client, test_bot):
    """
    Workflow:
    1. Add excuses, titles, and server crimes to a member's dossier via API.
    2. Generate shame card via /api/shame_card.
    3. Verify generated SVG and metadata reflect the exact accumulated criminal history.
    """
    user_id = 1001

    # Step 1: Add items to dossier
    await web_client.post("/api/dossier/add", json={
        "member_id": user_id,
        "type": "title",
        "content": "زعيم الأصنام"
    })
    await web_client.post("/api/dossier/add", json={
        "member_id": user_id,
        "type": "excuse",
        "content": "النت علق في الفاينل"
    })
    await web_client.post("/api/dossier/add", json={
        "member_id": user_id,
        "type": "crime",
        "content": "سحبة جماعية في ليلة البطولة"
    })

    # Step 2: Request Shame Card
    resp = await web_client.post("/api/shame_card", json={
        "member_id": user_id,
        "dialect": "riyadh"
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True

    card_data = data["card_data"]
    svg = data["svg"]

    # Step 3: Assert cross-feature reflection
    assert card_data["title"] == "زعيم الأصنام"
    assert card_data["top_excuse"] == "النت علق في الفاينل"
    assert card_data["crime"] == "سحبة جماعية في ليلة البطولة"
    assert "زعيم الأصنام" in svg
    assert "سحبة جماعية" in svg


@pytest.mark.asyncio
async def test_interaction_dossier_persistence_across_restart(tmp_path):
    """
    Workflow:
    1. StateManager records user dossier infractions.
    2. Simulate server restart by creating a new StateManager pointing to same directory.
    3. Verify all recorded infractions and grudge scores survive intact.
    """
    from modules.state_manager import StateManager
    data_dir = tmp_path / "persist_test"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Initial session
    mgr1 = StateManager(data_dir=str(data_dir), state_filename="state.json")
    await mgr1.set_grudge_level(5001, 4)
    await mgr1.add_infraction(5001, "RAGE_QUIT", "غادر اللعبة والنتيجة تعادل")
    await mgr1.record_roast(5001, "Sami", "ذبة نارية", "riyadh", 4)

    # Simulated restart: create new manager instance from same disk file
    mgr2 = StateManager(data_dir=str(data_dir), state_filename="state.json")
    dossier = await mgr2.get_dossier(5001)

    assert dossier["grudge_level"] == 4
    assert len(dossier["infractions"]) == 1
    assert dossier["infractions"][0]["type"] == "RAGE_QUIT"
    assert len(dossier["roast_history"]) == 1
    assert dossier["roast_history"][0]["roast_text"] == "ذبة نارية"


# ============================================================================
# 2. Court Indictment -> Voting -> Grudge Update & Infraction Workflow
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_courtroom_trial_to_conviction_and_grudge(test_bot):
    """
    Workflow:
    1. A public trial is initiated on Discord via /court against Defendant (1001).
    2. Multiple jurors cast guilty votes via CourtVoteView.
    3. 90-second timeout fires: sentencing is executed.
    4. Verify:
       - Conviction announcement published to channel.
       - Defendant dossier is updated with conviction charge.
       - A sentencing roast is generated for the defendant.
    """
    from main import cmd_court, CourtVoteView
    guild = test_bot.guilds[0]
    defendant = guild.members[0]  # id 1001
    juror1 = guild.members[1]     # id 1002
    juror2 = guild.members[2]     # id 1003
    channel = guild.text_channels[0]

    interaction = MockInteraction(user=juror1, channel=channel, guild=guild)

    # Step 1: Start trial
    await cmd_court.callback(interaction, defendant=defendant, charge="تخريب الرانك والهروب المفاجئ")
    assert len(interaction.followup.sent_messages) == 1
    view = interaction.followup.sent_messages[0]["view"]
    assert isinstance(view, CourtVoteView)

    # Step 2: Jurors vote guilty
    btn_guilty = [c for c in view.children if c.custom_id == "vote_guilty"][0]
    i1 = MockInteraction(user=juror1, channel=channel, guild=guild)
    i2 = MockInteraction(user=juror2, channel=channel, guild=guild)
    await btn_guilty.callback(i1)
    await btn_guilty.callback(i2)

    assert len(view.guilty_votes) == 2

    # Step 3: Verdict timeout
    await view.on_timeout()

    # Step 4: Verify punishment execution
    assert len(channel.sent_messages) >= 1
    sent_text = "\n".join(m["content"] for m in channel.sent_messages)
    assert "ثبتت إدانة المتهم" in sent_text

    # Verify defendant dossier records the crime
    dossier = test_bot.dossier_mgr.get_user_dossier(defendant.id)
    assert "تخريب الرانك والهروب المفاجئ" in dossier["crimes"]


@pytest.mark.asyncio
async def test_interaction_web_court_start_to_discord_sync(web_client, test_bot):
    """
    Workflow:
    1. Start a court trial from the Web Dashboard via POST /api/court/start.
    2. Verify indictment is generated and sent to Discord channel with CourtVoteView.
    3. Verify active trial details are returned to web client.
    """
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    channel = guild.text_channels[0]

    payload = {
        "defendant_id": defendant.id,
        "charge": "النكبة في الجولة الحاسمة",
        "dialect": "jeddah"
    }

    resp = await web_client.post("/api/court/start", json=payload)
    assert resp.status == 200
    data = await resp.json()

    assert data["ok"] is True
    assert "indictment" in data
    assert len(channel.sent_messages) == 1
    assert "محاكمة علنية" in channel.sent_messages[0]["content"]
    assert channel.sent_messages[0]["view"] is not None


# ============================================================================
# 3. Voice Contradiction & Intelligence -> Roast Prompt Pipeline
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_voice_contradiction_injected_into_roast(test_bot):
    """
    Workflow:
    1. Member is active in voice channel.
    2. Member sets custom presence to "نايم" (sleeping) while in voice.
    3. Roast generation executes for this member.
    4. Verify status contradiction context is detected and injected into AI prompt.
    """
    guild = test_bot.guilds[0]
    target = guild.members[0]
    target.set_custom_status("نايم في العسل")
    target.voice.self_deaf = True

    channel = guild.text_channels[0]
    test_bot.vc_join_times[target.id] = time.time() - 3600  # 1 hour ago

    captured_prompts = []

    async def mock_gen(contents, **kwargs):
        captured_prompts.append(str(contents))
        mock_resp = MagicMock()
        mock_resp.text = "كاتب نايم وأنت مسوي دفن ومسهر بالسيرفر؟ تسوقها!"
        return mock_resp

    with patch("main.generate_content_ai", side_effect=mock_gen):
        roast_text = await test_bot.generate_roast_for_member(target, channel)

    assert roast_text is not None
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # Assert voice intelligence context extraction
    assert "نايم في العسل" in prompt
    assert "مسوي دفن" in prompt
    assert target.mention in channel.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_interaction_voice_gaming_activity_in_roast_context(test_bot):
    """
    Workflow:
    1. Member is active in voice playing "Valorant".
    2. Generate roast for member.
    3. Verify game name is captured and incorporated into roast context.
    """
    guild = test_bot.guilds[0]
    target = guild.members[1]
    target.set_playing("Valorant")
    test_bot.user_game_history[target.id] = {"Valorant"}

    channel = guild.text_channels[0]
    captured_prompts = []

    async def mock_gen(contents, **kwargs):
        captured_prompts.append(str(contents))
        mock_resp = MagicMock()
        mock_resp.text = "تلعب فالورانت وإيمك في السماء؟"
        return mock_resp

    with patch("main.generate_content_ai", side_effect=mock_gen):
        await test_bot.generate_roast_for_member(target, channel)

    assert len(captured_prompts) == 1
    assert "Valorant" in captured_prompts[0]


# ============================================================================
# 4. Web CLI -> System State -> Telemetry & Protection Rules
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_cli_dialect_switch_propagates_to_telemetry(web_client, test_bot):
    """
    Workflow:
    1. Switch dialect to 'qassim' via Cyber CLI.
    2. Check GET /api/stats telemetry.
    3. Verify active dialect across system is now 'qassim'.
    """
    # Step 1: CLI execute
    resp1 = await web_client.post("/api/cli/execute", json={"command": "dialect qassim"})
    assert resp1.status == 200
    data1 = await resp1.json()
    assert data1["ok"] is True
    assert "Qassim" in data1["output"] or "القصيم" in data1["output"]

    # Step 2: Query stats
    resp2 = await web_client.get("/api/stats")
    data2 = await resp2.json()
    assert data2["current_dialect"] == "qassim"


@pytest.mark.asyncio
async def test_interaction_cli_protect_prevents_random_roast(web_client, test_bot):
    """
    Workflow:
    1. Member 1001 is added to protection immunity via CLI.
    2. force_random_roast is triggered.
    3. Verify member 1001 is NEVER selected while protected.
    """
    guild = test_bot.guilds[0]
    channel = guild.text_channels[0]
    vc = guild.voice_channels[0]
    m1 = guild.members[0]  # id 1001
    m2 = guild.members[1]  # id 1002
    vc.members.append(m1)
    vc.members.append(m2)

    # Protect m1 via CLI
    await web_client.post("/api/cli/execute", json={"command": f"protect {m1.id}"})
    assert m1.id in test_bot.protected_users

    # Run random roast multiple times
    for _ in range(5):
        await test_bot.force_random_roast(channel)

    # Verify m1 was never roasted
    for msg in channel.sent_messages:
        assert m1.mention not in msg["content"]
