"""
tests/test_voice_intel.py - Comprehensive Unit Tests for Real-Time Voice Intelligence & Contradiction Engine
Covers:
1. AFK_DEAFENED Detection via voice_intel_loop (>15 min muted & deafened)
2. RAGE_QUIT Detection Case A: Disconnecting within 180s post-roast
3. RAGE_QUIT Detection Case B: Disconnecting mid-speech in populated VC
4. STATUS_FRAUD: Study/Work vs Gaming
5. STATUS_FRAUD: Sleep vs Active Voice / Gaming
6. STATUS_FRAUD: Offline/Busy Invisibility Fraud while talking
7. STATUS_FRAUD Debounce Cooldown (3600s anti-spam)
8. Contextual Dossier Formatting (Grudge scale 1-5, titles, categorized infractions, radar)
9. Cumulative Voice Stats persistence into permanent dossier
"""

import time
from unittest.mock import MagicMock

import discord
import pytest

from modules.state_manager import GRUDGE_TITLES, state_mgr
from tests.conftest import MockActivity, MockMember


@pytest.mark.asyncio
async def test_afk_deafened_detection(test_bot):
    """Verify voice_intel_loop detects and logs members muted & deafened >= 15 min."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    # Put member in VC
    now = time.time()
    test_bot.vc_join_times[member.id] = now - 1200
    test_bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1200,
        "is_muted": True,
        "is_deafened": True,
        "is_streaming": False,
        "mute_start": now - 1000,
        "deafen_start": now - 950,  # 950s > 900s (15 min)
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    # Execute voice_intel_loop iteration directly
    await test_bot.voice_intel_loop.coro(test_bot)

    # Verify infraction logged
    dossier = await test_bot.state_mgr.get_dossier(member.id)
    infractions = dossier.get("infractions", [])
    afk_infs = [inf for inf in infractions if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) >= 1
    assert "صنم مسوي ميوت ودفن" in afk_infs[0]["detail"]
    assert test_bot.voice_telemetry[member.id]["afk_deafened_flagged"] is True

    # Re-run loop: verify flag prevents duplicate logging
    await test_bot.voice_intel_loop.coro(test_bot)
    dossier_recheck = await test_bot.state_mgr.get_dossier(member.id)
    afk_infs_2 = [inf for inf in dossier_recheck.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs_2) == len(afk_infs)


@pytest.mark.asyncio
async def test_rage_quit_post_roast(test_bot):
    """Verify disconnecting within 180s of being roasted flags RAGE_QUIT."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[1]

    now = time.time()
    test_bot.vc_join_times[member.id] = now - 600
    test_bot.last_roasted_user = member.id
    test_bot.last_roast_time = now - 45  # 45 seconds ago (< 180s)

    test_bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 600,
        "is_muted": False,
        "is_deafened": False,
        "is_streaming": False,
        "mute_start": None,
        "deafen_start": None,
        "last_unmute_start": now - 600,
        "total_unmuted_seconds": 600.0,
        "last_spoke_time": now - 50,
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [guild.members[0], member]
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await test_bot.on_voice_state_update(member, before, after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) >= 1
    assert "انحاش وفصل من الفويس بعد قصف جبهته" in rq_infs[-1]["detail"]


@pytest.mark.asyncio
async def test_rage_quit_mid_speech(test_bot):
    """Verify disconnecting mid-speech in populated VC flags RAGE_QUIT."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[2]

    now = time.time()
    test_bot.vc_join_times[member.id] = now - 300  # 5 minutes in VC
    test_bot.last_roasted_user = None  # Not roasted recently

    test_bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 300,
        "is_muted": False,
        "is_deafened": False,
        "is_streaming": False,
        "mute_start": None,
        "deafen_start": None,
        "last_unmute_start": now - 300,
        "total_unmuted_seconds": 300.0,
        "last_spoke_time": now - 10,  # Spoke 10s ago (< 30s)
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [guild.members[0], member]
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await test_bot.on_voice_state_update(member, before, after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) >= 1
    assert "فصل المايك وخرج فجأة بنص السالفة" in rq_infs[-1]["detail"]


@pytest.mark.asyncio
async def test_status_fraud_study_vs_gaming(test_bot):
    """Verify claiming to study while actively gaming auto-logs STATUS_FRAUD."""
    guild = test_bot.guilds[0]
    member = guild.members[0]

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.online,
        activities=[
            MockActivity("فاينل ومذاكرة مكثفة", discord.ActivityType.custom),
            MockActivity("Valorant", discord.ActivityType.playing)
        ]
    )

    await test_bot.on_presence_update(pres_before, pres_after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    fraud_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"]
    assert len(fraud_infs) >= 1
    assert "فاينل ومذاكرة مكثفة" in fraud_infs[-1]["detail"]
    assert "Valorant" in fraud_infs[-1]["detail"]


@pytest.mark.asyncio
async def test_status_fraud_sleep_vs_voice(test_bot):
    """Verify claiming sleep while active in VC auto-logs STATUS_FRAUD."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[1]

    # Member is in voice
    test_bot.vc_join_times[member.id] = time.time() - 1800
    test_bot.voice_telemetry[member.id] = {"channel_name": vc.name, "is_muted": False}

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.online,
        activities=[
            MockActivity("نايم لحد يزعجني", discord.ActivityType.custom)
        ]
    )

    await test_bot.on_presence_update(pres_before, pres_after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    fraud_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"]
    assert len(fraud_infs) >= 1
    assert "نايم لحد يزعجني" in fraud_infs[-1]["detail"]
    assert "مسهر ومسنتر" in fraud_infs[-1]["detail"]


@pytest.mark.asyncio
async def test_status_fraud_invisibility_fraud(test_bot):
    """Verify invisible (offline) status while talking unmuted logs STATUS_FRAUD."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[2]

    test_bot.vc_join_times[member.id] = time.time() - 900
    test_bot.voice_telemetry[member.id] = {"channel_name": vc.name, "is_muted": False}

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.offline,  # Invisible
        activities=[
            MockActivity("مشغول خارج التغطية", discord.ActivityType.custom)
        ]
    )

    await test_bot.on_presence_update(pres_before, pres_after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    fraud_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"]
    assert len(fraud_infs) >= 1
    assert "أوفلاين ومختفي" in fraud_infs[-1]["detail"]
    assert "ماسك خط سوالف" in fraud_infs[-1]["detail"]


@pytest.mark.asyncio
async def test_status_fraud_debounce_cooldown(test_bot):
    """Verify 3600-second debounce prevents duplicate infraction spamming."""
    guild = test_bot.guilds[0]
    member = guild.members[0]

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.online,
        activities=[
            MockActivity("بذاكر فاينل", discord.ActivityType.custom),
            MockActivity("Roblox", discord.ActivityType.playing)
        ]
    )

    # First trigger: should log
    await test_bot.on_presence_update(pres_before, pres_after)
    d1 = await test_bot.state_mgr.get_dossier(member.id)
    count1 = len([inf for inf in d1.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])

    # Immediate second trigger: should be debounced
    await test_bot.on_presence_update(pres_before, pres_after)
    d2 = await test_bot.state_mgr.get_dossier(member.id)
    count2 = len([inf for inf in d2.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])
    assert count1 == count2

    # Fast forward debounce timestamp by 3601 seconds
    test_bot.last_infraction_log[(member.id, "STATUS_FRAUD")] = time.time() - 3601
    await test_bot.on_presence_update(pres_before, pres_after)
    d3 = await test_bot.state_mgr.get_dossier(member.id)
    count3 = len([inf for inf in d3.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])
    assert count3 == count1 + 1


@pytest.mark.asyncio
async def test_format_context_for_roast_formatting(test_bot):
    """Verify format_context_for_roast integrates grudge 1-5, titles, infractions, radar, excuses."""
    uid = 999111222
    await test_bot.state_mgr.set_grudge_level(uid, 4)
    await test_bot.state_mgr.update_dossier(uid, {
        "titles": ["نكبة الرانكات", "ملك التصريفات"],
        "excuses": ["الماوس علق", "النت فصل"],
        "embarrassing_moments": ["مات من الزون وهو يلوت"]
    })
    await test_bot.state_mgr.add_infraction(uid, "AFK_DEAFENED", "صنم لمدة 25 دقيقة")
    await test_bot.state_mgr.add_infraction(uid, "STATUS_FRAUD", "كاتب بذاكر وهو يلعب فالو")
    await test_bot.state_mgr.add_infraction(uid, "RAGE_QUIT", "فصل المايك وانحاش")

    live_telemetry = {
        "channel_name": "العام",
        "minutes": 45,
        "muted": False,
        "deafened": True,
        "streaming": False,
        "games": ["Valorant"],
        "custom_status": "نايم"
    }

    formatted = test_bot.state_mgr.format_context_for_roast(uid, live_voice_context=live_telemetry)

    # 1. Grudge & Title verification
    assert "[4/5]" in formatted
    assert GRUDGE_TITLES[4] in formatted
    assert "نكبة الرانكات" in formatted

    # 2. Categorized Infractions verification
    assert "سوابق نوم ودفن بالفويس" in formatted
    assert "تزوير الحالة والهروب" in formatted
    assert "هروب ريج كويت تكتيكي" in formatted

    # 3. Live Radar verification
    assert "متواجد في روم 'العام' منذ 45 دقيقة" in formatted
    assert "مسوي دفن (أصم)" in formatted
    assert "Valorant" in formatted
    assert "نايم" in formatted

    # 4. Excuses & moments verification
    assert "الماوس علق" in formatted
    assert "مات من الزون وهو يلوت" in formatted


@pytest.mark.asyncio
async def test_voice_stats_persistence_on_disconnect(test_bot):
    """Verify leaving a voice channel accumulates minutes and unmuted seconds in dossier voice_stats."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    test_bot.vc_join_times[member.id] = now - 2700  # 45 minutes
    test_bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 2700,
        "is_muted": True,
        "is_deafened": False,
        "is_streaming": False,
        "mute_start": now - 300,
        "deafen_start": None,
        "last_unmute_start": None,
        "total_unmuted_seconds": 420.0,
        "last_spoke_time": now - 310,
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [member]
    after = MagicMock(channel=None)

    await test_bot.on_voice_state_update(member, before, after)

    dossier = await test_bot.state_mgr.get_dossier(member.id)
    v_stats = dossier.get("voice_stats", {})
    assert v_stats.get("total_vc_minutes", 0) >= 45
    assert v_stats.get("total_unmuted_seconds", 0) >= 420
