"""
web_dashboard.py – لوحة تحكم شاملة لبوت مستر ذبات
14 ميزة: إحصائيات، لوحة العار، رسم بياني، أوقات الذروة، ألعاب شعبية،
ذبة موجهة، سلايدر الوقت، قائمة حماية، رسالة حرة، لوق كامل،
حالة البوت، إشعارات، وضع ليلي/نهاري، متجاوب
"""
import asyncio
import json
import os
import time
import discord
from aiohttp import web
from google import genai
from google.genai import types
from modules.dialects import DIALECTS, get_dialect_prompt
from modules.dossier import dossier_mgr

AFK_CHANNEL_ID = 782986605148635166

# ─── API endpoints ──────────────────────────────────────────────────────

async def handle_stats(request):
    bot = request.app["bot"]
    members_in_vc = []
    total_vc_minutes = 0
    guild_info = {}

    for guild in bot.guilds:
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
                            activities.append({"type":"playing","name":act.name})
                        elif act.type == discord.ActivityType.streaming:
                            activities.append({"type":"streaming","name":getattr(act,'game',act.name)})
                        elif act.type == discord.ActivityType.listening:
                            activities.append({"type":"listening","name":act.name})
                        elif act.type == discord.ActivityType.custom:
                            custom_status = getattr(act,'name','') or getattr(act,'state','') or ''
                    # حساب نسبة الكلام
                    spk = bot.user_speak_history.get(m.id, {"unmuted_sec": 0, "last_unmute": 0})
                    unmuted_time = spk["unmuted_sec"]
                    if spk["last_unmute"] > 0:
                        unmuted_time += (time.time() - spk["last_unmute"])
                    
                    speak_ratio = 0
                    if mins > 0:
                        speak_ratio = int((unmuted_time / (mins * 60)) * 100)

                    members_in_vc.append({
                        "id":m.id,"name":m.display_name,
                        "avatar":str(m.display_avatar.url),
                        "minutes":mins,"channel":vc.name,"games":games,
                        "activities":activities,"custom_status":custom_status,
                        "muted":m.voice.self_mute or m.voice.mute if m.voice else False,
                        "deafened":m.voice.self_deaf or m.voice.deaf if m.voice else False,
                        "streaming":m.voice.self_stream if m.voice else False,
                        "status":str(m.status),
                        "protected": m.id in bot.protected_users,
                        "speak_ratio": speak_ratio
                    })

    # كل الأعضاء
    all_members = []
    for guild in bot.guilds:
        for m in guild.members:
            if not m.bot:
                all_members.append({"id":m.id,"name":m.display_name,"avatar":str(m.display_avatar.url)})

    # لوحة العار والحقد
    shame = []
    for guild in bot.guilds:
        for uid, cnt in sorted(bot.roast_count_per_user.items(), key=lambda x:-x[1])[:15]:
            m = guild.get_member(uid)
            if m:
                grudge_lvl = getattr(bot, 'grudge_levels', {}).get(uid, 0)
                shame.append({"id":uid,"name":m.display_name,"avatar":str(m.display_avatar.url),"count":cnt,"grudge":grudge_lvl})

    # ألعاب شعبية
    top_games = sorted(bot.game_popularity.items(), key=lambda x:-x[1])[:10]
    top_games = [{"name":g,"count":c} for g,c in top_games]

    # آخر 7 أيام ذبات
    import datetime
    daily = {}
    for i in range(7):
        d = (datetime.date.today() - datetime.timedelta(days=6-i)).isoformat()
        daily[d] = bot.daily_roast_counts.get(d, 0)

    recent_roasts = [{"time":r[0],"member":r[1],"roast":r[2]} for r in bot.roast_log[-100:]]
    protected_list = []
    for guild in bot.guilds:
        for uid in bot.protected_users:
            m = guild.get_member(uid)
            if m:
                protected_list.append({"id":uid,"name":m.display_name,"avatar":str(m.display_avatar.url)})

    next_roast_in = 0
    if bot.roast_loop.is_running() and bot.roast_loop.next_iteration:
        diff = (bot.roast_loop.next_iteration - discord.utils.utcnow()).total_seconds()
        next_roast_in = max(0, int(diff / 60))

    data = {
        "bot_name": bot.user.name if bot.user else "مستر ذبات",
        "bot_avatar": str(bot.user.display_avatar.url) if bot.user else "",
        "roast_loop_running": bot.roast_loop.is_running(),
        "members_in_vc": members_in_vc,
        "all_members": all_members,
        "recent_roasts": recent_roasts,
        "guild": guild_info,
        "total_vc_minutes": total_vc_minutes,
        "total_roasts": sum(bot.roast_count_per_user.values()),
        "uptime_minutes": int((time.time() - bot._start_time) / 60),
        "shame_board": shame,
        "top_games": top_games,
        "daily_chart": daily,
        "hourly_activity": bot.hourly_vc_activity,
        "protected": protected_list,
        "last_roast_time": bot.last_roast_time,
        "next_roast_in": next_roast_in,
        "interval_min": bot.roast_interval_min,
        "interval_max": bot.roast_interval_max,
        "current_voice": getattr(bot, "current_voice", "Kore"),
        "current_persona": getattr(bot, "current_persona", "troll"),
        "voice_join_allowed": getattr(bot, "voice_join_allowed", True),
        "voice_proactive_audio": getattr(bot, "voice_proactive_audio", False),
        "voice_auto_leave_sec": getattr(bot, "voice_auto_leave_sec", 120),
        "voice_ai_mode": getattr(bot, "voice_ai_mode", "helper"),
        "voice_sessions_active": len(getattr(bot, "voice_sessions", {})),
        "voice_session_log": getattr(bot, "voice_session_log", [])[-20:],
        "voice_ignored": [{"id":uid,"name":str(uid)} for uid in getattr(bot, "voice_ignored_users", set())],
        "current_dialect": getattr(bot, "current_dialect", "default"),
        "dialects": [
            {
                "id": k,
                "name": v["name"],
                "region": v["region"],
                "icon": v["icon"],
                "badge": v["badge"],
                "catchphrase": v["catchphrases"][0]
            }
            for k, v in DIALECTS.items()
        ],
    }
    
    # تحذيرات الإدمن (AI Alerts)
    alerts = []
    for m in members_in_vc:
        if m["minutes"] > 60 and (m.get("deafened", False) or m.get("muted", False)):
            alerts.append(f"🎯 فرصة ذبة: {m['name']} مسوي دفن/ميوت من أكثر من ساعة!")
        if m.get("streaming", False) and len(members_in_vc) == 1:
            alerts.append(f"📺 فرصة ذبة: {m['name']} يبث لحاله بالروم!")
    data["alerts"] = alerts
    
    # تحسين الأسماء المتجاهلة
    for g in bot.guilds:
        for v in data["voice_ignored"]:
            m = g.get_member(v["id"])
            if m: v["name"] = m.display_name; v["avatar"] = str(m.display_avatar.url)
    return web.Response(text=json.dumps(data, ensure_ascii=False), content_type="application/json")


async def handle_force_roast(request):
    bot = request.app["bot"]
    asyncio.create_task(bot.force_random_roast())
    return web.Response(text='{"ok":true}', content_type="application/json")


async def handle_toggle(request):
    bot = request.app["bot"]
    running = await bot.toggle_roast_loop()
    return web.Response(text=json.dumps({"running":running}), content_type="application/json")


async def handle_custom_roast(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id",0)); txt = body.get("text","").strip()
        if not mid or not txt:
            return web.Response(text='{"ok":false,"error":"missing"}', content_type="application/json")
        ok = await bot.send_custom_roast(mid, txt)
        return web.Response(text=json.dumps({"ok":ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_free_message(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        txt = body.get("text","").strip()
        if not txt: return web.Response(text='{"ok":false}', content_type="application/json")
        ok = await bot.send_free_message(txt)
        return web.Response(text=json.dumps({"ok":ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_targeted_roast(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0))
        topic = body.get("topic", "").strip() or None
        intensity = int(body.get("intensity", 3))
        dialect = body.get("dialect", "").strip() or None
        play_audio = bool(body.get("play_audio", True))
        if not mid:
            return web.Response(text='{"ok":false,"error":"العضو غير محدد"}', content_type="application/json")
        ok = await bot.targeted_roast(
            mid,
            topic=topic,
            intensity=intensity,
            dialect=dialect,
            play_audio=play_audio
        )
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
        return web.Response(text=json.dumps({"ok": True, "dossier": bot.dossier_mgr.get_user_dossier(mid)}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok": False, "error": str(e)}), content_type="application/json")


async def handle_change_interval(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mn = int(body.get("min",120)); mx = int(body.get("max",240))
        mn, mx = bot.change_interval(mn, mx)
        return web.Response(text=json.dumps({"ok":True,"min":mn,"max":mx}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_protect(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id",0)); action = body.get("action","add")
        if action == "add":
            bot.protected_users.add(mid)
        else:
            bot.protected_users.discard(mid)
        return web.Response(text='{"ok":true}', content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_change_voice(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        voice = body.get("voice", "Kore")
        bot.current_voice = voice
        return web.Response(text=json.dumps({"ok":True,"voice":voice}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_change_persona(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        persona = body.get("persona", "troll")
        bot.current_persona = persona
        return web.Response(text=json.dumps({"ok":True,"persona":persona}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_voice_settings(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        if "join_allowed" in body:
            bot.voice_join_allowed = bool(body["join_allowed"])
        if "proactive_audio" in body:
            bot.voice_proactive_audio = bool(body["proactive_audio"])
        if "auto_leave_sec" in body:
            bot.voice_auto_leave_sec = max(30, min(int(body["auto_leave_sec"]), 600))
        if "ai_mode" in body:
            bot.voice_ai_mode = body["ai_mode"]
        return web.Response(text=json.dumps({"ok":True}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_voice_ignore(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        mid = int(body.get("member_id", 0)); action = body.get("action", "add")
        if action == "add":
            bot.voice_ignored_users.add(mid)
        else:
            bot.voice_ignored_users.discard(mid)
        return web.Response(text=json.dumps({"ok":True}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_voice_kick(request):
    bot = request.app["bot"]
    try:
        for gid, session in list(bot.voice_sessions.items()):
            await session.stop(reason="طرد من الداشبورد")
        return web.Response(text=json.dumps({"ok":True}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


async def handle_voice_debug(request):
    bot = request.app["bot"]
    sessions = getattr(bot, "voice_sessions", {})
    debug_data = {}
    for gid, session in sessions.items():
        if hasattr(session, "get_debug_info"):
            debug_data[str(gid)] = session.get_debug_info()
    if not debug_data:
        debug_data["status"] = "no_active_session"
    return web.Response(text=json.dumps(debug_data, ensure_ascii=False, default=str), content_type="application/json")


async def handle_ai_report(request):
    bot = request.app["bot"]
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        stats = f"Online users in VC: {sum(len(vc.members) for g in bot.guilds for vc in g.voice_channels)}\n"
        stats += f"Total roasts: {sum(bot.roast_count_per_user.values())}\n"
        shame = sorted(bot.roast_count_per_user.items(), key=lambda x:-x[1])[:3]
        stats += f"Shame board top 3 max roasts: {shame}\n"
        stats += f"Protected users: {len(bot.protected_users)}"
        
        prompt = (
            "أنت مستر ذبات. حلل إحصائيات الديسكورد التالية واكتب تقرير مسائي ساخر.\n"
            f"الإحصائيات: {stats}\n"
            "الناتج يجب أن يكون JSON فقط بالصيغة التالية بالضبط بدون أي نصوص أخرى:\n"
            "{\"title\": \"عنوان التقرير\", \"toxic_user\": \"أكثر عضو انجلد\", \"quiet_user\": \"أصنم عضو (اختر عشوائيا اذا لم يوجد)\", \"summary\": \"ملخص ساخر للوضع سطرين\", \"advice\": \"نصيحة للإدمن\"}"
        )
        response = await client.aio.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
        )
        text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(text)
        return web.Response(text=json.dumps({"ok":True, "report": data}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False, "error":str(e)}), content_type="application/json")


async def handle_build_persona(request):
    bot = request.app["bot"]
    try:
        reader = await request.multipart()
        field = await reader.next()
        if field and field.name == 'image':
            image_bytes = await field.read()
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            prompt = (
                "ابتكر شخصية مضحكة جداً أو قاسية لبوت ديسكورد بناءً على هذا الشكل/الصورة ليكون 'مستر ذبات' الجديد.\n"
                "أعطني JSON يحتوي على:\n"
                "1. name: اسم الشخصية القصير\n"
                "2. prompt: الـ System Prompt التفصيلي للشخصية وطريقة كلامها باللهجة السعودية (سطرين)\n"
                "3. voice: اختر الصوت الأنسب من (Kore, Aoede, Puck, Fenrir, Charon)\n"
                "الرد يجب أن يكون بصيغة JSON فقط بدون نصوص إضافية."
            )
            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=[prompt, part],
            )
            text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(text)
            
            bot.current_persona_custom = data.get("prompt", "شخصية جديدة")
            bot.current_voice = data.get("voice", "Kore")
            
            return web.Response(text=json.dumps({"ok":True, "persona": data}), content_type="application/json")
        return web.Response(text=json.dumps({"ok":False, "error":"No image"}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False, "error":str(e)}), content_type="application/json")


async def handle_start_minigame(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        game = body.get("type", "trivia")
        prompts = {
            "trivia": "اكتب سؤال تحدي معلومات صعب جدا عن الألعاب (Gaming) مع 4 خيارات، وخل كلامك بلهجة سعودية وتحدى الموجودين يجاوبون.",
            "roast_battle": "أعلن في الشات عن بدء 'حلبة الذبات'. اطلب من الموجودين يكتبون ذباتهم واللي ذبته أقوى بيفوز، واستفزهم بلهجة سعودية.",
            "math": "عطهم مسألة رياضيات معقدة شوي وقول أول واحد يحلها له جائزة، بلهجة سعودية مستفزة."
        }
        prompt = prompts.get(game, prompts["trivia"])
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = await client.aio.models.generate_content(
            model="gemini-flash-latest", contents=prompt
        )
        # Fetch MAIN_CHANNEL_ID
        ch = bot.get_channel(bot.get_channel(782986605148635166).guild.text_channels[0].id) # fallback
        for guild in bot.guilds:
            system = guild.system_channel or guild.text_channels[0]
            if system:
                ch = system
                break
        
        # Override if main channel is known
        import os
        mc_id = int(os.getenv("MAIN_CHANNEL_ID", 0))
        if mc_id: ch = bot.get_channel(mc_id)
        
        if ch:
            await ch.send(f"🎮 **لعبة جديدة** 🎮\n{response.text.strip()}")
            return web.Response(text='{"ok":true}', content_type="application/json")
        return web.Response(text='{"ok":false, "error":"No channel"}', content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False, "error":str(e)}), content_type="application/json")


async def handle_soundboard(request):
    bot = request.app["bot"]
    try:
        body = await request.json()
        effect = body.get("effect")
        prompts = {
            "laugh": "hahahaha HAHAHAHA! hahahaha!",
            "scream": "Aaaaaaaaaahhhhhh!",
            "bruh": "Bruh.",
            "sigh": "Ugh. Sigh."
        }
        text = prompts.get(effect, "Hello")
        
        target_member = None
        for g in bot.guilds:
            for vc in g.voice_channels:
                if len([m for m in vc.members if not m.bot]) > 0:
                    target_member = [m for m in vc.members if not m.bot][0]
                    break
            if target_member: break
            
        if target_member:
            import asyncio
            asyncio.create_task(bot.play_tts_in_voice(target_member, text))
            return web.Response(text='{"ok":true}', content_type="application/json")
        return web.Response(text='{"ok":false, "error":"لا يوجد أحد في الفويس"}', content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False, "error":str(e)}), content_type="application/json")

# ─── HTML ────────────────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مستر ذبات – لوحة التحكم</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0a0e14;--bg2:#111820;--card:#161d27;--card2:#1a2332;
  --border:#1e2a3a;--border-h:#2a3a4d;
  --accent:#f43f5e;--accent2:#fb7185;--accent-bg:rgba(244,63,94,.08);
  --green:#22c55e;--green-bg:rgba(34,197,94,.1);
  --yellow:#eab308;--yellow-bg:rgba(234,179,8,.1);
  --blue:#3b82f6;--blue-bg:rgba(59,130,246,.1);
  --purple:#a855f7;--purple-bg:rgba(168,85,247,.1);
  --cyan:#06b6d4;--cyan-bg:rgba(6,182,212,.1);
  --text:#e8edf4;--muted:#6b7a8d;--dim:#3d4f63;
}
.light{
  --bg:#f0f2f5;--bg2:#fff;--card:#fff;--card2:#f8f9fa;
  --border:#e0e4ea;--border-h:#c8d0dc;
  --text:#1a1a2e;--muted:#64748b;--dim:#94a3b8;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;transition:background .3s,color .3s}

/* Header */
.header{background:linear-gradient(135deg,rgba(244,63,94,.05),rgba(168,85,247,.05));
  border-bottom:1px solid var(--border);padding:1rem 2rem;
  display:flex;align-items:center;gap:1rem;position:sticky;top:0;z-index:50;
  backdrop-filter:blur(20px);transition:background .3s}
.header img{width:44px;height:44px;border-radius:50%;border:2px solid var(--accent);box-shadow:0 0 16px rgba(244,63,94,.25)}
.header .title{font-size:1.3rem;font-weight:900;background:linear-gradient(135deg,var(--accent),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .sub{color:var(--muted);font-size:.78rem}
.header-actions{margin-right:auto;display:flex;gap:.5rem;align-items:center}
.theme-btn{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.4rem .7rem;cursor:pointer;font-size:1rem;color:var(--text);transition:all .2s}
.theme-btn:hover{border-color:var(--accent)}

.container{max-width:1500px;margin:0 auto;padding:1.5rem}

/* Tabs */
.tabs{display:flex;gap:.5rem;margin-bottom:1.5rem;overflow-x:auto;padding-bottom:.5rem}
.tab{padding:.5rem 1.2rem;border-radius:10px;font-weight:700;font-size:.82rem;cursor:pointer;
  background:var(--card);border:1px solid var(--border);color:var(--muted);transition:all .2s;white-space:nowrap}
.tab:hover{border-color:var(--border-h);color:var(--text)}
.tab.active{background:var(--accent-bg);border-color:var(--accent);color:var(--accent)}

/* Page */
.page{display:none;animation:fadeIn .3s ease}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* Stats */
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:1.5rem}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:1rem;display:flex;align-items:center;gap:.8rem;transition:all .2s}
.stat-card:hover{border-color:var(--border-h);transform:translateY(-2px)}
.stat-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.3rem}
.stat-icon.red{background:var(--accent-bg)}.stat-icon.green{background:var(--green-bg)}
.stat-icon.blue{background:var(--blue-bg)}.stat-icon.purple{background:var(--purple-bg)}
.stat-icon.cyan{background:var(--cyan-bg)}.stat-icon.yellow{background:var(--yellow-bg)}
.stat-value{font-size:1.5rem;font-weight:900}
.stat-label{font-size:.72rem;color:var(--muted)}

/* Grid */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.5rem}
@media(max-width:1100px){.grid3{grid-template-columns:1fr 1fr}}
@media(max-width:800px){.grid,.grid3{grid-template-columns:1fr}}
.full{grid-column:1/-1}

/* Card */
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:all .2s}
.card:hover{border-color:var(--border-h)}
.card-head{padding:.9rem 1.1rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.card-head h2{font-size:.92rem;font-weight:700;color:var(--muted);display:flex;align-items:center;gap:.4rem}
.card-body{padding:1.1rem;max-height:420px;overflow-y:auto}
.card-body::-webkit-scrollbar{width:3px}
.card-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* Badge */
.badge{display:inline-flex;align-items:center;gap:.2rem;padding:.12rem .55rem;border-radius:20px;font-size:.7rem;font-weight:600}
.badge-green{background:var(--green-bg);color:var(--green)}
.badge-red{background:var(--accent-bg);color:var(--accent)}
.badge-yellow{background:var(--yellow-bg);color:var(--yellow)}
.badge-blue{background:var(--blue-bg);color:var(--blue)}
.badge-purple{background:var(--purple-bg);color:var(--purple)}
.badge-cyan{background:var(--cyan-bg);color:var(--cyan)}

/* Members */
.member{display:flex;align-items:center;gap:.7rem;padding:.7rem 0;border-bottom:1px solid var(--border);transition:background .2s}
.member:last-child{border-bottom:none}
.member:hover{background:rgba(255,255,255,.02)}
.member-avatar{position:relative}
.member-avatar img{width:38px;height:38px;border-radius:50%;border:2px solid var(--border)}
.status-dot{position:absolute;bottom:0;right:0;width:11px;height:11px;border-radius:50%;border:2px solid var(--card)}
.status-online{background:var(--green)}.status-idle{background:var(--yellow)}.status-dnd{background:var(--accent)}.status-offline{background:var(--dim)}
.member-info{flex:1;min-width:0}
.member-name{font-weight:700;font-size:.85rem;display:flex;align-items:center;gap:.3rem;flex-wrap:wrap}
.member-meta{color:var(--muted);font-size:.72rem;display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.1rem}

/* Shame board */
.shame-item{display:flex;align-items:center;gap:.7rem;padding:.6rem 0;border-bottom:1px solid var(--border)}
.shame-item:last-child{border-bottom:none}
.shame-rank{font-size:1.1rem;font-weight:900;width:28px;text-align:center}
.shame-rank.gold{color:#fbbf24}.shame-rank.silver{color:#94a3b8}.shame-rank.bronze{color:#d97706}
.shame-count{margin-right:auto;font-weight:900;color:var(--accent);font-size:.9rem}

/* Roasts */
.roast-item{padding:.65rem 0;border-bottom:1px solid var(--border)}
.roast-item:last-child{border-bottom:none}
.roast-head{display:flex;align-items:center;gap:.4rem}
.roast-name{color:var(--accent);font-weight:700;font-size:.8rem}
.roast-time{color:var(--dim);font-size:.7rem}
.roast-text{color:var(--text);font-size:.82rem;margin-top:.25rem;line-height:1.6;padding:.4rem .7rem;background:var(--card2);border-radius:8px;border-right:3px solid var(--accent)}

/* Buttons */
.btn{padding:.5rem 1.1rem;border:1px solid var(--border);border-radius:10px;font-family:'Cairo',sans-serif;font-weight:700;font-size:.82rem;cursor:pointer;transition:all .2s;display:inline-flex;align-items:center;gap:.3rem;background:var(--card2);color:var(--text)}
.btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.3)}
.btn-red{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-green{background:var(--green);border-color:var(--green);color:#fff}
.btn-yellow{border-color:var(--yellow);color:var(--yellow)}
.btn-blue{border-color:var(--blue);color:var(--blue)}
.btn-sm{padding:.35rem .8rem;font-size:.75rem}
.controls{display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:.8rem}

/* Forms */
.form-group{margin-bottom:.8rem}
.form-group label{font-size:.75rem;color:var(--muted);margin-bottom:.2rem;display:block}
select,textarea,input[type=text],input[type=number]{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:.6rem .9rem;color:var(--text);font-family:'Cairo',sans-serif;font-size:.82rem;outline:none;transition:border .2s;width:100%}
select:focus,textarea:focus,input:focus{border-color:var(--accent)}
textarea{resize:none;min-height:70px}
input[type=range]{width:100%;accent-color:var(--accent)}

/* Game bars */
.game-bar{display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem}
.game-bar .name{font-size:.8rem;min-width:100px;text-align:left}
.game-bar .bar{flex:1;height:22px;background:var(--bg2);border-radius:6px;overflow:hidden;position:relative}
.game-bar .fill{height:100%;border-radius:6px;transition:width .5s ease}
.game-bar .count{font-size:.72rem;color:var(--muted);min-width:30px;text-align:center}

/* Toast */
.toast-container{position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:.5rem}
.toast{background:var(--card);border:1px solid var(--accent);border-radius:12px;padding:.7rem 1.2rem;
  font-size:.82rem;box-shadow:0 8px 30px rgba(0,0,0,.4);animation:slideIn .3s ease,fadeOut .3s ease 3s forwards;
  display:flex;align-items:center;gap:.5rem}
@keyframes slideIn{from{opacity:0;transform:translateY(-20px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeOut{to{opacity:0;transform:translateY(-10px)}}

.empty{color:var(--dim);font-size:.82rem;text-align:center;padding:1.5rem}
.empty-icon{font-size:1.8rem;margin-bottom:.4rem}

/* Chart container */
.chart-box{position:relative;height:200px}

/* Hourly chart */
.hourly-bars{display:flex;align-items:flex-end;gap:3px;height:120px;padding:0 .2rem}
.hourly-bar{flex:1;border-radius:3px 3px 0 0;transition:height .5s;min-width:8px;position:relative}
.hourly-bar:hover{opacity:.8}
.hourly-label{font-size:.55rem;color:var(--dim);text-align:center;margin-top:2px}

@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.pulse{animation:pulse 2s ease-in-out infinite}

/* Dialects */
.dialect-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem;margin-top:.6rem}
.dialect-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem;cursor:pointer;transition:all .2s;position:relative}
.dialect-card:hover{border-color:var(--accent);transform:translateY(-2px)}
.dialect-card.active{border-color:var(--accent);background:linear-gradient(135deg,rgba(244,63,94,.12),rgba(168,85,247,.12));box-shadow:0 0 16px rgba(244,63,94,.25)}
.dialect-card-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:.4rem}
.dialect-name{font-weight:700;font-size:.9rem;display:flex;align-items:center;gap:.4rem}
.dialect-badge{font-size:.68rem;padding:.12rem .5rem;border-radius:12px;background:var(--card);border:1px solid var(--border);color:var(--muted)}
.dialect-desc{font-size:.74rem;color:var(--muted);line-height:1.4}
.dialect-quote{font-size:.72rem;color:var(--accent2);margin-top:.4rem;background:rgba(255,255,255,.03);padding:.25rem .5rem;border-radius:6px;border-right:2px solid var(--accent)}
.dialect-active-indicator{position:absolute;top:-8px;left:10px;background:var(--accent);color:#fff;font-size:.65rem;font-weight:700;padding:.1rem .5rem;border-radius:10px;display:none}
.dialect-card.active .dialect-active-indicator{display:block}

/* Dossier Modal */
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(5px);z-index:1000;display:none;align-items:center;justify-content:center;padding:1rem}
.modal-backdrop.open{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:16px;max-width:540px;width:100%;max-height:85vh;overflow-y:auto;box-shadow:0 20px 40px rgba(0,0,0,.5);animation:fadeIn .2s ease}
.modal-head{padding:1rem 1.3rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.modal-body{padding:1.3rem}
.dossier-tag{display:inline-block;padding:.2rem .6rem;background:var(--card2);border:1px solid var(--border);border-radius:8px;font-size:.75rem;margin:.2rem}
</style>
</head>
<body>

<div class="toast-container" id="toasts"></div>

<div class="header">
  <img id="bot-avatar" src="" alt="">
  <div>
    <div class="title" id="bot-name">مستر ذبات 🔥</div>
    <div class="sub" id="loop-status">جاري التحميل...</div>
  </div>
  <div class="header-actions">
    <span id="header-dialect" class="badge badge-purple" style="font-size:.76rem;padding:.35rem .7rem;cursor:pointer" onclick="showPage('control')" title="اضغط لتغيير اللهجة">🗣️ عامية</span>
    <button class="theme-btn" onclick="toggleTheme()" id="theme-btn">🌙</button>
  </div>
</div>

<div class="container">
  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="showPage('overview')">📊 نظرة عامة</div>
    <div class="tab" onclick="showPage('control')">🕹️ التحكم</div>
    <div class="tab" onclick="showPage('voice')">🎤 المحادثة الصوتية</div>
    <div class="tab" onclick="showPage('roasts')">🔥 الذبات</div>
    <div class="tab" onclick="showPage('analytics')">📈 التحليلات</div>
    <div class="tab" onclick="showPage('members')">👥 الأعضاء</div>
    <div class="tab" onclick="showPage('debug')">🔧 Debug</div>
  </div>

  <!-- ═══ PAGE: OVERVIEW ═══ -->
  <div class="page active" id="page-overview">
    <div class="stats-row">
      <div class="stat-card"><div class="stat-icon red">🎯</div><div><div class="stat-value" id="s-roasts">0</div><div class="stat-label">ذبة إجمالي</div></div></div>
      <div class="stat-card"><div class="stat-icon green">🎧</div><div><div class="stat-value" id="s-vc">0</div><div class="stat-label">بالفويس الحين</div></div></div>
      <div class="stat-card"><div class="stat-icon blue">⏱️</div><div><div class="stat-value" id="s-mins">0</div><div class="stat-label">دقيقة فويس</div></div></div>
      <div class="stat-card"><div class="stat-icon purple">👥</div><div><div class="stat-value" id="s-online">0</div><div class="stat-label">أونلاين</div></div></div>
      <div class="stat-card"><div class="stat-icon cyan">⏳</div><div><div class="stat-value" id="s-uptime">0</div><div class="stat-label">دقيقة شغّال</div></div></div>
      <div class="stat-card"><div class="stat-icon yellow">⏭️</div><div><div class="stat-value" id="s-next">—</div><div class="stat-label">الذبة الجاية</div></div></div>
    </div>

    <!-- Quick Dialect Bar in Overview -->
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:.8rem 1.2rem;margin-bottom:1.5rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.8rem">
      <div style="display:flex;align-items:center;gap:.6rem">
        <span style="font-size:1.3rem">🗣️</span>
        <div>
          <div style="font-weight:700;font-size:.88rem">اللهجة التلقائية الحالية: <span id="ov-dialect-name" style="color:var(--accent);font-weight:900">عامية</span></div>
          <div style="font-size:.72rem;color:var(--muted)">تحدد أسلوب ومفردات الذبات والمحادثات الصوتية فوراً</div>
        </div>
      </div>
      <div style="display:flex;gap:.4rem;flex-wrap:wrap" id="ov-dialect-btns">
        <button class="btn btn-sm" onclick="changeDialect('default')" id="btn-dial-default">⚡ عامية</button>
        <button class="btn btn-sm" onclick="changeDialect('riyadh')" id="btn-dial-riyadh">🇸🇦 الرياض</button>
        <button class="btn btn-sm" onclick="changeDialect('jeddah')" id="btn-dial-jeddah">🌴 جدة</button>
        <button class="btn btn-sm" onclick="changeDialect('qassim')" id="btn-dial-qassim">🌾 القصيم</button>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🎧 بالفويس الحين</h2><span class="badge badge-green" id="vc-count">0</span></div>
        <div class="card-body" id="members-list"><div class="empty"><div class="empty-icon">🔇</div>لا أحد</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>🏆 جدار العار والحقد</h2></div>
        <div class="card-body" id="shame-list"><div class="empty"><div class="empty-icon">😇</div>ما فيه ضحايا بعد</div></div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: CONTROL ═══ -->
  <div class="page" id="page-control">
    <!-- Dialect Selector Card -->
    <div class="card full" style="margin-bottom:1.5rem">
      <div class="card-head">
        <h2>🗣️ اختيار لهجة البوت التلقائية (Dialect Control)</h2>
        <span class="badge badge-purple" id="ctrl-dialect-badge">عامية</span>
      </div>
      <div class="card-body">
        <p style="font-size:.8rem;color:var(--muted);margin-bottom:.5rem">
          اختر اللهجة التي سيعتمدها البوت في الذبات التلقائية والردود الصوتية. اضغط على أي بطاقة لتفعيلها فوراً:
        </p>
        <div class="dialect-grid" id="dialect-grid"></div>
      </div>
    </div>

    <!-- Smart Roast Launcher -->
    <div class="card full" style="margin-bottom:1.5rem">
      <div class="card-head">
        <h2>🚀 منصة إطلاق الذبات الذكية (Smart Roast Launcher)</h2>
        <span class="badge badge-red">Gemini Thinking High 🔥</span>
      </div>
      <div class="card-body">
        <div class="grid" style="grid-template-columns:1fr 1fr;gap:1.2rem">
          <div>
            <div class="form-group">
              <label>🎯 الضحية المستهدفة</label>
              <select id="smart-roast-target"><option value="">اختر عضو...</option></select>
            </div>
            <div class="form-group">
              <label>🗣️ تخصيص اللهجة لهذه الذبة (اختياري)</label>
              <select id="smart-roast-dialect">
                <option value="">نفس لهجة البوت الحالية</option>
                <option value="default">⚡ عامية سعودية (Default)</option>
                <option value="riyadh">🇸🇦 لهجة الرياض / نجدية</option>
                <option value="jeddah">🌴 لهجة جدة / حجازية</option>
                <option value="qassim">🌾 لهجة القصيم</option>
              </select>
            </div>
            <div class="form-group">
              <label>🔥 مستوى القسوة: <span id="lbl-intensity" style="color:var(--accent);font-weight:900">3 - متوازنة 🎯</span></label>
              <input type="range" id="smart-roast-intensity" min="1" max="5" value="3" oninput="updateIntensityLabel(this.value)">
            </div>
            <div class="form-group" style="margin-top:.8rem">
              <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer;user-select:none;font-size:.82rem">
                <input type="checkbox" id="smart-roast-audio" checked style="width:auto;accent-color:var(--accent)">
                <span>تشغيل الذبة صوتياً بالفويس إذا كان متواجداً 🔊</span>
              </label>
            </div>
          </div>
          <div>
            <div class="form-group">
              <label>💡 موضوع الذبة وسياقها (اختياري)</label>
              <select id="smart-roast-preset" onchange="applyTopicPreset(this.value)" style="margin-bottom:.4rem">
                <option value="">-- أفكار جاهزة سريعة --</option>
                <option value="صنم بالفويس من زمان وما يتكلم">صنم بالفويس وما يتكلم</option>
                <option value="لعب نوب وخسر الرانك والكل يعاني منه">لعب نوب وتخريب الرانك</option>
                <option value="سهران ومسوي فيها مشغول وما ينام">سهران ومسوي فيها مشغول</option>
                <option value="دافن المايك وعايش في عالم موازي">مسوي دفن وسابح بعالمه</option>
                <option value="dossier">استخدم ملف الفضائح والسوابق حقه</option>
              </select>
              <textarea id="smart-roast-topic" placeholder="اكتب فكرة الذبة أو اتركه فارغاً والـ AI سيبحث في نشاطه وسوابقه ويجلده..."></textarea>
            </div>
            <button class="btn btn-red" style="width:100%;margin-top:.5rem;padding:.7rem;font-size:.88rem;justify-content:center" onclick="launchSmartRoast()" id="btn-smart-roast">🚀 أطلق الذبة الذكية</button>
            <p id="smart-roast-msg" style="font-size:.75rem;min-height:1rem;margin-top:.4rem"></p>
          </div>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🕹️ أوامر سريعة</h2></div>
        <div class="card-body">
          <div class="controls">
            <button class="btn btn-red" onclick="forceRoast()">⚡ ذب الحين (عشوائي)</button>
            <button class="btn btn-yellow" onclick="toggleLoop()" id="btn-toggle">⏯️ إيقاف/تشغيل</button>
            <button class="btn" onclick="loadData()">🔄 تحديث</button>
          </div>
          <div class="form-group" style="margin-top:1rem; border-top:1px solid var(--border); padding-top:1rem;">
            <label>🤖 شخصية البوت (يتغير أسلوب الذبة)</label>
            <div style="display:flex;gap:.5rem; margin-bottom: .8rem">
              <select id="persona-select" style="flex:1">
                <option value="troll">الطقطوقي المروق (العادي)</option>
                <option value="boomer">الشايب المعصّب (نصايح وتقريع)</option>
                <option value="tryhard">المحترف الأجنبي (متعالي واسبورتس)</option>
                <option value="psycho">المريض النفسي الغامض (مستفز وهادئ)</option>
              </select>
              <button class="btn btn-green btn-sm" onclick="changePersona()">🎭 تغيير</button>
            </div>
            
            <div style="margin-bottom:1rem; padding:1rem; background:var(--bg2); border-radius:10px; border:1px dashed var(--purple)">
              <label style="color:var(--purple);font-weight:bold;margin-bottom:.5rem;">🖼️ صانع الشخصيات الذكي (ارفع صورة)</label>
              <div style="display:flex;gap:.5rem; align-items:center">
                <input type="file" id="persona-image" accept="image/*" style="flex:1; font-size:.75rem">
                <button class="btn btn-purple btn-sm" onclick="buildPersona()" id="btn-build-persona" style="background:var(--purple);color:#fff;border-color:var(--purple)">✨ ابتكار شخصية</button>
              </div>
              <p id="persona-build-msg" style="font-size:.7rem; color:var(--muted); margin-top:.5rem"></p>
            </div>
            
            <label>🎙️ صوت البوت (يتغير بالروم)</label>
            <div style="display:flex;gap:.5rem">
              <select id="voice-select" style="flex:1">
                <option value="Kore">Kore - صوت البارزة الهادئة</option>
                <option value="Aoede">Aoede - صوت خفيف/طبيعي</option>
                <option value="Puck">Puck - الجان المشاغب (مناسب للذبات)</option>
                <option value="Fenrir">Fenrir - عميق وضخم</option>
                <option value="Charon">Charon - هادئ ورزين</option>
              </select>
              <button class="btn btn-purple btn-sm" onclick="changeVoice()" style="background:var(--purple);color:#fff;border-color:var(--purple)">🎙️ تغيير</button>
            </div>
            <p id="voice-msg" style="font-size:.75rem;color:var(--green);min-height:1rem;margin-top:.3rem"></p>
          </div>
          <!-- Minigames Section -->
          <div class="form-group" style="margin-top:1rem; border-top:1px dashed var(--border); padding-top:1rem;">
            <label>👾 توليد لعبة مصغرة في الشات (AI Minigames)</label>
            <div style="display:flex;gap:.5rem; align-items:center">
              <select id="minigame-type" style="flex:1">
                <option value="trivia">لعبة تحدي معلومات (Trivia)</option>
                <option value="roast_battle">تحدي الذبات (Roast Battle)</option>
                <option value="math">لعبة سرعة حساب (مسألة رياضية)</option>
              </select>
              <button class="btn btn-blue btn-sm" onclick="startMinigame()" id="btn-minigame">🚀 أطلق اللعبة</button>
            </div>
          </div>
          
          <p id="status-msg" style="font-size:.8rem;color:var(--muted);min-height:1rem"></p>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>⏱️ وقت الذبات التلقائية</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>أقل مدة: <strong id="lbl-min">120</strong> دقيقة</label>
            <input type="range" id="slider-min" min="30" max="600" value="120" oninput="document.getElementById('lbl-min').textContent=this.value">
          </div>
          <div class="form-group">
            <label>أقصى مدة: <strong id="lbl-max">240</strong> دقيقة</label>
            <input type="range" id="slider-max" min="30" max="720" value="240" oninput="document.getElementById('lbl-max').textContent=this.value">
          </div>
          <button class="btn btn-blue" onclick="changeInterval()">💾 حفظ</button>
          <p id="interval-msg" style="font-size:.8rem;color:var(--muted);min-height:1rem;margin-top:.5rem"></p>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>✍️ ذبة يدوية</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>اختر الضحية</label>
            <select id="roast-target"><option value="">— اختر —</option></select>
          </div>
          <div class="form-group">
            <label>اكتب الذبة</label>
            <textarea id="roast-text" placeholder="اكتب ذبتك هنا..."></textarea>
          </div>
          <button class="btn btn-red" onclick="sendCustom()">🚀 أرسل</button>
          <p id="custom-msg" style="font-size:.8rem;color:var(--muted);min-height:1rem;margin-top:.3rem"></p>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>📢 رسالة حرة</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>أرسل أي رسالة بالشات نيابة عن البوت</label>
            <textarea id="free-text" placeholder="اكتب رسالتك..."></textarea>
          </div>
          <button class="btn btn-green" onclick="sendFree()">📨 أرسل</button>
          <p id="free-msg" style="font-size:.8rem;color:var(--muted);min-height:1rem;margin-top:.3rem"></p>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: ROASTS ═══ -->
  <div class="page" id="page-roasts">
    <div class="card">
      <div class="card-head">
        <h2>🔥 سجل الذبات</h2>
        <div style="display:flex;gap:.5rem;align-items:center">
          <input type="text" id="roast-filter" placeholder="ابحث..." style="width:160px;padding:.35rem .6rem;font-size:.78rem" oninput="filterRoasts()">
          <span class="badge badge-red" id="roast-total">0</span>
        </div>
      </div>
      <div class="card-body" id="roasts-list" style="max-height:600px">
        <div class="empty"><div class="empty-icon">💤</div>لا توجد ذبات</div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: ANALYTICS ═══ -->
  <div class="page" id="page-analytics">
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>📈 الذبات آخر 7 أيام</h2></div>
        <div class="card-body"><div class="chart-box"><canvas id="dailyChart"></canvas></div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>⏰ أوقات الذروة (بتوقيت السعودية)</h2></div>
        <div class="card-body">
          <div class="hourly-bars" id="hourly-bars"></div>
          <div style="display:flex;justify-content:space-between;margin-top:4px">
            <span style="font-size:.6rem;color:var(--dim)">12ص</span>
            <span style="font-size:.6rem;color:var(--dim)">6ص</span>
            <span style="font-size:.6rem;color:var(--dim)">12م</span>
            <span style="font-size:.6rem;color:var(--dim)">6م</span>
            <span style="font-size:.6rem;color:var(--dim)">12ص</span>
          </div>
        </div>
      </div>
      <div class="card full">
        <div class="card-head"><h2>🎮 أكثر الألعاب شعبية</h2></div>
        <div class="card-body" id="games-list"><div class="empty">لا توجد بيانات</div></div>
      </div>
      
      <div class="card full">
        <div class="card-head"><h2>🧠 تقرير السيرفر الذكي (AI Report)</h2></div>
        <div class="card-body">
          <button class="btn btn-purple" onclick="generateAIReport()" id="btn-ai-report" style="background:var(--purple);color:#fff;border-color:var(--purple)">✨ توليد تقرير ذكي عن حالة السيرفر</button>
          <div id="ai-report-output" style="margin-top:1rem; display:none; background:var(--bg2); padding:1rem; border-radius:10px; border-right:3px solid var(--purple)">
            <h3 id="ai-title" style="color:var(--purple); margin-bottom:.5rem; font-size:1.1rem">عنوان</h3>
            <p style="font-size:.85rem; margin-bottom:.3rem"><strong>أكثر عضو انجلد:</strong> <span id="ai-toxic"></span></p>
            <p style="font-size:.85rem; margin-bottom:.3rem"><strong>أصنم عضو:</strong> <span id="ai-quiet"></span></p>
            <p style="margin-top:.6rem; font-size:.85rem"><strong>الملخص:</strong> <span id="ai-summary"></span></p>
            <p style="margin-top:.6rem; color:var(--yellow); font-size:.85rem"><strong>نصيحة الإدمن:</strong> <span id="ai-advice"></span></p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: MEMBERS ═══ -->
  <div class="page" id="page-members">
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🛡️ قائمة الحماية</h2><span class="badge badge-blue" id="prot-count">0</span></div>
        <div class="card-body">
          <div class="form-group">
            <label>أضف عضو للحماية (ما ينذب)</label>
            <div style="display:flex;gap:.5rem">
              <select id="prot-select" style="flex:1"><option value="">اختر</option></select>
              <button class="btn btn-blue btn-sm" onclick="addProtect()">🛡️ حمِ</button>
            </div>
          </div>
          <div id="protected-list" style="margin-top:.8rem"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>👥 كل الأعضاء</h2><span class="badge badge-purple" id="total-members">0</span></div>
        <div class="card-body" id="all-members-list"><div class="empty">جاري التحميل...</div></div>
      </div>
      <div class="card full" style="margin-top:1.5rem">
        <div class="card-head">
          <h2>📂 ملفات السوابق والفضائح (Criminal Dossiers)</h2>
          <span class="badge badge-purple">ذاكرة البوت الشخصية</span>
        </div>
        <div class="card-body">
          <p style="font-size:.78rem;color:var(--muted);margin-bottom:.8rem">
            اختر أي عضو للاطلاع على سجل سوابقه وأعذاره وتصريفاته المسجلة لدى البوت، أو إضافة مواقف محرجة وألقاب جديدة له:
          </p>
          <div style="display:flex;gap:.5rem;max-width:420px">
            <select id="dossier-member-select"><option value="">اختر عضواً لعرض ملفه...</option></select>
            <button class="btn btn-purple btn-sm" onclick="openSelectedDossier()">📂 فتح الملف</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: VOICE CHAT ═══ -->
  <div class="page" id="page-voice">
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🎤 إعدادات المحادثة الصوتية</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>🔒 السماح للبوت بدخول الفويس</label>
            <div style="display:flex;gap:.5rem;align-items:center">
              <button class="btn btn-sm" id="voice-toggle-btn" onclick="toggleVoiceJoin()">🔓 مسموح</button>
              <button class="btn btn-red btn-sm" onclick="kickVoice()">🚪 أطلع البوت الحين</button>
            </div>
          </div>
          <div class="form-group" style="margin-top:1rem">
            <label>🥷 الدخول الصوتي الاستباقي (Sneak In)</label>
            <div style="display:flex;gap:.5rem;align-items:center">
              <button class="btn btn-sm" id="proactive-toggle-btn" onclick="toggleProactiveAudio()">شغال</button>
              <span style="font-size: .7rem; color: var(--muted)">يدخل فجأة يسمع السوالف ويذب ثم يطلع</span>
            </div>
          </div>
          <div class="form-group" style="margin-top:1rem">
            <label>⏱️ الخروج التلقائي بعد سكوت: <strong id="lbl-leave">120</strong> ثانية</label>
            <input type="range" id="slider-leave" min="30" max="600" value="120" oninput="document.getElementById('lbl-leave').textContent=this.value">
          </div>
          <div class="form-group">
            <label>🎛️ وضع الـ AI بالمحادثة الصوتية</label>
            <select id="voice-mode-select">
              <option value="helper">🤖 مساعد ذكي ودود</option>
              <option value="roaster">🔥 مستر ذبات (يذب بشخصيته الحالية)</option>
              <option value="dj">🎵 DJ – يغني ويقول شعر</option>
            </select>
          </div>
          <button class="btn btn-blue" onclick="saveVoiceSettings()">💾 حفظ الإعدادات</button>
          <p id="voice-settings-msg" style="font-size:.8rem;color:var(--green);min-height:1rem;margin-top:.3rem"></p>
          <div style="margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border)">
            <p style="font-size:.8rem;color:var(--muted)">💡 الأعضاء يكتبون <strong>بوت تعال</strong> بالشات عشان البوت يدخل الروم ويتكلم معاهم، و <strong>بوت روح</strong> عشان يطلع.</p>
          </div>
          
          <div style="margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border)">
            <h3 style="font-size:.9rem; color:var(--purple); margin-bottom:.5rem">🎹 الساوند-بورد الذكي (AI Soundboard)</h3>
            <p style="font-size:.7rem; color:var(--muted); margin-bottom:.8rem">شغّل أصوات ذكية داخل الفويس الحالي بضغطة زر:</p>
            <div style="display:flex;gap:.5rem; flex-wrap:wrap">
              <button class="btn btn-purple btn-sm" onclick="playEffect('laugh')">😈 ضحكة شريرة</button>
              <button class="btn btn-purple btn-sm" onclick="playEffect('scream')">😱 صرخة</button>
              <button class="btn btn-purple btn-sm" onclick="playEffect('sigh')">😮‍💨 تنهيدة</button>
              <button class="btn btn-purple btn-sm" onclick="playEffect('bruh')">😑 Bruh</button>
            </div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>🔇 تجاهل أعضاء (ما يرد عليهم بالصوت)</h2></div>
        <div class="card-body">
          <div class="form-group">
            <div style="display:flex;gap:.5rem">
              <select id="voice-ignore-select" style="flex:1"><option value="">اختر</option></select>
              <button class="btn btn-red btn-sm" onclick="addVoiceIgnore()">🔇 تجاهل</button>
            </div>
          </div>
          <div id="voice-ignored-list"></div>
        </div>
      </div>
      <div class="card full">
        <div class="card-head"><h2>📊 سجل المحادثات الصوتية</h2><span class="badge badge-purple" id="voice-log-count">0</span></div>
        <div class="card-body" id="voice-log-list" style="max-height:350px"><div class="empty">لا توجد محادثات بعد</div></div>
      </div>
  </div>

  <!-- ═══ PAGE: DEBUG ═══ -->
  <div class="page" id="page-debug">
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🔧 Voice Debug – حالة الجلسة</h2><button class="btn btn-sm btn-blue" onclick="loadDebug()">🔄 تحديث</button></div>
        <div class="card-body">
          <div class="grid3" style="gap:.8rem">
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">الحالة</div>
              <div id="dbg-status" style="font-size:1.1rem;font-weight:bold">—</div>
            </div>
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">المتحدث النشط</div>
              <div id="dbg-speaker" style="font-size:1.1rem;font-weight:bold">—</div>
            </div>
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">البوت يتكلم؟</div>
              <div id="dbg-playing" style="font-size:1.1rem;font-weight:bold">—</div>
            </div>
          </div>
          <div class="grid3" style="gap:.8rem;margin-top:.8rem">
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">📥 Audio Received</div>
              <div id="dbg-recv" style="font-size:1.3rem;font-weight:bold;color:#22c55e">0</div>
            </div>
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">📤 Sent to Gemini</div>
              <div id="dbg-sent" style="font-size:1.3rem;font-weight:bold;color:#3b82f6">0</div>
            </div>
            <div style="text-align:center;padding:.5rem;background:var(--bg2);border-radius:8px">
              <div style="font-size:.7rem;color:var(--muted)">🤖 Gemini Responses</div>
              <div id="dbg-gemini" style="font-size:1.3rem;font-weight:bold;color:#a855f7">0</div>
            </div>
          </div>
          <div class="grid" style="grid-template-columns:1fr 1fr;gap:.8rem;margin-top:.8rem">
            <div style="padding:.5rem;background:var(--bg2);border-radius:8px">
              <span style="font-size:.7rem;color:var(--muted)">Input Buffer:</span>
              <strong id="dbg-buffer">0 bytes</strong>
            </div>
            <div style="padding:.5rem;background:var(--bg2);border-radius:8px">
              <span style="font-size:.7rem;color:var(--muted)">آخر نشاط قبل:</span>
              <strong id="dbg-lastact">—</strong>
            </div>
          </div>
          <div style="margin-top:.8rem;padding:.5rem;background:var(--bg2);border-radius:8px">
            <span style="font-size:.7rem;color:var(--muted)">المشاركين:</span>
            <span id="dbg-participants">—</span>
          </div>
        </div>
      </div>
      <div class="card full">
        <div class="card-head"><h2>📋 Event Log</h2><span class="badge badge-purple" id="dbg-log-count">0</span></div>
        <div class="card-body" id="dbg-log" style="max-height:500px;overflow-y:auto;font-family:monospace;font-size:.75rem;direction:ltr;text-align:left">
          <div class="empty">لا توجد جلسة أو أحداث بعد</div>
        </div>
      </div>
    </div>
  </div>

</div>

<!-- Dossier Modal -->
<div class="modal-backdrop" id="dossier-modal" onclick="if(event.target===this)closeDossierModal()">
  <div class="modal">
    <div class="modal-head">
      <div style="display:flex;align-items:center;gap:.6rem">
        <img id="dm-avatar" src="" style="width:36px;height:36px;border-radius:50%;border:2px solid var(--accent)">
        <div>
          <h3 id="dm-name" style="font-size:.95rem;font-weight:700">ملف العضو</h3>
          <span style="font-size:.7rem;color:var(--muted)" id="dm-id">ID</span>
        </div>
      </div>
      <button class="btn btn-sm" onclick="closeDossierModal()" style="border:none;background:transparent;font-size:1.1rem;cursor:pointer">✖</button>
    </div>
    <div class="modal-body">
      <div style="margin-bottom:1.2rem">
        <h4 style="font-size:.82rem;color:var(--yellow);margin-bottom:.4rem">👑 الألقاب الساخرة المعروفة</h4>
        <div id="dm-titles" style="display:flex;gap:.4rem;flex-wrap:wrap"><span class="badge">لا يوجد</span></div>
      </div>
      <div style="margin-bottom:1.2rem">
        <h4 style="font-size:.82rem;color:var(--blue);margin-bottom:.4rem">🤥 أشهر الأعذار والتصريفات</h4>
        <div id="dm-excuses" style="display:flex;flex-direction:column;gap:.3rem"><span style="font-size:.75rem;color:var(--muted)">لا يوجد</span></div>
      </div>
      <div style="margin-bottom:1.2rem">
        <h4 style="font-size:.82rem;color:var(--accent);margin-bottom:.4rem">🙈 مواقف محرجة وفضائح مسجلة</h4>
        <div id="dm-moments" style="display:flex;flex-direction:column;gap:.3rem"><span style="font-size:.75rem;color:var(--muted)">لا يوجد</span></div>
      </div>
      <hr style="border:none;border-top:1px solid var(--border);margin:1rem 0">
      <h4 style="font-size:.82rem;color:var(--green);margin-bottom:.5rem">➕ إضافة معلومة جديدة لملف العار</h4>
      <div class="form-group">
        <select id="dm-add-type" style="margin-bottom:.4rem">
          <option value="excuse">🤥 تصريفة / عذر مشهور</option>
          <option value="moment">🙈 موقف محرج / فضيحة</option>
          <option value="title">👑 لقب ساخر جديد</option>
        </select>
        <input type="text" id="dm-add-text" placeholder="اكتب المعلومة هنا ليستخدمها البوت في الذب...">
      </div>
      <button class="btn btn-green btn-sm" style="width:100%;justify-content:center" onclick="addDossierItem()">💾 حفظ في الملف</button>
    </div>
  </div>
</div>

<script>
let D={}, dailyChartInstance=null, allRoasts=[];

function showPage(id){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  event.target.classList.add('active');
  if(id==='analytics') renderCharts();
  if(id==='debug'){loadDebug();debugInterval=setInterval(loadDebug,3000)}
  else{if(debugInterval){clearInterval(debugInterval);debugInterval=null}}
}

function toggleTheme(){
  document.body.classList.toggle('light');
  document.getElementById('theme-btn').textContent=document.body.classList.contains('light')?'🌙':'☀️';
}

function toast(msg,type='info'){
  const c=document.getElementById('toasts');
  const t=document.createElement('div');
  t.className='toast';
  t.innerHTML=(type==='ok'?'✅':'🔔')+' '+msg;
  c.appendChild(t);
  setTimeout(()=>t.remove(),3500);
}

function fmtDur(m){
  if(m>=60){const h=Math.floor(m/60),mn=m%60;const hl=h===1?'ساعة':h===2?'ساعتين':h+' ساعات';return mn?hl+' و '+mn+' د':hl}
  return m+' دقيقة';
}

async function loadData(){
  try{
    const r=await fetch('/api/stats');D=await r.json();
    document.getElementById('bot-name').textContent=D.bot_name+' 🔥';
    document.getElementById('bot-avatar').src=D.bot_avatar;
    const ls=document.getElementById('loop-status');
    ls.innerHTML=D.roast_loop_running?'<span class="badge badge-green pulse">● شغّال</span> <span style="color:var(--muted);font-size:.72rem">الذبة الجاية بعد '+D.next_roast_in+' د</span>':'<span class="badge badge-red">● متوقف</span>';

    document.getElementById('s-roasts').textContent=D.total_roasts;
    document.getElementById('s-vc').textContent=D.members_in_vc.length;
    document.getElementById('s-mins').textContent=D.total_vc_minutes;
    document.getElementById('s-online').textContent=D.guild?.online||'—';
    document.getElementById('s-uptime').textContent=D.uptime_minutes;
    document.getElementById('s-next').textContent=D.roast_loop_running?D.next_roast_in+' د':'—';
    document.getElementById('vc-count').textContent=D.members_in_vc.length;
    document.getElementById('roast-total').textContent=D.recent_roasts.length;

    // AI Alerts
    const alertsBox = document.getElementById('ai-alerts-box');
    if(alertsBox) {
      if(D.alerts && D.alerts.length > 0) {
        alertsBox.innerHTML = D.alerts.map(a => `<div style="padding:.5rem; background:rgba(244,63,94,.1); border-left:3px solid var(--accent); margin-bottom:.5rem; font-size:.8rem; border-radius:4px">${a}</div>`).join('');
      } else {
        alertsBox.innerHTML = '<div class="empty" style="padding:.5rem; font-size:.75rem">لا توجد تنبيهات حالياً</div>';
      }
    }

    // Interval sliders
    document.getElementById('slider-min').value=D.interval_min;document.getElementById('lbl-min').textContent=D.interval_min;
    document.getElementById('slider-max').value=D.interval_max;document.getElementById('lbl-max').textContent=D.interval_max;
    // Settings
    if(D.current_voice) document.getElementById('voice-select').value = D.current_voice;
    if(D.current_persona) document.getElementById('persona-select').value = D.current_persona;

    // Voice chat settings
    if(D.voice_join_allowed !== undefined){
      document.getElementById('voice-toggle-btn').innerHTML = D.voice_join_allowed ? '🔓 مسموح' : '🔒 ممنوع';
      document.getElementById('voice-toggle-btn').className = D.voice_join_allowed ? 'btn btn-green btn-sm' : 'btn btn-red btn-sm';
    }
    if(D.voice_proactive_audio !== undefined){
      document.getElementById('proactive-toggle-btn').innerHTML = D.voice_proactive_audio ? '🥷 شغال (مفعل)' : '🛑 معطل';
      document.getElementById('proactive-toggle-btn').className = D.voice_proactive_audio ? 'btn btn-green btn-sm' : 'btn btn-red btn-sm';
    }
    if(D.voice_auto_leave_sec) { document.getElementById('slider-leave').value = D.voice_auto_leave_sec; document.getElementById('lbl-leave').textContent = D.voice_auto_leave_sec; }
    if(D.voice_ai_mode) document.getElementById('voice-mode-select').value = D.voice_ai_mode;

    // Voice ignore dropdown
    const viOpts='<option value="">اختر</option>'+D.all_members.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
    document.getElementById('voice-ignore-select').innerHTML = viOpts;

    // Voice ignored list
    const vil = document.getElementById('voice-ignored-list');
    if(!D.voice_ignored?.length){vil.innerHTML='<div class="empty" style="padding:.5rem">لا أحد متجاهل</div>'}
    else{vil.innerHTML=D.voice_ignored.map(p=>`<div style="display:flex;align-items:center;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--border)"><span style="flex:1;font-size:.82rem;font-weight:700">${p.name}</span><button class="btn btn-sm" onclick="removeVoiceIgnore(${p.id})" style="color:var(--accent)">❌</button></div>`).join('')}

    // Voice session log
    document.getElementById('voice-log-count').textContent = D.voice_session_log?.length || 0;
    const vll = document.getElementById('voice-log-list');
    if(!D.voice_session_log?.length){vll.innerHTML='<div class="empty">لا توجد محادثات بعد</div>'}
    else{vll.innerHTML=[...D.voice_session_log].reverse().map(s=>{
      const st = new Date(s.start*1000).toLocaleTimeString('ar-SA',{hour:'2-digit',minute:'2-digit'});
      const dur = s.end ? Math.round((s.end-s.start)/60) : '...';
      const badge = s.status==='active'?'<span class="badge badge-green pulse">● نشط</span>':'<span class="badge badge-red">● منتهي</span>';
      return `<div style="padding:.5rem 0;border-bottom:1px solid var(--border)"><div style="display:flex;align-items:center;gap:.5rem">${badge}<strong style="font-size:.82rem">${s.requester}</strong><span style="color:var(--muted);font-size:.72rem">${st} | ${s.channel} | ${dur} د | ${s.messages||0} رد</span></div>${s.reason?`<span style="font-size:.7rem;color:var(--dim)">📌 ${s.reason}</span>`:''}</div>`;
    }).join('')}

    // Members in VC
    const ml=document.getElementById('members-list');
    if(!D.members_in_vc.length){ml.innerHTML='<div class="empty"><div class="empty-icon">🔇</div>لا أحد بالفويس</div>'}
    else{ml.innerHTML=D.members_in_vc.map(m=>{
      const tags=[];
      if(m.deafened)tags.push('<span class="badge badge-red">🔇 دفن</span>');
      else if(m.muted)tags.push('<span class="badge badge-yellow">🔕 ميوت</span>');
      if(m.streaming)tags.push('<span class="badge badge-purple">📺 بث</span>');
      if(m.games?.length)tags.push('<span class="badge badge-blue">🎮 '+m.games[m.games.length-1]+'</span>');
      if(m.custom_status)tags.push('<span class="badge badge-cyan">💬 '+m.custom_status+'</span>');
      if(m.protected)tags.push('<span class="badge badge-green">🛡️</span>');
      
      let spkTag = '';
      if(m.speak_ratio > 70) spkTag = `<span title="مزعج الروم" style="font-size:.7rem; color:var(--accent);">🔊 يسولف واجد (${m.speak_ratio}%)</span>`;
      else if(m.speak_ratio < 10 && m.minutes > 5 && !m.muted && !m.deafened) spkTag = `<span title="صنم" style="font-size:.7rem; color:var(--muted);">💤 صامت (${m.speak_ratio}%)</span>`;

      return `<div class="member"><div class="member-avatar"><img src="${m.avatar}"><div class="status-dot status-${m.status||'offline'}"></div></div><div class="member-info"><div class="member-name">${m.name} ${tags.join(' ')}</div><div class="member-meta"><span>📍 ${m.channel}</span><span>⏱️ ${fmtDur(m.minutes)}</span> ${spkTag}</div></div><div style="display:flex;gap:.3rem;align-items:center;margin-right:auto"><button class="btn btn-sm" onclick="quickSmartRoast('${m.id}')" title="ذب عليه الآن" style="padding:.25rem .55rem;font-size:.72rem">🎯 ذب</button><button class="btn btn-sm" onclick="openDossierModal('${m.id}', '${m.name.replace(/'/g, "\\'")}', '${m.avatar}')" title="فتح ملف السوابق" style="padding:.25rem .55rem;font-size:.72rem">📂 ملفه</button></div></div>`;
    }).join('')}

    // Shame board
    const sl=document.getElementById('shame-list');
    if(!D.shame_board?.length){sl.innerHTML='<div class="empty"><div class="empty-icon">😇</div>ما فيه ضحايا</div>'}
    else{sl.innerHTML=D.shame_board.map((s,i)=>{
      const rc=i===0?'gold':i===1?'silver':i===2?'bronze':'';
      const medal=i===0?'🥇':i===1?'🥈':i===2?'🥉':(i+1);
      const grad = s.grudge > 40 ? '🔥 حقد شديد' : s.grudge > 10 ? '😡 عداوة' : '';
      return `<div class="shame-item">
        <div class="shame-rank ${rc}">${medal}</div>
        <img src="${s.avatar}" style="width:32px;height:32px;border-radius:50%">
        <div style="display:flex;flex-direction:column;">
          <span style="font-weight:700;font-size:.85rem">${s.name}</span>
          <span style="font-size:.65rem;color:var(--accent)">${grad ? grad + ' ('+s.grudge+')' : 'مستوى الحقد: '+s.grudge}</span>
        </div>
        <div style="display:flex;align-items:center;gap:.4rem;margin-right:auto">
          <button class="btn btn-sm" onclick="openDossierModal('${s.id}', '${s.name.replace(/'/g, "\\'")}', '${s.avatar}')" title="ملف السوابق" style="padding:.2rem .45rem;font-size:.7rem">📂</button>
          <span class="shame-count">${s.count} ذبة</span>
        </div>
      </div>`;
    }).join('')}

    // Roasts
    allRoasts=D.recent_roasts;filterRoasts();

    // Dropdowns
    const opts='<option value="">— اختر —</option>'+D.all_members.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
    ['roast-target','target-member','smart-roast-target','prot-select','dossier-member-select'].forEach(id=>{
      const el=document.getElementById(id);
      if(el) el.innerHTML=opts;
    });

    // Dialects
    if(D.current_dialect && D.dialects){
      renderDialects(D.current_dialect, D.dialects);
    }

    // Games
    const gl=document.getElementById('games-list');
    if(!D.top_games?.length){gl.innerHTML='<div class="empty">لا توجد بيانات</div>'}
    else{const mx=D.top_games[0].count;
      const colors=['var(--accent)','var(--purple)','var(--blue)','var(--green)','var(--yellow)','var(--cyan)','var(--accent2)','#f472b6','#34d399','#60a5fa'];
      gl.innerHTML=D.top_games.map((g,i)=>`<div class="game-bar"><span class="name">${g.name}</span><div class="bar"><div class="fill" style="width:${(g.count/mx*100)}%;background:${colors[i%colors.length]}"></div></div><span class="count">${g.count}</span></div>`).join('')}

    // Hourly
    const hb=document.getElementById('hourly-bars');
    if(D.hourly_activity){const mx=Math.max(...D.hourly_activity,1);
      const colors=D.hourly_activity.map((_,i)=>i>=22||i<6?'var(--purple)':i<12?'var(--blue)':'var(--green)');
      hb.innerHTML=D.hourly_activity.map((v,i)=>`<div><div class="hourly-bar" style="height:${Math.max(v/mx*110,4)}px;background:${colors[i]}" title="${i}:00 = ${v} دخلة"></div><div class="hourly-label">${i}</div></div>`).join('')}

    // Protected
    const pl=document.getElementById('protected-list');
    document.getElementById('prot-count').textContent=D.protected?.length||0;
    if(!D.protected?.length){pl.innerHTML='<div class="empty" style="padding:.5rem">لا أحد محمي</div>'}
    else{pl.innerHTML=D.protected.map(p=>`<div style="display:flex;align-items:center;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--border)"><img src="${p.avatar}" style="width:28px;height:28px;border-radius:50%"><span style="flex:1;font-size:.82rem;font-weight:700">${p.name}</span><button class="btn btn-sm" onclick="removeProtect(${p.id})" style="color:var(--accent)">❌</button></div>`).join('')}

    // Total members
    document.getElementById('total-members').textContent=D.all_members?.length||0;
    const aml=document.getElementById('all-members-list');
    aml.innerHTML=(D.all_members||[]).map(m=>`<div style="display:flex;align-items:center;gap:.5rem;padding:.35rem 0;border-bottom:1px solid var(--border)"><img src="${m.avatar}" style="width:26px;height:26px;border-radius:50%"><span style="font-size:.8rem">${m.name}</span></div>`).join('');

  }catch(e){console.error(e)}
}

function filterRoasts(){
  const q=(document.getElementById('roast-filter')?.value||'').toLowerCase();
  const list=q?allRoasts.filter(r=>r.member.toLowerCase().includes(q)||r.roast.toLowerCase().includes(q)):allRoasts;
  const rl=document.getElementById('roasts-list');
  if(!list.length){rl.innerHTML='<div class="empty"><div class="empty-icon">💤</div>لا توجد نتائج</div>';return}
  rl.innerHTML=[...list].reverse().map(r=>{
    const d=new Date(r.time*1000);const t=d.toLocaleTimeString('ar-SA',{hour:'2-digit',minute:'2-digit'});
    const day=d.toLocaleDateString('ar-SA',{month:'short',day:'numeric'});
    return `<div class="roast-item"><div class="roast-head"><span class="roast-name">@${r.member}</span><span class="roast-time">${day} ${t}</span></div><div class="roast-text">${r.roast}</div></div>`;
  }).join('');
}

function renderCharts(){
  if(!D.daily_chart)return;
  const ctx=document.getElementById('dailyChart');
  if(dailyChartInstance)dailyChartInstance.destroy();
  const labels=Object.keys(D.daily_chart).map(d=>{const p=d.split('-');return p[2]+'/'+p[1]});
  const values=Object.values(D.daily_chart);
  dailyChartInstance=new Chart(ctx,{type:'bar',data:{labels,datasets:[{label:'ذبات',data:values,backgroundColor:'rgba(244,63,94,.6)',borderRadius:6,borderSkipped:false}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{color:'#6b7a8d'}},x:{ticks:{color:'#6b7a8d'}}}}});
}

async function forceRoast(){await fetch('/api/force_roast',{method:'POST'});toast('أمر الذبة انطلق!','ok');setTimeout(loadData,3000)}
async function toggleLoop(){const r=await fetch('/api/toggle',{method:'POST'});const d=await r.json();toast(d.running?'الذبات شغّالة ▶️':'الذبات متوقفة ⏸️','ok');setTimeout(loadData,1000)}

async function generateAIReport(){
  const btn = document.getElementById('btn-ai-report');
  btn.textContent = '⏳ جاري التحليل...'; btn.disabled = true;
  try {
    const r = await fetch('/api/ai_report', {method:'POST'});
    const d = await r.json();
    if(d.ok && d.report){
      document.getElementById('ai-report-output').style.display='block';
      document.getElementById('ai-title').textContent=d.report.title;
      document.getElementById('ai-toxic').textContent=d.report.toxic_user;
      document.getElementById('ai-quiet').textContent=d.report.quiet_user;
      document.getElementById('ai-summary').textContent=d.report.summary;
      document.getElementById('ai-advice').textContent=d.report.advice;
      toast('تم استخراج التقرير الذكي ✨','ok');
    } else {
      toast('فشل التقرير، تأكد من البيانات','error');
    }
  }catch(e){toast('خطأ!','error');}
  if(btn){ btn.textContent = '✨ توليد تقرير ذكي عن حالة السيرفر'; btn.disabled = false; }
}

async function buildPersona(){
  const fileInput = document.getElementById('persona-image');
  if(!fileInput || !fileInput.files[0]){ toast('اختر صورة أولاً','error'); return; }
  const btn = document.getElementById('btn-build-persona');
  btn.textContent = '⏳ جاري الابتكار...'; btn.disabled = true;
  const formData = new FormData();
  formData.append('image', fileInput.files[0]);
  try {
    const r = await fetch('/api/build_persona', {method:'POST', body:formData});
    const d = await r.json();
    if(d.ok){
      document.getElementById('persona-build-msg').innerHTML = `<span style="color:var(--green)">تم تحويل البوت إلى: <strong>${d.persona.name||'شخصية مجهولة'}</strong> بصوت ${d.persona.voice||'Kore'}</span>`;
      toast('تم ابتكار الشخصية وتطبيقها بنجاح! 🎭','ok');
      loadData();
    } else {
      toast('فشل الابتكار','error');
    }
  }catch(e){toast('خطأ!','error');}
  if(btn){ btn.textContent = '✨ ابتكار شخصية'; btn.disabled = false; }
}


async function startMinigame(){
  const typ = document.getElementById('minigame-type').value;
  const btn = document.getElementById('btn-minigame');
  btn.textContent = '⏳ جاري الإطلاق...'; btn.disabled = true;
  try {
    const r = await fetch('/api/start_minigame', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type:typ})});
    const d = await r.json();
    if(d.ok){ toast('تم إرسال اللعبة للشات! 🎮','ok'); }
    else { toast('خطأ: ' + (d.error||'فشل'),'error'); }
  }catch(e){toast('خطأ!','error');}
  btn.textContent = '🚀 أطلق اللعبة'; btn.disabled = false;
}

async function playEffect(eff){
  try {
    const r = await fetch('/api/soundboard', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({effect:eff})});
    const d = await r.json();
    if(d.ok){ toast('جاري تشغيل الصوت... 🔊','ok'); }
    else { toast('خطأ: ' + (d.error||'لا يوجد أحد بالفويس'),'error'); }
  }catch(e){toast('خطأ!','error');}
}

async function sendCustom(){
  const mid=document.getElementById('roast-target').value,txt=document.getElementById('roast-text').value.trim();
  if(!mid||!txt){showMsg('custom-msg','⚠️ اختر عضو واكتب');return}
  const r=await fetch('/api/custom_roast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:mid,text:txt})});
  const d=await r.json();
  if(d.ok){toast('الذبة انرسلت! 🚀','ok');document.getElementById('roast-text').value='';setTimeout(loadData,2000)}
  else showMsg('custom-msg','❌ '+d.error);
}

async function sendFree(){
  const txt=document.getElementById('free-text').value.trim();
  if(!txt){showMsg('free-msg','⚠️ اكتب شيء');return}
  const r=await fetch('/api/free_message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:txt})});
  const d=await r.json();
  if(d.ok){toast('الرسالة انرسلت! 📨','ok');document.getElementById('free-text').value=''}
  else showMsg('free-msg','❌');
}

async function targetedRoast(){
  const mid=document.getElementById('target-member')?.value || document.getElementById('smart-roast-target')?.value;
  if(!mid){showMsg('status-msg','⚠️ اختر عضو');return}
  await fetch('/api/targeted_roast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:mid})});
  toast('ذبة موجهة انطلقت! 🎯','ok');setTimeout(loadData,3000);
}

// ─── Dialect Control ─────────────────────────
function renderDialects(currentDialect, dialects){
  const cur = (dialects||[]).find(d => d.id === currentDialect) || (dialects ? dialects[0] : null);
  const headerD = document.getElementById('header-dialect');
  if(headerD) headerD.textContent = '🗣️ ' + (cur ? cur.badge : 'عامية');
  const ovD = document.getElementById('ov-dialect-name');
  if(ovD) ovD.textContent = cur ? cur.name : 'عامية';
  const ctrlD = document.getElementById('ctrl-dialect-badge');
  if(ctrlD) ctrlD.textContent = cur ? cur.name : 'عامية';

  // Overview quick buttons
  ['default','riyadh','jeddah','qassim'].forEach(id => {
    const b = document.getElementById('btn-dial-' + id);
    if(b){
      if(id === currentDialect){
        b.className = 'btn btn-sm btn-red';
      } else {
        b.className = 'btn btn-sm';
      }
    }
  });

  // Dialect Grid Cards
  const grid = document.getElementById('dialect-grid');
  if(grid && dialects){
    grid.innerHTML = dialects.map(d => {
      const isActive = d.id === currentDialect;
      return `<div class="dialect-card ${isActive ? 'active' : ''}" onclick="changeDialect('${d.id}')">
        <span class="dialect-active-indicator">● مفعلة حالياً</span>
        <div class="dialect-card-top">
          <div class="dialect-name"><span>${d.icon}</span> <span>${d.name}</span></div>
          <span class="dialect-badge">${d.badge}</span>
        </div>
        <div class="dialect-desc">المنطقة: ${d.region}</div>
        <div class="dialect-quote">"${d.catchphrase}"</div>
      </div>`;
    }).join('');
  }
}

async function changeDialect(dialectId){
  try {
    const r = await fetch('/api/change_dialect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dialect: dialectId})
    });
    const d = await r.json();
    if(d.ok){
      toast('تم تغيير لهجة البوت إلى: ' + d.name + ' 🗣️', 'ok');
      loadData();
    } else {
      toast('فشل تغيير اللهجة: ' + (d.error || ''), 'error');
    }
  } catch(e) {
    toast('خطأ في الاتصال بالسيرفر', 'error');
  }
}

// ─── Smart Roast Launcher ────────────────────
function updateIntensityLabel(val){
  const labels = {
    "1": "1 - مداعبة خفيفة وحنونة 😊",
    "2": "2 - طقطقة خفيفة وودية 😉",
    "3": "3 - متوازنة وذكية 🎯",
    "4": "4 - قوية وحارة 🔥",
    "5": "5 - قصف نووي بدون رحمة 💥💀"
  };
  const el = document.getElementById('lbl-intensity');
  if(el) el.textContent = labels[val] || val;
}

function applyTopicPreset(val){
  if(!val || val === 'custom') return;
  const topicBox = document.getElementById('smart-roast-topic');
  if(val === 'dossier'){
    topicBox.value = 'نبش في ملف فضائحه وسوابقه وأعذاره واجلده بها';
  } else {
    topicBox.value = val;
  }
}

function quickSmartRoast(mid){
  showPage('control');
  const sel = document.getElementById('smart-roast-target');
  if(sel) sel.value = mid;
  window.scrollTo({top: 200, behavior: 'smooth'});
}

async function launchSmartRoast(){
  const mid = document.getElementById('smart-roast-target').value;
  if(!mid){
    showMsg('smart-roast-msg', '⚠️ اختر الضحية أولاً');
    return;
  }
  const dialect = document.getElementById('smart-roast-dialect').value;
  const intensity = document.getElementById('smart-roast-intensity').value;
  const topic = document.getElementById('smart-roast-topic').value.trim();
  const playAudio = document.getElementById('smart-roast-audio').checked;

  const btn = document.getElementById('btn-smart-roast');
  btn.textContent = '⏳ جاري التفكير وإطلاق الذبة...';
  btn.disabled = true;

  try {
    const r = await fetch('/api/targeted_roast', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        member_id: mid,
        dialect: dialect || null,
        intensity: parseInt(intensity),
        topic: topic || null,
        play_audio: playAudio
      })
    });
    const d = await r.json();
    if(d.ok){
      toast('تم إطلاق الذبة بنجاح! 🎯🔥', 'ok');
      showMsg('smart-roast-msg', '✅ تم إرسال الذبة!');
      setTimeout(loadData, 2500);
    } else {
      showMsg('smart-roast-msg', '❌ ' + (d.error || 'فشل'));
    }
  } catch(e) {
    showMsg('smart-roast-msg', '❌ خطأ بالاتصال');
  }
  btn.textContent = '🚀 أطلق الذبة الذكية';
  btn.disabled = false;
}

// ─── User Dossier Modal ──────────────────────
let currentDossierMid = null;

async function openDossierModal(mid, name, avatar){
  currentDossierMid = mid;
  document.getElementById('dm-name').textContent = name || 'عضو';
  document.getElementById('dm-id').textContent = 'ID: ' + mid;
  document.getElementById('dm-avatar').src = avatar || '';
  document.getElementById('dossier-modal').classList.add('open');

  document.getElementById('dm-titles').innerHTML = '<span style="color:var(--muted);font-size:.75rem">جاري التحميل...</span>';
  document.getElementById('dm-excuses').innerHTML = '<span style="color:var(--muted);font-size:.75rem">جاري التحميل...</span>';
  document.getElementById('dm-moments').innerHTML = '<span style="color:var(--muted);font-size:.75rem">جاري التحميل...</span>';

  try {
    const r = await fetch('/api/dossier?member_id=' + mid);
    const d = await r.json();
    if(d.ok && d.dossier){
      renderDossierData(d.dossier);
    }
  } catch(e){
    console.error(e);
  }
}

function renderDossierData(d){
  const titles = d.titles || [];
  const excuses = d.excuses || [];
  const moments = d.embarrassing_moments || [];

  const tEl = document.getElementById('dm-titles');
  tEl.innerHTML = titles.length ? titles.map(t => `<span class="badge badge-yellow">👑 ${t}</span>`).join(' ') : '<span style="font-size:.75rem;color:var(--muted)">لا توجد ألقاب مسجلة</span>';

  const eEl = document.getElementById('dm-excuses');
  eEl.innerHTML = excuses.length ? excuses.map(e => `<div class="dossier-tag" style="border-right:3px solid var(--blue)">🤥 "${e}"</div>`).join('') : '<span style="font-size:.75rem;color:var(--muted)">لا توجد أعذار مسجلة</span>';

  const mEl = document.getElementById('dm-moments');
  mEl.innerHTML = moments.length ? moments.map(m => `<div class="dossier-tag" style="border-right:3px solid var(--accent)">🙈 ${m}</div>`).join('') : '<span style="font-size:.75rem;color:var(--muted)">لا توجد فضائح مسجلة</span>';
}

function closeDossierModal(){
  document.getElementById('dossier-modal').classList.remove('open');
  currentDossierMid = null;
}

function openSelectedDossier(){
  const sel = document.getElementById('dossier-member-select');
  const mid = sel.value;
  if(!mid){ toast('اختر عضواً أولاً', 'error'); return; }
  const opt = sel.options[sel.selectedIndex];
  const name = opt ? opt.text : 'عضو';
  const mem = (D.all_members||[]).find(m => String(m.id) === String(mid));
  openDossierModal(mid, name, mem ? mem.avatar : '');
}

async function addDossierItem(){
  if(!currentDossierMid) return;
  const typ = document.getElementById('dm-add-type').value;
  const txt = document.getElementById('dm-add-text').value.trim();
  if(!txt){ toast('اكتب النص أولاً', 'error'); return; }

  try {
    const r = await fetch('/api/dossier/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        member_id: currentDossierMid,
        type: typ,
        content: txt
      })
    });
    const d = await r.json();
    if(d.ok && d.dossier){
      renderDossierData(d.dossier);
      document.getElementById('dm-add-text').value = '';
      toast('تم حفظ المعلومة في ملف العار! 📂', 'ok');
    } else {
      toast('فشل الحفظ: ' + (d.error||''), 'error');
    }
  } catch(e){
    toast('خطأ بالاتصال', 'error');
  }
}

async function changeInterval(){
  const mn=+document.getElementById('slider-min').value,mx=+document.getElementById('slider-max').value;
  const r=await fetch('/api/change_interval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min:mn,max:mx})});
  const d=await r.json();
  if(d.ok){toast('تم تغيير الوقت: '+d.min+'–'+d.max+' دقيقة','ok')}
}

async function changeVoice(){
  const v=document.getElementById('voice-select').value;
  const r=await fetch('/api/change_voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice:v})});
  const d=await r.json();
  if(d.ok){toast('تم تغيير صوت البوت لـ '+v+' 🎙️','ok');showMsg('voice-msg','✅ تم تغيير الصوت')}
}

async function changePersona(){
  const p=document.getElementById('persona-select').value;
  const pName=document.getElementById('persona-select').options[document.getElementById('persona-select').selectedIndex].text;
  const r=await fetch('/api/change_persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona:p})});
  const d=await r.json();
  if(d.ok){toast('شخصية البوت صارت: '+pName+' 🎭','ok')}
}

async function addProtect(){
  const mid=document.getElementById('prot-select').value;
  if(!mid)return;
  await fetch('/api/protect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:+mid,action:'add'})});
  toast('تمت الحماية 🛡️','ok');setTimeout(loadData,1000);
}

async function removeProtect(mid){
  await fetch('/api/protect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:mid,action:'remove'})});
  toast('تمت إزالة الحماية','ok');setTimeout(loadData,1000);
}

function showMsg(id,msg){const e=document.getElementById(id);e.textContent=msg;setTimeout(()=>e.textContent='',4000)}

async function toggleVoiceJoin(){
  const r=await fetch('/api/stats');const d=await r.json();
  const newVal = !d.voice_join_allowed;
  await fetch('/api/voice_settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({join_allowed:newVal})});
  toast(newVal?'البوت يقدر يدخل الفويس 🔓':'البوت ممنوع من الفويس 🔒','ok');setTimeout(loadData,500);
}
async function toggleProactiveAudio(){
  const r=await fetch('/api/stats');const d=await r.json();
  const newVal = !d.voice_proactive_audio;
  await fetch('/api/voice_settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proactive_audio:newVal})});
  toast(newVal?'الدخول الاستباقي مفعل 🥷':'الدخول الاستباقي معطل 🛑','ok');setTimeout(loadData,500);
}
async function kickVoice(){
  await fetch('/api/voice_kick',{method:'POST'});toast('تم طرد البوت من الفويس 🚪','ok');setTimeout(loadData,1000);
}
async function saveVoiceSettings(){
  const leave=+document.getElementById('slider-leave').value;
  const mode=document.getElementById('voice-mode-select').value;
  await fetch('/api/voice_settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_leave_sec:leave,ai_mode:mode})});
  toast('تم حفظ إعدادات المحادثة الصوتية ✅','ok');showMsg('voice-settings-msg','✅ تم الحفظ');
}
async function addVoiceIgnore(){
  const mid=document.getElementById('voice-ignore-select').value;if(!mid)return;
  await fetch('/api/voice_ignore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:+mid,action:'add'})});
  toast('تم تجاهل العضو 🔇','ok');setTimeout(loadData,500);
}
async function removeVoiceIgnore(mid){
  await fetch('/api/voice_ignore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:mid,action:'remove'})});
  toast('تمت إزالة التجاهل','ok');setTimeout(loadData,500);
}

loadData();setInterval(loadData,20000);

// ─── Debug Tab ───
let debugInterval=null;
async function loadDebug(){
  try{
    const r=await fetch('/api/voice_debug');
    const d=await r.json();
    if(d.status==='no_active_session'){
      document.getElementById('dbg-status').innerHTML='<span style="color:#ef4444">⚫ لا توجد جلسة</span>';
      document.getElementById('dbg-speaker').textContent='—';
      document.getElementById('dbg-playing').textContent='—';
      document.getElementById('dbg-recv').textContent='0';
      document.getElementById('dbg-sent').textContent='0';
      document.getElementById('dbg-gemini').textContent='0';
      document.getElementById('dbg-buffer').textContent='0 bytes';
      document.getElementById('dbg-lastact').textContent='—';
      document.getElementById('dbg-participants').textContent='—';
      document.getElementById('dbg-log').innerHTML='<div class="empty">لا توجد جلسة نشطة</div>';
      document.getElementById('dbg-log-count').textContent='0';
      return;
    }
    const s=Object.values(d)[0];
    document.getElementById('dbg-status').innerHTML=s.running?'<span style="color:#22c55e">🟢 شغّال</span>':'<span style="color:#ef4444">⚫ متوقف</span>';
    document.getElementById('dbg-speaker').textContent=s.active_speaker||'ما حد';
    document.getElementById('dbg-playing').innerHTML=s.is_playing?'<span style="color:#f59e0b">🔊 نعم</span>':'<span style="color:#64748b">🔇 لا</span>';
    document.getElementById('dbg-recv').textContent=s.audio_recv_count||0;
    document.getElementById('dbg-sent').textContent=s.audio_send_count||0;
    document.getElementById('dbg-gemini').textContent=s.gemini_recv_count||0;
    document.getElementById('dbg-buffer').textContent=(s.input_buffer_bytes||0)+' bytes';
    document.getElementById('dbg-lastact').textContent=(s.last_activity_ago||0)+'s ago';
    document.getElementById('dbg-participants').textContent=(s.participants||[]).join('، ')||'ما حد';
    const log=s.log||[];
    document.getElementById('dbg-log-count').textContent=log.length;
    const colors={SESSION_START:'#22c55e',AUDIO_SENT:'#3b82f6',GEMINI_RESPONSE:'#a855f7',PLAY_START:'#f59e0b',PLAY_CONVERTED:'#f59e0b',PLAY_DONE:'#06b6d4'};
    document.getElementById('dbg-log').innerHTML=log.length?log.slice().reverse().map(e=>{
      const c=colors[e.event]||'#94a3b8';
      return '<div style="padding:2px 4px;border-bottom:1px solid var(--border)"><span style="color:#64748b">'+e.elapsed+'s</span> <span style="color:'+c+';font-weight:bold">'+e.event+'</span> <span style="color:var(--text)">'+e.detail+'</span></div>';
    }).join(''):'<div class="empty">لا توجد أحداث</div>';
  }catch(e){console.error('Debug load error:',e)}
}
</script>
</body>
</html>"""


async def handle_index(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


def create_web_app(bot_instance) -> web.Application:
    app = web.Application()
    app["bot"] = bot_instance
    app.router.add_get("/",                   handle_index)
    app.router.add_get("/api/stats",          handle_stats)
    app.router.add_post("/api/force_roast",   handle_force_roast)
    app.router.add_post("/api/toggle",        handle_toggle)
    app.router.add_post("/api/custom_roast",  handle_custom_roast)
    app.router.add_post("/api/free_message",  handle_free_message)
    app.router.add_post("/api/targeted_roast",handle_targeted_roast)
    app.router.add_post("/api/change_interval",handle_change_interval)
    app.router.add_post("/api/change_voice",  handle_change_voice)
    app.router.add_post("/api/change_persona",handle_change_persona)
    app.router.add_post("/api/change_dialect",handle_change_dialect)
    app.router.add_get("/api/dossier",        handle_dossier)
    app.router.add_post("/api/dossier/add",   handle_add_dossier_item)
    app.router.add_post("/api/voice_settings", handle_voice_settings)
    app.router.add_post("/api/voice_ignore",   handle_voice_ignore)
    app.router.add_post("/api/voice_kick",     handle_voice_kick)
    app.router.add_post("/api/protect",       handle_protect)
    app.router.add_get("/api/voice_debug",    handle_voice_debug)
    app.router.add_post("/api/ai_report",     handle_ai_report)
    app.router.add_post("/api/build_persona", handle_build_persona)
    app.router.add_post("/api/start_minigame",handle_start_minigame)
    app.router.add_post("/api/soundboard",    handle_soundboard)
    return app


async def start_web_server(bot_instance):
    bot_instance._start_time = time.time()
    port = int(os.environ.get("PORT", 8080))
    app  = create_web_app(bot_instance)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web dashboard running on port {port}")
