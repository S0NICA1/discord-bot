"""
tests/test_adversarial_m2_challenger.py - Empirical Challenger Stress Suite for Milestone 2

Adversarial testing of:
1. AFK_DEAFENED boundary stress testing (899s, 900s, 1200s, undeafen reset, muted-only)
2. RAGE_QUIT boundary stress testing (179s vs 181s post-roast, mid-speech populated vs empty VC)
3. STATUS_FRAUD debounce stress testing (100 rapid presence updates, 3600s debounce window)
4. Dossier formatting stress testing (missing keys, None values, malformed user IDs, extreme grudge values [-10, 100], empty lists, backward compatibility)
"""

import os
import time
from unittest.mock import MagicMock
import discord
import pytest

from modules.state_manager import StateManager, GRUDGE_TITLES
from tests.conftest import MockActivity, MockMember, MockGuild, MockVoiceChannel


@pytest.fixture
def challenger_bot(tmp_path):
    """
    Creates a hermetic, strictly isolated RoastBot test instance.
    Guarantees state_mgr and dossier_mgr point to an isolated temporary vault,
    preventing any pollution of production data/state.json.
    """
    from main import RoastBot
    bot = RoastBot()

    # Create isolated StateManager
    iso_mgr = StateManager(data_dir=str(tmp_path), state_filename="challenger_state.json")
    bot.state_mgr = iso_mgr
    bot.dossier_mgr = iso_mgr

    # Reset in-memory telemetry and caches
    bot.vc_join_times = {}
    bot.user_game_history = {}
    bot.daily_stats = {}
    bot.roast_log = []
    bot.voice_telemetry = {}
    bot.last_infraction_log = {}
    bot.roast_count_per_user = {}
    bot.daily_roast_counts = {}
    bot.hourly_vc_activity = [0] * 24
    bot.game_popularity = {}
    bot.grudge_levels = {}
    bot.protected_users = set()
    bot.last_roasted_user = None
    bot.last_roast_time = None
    bot.current_dialect = "default"

    # Mock guild & members
    guild = MockGuild(999888, "Challenger Guild")
    m1 = MockMember(8001, "TargetUser1", "TargetUser1")
    m2 = MockMember(8002, "TargetUser2", "TargetUser2")
    m3 = MockMember(8003, "TargetUser3", "TargetUser3")
    guild.add_member(m1)
    guild.add_member(m2)
    guild.add_member(m3)

    bot._mock_guilds = [guild]
    bot._mock_user = MockMember(999999, "MrRoastBot", "Mr. Roast 3.0", bot=True)
    RoastBot.guilds = property(lambda self: getattr(self, "_mock_guilds", []))
    RoastBot.user = property(lambda self: getattr(self, "_mock_user", None))

    def mock_get_channel(cid: int):
        for vc in guild.voice_channels:
            if vc.id == cid:
                return vc
        return guild.text_channels[0]

    bot.get_channel = mock_get_channel
    return bot


# ═══════════════════════════════════════════════════════════════════════════════
# 1. AFK_DEAFENED Boundary Stress Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_afk_deafened_boundary_899s(challenger_bot):
    """At 899s (< 900s threshold), voice_intel_loop MUST NOT flag AFK_DEAFENED."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    now = time.time()
    bot.vc_join_times[member.id] = now - 1000
    bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1000,
        "is_muted": True,
        "is_deafened": True,
        "is_streaming": False,
        "mute_start": now - 1000,
        "deafen_start": now - 899,  # Exactly 899s
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    await bot.voice_intel_loop.coro(bot)

    dossier = await bot.state_mgr.get_dossier(member.id)
    afk_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) == 0, f"Expected 0 infractions at 899s, found {len(afk_infs)}"
    assert bot.voice_telemetry[member.id]["afk_deafened_flagged"] is False


@pytest.mark.asyncio
async def test_afk_deafened_boundary_900s_exact(challenger_bot):
    """At exactly 900s (threshold), voice_intel_loop MUST flag AFK_DEAFENED exactly once."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    now = time.time()
    bot.vc_join_times[member.id] = now - 1000
    bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1000,
        "is_muted": True,
        "is_deafened": True,
        "is_streaming": False,
        "mute_start": now - 1000,
        "deafen_start": now - 900,  # Exactly 900s
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    await bot.voice_intel_loop.coro(bot)

    dossier = await bot.state_mgr.get_dossier(member.id)
    afk_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) == 1, f"Expected exactly 1 infraction at 900s, found {len(afk_infs)}"
    assert "صنم مسوي ميوت ودفن" in afk_infs[0]["detail"]
    assert bot.voice_telemetry[member.id]["afk_deafened_flagged"] is True


@pytest.mark.asyncio
async def test_afk_deafened_boundary_1200s_dedup(challenger_bot):
    """At 1200s (subsequent iterations), flagged flag prevents duplicate infraction logging."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    now = time.time()
    bot.vc_join_times[member.id] = now - 1500
    bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1500,
        "is_muted": True,
        "is_deafened": True,
        "is_streaming": False,
        "mute_start": now - 1500,
        "deafen_start": now - 900,
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    # First trigger at 900s
    await bot.voice_intel_loop.coro(bot)
    assert bot.voice_telemetry[member.id]["afk_deafened_flagged"] is True

    # Advance time to 1200s
    bot.voice_telemetry[member.id]["deafen_start"] = now - 1200
    await bot.voice_intel_loop.coro(bot)

    # Re-verify infraction count is still exactly 1
    dossier = await bot.state_mgr.get_dossier(member.id)
    afk_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) == 1, f"Expected duplicate protection, but found {len(afk_infs)} infractions"


@pytest.mark.asyncio
async def test_afk_deafened_undeafen_reset(challenger_bot):
    """Undeafening resets afk_deafened_flagged and deafen_start, allowing subsequent flagging."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    now = time.time()
    bot.vc_join_times[member.id] = now - 1000
    bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1000,
        "is_muted": True,
        "is_deafened": True,
        "is_streaming": False,
        "mute_start": now - 1000,
        "deafen_start": now - 900,
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    # 1. Flag initial infraction
    await bot.voice_intel_loop.coro(bot)
    assert bot.voice_telemetry[member.id]["afk_deafened_flagged"] is True

    # 2. Member undeafens in same channel
    before = MagicMock(channel=vc, self_mute=True, mute=False, self_deaf=True, deaf=False)
    after = MagicMock(channel=vc, self_mute=True, mute=False, self_deaf=False, deaf=False)
    await bot.on_voice_state_update(member, before, after)

    session = bot.voice_telemetry[member.id]
    assert session["afk_deafened_flagged"] is False
    assert session["deafen_start"] is None
    assert session["is_deafened"] is False

    # 3. Member deafens again
    before = MagicMock(channel=vc, self_mute=True, mute=False, self_deaf=False, deaf=False)
    after = MagicMock(channel=vc, self_mute=True, mute=False, self_deaf=True, deaf=False)
    await bot.on_voice_state_update(member, before, after)

    session = bot.voice_telemetry[member.id]
    assert session["is_deafened"] is True
    assert session["deafen_start"] is not None

    # Fast forward to 900s after new deafen
    session["deafen_start"] = time.time() - 900
    await bot.voice_intel_loop.coro(bot)

    # Should have flagged a second infraction
    dossier = await bot.state_mgr.get_dossier(member.id)
    afk_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) == 2, f"Expected 2 infractions after reset, found {len(afk_infs)}"


@pytest.mark.asyncio
async def test_afk_deafened_muted_only_not_flagged(challenger_bot):
    """A member who is muted for 1200s but NOT deafened MUST NOT be flagged AFK_DEAFENED."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members = [member]

    now = time.time()
    bot.vc_join_times[member.id] = now - 1200
    bot.voice_telemetry[member.id] = {
        "channel_id": vc.id,
        "channel_name": vc.name,
        "join_time": now - 1200,
        "is_muted": True,
        "is_deafened": False,  # Not deafened!
        "is_streaming": False,
        "mute_start": now - 1200,
        "deafen_start": None,
        "last_unmute_start": None,
        "total_unmuted_seconds": 0.0,
        "last_spoke_time": 0.0,
        "afk_deafened_flagged": False
    }

    await bot.voice_intel_loop.coro(bot)

    dossier = await bot.state_mgr.get_dossier(member.id)
    afk_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "AFK_DEAFENED"]
    assert len(afk_infs) == 0, f"Muted-only member should not be flagged AFK_DEAFENED"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. RAGE_QUIT Boundary Stress Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rage_quit_boundary_179s_post_roast(challenger_bot):
    """Disconnecting at 179s post-roast (<= 180s) MUST flag RAGE_QUIT."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    bot.vc_join_times[member.id] = now - 600
    bot.last_roasted_user = member.id
    bot.last_roast_time = now - 179  # 179 seconds ago

    bot.voice_telemetry[member.id] = {
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
        "last_spoke_time": 0.0,  # Not speaking recently
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [guild.members[1], member]
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await bot.on_voice_state_update(member, before, after)

    dossier = await bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) == 1, "Expected RAGE_QUIT at 179s post-roast"
    assert "انحاش وفصل من الفويس بعد قصف جبهته" in rq_infs[0]["detail"]


@pytest.mark.asyncio
async def test_rage_quit_boundary_181s_post_roast(challenger_bot):
    """Disconnecting at 181s post-roast (> 180s) MUST NOT flag post-roast RAGE_QUIT."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    bot.vc_join_times[member.id] = now - 600
    bot.last_roasted_user = member.id
    bot.last_roast_time = now - 181  # 181 seconds ago

    bot.voice_telemetry[member.id] = {
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
        "last_spoke_time": 0.0,  # Not speaking recently
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [guild.members[1], member]
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await bot.on_voice_state_update(member, before, after)

    dossier = await bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) == 0, f"Expected 0 RAGE_QUIT infractions at 181s post-roast, found {len(rq_infs)}"


@pytest.mark.asyncio
async def test_rage_quit_mid_speech_populated_vc(challenger_bot):
    """Mid-speech disconnect in a populated VC (other members present) MUST flag RAGE_QUIT."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    bot.vc_join_times[member.id] = now - 300  # 5 minutes (> 2 min)
    bot.last_roasted_user = None

    bot.voice_telemetry[member.id] = {
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
        "last_spoke_time": now - 10,  # Spoke 10s ago (<= 30s)
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = [guild.members[1], member]  # Other member present
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await bot.on_voice_state_update(member, before, after)

    dossier = await bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) == 1, "Expected mid-speech RAGE_QUIT in populated VC"
    assert "فصل المايك وخرج فجأة بنص السالفة" in rq_infs[0]["detail"]


@pytest.mark.asyncio
async def test_rage_quit_mid_speech_empty_vc_empty_list(challenger_bot):
    """Mid-speech disconnect in an empty VC (members=[]) MUST NOT flag RAGE_QUIT."""
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    bot.vc_join_times[member.id] = now - 300
    bot.last_roasted_user = None

    bot.voice_telemetry[member.id] = {
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
        "last_spoke_time": now - 10,
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    before.channel.members = []  # Empty VC
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await bot.on_voice_state_update(member, before, after)

    dossier = await bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) == 0, f"Expected 0 infractions in empty VC, found {len(rq_infs)}"


@pytest.mark.asyncio
async def test_rage_quit_mid_speech_alone_in_vc_audit(challenger_bot):
    """
    Adversarial Audit: What if before.channel.members contains only the disconnecting member?
    In Discord.py, before.channel.members before event completion may contain [member].
    `other_members_present = len(members_in_channel) >= 1` erroneously evaluates to True if member alone!
    We empirically test whether a user alone in VC ([member]) is falsely flagged for leaving an active discussion.
    """
    bot = challenger_bot
    guild = bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]

    now = time.time()
    bot.vc_join_times[member.id] = now - 300
    bot.last_roasted_user = None

    bot.voice_telemetry[member.id] = {
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
        "last_spoke_time": now - 10,
        "afk_deafened_flagged": False
    }

    before = MagicMock(channel=vc)
    # The member is the ONLY member in the VC! No other members exist!
    before.channel.members = [member]
    before.channel.name = vc.name
    after = MagicMock(channel=None)

    await bot.on_voice_state_update(member, before, after)

    # A member alone in VC has no audience; leaving should NOT be flagged as quitting mid-conversation with others!
    # However, main.py checks `len(members_in_channel) >= 1`, counting the departing member as another member present.
    dossier = await bot.state_mgr.get_dossier(member.id)
    rq_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "RAGE_QUIT"]
    assert len(rq_infs) == 0, (
        f"Exposed Bug in main.py:288-289: A member alone in VC ([member]) was falsely flagged "
        f"for RAGE_QUIT because `other_members_present = len(members_in_channel) >= 1` counts the disconnecting user themselves!"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. STATUS_FRAUD Debounce Stress Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_status_fraud_100_rapid_updates_debounce(challenger_bot):
    """
    Trigger 100 rapid presence updates with Study vs Gaming contradiction.
    Verify that EXACTLY 1 infraction is logged per hour (3600s debounce).
    """
    bot = challenger_bot
    guild = bot.guilds[0]
    member = guild.members[0]

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.online,
        activities=[
            MockActivity("مذاكرة فاينل مكثفة", discord.ActivityType.custom),
            MockActivity("Valorant", discord.ActivityType.playing)
        ]
    )

    # Fire 100 rapid presence updates in tight succession
    for _ in range(100):
        await bot.on_presence_update(pres_before, pres_after)

    dossier = await bot.state_mgr.get_dossier(member.id)
    fraud_infs = [inf for inf in dossier.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"]
    assert len(fraud_infs) == 1, f"Expected exactly 1 infraction after 100 updates, found {len(fraud_infs)}"


@pytest.mark.asyncio
async def test_status_fraud_debounce_window_expiry(challenger_bot):
    """
    Verify debounce behavior over time:
    - Update 1: Logged (count=1)
    - Update at T+3599s: Debounced (count=1)
    - Update at T+3601s: Logged (count=2)
    """
    bot = challenger_bot
    guild = bot.guilds[0]
    member = guild.members[0]

    pres_before = MagicMock(bot=False, activities=[])
    pres_after = MagicMock(
        bot=False,
        id=member.id,
        display_name=member.display_name,
        status=discord.Status.online,
        activities=[
            MockActivity("بذاكر لا أحد يزعجني", discord.ActivityType.custom),
            MockActivity("Roblox", discord.ActivityType.playing)
        ]
    )

    # 1. Initial trigger
    await bot.on_presence_update(pres_before, pres_after)
    d1 = await bot.state_mgr.get_dossier(member.id)
    count1 = len([inf for inf in d1.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])
    assert count1 == 1

    # 2. Advance to 3599 seconds (1 second BEFORE 3600s cooldown expires)
    bot.last_infraction_log[(member.id, "STATUS_FRAUD")] = time.time() - 3599
    await bot.on_presence_update(pres_before, pres_after)
    d2 = await bot.state_mgr.get_dossier(member.id)
    count2 = len([inf for inf in d2.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])
    assert count2 == 1, f"At 3599s, expected debounce to hold (count=1), but got {count2}"

    # 3. Advance to 3601 seconds (cooldown expired)
    bot.last_infraction_log[(member.id, "STATUS_FRAUD")] = time.time() - 3601
    await bot.on_presence_update(pres_before, pres_after)
    d3 = await bot.state_mgr.get_dossier(member.id)
    count3 = len([inf for inf in d3.get("infractions", []) if inf.get("type") == "STATUS_FRAUD"])
    assert count3 == 2, f"At 3601s, expected new infraction logged (count=2), got {count3}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Dossier Formatting Stress Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_dossier_formatting_missing_keys(challenger_bot):
    """format_context_for_roast MUST handle dossiers with missing keys without raising exceptions."""
    bot = challenger_bot
    mgr = bot.state_mgr

    # Inject bare minimum dict directly into memory state
    uid_str = "77771"
    mgr._state["dossiers"][uid_str] = {
        "user_id": 77771
        # titles, excuses, embarrassing_moments, crimes, infractions, voice_stats, grudge_level all missing
    }

    result = mgr.format_context_for_roast(77771)
    assert isinstance(result, str)
    assert "ملف سوابق واستخبارات الضحية" in result
    assert "[1/5]" in result
    assert "عضو تحت المراقبة" in result


def test_dossier_formatting_none_values(challenger_bot):
    """format_context_for_roast MUST handle None values gracefully or reveal edge cases."""
    bot = challenger_bot
    mgr = bot.state_mgr

    uid_str = "77772"
    mgr._state["dossiers"][uid_str] = {
        "user_id": 77772,
        "titles": None,
        "excuses": None,
        "embarrassing_moments": None,
        "crimes": None,
        "infractions": None,
        "voice_stats": None,
        "grudge_level": 1
    }

    # If voice_stats is None and live_voice_context is None:
    # v_stats = d.get("voice_stats", {}) -> evaluates to None
    # total_mins = v_stats.get("total_vc_minutes", 0) -> may crash if None!
    try:
        result = mgr.format_context_for_roast(77772)
        assert isinstance(result, str)
    except AttributeError as ex:
        pytest.fail(f"format_context_for_roast crashed on None voice_stats: {ex}")


def test_dossier_formatting_malformed_user_ids(challenger_bot):
    """format_context_for_roast handles non-numeric, negative, and string user IDs."""
    bot = challenger_bot
    mgr = bot.state_mgr

    test_ids = ["", "-12345", "corrupted_id_#$%", 0]
    for test_id in test_ids:
        result = mgr.format_context_for_roast(test_id)
        assert isinstance(result, str)
        assert "ملف سوابق واستخبارات الضحية" in result


def test_dossier_formatting_extreme_grudge_levels(challenger_bot):
    """format_context_for_roast strictly clamps grudge levels to [1, 5]."""
    bot = challenger_bot
    mgr = bot.state_mgr

    # Extreme low: -10
    mgr._state["dossiers"]["88881"] = {"user_id": 88881, "grudge_level": -10}
    res_low = mgr.format_context_for_roast(88881)
    assert "[1/5]" in res_low
    assert GRUDGE_TITLES[1] in res_low

    # Extreme high: 100
    mgr._state["dossiers"]["88882"] = {"user_id": 88882, "grudge_level": 100}
    res_high = mgr.format_context_for_roast(88882)
    assert "[5/5]" in res_high
    assert GRUDGE_TITLES[5] in res_high


def test_dossier_formatting_empty_lists_and_radar(challenger_bot):
    """format_context_for_roast handles empty lists and empty live voice radar gracefully."""
    bot = challenger_bot
    mgr = bot.state_mgr

    mgr._state["dossiers"]["88883"] = {
        "user_id": 88883,
        "grudge_level": 3,
        "titles": [],
        "excuses": [],
        "embarrassing_moments": [],
        "crimes": [],
        "infractions": [],
        "voice_stats": {
            "total_vc_minutes": 0,
            "total_unmuted_seconds": 0
        }
    }

    # Empty radar
    result = mgr.format_context_for_roast(88883, live_voice_context={})
    assert isinstance(result, str)
    assert "[3/5]" in result
    assert GRUDGE_TITLES[3] in result


def test_dossier_formatting_backward_compatibility(challenger_bot):
    """format_context_for_roast full backward-compatibility and rich formatting verification."""
    bot = challenger_bot
    mgr = bot.state_mgr
    uid = 88884

    mgr._state["dossiers"][str(uid)] = {
        "user_id": uid,
        "grudge_level": 5,
        "titles": ["نكبة السيرفر", "مجرم رانكات"],
        "excuses": ["الماوس علق", "أمي فصلت الراوتر"],
        "embarrassing_moments": ["مات بالزون مع درع 3"],
        "crimes": ["تخريب الرانك"],
        "infractions": [
            {"id": "1", "timestamp": time.time(), "type": "AFK_DEAFENED", "detail": "صنم 30 دقيقة"},
            {"id": "2", "timestamp": time.time(), "type": "STATUS_FRAUD", "detail": "نايم وهو يلعب"},
            {"id": "3", "timestamp": time.time(), "type": "RAGE_QUIT", "detail": "فصل بعد الجلد"}
        ],
        "voice_stats": {
            "total_vc_minutes": 185,
            "total_unmuted_seconds": 3000
        }
    }

    live_radar = {
        "channel_name": "روم السهارى",
        "minutes": 42,
        "muted": False,
        "deafened": False,
        "games": ["League of Legends"],
        "custom_status": "مشغول"
    }

    formatted = mgr.format_context_for_roast(uid, live_voice_context=live_radar)
    assert "[5/5]" in formatted
    assert GRUDGE_TITLES[5] in formatted
    assert "نكبة السيرفر" in formatted
    assert "سوابق نوم ودفن بالفويس" in formatted
    assert "تزوير الحالة والهروب" in formatted
    assert "هروب ريج كويت تكتيكي" in formatted
    assert "روم السهارى" in formatted
    assert "League of Legends" in formatted
    assert "الماوس علق" in formatted
    assert "مات بالزون مع درع 3" in formatted
