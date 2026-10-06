"""Configuration locale du stand, validée et écrite atomiquement."""
from copy import deepcopy
import json
import os
import re
import math
from pathlib import Path
import tempfile

BOARD_SIZES = {
    "small": {"label": "Petit", "width": 4, "height": 3, "selection_seconds": 15},
    "medium": {"label": "Moyen", "width": 5, "height": 4, "selection_seconds": 20},
    "large": {"label": "Grand", "width": 7, "height": 5, "selection_seconds": 30},
    "huge": {"label": "Très grand", "width": 9, "height": 7, "selection_seconds": 40},
}
DEFAULT_AI_TIMING = {"easy":12,"normal":18,"expert":24,"message_seconds":3}
DEFAULT_CONFIG = {"ai_timing":deepcopy(DEFAULT_AI_TIMING),"map_source": "procedural", "sizes": {
    "easy": ["small"], "normal": ["medium"], "expert": ["large"],
}}


def board_settings(size):
    if isinstance(size,str) and size in BOARD_SIZES:
        return deepcopy(BOARD_SIZES[size])
    match=re.fullmatch(r"custom_([1-9][0-9]*)x([1-9][0-9]*)",size) if isinstance(size,str) else None
    if not match:
        raise ValueError("Taille de carte inconnue.")
    width,height=map(int,match.groups())
    if not (3 <= width <= 30 and 3 <= height <= 30 and 12 <= width*height <= 750):
        raise ValueError("Dimensions : 3 à 30 par côté, de 12 à 750 carrefours au total.")
    return {"label":"Personnalisé", "width":width,"height":height,
            "selection_seconds":min(120,max(20,round((width+height)*2.5)))}


def validate_config(data):
    if not isinstance(data, dict) or data.get("map_source") not in ("procedural", "authored"):
        raise ValueError("Choisissez des cartes générées ou préparées.")
    sizes = data.get("sizes")
    if not isinstance(sizes, dict) or set(sizes) != set(DEFAULT_CONFIG["sizes"]):
        raise ValueError("Renseignez les tailles pour les trois difficultés.")
    normalized = {}
    for difficulty, allowed in sizes.items():
        if (not isinstance(allowed, list) or not allowed
                or len(allowed)>20 or any(not isinstance(s, str) for s in allowed)):
            raise ValueError("Sélectionnez au moins une taille valide par difficulté.")
        for size in allowed:
            board_settings(size)
        normalized[difficulty] = list(dict.fromkeys(allowed))
    timing = data.get("ai_timing", DEFAULT_AI_TIMING)
    if not isinstance(timing,dict) or set(timing)!=set(DEFAULT_AI_TIMING):
        raise ValueError("Renseignez les durées des trois robots et des messages.")
    for key,value in timing.items():
        low,high=(1,15) if key=="message_seconds" else (5,120)
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError("Durée des robots : 5 à 120 s ; messages : 1 à 15 s.")
    return {"map_source": data["map_source"], "sizes": normalized, "ai_timing":deepcopy(timing)}


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.value = deepcopy(DEFAULT_CONFIG)
        self.warning = None
        try:
            self.value = validate_config(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.warning = "Configuration illisible : les réglages par défaut sont utilisés."

    def save(self, data):
        value = validate_config(data)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="config-", suffix=".tmp", delete=False) as output:
                temporary = output.name
                json.dump(value, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise ValueError("Impossible d’enregistrer la configuration. Les anciens réglages restent actifs.") from exc
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        self.value, self.warning = value, None
        return deepcopy(value)
