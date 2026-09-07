"""
tests/test_dialect_engine.py - Comprehensive Unit Tests for Authentic Saudi Dialect Engine
Covers:
1. DIALECTS catalog completeness (all 4 dialects, metadata, metrics, core lexicons)
2. Strict NEGATIVE_CONSTRAINTS (anti-Egyptian, anti-Levantine, anti-Maghrebi, anti-Fusha)
3. 1-5 Intensity calibration & shame tags
4. Anti-repetition prompt formatting & bounding
5. DialectSynthesisEngine.get_dialect_prompt contract
6. 4-Way comparative generation with live/mocked AI
7. 4-Way comparative fallback generation when AI is unavailable
8. Backward-compatible standalone module functions
"""

from unittest.mock import AsyncMock, patch

import pytest

from modules.dialects import (
    DIALECTS,
    INTENSITY_CONFIG,
    NEGATIVE_CONSTRAINTS,
    DialectSynthesisEngine,
    dialect_engine,
    format_anti_repetition_prompt,
    get_comparative_prompt,
    get_dialect_prompt,
    get_intensity_instruction,
)


def test_dialects_catalog_structure():
    """Verify all 4 required Saudi dialects exist with comprehensive linguistic metadata."""
    required_keys = ["default", "riyadh", "jeddah", "qassim"]
    for key in required_keys:
        assert key in DIALECTS, f"Missing dialect key: {key}"
        d = DIALECTS[key]
        assert "name" in d and len(d["name"]) > 0
        assert "region" in d and len(d["region"]) > 0
        assert "icon" in d
        assert "badge" in d
        assert "instructions" in d and len(d["instructions"]) > 20
        assert "catchphrases" in d and len(d["catchphrases"]) >= 3
        assert "metrics" in d
        assert "vibe" in d and len(d["vibe"]) > 0
        assert "core_lexicon" in d and len(d["core_lexicon"]) >= 10
        assert "phonology_rules" in d and len(d["phonology_rules"]) > 0
        assert "sample_burns" in d and len(d["sample_burns"]) >= 2

        # Verify metrics dimensions
        metrics = d["metrics"]
        for m in ["sharpness", "speed", "authenticity", "humor"]:
            assert m in metrics
            assert 0 <= metrics[m] <= 100


def test_negative_constraints_content():
    """Verify NEGATIVE_CONSTRAINTS strictly outlaws Egyptian, Levantine, Maghrebi, and fake Fusha."""
    forbidden_terms = [
        "إيه دا", "ازيك", "عايز", "كده", "بتاع",  # Egyptian
        "شو", "عم بحكي", "بدي", "بديش", "كتير", "يا زلمة",  # Levantine
        "واش", "بزاف", "برشا", "مزيان",  # Maghrebi
        "أيها", "لماذا", "تباً لك", "يا هذا",  # Fusha
        "بالتأكيد", "إليك الذبة"  # AI boilerplate
    ]
    for term in forbidden_terms:
        assert term in NEGATIVE_CONSTRAINTS, f"Missing negative constraint for term: {term}"


def test_intensity_levels_calibration():
    """Verify strict 1-5 intensity calibration and corresponding community shame tags."""
    expected_tags = {
        1: "مزوح",
        2: "مستقعد",
        3: "سوابق",
        4: "مجلود",
        5: "إبادة نووية"
    }
    for level, tag in expected_tags.items():
        assert level in INTENSITY_CONFIG
        cfg = INTENSITY_CONFIG[level]
        assert cfg["shame_tag"] == tag
        assert "name" in cfg
        assert "guidance" in cfg

        instr = get_intensity_instruction(level)
        assert tag in instr
        assert f"المستوى {level}" in instr

    # Verify bounding logic (clamps <1 to 1 and >5 to 5)
    assert get_intensity_instruction(0) == get_intensity_instruction(1)
    assert get_intensity_instruction(99) == get_intensity_instruction(5)


def test_anti_repetition_prompt_formatting():
    """Verify format_anti_repetition_prompt converts historical roasts into strict negative blocks."""
    # Empty inputs
    assert format_anti_repetition_prompt(None) == ""
    assert format_anti_repetition_prompt([]) == ""
    assert format_anti_repetition_prompt(["   ", ""]) == ""

    # Valid inputs
    roasts = [
        "يا رجال وش وضعك تسوقها؟",
        "مسوي كاري والرانك ضايع",
        "كيس كبير وفكنا بس"
    ]
    block = format_anti_repetition_prompt(roasts)
    assert "ANTI-REPETITION" in block
    for r in roasts:
        assert r in block

    # Max 5 limitation
    ten_roasts = [f"ذبة رقم {i}" for i in range(10)]
    bounded_block = format_anti_repetition_prompt(ten_roasts)
    assert "ذبة رقم 9" in bounded_block
    assert "ذبة رقم 5" in bounded_block
    assert "ذبة رقم 0" not in bounded_block  # Older than last 5


def test_dialect_engine_get_dialect_prompt():
    """Verify DialectSynthesisEngine.get_dialect_prompt satisfies Contract 3."""
    engine = DialectSynthesisEngine()
    sys_inst, user_prompt = engine.get_dialect_prompt(
        dialect_id="riyadh",
        intensity=4,
        context={"جريمة": "هروب من الرانك", "مدة": "ساعتين"},
        recent_roasts=["ياخي اركد شوي"]
    )

    # System instruction verification
    assert "لهجة الرياض / نجدية" in sys_inst
    assert NEGATIVE_CONSTRAINTS in sys_inst
    assert "مجلود" in sys_inst
    assert "المستوى 4" in sys_inst

    # User prompt verification
    assert "هروب من الرانك" in user_prompt
    assert "ساعتين" in user_prompt
    assert "ياخي اركد شوي" in user_prompt
    assert "ANTI-REPETITION" in user_prompt


@pytest.mark.asyncio
async def test_dialect_engine_generate_comparative():
    """Verify generate_comparative generates all 4 Saudi dialect variations."""
    engine = DialectSynthesisEngine()
    result = await engine.generate_comparative(
        target_name="سعد",
        dossier_context="مسوي ميوت ويلعب روبلوكس"
    )

    assert isinstance(result, dict)
    for d in ["default", "riyadh", "jeddah", "qassim"]:
        assert d in result
        assert isinstance(result[d], str)
        assert len(result[d].strip()) > 5


@pytest.mark.asyncio
async def test_dialect_engine_generate_comparative_fallback():
    """Verify generate_comparative gracefully returns authentic Saudi fallbacks if AI fails."""
    broken_ai = AsyncMock(side_effect=RuntimeError("Google GenAI Unreachable"))
    engine = DialectSynthesisEngine(ai_service_func=broken_ai)

    result = await engine.generate_comparative(
        target_name="خالد",
        dossier_context="النكبة المستمرة"
    )

    assert isinstance(result, dict)
    assert "خالد" in result["default"]
    assert "خالد" in result["riyadh"]
    assert "خالد" in result["jeddah"]
    assert "خالد" in result["qassim"]
    assert "تسوقها" in result["default"]
    assert "مهوب" in result["riyadh"]
    assert "يا واد" in result["jeddah"]
    assert "تسذا" in result["qassim"]


def test_backward_compatible_functions():
    """Verify top-level module functions remain backward compatible."""
    # get_dialect_prompt returns str with negative constraints
    prompt = get_dialect_prompt("jeddah")
    assert isinstance(prompt, str)
    assert "حجازية" in prompt
    assert NEGATIVE_CONSTRAINTS in prompt

    # get_comparative_prompt returns valid prompt template
    comp_prompt = get_comparative_prompt(topic="الهروب", member_name="فيصل")
    assert "فيصل" in comp_prompt
    assert "الهروب" in comp_prompt
    assert "default" in comp_prompt
    assert "riyadh" in comp_prompt
    assert "jeddah" in comp_prompt
    assert "qassim" in comp_prompt


def test_anti_hostility_and_comedy_first_constraints():
    """Verify negative constraints forbid toxic/hostile arguing phrases and enforce comedy."""
    banned_toxic = ["خلك ساكت", "انثبر", "وضعك مزري", "النفسية"]
    for word in banned_toxic:
        assert word in NEGATIVE_CONSTRAINTS

    for dialect_key in ["default", "riyadh", "jeddah", "qassim"]:
        d = DIALECTS[dialect_key]
        assert d["metrics"]["humor"] >= 90
        assert "ضحك" in d["instructions"] or "فكاهية" in d["instructions"] or "كوميدي" in d["instructions"]

