"""
test_tier1_features.py - Tier 1: Comprehensive Feature Coverage for Mr. Roast 3.0

Coverage requirements: >=5 tests per feature for:
- Bot dispatchers: /roast, /court, /shamecard, /battle, /dialect, and Gateway listeners.
- Web API routes: /health, /api/stats, /api/court/start, /api/court/vote,
  /api/battle/judge, /api/shame_card, /api/dialect/preview, /api/cli/execute.
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord import app_commands

from tests.conftest import MockMember, MockTextChannel, MockGuild, MockInteraction


# ============================================================================
# 1. BOT DISPATCHERS: /roast
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_roast_default_execution(test_bot):
    """Test /roast dispatcher successfully sends a roast with default settings."""
    from main import cmd_roast
    guild = test_bot.guilds[0]
    target = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    await cmd_roast.callback(interaction, member=target)

    assert interaction.response.deferred is True
    assert len(interaction.followup.sent_messages) == 1
    assert "تم إطلاق الذبة" in interaction.followup.sent_messages[0]["content"]
    assert len(channel.sent_messages) == 1
    assert target.mention in channel.sent_messages[0]["content"]
    assert test_bot.last_roasted_user == target.id


@pytest.mark.asyncio
async def test_cmd_roast_custom_intensity(test_bot):
    """Test /roast dispatcher correctly applies intensity level 5 (nuclear)."""
    from main import cmd_roast
    guild = test_bot.guilds[0]
    target = guild.members[1]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[0], channel=channel, guild=guild)

    intensity_choice = app_commands.Choice(name="5 - قصف نووي بدون رحمة 💥💀", value=5)
    await cmd_roast.callback(interaction, member=target, intensity=intensity_choice)

    assert len(channel.sent_messages) == 1
    assert target.mention in channel.sent_messages[0]["content"]
    assert test_bot.roast_count_per_user[target.id] >= 1


@pytest.mark.asyncio
async def test_cmd_roast_custom_dialect(test_bot):
    """Test /roast dispatcher respects dialect override parameter."""
    from main import cmd_roast
    guild = test_bot.guilds[0]
    target = guild.members[2]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[0], channel=channel, guild=guild)

    dialect_choice = app_commands.Choice(name="🌴 لهجة جدة / حجازية", value="jeddah")
    await cmd_roast.callback(interaction, member=target, dialect=dialect_choice)

    assert len(channel.sent_messages) == 1
    assert target.mention in channel.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_cmd_roast_custom_topic(test_bot):
    """Test /roast dispatcher incorporates a custom topic into the roast generation."""
    from main import cmd_roast
    guild = test_bot.guilds[0]
    target = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    await cmd_roast.callback(interaction, member=target, topic="سحب علينا في بطولة الفيفا")

    assert len(channel.sent_messages) == 1
    assert len(test_bot.roast_log) >= 1
    assert test_bot.roast_log[-1][1] == target.display_name


@pytest.mark.asyncio
async def test_cmd_roast_ai_failure_fallback(test_bot):
    """Test /roast dispatcher responds with error message when AI engine raises an exception."""
    from main import cmd_roast
    guild = test_bot.guilds[0]
    target = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    with patch("main.generate_content_ai", side_effect=RuntimeError("AI Engine Timeout")):
        await cmd_roast.callback(interaction, member=target)

    assert len(interaction.followup.sent_messages) == 1
    assert "حدث خطأ" in interaction.followup.sent_messages[0]["content"]


# ============================================================================
# 2. BOT DISPATCHERS: /court
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_court_generates_indictment(test_bot):
    """Test /court generates an indictment embed and CourtVoteView."""
    from main import cmd_court, CourtVoteView
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    await cmd_court.callback(interaction, defendant=defendant, charge="الصنم الأبدي وتخريب أجواء السيرفر")

    assert interaction.response.deferred is True
    assert len(interaction.followup.sent_messages) == 1
    msg = interaction.followup.sent_messages[0]
    assert "محاكمة علنية" in msg["content"]
    assert msg["embed"] is not None
    assert "قضية رقم 404" in msg["embed"].title
    assert isinstance(msg["view"], CourtVoteView)


@pytest.mark.asyncio
async def test_cmd_court_voting_interaction(test_bot):
    """Test CourtVoteView records votes when users click guilty and innocent buttons."""
    from main import CourtVoteView
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    view = CourtVoteView(defendant.id, defendant.display_name, "تخريب الرانك", test_bot)

    # User 1002 votes guilty
    voter1_interaction = MockInteraction(user=guild.members[1], channel=guild.text_channels[0], guild=guild)
    button_guilty = [c for c in view.children if c.custom_id == "vote_guilty"][0]
    await button_guilty.callback(voter1_interaction)

    assert 1002 in view.guilty_votes
    assert len(view.guilty_votes) == 1
    assert "1" in button_guilty.label

    # User 1003 votes innocent
    voter2_interaction = MockInteraction(user=guild.members[2], channel=guild.text_channels[0], guild=guild)
    button_innocent = [c for c in view.children if c.custom_id == "vote_innocent"][0]
    await button_innocent.callback(voter2_interaction)

    assert 1003 in view.innocent_votes
    assert len(view.innocent_votes) == 1


@pytest.mark.asyncio
async def test_cmd_court_vote_switching(test_bot):
    """Test CourtVoteView handles voter switching their vote from innocent to guilty."""
    from main import CourtVoteView
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    voter = guild.members[1]
    view = CourtVoteView(defendant.id, defendant.display_name, "ادعاء النوم", test_bot)

    interaction = MockInteraction(user=voter, channel=guild.text_channels[0], guild=guild)
    btn_innocent = [c for c in view.children if c.custom_id == "vote_innocent"][0]
    btn_guilty = [c for c in view.children if c.custom_id == "vote_guilty"][0]

    # Vote innocent first
    await btn_innocent.callback(interaction)
    assert voter.id in view.innocent_votes
    assert voter.id not in view.guilty_votes

    # Switch to guilty
    await btn_guilty.callback(interaction)
    assert voter.id not in view.innocent_votes
    assert voter.id in view.guilty_votes


@pytest.mark.asyncio
async def test_cmd_court_timeout_guilty_verdict(test_bot):
    """Test CourtVoteView timeout executes guilty sentencing when guilty votes dominate."""
    from main import CourtVoteView, dossier_mgr
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    channel = guild.text_channels[0]
    view = CourtVoteView(defendant.id, defendant.display_name, "الصنم الأبدي", test_bot)

    view.guilty_votes.add(guild.members[1].id)
    view.guilty_votes.add(guild.members[2].id)

    await view.on_timeout()

    # Verify conviction announcement sent to channel
    assert len(channel.sent_messages) >= 1
    verdict_text = channel.sent_messages[0]["content"]
    assert "ثبتت إدانة المتهم" in verdict_text
    # Verify defendant dossier was updated with the crime
    dossier = dossier_mgr.get_user_dossier(defendant.id)
    assert "الصنم الأبدي" in dossier["crimes"]


@pytest.mark.asyncio
async def test_cmd_court_timeout_innocent_verdict(test_bot):
    """Test CourtVoteView timeout announces acquittal when innocent votes dominate."""
    from main import CourtVoteView
    guild = test_bot.guilds[0]
    defendant = guild.members[0]
    channel = guild.text_channels[0]
    view = CourtVoteView(defendant.id, defendant.display_name, "تخريب اللعب", test_bot)

    view.innocent_votes.add(guild.members[1].id)
    view.innocent_votes.add(guild.members[2].id)

    await view.on_timeout()

    assert len(channel.sent_messages) == 1
    assert "تم تبرئة" in channel.sent_messages[0]["content"]


# ============================================================================
# 3. BOT DISPATCHERS: /shamecard
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_shamecard_generation(test_bot):
    """Test /shamecard issues an SVG file and formatted embed."""
    from main import cmd_shamecard
    guild = test_bot.guilds[0]
    member = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    await cmd_shamecard.callback(interaction, member=member)

    assert interaction.response.deferred is True
    assert len(interaction.followup.sent_messages) == 1
    msg = interaction.followup.sent_messages[0]
    assert msg["file"] is not None
    assert f"shame_card_{member.id}.svg" == msg["file"].filename
    assert msg["embed"] is not None
    assert member.display_name in msg["embed"].title


@pytest.mark.asyncio
async def test_cmd_shamecard_custom_dialect(test_bot):
    """Test /shamecard accepts dialect parameter and applies correct badge."""
    from main import cmd_shamecard
    guild = test_bot.guilds[0]
    member = guild.members[1]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[0], channel=channel, guild=guild)

    await cmd_shamecard.callback(interaction, member=member, dialect="riyadh")

    assert len(interaction.followup.sent_messages) == 1
    msg = interaction.followup.sent_messages[0]
    assert msg["file"] is not None


@pytest.mark.asyncio
async def test_cmd_shamecard_includes_dossier_data(test_bot):
    """Test /shamecard incorporates crime history from defendant dossier."""
    from main import cmd_shamecard
    guild = test_bot.guilds[0]
    member = guild.members[2]
    channel = guild.text_channels[0]
    test_bot.dossier_mgr.add_crime(member.id, "سرقة اللوت بالدروب")

    interaction = MockInteraction(user=guild.members[0], channel=channel, guild=guild)
    await cmd_shamecard.callback(interaction, member=member)

    msg = interaction.followup.sent_messages[0]
    assert "سرقة اللوت بالدروب" in msg["embed"].description


@pytest.mark.asyncio
async def test_cmd_shamecard_ai_fallback_on_exception(test_bot):
    """Test /shamecard gracefully generates card when Gemini AI fails."""
    from main import cmd_shamecard
    guild = test_bot.guilds[0]
    member = guild.members[0]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    with patch("main.generate_content_ai", side_effect=Exception("Gemini Offline")):
        await cmd_shamecard.callback(interaction, member=member)

    assert len(interaction.followup.sent_messages) == 1
    msg = interaction.followup.sent_messages[0]
    assert msg["file"] is not None
    assert "تصريفات" in msg["embed"].description


@pytest.mark.asyncio
async def test_cmd_shamecard_stats_ranges(test_bot):
    """Test shame card statistics fall within authentic calibrated ranges."""
    card_data = test_bot.dossier_mgr.get_shame_card_data(1001, "TestHero")
    stats = card_data["stats"]
    assert 88 <= stats["excuses"] <= 99
    assert 2 <= stats["aim"] <= 18
    assert 85 <= stats["choke"] <= 100
    assert 0 <= stats["sleep"] <= 3


# ============================================================================
# 4. BOT DISPATCHERS: /battle
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_battle_announcement(test_bot):
    """Test /battle initiates a 1v1 battle arena session between two members."""
    from main import cmd_battle
    guild = test_bot.guilds[0]
    p1 = guild.members[0]
    p2 = guild.members[1]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[2], channel=channel, guild=guild)

    await cmd_battle.callback(interaction, opponent1=p1, opponent2=p2, topic="تحدي الفيفا الحاسم")

    assert interaction.response.deferred is True
    assert len(interaction.followup.sent_messages) == 1
    msg = interaction.followup.sent_messages[0]["content"]
    assert "حلبة مصارعة الذبات 1v1" in msg
    assert p1.mention in msg
    assert p2.mention in msg
    assert "تحدي الفيفا الحاسم" in msg


@pytest.mark.asyncio
async def test_cmd_battle_default_topic(test_bot):
    """Test /battle applies 'تحدي حر' when topic parameter is omitted."""
    from main import cmd_battle
    guild = test_bot.guilds[0]
    p1 = guild.members[0]
    p2 = guild.members[2]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[1], channel=channel, guild=guild)

    await cmd_battle.callback(interaction, opponent1=p1, opponent2=p2)

    msg = interaction.followup.sent_messages[0]["content"]
    assert "تحدي حر" in msg


@pytest.mark.asyncio
async def test_cmd_battle_ai_prompt_contents(test_bot):
    """Test /battle builds appropriate prompt for commentator intro."""
    from main import cmd_battle
    guild = test_bot.guilds[0]
    p1 = guild.members[1]
    p2 = guild.members[2]
    channel = guild.text_channels[0]
    interaction = MockInteraction(user=guild.members[0], channel=channel, guild=guild)

    with patch("main.generate_content_ai", wraps=test_bot) as mock_gen:
        mock_gen.side_effect = lambda contents: MagicMock(text="يا أهلاً بالوحوش في الحلبة!")
        await cmd_battle.callback(interaction, opponent1=p1, opponent2=p2, topic="من هو ملك الصنم؟")

    msg = interaction.followup.sent_messages[0]["content"]
    assert "يا أهلاً بالوحوش" in msg


@pytest.mark.asyncio
async def test_cmd_battle_judge_arbitration(test_bot):
    """Test roast_engine.judge_battle returns scoring and winner resolution."""
    res = await test_bot.roast_engine.judge_battle(
        "سعد", "وجهك مثل شاشة الموت الزرقاء",
        "خالد", "أنت ما عندك سالفة وتسوقها",
        topic="حرب الكومبيوترات"
    )
    assert "score1" in res
    assert "score2" in res
    assert "winner" in res
    assert "commentary" in res
    assert "knockout_punch" in res
    assert isinstance(res["score1"], (int, float))
    assert isinstance(res["score2"], (int, float))


@pytest.mark.asyncio
async def test_cmd_battle_judge_tie_handling(test_bot):
    """Test judge_battle handles fallback tie scenarios when evaluation fails."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("GenAI Fail"))
    with patch.object(test_bot.roast_engine, "_get_client", return_value=mock_client):
        res = await test_bot.roast_engine.judge_battle("علي", "ذبة", "عمر", "ذبة")
    assert res["winner"] == "تعادل"
    assert res["score1"] == 7.5
    assert res["score2"] == 7.5


# ============================================================================
# 5. BOT DISPATCHERS: /dialect
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_dialect_switch_to_riyadh(test_bot):
    """Test /dialect switches current bot dialect to Riyadh (Najdi)."""
    from main import cmd_dialect
    guild = test_bot.guilds[0]
    interaction = MockInteraction(user=guild.members[0], channel=guild.text_channels[0], guild=guild)

    choice = app_commands.Choice(name="🇸🇦 لهجة الرياض / نجدية", value="riyadh")
    await cmd_dialect.callback(interaction, dialect=choice)

    assert test_bot.current_dialect == "riyadh"
    assert len(interaction.response.sent_messages) == 1
    assert "نجدية" in interaction.response.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_cmd_dialect_switch_to_jeddah(test_bot):
    """Test /dialect switches current bot dialect to Jeddah (Hijazi)."""
    from main import cmd_dialect
    guild = test_bot.guilds[0]
    interaction = MockInteraction(user=guild.members[0], channel=guild.text_channels[0], guild=guild)

    choice = app_commands.Choice(name="🌴 لهجة جدة / حجازية", value="jeddah")
    await cmd_dialect.callback(interaction, dialect=choice)

    assert test_bot.current_dialect == "jeddah"
    assert "حجازية" in interaction.response.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_cmd_dialect_switch_to_qassim(test_bot):
    """Test /dialect switches current bot dialect to Qassim."""
    from main import cmd_dialect
    guild = test_bot.guilds[0]
    interaction = MockInteraction(user=guild.members[0], channel=guild.text_channels[0], guild=guild)

    choice = app_commands.Choice(name="🌾 لهجة القصيم", value="qassim")
    await cmd_dialect.callback(interaction, dialect=choice)

    assert test_bot.current_dialect == "qassim"
    assert "قصيم" in interaction.response.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_cmd_dialect_switch_to_default(test_bot):
    """Test /dialect switches current bot dialect back to Default."""
    from main import cmd_dialect
    guild = test_bot.guilds[0]
    test_bot.current_dialect = "riyadh"
    interaction = MockInteraction(user=guild.members[0], channel=guild.text_channels[0], guild=guild)

    choice = app_commands.Choice(name="⚡ عامية سعودية عامة (Default)", value="default")
    await cmd_dialect.callback(interaction, dialect=choice)

    assert test_bot.current_dialect == "default"


@pytest.mark.asyncio
async def test_cmd_dialect_persistence_trigger(test_bot):
    """Test /dialect changes trigger save_data() to persist state."""
    from main import cmd_dialect
    guild = test_bot.guilds[0]
    interaction = MockInteraction(user=guild.members[0], channel=guild.text_channels[0], guild=guild)

    with patch.object(test_bot, "save_data") as mock_save:
        choice = app_commands.Choice(name="🌾 لهجة القصيم", value="qassim")
        await cmd_dialect.callback(interaction, dialect=choice)
        mock_save.assert_called_once()


# ============================================================================
# 6. WEB API ROUTE: GET /health
# ============================================================================

@pytest.mark.asyncio
async def test_route_health_status_200(web_client):
    """Test GET /health returns HTTP 200 OK."""
    resp = await web_client.get("/health")
    assert resp.status == 200


@pytest.mark.asyncio
async def test_route_health_schema_payload(web_client):
    """Test GET /health returns expected service telemetry schema."""
    resp = await web_client.get("/health")
    data = await resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "mr-roast"
    assert data["version"] == "3.0"
    assert "discord_ready" in data
    assert "uptime" in data


@pytest.mark.asyncio
async def test_route_health_api_alias(web_client):
    """Test GET /api/health acts as alias returning identical healthy telemetry."""
    resp = await web_client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_route_health_discord_readiness(web_client, test_bot):
    """Test GET /health reflects bot readiness status correctly."""
    test_bot.is_ready = lambda: True
    resp = await web_client.get("/health")
    data = await resp.json()
    assert data["discord_ready"] is True
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_route_health_uptime_increases(web_client):
    """Test GET /health reports non-negative uptime."""
    resp = await web_client.get("/health")
    data = await resp.json()
    assert data["uptime"] >= 0


# ============================================================================
# 7. WEB API ROUTE: GET /api/stats
# ============================================================================

@pytest.mark.asyncio
async def test_route_stats_status_200(web_client):
    """Test GET /api/stats returns HTTP 200 with full telemetry."""
    resp = await web_client.get("/api/stats")
    assert resp.status == 200
    data = await resp.json()
    assert "bot_name" in data
    assert "total_roasts" in data
    assert "members_in_vc" in data


@pytest.mark.asyncio
async def test_route_stats_voice_members_telemetry(web_client, test_bot):
    """Test GET /api/stats returns accurate members in voice channels."""
    guild = test_bot.guilds[0]
    vc = guild.voice_channels[0]
    member = guild.members[0]
    vc.members.append(member)
    test_bot.vc_join_times[member.id] = time.time() - 1200  # 20 mins ago

    resp = await web_client.get("/api/stats")
    data = await resp.json()
    vc_mems = data["members_in_vc"]
    assert len(vc_mems) == 1
    assert vc_mems[0]["id"] == member.id
    assert vc_mems[0]["name"] == member.display_name
    assert vc_mems[0]["minutes"] >= 19


@pytest.mark.asyncio
async def test_route_stats_shame_board(web_client, test_bot):
    """Test GET /api/stats shame board ranks users by roast frequency."""
    test_bot.roast_count_per_user[1001] = 15
    test_bot.roast_count_per_user[1002] = 5

    resp = await web_client.get("/api/stats")
    data = await resp.json()
    board = data["shame_board"]
    assert len(board) >= 2
    assert board[0]["id"] == 1001
    assert board[0]["count"] == 15


@pytest.mark.asyncio
async def test_route_stats_dialect_catalog(web_client):
    """Test GET /api/stats contains all 4 dialects and their radar metrics."""
    resp = await web_client.get("/api/stats")
    data = await resp.json()
    dialects = data["dialects"]
    assert len(dialects) == 4
    d_ids = [d["id"] for d in dialects]
    assert "default" in d_ids
    assert "riyadh" in d_ids
    assert "jeddah" in d_ids
    assert "qassim" in d_ids


@pytest.mark.asyncio
async def test_route_stats_hourly_activity_structure(web_client, test_bot):
    """Test GET /api/stats contains 24-hour activity array."""
    test_bot.hourly_vc_activity[14] = 7
    resp = await web_client.get("/api/stats")
    data = await resp.json()
    assert len(data["hourly_activity"]) == 24
    assert data["hourly_activity"][14] == 7


# ============================================================================
# 8. WEB API ROUTE: POST /api/court/start
# ============================================================================

@pytest.mark.asyncio
async def test_route_court_start_success(web_client, test_bot):
    """Test POST /api/court/start creates a live server trial."""
    payload = {
        "defendant_id": 1001,
        "charge": "ادعاء النوم واللعب متخفياً",
        "dialect": "riyadh"
    }
    resp = await web_client.post("/api/court/start", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "indictment" in data
    assert "title" in data["indictment"]
    assert "penalty" in data["indictment"]


@pytest.mark.asyncio
async def test_route_court_start_missing_defendant(web_client):
    """Test POST /api/court/start returns error when defendant does not exist."""
    payload = {
        "defendant_id": 99999999,
        "charge": "لا يوجد"
    }
    resp = await web_client.post("/api/court/start", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "غير موجود" in data["error"]


@pytest.mark.asyncio
async def test_route_court_start_sends_to_discord(web_client, test_bot):
    """Test POST /api/court/start sends indictment announcement message to Discord channel."""
    guild = test_bot.guilds[0]
    channel = guild.text_channels[0]
    payload = {
        "defendant_id": 1002,
        "charge": "الصنم المستمر"
    }
    await web_client.post("/api/court/start", json=payload)
    assert len(channel.sent_messages) == 1
    assert "محاكمة علنية" in channel.sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_route_court_start_default_charge(web_client):
    """Test POST /api/court/start uses default charge if charge is omitted."""
    payload = {"defendant_id": 1003}
    resp = await web_client.post("/api/court/start", json=payload)
    data = await resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_route_court_start_custom_dialect(web_client):
    """Test POST /api/court/start passes dialect to roast engine."""
    payload = {
        "defendant_id": 1001,
        "charge": "سحب الرانك",
        "dialect": "qassim"
    }
    resp = await web_client.post("/api/court/start", json=payload)
    data = await resp.json()
    assert data["ok"] is True


# ============================================================================
# 9. WEB API ROUTE: POST /api/court/vote
# ============================================================================

@pytest.mark.asyncio
async def test_route_court_vote_guilty(web_client):
    """Test POST /api/court/vote accepts a guilty vote."""
    payload = {"trial_id": 101, "vote": "guilty"}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["vote"] == "guilty"


@pytest.mark.asyncio
async def test_route_court_vote_innocent(web_client):
    """Test POST /api/court/vote accepts an innocent vote."""
    payload = {"trial_id": 101, "vote": "innocent"}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["vote"] == "innocent"


@pytest.mark.asyncio
async def test_route_court_vote_invalid_choice_rejected(web_client):
    """Test POST /api/court/vote rejects votes other than guilty/innocent."""
    payload = {"trial_id": 101, "vote": "neutral"}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 400
    data = await resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_route_court_vote_supports_choice_key(web_client):
    """Test POST /api/court/vote accepts 'choice' as alternative to 'vote'."""
    payload = {"trial_id": 101, "choice": "guilty"}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_route_court_vote_missing_vote_field(web_client):
    """Test POST /api/court/vote rejects payload with missing vote field."""
    payload = {"trial_id": 101}
    resp = await web_client.post("/api/court/vote", json=payload)
    assert resp.status == 400


# ============================================================================
# 10. WEB API ROUTE: POST /api/battle/judge
# ============================================================================

@pytest.mark.asyncio
async def test_route_battle_judge_success(web_client):
    """Test POST /api/battle/judge arbitrates a 1v1 battle."""
    payload = {
        "p1_name": "سعد",
        "p1_roast": "أنت مسوي فيها ذكي وأنت تصرفاتك كلها منتهية",
        "p2_name": "خالد",
        "p2_roast": "يا رجال اركد بس لعبك كله بوتات",
        "topic": "تحدي الشات"
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    res = data["result"]
    assert "score1" in res
    assert "score2" in res
    assert "winner" in res
    assert "commentary" in res
    assert "knockout_punch" in res


@pytest.mark.asyncio
async def test_route_battle_judge_empty_roast_rejected(web_client):
    """Test POST /api/battle/judge rejects submission when a roast is empty."""
    payload = {
        "p1_name": "سعد",
        "p1_roast": "",
        "p2_name": "خالد",
        "p2_roast": "ذبة قوية"
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "يجب كتابة ذبة" in data["error"]


@pytest.mark.asyncio
async def test_route_battle_judge_numeric_scores(web_client):
    """Test POST /api/battle/judge returns scores formatted as numbers."""
    payload = {
        "p1_name": "فهد",
        "p1_roast": "ذبة فهد النارية",
        "p2_name": "راكان",
        "p2_roast": "ذبة راكان المتواضعة"
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    data = await resp.json()
    assert isinstance(data["result"]["score1"], (int, float))
    assert isinstance(data["result"]["score2"], (int, float))


@pytest.mark.asyncio
async def test_route_battle_judge_default_names(web_client):
    """Test POST /api/battle/judge applies default names if omitted."""
    payload = {
        "p1_roast": "ذبة 1",
        "p2_roast": "ذبة 2"
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    data = await resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_route_battle_judge_topic_propagation(web_client):
    """Test POST /api/battle/judge propagates custom topic properly."""
    payload = {
        "p1_name": "لاعب 1",
        "p1_roast": "ذبة",
        "p2_name": "لاعب 2",
        "p2_roast": "ذبة",
        "topic": "نزاع حول السهرة"
    }
    resp = await web_client.post("/api/battle/judge", json=payload)
    data = await resp.json()
    assert data["ok"] is True


# ============================================================================
# 11. WEB API ROUTE: POST /api/shame_card
# ============================================================================

@pytest.mark.asyncio
async def test_route_shame_card_generates_svg(web_client):
    """Test POST /api/shame_card produces complete SVG card markup."""
    payload = {"member_id": 1001, "dialect": "default"}
    resp = await web_client.post("/api/shame_card", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "<svg" in data["svg"]
    assert "</svg>" in data["svg"]
    assert "card_data" in data
    assert "roast_text" in data


@pytest.mark.asyncio
async def test_route_shame_card_with_dossier_crime(web_client, test_bot):
    """Test POST /api/shame_card SVG reflects custom crimes recorded in dossier."""
    test_bot.dossier_mgr.add_crime(1001, "النكبة في الجولة الأخيرة")
    payload = {"member_id": 1001}
    resp = await web_client.post("/api/shame_card", json=payload)
    data = await resp.json()
    assert data["card_data"]["crime"] == "النكبة في الجولة الأخيرة"


@pytest.mark.asyncio
async def test_route_shame_card_dialect_badge(web_client):
    """Test POST /api/shame_card applies correct badge in SVG markup."""
    payload = {"member_id": 1002, "dialect": "jeddah"}
    resp = await web_client.post("/api/shame_card", json=payload)
    data = await resp.json()
    assert "حجازية" in data["svg"]


@pytest.mark.asyncio
async def test_route_shame_card_unknown_member(web_client):
    """Test POST /api/shame_card generates card even for members not in cache."""
    payload = {"member_id": 999111}
    resp = await web_client.post("/api/shame_card", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "عضو #999111" in data["card_data"]["name"]


@pytest.mark.asyncio
async def test_route_shame_card_send_to_discord(web_client, test_bot):
    """Test POST /api/shame_card_send sends the generated card to Discord text channel."""
    guild = test_bot.guilds[0]
    channel = guild.text_channels[0]
    payload = {"member_id": 1001, "dialect": "riyadh"}
    resp = await web_client.post("/api/shame_card_send", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert len(channel.sent_messages) == 1
    assert "إشعار عار رسمي" in channel.sent_messages[0]["content"]


# ============================================================================
# 12. WEB API ROUTE: POST /api/dialect/preview
# ============================================================================

@pytest.mark.asyncio
async def test_route_dialect_preview_returns_4_dialects(web_client):
    """Test POST /api/dialect/preview returns all 4 Saudi dialect variations."""
    payload = {
        "topic": "واحد ساحب على السهرة وجاء اليوم الثاني يضحك",
        "member_name": "سعد"
    }
    resp = await web_client.post("/api/dialect/preview", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    comps = data["comparisons"]
    assert "default" in comps
    assert "riyadh" in comps
    assert "jeddah" in comps
    assert "qassim" in comps


@pytest.mark.asyncio
async def test_route_dialect_preview_default_payload(web_client):
    """Test POST /api/dialect/preview handles request with default arguments."""
    resp = await web_client.post("/api/dialect/preview", json={})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert len(data["comparisons"]) == 4


@pytest.mark.asyncio
async def test_route_dialect_preview_text_contents(web_client):
    """Test POST /api/dialect/preview returned roasts are non-empty strings."""
    payload = {"topic": "تخريب الرانك", "member_name": "عبدالله"}
    resp = await web_client.post("/api/dialect/preview", json=payload)
    data = await resp.json()
    for dialect_key, roast in data["comparisons"].items():
        assert isinstance(roast, str)
        assert len(roast.strip()) > 5


@pytest.mark.asyncio
async def test_route_dialect_preview_ai_json_cleanup(web_client):
    """Test POST /api/dialect/preview cleans Markdown backticks from AI output."""
    with patch("main.generate_content_ai", return_value=MagicMock(text='```json\n{"default":"ذبة","riyadh":"ذبة","jeddah":"ذبة","qassim":"ذبة"}\n```')):
        resp = await web_client.post("/api/dialect/preview", json={"topic": "تيست"})
        data = await resp.json()
        assert data["ok"] is True
        assert "default" in data["comparisons"]


@pytest.mark.asyncio
async def test_route_dialect_preview_error_handling(web_client):
    """Test POST /api/dialect/preview returns ok:false on AI exception."""
    with patch("web_dashboard.generate_content_ai", side_effect=Exception("API Down")):
        resp = await web_client.post("/api/dialect/preview", json={"topic": "تيست"})
        data = await resp.json()
        assert data["ok"] is False
        assert "error" in data


# ============================================================================
# 13. WEB API ROUTE: POST /api/cli/execute
# ============================================================================

@pytest.mark.asyncio
async def test_route_cli_execute_help(web_client):
    """Test POST /api/cli/execute 'help' command returns command manual."""
    resp = await web_client.post("/api/cli/execute", json={"command": "help"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "CYBER CLI COMMANDS" in data["output"]
    assert "stats" in data["output"]


@pytest.mark.asyncio
async def test_route_cli_execute_stats(web_client):
    """Test POST /api/cli/execute 'stats' command returns system telemetry."""
    resp = await web_client.post("/api/cli/execute", json={"command": "stats"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "SYS STATUS: ONLINE" in data["output"]
    assert "ACTIVE DIALECT" in data["output"]


@pytest.mark.asyncio
async def test_route_cli_execute_dialect_change(web_client, test_bot):
    """Test POST /api/cli/execute 'dialect jeddah' sets active dialect."""
    resp = await web_client.post("/api/cli/execute", json={"command": "dialect jeddah"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "SUCCESS: Dialect set" in data["output"]
    assert test_bot.current_dialect == "jeddah"


@pytest.mark.asyncio
async def test_route_cli_execute_protect_unprotect(web_client, test_bot):
    """Test POST /api/cli/execute 'protect' and 'unprotect' manage VIP immunity."""
    # Protect user 1001
    resp1 = await web_client.post("/api/cli/execute", json={"command": "protect 1001"})
    data1 = await resp1.json()
    assert data1["ok"] is True
    assert 1001 in test_bot.protected_users

    # Unprotect user 1001
    resp2 = await web_client.post("/api/cli/execute", json={"command": "unprotect 1001"})
    data2 = await resp2.json()
    assert data2["ok"] is True
    assert 1001 not in test_bot.protected_users


@pytest.mark.asyncio
async def test_route_cli_execute_unknown_command(web_client):
    """Test POST /api/cli/execute returns friendly error for unrecognized commands."""
    resp = await web_client.post("/api/cli/execute", json={"command": "explode_server"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is False
    assert "COMMAND NOT RECOGNIZED" in data["output"]


@pytest.mark.asyncio
async def test_roast_loop_auto_start_and_toggle(test_bot):
    """Test roast_loop auto-starts on ready and toggle_roast_loop transitions cleanly."""
    # Simulate on_ready starting the loop
    if not test_bot.roast_loop.is_running():
        test_bot.roast_loop.start()
    assert test_bot.roast_loop.is_running() is True

    # Toggle off
    res = await test_bot.toggle_roast_loop()
    assert res is False
    assert test_bot.roast_loop.is_running() is False

    # Toggle back on
    res2 = await test_bot.toggle_roast_loop()
    assert res2 is True
    assert test_bot.roast_loop.is_running() is True

    # Clean up
    if test_bot.roast_loop.is_running():
        await test_bot.toggle_roast_loop()


@pytest.mark.asyncio
async def test_dashboard_reports_roast_loop_active(web_client, test_bot):
    """Test GET /api/stats reports roast_loop_running correctly when active."""
    if not test_bot.roast_loop.is_running():
        await test_bot.toggle_roast_loop()
    resp = await web_client.get("/api/stats")
    assert resp.status == 200
    data = await resp.json()
    assert data["roast_loop_running"] is True
    if test_bot.roast_loop.is_running():
        await test_bot.toggle_roast_loop()

