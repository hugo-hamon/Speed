"""Records du jour atomiques ; score de session conservé uniquement en mémoire."""
from datetime import date
import json
import math
import os
from pathlib import Path
import tempfile


class ScoreStore:
    def __init__(self, path, today=date.today):
        self.path, self.today = Path(path), today
        self.best_score = 0
        self.day = self.today().isoformat()
        self.records = {}
        self.warning = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("records"), dict):
                raise ValueError("Format de records invalide")
            if data.get("date") == self.day:
                if not all(isinstance(k, str) and isinstance(v, (int, float))
                           and not isinstance(v, bool) and math.isfinite(v) and v > 0
                           for k, v in data["records"].items()):
                    raise ValueError("Temps de record invalide")
                self.records = data["records"]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.warning = "Records illisibles : une nouvelle liste locale sera créée."

    def _rollover(self):
        day = self.today().isoformat()
        if day != self.day:
            self.day, self.records = day, {}

    def get_record(self, map_id, difficulty):
        self._rollover()
        return self.records.get(f"{difficulty}:{map_id}")

    def save_session_score(self, score):
        if not isinstance(score, int) or isinstance(score, bool) or score < 0:
            raise ValueError("Score invalide.")
        self.best_score = max(self.best_score, score)
        return self.best_score

    def record(self, map_id, difficulty, travel_time):
        if not math.isfinite(travel_time) or travel_time <= 0:
            raise ValueError("Temps de record invalide.")
        self._rollover()
        key = f"{difficulty}:{map_id}"
        previous = self.records.get(key)
        if previous is not None and travel_time >= previous:
            return False
        self.records[key] = travel_time
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="records-", suffix=".tmp", delete=False) as out:
                temp = out.name
                json.dump({"date": self.day, "records": self.records}, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, self.path)
        except OSError:
            self.warning = "Sauvegarde impossible : ce record reste disponible jusqu’à la fermeture."
        finally:
            if temp and os.path.exists(temp):
                try:
                    os.unlink(temp)
                except OSError:
                    pass
        return True
