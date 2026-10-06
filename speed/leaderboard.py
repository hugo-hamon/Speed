"""Classement local persistant, indépendant des records quotidiens."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

LEVELS = ("easy", "normal", "expert")


class LeaderboardStore:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {level: [] for level in LEVELS}
        self.warning = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != set(LEVELS):
                raise ValueError()
            for level, entries in data.items():
                if not isinstance(entries, list) or len(entries) > 10:
                    raise ValueError()
                for e in entries:
                    if (not isinstance(e, dict) or not isinstance(e.get("name"), str)
                        or not 1 <= len(e["name"].strip()) <= 24
                        or type(e.get("score")) is not int or e["score"] < 0
                        or type(e.get("time")) not in (int, float)
                        or not math.isfinite(e["time"]) or e["time"] <= 0):
                        raise ValueError()
            self.entries = {level: sorted(entries, key=lambda e: (-e["score"], e["time"])) for level, entries in data.items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.warning = "Classement illisible : une nouvelle liste sera créée au prochain enregistrement."

    def get(self):
        return {"entries": deepcopy(self.entries), "warning": self.warning}

    def add(self, level, name, result):
        if not isinstance(name, str):
            raise ValueError("Saisis un nom de 1 à 24 caractères.")
        name = " ".join(name.split())
        if not 1 <= len(name) <= 24 or any(ord(c) < 32 for c in name):
            raise ValueError("Saisis un nom de 1 à 24 caractères.")
        updated = deepcopy(self.entries)
        updated[level].append({"name": name, "time": result["player_time"], "score": result["score"]})
        updated[level] = sorted(updated[level], key=lambda e: (-e["score"], e["time"]))[:10]
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix="leaderboard-", suffix=".tmp", delete=False) as out:
                temporary = out.name
                json.dump(updated, out, ensure_ascii=False, indent=2)
                out.flush(); os.fsync(out.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise ValueError("Classement non enregistré. Réessaie ou continue avec une nouvelle course.") from exc
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        self.entries, self.warning = updated, None
        return self.get()
