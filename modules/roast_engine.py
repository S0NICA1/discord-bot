"""
roast_engine.py - محرك الذبات المتقدم 3.0
يشمل:
1. جلسات محكمة السيرفر (Server Court & Trials)
2. حلبة مواجهات 1v1 مع تحكيم الذكاء الاصطناعي (Roast Battles)
3. مولد بطاقات العار الرقمية (Visual Shame Cards - SVG/HTML)
"""
import asyncio
import json
import os
import random
import time
from google import genai
from google.genai import types
from modules.dialects import DIALECTS, get_dialect_prompt
from modules.dossier import dossier_mgr
from modules.ai_service import get_genai_client

class RoastEngine:
    def __init__(self):
        self.active_trials = {} # channel_id -> trial_data
        self.active_battles = {} # channel_id -> battle_data
        self.api_key = os.getenv("GEMINI_API_KEY")

    def _get_client(self):
        return get_genai_client()

    async def generate_trial_indictment(self, defendant_name: str, charge: str, dialect: str = "default") -> dict:
        """توليد لائحة اتهام رسمية ساخرة لمحكمة السيرفر."""
        client = self._get_client()
        prompt = f"""
أنت رئيس محكمة السيرفر الساخر ومستر ذبات.
المطلوب فتح جلسة محاكمة علنية طارئة ضد المتهم: ({defendant_name}).
التهمة الموجهة له: ({charge}).
اللهجة المطلوبة: {dialect} ({DIALECTS.get(dialect, DIALECTS['default'])['name']}).

صغ لائحة الاتهام بصيغة محكمة ساخرة وقوية جداً تتضمن:
1. title: عنوان القضية الرسمي (مثل: قضية رقم 404 - جناية الصنم الأبدي)
2. indictment: تفاصيل لائحة الاتهام والأدلة المزعومة (سطرين ساخرين جداً باللهجة المختارة)
3. penalty: العقوبة المقترحة إذا ثبتت إدانته

الرد يجب أن يكون JSON فقط بالصيغة التالية بالضبط:
{{
  "title": "عنوان القضية",
  "indictment": "تفاصيل الاتهام بالعامية المطلوبة...",
  "penalty": "العقوبة الساخرة..."
}}
"""
        try:
            resp = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="HIGH")
                )
            )
            txt = resp.text.replace('```json', '').replace('```', '').strip()
            return json.loads(txt)
        except Exception as e:
            return {
                "title": f"محاكمة عاجلة: {defendant_name}",
                "indictment": f"تم استدعاء {defendant_name} بتهمة {charge} ولائحة سوابقه لا تشفع له أبداً!",
                "penalty": "الجلد الساخر الفوري ووضع اسمه في جدار العار"
            }

    async def judge_battle(self, user1: str, user2: str, roast1: str, roast2: str, topic: str = "تحدي حر") -> dict:
        """تحكيم معركة ذبات بين عضوين وإعلان الفائز."""
        client = self._get_client()
        prompt = f"""
أنت حكم حلبة معارك الذبات (Roast Battle Referee) الأسطوري في الديسكورد.
المتسابق 1: {user1}
ذبة {user1}: "{roast1}"

المتسابق 2: {user2}
ذبة {user2}: "{roast2}"

موضوع التحدي: {topic}

قم بتحكيم المعركة بعدالة وبأسلوب معلق رياضي فكاهي ومشتعل:
1. score1: تقييم ذبة {user1} من 10
2. score2: تقييم ذبة {user2} من 10
3. winner: اسم الفائز (أو 'تعادل')
4. commentary: تعليق الحكم الساخر على الذبتين ولماذا فاز هذا الطرف (سطرين مضحكين)
5. knockout_punch: أقوى كلمة أو قصف في المعركة

الرد يجب أن يكون JSON فقط بالصيغة التالية:
{{
  "score1": 8.5,
  "score2": 7.0,
  "winner": "{user1}",
  "commentary": "تعليق الحكم بالعامية السعودية...",
  "knockout_punch": "الكلمة القاضية"
}}
"""
        try:
            resp = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="HIGH")
                )
            )
            txt = resp.text.replace('```json', '').replace('```', '').strip()
            return json.loads(txt)
        except Exception as e:
            return {
                "score1": 7.5,
                "score2": 7.5,
                "winner": "تعادل",
                "commentary": "الاثنين جابوا العيد بس الذبات تمشي الحال!",
                "knockout_punch": "ما فيه أحد حسمها"
            }

    def generate_shame_card_svg(self, card_data: dict, roast_text: str = "", dialect_badge: str = "عامية") -> str:
        """توليد كود بطاقة العار الرسومية بصيغة SVG فائقة الدقة."""
        name = card_data.get("name", "مجهول")
        title = card_data.get("title", "متهم تحت المراقبة")
        crime = card_data.get("crime", "النكبة المستمرة")
        top_excuse = card_data.get("top_excuse", "الماوس علق والنت فصل")
        avatar = card_data.get("avatar") or "https://cdn.discordapp.com/embed/avatars/0.png"
        stats = card_data.get("stats", {"excuses": 99, "aim": 4, "choke": 95, "sleep": 1})

        roast_display = roast_text or f"أشهر تصريفاته: {top_excuse}"
        if len(roast_display) > 85:
            roast_display = roast_display[:82] + "..."

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 700" width="500" height="700">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0f18"/>
      <stop offset="50%" stop-color="#121a29"/>
      <stop offset="100%" stop-color="#07090e"/>
    </linearGradient>
    <linearGradient id="borderGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff2a5f"/>
      <stop offset="50%" stop-color="#8b5cf6"/>
      <stop offset="100%" stop-color="#00f0ff"/>
    </linearGradient>
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fbbf24"/>
      <stop offset="100%" stop-color="#f59e0b"/>
    </linearGradient>
    <filter id="neonGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
    <clipPath id="avatarClip">
      <circle cx="250" cy="190" r="75"/>
    </clipPath>
  </defs>

  <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&amp;display=swap');
    text {{ font-family: 'Cairo', sans-serif; }}
    .title-txt {{ font-size: 26px; font-weight: 900; fill: #ffffff; text-anchor: middle; }}
    .sub-txt {{ font-size: 15px; font-weight: 700; fill: #ff2a5f; text-anchor: middle; }}
    .crime-txt {{ font-size: 13px; fill: #94a3b8; text-anchor: middle; }}
    .stat-val {{ font-size: 22px; font-weight: 900; fill: #00f0ff; text-anchor: middle; }}
    .stat-lbl {{ font-size: 11px; font-weight: 700; fill: #64748b; text-anchor: middle; }}
    .roast-txt {{ font-size: 14px; font-weight: 600; fill: #e2e8f0; text-anchor: middle; }}
  </style>

  <!-- Base Card -->
  <rect x="15" y="15" width="470" height="670" rx="30" fill="url(#bgGrad)" stroke="url(#borderGrad)" stroke-width="4" filter="url(#neonGlow)"/>
  <rect x="25" y="25" width="450" height="650" rx="24" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1.5"/>

  <!-- Top Badges -->
  <rect x="40" y="45" width="80" height="28" rx="8" fill="rgba(255,42,95,0.15)" stroke="#ff2a5f" stroke-width="1.5"/>
  <text x="80" y="64" font-size="12" font-weight="900" fill="#ff2a5f" text-anchor="middle">WANTED</text>

  <rect x="370" y="45" width="90" height="28" rx="8" fill="rgba(139,92,246,0.15)" stroke="#8b5cf6" stroke-width="1.5"/>
  <text x="415" y="64" font-size="12" font-weight="700" fill="#a855f7" text-anchor="middle">{dialect_badge}</text>

  <!-- Mugshot / Avatar -->
  <circle cx="250" cy="190" r="82" fill="none" stroke="url(#borderGrad)" stroke-width="4" stroke-dasharray="8 4"/>
  <circle cx="250" cy="190" r="77" fill="#1e293b"/>
  <image href="{avatar}" x="175" y="115" width="150" height="150" clip-path="url(#avatarClip)"/>

  <!-- Suspect Info -->
  <text x="250" y="305" class="title-txt">{name}</text>
  <text x="250" y="332" class="sub-txt">« {title} »</text>
  <text x="250" y="358" class="crime-txt">التهمة: {crime}</text>

  <!-- Stats Grid -->
  <g transform="translate(45, 385)">
    <!-- Card 1 -->
    <rect x="0" y="0" width="90" height="75" rx="14" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="45" y="38" class="stat-val" fill="#ff2a5f">{stats.get('excuses', 99)}%</text>
    <text x="45" y="60" class="stat-lbl">نسبة التصريف</text>

    <!-- Card 2 -->
    <rect x="105" y="0" width="90" height="75" rx="14" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="150" y="38" class="stat-val" fill="#ef4444">{stats.get('aim', 5)}%</text>
    <text x="150" y="60" class="stat-lbl">دقة الإيم</text>

    <!-- Card 3 -->
    <rect x="210" y="0" width="90" height="75" rx="14" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="255" y="38" class="stat-val" fill="#f59e0b">{stats.get('choke', 92)}%</text>
    <text x="255" y="60" class="stat-lbl">معدل النكبة</text>

    <!-- Card 4 -->
    <rect x="315" y="0" width="90" height="75" rx="14" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="360" y="38" class="stat-val" fill="#8b5cf6">{stats.get('sleep', 1)}h</text>
    <text x="360" y="60" class="stat-lbl">ساعات النوم</text>
  </g>

  <!-- Roast / Verdict Box -->
  <g transform="translate(45, 485)">
    <rect x="0" y="0" width="410" height="135" rx="18" fill="rgba(255,42,95,0.06)" stroke="rgba(255,42,95,0.3)" stroke-width="1.5"/>
    <rect x="0" y="0" width="8" height="135" rx="4" fill="#ff2a5f"/>
    <text x="205" y="32" font-size="13" font-weight="700" fill="#ff2a5f" text-anchor="middle">🎯 حكم محكمة العار الرسمي</text>
    <text x="205" y="70" class="roast-txt">"{roast_display}"</text>
    <text x="205" y="112" font-size="11" fill="#64748b" text-anchor="middle">صادر عن مستر ذبات 3.0 • غير قابل للاستئناف</text>
  </g>
</svg>"""
        return svg

roast_engine = RoastEngine()