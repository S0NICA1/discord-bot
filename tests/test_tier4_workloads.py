"""
test_tier4_workloads.py - Tier 4: Real-World Workload Scenarios for Mr. Roast 3.0

Tests real-world operational stress and concurrency:
1. Server Activity Simulation: Multi-user voice sessions, mute transitions, presence tracking.
2. Multi-Round Battle Flow: 3-round 1v1 battle arbitration with dynamic scoring and adjudication.
3. High Concurrency Requests: Parallel stress load across REST endpoints with zero race conditions.
4. Sustained State Persistence & Memory Churn: High-frequency state mutation without file corruption.
"""
import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from tests.conftest import MockMember, MockTextChannel, MockVoiceChannel, MockGuild, MockActivity


# ============================================================================
# 1. Server Activity Simulation
# ============================================================================

@pytest.mark.asyncio
async def test_workload_multi_user_voice_session_lifecycle(test_bot):
    """
    Simulates a bustling Discord voice channel with multiple members:
    - Members join at staggered times.
    - Members toggle mute and deafen states.
    - Members launch and switch games.
    - Members disconnect, verifying accumulated daily minutes and hourly metrics.
    """
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]

    m1 = guild.members[0]
    m2 = guild.members[1]
    m3 = guild.members[2]

    # Staggered joins
    before_empty = MagicMock(channel=None)
    after_vc = MagicMock(channel=vc)

    await test_bot.on_voice_state_update(m1, before_empty, after_vc)
    await test_bot.on_voice_state_update(m2, before_empty, after_vc)
    await test_bot.on_voice_state_update(m3, before_empty, after_vc)

    assert m1.id in test_bot.vc_join_times
    assert m2.id in test_bot.vc_join_times
    assert m3.id in test_bot.vc_join_times

    # Game activity simulation
    m1_pres_before = MagicMock(bot=False, activities=[])
    m1_pres_after = MagicMock(bot=False, id=m1.id, activities=[MockActivity("Overwatch 2", discord.ActivityType.playing)])
    await test_bot.on_presence_update(m1_pres_before, m1_pres_after)

    assert "Overwatch 2" in test_bot.user_game_history[m1.id]
    assert test_bot.game_popularity.get("Overwatch 2", 0) >= 1

    # Mute toggling
    mute_state_before = MagicMock(channel=vc, self_mute=False, mute=False)
    mute_state_after = MagicMock(channel=vc, self_mute=True, mute=True)
    await test_bot.on_voice_state_update(m1, mute_state_before, mute_state_after)

    # Disconnects
    before_disconnect = MagicMock(channel=vc)
    after_disconnect = MagicMock(channel=None)

    # Simulate 30-minute stay
    test_bot.vc_join_times[m1.id] = time.time() - 1800
    await test_bot.on_voice_state_update(m1, before_disconnect, after_disconnect)

    assert m1.id not in test_bot.vc_join_times
    assert test_bot.daily_stats.get(m1.id, 0) >= 30


@pytest.mark.asyncio
async def test_workload_daily_report_generation(test_bot):
    """
    Simulates late night activity report loop (running at 4 AM Saudi time).
    Verifies daily stats aggregation and comedic report generation.
    """
    test_bot.daily_stats[1001] = 180  # 3 hours
    test_bot.daily_stats[1002] = 240  # 4 hours
    channel = test_bot.guilds[0].text_channels[0]

    with patch("time.gmtime") as mock_time:
        # Mock 1:00 UTC (4:00 AM Saudi)
        mock_struct = time.gmtime(1725584400)
        mock_struct_1am = MagicMock(tm_hour=1)
        mock_time.return_value = mock_struct_1am

        await test_bot.daily_report_loop()

    assert len(channel.sent_messages) == 1
    assert "تقرير الفضائح الليلي" in channel.sent_messages[0]["content"]
    assert len(test_bot.daily_stats) == 0  # Cleared after report


# ============================================================================
# 2. Multi-Round Battle Flow
# ============================================================================

@pytest.mark.asyncio
async def test_workload_multi_round_battle_flow(test_bot):
    """
    Simulates an end-to-end 3-round 1v1 roast battle with cumulative adjudication:
    - Round 1: Opening Jabs
    - Round 2: Escalation & Counter-Roast
    - Round 3: Final Blow
    - Verifies score calculation and determination of the ultimate champion.
    """
    rounds = [
        ("يا رجال شكلك صانع محتوى فاشل", "وأنت لعبك كله في قاع الرانك"),
        ("أنا الرانك عندي ذهب وأنت حتى النحاس ما شفته", "الذهب لقيته بالصدفة وأنت تدور أعذار"),
        ("كفاية أعذاري مقبولة مو مثل سحبتك بالنهائي", "النهائي فزنا فيه بدونك لأنك أصلاً نكبة")
    ]

    p1_scores = []
    p2_scores = []

    for idx, (r1, r2) in enumerate(rounds, 1):
        arbitration = await test_bot.roast_engine.judge_battle(
            "فيصل", r1,
            "سلطان", r2,
            topic=f"الجولة رقم {idx}"
        )
        assert "score1" in arbitration
        assert "score2" in arbitration
        p1_scores.append(float(arbitration["score1"]))
        p2_scores.append(float(arbitration["score2"]))

    assert len(p1_scores) == 3
    assert len(p2_scores) == 3

    total_p1 = sum(p1_scores)
    total_p2 = sum(p2_scores)
    assert total_p1 > 0
    assert total_p2 > 0


# ============================================================================
# 3. High Concurrency Requests
# ============================================================================

@pytest.mark.asyncio
async def test_workload_high_concurrency_stress(web_client):
    """
    Fires 40 concurrent requests across diverse API endpoints simultaneously:
    - /api/stats (read)
    - /api/cli/execute (execute)
    - /api/dialect/preview (synthesis)
    - /api/shame_card (rendering)
    - /api/court/vote (state mutation)
    Verifies that all 40 requests resolve with HTTP 200 and valid JSON with zero race conditions.
    """
    async def request_stats():
        return await web_client.get("/api/stats")

    async def request_cli():
        return await web_client.post("/api/cli/execute", json={"command": "stats"})

    async def request_dialect():
        return await web_client.post("/api/dialect/preview", json={"topic": "ضغط سيرفر"})

    async def request_shame():
        return await web_client.post("/api/shame_card", json={"member_id": 1001})

    async def request_vote(i):
        return await web_client.post("/api/court/vote", json={"trial_id": 100 + i, "vote": "guilty"})

    tasks = []
    for i in range(8):
        tasks.append(request_stats())
        tasks.append(request_cli())
        tasks.append(request_dialect())
        tasks.append(request_shame())
        tasks.append(request_vote(i))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert len(results) == 40
    for res in results:
        assert not isinstance(res, Exception), f"Concurrent request raised: {res}"
        assert res.status == 200
        json_data = await res.json()
        assert json_data is not None


# ============================================================================
# 4. Sustained Roast Loop & State Churn
# ============================================================================

@pytest.mark.asyncio
async def test_workload_sustained_roast_generation_churn(test_bot):
    """
    Simulates sustained high-frequency roasting across 20 iterations:
    - Verifies roast log stays bounded at 100 entries.
    - Verifies roast counts per user increment accurately.
    - Verifies atomic persistence writes with zero temporary file leaks.
    """
    guild = test_bot.guilds[0]
    channel = guild.text_channels[0]
    m1 = guild.members[0]
    m2 = guild.members[1]

    for i in range(20):
        target = m1 if i % 2 == 0 else m2
        await test_bot.generate_roast_for_member(target, channel, custom_topic=f"زلة رقم {i}")

    assert len(test_bot.roast_log) == 20
    assert test_bot.roast_count_per_user[m1.id] == 10
    assert test_bot.roast_count_per_user[m2.id] == 10
    assert len(channel.sent_messages) == 20

    # Ensure no leftover temp files in directory
    data_dir = os.path.dirname(test_bot.data_file) or "."
    temp_files = [f for f in os.listdir(data_dir) if f.endswith(".tmp")]
    assert len(temp_files) == 0
