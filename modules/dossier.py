"""
dossier.py - سجل السوابق والفضائح (Criminal Dossier) لأعضاء السيرفر
لتخزين الأعذار المتكررة، الألقاب الساخرة، ومواقف الخسارات المحرجة
"""
import json
import os
import time

DOSSIER_FILE = "user_dossiers.json"


class DossierManager:
    def __init__(self, filepath=DOSSIER_FILE):
        self.filepath = filepath
        self.dossiers = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.dossiers = json.load(f)
            except Exception:
                self.dossiers = {}
        else:
            self.dossiers = {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.dossiers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving dossier: {e}")

    def get_user_dossier(self, user_id: int | str) -> dict:
        uid = str(user_id)
        if uid not in self.dossiers:
            self.dossiers[uid] = {
                "excuses": [],
                "titles": [],
                "embarrassing_moments": [],
                "game_notes": [],
                "updated_at": time.time()
            }
        return self.dossiers[uid]

    def add_excuse(self, user_id: int | str, excuse: str):
        d = self.get_user_dossier(user_id)
        if excuse and excuse not in d["excuses"]:
            d["excuses"].append(excuse)
            d["updated_at"] = time.time()
            self.save()

    def add_title(self, user_id: int | str, title: str):
        d = self.get_user_dossier(user_id)
        if title and title not in d["titles"]:
            d["titles"].append(title)
            d["updated_at"] = time.time()
            self.save()

    def add_moment(self, user_id: int | str, moment: str):
        d = self.get_user_dossier(user_id)
        if moment:
            d["embarrassing_moments"].append(moment)
            d["embarrassing_moments"] = d["embarrassing_moments"][-15:]
            d["updated_at"] = time.time()
            self.save()

    def format_context_for_roast(self, user_id: int | str) -> str:
        d = self.get_user_dossier(user_id)
        parts = []
        if d.get("titles"):
            parts.append(f"ألقابه الساخرة المعروفة: {', '.join(d['titles'][-3:])}")
        if d.get("excuses"):
            parts.append(f"أعذاره المشهورة لما ينكب: {', '.join(d['excuses'][-3:])}")
        if d.get("embarrassing_moments"):
            parts.append(f"فضائح سابقة له: {'; '.join(d['embarrassing_moments'][-2:])}")
        if parts:
            return "--- ملف سوابق الضحية (استخدم هذه المعلومات لذبّة شخصية وقاتلة) ---\n" + "\n".join(parts) + "\n----------------------------------------"
        return ""


dossier_mgr = DossierManager()
