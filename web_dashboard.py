"""
web_dashboard.py – لوحة تحكم ويب لبوت مستر ذبات
تُشغَّل بجانب البوت عبر asyncio (aiohttp)
"""
import asyncio
import json
import time
from aiohttp import web

# ─── API endpoints ──────────────────────────────────────────────────────────

async def handle_stats(request):
    bot = request.app["bot"]
    members_in_vc = []
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for m in vc.members:
                if not m.bot:
                    join_time = bot.vc_join_times.get(m.id, time.time())
                    mins = int((time.time() - join_time) / 60)
                    games = list(bot.user_game_history.get(m.id, []))
                    members_in_vc.append({
                        "name": m.display_name,
                        "avatar": str(m.display_avatar.url),
                        "minutes": mins,
                        "channel": vc.name,
                        "games": games,
                        "muted": m.voice.self_mute or m.voice.mute if m.voice else False,
                        "deafened": m.voice.self_deaf or m.voice.deaf if m.voice else False,
                    })

    recent_roasts = [
        {"time": r[0], "member": r[1], "roast": r[2]}
        for r in bot.roast_log[-10:]
    ]

    data = {
        "bot_name": bot.user.name if bot.user else "مستر ذبات",
        "bot_avatar": str(bot.user.display_avatar.url) if bot.user else "",
        "roast_loop_running": bot.roast_loop.is_running(),
        "members_in_vc": members_in_vc,
        "recent_roasts": recent_roasts,
    }
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json"
    )


async def handle_force_roast(request):
    bot = request.app["bot"]
    asyncio.create_task(bot.force_random_roast())
    return web.Response(text='{"ok": true}', content_type="application/json")


async def handle_toggle(request):
    bot = request.app["bot"]
    running = await bot.toggle_roast_loop()
    return web.Response(
        text=json.dumps({"running": running}),
        content_type="application/json"
    )


# ─── HTML Dashboard ──────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>مستر ذبات – لوحة التحكم</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --accent: #e11d48; --green: #16a34a; --yellow: #ca8a04;
    --text: #e6edf3; --muted: #8b949e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Cairo', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1a0a0f, #2d0a1a); border-bottom: 1px solid var(--border); padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem; }
  .header img { width: 52px; height: 52px; border-radius: 50%; border: 2px solid var(--accent); }
  .header h1 { font-size: 1.6rem; font-weight: 900; color: var(--accent); }
  .header .sub { color: var(--muted); font-size: 0.85rem; }
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; }
  .card h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
  .badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.78rem; font-weight: 600; }
  .badge-green { background: #14532d; color: #4ade80; }
  .badge-red   { background: #450a0a; color: #f87171; }
  .badge-yellow{ background: #422006; color: #fbbf24; }
  .member { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
  .member:last-child { border-bottom: none; }
  .member img { width: 36px; height: 36px; border-radius: 50%; }
  .member-info { flex: 1; }
  .member-name { font-weight: 700; font-size: 0.95rem; }
  .member-meta { color: var(--muted); font-size: 0.78rem; }
  .roast-item { padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
  .roast-item:last-child { border-bottom: none; }
  .roast-name { color: var(--accent); font-weight: 700; font-size: 0.85rem; }
  .roast-text { color: var(--text); font-size: 0.88rem; margin-top: 0.2rem; line-height: 1.5; }
  .controls { display: flex; gap: 1rem; flex-wrap: wrap; }
  .btn { padding: 0.6rem 1.4rem; border: none; border-radius: 8px; font-family: 'Cairo', sans-serif; font-weight: 700; font-size: 0.95rem; cursor: pointer; transition: opacity 0.2s; }
  .btn:hover { opacity: 0.85; }
  .btn-red   { background: var(--accent); color: #fff; }
  .btn-green { background: var(--green); color: #fff; }
  .btn-yellow{ background: var(--yellow); color: #fff; }
  #status-msg { margin-top: 0.8rem; font-size: 0.85rem; color: var(--muted); }
  .empty { color: var(--muted); font-size: 0.88rem; text-align: center; padding: 1rem 0; }
</style>
</head>
<body>
<div class="header">
  <img id="bot-avatar" src="" alt="bot">
  <div>
    <h1 id="bot-name">مستر ذبات</h1>
    <div class="sub" id="loop-status">جاري التحميل...</div>
  </div>
</div>

<div class="container">
  <div class="grid">

    <!-- Controls -->
    <div class="card">
      <h2>🕹️ التحكم</h2>
      <div class="controls">
        <button class="btn btn-red"    onclick="forceRoast()">⚡ ذب الآن</button>
        <button class="btn btn-yellow" onclick="toggleLoop()">⏯️ إيقاف/تشغيل</button>
        <button class="btn btn-green"  onclick="loadData()">🔄 تحديث</button>
      </div>
      <p id="status-msg"></p>
    </div>

    <!-- Members in VC -->
    <div class="card">
      <h2>🎧 بالفويس الحين</h2>
      <div id="members-list"><p class="empty">لا أحد بالفويس</p></div>
    </div>

    <!-- Recent roasts -->
    <div class="card" style="grid-column: 1 / -1">
      <h2>🔥 آخر الذبات</h2>
      <div id="roasts-list"><p class="empty">لا توجد ذبات بعد</p></div>
    </div>

  </div>
</div>

<script>
async function loadData() {
  const res  = await fetch('/api/stats');
  const data = await res.json();

  document.getElementById('bot-name').textContent   = data.bot_name;
  document.getElementById('bot-avatar').src         = data.bot_avatar;
  document.getElementById('loop-status').innerHTML  = data.roast_loop_running
    ? '<span class="badge badge-green">الذبات التلقائية: شغالة</span>'
    : '<span class="badge badge-red">الذبات التلقائية: متوقفة</span>';

  // Members
  const ml = document.getElementById('members-list');
  if (data.members_in_vc.length === 0) {
    ml.innerHTML = '<p class="empty">لا أحد بالفويس</p>';
  } else {
    ml.innerHTML = data.members_in_vc.map(m => {
      const tags = [];
      if (m.deafened) tags.push('<span class="badge badge-red">دفن</span>');
      else if (m.muted) tags.push('<span class="badge badge-yellow">ميوت</span>');
      if (m.games.length) tags.push(`<span class="badge badge-green">${m.games[m.games.length-1]}</span>`);
      const h = Math.floor(m.minutes/60), min = m.minutes%60;
      const dur = h ? (h===1?'ساعة':h===2?'ساعتين':h+' ساعات') + (min ? ' و '+min+' د' : '') : m.minutes + ' دقيقة';
      return `<div class="member">
        <img src="${m.avatar}" alt="${m.name}">
        <div class="member-info">
          <div class="member-name">${m.name} ${tags.join(' ')}</div>
          <div class="member-meta">📍 ${m.channel} &nbsp;⏱️ ${dur}</div>
        </div>
      </div>`;
    }).join('');
  }

  // Roasts
  const rl = document.getElementById('roasts-list');
  if (data.recent_roasts.length === 0) {
    rl.innerHTML = '<p class="empty">لا توجد ذبات بعد</p>';
  } else {
    rl.innerHTML = [...data.recent_roasts].reverse().map(r => {
      const d = new Date(r.time * 1000);
      const t = d.toLocaleTimeString('ar-SA', {hour:'2-digit', minute:'2-digit'});
      return `<div class="roast-item">
        <div class="roast-name">@${r.member} &nbsp; <span style="color:var(--muted);font-weight:400">${t}</span></div>
        <div class="roast-text">${r.roast}</div>
      </div>`;
    }).join('');
  }
}

async function forceRoast() {
  await fetch('/api/force_roast', {method:'POST'});
  document.getElementById('status-msg').textContent = '✅ تم إرسال أمر الذبة!';
  setTimeout(() => { document.getElementById('status-msg').textContent=''; loadData(); }, 2000);
}

async function toggleLoop() {
  const res  = await fetch('/api/toggle', {method:'POST'});
  const data = await res.json();
  document.getElementById('status-msg').textContent = data.running ? '▶️ الذبات التلقائية شغّالة' : '⏸️ الذبات التلقائية متوقفة';
  setTimeout(() => { document.getElementById('status-msg').textContent=''; loadData(); }, 2000);
}

// تحديث تلقائي كل 30 ثانية
loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>"""


async def handle_index(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


# ─── Server factory ──────────────────────────────────────────────────────────

def create_web_app(bot_instance) -> web.Application:
    app = web.Application()
    app["bot"] = bot_instance
    app.router.add_get("/",                handle_index)
    app.router.add_get("/api/stats",       handle_stats)
    app.router.add_post("/api/force_roast", handle_force_roast)
    app.router.add_post("/api/toggle",     handle_toggle)
    return app


async def start_web_server(bot_instance):
    port = int(os.environ.get("PORT", 8080))
    app  = create_web_app(bot_instance)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web dashboard running on port {port}")


import os  # needed for PORT env var above
