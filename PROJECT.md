# Project: Mr. Roast Reimagining

## Architecture Overview
Mr. Roast 3.0 is an autonomous Discord community intelligence platform and editorial-grade web management command center.
The architecture enforces strict decoupling between Discord Gateway event processing, an aiohttp web server, an atomic persistence state layer, a deep Gemini AI reasoning engine with Saudi dialect synthesis, and an in-browser cybernetic command deck with Web Audio synthesis.

```
+-----------------------------------------------------------------------------------+
|                               Mr. Roast 3.0 Core                                  |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  +--------------------+     +---------------------+     +----------------------+  |
|  |    Discord Bot     |     |   aiohttp Web Deck  |     |   E2E Test Suite     |  |
|  |   (Async Gateway)  |     | (0.0.0.0:$PORT)     |     |   (Opaque-Box T1-T5) |  |
|  | - Voice Intel      |     | - Telemetry Polling |     +----------------------+  |
|  | - Commands         |     | - Court & Battles   |                               |
|  | - Courtroom Views  |     | - Cyber CLI / Audio |                               |
|  +---------+----------+     +----------+----------+                               |
|            |                           |                                          |
|            +-------------+-------------+                                          |
|                          |                                                        |
|                          v                                                        |
|             +-------------------------+                                           |
|             |  Atomic State Manager   |                                           |
|             |  (DossierVault / Locks) |                                           |
|             |  - User Dossiers        |                                           |
|             |  - Grudge Scale (1-5)   |                                           |
|             |  - Active Trials/Arena  |                                           |
|             +------------+------------+                                           |
|                          |                                                        |
|                          v                                                        |
|             +-------------------------+                                           |
|             |  Gemini AI Engine &     |                                           |
|             |  Saudi Dialect Engine   |                                           |
|             |  - Thinking Level HIGH  |                                           |
|             |  - 4 Authentic Dialects |                                           |
|             |  - Anti-Repetition Cache|                                           |
|             +-------------------------+                                           |
+-----------------------------------------------------------------------------------+
```

## Feature Inventory
Every feature from `ORIGINAL_REQUEST.md` and the Phase 0 Survey is mapped below:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Decoupled Bot & Web Lifecycle | Independent asynchronous startup, error isolation, graceful degradation on API failures | M1 | R1, Survey 1 |
| 2 | Atomic Persistence Vault | Thread/coroutine-safe atomic file writes (`NamedTemporaryFile` + `os.replace`), zero data loss on restart | M1 | R1, Survey 1 |
| 3 | Clean Runtime Manifests | Fix Procfile (`web: python main.py`), clean nixpacks.toml, add .dockerignore, purge legacy voice audio bloat | M1 | R1, Survey 1 |
| 4 | HTTP Health Check Routes | Expose `GET /health` and `GET /api/health` returning 200 OK with bot readiness telemetry | M1 | R1, Survey 1 |
| 5 | Unified Gemini High Thinking Client | Singleton `google-genai` client, `thinking_level="HIGH"`, exponential backoff with jitter on 429/503 | M2 | R2, Survey 2 |
| 6 | Criminal Dossier & Grudge Scale | Bounded 1-5 integer grudge scale, structured infraction logging (AFK, Rage Quit, Status Fraud) | M2 | R2, Survey 2 |
| 7 | Real-Time Voice State Intelligence | Track VC duration, mute/deafen ratios, presence status contradictions, auto-dossier ingestion | M2 | R2, Survey 2 |
| 8 | Authentic 4-Dialect Synthesis | Default (slang), Riyadh (Najdi sarcasm), Jeddah (Hijazi cadence), Qassim (traditional particles) without stubs | M2 | R2, Survey 2 |
| 9 | Anti-Repetition & Intensity Engine | Strict 1-5 intensity calibration, historical roast negative prompt constraints, fresh lexical rotation | M2 | R2, Survey 2 |
| 10 | Spatial Hierarchy & 60fps Web Deck | Dark cybernetic command center, responsive grids, canvas animation with tab throttling | M3 | R3, Survey 3 |
| 11 | Live Server Courtroom Synchronization | Synchronize Discord `CourtVoteView` with Web Deck live voting bar, countdown clock, gavel sounds | M3 | R3, Survey 3 |
| 12 | 1v1 Roast Arena & Crowd Scoring | Member dropdown selection, multi-round battle adjudication, crowd voting meter, battle hit acoustics | M3 | R3, Survey 3 |
| 13 | Holographic Shame Cards Suite | 3D tilt interaction, dynamic crime tags, shame tier levels (Bronze to Cybernetic SSS), Canvas PNG/clipboard copy | M3 | R3, Survey 3 |
| 14 | 4-Way Dialect Simulator Deck | Member targeting from dossier, live 4-way comparative generation, one-click Discord deployment and copy | M3 | R3, Survey 3 |
| 15 | Cyber CLI Terminal | In-browser command interface with Tab auto-complete, command history buffer (Up/Down), syntax feedback | M3 | R3, Survey 3 |
| 16 | Web Audio Synthesizer Suite | Native Web Audio API sounds: typing clicks, alarm sirens, battle impacts, gavel strikes, button triggers | M3 | R3, Survey 3 |
| 17 | Hermetic Automated Test Suite | Unit tests, API integration tests, atomic persistence stress tests, simulated Gemini fallbacks in `tests/` | M4 & E2E | R4, Survey 3 |
| 18 | Render Deployment Verification | Verify zero-downtime deployment on `redesign` branch, passing live HTTP health checks | M4 | R4, Survey 1 |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | First-Principles Core & Atomic Data Layer | Decoupled startup, atomic StateManager/DossierVault, /health route, clean Procfile/manifests, purge audio bloat | none | DONE |
| M2 | Contextual Intelligence & Saudi Dialect Engine | Unified Gemini Flash client with High Thinking & backoff, Voice Intelligence, 4-Dialect engine, 1-5 Grudge scale | M1 | DONE |
| M3 | Editorial-Grade Web Command Center & Audio Suite | Courtroom live sync, 1v1 Arena, Holographic Shame Cards, 4-Way Dialect Simulator, Cyber CLI, Web Audio synth | M1, M2 | DONE |
| M4 | Final Milestone: E2E Verification & Adversarial Hardening | Pass 100% Tiers 1-4 E2E test suite + Tier 5 adversarial coverage hardening + Render deployment readiness | M1, M2, M3, E2E | DONE |

## Parallel Track: E2E Testing Track
- Spawned concurrently with M1.
- Operates autonomously to construct an opaque-box test harness derived from `ORIGINAL_REQUEST.md`.
- Delivers `TEST_INFRA.md` and `TEST_READY.md` covering Tiers 1-4.

## Interface Contracts

### 1. `StateManager` (Core Persistence Contract)
```python
class StateManager:
    async def get_dossier(self, user_id: int) -> dict: ...
    async def update_dossier(self, user_id: int, updates: dict) -> dict: ...
    async def add_infraction(self, user_id: int, crime_type: str, detail: str) -> None: ...
    async def set_grudge_level(self, user_id: int, level: int) -> int: ... # 1-5 bounded
    async def get_all_dossiers(self) -> dict: ...
    async def record_roast(self, user_id: int, username: str, roast_text: str, dialect: str, intensity: int) -> None: ...
    async def get_recent_roasts(self, user_id: int, limit: int = 5) -> list[str]: ...
    async def save_state_atomic(self) -> None: ...
```

### 2. `GeminiService` (AI Pipeline Contract)
```python
class GeminiService:
    async def generate_roast(self, prompt: str, system_instruction: str, context: dict = None) -> str: ...
    async def generate_structured(self, prompt: str, schema: type[BaseModel] | dict) -> dict: ...
    # Built-in exponential backoff with jitter on 429/503
```

### 3. `DialectSynthesisEngine` (Dialect Engine Contract)
```python
class DialectSynthesisEngine:
    DIALECTS = ["default", "riyadh", "jeddah", "qassim"]
    def get_dialect_prompt(self, dialect_id: str, intensity: int, context: dict, recent_roasts: list[str]) -> tuple[str, str]: ...
    async def generate_comparative(self, target_name: str, dossier_context: str) -> dict[str, str]: ...
```

### 4. `TrialManager` & `BattleManager` (Courtroom & Arena Sync Contract)
```python
class TrialManager:
    active_trial: Optional[dict]
    async def start_trial(self, defendant_id: int, defendant_name: str, charge: str) -> dict: ...
    async def cast_vote(self, voter_id: int, choice: str) -> dict: ... # 'guilty' or 'innocent'
    def get_trial_status(self) -> dict: ... # used by /api/stats and CourtVoteView
```

### 5. Web Routes Contract
- `GET /health` -> `{"status": "healthy", "service": "mr-roast", "version": "3.0", "discord_ready": bool, "uptime": float}` (HTTP 200)
- `GET /api/stats` -> Full telemetry including `active_trial`, `voice_intelligence`, `dossiers`, `roast_log`, `current_dialect`
- `POST /api/court/vote` -> `{"trial_id": ..., "vote": "guilty"|"innocent"}`
- `POST /api/battle/judge` -> Multi-round arbitration schema
- `POST /api/dialect/preview` -> 4-way comparative synthesis schema
- `POST /api/shame_card` -> Shame card SVG and tier metadata

## Code Layout
- `main.py`: Decoupled Discord bot runner with resilient background web server launch.
- `web_dashboard.py`: aiohttp web server, REST API endpoints, static assets, and Web Audio synthesis.
- `modules/` (or `core/` & `intelligence/`):
  - `state_manager.py`: Atomic persistence vault and thread-safe data operations.
  - `gemini_client.py`: Resilient Gemini Flash High Thinking client with backoff.
  - `dialects.py`: Saudi dialect synthesis engine (Default, Riyadh, Jeddah, Qassim) with negative constraints.
  - `dossier.py`: Criminal dossier, grudge scale (1-5), and voice intelligence processor.
  - `roast_engine.py`: Courtroom, 1v1 Arena, and Shame card generators.
- `tests/`: Automated test suite (unit tests, API integration tests, persistence stress tests, Gemini fallbacks).
- Root deployment manifests: `Dockerfile`, `Procfile`, `runtime.txt`, `nixpacks.toml`, `.dockerignore`.
