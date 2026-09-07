"""
web_dashboard.py - لوحة تحكم مستر ذبات 3.0 (Quantum Cyber Deck)
الجيل الجديد من منصات قيادة وتوجيه الذبات والمحاكمات السيرفرية:
1. Tactical Operations Command (مركز العمليات التكتيكي والرادار الحي)
2. Shame Card Holographic Studio (استوديو بطاقات العار الرقمية التفاعلي)
3. The Server Courtroom (محكمة السيرفر العليا وتصويت المحلفين الحي)
4. 1v1 Roast Battle Arena (حلبة مواجهات الذبات وتحكيم الذكاء الاصطناعي)
5. Dialect Nexus & 4-Way Comparative Simulator (مختبر ومحاكي اللهجات الأربعة)
6. Criminal Dossier Vault (أرشيف السوابق والفضائح وجرائم السيرفر)
7. Deep Intelligence & Analytics (التحليلات، الرادار، وقائمة الحماية)
8. Cyber CLI Terminal (طرفية الأوامر السريعة المباشرة)
"""
import asyncio
import io
import json
import logging
import os
import random
import re
import time
import discord
from aiohttp import web
from google import genai
from google.genai import types
from modules.dialects import DIALECTS, get_dialect_prompt, get_comparative_prompt
from modules.dossier import dossier_mgr
from modules.roast_engine import roast_engine
from modules.ai_service import generate_content_ai
from modules.court import CourtVoteView
from modules.state_manager import state_mgr

logger = logging.getLogger("mr_roast.web")

AFK_CHANNEL_ID = 782986605148635166

# ─── API Endpoints ──────────────────────────────────────────────────────────

async def handle_stats(request):
    bot = request.app["bot"]
    try:
        members_in_vc = []
        total_vc_minutes = 0
        guild_info = {}

        for guild in getattr(bot, "guilds", []):
            guild_info = {
                "name": guild.name,
                "icon": str(guild.icon.url) if guild.icon else "",
                "member_count": guild.member_count,
                "online": sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot),
            }
            for vc in guild.voice_channels:
                if vc.id == AFK_CHANNEL_ID:
                    continue
                for m in vc.members:
                    if not m.bot:
                        join_time = bot.vc_join_times.get(m.id, time.time())
                        mins = int((time.time() - join_time) / 60)
                        total_vc_minutes += mins
                        games = list(bot.user_game_history.get(m.id, []))
                        activities = []
                        custom_status = ""
                        for act in m.activities:
                            if act.type == discord.ActivityType.playing:
                                activities.append({"type": "playing", "name": act.name})
                            elif act.type == discord.ActivityType.streaming:
                                activities.append({"type": "streaming", "name": getattr(act, 'game', act.name)})
                            elif act.type == discord.ActivityType.listening:
                                activities.append({"type": "listening", "name": act.name})
                            elif act.type == discord.ActivityType.custom:
                                custom_status = getattr(act, 'name', '') or getattr(act, 'state', '') or ''

                        spk = bot.user_speak_history.get(m.id, {"unmuted_sec": 0, "last_unmute": 0})
                        unmuted_time = spk["unmuted_sec"]
                        if spk["last_unmute"] > 0:
                            unmuted_time += (time.time() - spk["last_unmute"])

                        speak_ratio = 0
                        if mins > 0:
                            speak_ratio = min(100, int((unmuted_time / (mins * 60)) * 100))

                        u_dossier = bot.dossier_mgr.get_user_dossier(m.id)

                        members_in_vc.append({
                            "id": m.id,
                            "name": m.display_name,
                            "avatar": str(m.display_avatar.url),
                            "minutes": mins,
                            "channel": vc.name,
                            "games": games,
                            "activities": activities,
                            "custom_status": custom_status,
                            "muted": m.voice.self_mute or m.voice.mute if m.voice else False,
                            "deafened": m.voice.self_deaf or m.voice.deaf if m.voice else False,
                            "streaming": m.voice.self_stream if m.voice else False,
                            "status": str(m.status),
                            "protected": m.id in bot.protected_users,
                            "speak_ratio": speak_ratio,
                            "title": u_dossier.get("titles", ["عضو عادي"])[0] if u_dossier.get("titles") else "عضو عادي",
                            "excuse_count": len(u_dossier.get("excuses", [])),
                            "crime_count": len(u_dossier.get("crimes", [])),
                            "grudge": bot.grudge_levels.get(m.id, 0)
                        })

        all_members = []
        for guild in getattr(bot, "guilds", []):
            for m in guild.members:
                if not m.bot:
                    all_members.append({
                        "id": m.id,
                        "name": m.display_name,
                        "avatar": str(m.display_avatar.url),
                        "status": str(m.status)
                    })

        shame = []
        for guild in getattr(bot, "guilds", []):
            for uid, cnt in sorted(bot.roast_count_per_user.items(), key=lambda x: -x[1])[:15]:
                m = guild.get_member(uid)
                if m:
                    grudge_lvl = bot.grudge_levels.get(uid, 0)
                    u_dos = bot.dossier_mgr.get_user_dossier(uid)
                    top_excuse = u_dos.get("excuses", ["لا توجد تصريفات"])[0] if u_dos.get("excuses") else "لا توجد"
                    title = u_dos.get("titles", ["المستهدف"])[0] if u_dos.get("titles") else "المستهدف"
                    shame.append({
                        "id": uid,
                        "name": m.display_name,
                        "avatar": str(m.display_avatar.url),
                        "count": cnt,
                        "grudge": grudge_lvl,
                        "title": title,
                        "top_excuse": top_excuse
                    })

        top_games = sorted(bot.game_popularity.items(), key=lambda x: -x[1])[:10]
        top_games = [{"name": g, "count": c} for g, c in top_games]

        import datetime
        daily = {}
        for i in range(7):
            d = (datetime.date.today() - datetime.timedelta(days=6-i)).isoformat()
            daily[d] = bot.daily_roast_counts.get(d, 0)

        recent_roasts = [{"time": r[0], "member": r[1], "roast": r[2]} for r in bot.roast_log[-100:]]

        protected_list = []
        for guild in getattr(bot, "guilds", []):
            for uid in bot.protected_users:
                m = guild.get_member(uid)
                if m:
                    protected_list.append({"id": uid, "name": m.display_name, "avatar": str(m.display_avatar.url)})

        next_roast_in = 0
        if getattr(bot, "roast_loop", None) and bot.roast_loop.is_running() and bot.roast_loop.next_iteration:
            diff = (bot.roast_loop.next_iteration - discord.utils.utcnow()).total_seconds()
            next_roast_in = max(0, int(diff / 60))

        # AI Alerts
        alerts = []
        for m in members_in_vc:
            if m["minutes"] > 60 and (m.get("deafened", False) or m.get("muted", False)):
                alerts.append({"type": "warning", "msg": f"🎯 فرصة قصف: {m['name']} صنم ومسوي ميوت/دفن من أكثر من {m['minutes']} دقيقة!"})
            if m.get("streaming", False) and len(members_in_vc) == 1:
                alerts.append({"type": "info", "msg": f"📺 بث انفرادي: {m['name']} يبث لنفسه لحاله بالروم بدون جمهور!"})
            if m.get("grudge", 0) >= 15:
                alerts.append({"type": "danger", "msg": f"🔥 حقد متراكم: العداد وصل {m['grudge']} على {m['name']}، يحتاج قصف تأديبي!"})

        # Recent Crimes from Dossiers
        recent_crimes = []
        dossiers_map = getattr(bot.dossier_mgr, 'dossiers', getattr(bot.dossier_mgr, 'data', {}))
        for uid, dos in list(dossiers_map.items())[:20]:
            for cr in dos.get("crimes", []):
                recent_crimes.append({"user_id": uid, "crime": cr})

        dialects_data = [
            {
                "id": k,
                "name": v["name"],
                "region": v["region"],
                "icon": v["icon"],
                "badge": v["badge"],
                "catchphrases": v["catchphrases"],
                "metrics": v.get("metrics", {"sharpness": 85, "speed": 90, "authenticity": 95, "humor": 90})
            }
            for k, v in DIALECTS.items()
        ]

        data = {
            "bot_name": bot.user.name if bot.user else "مستر ذبات 3.0",
            "bot_avatar": str(bot.user.display_avatar.url) if (bot.user and bot.user.display_avatar) else "",
            "roast_loop_running": bot.roast_loop.is_running() if hasattr(bot, "roast_loop") else False,
            "members_in_vc": members_in_vc,
            "all_members": all_members,
            "recent_roasts": recent_roasts,
            "guild": guild_info,
            "total_vc_minutes": total_vc_minutes,
            "total_roasts": sum(bot.roast_count_per_user.values()),
            "uptime_minutes": int((time.time() - getattr(bot, "_start_time", time.time())) / 60),
            "shame_board": shame,
            "top_games": top_games,
            "daily_chart": daily,
            "hourly_activity": getattr(bot, "hourly_vc_activity", [0]*24),
            "protected": protected_list,
            "last_roast_time": getattr(bot, "last_roast_time", None),
            "next_roast_in": next_roast_in,
            "interval_min": getattr(bot, "roast_interval_min", 360),
            "interval_max": getattr(bot, "roast_interval_max", 720),
            "interval_choices": getattr(bot, "roast_interval_choices", [6, 12]),
            "current_dialect": getattr(bot, "current_dialect", "default"),
            "dialects": dialects_data,
            "alerts": alerts,
            "recent_crimes": recent_crimes[-10:]
        }
        return web.Response(text=json.dumps(data, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        import traceback
        traceback.print_exc()
        fallback_data = {
            "error": str(e),
            "bot_name": "مستر ذبات 3.0",
            "bot_avatar": "",
            "roast_loop_running": False,
            "members_in_vc": [],
            "all_members": [],
            "recent_roasts": [],
            "guild": {},
            "total_vc_minutes": 0,
            "total_roasts": 0,
            "uptime_minutes": 0,
            "shame_board": [],
            "top_games": [],
            "daily_chart": {},
            "hourly_activity": [0]*24,
            "protected": [],
            "last_roast_time": None,
            "next_roast_in": 0,
            "interval_min": 360,
            "interval_max": 720,
            "interval_choices": [6, 12],
            "current_dialect": "default",
            "dialects": [],
            "alerts": [],
            "recent_crimes": []
        }
        return web.Response(text=json.dumps(fallback_data, ensure_ascii=False), content_type="application/json")


async def handle_toggle(request):
    bot = request.app["bot"]
    running = await bot.toggle_roast_loop()
    return web.Response(text=json.dumps({"running": running}), content_type="application/json")


async def handle_force_roast(request):
    bot = request.app["bot"]
    asyncio.create_task(bot.force_random_roast())
    return web.Response(text='{"ok":true}', content_type="application/json")


async def handle_targeted_roast(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        topic = body.get("topic", "").strip() or None
        intensity = int(body.get("intensity", 3))
        dialect = body.get("dialect", "").strip() or None
        if not mid:
            return web.Response(text='{"ok":false,"error":"العضو غير محدد"}', content_type="application/json")
        ok = await bot.targeted_roast(
            mid,
            topic=topic,
            intensity=intensity,
            dialect=dialect
        )
        return web.Response(text=json.dumps({"ok": ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_custom_roast(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        txt = body.get("text", "").strip()
        if not mid or not txt:
            return web.Response(text='{"ok":false,"error":"بيانات ناقصة"}', content_type="application/json")
        ok = await bot.send_custom_roast(mid, txt)
        return web.Response(text=json.dumps({"ok": ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_free_message(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        txt = body.get("text", "").strip()
        if not txt:
            return web.Response(text='{"ok":false}', content_type="application/json")
        ok = await bot.send_free_message(txt)
        return web.Response(text=json.dumps({"ok": ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_change_dialect(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        dialect = body.get("dialect", "default")
        if dialect in DIALECTS:
            bot.current_dialect = dialect
            bot.save_data()
            return web.Response(
                text=json.dumps({"ok": True, "dialect": dialect, "name": DIALECTS[dialect]["name"]}),
                content_type="application/json"
            )
        return web.Response(text=json.dumps({"ok": False, "error": "اللهجة غير صالحة"}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_change_interval(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mn = int(body.get("min", 120))
        mx = int(body.get("max", 240))
        mn, mx = bot.change_interval(mn, mx)
        return web.Response(text=json.dumps({"ok": True, "min": mn, "max": mx}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_protect(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        action = body.get("action", "add")
        if action == "add":
            bot.protected_users.add(mid)
        else:
            bot.protected_users.discard(mid)
        return web.Response(text='{"ok":true}', content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_dossier(request):
    bot = request.app["bot"]
    try:
        mid = request.query.get("member_id")
        if not mid:
            return web.Response(text=json.dumps({"ok": False, "error": "No member_id"}), content_type="application/json")
        dossier = bot.dossier_mgr.get_user_dossier(mid)
        return web.Response(text=json.dumps({"ok": True, "dossier": dossier}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_add_dossier_item(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = body.get("member_id")
        item_type = body.get("type", "excuse")
        content = body.get("content", "").strip()
        if not mid or not content:
            return web.Response(text=json.dumps({"ok": False, "error": "بيانات ناقصة"}), content_type="application/json")
        if item_type == "excuse":
            bot.dossier_mgr.add_excuse(mid, content)
        elif item_type == "title":
            bot.dossier_mgr.add_title(mid, content)
        elif item_type == "moment":
            bot.dossier_mgr.add_moment(mid, content)
        elif item_type == "crime":
            bot.dossier_mgr.add_crime(mid, content)
        return web.Response(text=json.dumps({"ok": True, "dossier": bot.dossier_mgr.get_user_dossier(mid)}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_shame_card(request):
    """توليد كود بطاقة العار SVG وبياناتها."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        dialect = body.get("dialect", bot.current_dialect)

        member = None
        for g in bot.guilds:
            member = g.get_member(mid)
            if member:
                break

        name = member.display_name if member else f"عضو #{mid}"
        avatar = str(member.display_avatar.url) if member else ""

        card_data = bot.dossier_mgr.get_shame_card_data(mid, name, avatar)

        # توليد الذبة السريعة
        roast_prompt = f"أنت مستر ذبات. اكتب ذبة لبطاقة العار الرسمية للعضو '{name}' عن جريمته '{card_data.get('crime')}'. سطر واحد فقط قوي جداً بلهجة {dialect}."
        try:
            resp = await generate_content_ai(contents=roast_prompt)
            roast_txt = resp.text.strip()
        except Exception:
            roast_txt = f"أشهر تصريفاته: {card_data.get('top_excuse')}"

        badge = DIALECTS.get(dialect, DIALECTS["default"])["badge"]
        svg_code = bot.roast_engine.generate_shame_card_svg(card_data, roast_txt, badge)

        return web.Response(
            text=json.dumps({
                "ok": True,
                "card_data": card_data,
                "roast_text": roast_txt,
                "svg": svg_code
            }, ensure_ascii=False),
            content_type="application/json"
        )
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_shame_card_send(request):
    """إرسال بطاقة العار مباشرة لروم الديسكورد."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        dialect = body.get("dialect", bot.current_dialect)

        member = None
        for g in bot.guilds:
            member = g.get_member(mid)
            if member:
                break

        if not member:
            return web.Response(text=json.dumps({"ok": False, "error": "العضو غير موجود بالسيرفر"}), content_type="application/json")

        card_data = bot.dossier_mgr.get_shame_card_data(mid, member.display_name, str(member.display_avatar.url))

        roast_prompt = f"أنت مستر ذبات. اكتب ذبة لبطاقة العار الرسمية للعضو '{member.display_name}' عن جريمته '{card_data.get('crime')}'. سطر واحد فقط قوي جداً بلهجة {dialect}."
        try:
            resp = await generate_content_ai(contents=roast_prompt)
            roast_txt = resp.text.strip()
        except Exception:
            roast_txt = f"أشهر تصريفاته: {card_data.get('top_excuse')}"

        badge = DIALECTS.get(dialect, DIALECTS["default"])["badge"]
        svg_code = bot.roast_engine.generate_shame_card_svg(card_data, roast_txt, badge)

        target_ch = bot.get_channel(int(os.getenv("MAIN_CHANNEL_ID", 0))) or (bot.guilds[0].system_channel if bot.guilds else None)
        if not target_ch:
            return web.Response(text=json.dumps({"ok": False, "error": "لم يتم العثور على روم لإرسال البطاقة"}), content_type="application/json")

        file_bytes = io.BytesIO(svg_code.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename=f"shame_card_{mid}.svg")

        embed = discord.Embed(
            title=f"🎴 بطاقة العار الرسمية: {member.display_name}",
            description=f"**اللقب:** {card_data.get('title')}\n**التهمة:** {card_data.get('crime')}\n\n**الإحصائيات الساخرة:**\n• نسبة التصريف: `{card_data['stats']['excuses']}%`\n• دقة الإيم: `{card_data['stats']['aim']}%`\n• معدل النكبة: `{card_data['stats']['choke']}%`\n• ساعات النوم: `{card_data['stats']['sleep']} ساعة`\n\n🎯 **الحكم:**\n\"{roast_txt}\"",
            color=0xa855f7
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await target_ch.send(content=f"🚨 **إشعار عار رسمي من لوحة التحكم:**", file=discord_file, embed=embed)

        return web.Response(text=json.dumps({"ok": True}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_court_start(request):
    """بدء جلسة محاكمة علنية طارئة ضد عضو وإرسالها للديسكورد مع أزرار التصويت."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("defendant_id", 0))
        charge = body.get("charge", "الصنم الأبدي وتخريب أجواء السيرفر").strip()
        dialect = body.get("dialect", bot.current_dialect)

        member = None
        for g in bot.guilds:
            member = g.get_member(mid)
            if member:
                break

        if not member:
            return web.Response(text=json.dumps({"ok": False, "error": "المتهم غير موجود بالسيرفر"}), content_type="application/json")

        indictment = await bot.roast_engine.generate_trial_indictment(member.display_name, charge, dialect=dialect)

        target_ch = bot.get_channel(int(os.getenv("MAIN_CHANNEL_ID", 0))) or (bot.guilds[0].system_channel if bot.guilds else None)
        if not target_ch:
            return web.Response(text=json.dumps({"ok": False, "error": "لم يتم العثور على روم المحاكمة"}), content_type="application/json")

        embed = discord.Embed(
            title=f"⚖️ {indictment.get('title', 'محكمة السيرفر العليا')}",
            description=f"**المتهم في قفص الاتهام:** {member.mention}\n**التهمة المنسوبة إليه:** {charge}\n\n📜 **لائحة الادعاء:**\n{indictment.get('indictment', '')}\n\n⚖️ **العقوبة المقترحة:**\n{indictment.get('penalty', '')}",
            color=0xff2a5f
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="جلسة محاكمة طارئة بدأت من لوحة التحكم • التصويت مفتوح 90 ثانية")

        view = CourtVoteView(member.id, member.display_name, charge, bot)
        await target_ch.send(content=f"🚨 **محاكمة علنية طارئة ضد {member.mention}!**", embed=embed, view=view)

        return web.Response(text=json.dumps({"ok": True, "indictment": indictment}, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_battle_judge(request):
    """تحكيم معركة ذبات 1v1 بين شخصين بواسطة الذكاء الاصطناعي."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        p1_name = body.get("p1_name", "المتحدي 1")
        p1_roast = body.get("p1_roast", "")
        p2_name = body.get("p2_name", "المتحدي 2")
        p2_roast = body.get("p2_roast", "")
        topic = body.get("topic", "نزاع حر")

        if not p1_roast or not p2_roast:
            return web.Response(text=json.dumps({"ok": False, "error": "يجب كتابة ذبة لكل من المتحديين"}), content_type="application/json")

        result = await bot.roast_engine.judge_battle(p1_name, p1_roast, p2_name, p2_roast, topic=topic)
        return web.Response(text=json.dumps({"ok": True, "result": result}, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_dialect_preview(request):
    """توليد مقارنة فورية بين الـ 4 لهجات في نفس الوقت على موضوع محدد."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        topic = body.get("topic", "واحد سحب علينا بالرانك وجاء اليوم الثاني كأنه ما صار شيء").strip()
        member_name = body.get("member_name", "العضو المستهدف").strip()

        if hasattr(bot, "dialect_engine") and bot.dialect_engine:
            comparisons = await bot.dialect_engine.generate_comparative(member_name, topic)
        else:
            prompt = get_comparative_prompt(topic, member_name)
            resp = await generate_content_ai(contents=prompt)
            raw_text = resp.text.replace('```json', '').replace('```', '').strip()
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                raw_text = match.group(0)
            comparisons = json.loads(raw_text)

        return web.Response(text=json.dumps({"ok": True, "comparisons": comparisons}, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        logger.error(f"Error in handle_dialect_preview: {e}")
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_ai_report(request):
    """توليد تقرير الاستخبارات الساخر للمجلس."""
    bot = request.app["bot"]
    try:
        stats = f"Online users in VC: {sum(len(vc.members) for g in bot.guilds for vc in g.voice_channels)}\n"
        stats += f"Total roasts: {sum(bot.roast_count_per_user.values())}\n"
        shame = sorted(bot.roast_count_per_user.items(), key=lambda x: -x[1])[:3]
        stats += f"Top 3 most roasted: {shame}\n"
        stats += f"Protected users: {len(bot.protected_users)}\n"
        stats += f"Active Dialect: {bot.current_dialect}"

        prompt = (
            "أنت مستر ذبات 3.0. حلل إحصائيات الديسكورد التالية واكتب تقرير مسائي ساخر جداً.\n"
            f"الإحصائيات: {stats}\n"
            "الناتج يجب أن يكون JSON فقط بالصيغة التالية بالضبط بدون أي نصوص أخرى:\n"
            "{\"title\": \"عنوان التقرير الساخر\", \"toxic_user\": \"أكثر عضو مسكين انجلد\", \"quiet_user\": \"أصنم عضو بالسيرفر\", \"summary\": \"ملخص ساخر للوضع سطرين\", \"advice\": \"نصيحة ساخرة للإدمن\"}"
        )
        response = await generate_content_ai(contents=prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        data = json.loads(text)
        return web.Response(text=json.dumps({"ok": True, "report": data}, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_cli_execute(request):
    """طرفية الأوامر السريعة Cyber CLI."""
    bot = request.app["bot"]
    try:
        body = await request.json()
        cmd_raw = body.get("command", "").strip()
        if not cmd_raw:
            return web.Response(text=json.dumps({"ok": False, "output": "No command provided"}), content_type="application/json")

        parts = cmd_raw.split()
        root = parts[0].lower()

        if root == "help":
            output = (
                "=== MR. ROAST OS 3.0 CYBER CLI COMMANDS ===\n"
                "• stats                     - عرض إحصائيات السيرفر السريعة\n"
                "• roast <id> [topic]        - إطلاق ذبة فورية على عضو محدد\n"
                "• court <id> <charge>       - فتح محاكمة طارئة ضد عضو في الديسكورد\n"
                "• shamecard <id>            - إصدار وإرسال بطاقة عار لعضو\n"
                "• dialect <default|riyadh|jeddah|qassim> - تغيير اللهجة النشطة\n"
                "• protect <id>              - إضافة عضو لقائمة الحماية\n"
                "• unprotect <id>            - إزالة عضو من الحماية\n"
                "• loop <on|off>             - تشغيل/إيقاف محرك القصف التلقائي\n"
                "• purge                     - تفريغ سجل الذبات المؤقت\n"
                "• clear                     - مسح الشاشة"
            )
            return web.Response(text=json.dumps({"ok": True, "output": output}), content_type="application/json")

        elif root == "stats":
            total_r = sum(bot.roast_count_per_user.values())
            uptime = int((time.time() - bot._start_time) / 60)
            output = (
                f"SYS STATUS: ONLINE | LOOP: {'ACTIVE' if bot.roast_loop.is_running() else 'OFFLINE'}\n"
                f"UPTIME: {uptime} mins | TOTAL ROASTS: {total_r}\n"
                f"ACTIVE DIALECT: {bot.current_dialect.upper()} ({DIALECTS.get(bot.current_dialect, {}).get('name')})\n"
                f"PROTECTED TARGETS: {len(bot.protected_users)}"
            )
            return web.Response(text=json.dumps({"ok": True, "output": output}), content_type="application/json")

        elif root == "dialect":
            if len(parts) > 1 and parts[1] in DIALECTS:
                bot.current_dialect = parts[1]
                bot.save_data()
                return web.Response(text=json.dumps({"ok": True, "output": f"SUCCESS: Dialect set to [{DIALECTS[parts[1]]['name']}]"}), content_type="application/json")
            return web.Response(text=json.dumps({"ok": False, "output": "USAGE: dialect <default|riyadh|jeddah|qassim>"}), content_type="application/json")

        elif root == "loop":
            if len(parts) > 1:
                action = parts[1].lower()
                if action == "on" and not bot.roast_loop.is_running():
                    try:
                        bot.roast_loop.start()
                    except RuntimeError:
                        bot.roast_loop.restart()
                elif action == "off" and bot.roast_loop.is_running():
                    bot.roast_loop.stop()
                    bot.roast_loop.cancel()
                return web.Response(text=json.dumps({"ok": True, "output": f"Roast loop state: {bot.roast_loop.is_running()}"}), content_type="application/json")
            return web.Response(text=json.dumps({"ok": False, "output": "USAGE: loop <on|off>"}), content_type="application/json")

        elif root == "protect":
            if len(parts) > 1:
                uid = int(parts[1].replace("<@", "").replace(">", "").strip())
                bot.protected_users.add(uid)
                return web.Response(text=json.dumps({"ok": True, "output": f"TARGET [{uid}] ADDED TO VIP IMMUNITY."}), content_type="application/json")
            return web.Response(text=json.dumps({"ok": False, "output": "USAGE: protect <user_id>"}), content_type="application/json")

        elif root == "unprotect":
            if len(parts) > 1:
                uid = int(parts[1].replace("<@", "").replace(">", "").strip())
                bot.protected_users.discard(uid)
                return web.Response(text=json.dumps({"ok": True, "output": f"TARGET [{uid}] REMOVED FROM IMMUNITY."}), content_type="application/json")
            return web.Response(text=json.dumps({"ok": False, "output": "USAGE: unprotect <user_id>"}), content_type="application/json")

        elif root == "purge":
            bot.roast_log.clear()
            bot.save_data()
            return web.Response(text=json.dumps({"ok": True, "output": "SYSTEM LOG PURGED."}), content_type="application/json")

        elif root == "roast":
            if len(parts) > 1:
                uid = int(parts[1].replace("<@", "").replace(">", "").strip())
                topic = " ".join(parts[2:]) if len(parts) > 2 else None
                ok = await bot.targeted_roast(uid, topic=topic)
                return web.Response(text=json.dumps({"ok": ok, "output": f"STRIKE EXECUTED on target [{uid}]" if ok else "STRIKE FAILED (target not found)"}), content_type="application/json")
            return web.Response(text=json.dumps({"ok": False, "output": "USAGE: roast <user_id> [topic]"}), content_type="application/json")

        else:
            return web.Response(text=json.dumps({"ok": False, "output": f"COMMAND NOT RECOGNIZED: '{root}'. Type 'help' for instructions."}), content_type="application/json")

    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "output": f"EXECUTION ERROR: {str(e)}"}), content_type="application/json")


# ─── FRONTEND HTML (QUANTUM CYBER DECK 3.0) ──────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>مستر ذبات 3.0 • QUANTUM CYBER DECK</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg-deep: #06090e;
  --bg-surface: #0c121b;
  --bg-card: rgba(16, 25, 38, 0.75);
  --bg-card-hover: rgba(22, 35, 54, 0.85);
  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-glow: rgba(0, 240, 255, 0.3);
  
  --cyan: #00f0ff;
  --cyan-dim: rgba(0, 240, 255, 0.12);
  --magenta: #ff0055;
  --magenta-dim: rgba(255, 0, 85, 0.15);
  --amber: #ffb703;
  --amber-dim: rgba(255, 183, 3, 0.12);
  --emerald: #00ff88;
  --emerald-dim: rgba(0, 255, 136, 0.12);
  --purple: #a855f7;
  --purple-dim: rgba(168, 85, 247, 0.15);

  --text-main: #f0f6fc;
  --text-muted: #8b949e;
  --text-dim: #484f58;

  --font-arabic: 'Cairo', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --glass: blur(16px);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg-deep);
  color: var(--text-main);
  font-family: var(--font-arabic);
  min-height: 100vh;
  overflow-x: hidden;
  position: relative;
}

/* Background Canvas */
#cyberCanvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
  opacity: 0.55;
}

/* Top App Bar */
.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(6, 9, 14, 0.85);
  backdrop-filter: var(--glass);
  border-bottom: 1px solid var(--border-subtle);
  padding: 0.75rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.brand-box {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}
.brand-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  border: 2px solid var(--cyan);
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.4);
  object-fit: cover;
}
.brand-titles h1 {
  font-size: 1.25rem;
  font-weight: 900;
  background: linear-gradient(135deg, #fff, var(--cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.version-badge {
  font-size: 0.65rem;
  font-family: var(--font-mono);
  background: var(--cyan-dim);
  color: var(--cyan);
  border: 1px solid var(--cyan);
  padding: 2px 6px;
  border-radius: 6px;
  letter-spacing: 1px;
}
.brand-titles p {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.chip-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  color: var(--text-main);
  padding: 0.45rem 0.9rem;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  transition: all 0.2s ease;
  font-family: var(--font-arabic);
}
.chip-btn:hover {
  border-color: var(--cyan);
  box-shadow: 0 0 12px rgba(0, 240, 255, 0.2);
  transform: translateY(-1px);
}
.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--emerald);
  box-shadow: 0 0 8px var(--emerald);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0% { transform: scale(0.95); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.95); opacity: 0.8; }
}

/* Nav Tabs */
.nav-tabs-wrapper {
  position: sticky;
  top: 61px;
  z-index: 90;
  background: rgba(8, 12, 18, 0.92);
  backdrop-filter: var(--glass);
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 2rem;
  overflow-x: auto;
}
.nav-tabs {
  display: flex;
  gap: 0.5rem;
  min-width: max-content;
}
.nav-tab {
  padding: 0.85rem 1.25rem;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-muted);
  border-bottom: 2px solid transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
}
.nav-tab:hover {
  color: var(--text-main);
}
.nav-tab.active {
  color: var(--cyan);
  border-bottom-color: var(--cyan);
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);
}

/* Main Layout */
.container {
  position: relative;
  z-index: 10;
  max-width: 1440px;
  margin: 0 auto;
  padding: 1.75rem 2rem 4rem;
}
.tab-content {
  display: none;
  animation: fadeIn 0.3s ease;
}
.tab-content.active {
  display: block;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Glass Cards */
.glass-card {
  background: var(--bg-card);
  backdrop-filter: var(--glass);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  padding: 1.5rem;
  position: relative;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.glass-card:hover {
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}
.glass-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 240, 255, 0.3), transparent);
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}
.card-title {
  font-size: 1.1rem;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* HUD Metric Cards Grid */
.hud-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.25rem;
  margin-bottom: 1.75rem;
}
.metric-card {
  padding: 1.25rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}
.metric-icon-box {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6rem;
}
.metric-val {
  font-size: 1.85rem;
  font-weight: 900;
  font-family: var(--font-mono);
  line-height: 1.1;
}
.metric-label {
  font-size: 0.8rem;
  color: var(--text-muted);
  font-weight: 600;
  margin-top: 0.2rem;
}

/* Fast Action Bar */
.action-strip {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1.75rem;
}
.cyber-btn {
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(0, 240, 255, 0.05));
  border: 1px solid var(--cyan);
  color: var(--cyan);
  padding: 0.75rem 1.4rem;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 700;
  font-family: var(--font-arabic);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.15);
}
.cyber-btn:hover {
  background: var(--cyan);
  color: #000;
  box-shadow: 0 0 25px rgba(0, 240, 255, 0.5);
  transform: translateY(-2px);
}
.cyber-btn.danger {
  background: linear-gradient(135deg, rgba(255, 0, 85, 0.15), rgba(255, 0, 85, 0.05));
  border-color: var(--magenta);
  color: var(--magenta);
  box-shadow: 0 0 15px rgba(255, 0, 85, 0.15);
}
.cyber-btn.danger:hover {
  background: var(--magenta);
  color: #fff;
  box-shadow: 0 0 25px rgba(255, 0, 85, 0.5);
}
.cyber-btn.purple {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.15), rgba(168, 85, 247, 0.05));
  border-color: var(--purple);
  color: var(--purple);
  box-shadow: 0 0 15px rgba(168, 85, 247, 0.15);
}
.cyber-btn.purple:hover {
  background: var(--purple);
  color: #fff;
  box-shadow: 0 0 25px rgba(168, 85, 247, 0.5);
}

/* Two Column Layout */
.layout-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
@media (max-width: 1024px) {
  .layout-2col { grid-template-columns: 1fr; }
}

/* Voice Chamber Radar */
.vc-members-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}
.member-radar-card {
  background: rgba(12, 18, 27, 0.6);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  transition: all 0.2s;
}
.member-radar-card:hover {
  border-color: var(--border-glow);
  background: rgba(16, 25, 38, 0.9);
}
.member-radar-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.member-radar-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.member-radar-avatar {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid var(--border-subtle);
}
.member-radar-name {
  font-weight: 800;
  font-size: 0.95rem;
}
.member-radar-title {
  font-size: 0.75rem;
  color: var(--cyan);
}
.badges-row {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.badge-chip {
  font-size: 0.7rem;
  padding: 2px 7px;
  border-radius: 5px;
  font-weight: 600;
}
.badge-muted { background: var(--magenta-dim); color: var(--magenta); border: 1px solid rgba(255, 0, 85, 0.3); }
.badge-deaf { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.badge-stream { background: var(--purple-dim); color: var(--purple); border: 1px solid rgba(168, 85, 247, 0.3); }
.badge-game { background: var(--cyan-dim); color: var(--cyan); border: 1px solid rgba(0, 240, 255, 0.3); }

/* Live Feeds */
.feed-box {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 420px;
  overflow-y: auto;
  padding-left: 0.5rem;
}
.feed-item {
  background: rgba(12, 18, 27, 0.5);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.feed-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.feed-member {
  font-weight: 800;
  color: var(--amber);
}
.feed-roast-text {
  font-size: 0.9rem;
  line-height: 1.5;
  color: var(--text-main);
}

/* 3D Shame Card Hologram Studio */
.shame-studio-grid {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 2rem;
  align-items: start;
}
@media (max-width: 900px) {
  .shame-studio-grid { grid-template-columns: 1fr; }
}

.holo-card-viewport {
  perspective: 1000px;
  display: flex;
  justify-content: center;
}
.holo-card {
  width: 320px;
  background: linear-gradient(145deg, #101622, #080c14);
  border: 2px solid var(--purple);
  box-shadow: 0 0 35px rgba(168, 85, 247, 0.25);
  border-radius: 20px;
  padding: 1.5rem;
  position: relative;
  overflow: hidden;
  transition: transform 0.15s ease-out, box-shadow 0.15s ease-out;
  transform-style: preserve-3d;
}
.holo-card::before {
  content: '';
  position: absolute;
  inset: -100%;
  background: linear-gradient(45deg, transparent 40%, rgba(255, 255, 255, 0.12) 50%, transparent 60%);
  pointer-events: none;
  transform: rotate(35deg);
}
.holo-avatar-wrap {
  position: relative;
  width: 96px;
  height: 96px;
  margin: 0 auto 1rem;
}
.holo-avatar {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  border: 3px solid var(--purple);
}
.holo-name {
  text-align: center;
  font-size: 1.25rem;
  font-weight: 900;
}
.holo-title {
  text-align: center;
  font-size: 0.8rem;
  color: var(--cyan);
  margin-bottom: 1.25rem;
}
.holo-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
  margin-bottom: 1.25rem;
}
.holo-stat-box {
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 0.6rem;
  text-align: center;
}
.holo-stat-val {
  font-size: 1.15rem;
  font-weight: 900;
  font-family: var(--font-mono);
  color: var(--amber);
}
.holo-stat-lbl {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.holo-quote {
  background: rgba(168, 85, 247, 0.1);
  border-right: 3px solid var(--purple);
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-style: italic;
  line-height: 1.4;
  color: #fff;
  min-height: 60px;
}

/* Courtroom Tab */
.court-banner {
  background: linear-gradient(135deg, rgba(255, 0, 85, 0.15), rgba(168, 85, 247, 0.1));
  border: 1px solid var(--magenta);
  border-radius: 16px;
  padding: 2rem;
  margin-bottom: 2rem;
  text-align: center;
  position: relative;
}
.court-banner h2 {
  font-size: 2rem;
  font-weight: 900;
  color: #fff;
  margin-bottom: 0.5rem;
}
.court-banner p {
  color: var(--text-muted);
  max-width: 600px;
  margin: 0 auto;
}

/* 1v1 Battle Arena */
.battle-ring {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 1.5rem;
  align-items: center;
  margin-bottom: 2rem;
}
@media (max-width: 800px) {
  .battle-ring { grid-template-columns: 1fr; }
}
.versus-badge {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--magenta);
  box-shadow: 0 0 25px rgba(255, 0, 85, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  font-family: var(--font-mono);
  font-size: 1.4rem;
  color: #fff;
  margin: 0 auto;
}

/* Dialects Cards */
.dialect-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}
.dialect-card {
  cursor: pointer;
  position: relative;
}
.dialect-card.selected {
  border-color: var(--cyan);
  box-shadow: 0 0 25px rgba(0, 240, 255, 0.3);
}
.metric-bar-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0;
}
.metric-bar-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.metric-bar-track {
  width: 120px;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}
.metric-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--cyan);
}

/* 4-Way Simulator */
.comparative-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
  margin-top: 1.5rem;
}
.sim-card {
  background: rgba(12, 18, 27, 0.6);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.25rem;
  min-height: 140px;
}
.sim-card-header {
  font-weight: 800;
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Cyber CLI Slide-Out */
#cyberCliModal {
  position: fixed;
  bottom: 20px;
  left: 20px;
  width: 480px;
  max-width: 90vw;
  height: 380px;
  background: rgba(6, 10, 16, 0.95);
  backdrop-filter: var(--glass);
  border: 1px solid var(--cyan);
  box-shadow: 0 0 35px rgba(0, 240, 255, 0.25);
  border-radius: 12px;
  z-index: 200;
  display: none;
  flex-direction: column;
  overflow: hidden;
  font-family: var(--font-mono);
}
.cli-header {
  background: rgba(0, 240, 255, 0.1);
  padding: 0.5rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(0, 240, 255, 0.2);
  font-size: 0.8rem;
  color: var(--cyan);
}
.cli-body {
  flex: 1;
  padding: 0.75rem 1rem;
  overflow-y: auto;
  font-size: 0.8rem;
  line-height: 1.5;
  color: #7ee787;
  white-space: pre-wrap;
}
.cli-input-line {
  display: flex;
  align-items: center;
  padding: 0.5rem 1rem;
  background: rgba(0, 0, 0, 0.4);
  border-top: 1px solid var(--border-subtle);
}
.cli-prompt {
  color: var(--cyan);
  margin-left: 0.5rem;
}
.cli-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #fff;
  font-family: var(--font-mono);
  font-size: 0.85rem;
  outline: none;
}

/* Inputs & Form Elements */
.input-control {
  width: 100%;
  background: rgba(12, 18, 27, 0.7);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 0.65rem 1rem;
  color: #fff;
  font-family: var(--font-arabic);
  font-size: 0.9rem;
  outline: none;
  transition: border-color 0.2s;
}
.input-control:focus {
  border-color: var(--cyan);
}
select.input-control option {
  background: #0d131d;
  color: #fff;
}
textarea.input-control {
  resize: vertical;
  min-height: 80px;
}

/* Toast System */
#toastHost {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 300;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  pointer-events: none;
}
.toast {
  background: rgba(16, 25, 38, 0.95);
  backdrop-filter: var(--glass);
  border: 1px solid var(--border-subtle);
  color: #fff;
  padding: 0.75rem 1.25rem;
  border-radius: 10px;
  font-size: 0.85rem;
  font-weight: 700;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: slideIn 0.3s ease;
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.toast.success { border-color: var(--emerald); }
.toast.danger { border-color: var(--magenta); }
@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

/* Scrollbars */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.3); }
</style>
</head>
<body>

<!-- Interactive Particle Neural Background -->
<canvas id="cyberCanvas"></canvas>

<!-- Top App Bar -->
<header class="topbar">
  <div class="brand-box">
    <img id="botAvatar" class="brand-avatar" src="" alt="Bot">
    <div class="brand-titles">
      <h1>
        <span id="botName">مستر ذبات</span>
        <span class="version-badge">OS 3.0</span>
      </h1>
      <p id="serverInfo">جاري الاتصال بالسيرفر...</p>
    </div>
  </div>

  <div class="topbar-actions">
    <button class="chip-btn" id="sfxToggleBtn" onclick="toggleAudioSFX()">
      <span id="sfxIcon">🔊</span>
      <span>مؤثرات الصوت: مفعّلة</span>
    </button>
    <button class="chip-btn" onclick="toggleCliModal()">
      <span>>_</span>
      <span>Cyber CLI</span>
    </button>
    <div class="chip-btn">
      <div class="pulse-dot"></div>
      <span id="loopStatusText">المحرك: نشط</span>
    </div>
  </div>
</header>

<!-- Navigation Tabs -->
<div class="nav-tabs-wrapper">
  <nav class="nav-tabs">
    <div class="nav-tab active" onclick="switchTab('tactical', this)">🛰️ العمليات التكتيكية</div>
    <div class="nav-tab" onclick="switchTab('shamecard', this)">🎴 استوديو بطاقات العار</div>
    <div class="nav-tab" onclick="switchTab('courtroom', this)">⚖️ محكمة السيرفر</div>
    <div class="nav-tab" onclick="switchTab('battle', this)">⚔️ حلبة المواجهات 1v1</div>
    <div class="nav-tab" onclick="switchTab('dialects', this)">🗣️ مختبر اللهجات الـ 4</div>
    <div class="nav-tab" onclick="switchTab('dossiers', this)">🗄️ أرشيف السوابق والفضائح</div>
    <div class="nav-tab" onclick="switchTab('analytics', this)">📊 الرادار والتحليلات</div>
  </nav>
</div>

<!-- Main Content Container -->
<main class="container">

  <!-- ================= TAB 1: TACTICAL OPERATIONS ================= -->
  <section id="tab-tactical" class="tab-content active">
    <!-- HUD Metrics -->
    <div class="hud-grid">
      <div class="glass-card metric-card">
        <div class="metric-icon-box" style="background:var(--magenta-dim); color:var(--magenta);">🎯</div>
        <div>
          <div class="metric-val" id="hudTotalRoasts">0</div>
          <div class="metric-label">إجمالي القصف والذبات</div>
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-icon-box" style="background:var(--cyan-dim); color:var(--cyan);">🎙️</div>
        <div>
          <div class="metric-val" id="hudActiveVc">0</div>
          <div class="metric-label">الأهداف في الفويس الآن</div>
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-icon-box" style="background:var(--amber-dim); color:var(--amber);">⚡</div>
        <div>
          <div class="metric-val" id="hudCurrentDialect">-</div>
          <div class="metric-label">اللهجة النشطة الرسمية</div>
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-icon-box" style="background:var(--emerald-dim); color:var(--emerald);">⏱️</div>
        <div>
          <div class="metric-val" id="hudNextRoast">0 د</div>
          <div class="metric-label">القصف العشوائي القادم</div>
        </div>
      </div>
    </div>

    <!-- Quick Tactical Actions -->
    <div class="action-strip">
      <button class="cyber-btn" onclick="forceRandomRoast()">
        <span>🚀 إطلاق قصف عشوائي فوري</span>
      </button>
      <button class="cyber-btn danger" onclick="toggleEngineLoop()">
        <span id="btnLoopToggleTxt">⏸️ إيقاف المحرك التلقائي</span>
      </button>
      <button class="cyber-btn purple" onclick="openQuickCourtModal()">
        <span>⚖️ فتح جلسة محاكمة فورية</span>
      </button>
      <button class="cyber-btn" onclick="generateAiReport()">
        <span>📑 توليد تقرير استخباراتي ساخر</span>
      </button>
    </div>

    <!-- Live Tactical Radar & Feeds -->
    <div class="layout-2col">
      <!-- Active Targets Radar -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">🎙️ رادار المتواجدين في الفويس (أهداف محتملة)</div>
          <span class="version-badge" id="vcCountBadge">0 أهداف</span>
        </div>
        <div class="vc-members-grid" id="vcRadarContainer">
          <p style="color:var(--text-muted);">لا يوجد أحد في الفويس حالياً... الجميع مختبئ!</p>
        </div>
      </div>

      <!-- Live Stream of Roasts -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">📜 رادار الذبات المباشر (Live Strike Feed)</div>
          <button class="chip-btn" onclick="fetchData()">🔄 تحديث</button>
        </div>
        <div class="feed-box" id="roastFeedContainer">
          <!-- Populated by JS -->
        </div>
      </div>
    </div>

    <!-- Tactical AI Alerts -->
    <div class="glass-card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <div class="card-title">🚨 تنبيهات الرادار الذكي (Tactical Recon Alerts)</div>
      </div>
      <div id="reconAlertsContainer" style="display:flex; flex-direction:column; gap:0.5rem;">
        <p style="color:var(--text-muted);">الرادار يمسح السيرفر... لا توجد خروقات حالياً.</p>
      </div>
    </div>
  </section>

  <!-- ================= TAB 2: SHAME CARDS STUDIO ================= -->
  <section id="tab-shamecard" class="tab-content">
    <div class="glass-card" style="margin-bottom: 2rem;">
      <div class="card-header">
        <div class="card-title">🎴 استوديو بطاقات العار الهولوغرافية (Shame Card Hologram Studio)</div>
      </div>
      <p style="color:var(--text-muted); margin-bottom: 1.5rem;">
        قم بإصدار بطاقة عار رسمية رقمية لأي عضو في السيرفر مع إحصائياته الفضائحية، لقبه المخزي، وذبته الخاصة بدقة عالية وإرسالها مباشرة لقناة الديسكورد!
      </p>

      <div class="shame-studio-grid">
        <!-- 3D Interactive Card Preview -->
        <div class="holo-card-viewport">
          <div class="holo-card" id="holoCardPreview" onmousemove="handleCardTilt(event, this)" onmouseleave="resetCardTilt(this)">
            <div class="holo-avatar-wrap">
              <img id="cardHoloAvatar" class="holo-avatar" src="https://cdn.discordapp.com/embed/avatars/0.png" alt="Avatar">
            </div>
            <div class="holo-name" id="cardHoloName">اسم العضو</div>
            <div class="holo-title" id="cardHoloTitle">أمير التصريفات</div>

            <div class="holo-stats">
              <div class="holo-stat-box">
                <div class="holo-stat-val" id="statExcuse">94%</div>
                <div class="holo-stat-lbl">نسبة التصريف</div>
              </div>
              <div class="holo-stat-box">
                <div class="holo-stat-val" id="statAim">12%</div>
                <div class="holo-stat-lbl">دقة الإيم</div>
              </div>
              <div class="holo-stat-box">
                <div class="holo-stat-val" id="statChoke">88%</div>
                <div class="holo-stat-lbl">معدل النكبة</div>
              </div>
              <div class="holo-stat-box">
                <div class="holo-stat-val" id="statSleep">14h</div>
                <div class="holo-stat-lbl">نوم وتصريف</div>
              </div>
            </div>

            <div class="holo-quote" id="cardHoloQuote">
              "أشهر تصريفاته: النت طفى فجأة وأمي تناديني!"
            </div>
          </div>
        </div>

        <!-- Studio Controls -->
        <div>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-bottom:1.25rem;">
            <div>
              <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">اختر العضو المستهدف:</label>
              <select id="shameMemberSelect" class="input-control" onchange="previewShameCard()">
                <!-- Populated dynamically -->
              </select>
            </div>
            <div>
              <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">اللهجة المعتمدة للبطاقة:</label>
              <select id="shameDialectSelect" class="input-control" onchange="previewShameCard()">
                <option value="default">عامية سعودية معاصرة</option>
                <option value="riyadh">لهجة الرياض / نجدية</option>
                <option value="jeddah">لهجة جدة / حجازية</option>
                <option value="qassim">لهجة القصيم</option>
              </select>
            </div>
          </div>

          <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
            <button class="cyber-btn purple" onclick="previewShameCard()">
              <span>🎲 إعادة توليد بيانات البطاقة</span>
            </button>
            <button class="cyber-btn danger" onclick="sendShameCardToDiscord()">
              <span>🚀 إرسال البطاقة لقناة الديسكورد فوراً</span>
            </button>
            <button class="cyber-btn" onclick="downloadShameCardSvg()">
              <span>📥 تحميل ملف SVG عالي الدقة</span>
            </button>
          </div>

          <div style="margin-top: 2rem; background:rgba(0,0,0,0.3); border:1px solid var(--border-subtle); border-radius:12px; padding:1.25rem;">
            <div style="font-weight:800; margin-bottom:0.5rem; color:var(--amber);">💡 مميزات بطاقة العار الرسمية:</div>
            <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.6;">
              • يتم تحليل سوابق العضو المسجلة في الـ Dossier وتوليد الإحصائيات الفضائحية بناءً على ساعات تواجده، تصريفاته الموثقة، ومعدل سكوته.<br>
              • البطاقة ترسل كملف رسومي متقدم (SVG) داخل ديسكورد ليتمكن الجميع من حفظها والتندر بها!
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ================= TAB 3: SERVER COURTROOM ================= -->
  <section id="tab-courtroom" class="tab-content">
    <div class="court-banner">
      <h2>⚖️ محكمة السيرفر العليا (Server Supreme Court)</h2>
      <p>محاكمات علنية مباشرة مع لائحة اتهام مدعومة بالذكاء الاصطناعي وتصويت حي بأزرار الديسكورد لمدة 90 ثانية لإدانة أو تبرئة المتهم!</p>
    </div>

    <div class="layout-2col">
      <!-- Trial Initiator -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">🔨 فتح جلسة محاكمة طارئة</div>
        </div>

        <div style="display:flex; flex-direction:column; gap:1rem;">
          <div>
            <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">المتهم في قفص الاتهام:</label>
            <select id="courtDefendantSelect" class="input-control">
              <!-- Populated dynamically -->
            </select>
          </div>

          <div>
            <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">التهمة الجنائية الموجهة له:</label>
            <input type="text" id="courtChargeInput" class="input-control" placeholder="مثال: الصنم الأبدي لمدة 3 ساعات وتخريب آخر قيم بالرانك">
          </div>

          <div>
            <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">نماذج اتهامات جاهزة وسريعة:</label>
            <div style="display:flex; gap:0.4rem; flex-wrap:wrap;">
              <button class="chip-btn" onclick="setCharge('الصنم الأبدي: مسوي ميوت ودفن وساهر على قلوبنا')">الصنم الأبدي</button>
              <button class="chip-btn" onclick="setCharge('تخريب الرانك: دخل ومات أول واحد وطلع يصرف')">تخريب الرانك</button>
              <button class="chip-btn" onclick="setCharge('ادعاء النوم: كاتب Sleeping وهو يلعب بالسيرفر')">ادعاء النوم الكاذب</button>
              <button class="chip-btn" onclick="setCharge('التصريف الاحترافي: قال بجيب موية واختفى 4 أيام')">تصريفة الموية</button>
            </div>
          </div>

          <div>
            <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">لهجة القاضي رئيس المحكمة:</label>
            <select id="courtDialectSelect" class="input-control">
              <option value="default">العامية السعودية</option>
              <option value="riyadh">نجدية / الرياض</option>
              <option value="jeddah">حجازية / جدة</option>
              <option value="qassim">قصيمية</option>
            </select>
          </div>

          <button class="cyber-btn danger" style="margin-top:0.5rem;" onclick="startCourtTrial()">
            <span>🔨 النطق ببدء المحاكمة وإرسال التصويت للديسكورد</span>
          </button>
        </div>
      </div>

      <!-- Courtroom Live Dossier Feed -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">📜 سجل الجرائم والإدانات الصادرة</div>
        </div>
        <div class="feed-box" id="courtCrimesFeed">
          <p style="color:var(--text-muted);">لا توجد جرائم مسجلة مؤخراً.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ================= TAB 4: 1v1 ROAST BATTLE ARENA ================= -->
  <section id="tab-battle" class="tab-content">
    <div class="glass-card">
      <div class="card-header">
        <div class="card-title">⚔️ حلبة مواجهات الذبات 1v1 (The Roast Battle Arena)</div>
      </div>
      <p style="color:var(--text-muted); margin-bottom: 2rem;">
        ضع أي شخصين أو اكتب ذباتهما، وسيقوم حكم الذكاء الاصطناعي (Gemini Flash مع التفكير العالي) بفحص الجبهات، تقييم القوة والسرعة، وإعلان الفائز بالضربة القاضية!
      </p>

      <div class="battle-ring">
        <!-- Fighter 1 -->
        <div class="glass-card" style="border-color: rgba(0, 240, 255, 0.3);">
          <div style="font-weight:900; color:var(--cyan); margin-bottom:0.75rem;">🥊 المتحدي الأول</div>
          <input type="text" id="battleP1Name" class="input-control" placeholder="اسم المتحدي الأول" value="سعود" style="margin-bottom:0.75rem;">
          <textarea id="battleP1Roast" class="input-control" placeholder="اكتب ذبة المتحدي الأول هنا..."></textarea>
        </div>

        <div class="versus-badge">VS</div>

        <!-- Fighter 2 -->
        <div class="glass-card" style="border-color: rgba(255, 0, 85, 0.3);">
          <div style="font-weight:900; color:var(--magenta); margin-bottom:0.75rem;">🥊 المتحدي الثاني</div>
          <input type="text" id="battleP2Name" class="input-control" placeholder="اسم المتحدي الثاني" value="خالد" style="margin-bottom:0.75rem;">
          <textarea id="battleP2Roast" class="input-control" placeholder="اكتب ذبة المتحدي الثاني هنا..."></textarea>
        </div>
      </div>

      <div style="margin-bottom: 1.5rem;">
        <label style="display:block; font-size:0.85rem; font-weight:700; margin-bottom:0.4rem;">موضوع النزاع (اختياري):</label>
        <input type="text" id="battleTopicInput" class="input-control" placeholder="مثال: من نكب الثاني في الرانك؟ أو من أكثر واحد يصرف؟">
      </div>

      <div style="display:flex; justify-content:center;">
        <button class="cyber-btn" style="padding:0.9rem 2.5rem; font-size:1.1rem;" onclick="judgeBattle()">
          <span>🔥 تحكيم الذكاء الاصطناعي وإعلان الفائز</span>
        </button>
      </div>

      <!-- Verdict Box -->
      <div id="battleVerdictContainer" style="display:none; margin-top:2rem; background:rgba(0,0,0,0.5); border:1px solid var(--amber); border-radius:14px; padding:1.5rem;">
        <div style="display:flex; align-items:center; gap:1rem; margin-bottom:1rem;">
          <div style="font-size:2rem;">🏆</div>
          <div>
            <div style="font-size:1.3rem; font-weight:900; color:var(--amber);" id="battleWinnerTitle">الفائز: -</div>
            <div style="font-size:0.85rem; color:var(--text-muted);" id="battleScoresTxt">النقاط: -</div>
          </div>
        </div>
        <p id="battleCommentaryTxt" style="line-height:1.6; font-size:0.95rem; color:#fff;"></p>
      </div>
    </div>
  </section>

  <!-- ================= TAB 5: DIALECTS & 4-WAY SIMULATOR ================= -->
  <section id="tab-dialects" class="tab-content">
    <div class="glass-card" style="margin-bottom: 2rem;">
      <div class="card-header">
        <div class="card-title">🗣️ نكسس اللهجات السعودية الرسمية (The Dialect Nexus)</div>
      </div>
      <p style="color:var(--text-muted); margin-bottom: 1.5rem;">
        تحكم في الهوية اللغوية لمستر ذبات! اختر لهجة السيرفر الرسمية واطلع على مقاييس كل لهجة:
      </p>

      <div class="dialect-grid" id="dialectCardsContainer">
        <!-- Rendered by JS -->
      </div>
    </div>

    <!-- 4-Way Comparative Simulator -->
    <div class="glass-card">
      <div class="card-header">
        <div class="card-title">⚡ المحاكي المقارن اللحظي (4-Dialect Comparative Simulator)</div>
      </div>
      <p style="color:var(--text-muted); margin-bottom: 1rem;">
        أدخل أي موقف أو زلة أو تهمة، وشاهد كيف يقصف مستر ذبات الجبهة بـ 4 لهجات مختلفة في نفس الثانية جنباً إلى جنب!
      </p>

      <div style="display:flex; gap:1rem; margin-bottom:1.25rem;">
        <input type="text" id="simTopicInput" class="input-control" placeholder="اكتب الموقف هنا (مثلاً: واحد خسرنا بالرانك وقال الماوس طفى شحنه)">
        <button class="cyber-btn" onclick="runComparativeSim()" style="white-space:nowrap;">
          <span>🚀 محاكاة الـ 4 لهجات</span>
        </button>
      </div>

      <div class="comparative-grid" id="comparativeResults">
        <div class="sim-card">
          <div class="sim-card-header">
            <span>⚡ عامية معاصرة</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.85rem;">في انتظار إطلاق المحاكاة...</p>
        </div>
        <div class="sim-card">
          <div class="sim-card-header">
            <span>🇸🇦 الرياض / نجدية</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.85rem;">في انتظار إطلاق المحاكاة...</p>
        </div>
        <div class="sim-card">
          <div class="sim-card-header">
            <span>🌴 جدة / حجازية</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.85rem;">في انتظار إطلاق المحاكاة...</p>
        </div>
        <div class="sim-card">
          <div class="sim-card-header">
            <span>🌾 القصيم</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.85rem;">في انتظار إطلاق المحاكاة...</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ================= TAB 6: CRIMINAL DOSSIER VAULT ================= -->
  <section id="tab-dossiers" class="tab-content">
    <div class="glass-card">
      <div class="card-header">
        <div class="card-title">🗄️ أرشيف السوابق والفضائح (Criminal Dossier Vault)</div>
        <div style="width:260px;">
          <select id="dossierMemberSelect" class="input-control" onchange="loadUserDossier()">
            <!-- Populated dynamically -->
          </select>
        </div>
      </div>

      <div id="dossierDisplayArea">
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:1.25rem; margin-bottom:2rem;">
          <!-- Titles -->
          <div class="glass-card" style="background:rgba(0,0,0,0.3);">
            <div style="font-weight:800; color:var(--cyan); margin-bottom:0.75rem;">🏷️ الألقاب والصفات الرسمية</div>
            <ul id="dossierTitlesList" style="list-style:none; display:flex; flex-direction:column; gap:0.4rem; font-size:0.85rem;">
              <li>لا توجد ألقاب</li>
            </ul>
          </div>

          <!-- Excuses -->
          <div class="glass-card" style="background:rgba(0,0,0,0.3);">
            <div style="font-weight:800; color:var(--amber); margin-bottom:0.75rem;">📜 التصريفات الموثقة</div>
            <ul id="dossierExcusesList" style="list-style:none; display:flex; flex-direction:column; gap:0.4rem; font-size:0.85rem;">
              <li>لا توجد تصريفات</li>
            </ul>
          </div>

          <!-- Moments -->
          <div class="glass-card" style="background:rgba(0,0,0,0.3);">
            <div style="font-weight:800; color:var(--purple); margin-bottom:0.75rem;">🤦 الفضائح والمواقف المحرجة</div>
            <ul id="dossierMomentsList" style="list-style:none; display:flex; flex-direction:column; gap:0.4rem; font-size:0.85rem;">
              <li>لا توجد مواقف مسجلة</li>
            </ul>
          </div>

          <!-- Crimes -->
          <div class="glass-card" style="background:rgba(0,0,0,0.3);">
            <div style="font-weight:800; color:var(--magenta); margin-bottom:0.75rem;">⚖️ إدانات المحكمة الجنائية</div>
            <ul id="dossierCrimesList" style="list-style:none; display:flex; flex-direction:column; gap:0.4rem; font-size:0.85rem;">
              <li>سجل نظيف حتى الآن</li>
            </ul>
          </div>
        </div>

        <!-- Add Entry Form -->
        <div class="glass-card" style="border-color: rgba(255, 255, 255, 0.1);">
          <div class="card-title" style="margin-bottom:1rem; font-size:0.95rem;">➕ إضافة سابقة أو تهمة جديدة لهذا العضو:</div>
          <div style="display:grid; grid-template-columns: 180px 1fr auto; gap:0.75rem;">
            <select id="dossierAddType" class="input-control">
              <option value="excuse">تصريفة موثقة</option>
              <option value="title">لقب رسمي</option>
              <option value="moment">موقف محرج</option>
              <option value="crime">إدانة جريمة</option>
            </select>
            <input type="text" id="dossierAddContent" class="input-control" placeholder="اكتب النص هنا...">
            <button class="cyber-btn" onclick="addDossierEntry()"><span>إضافة للملف</span></button>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ================= TAB 7: ANALYTICS & DEEP INTEL ================= -->
  <section id="tab-analytics" class="tab-content">
    <div class="layout-2col" style="margin-bottom: 2rem;">
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">📈 معدل القصف والذبات (آخر 7 أيام)</div>
        </div>
        <canvas id="dailyRoastChart" height="180"></canvas>
      </div>

      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">🕒 رادار أوقات الذروة والتواجد في الفويس (24 ساعة)</div>
        </div>
        <canvas id="hourlyActivityChart" height="180"></canvas>
      </div>
    </div>

    <div class="layout-2col">
      <!-- Hall of Shame -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">🏆 لوحة العار (أكثر الأعضاء تعرضاً للجلد)</div>
        </div>
        <div class="feed-box" id="shameLeaderboard">
          <!-- Populated by JS -->
        </div>
      </div>

      <!-- Protected VIPs -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title">🛡️ قائمة الحصانة الدبلوماسية (الأعضاء المحميون)</div>
        </div>
        <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">
          الأعضاء المدرجون هنا يتمتعون بحصانة مطلقة ضد القصف التلقائي والمحاكمات العشوائية.
        </p>
        <div style="display:flex; gap:0.75rem; margin-bottom:1rem;">
          <select id="protectMemberSelect" class="input-control">
            <!-- Populated dynamically -->
          </select>
          <button class="cyber-btn" onclick="addProtectedMember()"><span>إضافة حصانة</span></button>
        </div>
        <div id="protectedListContainer" style="display:flex; flex-direction:column; gap:0.5rem;">
          <!-- Populated by JS -->
        </div>
      </div>
    </div>
  </section>

</main>

<!-- Slide-Out Cyber CLI Terminal -->
<div id="cyberCliModal">
  <div class="cli-header">
    <span>MR. ROAST OS 3.0 // CYBER CLI TERMINAL</span>
    <span style="cursor:pointer;" onclick="toggleCliModal()">✕</span>
  </div>
  <div class="cli-body" id="cliOutput">Type 'help' to view available system commands.</div>
  <div class="cli-input-line">
    <span class="cli-prompt">></span>
    <input type="text" id="cliInput" class="cli-input" placeholder="enter command..." onkeydown="handleCliKey(event)">
  </div>
</div>

<!-- Toast Container -->
<div id="toastHost"></div>

<script>
// ─── Web Audio Synthesizer (Zero Audio Files Needed) ─────────────────────────
let audioCtx = null;
let sfxEnabled = true;

function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function playSound(type) {
  if (!sfxEnabled) return;
  try {
    initAudio();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const t = audioCtx.currentTime;

    if (type === 'beep') {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, t);
      osc.frequency.exponentialRampToValueAtTime(400, t + 0.08);
      gain.gain.setValueAtTime(0.12, t);
      gain.gain.linearRampToValueAtTime(0.01, t + 0.08);
      osc.connect(gain); gain.connect(audioCtx.destination);
      osc.start(t); osc.stop(t + 0.08);
    }
    else if (type === 'laser') {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(1200, t);
      osc.frequency.exponentialRampToValueAtTime(80, t + 0.25);
      gain.gain.setValueAtTime(0.2, t);
      gain.gain.linearRampToValueAtTime(0.01, t + 0.25);
      osc.connect(gain); gain.connect(audioCtx.destination);
      osc.start(t); osc.stop(t + 0.25);
    }
    else if (type === 'gavel') {
      // Deep resonant court gavel thud
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(160, t);
      osc.frequency.exponentialRampToValueAtTime(30, t + 0.4);
      gain.gain.setValueAtTime(0.5, t);
      gain.gain.linearRampToValueAtTime(0.01, t + 0.4);
      osc.connect(gain); gain.connect(audioCtx.destination);
      osc.start(t); osc.stop(t + 0.4);
    }
    else if (type === 'fanfare') {
      [300, 450, 600, 900].forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.setValueAtTime(freq, t + i * 0.07);
        gain.gain.setValueAtTime(0.15, t + i * 0.07);
        gain.gain.linearRampToValueAtTime(0.01, t + i * 0.07 + 0.2);
        osc.connect(gain); gain.connect(audioCtx.destination);
        osc.start(t + i * 0.07); osc.stop(t + i * 0.07 + 0.2);
      });
    }
  } catch(e) {}
}

function toggleAudioSFX() {
  sfxEnabled = !sfxEnabled;
  document.getElementById('sfxIcon').innerText = sfxEnabled ? '🔊' : '🔇';
  document.getElementById('sfxToggleBtn').children[1].innerText = sfxEnabled ? 'مؤثرات الصوت: مفعّلة' : 'مؤثرات الصوت: معطّلة';
  showToast(sfxEnabled ? 'تم تفعيل المؤثرات الصوتية' : 'تم تعطيل المؤثرات الصوتية', 'info');
}

// ─── Cyber Background Animation ──────────────────────────────────────────────
const canvas = document.getElementById('cyberCanvas');
const ctx = canvas.getContext('2d');
let particles = [];

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

class Particle {
  constructor() {
    this.x = Math.random() * canvas.width;
    this.y = Math.random() * canvas.height;
    this.vx = (Math.random() - 0.5) * 0.4;
    this.vy = (Math.random() - 0.5) * 0.4;
    this.radius = Math.random() * 1.8 + 0.6;
    this.color = Math.random() > 0.6 ? '#00f0ff' : (Math.random() > 0.5 ? '#ff0055' : '#a855f7');
  }
  update() {
    this.x += this.vx;
    this.y += this.vy;
    if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
    if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
  }
  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
    ctx.fillStyle = this.color;
    ctx.fill();
  }
}
for (let i = 0; i < 45; i++) particles.push(new Particle());

function animateCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < particles.length; i++) {
    particles[i].update();
    particles[i].draw();
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 110) {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(0, 240, 255, ${0.12 * (1 - dist / 110)})`;
        ctx.lineWidth = 0.6;
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.stroke();
      }
    }
  }
  requestAnimationFrame(animateCanvas);
}
animateCanvas();

// ─── Navigation & Tabs ───────────────────────────────────────────────────────
function switchTab(tabId, el) {
  playSound('beep');
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  if (el) el.classList.add('active');
}

// ─── 3D Card Hover Tilt ──────────────────────────────────────────────────────
function handleCardTilt(e, card) {
  const rect = card.getBoundingClientRect();
  const x = e.clientX - rect.left - rect.width / 2;
  const y = e.clientY - rect.top - rect.height / 2;
  const rotX = (y / (rect.height / 2)) * -12;
  const rotY = (x / (rect.width / 2)) * 12;
  card.style.transform = `rotateX(${rotX}deg) rotateY(${rotY}deg) scale(1.02)`;
}
function resetCardTilt(card) {
  card.style.transform = 'rotateX(0deg) rotateY(0deg) scale(1)';
}

// ─── Toast Notifications ─────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const host = document.getElementById('toastHost');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✅' : (type === 'danger' ? '❌' : 'ℹ️')}</span><span>${msg}</span>`;
  host.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3500);
}

// ─── State & Charts ─────────────────────────────────────────────────────────
let state = null;
let dailyChartInstance = null;
let hourlyChartInstance = null;

async function fetchData() {
  try {
    const res = await fetch('/api/stats');
    state = await res.json();
    renderDashboard(state);
  } catch (e) {
    console.error('Fetch stats error:', e);
  }
}

function renderDashboard(data) {
  // Brand & Guild
  if (data.bot_name) document.getElementById('botName').innerText = data.bot_name;
  if (data.bot_avatar) document.getElementById('botAvatar').src = data.bot_avatar;
  if (data.guild && data.guild.name) {
    document.getElementById('serverInfo').innerText = `${data.guild.name} • ${data.guild.online || 0} متصل الآن`;
  }

  // HUD
  document.getElementById('hudTotalRoasts').innerText = data.total_roasts || 0;
  document.getElementById('hudActiveVc').innerText = data.members_in_vc ? data.members_in_vc.length : 0;
  const nextMin = data.next_roast_in || 0;
  if (nextMin >= 60) {
    const hrs = Math.floor(nextMin / 60);
    const remMin = nextMin % 60;
    document.getElementById('hudNextRoast').innerText = remMin > 0 ? `${hrs} س ${remMin} د` : `${hrs} ساعات`;
  } else {
    document.getElementById('hudNextRoast').innerText = `${nextMin} د`;
  }
  document.getElementById('vcCountBadge').innerText = `${data.members_in_vc ? data.members_in_vc.length : 0} أهداف`;

  // Loop button
  const loopRunning = data.roast_loop_running;
  document.getElementById('loopStatusText').innerText = loopRunning ? 'المحرك: نشط' : 'المحرك: متوقف';
  document.getElementById('btnLoopToggleTxt').innerText = loopRunning ? '⏸️ إيقاف المحرك التلقائي' : '▶️ تشغيل المحرك التلقائي';

  // Populate Dropdowns
  populateMembersSelects(data);

  // Render VC Members
  renderVcRadar(data.members_in_vc || []);

  // Render Roast Feed
  renderRoastFeed(data.recent_roasts || []);

  // Render AI Alerts
  renderReconAlerts(data.alerts || []);

  // Render Dialect Cards
  renderDialectCards(data.dialects || [], data.current_dialect);

  // Render Hall of Shame
  renderHallOfShame(data.shame_board || []);

  // Render Protected List
  renderProtectedList(data.protected || []);

  // Render Charts
  renderCharts(data);
}

function populateMembersSelects(data) {
  const all = data.all_members || [];
  const inVc = data.members_in_vc || [];
  const combined = inVc.concat(all.filter(a => !inVc.some(v => v.id === a.id)));

  const fill = (selectId) => {
    const el = document.getElementById(selectId);
    if (!el) return;
    const curr = el.value;
    el.innerHTML = '';
    combined.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.innerText = m.name;
      el.appendChild(opt);
    });
    if (curr) el.value = curr;
  };

  fill('shameMemberSelect');
  fill('courtDefendantSelect');
  fill('dossierMemberSelect');
  fill('protectMemberSelect');
}

function renderVcRadar(members) {
  const container = document.getElementById('vcRadarContainer');
  if (!members.length) {
    container.innerHTML = '<p style="color:var(--text-muted); padding:1rem;">لا يوجد أحد في الفويس حالياً... الجميع مختبئ!</p>';
    return;
  }
  container.innerHTML = members.map(m => `
    <div class="member-radar-card">
      <div class="member-radar-top">
        <div class="member-radar-info">
          <img class="member-radar-avatar" src="${m.avatar}" alt="${m.name}">
          <div>
            <div class="member-radar-name">${m.name}</div>
            <div class="member-radar-title">${m.title || 'عضو عادي'}</div>
          </div>
        </div>
        <button class="chip-btn" onclick="quickRoastMember(${m.id})">🎯 اقصفه</button>
      </div>
      <div class="badges-row">
        <span class="badge-chip badge-game">⏱️ ${m.minutes} دقيقة</span>
        ${m.muted ? '<span class="badge-chip badge-muted">🔇 صامت (Muted)</span>' : ''}
        ${m.deafened ? '<span class="badge-chip badge-deaf">🦻 أطمش (Deafened)</span>' : ''}
        ${m.streaming ? '<span class="badge-chip badge-stream">📺 يبث شاشة</span>' : ''}
        ${m.games && m.games.length ? `<span class="badge-chip badge-game">🎮 ${m.games[0]}</span>` : ''}
      </div>
      <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-muted); margin-top:0.2rem;">
        <span>نسبة الكلام: ${m.speak_ratio}%</span>
        <span>عداد الحقد: 🔥 ${m.grudge}</span>
      </div>
    </div>
  `).join('');
}

function renderRoastFeed(roasts) {
  const container = document.getElementById('roastFeedContainer');
  if (!roasts.length) {
    container.innerHTML = '<p style="color:var(--text-muted); padding:1rem;">لا توجد قذائف مسجلة مؤخراً.</p>';
    return;
  }
  const rev = roasts.slice().reverse().slice(0, 30);
  container.innerHTML = rev.map(r => `
    <div class="feed-item">
      <div class="feed-meta">
        <span class="feed-member">🎯 الضحية: ${r.member}</span>
        <span>${new Date(r.time * 1000).toLocaleTimeString('ar-SA')}</span>
      </div>
      <div class="feed-roast-text">"${r.roast}"</div>
    </div>
  `).join('');
}

function renderReconAlerts(alerts) {
  const container = document.getElementById('reconAlertsContainer');
  if (!alerts.length) {
    container.innerHTML = '<p style="color:var(--text-muted);">الرادار يمسح السيرفر... لا توجد خروقات حالياً.</p>';
    return;
  }
  container.innerHTML = alerts.map(a => `
    <div style="background:rgba(255,0,85,0.08); border:1px solid rgba(255,0,85,0.3); border-radius:8px; padding:0.65rem 1rem; font-size:0.85rem; color:#fff;">
      ${a.msg}
    </div>
  `).join('');
}

function renderDialectCards(dialects, activeId) {
  const container = document.getElementById('dialectCardsContainer');
  container.innerHTML = dialects.map(d => {
    const isSel = d.id === activeId;
    const m = d.metrics || { sharpness: 85, speed: 90, authenticity: 95, humor: 90 };
    return `
      <div class="glass-card dialect-card ${isSel ? 'selected' : ''}" onclick="selectDialect('${d.id}')">
        <div class="card-header" style="margin-bottom:0.75rem;">
          <div style="font-size:1.15rem; font-weight:900;">${d.icon} ${d.name}</div>
          <span class="version-badge" style="color:var(--cyan); border-color:var(--cyan);">${d.badge}</span>
        </div>
        <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.75rem;">${d.region}</p>

        <div class="metric-bar-group">
          <div class="metric-bar-item">
            <span>حدة القصف</span>
            <div class="metric-bar-track"><div class="metric-bar-fill" style="width:${m.sharpness}%; background:var(--magenta);"></div></div>
          </div>
          <div class="metric-bar-item">
            <span>سرعة البديهة</span>
            <div class="metric-bar-track"><div class="metric-bar-fill" style="width:${m.speed}%; background:var(--cyan);"></div></div>
          </div>
          <div class="metric-bar-item">
            <span>أصالة المفردات</span>
            <div class="metric-bar-track"><div class="metric-bar-fill" style="width:${m.authenticity}%; background:var(--amber);"></div></div>
          </div>
          <div class="metric-bar-item">
            <span>خفة الدم</span>
            <div class="metric-bar-track"><div class="metric-bar-fill" style="width:${m.humor}%; background:var(--emerald);"></div></div>
          </div>
        </div>

        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-top:0.75rem;">
          ${(d.catchphrases || []).slice(0, 3).map(c => `<span class="badge-chip badge-game">${c}</span>`).join('')}
        </div>

        <div style="margin-top:1rem; text-align:center;">
          <button class="chip-btn" style="width:100%; justify-content:center; ${isSel ? 'background:var(--cyan); color:#000; border-color:var(--cyan);' : ''}">
            ${isSel ? '✓ اللهجة النشطة حالياً' : 'تفعيل هذه اللهجة'}
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderHallOfShame(shameList) {
  const container = document.getElementById('shameLeaderboard');
  if (!shameList.length) {
    container.innerHTML = '<p style="color:var(--text-muted); padding:1rem;">لا توجد بيانات عار مسجلة بعد.</p>';
    return;
  }
  container.innerHTML = shameList.map((s, idx) => `
    <div class="feed-item" style="display:flex; flex-direction:row; align-items:center; justify-content:space-between;">
      <div style="display:flex; align-items:center; gap:0.75rem;">
        <span style="font-weight:900; font-size:1.1rem; color:${idx === 0 ? 'var(--amber)' : (idx === 1 ? '#e2e8f0' : '#d97706')};">#${idx + 1}</span>
        <img src="${s.avatar}" style="width:38px; height:38px; border-radius:8px; object-fit:cover;">
        <div>
          <div style="font-weight:800; font-size:0.9rem;">${s.name}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${s.title} • أكلها ${s.count} مرة</div>
        </div>
      </div>
      <div style="text-align:left;">
        <span class="badge-chip badge-muted">🔥 حقد ${s.grudge}</span>
      </div>
    </div>
  `).join('');
}

function renderProtectedList(list) {
  const container = document.getElementById('protectedListContainer');
  if (!list.length) {
    container.innerHTML = '<p style="color:var(--text-muted);">لا يوجد أي شخص محمي حالياً.</p>';
    return;
  }
  container.innerHTML = list.map(p => `
    <div style="display:flex; align-items:center; justify-content:space-between; background:rgba(0,0,0,0.3); padding:0.6rem 0.85rem; border-radius:8px;">
      <div style="display:flex; align-items:center; gap:0.5rem;">
        <img src="${p.avatar}" style="width:30px; height:30px; border-radius:6px; object-fit:cover;">
        <span style="font-size:0.85rem; font-weight:700;">${p.name}</span>
      </div>
      <button class="chip-btn" style="padding:2px 8px; font-size:0.75rem;" onclick="removeProtectedMember(${p.id})">إلغاء الحصانة</button>
    </div>
  `).join('');
}

function renderCharts(data) {
  if (data.daily_chart) {
    const labels = Object.keys(data.daily_chart);
    const vals = Object.values(data.daily_chart);
    if (!dailyChartInstance) {
      const ctx1 = document.getElementById('dailyRoastChart').getContext('2d');
      dailyChartInstance = new Chart(ctx1, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'عدد القذائف اليومية',
            data: vals,
            backgroundColor: 'rgba(0, 240, 255, 0.4)',
            borderColor: '#00f0ff',
            borderWidth: 1.5,
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e', font: { family: 'Cairo' } } },
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e', stepSize: 1 } }
          }
        }
      });
    } else {
      dailyChartInstance.data.labels = labels;
      dailyChartInstance.data.datasets[0].data = vals;
      dailyChartInstance.update();
    }
  }

  if (data.hourly_activity) {
    const hLabels = Array.from({length: 24}, (_, i) => `${i}:00`);
    if (!hourlyChartInstance) {
      const ctx2 = document.getElementById('hourlyActivityChart').getContext('2d');
      hourlyChartInstance = new Chart(ctx2, {
        type: 'line',
        data: {
          labels: hLabels,
          datasets: [{
            label: 'نشاط الفويس (24 ساعة)',
            data: data.hourly_activity,
            borderColor: '#a855f7',
            backgroundColor: 'rgba(168, 85, 247, 0.15)',
            fill: true,
            tension: 0.35,
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e' } },
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e', stepSize: 1 } }
          }
        }
      });
    } else {
      hourlyChartInstance.data.datasets[0].data = data.hourly_activity;
      hourlyChartInstance.update();
    }
  }
}

// ─── Actions & API Calls ─────────────────────────────────────────────────────

async function forceRandomRoast() {
  playSound('laser');
  try {
    const res = await fetch('/api/force_roast', { method: 'POST' });
    const json = await res.json();
    if (json.ok) {
      showToast('🚀 تم إطلاق قصف عشوائي في السيرفر!');
      setTimeout(fetchData, 2000);
    }
  } catch (e) { showToast('خطأ أثناء إطلاق القصف', 'danger'); }
}

async function toggleEngineLoop() {
  playSound('beep');
  try {
    const res = await fetch('/api/toggle', { method: 'POST' });
    const json = await res.json();
    showToast(json.running ? 'تم تشغيل محرك القصف التلقائي' : 'تم إيقاف محرك القصف التلقائي');
    fetchData();
  } catch (e) { showToast('خطأ أثناء تبديل حالة المحرك', 'danger'); }
}

async function quickRoastMember(memberId) {
  playSound('laser');
  try {
    const res = await fetch('/api/targeted_roast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: memberId, intensity: 4 })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('🚀 تم توجيه قصف مركز على العضو!');
      setTimeout(fetchData, 2000);
    } else {
      showToast(json.error || 'فشل القصف', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء القصف', 'danger'); }
}

async function selectDialect(dialectId) {
  playSound('beep');
  try {
    const res = await fetch('/api/change_dialect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dialect: dialectId })
    });
    const json = await res.json();
    if (json.ok) {
      showToast(`تم تحويل لهجة مستر ذبات الرسمية إلى: ${json.name} 🗣️`);
      fetchData();
    }
  } catch (e) { showToast('خطأ أثناء تغيير اللهجة', 'danger'); }
}

// ─── Shame Card Hologram Studio ──────────────────────────────────────────────
let currentShameSvg = '';

async function previewShameCard() {
  const memberId = document.getElementById('shameMemberSelect').value;
  const dialect = document.getElementById('shameDialectSelect').value;
  if (!memberId) return;

  playSound('beep');
  showToast('جاري توليد بطاقة العار الرقمية...', 'info');

  try {
    const res = await fetch('/api/shame_card', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: memberId, dialect: dialect })
    });
    const json = await res.json();
    if (json.ok) {
      const cd = json.card_data;
      document.getElementById('cardHoloAvatar').src = cd.avatar || 'https://cdn.discordapp.com/embed/avatars/0.png';
      document.getElementById('cardHoloName').innerText = cd.name;
      document.getElementById('cardHoloTitle').innerText = cd.title;
      document.getElementById('statExcuse').innerText = `${cd.stats.excuses}%`;
      document.getElementById('statAim').innerText = `${cd.stats.aim}%`;
      document.getElementById('statChoke').innerText = `${cd.stats.choke}%`;
      document.getElementById('statSleep').innerText = `${cd.stats.sleep}h`;
      document.getElementById('cardHoloQuote').innerText = `"${json.roast_text}"`;
      currentShameSvg = json.svg;
      showToast('تم تجهيز بطاقة العار بنجاح!');
    } else {
      showToast(json.error || 'فشل توليد البطاقة', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء تجهيز البطاقة', 'danger'); }
}

async function sendShameCardToDiscord() {
  const memberId = document.getElementById('shameMemberSelect').value;
  const dialect = document.getElementById('shameDialectSelect').value;
  if (!memberId) return;

  playSound('fanfare');
  showToast('جاري إرسال بطاقة العار إلى ديسكورد...', 'info');

  try {
    const res = await fetch('/api/shame_card_send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: memberId, dialect: dialect })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('🚀 تم إرسال بطاقة العار بنجاح إلى القناة العامة!');
    } else {
      showToast(json.error || 'فشل الإرسال', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء الإرسال للديسكورد', 'danger'); }
}

function downloadShameCardSvg() {
  if (!currentShameSvg) {
    showToast('قم بتوليد بطاقة العار أولاً', 'danger');
    return;
  }
  const blob = new Blob([currentShameSvg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `shame_card_${Date.now()}.svg`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('تم تنزيل ملف SVG بنجاح!');
}

// ─── Courtroom Actions ───────────────────────────────────────────────────────
function setCharge(text) {
  document.getElementById('courtChargeInput').value = text;
  playSound('beep');
}

function openQuickCourtModal() {
  switchTab('courtroom');
}

async function startCourtTrial() {
  const defId = document.getElementById('courtDefendantSelect').value;
  const charge = document.getElementById('courtChargeInput').value.trim();
  const dialect = document.getElementById('courtDialectSelect').value;

  if (!defId || !charge) {
    showToast('يرجى تحديد المتهم وكتابة التهمة', 'danger');
    return;
  }

  playSound('gavel');
  showToast('🔨 جاري فتح جلسة المحاكمة وإرسال التصويت للديسكورد...', 'info');

  try {
    const res = await fetch('/api/court/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ defendant_id: defId, charge: charge, dialect: dialect })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('⚖️ بدأت المحاكمة في الديسكورد! التصويت مفتوح 90 ثانية للأعضاء.');
      setTimeout(fetchData, 2000);
    } else {
      showToast(json.error || 'فشل بدء المحاكمة', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء بدء المحاكمة', 'danger'); }
}

// ─── 1v1 Battle Arena ────────────────────────────────────────────────────────
async function judgeBattle() {
  const p1Name = document.getElementById('battleP1Name').value.trim();
  const p1Roast = document.getElementById('battleP1Roast').value.trim();
  const p2Name = document.getElementById('battleP2Name').value.trim();
  const p2Roast = document.getElementById('battleP2Roast').value.trim();
  const topic = document.getElementById('battleTopicInput').value.trim();

  if (!p1Roast || !p2Roast) {
    showToast('يرجى كتابة ذبة لكل من المتحديين', 'danger');
    return;
  }

  playSound('laser');
  showToast('الحكم يفحص الجبهات ويقيم الأضرار...', 'info');

  try {
    const res = await fetch('/api/battle/judge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        p1_name: p1Name,
        p1_roast: p1Roast,
        p2_name: p2Name,
        p2_roast: p2Roast,
        topic: topic
      })
    });
    const json = await res.json();
    if (json.ok) {
      playSound('fanfare');
      const r = json.result;
      document.getElementById('battleVerdictContainer').style.display = 'block';
      document.getElementById('battleWinnerTitle').innerText = `🏆 الفائز بالضربة القاضية: ${r.winner || 'تعادل'}`;
      document.getElementById('battleScoresTxt').innerText = `النقاط: ${p1Name} (${r.score1 || 0}/10) | ${p2Name} (${r.score2 || 0}/10)`;
      document.getElementById('battleCommentaryTxt').innerText = r.commentary || r.verdict || '';
      showToast('تم صدور قرار الحكم الرسمي!');
    } else {
      showToast(json.error || 'فشل التحكيم', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء تحكيم المعركة', 'danger'); }
}

// ─── 4-Way Comparative Simulator ─────────────────────────────────────────────
async function runComparativeSim() {
  const topic = document.getElementById('simTopicInput').value.trim();
  if (!topic) {
    showToast('يرجى كتابة الموقف للمحاكاة', 'danger');
    return;
  }

  playSound('beep');
  showToast('جاري استدعاء الـ 4 لهجات في نفس اللحظة...', 'info');

  try {
    const res = await fetch('/api/dialect/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic: topic })
    });
    const json = await res.json();
    if (json.ok) {
      playSound('laser');
      const c = json.comparisons;
      document.getElementById('comparativeResults').innerHTML = `
        <div class="sim-card" style="border-color:var(--cyan);">
          <div class="sim-card-header"><span style="color:var(--cyan);">⚡ عامية معاصرة</span></div>
          <p style="font-size:0.9rem; line-height:1.5;">${c.default || '-'}</p>
        </div>
        <div class="sim-card" style="border-color:var(--amber);">
          <div class="sim-card-header"><span style="color:var(--amber);">🇸🇦 الرياض / نجدية</span></div>
          <p style="font-size:0.9rem; line-height:1.5;">${c.riyadh || '-'}</p>
        </div>
        <div class="sim-card" style="border-color:var(--emerald);">
          <div class="sim-card-header"><span style="color:var(--emerald);">🌴 جدة / حجازية</span></div>
          <p style="font-size:0.9rem; line-height:1.5;">${c.jeddah || '-'}</p>
        </div>
        <div class="sim-card" style="border-color:var(--magenta);">
          <div class="sim-card-header"><span style="color:var(--magenta);">🌾 القصيم</span></div>
          <p style="font-size:0.9rem; line-height:1.5;">${c.qassim || '-'}</p>
        </div>
      `;
      showToast('تمت المحاكاة بـ 4 لهجات بنجاح!');
    }
  } catch (e) { showToast('خطأ أثناء تشغيل المحاكي', 'danger'); }
}

// ─── Dossier Manager ─────────────────────────────────────────────────────────
async function loadUserDossier() {
  const uid = document.getElementById('dossierMemberSelect').value;
  if (!uid) return;

  try {
    const res = await fetch(`/api/dossier?member_id=${uid}`);
    const json = await res.json();
    if (json.ok) {
      const d = json.dossier;
      const renderList = (listId, items) => {
        const el = document.getElementById(listId);
        if (!items || !items.length) {
          el.innerHTML = '<li style="color:var(--text-muted);">لا توجد عناصر</li>';
          return;
        }
        el.innerHTML = items.map(it => `<li>• ${it}</li>`).join('');
      };
      renderList('dossierTitlesList', d.titles);
      renderList('dossierExcusesList', d.excuses);
      renderList('dossierMomentsList', d.embarrassing_moments);
      renderList('dossierCrimesList', d.crimes);
    }
  } catch (e) { console.error('Dossier fetch error:', e); }
}

async function addDossierEntry() {
  const uid = document.getElementById('dossierMemberSelect').value;
  const type = document.getElementById('dossierAddType').value;
  const content = document.getElementById('dossierAddContent').value.trim();

  if (!uid || !content) {
    showToast('يرجى إدخال محتوى السابقة', 'danger');
    return;
  }

  playSound('beep');
  try {
    const res = await fetch('/api/dossier/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: uid, type: type, content: content })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('تم توثيق السابقة في ملف العضو بنجاح!');
      document.getElementById('dossierAddContent').value = '';
      loadUserDossier();
    }
  } catch (e) { showToast('خطأ أثناء إضافة السابقة', 'danger'); }
}

// ─── Protected VIPs ──────────────────────────────────────────────────────────
async function addProtectedMember() {
  const uid = document.getElementById('protectMemberSelect').value;
  if (!uid) return;
  playSound('beep');
  try {
    const res = await fetch('/api/protect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: uid, action: 'add' })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('تم منح الحصانة المطلقة للعضو!');
      fetchData();
    }
  } catch (e) { showToast('خطأ أثناء إضافة الحصانة', 'danger'); }
}

async function removeProtectedMember(uid) {
  playSound('beep');
  try {
    const res = await fetch('/api/protect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ member_id: uid, action: 'remove' })
    });
    const json = await res.json();
    if (json.ok) {
      showToast('تم إلغاء الحصانة عن العضو!');
      fetchData();
    }
  } catch (e) { showToast('خطأ أثناء إلغاء الحصانة', 'danger'); }
}

// ─── AI Intelligence Server Report ──────────────────────────────────────────
async function generateAiReport() {
  playSound('laser');
  showToast('جاري استخراج التقرير الاستخباراتي الساخر بالذكاء الاصطناعي...', 'info');
  try {
    const res = await fetch('/api/ai_report', { method: 'POST' });
    const json = await res.json();
    if (json.ok) {
      playSound('fanfare');
      const r = json.report;
      alert(`📊 ${r.title}\n\n• أكثر عضو انجلد: ${r.toxic_user}\n• أصنم عضو: ${r.quiet_user}\n\n📝 الملخص:\n${r.summary}\n\n💡 نصيحة للإدمن:\n${r.advice}`);
    } else {
      showToast(json.error || 'فشل توليد التقرير', 'danger');
    }
  } catch (e) { showToast('خطأ أثناء توليد التقرير', 'danger'); }
}

// ─── Cyber CLI Terminal ──────────────────────────────────────────────────────
function toggleCliModal() {
  const modal = document.getElementById('cyberCliModal');
  const isShown = modal.style.display === 'flex';
  modal.style.display = isShown ? 'none' : 'flex';
  playSound('beep');
  if (!isShown) document.getElementById('cliInput').focus();
}

async function handleCliKey(e) {
  if (e.key === 'Enter') {
    const input = document.getElementById('cliInput');
    const cmd = input.value.trim();
    if (!cmd) return;
    input.value = '';

    const out = document.getElementById('cliOutput');
    out.innerText += `\n> ${cmd}`;

    if (cmd.toLowerCase() === 'clear') {
      out.innerText = 'Terminal cleared.';
      return;
    }

    try {
      const res = await fetch('/api/cli/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd })
      });
      const json = await res.json();
      out.innerText += `\n${json.output || 'OK'}`;
      out.scrollTop = out.scrollHeight;
    } catch (err) {
      out.innerText += `\nERR: ${err.message}`;
    }
  }
}

// ─── Boot Sequence ───────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  fetchData();
  setInterval(fetchData, 5000);
});
</script>
</body>
</html>"""

async def handle_index(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_health(request):
    """
    Health check endpoint for Render, Docker, and monitoring probes.
    Guaranteed to return HTTP 200 with status telemetry.
    Reports degraded status when Discord is offline without failing the probe.
    """
    bot = request.app.get("bot")
    start_time = request.app.get("start_time", time.time())

    uptime_seconds = round(float(time.time() - start_time), 2)

    # Check Discord readiness safely
    discord_ready = False
    if bot is not None:
        is_ready_fn = getattr(bot, "is_ready", None)
        if callable(is_ready_fn):
            try:
                discord_ready = bool(is_ready_fn())
            except Exception:
                discord_ready = False

    # Status reporting:
    # "healthy" when Discord bot is connected and ready.
    # "degraded" when Discord is connecting, failed, or disabled (token missing).
    # Note: HTTP status code is ALWAYS 200 to keep cloud container routing active.
    status = "healthy" if discord_ready else "degraded"

    payload = {
        "status": status,
        "service": "mr-roast",
        "version": "3.0",
        "discord_ready": discord_ready,
        "uptime": uptime_seconds
    }

    return web.json_response(payload, status=200)


def create_web_app(bot_instance) -> web.Application:
    app = web.Application()
    app["bot"] = bot_instance
    app["start_time"] = time.time()

    # Register Health Check Routes FIRST
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/health", handle_health)

    app.router.add_get("/",                     handle_index)
    app.router.add_get("/api/stats",            handle_stats)
    app.router.add_post("/api/toggle",          handle_toggle)
    app.router.add_post("/api/force_roast",     handle_force_roast)
    app.router.add_post("/api/targeted_roast",  handle_targeted_roast)
    app.router.add_post("/api/custom_roast",    handle_custom_roast)
    app.router.add_post("/api/free_message",    handle_free_message)
    app.router.add_post("/api/change_dialect",  handle_change_dialect)
    app.router.add_post("/api/change_interval", handle_change_interval)
    app.router.add_post("/api/protect",         handle_protect)
    app.router.add_get("/api/dossier",          handle_dossier)
    app.router.add_post("/api/dossier/add",     handle_add_dossier_item)
    app.router.add_post("/api/shame_card",      handle_shame_card)
    app.router.add_post("/api/shame_card_send", handle_shame_card_send)
    app.router.add_post("/api/court/start",     handle_court_start)
    app.router.add_post("/api/battle/judge",    handle_battle_judge)
    app.router.add_post("/api/dialect/preview", handle_dialect_preview)
    app.router.add_post("/api/ai_report",       handle_ai_report)
    app.router.add_post("/api/cli/execute",     handle_cli_execute)
    return app


async def start_web_server(bot_instance, host: str = "0.0.0.0", port: int = None, max_fallback_attempts: int = 5):
    """
    Starts the aiohttp web server with resilient port binding,
    automatic port conflict fallback (in local dev), and safe lifecycle tracking.

    Returns:
        tuple[web.AppRunner, web.TCPSite, int]: (runner, site, bound_port) or (runner, None, None) on failure
    """
    start_time = time.time()
    if bot_instance is not None:
        try:
            bot_instance._start_time = start_time
        except Exception:
            pass

    if port is None:
        raw_port = os.environ.get("PORT", "8080")
        try:
            port = int(raw_port)
        except ValueError:
            logger.warning(f"Invalid PORT environment variable '{raw_port}'. Falling back to 8080.")
            port = 8080

    app = create_web_app(bot_instance)
    app["start_time"] = start_time
    runner = web.AppRunner(app)
    await runner.setup()

    is_cloud_env = "RENDER" in os.environ or "DYNO" in os.environ
    attempts = 1 if is_cloud_env else max_fallback_attempts

    bound_port = None
    site = None

    for attempt in range(attempts):
        candidate_port = port + attempt
        try:
            site = web.TCPSite(runner, host, candidate_port, reuse_address=True)
            await site.start()
            bound_port = candidate_port
            logger.info(f"Mr. Roast OS 3.0 Web Dashboard active on http://{host}:{bound_port}")
            print(f"Mr. Roast OS 3.0 Web Dashboard running on port {bound_port}")
            break
        except OSError as e:
            logger.warning(f"Port {candidate_port} is currently unavailable ({e}).")
            if attempt < attempts - 1:
                logger.info(f"Attempting fallback port {candidate_port + 1}...")
            else:
                logger.error(f"Could not bind to any port after {attempts} attempts.")
                if is_cloud_env:
                    logger.critical(f"FATAL: Render requires binding to designated PORT={port}. Check for process conflicts.")
                    await runner.cleanup()
                    raise

    if bound_port is None:
        logger.error("Web dashboard failed to start. Bot operating in headless mode.")
        await runner.cleanup()
        return runner, None, None

    return runner, site, bound_port
