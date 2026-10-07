"""API applicative, validation des manches et résultats faisant autorité."""
from copy import deepcopy
from collections import OrderedDict
from math import floor
from time import monotonic
from uuid import uuid4
import random
from pathlib import Path

import networkx as nx

from .algorithms import compute, dijkstra, path_time
from .maps import DIFFICULTIES, MapRepository, validate_map
from .traffic import add_traffic_events
from .scores import ScoreStore
from .leaderboard import LeaderboardStore
from .config import BOARD_SIZES, ConfigStore, board_settings
from .generator import generate_map


class GameService:
    def __init__(self, record_path, depth=3, repository=None, clock=monotonic):
        if not 1 <= depth <= 8:
            raise ValueError("La profondeur du robot doit être comprise entre 1 et 8.")
        self.repository = repository or MapRepository()
        self.scores = ScoreStore(record_path)
        self.leaderboard = LeaderboardStore(Path(record_path).parent / "leaderboard.json")
        self.depth = depth
        self.rounds = {}
        self.clock = clock
        self.config = ConfigStore(Path(record_path).parent / "config.json")
        self.generated = OrderedDict()

    def get_leaderboard(self):
        return self.leaderboard.get()

    def submit_leaderboard(self, round_id, name):
        state = self.rounds.get(round_id)
        if not state or not state.get("result"):
            raise ValueError("Termine une course avant de t’inscrire au classement.")
        if state["result"]["assisted"]:
            raise ValueError("Seules les courses terminées sans aide comptent au classement.")
        if state.get("leaderboard_saved"):
            return self.leaderboard.get()
        data = self.generated[state["map_id"]][0] if state["map_id"] in self.generated else self.repository.maps[state["map_id"]]
        result = self.leaderboard.add(data["difficulty"], name, state["result"])
        state["leaderboard_saved"] = True
        return result

    def get_config(self):
        catalog=deepcopy(BOARD_SIZES)
        for allowed in self.config.value["sizes"].values():
            for size in allowed:
                catalog[size]=board_settings(size)
        return {"config":deepcopy(self.config.value), "board_sizes":catalog, "warning":self.config.warning}

    def save_config(self, value):
        self.config.save(value)
        return self.get_config()

    def get_random_map(self, difficulty="normal"):
        if difficulty not in DIFFICULTIES:
            raise ValueError("Choisissez Facile, Normal ou Expert.")
        if self.config.value["map_source"] == "procedural":
            size = random.choice(self.config.value["sizes"][difficulty])
            data = generate_map(difficulty,size,random.SystemRandom().randrange(2**32),self.depth)
        else:
            data = deepcopy(self.repository.random(difficulty))
            if difficulty != "easy":
                seed = random.SystemRandom().randrange(2**32)
                rng = random.Random(seed)
                for _ in range(128):
                    add_traffic_events(data, rng)
                    try:
                        validate_map(data)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError("Impossible de préparer la circulation. Relance une course.")
                data["id"] += f"_traffic_v2_{seed}"
        if data.get("procedural") or difficulty != "easy":
            self.generated[data["id"]] = (deepcopy(data), self._build_generated_graph(data))
            while len(self.generated) > 40:
                self.generated.popitem(last=False)
        round_id = uuid4().hex
        self.rounds[round_id] = {"map_id": data["id"], "assisted": False, "result": None,
                                 "selection_started": None, "reflection_time": None, "locked_path": None}
        # Borné pour les longues journées de stand et les démonstrations.
        while len(self.rounds) > 32:
            del self.rounds[next(iter(self.rounds))]
        data.update(round_id=round_id, ai_type=DIFFICULTIES[difficulty], ai_depth=self.depth,
                    record=self.scores.get_record(data["id"], difficulty))
        data["ai_timing"] = deepcopy(self.config.value["ai_timing"])
        data.setdefault("selection_seconds",15)
        goal = next(n["id"] for n in data["nodes"] if n["type"] == "goal")
        data["remaining_times"] = {
            node: round(cost, 4) for node, cost in nx.single_source_dijkstra_path_length(
                self._graph(data["id"]).reverse(copy=False), goal, weight="travel_time").items()
        }
        return data

    def _graph(self, map_id):
        if map_id in self.generated:
            return self.generated[map_id][1]
        if map_id not in self.repository.graphs:
            raise ValueError("Carte inconnue.")
        return self.repository.graphs[map_id]

    @staticmethod
    def _build_generated_graph(data):
        from .generator import _directed
        return _directed(data["nodes"], data["edges"])

    def compute_ai_path(self, map_id, ai_type, start, goal):
        return compute(self._graph(map_id), ai_type, start, goal, self.depth)

    def get_optimal_path(self, map_id, start, goal):
        return dijkstra(self._graph(map_id), start, goal)

    def save_session_score(self, score):
        return self.scores.save_session_score(score)

    def _round(self, round_id):
        if round_id not in self.rounds:
            raise ValueError("Cette manche a expiré. Lancez une nouvelle course.")
        state = self.rounds[round_id]
        data = self.generated[state["map_id"]][0] if state["map_id"] in self.generated else self.repository.maps[state["map_id"]]
        start = next(n["id"] for n in data["nodes"] if n["type"] == "start")
        goal = next(n["id"] for n in data["nodes"] if n["type"] == "goal")
        return state, data, self._graph(data["id"]), start, goal

    @staticmethod
    def _validate_path(graph, path, start):
        if not isinstance(path, list) or not path or len(path) > 512:
            raise ValueError("Trajet vide ou trop long.")
        if any(not isinstance(n, str) for n in path) or path[0] != start:
            raise ValueError("Le trajet doit commencer au garage.")
        return path_time(graph, path)

    def complete_route(self, round_id, path):
        state, data, graph, start, goal = self._round(round_id)
        if state["result"]:
            raise ValueError("Cette manche est terminée.")
        cost = self._validate_path(graph, path, start)
        suffix = dijkstra(graph, path[-1], goal, departure_time=cost)
        if cost + suffix["travel_time"] > data["max_travel_time"] + .0001:
            raise ValueError(f"Ce trajet dépasse la limite de {data['max_travel_time']} s. Annule une étape.")
        if state["locked_path"] is not None:
            raise ValueError("Le trajet est déjà validé.")
        if path[-1] != goal:
            path = path + suffix["path"][1:]
            state["assisted"] = True
        return {"path": path, "travel_time": path_time(graph, path), "assisted": state["assisted"]}

    def begin_selection(self, round_id):
        state, _, _, _, _ = self._round(round_id)
        if state["selection_started"] is None:
            state["selection_started"] = self.clock()
        return {"started": True}

    def lock_route(self, round_id, path, automatic=False):
        state, data, _, _, goal = self._round(round_id)
        if state["locked_path"] is not None:
            if path != state["locked_path"]:
                raise ValueError("Le trajet est déjà validé.")
            return {"path": list(path), "assisted": state["assisted"], "reflection_time": state["reflection_time"]}
        if state["selection_started"] is None:
            raise ValueError("La sélection n’a pas encore commencé.")
        if not automatic and (not path or path[-1] != goal):
            raise ValueError("Rejoins l’arrivée avant de valider.")
        result = self.complete_route(round_id, path)
        state["locked_path"] = list(result["path"])
        # Mesure serveur : le compte à rebours, l’attente du robot et la course
        # n’entrent jamais dans le bonus de réflexion.
        state["reflection_time"] = round(min(data.get("selection_seconds",15), max(0., self.clock() - state["selection_started"])), 2)
        result["reflection_time"] = state["reflection_time"]
        return result

    def finalize_round(self, round_id, path):
        state, data, graph, start, goal = self._round(round_id)
        if state["result"] is not None:
            return state["result"]
        player_time = self._validate_path(graph, path, start)
        if player_time > data["max_travel_time"] + .0001:
            raise ValueError(f"Ce trajet dépasse la limite de {data['max_travel_time']} s.")
        if state["locked_path"] is not None and path != state["locked_path"]:
            raise ValueError("Le trajet a été modifié après sa validation.")
        if path[-1] != goal:
            raise ValueError("Rejoignez la destination avant de valider.")
        robot = compute(graph, DIFFICULTIES[data["difficulty"]], start, goal, self.depth)
        optimal = dijkstra(graph, start, goal)
        difference = round(robot["travel_time"] - player_time, 4)
        winner = "tie" if abs(difference) < .01 else "player" if difference > 0 else "robot"
        is_optimal = abs(player_time - optimal["travel_time"]) < .01
        score = 0
        speed_bonus = 0
        new_record = False
        if not state["assisted"]:
            if state["reflection_time"] is not None:
                speed_bonus = floor(150 * max(0, 1 - state["reflection_time"] / data.get("selection_seconds",15)) + .5)
            score = (100 if winner == "player" else 0) + 10 * int(max(0, difference) + .5) + (50 if is_optimal else 0)
            score += speed_bonus
            self.save_session_score(score)
            new_record = self.scores.record(data["id"], data["difficulty"], player_time)
        result = {"winner": winner, "player_time": player_time, "robot_time": robot["travel_time"],
                  "difference": difference, "assisted": state["assisted"], "optimal": is_optimal,
                  "optimal_path": optimal["path"], "optimal_time": optimal["travel_time"],
                  "record": self.scores.get_record(data["id"], data["difficulty"]),
                  "new_record": new_record, "score": score, "best_score": self.scores.best_score,
                  "reflection_time": state["reflection_time"], "speed_bonus": speed_bonus,
                  "warning": self.scores.warning, "metadata": robot["metadata"]}
        state["result"] = result
        return result
