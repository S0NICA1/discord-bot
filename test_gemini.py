import os
import sys
import pytest
from dotenv import load_dotenv


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_GEMINI"),
    reason="Requires live Gemini API key and opt-in"
)
def test_live_gemini_generation():
    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        pytest.skip("GEMINI_API_KEY is not set")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_api_key)
    model_name = "gemini-flash-latest"
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
        assert res.text
    except Exception:
        cfg_fb = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        )
        res = client.models.generate_content(
            model=model_name,
            contents="من هو مؤسس المملكة العربية السعودية؟ أجب بإيجاز.",
            config=cfg_fb
        )
        assert res.text


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_live_gemini_generation()
