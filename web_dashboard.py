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
                    })

    # كل الأعضاء
    all_members = []
    for guild in bot.guilds:
        for m in guild.members:
            if not m.bot:
                all_members.append({"id":m.id,"name":m.display_name,"avatar":str(m.display_avatar.url)})

    # لوحة العار
    shame = []
    for guild in bot.guilds:
        for uid, cnt in sorted(bot.roast_count_per_user.items(), key=lambda x:-x[1])[:15]:
            m = guild.get_member(uid)
            if m:
                shame.append({"id":uid,"name":m.display_name,"avatar":str(m.display_avatar.url),"count":cnt})

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
        "current_voice": getattr(bot, "current_voice", "Kore")
    }
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
        mid = int(body.get("member_id",0))
        if not mid: return web.Response(text='{"ok":false}', content_type="application/json")
        ok = await bot.targeted_roast(mid)
        return web.Response(text=json.dumps({"ok":ok}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"ok":False,"error":str(e)}), content_type="application/json")


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
    <button class="theme-btn" onclick="toggleTheme()" id="theme-btn">🌙</button>
  </div>
</div>

<div class="container">
  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="showPage('overview')">📊 نظرة عامة</div>
    <div class="tab" onclick="showPage('control')">🕹️ التحكم</div>
    <div class="tab" onclick="showPage('roasts')">🔥 الذبات</div>
    <div class="tab" onclick="showPage('analytics')">📈 التحليلات</div>
    <div class="tab" onclick="showPage('members')">👥 الأعضاء</div>
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
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🎧 بالفويس الحين</h2><span class="badge badge-green" id="vc-count">0</span></div>
        <div class="card-body" id="members-list"><div class="empty"><div class="empty-icon">🔇</div>لا أحد</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>🏆 لوحة العار</h2></div>
        <div class="card-body" id="shame-list"><div class="empty"><div class="empty-icon">😇</div>ما فيه ضحايا بعد</div></div>
      </div>
    </div>
  </div>

  <!-- ═══ PAGE: CONTROL ═══ -->
  <div class="page" id="page-control">
    <div class="grid">
      <div class="card">
        <div class="card-head"><h2>🕹️ أوامر سريعة</h2></div>
        <div class="card-body">
          <div class="controls">
            <button class="btn btn-red" onclick="forceRoast()">⚡ ذب الحين (عشوائي)</button>
            <button class="btn btn-yellow" onclick="toggleLoop()" id="btn-toggle">⏯️ إيقاف/تشغيل</button>
            <button class="btn" onclick="loadData()">🔄 تحديث</button>
          </div>
          <div class="form-group">
            <label>🎯 ذبة موجهة (AI يولّد الذبة)</label>
            <div style="display:flex;gap:.5rem">
              <select id="target-member" style="flex:1"><option value="">اختر عضو</option></select>
              <button class="btn btn-red btn-sm" onclick="targetedRoast()">🎯 ذب</button>
            </div>
          </div>
          <div class="form-group" style="margin-top:1rem; border-top:1px solid var(--border); padding-top:1rem;">
            <label>🎙️ صوت المشوي (تغيير صوت البوت)</label>
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

    // Interval sliders
    document.getElementById('slider-min').value=D.interval_min;document.getElementById('lbl-min').textContent=D.interval_min;
    document.getElementById('slider-max').value=D.interval_max;document.getElementById('lbl-max').textContent=D.interval_max;
    // Voice
    if(D.current_voice) document.getElementById('voice-select').value = D.current_voice;

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
      return `<div class="member"><div class="member-avatar"><img src="${m.avatar}"><div class="status-dot status-${m.status||'offline'}"></div></div><div class="member-info"><div class="member-name">${m.name} ${tags.join(' ')}</div><div class="member-meta"><span>📍 ${m.channel}</span><span>⏱️ ${fmtDur(m.minutes)}</span></div></div></div>`;
    }).join('')}

    // Shame board
    const sl=document.getElementById('shame-list');
    if(!D.shame_board?.length){sl.innerHTML='<div class="empty"><div class="empty-icon">😇</div>ما فيه ضحايا</div>'}
    else{sl.innerHTML=D.shame_board.map((s,i)=>{
      const rc=i===0?'gold':i===1?'silver':i===2?'bronze':'';
      const medal=i===0?'🥇':i===1?'🥈':i===2?'🥉':(i+1);
      return `<div class="shame-item"><div class="shame-rank ${rc}">${medal}</div><img src="${s.avatar}" style="width:32px;height:32px;border-radius:50%"><span style="font-weight:700;font-size:.85rem">${s.name}</span><span class="shame-count">${s.count} ذبة</span></div>`;
    }).join('')}

    // Roasts
    allRoasts=D.recent_roasts;filterRoasts();

    // Dropdowns
    const opts='<option value="">— اختر —</option>'+D.all_members.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
    ['roast-target','target-member','prot-select'].forEach(id=>document.getElementById(id).innerHTML=opts);

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
  const mid=document.getElementById('target-member').value;
  if(!mid){showMsg('status-msg','⚠️ اختر عضو');return}
  await fetch('/api/targeted_roast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:mid})});
  toast('ذبة موجهة انطلقت! 🎯','ok');setTimeout(loadData,3000);
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

loadData();setInterval(loadData,20000);
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
    app.router.add_post("/api/protect",       handle_protect)
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
