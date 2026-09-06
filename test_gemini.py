import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

model_name = "gemini-flash-latest"
print(f"Testing {model_name}...")

try:
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    res = client.models.generate_content(
        model=model_name,
        contents="من هو مؤسس المملكة العربية السعودية؟ أجب بإيجاز.",
        config=cfg
    )
    print("SUCCESS (with Google Search & High Thinking):")
    print(res.text)
except Exception as e:
    print(f"Search tool failed ({e}), testing fallback without search...")
    cfg_fb = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
    )
    res = client.models.generate_content(
        model=model_name,
        contents="من هو مؤسس المملكة العربية السعودية؟ أجب بإيجاز.",
        config=cfg_fb
    )
    print("SUCCESS (Fallback with High Thinking):")
    print(res.text)

