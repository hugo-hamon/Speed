"""Chargement et validation des cartes éditoriales JSON."""
import json
import math
import random
from pathlib import Path

import networkx as nx

from .algorithms import compute, dijkstra
from .traffic import rail_is_dry

DIFFICULTIES = {"easy": "myopic", "normal": "bfs", "expert": "dijkstra"}


def validate_map(data):
    prefix = f"Carte {data.get('id', '?')} : "
    def require(condition, message):
        if not condition:
            raise ValueError(prefix + message)

    require(data.get("difficulty") in DIFFICULTIES, "difficulté inconnue")
    nodes, edges = data.get("nodes", []), data.get("edges", [])
    procedural = data.get("procedural", False)
    require(10 <= len(nodes) <= (750 if procedural else 20), "nombre de carrefours invalide")
    require(14 <= len(edges) <= (1500 if procedural else 30), "nombre de routes invalide")
    ids = [n["id"] for n in nodes]
    require(len(set(ids)) == len(ids), "identifiants de carrefours dupliqués")
    require(all(isinstance(n.get(c), (int, float)) and math.isfinite(n[c])
                for n in nodes for c in ("x", "y")), "coordonnées invalides")
    require(len({(n['x'], n['y']) for n in nodes}) == len(nodes), "carrefours superposés")
    starts = [n["id"] for n in nodes if n.get("type") == "start"]
    goals = [n["id"] for n in nodes if n.get("type") == "goal"]
    require(len(starts) == len(goals) == 1, "départ et arrivée uniques requis")
    graph = nx.DiGraph()
    graph.add_nodes_from((n["id"], n) for n in nodes)
    used, edge_ids = set(), set()
    for edge in edges:
        a, b, cost = edge["source"], edge["target"], edge.get("travel_time")
        require(a in graph and b in graph and a != b, "extrémités de route invalides")
        require(isinstance(cost, (int, float)) and not isinstance(cost, bool)
                and math.isfinite(cost) and cost > 0, "coût non positif ou non fini")
        key = frozenset((a, b))
        require(key not in used, "route dupliquée")
        require(edge.get("id") and edge["id"] not in edge_ids, "identifiant de route invalide")
        require(edge.get("road_type") in {"normal", "fast", "traffic", "bridge", "light"}, "type de route inconnu")
        event = edge.get("traffic_event")
        if event is not None:
            require(data["difficulty"] != "easy" and isinstance(event, dict), "obstacle hors mode moyen/expert")
            require(event.get("kind") in {"signal", "rail", "bridge"}, "obstacle inconnu")
            require(event["kind"] == "signal" or data["difficulty"] == "expert", "obstacle réservé au mode expert")
            require(event["kind"] != "rail" or rail_is_dry(data,edge), "voie ferrée sur la rivière")
            require(all(type(event.get(k)) in (int,float) and math.isfinite(event[k])
                        for k in ("period", "closed_for", "phase")), "cycle d’obstacle invalide")
            require(0 < event["closed_for"] < event["period"] <= 30
                    and 0 <= event["phase"] <= event["period"], "cycle d’obstacle invalide")
            require(event["kind"] != "bridge" or data.get("river") and edge["road_type"] == "bridge",
                    "pont levant sans rivière")
        require(not edge.get("one_way") or data["difficulty"] == "expert", "sens unique hors mode expert")
        used.add(key)
        edge_ids.add(edge["id"])
        graph.add_edge(a, b, **edge)
        if not edge.get("one_way", False):
            graph.add_edge(b, a, **edge)
    start, goal = starts[0], goals[0]
    if procedural:
        require(nx.is_biconnected(graph.to_undirected()), "la ville contient une impasse ou un passage unique")
        require(nx.is_strongly_connected(graph), "sens uniques sans possibilité de retour")
        for a,b in graph.edges:
            require(abs(graph.nodes[a]["x"]-graph.nodes[b]["x"])+abs(graph.nodes[a]["y"]-graph.nodes[b]["y"]) == 1,
                    "route hors grille")
    require(set(nx.descendants(graph, start)) | {start} == set(ids), "carrefour inaccessible depuis le départ")
    require(set(nx.ancestors(graph, goal)) | {goal} == set(ids), "carrefour sans issue vers l'arrivée")
    paths = nx.shortest_simple_paths(graph, start, goal, weight="travel_time")
    require(next(paths, None) is not None and next(paths, None) is not None,
            "deux itinéraires distincts requis")
    optimal = dijkstra(graph, start, goal)["travel_time"]
    require(6 <= optimal <= 15, "durée optimale hors intervalle 6–15 secondes")
    limit = data.get("max_travel_time")
    require(isinstance(limit, (int, float)) and not isinstance(limit, bool)
            and math.isfinite(limit) and optimal <= limit <= 60, "limite de trajet invalide")
    for depth in range(1, 9):
        robot = compute(graph, DIFFICULTIES[data["difficulty"]], start, goal, depth)
        require(robot["travel_time"] <= limit, "le trajet du robot dépasse la limite")
    if data.get("trap"):
        naive = compute(graph, "myopic", start, goal)
        require(naive["travel_time"] >= optimal + 1, "piège trop faible pour le robot myope")
    return graph


class MapRepository:
    def __init__(self, directory=None):
        directory = directory or Path(__file__).resolve().parent.parent / "maps"
        self.maps, self.graphs = {}, {}
        for filename in sorted(Path(directory).glob("*.json")):
            try:
                data = json.loads(filename.read_text(encoding="utf-8"))
                graph = validate_map(data)
                if data["id"] in self.maps:
                    raise ValueError("Identifiant de carte dupliqué")
                self.maps[data["id"]], self.graphs[data["id"]] = data, graph
            except (ValueError, KeyError, TypeError, nx.NetworkXException) as exc:
                raise ValueError(f"{filename.name} : {exc}") from exc
        if not self.maps:
            raise ValueError("Aucune carte trouvée dans le dossier maps.")
        self.previous = {}

    def random(self, difficulty):
        if difficulty not in DIFFICULTIES:
            raise ValueError("Choisissez Facile, Normal ou Expert.")
        choices = [m for m in self.maps.values() if m["difficulty"] == difficulty]
        if not choices:
            raise ValueError("Aucune carte pour cette difficulté.")
        alternatives = [m for m in choices if m["id"] != self.previous.get(difficulty)]
        selected = random.choice(alternatives or choices)
        self.previous[difficulty] = selected["id"]
        return selected
