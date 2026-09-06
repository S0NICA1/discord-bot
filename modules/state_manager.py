"""
modules/state_manager.py - Mr. Roast 3.0 Atomic State Manager
Provides thread-safe and coroutine-safe atomic persistence, schema unification,
automatic migration from legacy JSON files, and defensive error recovery.
"""
import os
import sys
import json
import time
import shutil
import random
import asyncio
import logging
import tempfile
import threading
import datetime
from typing import Any, Optional

logger = logging.getLogger("mr_roast.state_manager")

GRUDGE_TITLES = {
    1: "مواطن مسالم (تحت المراقبة العادية)",
    2: "مثير للشبهات (سوابق ونكبات خفيفة)",
    3: "مطلوب أمنياً في قضايا تخريب وتهرب",
    4: "عدو الشعب الأول ومجرم رانكات محترف",
    5: "مجرم حرب سيرفرية (هدف تصفية نووية قصوى)"
}


class StateManager:
    """
    Centralized persistence and state vault for Mr. Roast 3.0.
    Enforces atomic disk writes via tempfile.NamedTemporaryFile + os.replace,
    dual-lock concurrency control (asyncio.Lock + threading.Lock),
    and zero-data-loss legacy migration.
    """

    DEFAULT_STATE = {
        "_version": 1,
        "last_saved": 0.0,
        "dossiers": {},
        "metrics": {
            "roast_log": [],
            "roast_count_per_user": {},
            "daily_roast_counts": {},
            "hourly_vc_activity": [0] * 24,
            "game_popularity": {},
            "grudge_levels": {},
            "current_dialect": "default",
            "protected_users": []
        }
    }

    def __init__(self, data_dir: str = "data", state_filename: str = "state.json", legacy_dir: Optional[str] = None):
        self.data_dir = data_dir
        self.filepath = os.path.join(data_dir, state_filename)
        self.bak_path = self.filepath + ".bak"
        self.legacy_dir = legacy_dir if legacy_dir is not None else ("" if data_dir == "data" else data_dir)

        self._async_lock = asyncio.Lock()
        self._thread_lock = threading.RLock()
        self._disk_lock = threading.Lock()

        os.makedirs(self.data_dir, exist_ok=True)
        self._state = json.loads(json.dumps(self.DEFAULT_STATE))
        self._load_state()

    def _init_default_dossier_unlocked(self, user_id: int | str) -> dict:
        """Constructs default user dossier schema without locking."""
        uid = str(user_id)
        numeric_id = int(uid) if str(uid).lstrip("-").isdigit() else 0
        return {
            "user_id": numeric_id,
            "username": f"User_{uid}",
            "display_name": f"User_{uid}",
            "grudge_level": 1,
            "grudge_points": 0,
            "titles": [],
            "excuses": [],
            "embarrassing_moments": [],
            "game_notes": [],
            "crimes": [],
            "infractions": [],
            "roast_history": [],
            "voice_stats": {
                "total_vc_minutes": 0,
                "total_unmuted_seconds": 0,
                "mute_toggle_count": 0,
                "choke_count": 0,
                "last_seen_vc": 0.0
            },
            "updated_at": time.time()
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Defensive Loading & Recovery
    # ──────────────────────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        """Loads state with zero-byte detection, quarantine of corrupt files, and .bak restoration."""
        with self._thread_lock:
            if not os.path.exists(self.filepath):
                self._check_and_migrate_legacy()
                return

            size = os.path.getsize(self.filepath)
            if size == 0:
                logger.warning("Zero-byte state file detected at %s", self.filepath)
                if os.path.exists(self.bak_path) and os.path.getsize(self.bak_path) > 0:
                    try:
                        with open(self.bak_path, "r", encoding="utf-8") as f:
                            self._state = json.load(f)
                        logger.info("Successfully recovered state from %s", self.bak_path)
                        return
                    except Exception as e:
                        logger.error("Failed to recover from backup: %s", e)
                self._check_and_migrate_legacy()
                return

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error("Corrupted state file detected: %s", e)
                quarantine_path = f"{self.filepath}.corrupt.{int(time.time())}"
                try:
                    shutil.copy2(self.filepath, quarantine_path)
                    logger.warning("Corrupt state quarantined to %s", quarantine_path)
                except Exception as ce:
                    logger.error("Failed to quarantine corrupt file: %s", ce)

                if os.path.exists(self.bak_path) and os.path.getsize(self.bak_path) > 0:
                    try:
                        with open(self.bak_path, "r", encoding="utf-8") as f:
                            self._state = json.load(f)
                        logger.info("Successfully recovered state from backup %s", self.bak_path)
                        return
                    except Exception as be:
                        logger.error("Failed to load backup: %s", be)

                self._state = json.loads(json.dumps(self.DEFAULT_STATE))

    # ──────────────────────────────────────────────────────────────────────────
    # Legacy Migration
    # ──────────────────────────────────────────────────────────────────────────

    def _check_and_migrate_legacy(self) -> None:
        """Automatically imports legacy user_dossiers.json and bot_data.json without data loss."""
        legacy_dossiers_path = os.path.join(self.legacy_dir, "user_dossiers.json") if self.legacy_dir else "user_dossiers.json"
        legacy_bot_data_path = os.path.join(self.legacy_dir, "bot_data.json") if self.legacy_dir else "bot_data.json"

        has_dossiers = os.path.exists(legacy_dossiers_path) and os.path.getsize(legacy_dossiers_path) > 0
        has_bot_data = os.path.exists(legacy_bot_data_path) and os.path.getsize(legacy_bot_data_path) > 0

        if not has_dossiers and not has_bot_data:
            return

        logger.info("Migrating legacy data stores into unified StateManager...")
        legacy_dos = {}
        legacy_bot = {}

        if has_dossiers:
            try:
                with open(legacy_dossiers_path, "r", encoding="utf-8") as f:
                    legacy_dos = json.load(f)
            except Exception as e:
                logger.error("Could not read legacy dossiers: %s", e)

        if has_bot_data:
            try:
                with open(legacy_bot_data_path, "r", encoding="utf-8") as f:
                    legacy_bot = json.load(f)
            except Exception as e:
                logger.error("Could not read legacy bot data: %s", e)

        dossiers = {}
        grudge_map = legacy_bot.get("grudge_levels", {})

        for uid_str, d in legacy_dos.items():
            try:
                uid = int(uid_str)
            except ValueError:
                continue

            raw_grudge = grudge_map.get(uid_str, grudge_map.get(uid, 0))
            if 1 <= raw_grudge <= 5:
                grudge_level = int(raw_grudge)
            elif raw_grudge > 5:
                grudge_level = min(5, max(1, (raw_grudge // 20) + 1))
            else:
                grudge_level = 1

            crimes = []
            infractions = []
            for idx, c in enumerate(d.get("crimes", [])):
                crime_str = str(c)
                crimes.append(crime_str)
                infractions.append({
                    "id": f"inf_legacy_{uid}_{idx}",
                    "timestamp": d.get("updated_at", time.time()),
                    "type": "LEGACY_CRIME",
                    "detail": crime_str,
                    "severity": 1
                })

            dossiers[str(uid)] = {
                "user_id": uid,
                "username": f"User_{uid}",
                "display_name": f"User_{uid}",
                "grudge_level": grudge_level,
                "grudge_points": min(100, max(0, int(raw_grudge))),
                "titles": list(d.get("titles", [])),
                "excuses": list(d.get("excuses", [])),
                "embarrassing_moments": list(d.get("embarrassing_moments", [])),
                "game_notes": list(d.get("game_notes", [])),
                "crimes": crimes[-15:],
                "infractions": infractions[-15:],
                "roast_history": [],
                "voice_stats": {
                    "total_vc_minutes": 0,
                    "total_unmuted_seconds": 0,
                    "mute_toggle_count": 0,
                    "choke_count": 0,
                    "last_seen_vc": 0.0
                },
                "updated_at": d.get("updated_at", time.time())
            }

        # Ingest users present only in bot_data
        for uid_raw in legacy_bot.get("roast_count_per_user", {}).keys():
            uid_str = str(uid_raw)
            if uid_str not in dossiers:
                try:
                    uid = int(uid_str)
                except ValueError:
                    continue
                raw_grudge = grudge_map.get(uid_str, grudge_map.get(uid, 0))
                grudge_level = min(5, max(1, (raw_grudge // 20) + 1)) if raw_grudge > 5 else max(1, raw_grudge)
                dossiers[uid_str] = {
                    "user_id": uid,
                    "username": f"User_{uid}",
                    "display_name": f"User_{uid}",
                    "grudge_level": grudge_level,
                    "grudge_points": min(100, max(0, int(raw_grudge))),
                    "titles": ["متهم تحت المراقبة"],
                    "excuses": [],
                    "embarrassing_moments": [],
                    "game_notes": [],
                    "crimes": [],
                    "infractions": [],
                    "roast_history": [],
                    "voice_stats": {
                        "total_vc_minutes": 0,
                        "total_unmuted_seconds": 0,
                        "mute_toggle_count": 0,
                        "choke_count": 0,
                        "last_seen_vc": 0.0
                    },
                    "updated_at": time.time()
                }

        self._state["dossiers"] = dossiers

        # Normalize metrics
        norm_log = []
        for r in legacy_bot.get("roast_log", []):
            if isinstance(r, (list, tuple)) and len(r) >= 3:
                norm_log.append({"timestamp": r[0], "member": r[1], "roast": r[2]})
            elif isinstance(r, dict):
                norm_log.append(r)
        self._state["metrics"]["roast_log"] = norm_log[-100:]
        self._state["metrics"]["roast_count_per_user"] = {
            str(k): v for k, v in legacy_bot.get("roast_count_per_user", {}).items()
        }
        self._state["metrics"]["daily_roast_counts"] = legacy_bot.get("daily_roast_counts", {})
        self._state["metrics"]["hourly_vc_activity"] = legacy_bot.get("hourly_vc_activity", [0] * 24)
        self._state["metrics"]["game_popularity"] = legacy_bot.get("game_popularity", {})
        self._state["metrics"]["current_dialect"] = legacy_bot.get("current_dialect", "default")
        self._state["metrics"]["grudge_levels"] = {
            str(k): v for k, v in legacy_bot.get("grudge_levels", {}).items()
        }

        self._sync_save_state_atomic()
        logger.info("Legacy migration successfully committed to %s", self.filepath)

    # ──────────────────────────────────────────────────────────────────────────
    # Atomic Persistence Engine
    # ──────────────────────────────────────────────────────────────────────────

    def _sync_save_state_atomic(self) -> None:
        """Synchronously writes memory state to tempfile, fsyncs, closes, and replaces atomically."""
        with self._thread_lock:
            self._state["last_saved"] = time.time()
            payload = json.dumps(self._state, ensure_ascii=False, indent=2)

        with self._disk_lock:
            temp_path = None
            try:
                tf = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.data_dir, delete=False)
                temp_path = tf.name
                try:
                    tf.write(payload)
                    tf.flush()
                    os.fsync(tf.fileno())
                finally:
                    tf.close()  # Guaranteed closure before os.replace or os.remove on Windows NTFS

                # Maintain backup of previous valid state
                if os.path.exists(self.filepath) and os.path.getsize(self.filepath) > 0:
                    try:
                        shutil.copy2(self.filepath, self.bak_path)
                    except OSError:
                        pass

                # Guard against transient Windows NTFS file locks (WinError 5)
                for attempt in range(5):
                    try:
                        os.replace(temp_path, self.filepath)
                        temp_path = None
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        time.sleep(0.025)
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    async def save_state_atomic(self) -> None:
        """Coroutine-safe entrypoint that offloads disk fsync to a thread pool."""
        async with self._async_lock:
            await asyncio.to_thread(self._sync_save_state_atomic)

    # ──────────────────────────────────────────────────────────────────────────
    # Interface Contracts (PROJECT.md § Interface Contracts)
    # ──────────────────────────────────────────────────────────────────────────

    async def get_dossier(self, user_id: int) -> dict:
        """Retrieves user dossier or initializes default if non-existent."""
        uid = str(user_id)
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            return dict(self._state["dossiers"][uid])

    async def update_dossier(self, user_id: int, updates: dict) -> dict:
        """Merges updates into user dossier and persists atomically."""
        uid = str(user_id)
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            self._state["dossiers"][uid].update(updates)
            self._state["dossiers"][uid]["updated_at"] = time.time()
            res = dict(self._state["dossiers"][uid])
        await self.save_state_atomic()
        return res

    async def add_infraction(self, user_id: int, crime_type: str, detail: str) -> None:
        """Records a structured infraction and synchronizes readable crime string."""
        uid = str(user_id)
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            d = self._state["dossiers"][uid]
            inf_id = f"inf_{int(time.time() * 1000)}"
            inf = {
                "id": inf_id,
                "timestamp": time.time(),
                "type": crime_type,
                "detail": detail,
                "severity": 1
            }
            d.setdefault("infractions", []).append(inf)
            d["infractions"] = d["infractions"][-15:]

            crime_str = f"[{crime_type}] {detail}" if crime_type else detail
            d.setdefault("crimes", []).append(crime_str)
            d["crimes"] = d["crimes"][-15:]
            d["updated_at"] = time.time()
        await self.save_state_atomic()

    async def set_grudge_level(self, user_id: int, level: int) -> int:
        """Enforces bounded 1-5 integer grudge scale."""
        uid = str(user_id)
        bounded = max(1, min(5, int(level)))
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            self._state["dossiers"][uid]["grudge_level"] = bounded
            self._state["dossiers"][uid]["grudge_points"] = (bounded - 1) * 20
            self._state["dossiers"][uid]["updated_at"] = time.time()
            self._state["metrics"]["grudge_levels"][uid] = bounded
        await self.save_state_atomic()
        return bounded

    async def get_all_dossiers(self) -> dict:
        """Returns shallow copy of all stored dossiers."""
        with self._thread_lock:
            return {k: dict(v) for k, v in self._state["dossiers"].items()}

    async def record_roast(
        self,
        user_id: int,
        username: str,
        roast_text: str,
        dialect: str,
        intensity: int
    ) -> None:
        """Appends roast to per-user history and global metrics."""
        uid = str(user_id)
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            d = self._state["dossiers"][uid]
            d["username"] = username
            d.setdefault("roast_history", []).append({
                "timestamp": time.time(),
                "roast_text": roast_text,
                "dialect": dialect,
                "intensity": intensity
            })
            d["roast_history"] = d["roast_history"][-15:]
            d["updated_at"] = time.time()

            # Update metrics
            log_entry = {
                "timestamp": time.time(),
                "user_id": user_id,
                "member": username,
                "roast": roast_text,
                "dialect": dialect,
                "intensity": intensity
            }
            self._state["metrics"]["roast_log"].append(log_entry)
            self._state["metrics"]["roast_log"] = self._state["metrics"]["roast_log"][-100:]

            cnt = self._state["metrics"]["roast_count_per_user"].get(uid, 0) + 1
            self._state["metrics"]["roast_count_per_user"][uid] = cnt

            today = datetime.date.today().isoformat()
            dcnt = self._state["metrics"]["daily_roast_counts"].get(today, 0) + 1
            self._state["metrics"]["daily_roast_counts"][today] = dcnt

        await self.save_state_atomic()

    async def get_recent_roasts(self, user_id: int, limit: int = 5) -> list[str]:
        """Retrieves last N roast texts for anti-repetition negative constraints."""
        uid = str(user_id)
        with self._thread_lock:
            if uid not in self._state["dossiers"]:
                return []
            history = self._state["dossiers"][uid].get("roast_history", [])
            return [h["roast_text"] for h in history[-limit:]]

    # ──────────────────────────────────────────────────────────────────────────
    # Backward Compatibility Shims for DossierManager & Legacy Callers
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def dossiers(self) -> dict:
        with self._thread_lock:
            return self._state["dossiers"]

    @property
    def data(self) -> dict:
        with self._thread_lock:
            return self._state["dossiers"]

    @property
    def metrics(self) -> dict:
        with self._thread_lock:
            return self._state["metrics"]

    def get_user_dossier(self, user_id: int | str) -> dict:
        """Synchronous accessor matching legacy DossierManager."""
        with self._thread_lock:
            uid = str(user_id)
            if uid not in self._state["dossiers"]:
                self._state["dossiers"][uid] = self._init_default_dossier_unlocked(user_id)
            return self._state["dossiers"][uid]

    def add_excuse(self, user_id: int | str, excuse: str) -> None:
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            if excuse and excuse not in d["excuses"]:
                d["excuses"].append(excuse)
                d["updated_at"] = time.time()
                self._sync_save_state_atomic()

    def add_title(self, user_id: int | str, title: str) -> None:
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            if title and title not in d["titles"]:
                d["titles"].append(title)
                d["updated_at"] = time.time()
                self._sync_save_state_atomic()

    def add_moment(self, user_id: int | str, moment: str) -> None:
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            if moment:
                d["embarrassing_moments"].append(moment)
                d["embarrassing_moments"] = d["embarrassing_moments"][-15:]
                d["updated_at"] = time.time()
                self._sync_save_state_atomic()

    def add_crime(self, user_id: int | str, crime: str) -> None:
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            if crime and crime not in d.get("crimes", []):
                d.setdefault("crimes", []).append(crime)
                d["crimes"] = d["crimes"][-15:]
                inf_id = f"inf_{int(time.time() * 1000)}"
                d.setdefault("infractions", []).append({
                    "id": inf_id,
                    "timestamp": time.time(),
                    "type": "USER_CRIME",
                    "detail": crime,
                    "severity": 1
                })
                d["infractions"] = d["infractions"][-15:]
                d["updated_at"] = time.time()
                self._sync_save_state_atomic()

    def get_shame_card_data(self, user_id: int | str, member_name: str = "", avatar_url: str = "") -> dict:
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            seed = sum(ord(c) for c in str(user_id))
            rng = random.Random(seed)

            excuse_rate = rng.randint(88, 99)
            aim_accuracy = rng.randint(2, 18)
            choke_level = rng.randint(85, 100)
            sleep_hours = rng.randint(0, 3)

            title = d.get("titles")[-1] if d.get("titles") else "متهم تحت المراقبة"
            crime = d.get("crimes")[-1] if d.get("crimes") else (
                d.get("embarrassing_moments")[-1] if d.get("embarrassing_moments") else "النكبة الجماعية المستمرة"
            )
            top_excuse = d.get("excuses")[-1] if d.get("excuses") else "الماوس علق والنت فصل"

            return {
                "id": str(user_id),
                "name": member_name or f"مجهول #{user_id}",
                "avatar": avatar_url,
                "title": title,
                "crime": crime,
                "top_excuse": top_excuse,
                "stats": {
                    "excuses": excuse_rate,
                    "aim": aim_accuracy,
                    "choke": choke_level,
                    "sleep": sleep_hours
                },
                "crimes_count": len(d.get("crimes", [])) + len(d.get("embarrassing_moments", []))
            }

    def format_context_for_roast(self, user_id: int | str, live_voice_context: Optional[dict] = None) -> str:
        """
        Dynamically formats the criminal dossier and live telemetry for system prompt injection.
        Integrates bounded 1-5 grudge score, grudge titles, categorized infractions
        (AFK_DEAFENED, STATUS_FRAUD, RAGE_QUIT), excuses, and embarrassing moments.
        """
        with self._thread_lock:
            d = self.get_user_dossier(user_id)
            lines = []

            # 1. Grudge & Classification
            grudge_lvl = max(1, min(5, int(d.get("grudge_level") or 1)))
            grudge_title = GRUDGE_TITLES.get(grudge_lvl, GRUDGE_TITLES[1])
            titles_str = ", ".join(d.get("titles", [])) if d.get("titles") else "عضو تحت المراقبة"
            lines.append(f"• مستوى الحقد والعداوة: [{grudge_lvl}/5] - «{grudge_title}»")
            lines.append(f"• الألقاب الساخرة المعروفة: {titles_str}")

            # 2. Infractions & Criminal Record
            infractions = d.get("infractions") or []
            if infractions:
                crime_counts = {}
                recent_details = []
                for inf in infractions[-8:]:
                    itype = inf.get("type", "CRIME")
                    crime_counts[itype] = crime_counts.get(itype, 0) + 1
                    recent_details.append(f"[{itype}] {inf.get('detail', '')}")

                summary_parts = []
                if "AFK_DEAFENED" in crime_counts:
                    summary_parts.append(f"سوابق نوم ودفن بالفويس ({crime_counts['AFK_DEAFENED']} مرات)")
                if "STATUS_FRAUD" in crime_counts:
                    summary_parts.append(f"تزوير الحالة والهروب ({crime_counts['STATUS_FRAUD']} مرات)")
                if "RAGE_QUIT" in crime_counts:
                    summary_parts.append(f"هروب ريج كويت تكتيكي ({crime_counts['RAGE_QUIT']} مرات)")

                if summary_parts:
                    lines.append(f"• ملخص الجرائم المستمرة: {', '.join(summary_parts)}")
                lines.append(f"• أحدث السوابق والفضائح الموثقة: {'; '.join(recent_details[-3:])}")
            elif d.get("crimes"):
                lines.append(f"• سجل الجرائم: {'; '.join(d['crimes'][-3:])}")

            # 3. Voice Telemetry (Live + Cumulative)
            if live_voice_context:
                v_desc = []
                if live_voice_context.get("channel_name"):
                    v_desc.append(f"متواجد في روم '{live_voice_context['channel_name']}' منذ {live_voice_context.get('minutes', 0)} دقيقة")
                if live_voice_context.get("deafened"):
                    v_desc.append("مسوي دفن (أصم) وما يسمع أحد")
                elif live_voice_context.get("muted"):
                    v_desc.append("مسوي ميوت (صامت)")
                else:
                    v_desc.append("المايك مفتوح وشغال سوالف")
                if live_voice_context.get("games"):
                    v_desc.append(f"يلعب حالياً: {', '.join(live_voice_context['games'])}")
                if live_voice_context.get("custom_status"):
                    v_desc.append(f"حالته المكتوبة: '{live_voice_context['custom_status']}'")
                lines.append(f"• الرادار الصوتي الحي: {', '.join(v_desc)}")
            else:
                # Historical cumulative voice stats
                v_stats = d.get("voice_stats") or {}
                total_mins = v_stats.get("total_vc_minutes", 0)
                if total_mins > 0:
                    hours = total_mins // 60
                    rem_mins = total_mins % 60
                    lines.append(f"• السجل الصوتي التراكمي: قضى {hours} ساعة و {rem_mins} دقيقة سهر بالفويس")

            # 4. Excuses & Embarrassing Moments
            if d.get("excuses"):
                lines.append(f"• أشهر تصريفاته وأعذاره: {', '.join(d['excuses'][-3:])}")
            if d.get("embarrassing_moments"):
                lines.append(f"• زلات ومواقف محرجة سابقة: {'; '.join(d['embarrassing_moments'][-2:])}")

            return (
                "--- ملف سوابق واستخبارات الضحية (استخدم هذه المعلومات لذبّة شخصية قاتلة تكشف المستور) ---\n"
                + "\n".join(lines)
                + "\n----------------------------------------------------------------------------------"
            )


# Singleton instance for system-wide injection
state_mgr = StateManager()
