# Test Infrastructure & Methodology Specification (Mr. Roast 3.0)

## 1. Test Architecture Overview

The Mr. Roast 3.0 automated verification suite is an opaque-box, hermetic test harness designed to guarantee platform stability, dialect authenticity, REST API contracts, and atomic persistence with **zero external network dependencies** and **zero runtime flakiness**.

```
+-------------------------------------------------------------------------------+
|                            Mr. Roast 3.0 Test Harness                         |
+-------------------------------------------------------------------------------+
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  |                     Global Autouse Mock Engine                          |  |
|  |  (tests/conftest.py - patches google.genai.Client & Discord primitives) |  |
|  +-------------------------------------------------------------------------+  |
|         |                                 |                         |         |
|         v                                 v                         v         |
|  +---------------+               +-----------------+       +---------------+  |
|  |  Mock GenAI   |               |  Mock Discord   |       | Atomic State  |  |
|  |  Thinking AI  |               |  Gateway / UI   |       | Temp Vault    |  |
|  +---------------+               +-----------------+       +---------------+  |
|         |                                 |                         |         |
|         +---------------------------------+-------------------------+         |
|                                           |                                   |
|                                           v                                   |
|  +-------------------------------------------------------------------------+  |
|  |                         4-Tier Test Suites                              |  |
|  |  - Tier 1: Feature Coverage (tests/test_tier1_features.py - 65 tests)   |  |
|  |  - Tier 2: Boundary & Corner (tests/test_tier2_boundaries.py - 25 tests)|  |
|  |  - Tier 3: Interactions (tests/test_tier3_interactions.py - 8 tests)    |  |
|  |  - Tier 4: Workloads & Load (tests/test_tier4_workloads.py - 5 tests)   |  |
|  |  - Live Opt-In Suite (test_gemini.py - 1 test, conditionally skipped)   |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
```

---

## 2. 4-Tier Testing Methodology

### Tier 1: Feature Coverage (>=5 Tests Per Feature)
Validates primary behavior and interface contracts for all bot dispatchers and web routes:
1. **Bot Slash Command `/roast`**: Default generation, intensity calibration (1-5), dialect override, custom topic incorporation, AI timeout fallback (5 tests).
2. **Bot Slash Command `/court`**: Indictment generation, CourtVoteView button creation, jury voting, vote switching, guilty sentencing vs acquittal (5 tests).
3. **Bot Slash Command `/shamecard`**: SVG generation, dialect badge styling, criminal history inclusion, fallback roast, statistics calibration (5 tests).
4. **Bot Slash Command `/battle`**: 1v1 arena announcement, default topic handling, commentator intro, battle adjudication, tie fallback (5 tests).
5. **Bot Slash Command `/dialect`**: Riyadh (Najdi), Jeddah (Hijazi), Qassim, Default switching, state persistence trigger (5 tests).
6. **Web API Route `GET /health` & `GET /api/health`**: HTTP 200 verification, service telemetry, discord readiness status, uptime tracking (5 tests).
7. **Web API Route `GET /api/stats`**: Full telemetry inspection, voice members, shame board ranking, dialect radar catalog, 24-hour activity grid (5 tests).
8. **Web API Route `POST /api/court/start`**: Indictment schema, nonexistent defendant rejection, Discord announcement dispatch, default charge handling, dialect parameter propagation (5 tests).
9. **Web API Route `POST /api/court/vote`**: Guilty voting, innocent voting, invalid choice rejection (HTTP 400), choice/vote alias support, missing parameter rejection (5 tests).
10. **Web API Route `POST /api/battle/judge`**: Two-fighter arbitration, empty roast rejection, numeric score verification, default names fallback, topic propagation (5 tests).
11. **Web API Route `POST /api/shame_card` & `POST /api/shame_card_send`**: SVG markup generation, custom crime reflection, dialect badge styling, unknown member handling, Discord delivery (5 tests).
12. **Web API Route `POST /api/dialect/preview`**: 4-way comparative synthesis, all 4 regional dialects returned, non-empty outputs, Markdown cleanup, error handling (5 tests).
13. **Web API Route `POST /api/cli/execute`**: `help`, `stats`, `dialect <name>`, `protect`/`unprotect`, unrecognized command handling (5 tests).

### Tier 2: Boundary & Corner Cases (>=5 Tests Per Category)
Evaluates extreme conditions, malformed payloads, and fault recovery:
- **Category 1: Empty Payloads**: Empty CLI execution `{}` , whitespace custom roasts, empty free messages, empty battle roasts, empty dossier additions (5 tests).
- **Category 2: Malformed Inputs**: Non-numeric member IDs, invalid dialect names, missing CLI arguments, invalid vote strings (HTTP 400), malformed non-JSON bodies (5 tests).
- **Category 3: Out-of-bounds Grudge Levels**: Negative grudge levels clamped to 1, zero clamped to 1, excessive levels clamped to 5, string numeric coercion, legacy unbounded score normalization (5 tests).
- **Category 4: Missing Parameters**: Missing member_id query parameters, missing targets in targeted roasts, missing vote field, missing dossier content, missing protection member_id (5 tests).
- **Category 5: Unhandled Exceptions & Defensive Recovery**: Targeted roasts for nonexistent users, shame card send to nonexistent users, AI generation exception recovery, StateManager corrupt JSON quarantine, StateManager 0-byte file recovery (5 tests).

### Tier 3: Cross-Feature Interactions
Validates interconnected state and multi-service transaction flows:
- **Dossier Persistence -> Shame Card Generation**: Accumulating criminal records, excuses, and titles via API, then generating a shame card verifying all dossier items appear in the resulting SVG markup (2 tests).
- **Courtroom Indictment -> Voting -> Conviction & Grudge Escalation**: Full Discord courtroom trial lifecycle from `/court` command through jury voting to conviction timeout, dossier crime recording, and sentencing roast generation (2 tests).
- **Voice Intelligence & Contradiction -> Roast Synthesis**: Real-time voice state analysis (deafened/muted) and custom status contradiction detection (e.g., status "نايم" while in voice) injected directly into the Gemini roast prompt (2 tests).
- **Cyber CLI -> Telemetry & Protection Rules**: Executing CLI commands, verifying real-time synchronization in `/api/stats`, and confirming VIP immunity rules protect users from autonomous roasts (2 tests).

### Tier 4: Real-World Workloads & High Concurrency
Tests platform resilience under sustained operational stress:
- **Server Activity Simulation**: Multi-user voice session lifecycles, staggered joins, game activity updates, mute/deafen transitions, disconnect minute accumulation, and 4 AM Saudi daily report generation (2 tests).
- **Multi-Round Battle Flow**: Complete 3-round 1v1 battle matchup with cumulative scoring across rounds and victory determination (1 test).
- **High Concurrency Load**: 40 simultaneous parallel requests across `/api/stats`, `/api/cli/execute`, `/api/dialect/preview`, `/api/shame_card`, and `/api/court/vote`, verifying 100% HTTP 200 with zero race conditions (1 test).
- **Sustained State Mutation & Churn**: 20 rapid successive roast generations, verifying roast logs stay bounded at 100 entries, user counters increment, and no temporary files leak to disk (1 test).

---

## 3. Test Suite Inventory

| File Path | Tier | Test Count | Description |
| :--- | :--- | :---: | :--- |
| `tests/test_tier1_features.py` | Tier 1 | 65 | Comprehensive feature coverage for all 5 bot dispatchers & 8 web API routes. |
| `tests/test_tier2_boundaries.py` | Tier 2 | 25 | Corner cases: empty payloads, malformed inputs, grudge bounds, missing fields, crash recovery. |
| `tests/test_tier3_interactions.py` | Tier 3 | 8 | Cross-feature flows: dossier->shame card, court->voting->grudge, voice contradiction. |
| `tests/test_tier4_workloads.py` | Tier 4 | 5 | Real-world stress: voice lifecycles, 3-round battles, 40-request concurrency, state churn. |
| `test_gemini.py` | Integration | 1 | Live Gemini test, safely wrapped with `@pytest.mark.skipif(not os.getenv("RUN_LIVE_GEMINI"))`. |
| **Total Test Suite** | **All** | **113** | **112 passing, 1 opt-in skipped, 0 failing.** |

---

## 4. Hermetic Mock Engine (`tests/conftest.py`)

1. **Deterministic AI Synthesis**:
   - `determine_mock_ai_output` analyzes incoming prompt contents to dynamically produce schema-accurate JSON responses (Court indictments, Battle arbitration, 4-Way Dialect previews, AI Reports) or authentic Saudi dialect roasts.
   - Completely replaces `google.genai.Client` and `client.aio.models.generate_content` across all modules.
   - Zero external HTTP requests, zero quota consumption, zero 429 errors.

2. **Discord Gateway & UI Emulation**:
   - `MockMember`, `MockTextChannel`, `MockVoiceChannel`, `MockGuild`, `MockInteraction`, `MockInteractionResponse`, `MockInteractionFollowup`.
   - Captures all outbound channel messages, embeds, files, and button interactions for exact assertions.

3. **Atomic State Isolation**:
   - Every test execution receives a fresh temporary data directory (`tmp_path`) for `state.json` and `bot_data.json`.
   - Dual-lock synchronization (`asyncio.Lock` + `threading.Lock`) protects all state mutations.

4. **Live Test Guarding**:
   - `test_gemini.py` is guarded with `@pytest.mark.skipif(not os.getenv("RUN_LIVE_GEMINI"), reason="Requires live Gemini API key and opt-in")`.
   - Standard test execution skips live calls, ensuring CI/CD passes without network access.

---

## 5. Verification Commands

To execute the complete automated test suite locally:

```bash
# Standard hermetic test execution (100% offline, 0 API keys required)
python -m pytest tests/ test_gemini.py -v

# Quick execution with summary output
python -m pytest tests/ test_gemini.py -q
```

**Expected Result**:
- `112 passed, 1 skipped in ~7.5 seconds`
- Exit code: `0`
