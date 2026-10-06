"""Point d'entrée : python app.py (ou --no-browser pour un navigateur manuel)."""
import argparse
import os
from pathlib import Path
import sys

from speed.service import GameService

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Speed — Arrive avant le robot !")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Démarrer uniquement le serveur local")
    parser.add_argument("--depth", type=int, default=3, help="Profondeur BFS (1 à 8, défaut : 3)")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("SPEED_DATA_DIR", ROOT / "data")))
    parser.add_argument("--check-maps", action="store_true", help="Valider les cartes puis quitter")
    args = parser.parse_args()
    try:
        service = GameService(args.data_dir / "records.json", args.depth)
    except (ValueError, OSError) as exc:
        print(f"Speed ne peut pas démarrer : {exc}", file=sys.stderr)
        return 1
    if args.check_maps:
        print(f"{len(service.repository.maps)} cartes valides.")
        return 0
    import eel
    eel.init(str(ROOT / "web"))
    for name in ("get_random_map", "compute_ai_path", "get_optimal_path", "save_session_score",
                 "complete_route", "finalize_round", "begin_selection", "lock_route", "get_config", "save_config", "get_leaderboard", "submit_leaderboard"):
        method = getattr(service, name)
        def exposed(*values, _method=method):
            try:
                return {"ok": True, "data": _method(*values)}
            except (ValueError, TypeError, KeyError) as exc:
                return {"ok": False, "error": str(exc)}
        eel.expose(name)(exposed)
    print(f"Speed prêt — http://localhost:{args.port} — Ctrl+C pour arrêter", flush=True)
    try:
        eel.start("index.html", host="localhost", port=args.port,
                  mode=None if args.no_browser else "default", size=(1440, 900),
                  close_callback=lambda page, sockets: None)
    except (OSError, EnvironmentError) as exc:
        print(f"Impossible de lancer Speed : {exc}. Essayez --no-browser ou un autre --port.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
