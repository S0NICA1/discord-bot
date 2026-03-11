from config import TONY_PERSONA, GEMINI_TEMPERATURE
import random
import datetime

# Global state to easily get/set variables without circular imports
_current_persona = TONY_PERSONA
_current_temperature = GEMINI_TEMPERATURE

# Dynamic Mood System
_current_mood = ""
_mood_date = ""

# Track interactions per user ID to act as "تمون" logic
_friendship_levels = {}

def track_interaction(user_id: int):
    if user_id not in _friendship_levels:
        _friendship_levels[user_id] = 1
    else:
        _friendship_levels[user_id] += 1

def get_friendship_status(user_id: int) -> str:
    count = _friendship_levels.get(user_id, 0)
    if count == 0:
        return "هذا شخص جديد ما تعرفه، عامله برسمية شوي أو طقطق بخفة."
    elif count < 5:
        return "تعرفه شوية، بدأت تمون عليه بس خلك حذر."
    elif count < 20:
        return "هذا خويك، تمون عليه وتطقطق براحتك."
    else:
        return "هذا أعز أخوياك السبايك! ادعس عليه بالطقطقة ولا ترحمه أبداً، تمونون على بعض ألف."

MOODS = [
    "اليوم أنت مروق ومبسوط، ردودك فيها تفاؤل وضحك كثير وتسوقها مع الشباب.",
    "اليوم أنت 'نفسية' ومطنقر، ردودك تسليكية وقصيرة وفيها طقطقة ثقيلة لأنك طفشان.",
    "اليوم أنت تحاول تصير حكيم وتتفلسف بزيادة في أي موضوع ينفتح، وتجيب أمثلة شيبان قديمة.",
    "اليوم أنت مستعجل وحقاني، تعطيهم الزبدة بدون لف ودوران.",
    "اليوم أنت محقق كونان، تشك في كل كلمة تنقال وتدور وراهم زلات."
]

def get_daily_mood():
    global _current_mood, _mood_date
    today = datetime.date.today().isoformat()
    if today != _mood_date:
        _current_mood = random.choice(MOODS)
        _mood_date = today
    return _current_mood

def get_persona():
    referee_rules = "\n[قوانين إضافية: إذا طلب منك شخصين تحكم بينهم، افصل بينهم بطريقة ساخرة بدون ما تحل المشكلة بجدية. تراك حكم فاشل.]"
    afk_rules = "\n[قوانين إضافية: إذا لاحظت أو انذكر لك إن فيه شخص AFK أو مسوي ميوت، علق عليه وذب عليه بأنه نايم أو خايف.]"
    black_book_rules = "\n[قوانين المستودع السري: إذا سمعت شخص يقول شيء غبي أو مضحك وتقدر تستخدمه ضده مستقبلاً، أضف في نهاية كلامك [SAVE_QUOTE: message] للحفظ.]"
    
    return _current_persona + referee_rules + afk_rules + black_book_rules + f"\n\n[حالتك المزاجية لهذا اليوم حصراً: {get_daily_mood()}]"

def set_persona(new_persona):
    global _current_persona
    _current_persona = new_persona

def get_temperature():
    return _current_temperature

def set_temperature(new_temp):
    global _current_temperature
    _current_temperature = new_temp
