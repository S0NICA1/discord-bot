"""
modules/dialects.py - Authentic Saudi Dialect Engine & Linguistic Architecture (R2)
Implements:
1. Saudi Dialect Specifications:
   - default: Modern Saudi youth internet slang, Twitch/Discord gaming colloquialisms
   - riyadh: Najdi dialect, dry cynicism, deadpan delivery, stoic phrasing
   - jeddah: Hijazi dialect, melodious cadence, humorous flow, rapid playful rhythm
   - qassim: Qassimi dialect, traditional particles, warm rustic irony
2. Strict Negative Constraints (Anti-pan-Arab, anti-Egyptian, anti-Levantine, anti-North African, anti-Fusha)
3. Intensity Calibration (Levels 1 to 5) with Community Shame Tags
4. Anti-Repetition Mechanism (integration with StateManager.get_recent_roasts)
5. DialectSynthesisEngine & 4-Way Comparative Synthesis Interface (Contract 3)
"""

import json
import logging
import re
from typing import Any, Optional

from modules.ai_service import generate_content_ai

logger = logging.getLogger("mr_roast.dialects")

# ──────────────────────────────────────────────────────────────────────────────
# 1. Authentic Saudi Dialect Specifications & Catalog
# ──────────────────────────────────────────────────────────────────────────────

DIALECTS = {
    "default": {
        "id": "default",
        "name": "عامية سعودية عامة وشبابية",
        "region": "المملكة بشكل عام / مجتمع الألعاب والإنترنت",
        "icon": "⚡",
        "badge": "Default",
        "vibe": "خفة دم وفصلات استراحة، ذبات سريعة تعتمد على التشبيهات والمفارقات الكوميدية اللي تفطس ضحك بدون أي نفسية أو تهاوش",
        "core_lexicon": [
            "بالله شوف", "يا ساتر", "كأنه", "طقطقة", "جاب العيد",
            "فاهي", "فاصل", "كاري", "رانك", "تكتيك",
            "عايش الدور", "متحمس", "مضيع", "لقطة", "روقنا",
            "وش هالجو", "من كيسك", "يا رجل", "تحفة", "مسوي فيها"
        ],
        "phonology_rules": (
            "استخدم صيغ الاستفهام العامية الطريفة: (وش هالجو، كيف كذا، وش وضعه، بالله من جدك). "
            "استخدم أفعال الأمر الكوميدية: (روقنا، اركد، خف علينا، وسّع صدرك). "
            "استخدم التشبيهات الاستعارية المضحكة: (كأنه، تقل، مسوي فيها)."
        ),
        "instructions": (
            "تكلم بلهجة عامية سعودية شبابية فكاهية وخفيفة دم، تشبه طقطقة الأخوياء الفاصلة في الاستراحة. "
            "ركز على التشبيهات المضحكة والمفارقات الكوميدية العجيبة اللي تخلي السيرفر يفطس ضحك، والضحية نفسه يبتسم ويضحك! "
            "ممنوع نهائياً أسلوب النفسية، النكد، العصبية، الهواش، أو عبارات الإسكات والتسفيل (مثل: خلك ساكت، انثبر، وضعك مزري، يكسر الخاطر، درملها وخلك ساكت)."
        ),
        "catchphrases": [
            "بالله شوف وش هالجو اللي عايشه؟",
            "روقنا يا كابتن وراك فاصل كذا؟",
            "يا ساتر على التكتيك اللي جاب العيد!"
        ],
        "sample_burns": [
            "بالله شوف كيف متكي بالروم وساكت، كأنه جهاز وايفاي طافي بالصالة! لا حس ولا حركة ومسوي فيها مراقب دولي، روقنا يا كابتن وعطنا سالفة!",
            "متحمس وفاتح بث وآخرتها جالس يلعب ضد بوتات وسادحينه بالزون ثلاث مرات ورا بعض.. وش هالاحتراف اللي يدرس ما شاء الله!"
        ],
        "metrics": {"sharpness": 80, "speed": 85, "authenticity": 88, "humor": 98}
    },
    "riyadh": {
        "id": "riyadh",
        "name": "لهجة الرياض / نجدية",
        "region": "الرياض والمنطقة الوسطى (نجد)",
        "icon": "🇸🇦",
        "badge": "نجدية",
        "vibe": "برود نجدي كوميدي، طقطقة هادئة ساخرة بمفارقات وتشبيهات تفطس ضحك بدون عصبية",
        "core_lexicon": [
            "مهوب", "اركد", "تسوق أمها", "مالك لوا", "وش السالفة",
            "بالحيل", "وش تبي", "يا دافع البلا", "وراه", "يا بعد راسي",
            "حركات الشفاحة", "ما عندك أحد", "والله إنك فاصل", "خابرك",
            "وش تحس به", "مدرعم", "يا حبيلك", "على هونك", "روق"
        ],
        "phonology_rules": (
            "أداة النفي الأساسية هي (مهوب / مهيب / مهوب كذا) ولا تستخدم 'مش' أو 'مو'. "
            "الاستفهام يبدأ بـ (وراه، وش تبي، وش السالفة). "
            "ألفاظ التأكيد: (بالحيل، خابرك، مالك لوا)."
        ),
        "instructions": (
            "تكلم بلهجة نجدية / أهل الرياض أصيلة وفكاهية وباردة جداً. "
            "الذبة تعتمد على البرود الكوميدي والتشبيهات الساخرة المضحكة. "
            "ممنوع العصبية أو الهواش أو عبارات الإسكات الفظة مثل (انثبر وخلك ساكت). ارمِ الذبة بهدوء تام وبشكل كوميدي يخلي الضحية نفسه يضحك."
        ),
        "catchphrases": [
            "يا بعد راسي اركد شوي مهوب كذا!",
            "تسوق أمها انت؟ مالك لوا يالحبيب!",
            "يا دافع البلا وش تحس به؟"
        ],
        "sample_burns": [
            "يا بعد راسي اركد شوي وراك مدرعم كأنك تلحق آخر حبة تميس بالسوق؟ مسوي فاهم بالسالفة وتوك تدري وش الطبخة، على هونك يا الحبيب!",
            "يا دافع البلا وش تحس به وأنت متكي صنم كذا؟ تقل شايب جالس عند باب الديرة ينتظر العصر، وسّع صدرك وعطنا علومك!"
        ],
        "metrics": {"sharpness": 88, "speed": 75, "authenticity": 96, "humor": 95}
    },
    "jeddah": {
        "id": "jeddah",
        "name": "لهجة جدة / حجازية",
        "region": "جدة والمنطقة الغربية (الحجاز)",
        "icon": "🌴",
        "badge": "حجازية",
        "vibe": "إيقاع سريع ومرن، خفة دم، دراما كوميدية وعتب فكاهي ممتع",
        "core_lexicon": [
            "يا واد", "إيش الهرجة", "سيبك منه", "يا بويا", "دحين",
            "بلاش فذلكة", "على كيفك", "هرجة فاضية", "لا تفلم علينا",
            "يا سيدي", "روقنا", "حل عن سمايا", "كدا على طول", "لا تسويلي فيها",
            "مفلوت", "قرمبع", "وربي وضعك فلم", "من جدك انت", "ايش بك"
        ],
        "phonology_rules": (
            "النداء الحجازي الشهير: (يا واد، يا بويا، يا سيدي). "
            "صيغ الزمن والاستفهام: (دحين، إيش الهرجة، إيش بك). "
            "النهي والتحذير الفكاهي: (سيبك منه، لا تفلم علينا، بلاش فذلكة)."
        ),
        "instructions": (
            "تكلم بلهجة حجازية / أهل جدة كول وفكاهية وسريعة وإيقاعها نغمي ممتع. "
            "استخدم كلمات ومصطلحات مثل: (يا واد، إيش الهرجة، سيبك منه، يا بويا، دحين، بلاش فذلكة، على كيفك، هرجة فاضية، لا تفلم علينا، يا سيدي، روقنا، بالله حل عن سمايا، كدا على طول). "
            "النبرة: سريعة، مرحة، خفيفة دم، دراما كوميدية بدون كراهية أو نفسية."
        ),
        "catchphrases": [
            "يا واد إيش الهرجة بالله؟",
            "سيبك منه لا يفلم علينا وروقنا يا بويا!",
            "بلاش فذلكة وهرجة فاضية!"
        ],
        "sample_burns": [
            "يا واد إيش الهرجة دي بالله؟ داخل الفويس وساكت كأنك حارس أمن في مجمع مقفل بعد الدوام.. روقنا يا بويا وفك الميوت نسمع إيش عندك!",
            "سيبك منه مسويلي فيها توم كروز غامض ومكتم على الصوت، وآخرتها ناسي المايك يلقط صوت مروحة المكيف يصارع من 2010.. دراما وربي!"
        ],
        "metrics": {"sharpness": 78, "speed": 95, "authenticity": 94, "humor": 96}
    },
    "qassim": {
        "id": "qassim",
        "name": "لهجة القصيم",
        "region": "منطقة القصيم",
        "icon": "🌾",
        "badge": "قصيمية",
        "vibe": "نصيحة قروية دافئة تبطن قصفاً تدميرياً للجبهة، أصالة وحروف جر تقليدية",
        "core_lexicon": [
            "وش نوحك", "مير", "تسذا", "بوه", "غديه",
            "يا بعد حيي", "وش عندك", "طس", "يا مال الغنيمة", "وراه مهبول",
            "يا علك الصلاح", "اركد", "ما عندك ما عند جدتي", "مهوب عاقل",
            "بوه مير نيم", "تهقى", "وشنهو", "دوفه", "تقل كذا"
        ],
        "phonology_rules": (
            "إبدال الكاف بحرف التاء سين (تس) في مواضع الإشارة: (تسذا بدل كذا). "
            "أدوات الربط والوجود التراثية: (مير = لكن/ثم، بوه = يوجد/فيه، غديه = لعله/يمكن). "
            "الدعاء بالصلاح كمدخل للجلد: (يا علك الصلاح، يا مال الغنيمة)."
        ),
        "instructions": (
            "تكلم بلهجة قصيمية طريفة ولاذعة جداً وأصيلة، باسلوب النصيحة التراثية التي تقصف الجبهة بالصميم. "
            "استخدم كلمات ومصطلحات مثل: (وش نوحك، مير، تسذا، بوه، غديه، يا بعد حيي، وش عندك، طس، يا مال الغنيمة، وراه مهبول، يا علك الصلاح، اركد يا مال الغنيمة، ما عندك ما عند جدتي، مهوب عاقل، بوه مير نيم، تهقى). "
            "النبرة: نصوحة ودافئة لكن تجلد وتفضح التناقضات بفكاهية قاتلة تضحك الجميع."
        ),
        "catchphrases": [
            "وش نوحك تسذا يا مال الغنيمة؟",
            "مير اركد يا بعد حيي وعلك الصلاح!",
            "ما عندك ما عند جدتي وطس بس!"
        ],
        "sample_burns": [
            "وش نوحك تسذا يا مال الغنيمة؟ متكي بالسيرفر تقل كرتون طماط منسي بحلقة الخضار، مير اركد يا بعد حيي وعطنا سالفة تسوى!",
            "غديه يعقل مير مهوب عاقل! مدرعم بالقيم تقل مضيع مفتاح الداتسون، يا علك الصلاح اركد شوي!"
        ],
        "metrics": {"sharpness": 90, "speed": 60, "authenticity": 98, "humor": 95}
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# 2. Strict Negative Constraints (Anti-Drift Guardrails)
# ──────────────────────────────────────────────────────────────────────────────

NEGATIVE_CONSTRAINTS = (
    "═══════════════════════════════════════════════════════════════════════════════\n"
    "🚫 قواعد المنع والتحذير اللغوي والأسلوبي الصارم (STRICT NEGATIVE CONSTRAINTS)\n"
    "يُحظر منعاً باتاً الانجراف إلى أي لهجة عربية أخرى أو الفصحى المصطنعة أو الأسلوب النفسي العدواني:\n"
    "1. حظر اللهجة المصرية: يمنع منعاً باتاً كلمات مثل (إيه دا، ازيك، عايز، كده، بتاع، يا راجل، معلش، خالص، يا ابني، عشان ايه، ده، دلوقتي).\n"
    "2. حظر اللهجة الشامية: يمنع منعاً باتاً كلمات مثل (شو، عم بحكي، بدي، بديش، كتير، يا زلمة، هيك، ليش عم، هلق، منيح، هاد، شو صاير).\n"
    "3. حظر اللهجة المغاربية: يمنع منعاً باتاً كلمات مثل (واش، بزاف، برشا، ديال، كيداير، راك، مزيان).\n"
    "4. حظر الفصحى المترجمة والكرتونية: يمنع منعاً باتاً كلمات مثل (أيها، لماذا، حسناً، تباً لك، في الحقيقة، يا هذا، بكل تأكيد، ويلك).\n"
    "5. حظر نصوص الذكاء الاصطناعي التمهيدية: ممنوع قول 'بالتأكيد'، 'إليك الذبة'، 'تفضل الرد' — ادخل في الذبة فوراً بسطر أو سطرين.\n"
    "6. حظر أسلوب النفسية والعصبية والهواش (Anti-Hostility & Anti-Toxicity):\n"
    "   - يمنع منعاً باتاً أسلوب النكد أو المشاحنات أو التهاوش الشخصي أو الكلام الفظ الكئيب (مثل: 'خلك ساكت بس'، 'انثبر'، 'وضعك مزري'، 'يكسر الخاطر'، 'درملها وخلك ساكت'، 'سواليفك ميتة').\n"
    "   - يمنع البدء الدائم بكلمة 'تسوقها' في كل جملة.\n"
    "   - يمنع التكرار الآلي لكلمة 'لك نص ساعة' في كل ذبة.\n"
    "   - المبدأ الأسمى: الذبة كوميدية ساخرة وخفيفة دم (Comedy & Wit)، تعتمد على التشبيهات والمفارقات التي تفطس الجميع ضحك بما فيهم الضحية، وليست خناقة أو هواش شوارع!\n"
    "═══════════════════════════════════════════════════════════════════════════════"
)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Intensity Calibration (Levels 1 to 5)
# ──────────────────────────────────────────────────────────────────────────────

INTENSITY_CONFIG = {
    1: {
        "level": 1,
        "name": "مداعبة خفيفة (Banter)",
        "tone": "مزاح لطيف ومداعبة بريئة وفكاهية بين أصدقاء",
        "guidance": "طقطقة خفيفة ومرحة جداً، صفر تجريح أو نكد، تشبيه بسيط لطيف يرسم ابتسامة.",
        "shame_tag": "مزوح"
    },
    2: {
        "level": 2,
        "name": "سخرية واضحة (Call-out)",
        "tone": "تهكم فكاهي واستقعاد كوميدي ساخر",
        "guidance": "سخرية كوميدية مضحكة من تصريفات الضحية وتناقضاته، كشف الأعذار بأسلوب يضحك الجميع بدون فظاظة.",
        "shame_tag": "مستقعد"
    },
    3: {
        "level": 3,
        "name": "قصف جبهة ذكي (Razor Comedy)",
        "tone": "كوميديا ذكية وقصف جبهة يفطس ضحك",
        "guidance": "ذبة ذكية متقنة تستدعي سوابقه أو حركته في الفويس بتشبيه غير متوقع يفجر الضحك بالسيرفر.",
        "shame_tag": "سوابق"
    },
    4: {
        "level": 4,
        "name": "جلد ثقيل وحارق (Savage Roast)",
        "tone": "كوميديا ثقيلة وتشبيهات قوية تفجر السيرفر ضحك",
        "guidance": "طقطقة كوميدية عالية التركيز، إحراج ساخر مرح يفضح التناقضات بتشبيهات ساخرة تجعل الضحية نفسه يضحك.",
        "shame_tag": "مجلود"
    },
    5: {
        "level": 5,
        "name": "قصف نووي مدمر (Nuclear Obliteration)",
        "tone": "ذبة أسطورية خارقة تفطس السيرفر من الضحك",
        "guidance": "ذروة الإبداع الكوميدي الساخر، تشبيه تاريخي عجيب ومفاجئ يخلد في ذاكرة السيرفر كأقوى نكتة بدون أي نفسية أو تهاوش.",
        "shame_tag": "إبادة نووية"
    }
}


def get_intensity_instruction(level: int = 3) -> str:
    """إرجاع تعليمات مستوى الشدة المحكوم بدقة بين 1 و 5."""
    lvl = max(1, min(5, int(level)))
    cfg = INTENSITY_CONFIG[lvl]
    return f"[{cfg['name']} - المستوى {lvl}]: {cfg['guidance']} (الوسم: {cfg['shame_tag']})"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Anti-Repetition Mechanism
# ──────────────────────────────────────────────────────────────────────────────

def format_anti_repetition_prompt(recent_roasts: Optional[list[str]]) -> str:
    """
    تحويل قائمة الذبات السابقة إلى قيود نفي قطعية تمنع Gemini من تكرار
    نفس القفلات أو التشبيهات أو الأفكار.
    """
    if not recent_roasts:
        return ""

    valid_roasts = [r.strip() for r in recent_roasts if r and r.strip()]
    if not valid_roasts:
        return ""

    bullets = "\n".join(f"  • \"{r}\"" for r in valid_roasts[-5:])
    return (
        "⛔ قائمة الذبات السابقة المحظور تكرارها نهائياً (ANTI-REPETITION NEGATIVE GUARDRAILS):\n"
        f"{bullets}\n"
        "التعليمات:\n"
        "1. يحظر تماماً استخدام نفس الأفكار أو التشبيهات أو القفلات السابقة أعلاه.\n"
        "2. يحظر البدء بنفس الكلمات الافتتاحية السابقة.\n"
        "3. ابتكر زاوية جديدة غير مكررة واصنع قصفاً طازجاً ومختلفاً تماماً."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. DialectSynthesisEngine & Interfaces (Contract 3)
# ──────────────────────────────────────────────────────────────────────────────

class DialectSynthesisEngine:
    """
    محرك توليد وتنسيق اللهجات السعودية الأصيلة.
    يطبق متطلبات PROJECT.md:
    - DIALECTS = ['default', 'riyadh', 'jeddah', 'qassim']
    - get_dialect_prompt(dialect_id, intensity, context, recent_roasts) -> tuple[str, str]
    - generate_comparative(target_name, dossier_context) -> dict[str, str]
    """

    DIALECTS = ["default", "riyadh", "jeddah", "qassim"]

    def __init__(self, ai_service_func=None):
        self.ai_service = ai_service_func or generate_content_ai

    def get_dialect_prompt(
        self,
        dialect_id: str = "default",
        intensity: int = 3,
        context: Optional[dict] = None,
        recent_roasts: Optional[list[str]] = None
    ) -> tuple[str, str]:
        """
        توليد زوج (system_instruction, user_prompt) متكامل يجمع بين
        اللهجة، قيود المنع الصارمة، مستوى الشدة، ومنع التكرار.
        """
        d_key = dialect_id if dialect_id in DIALECTS else "default"
        dialect_meta = DIALECTS[d_key]
        intensity_text = get_intensity_instruction(intensity)
        anti_rep = format_anti_repetition_prompt(recent_roasts)

        system_instruction = (
            f"أنت مستر ذبات 3.0، خبير اللهجات السعودية والكوميديا اللاذعة.\n"
            f"اللهجة المعتمدة حصراً: {dialect_meta['name']} ({dialect_meta['region']}).\n"
            f"{dialect_meta['instructions']}\n\n"
            f"{NEGATIVE_CONSTRAINTS}\n\n"
            f"مستوى القوة المطلوب:\n{intensity_text}\n"
        )

        ctx_str = ""
        if context:
            ctx_parts = []
            for k, v in context.items():
                if v:
                    ctx_parts.append(f"- {k}: {v}")
            if ctx_parts:
                ctx_str = "سياق وبيانات الضحية:\n" + "\n".join(ctx_parts) + "\n"

        user_prompt = (
            f"{ctx_str}"
            f"{anti_rep}\n"
            "المطلوب: كتابة ذبة حارقة بسطرين بالكثير، أصيلة باللهجة المحددة وتلتزم بجميع قواعد المنع بدون أي مقدمات."
        ).strip()

        return system_instruction, user_prompt

    async def generate_comparative(
        self,
        target_name: str,
        dossier_context: str
    ) -> dict[str, str]:
        """
        توليد مقارنة فورية بين الـ 4 لهجات في نفس الوقت لنفس الشخص والموضوع
        لصالح Web Deck Simulator.
        ترجع قاموساً يحتوي على المفاتيح: default, riyadh, jeddah, qassim.
        """
        prompt = get_comparative_prompt(topic=dossier_context, member_name=target_name)
        try:
            resp = await self.ai_service(contents=prompt)
            raw_text = resp.text if hasattr(resp, "text") else str(resp)
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            data = json.loads(cleaned)

            result = {}
            for d in self.DIALECTS:
                val = data.get(d)
                if isinstance(val, str) and len(val.strip()) > 3:
                    result[d] = val.strip()
                else:
                    result[d] = self._get_fallback_roast(d, target_name, dossier_context)
            return result
        except Exception as e:
            logger.warning("generate_comparative failed via AI (%s), invoking authentic fallbacks", e)
            return {
                d: self._get_fallback_roast(d, target_name, dossier_context)
                for d in self.DIALECTS
            }

    def _get_fallback_roast(self, dialect_key: str, member_name: str, topic: str) -> str:
        """توليد ذبة احتياطية أصيلة ومضمونة لكل لهجة عند تعذر استجابة الذكاء الاصطناعي."""
        fallbacks = {
            "default": f"يا رجال وش وضعك يا {member_name} تسوقها على موضوع '{topic}'؟ وضعك مزري وكيسك كبير ودرملها أحسن لك!",
            "riyadh": f"ياخي اركد يا {member_name} مهوب كذا تسوق أُمها بموضوع '{topic}'! مالك لوا وخابرك منتهي ما عندك أحد.",
            "jeddah": f"يا واد إيش الهرجة دي يا {member_name}؟ دحين سيبك من موضوع '{topic}' وبلاش تفلم علينا وروقنا يا بويا!",
            "qassim": f"وش نوحك تسذا يا {member_name} بموضوع '{topic}'؟ مير اركد يا مال الغنيمة وعلك الصلاح ترا ما عندك ما عند جدتي وطس بس!"
        }
        return fallbacks.get(dialect_key, fallbacks["default"])


# ──────────────────────────────────────────────────────────────────────────────
# 6. Backward-Compatibility Standalone Functions
# ──────────────────────────────────────────────────────────────────────────────

def get_dialect_prompt(dialect_key: str = "default") -> str:
    """
    إرجاع تعليمات اللهجة المختارة أو الافتراضية مع قيود المنع الصارمة.
    متوافق كلياً مع الاستدعاءات الحالية في main.py و web_dashboard.py.
    """
    dialect = DIALECTS.get(dialect_key, DIALECTS["default"])
    return f"{dialect['instructions']}\n{NEGATIVE_CONSTRAINTS}"


def get_comparative_prompt(topic: str, member_name: str = "الضحية") -> str:
    """
    توليد برومت للمقارنة الفورية بين اللهجات الأربع.
    """
    return f"""أنت مستر ذبات، خبير اللهجات السعودية والكوميديا والجلد الساخر.
المطلوب صياغة 4 ذبات مختلفة لنفس الموضوع ولنفس الشخص ({member_name})، كل ذبة بإحدى اللهجات الأربع بدقة وأصالة تامة.

الموضوع: {topic}

اللهجات المطلوبة:
1. default (عامية سعودية معاصرة ومفهومة: تسوقها، يا رجال، منتهي، كيس كبير، درملها)
2. riyadh (لهجة أهل الرياض / نجدية قوية ببرود وسخرية: مهوب، اركد، تسوق أمها، مالك لوا، وش تبي)
3. jeddah (لهجة أهل جدة / حجازية خفيفة دم وسريعة: يا واد، إيش الهرجة، سيبك منه، يا بويا، دحين)
4. qassim (لهجة قصيمية طريفة ونصوحة تجلد بالصميم: وش نوحك، مير، تسذا، بوه، يا مال الغنيمة)

{NEGATIVE_CONSTRAINTS}

الرد يجب أن يكون بصيغة JSON فقط بهذا الشكل بالضبط بدون أي نصوص أخرى:
{{
  "default": "الذبة بالعامية هنا...",
  "riyadh": "الذبة النجدية هنا...",
  "jeddah": "الذبة الحجازية هنا...",
  "qassim": "الذبة القصيمية هنا..."
}}
"""


# Singleton engine instance exported for system-wide injection
dialect_engine = DialectSynthesisEngine()
