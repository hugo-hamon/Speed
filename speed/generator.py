"""Villes orthogonales reproductibles, sans impasse et avec des choix de trajet.

La grille est élaguée en conservant sa biconnexité. Les sens uniques sont
acceptés seulement si la connexité forte subsiste. Les tentatives sont bornées.
"""
from math import ceil
import random

import networkx as nx

from .algorithms import compute, dijkstra
from .traffic import add_traffic_events, edge_arrival
from .config import board_settings
from .maps import DIFFICULTIES, validate_map

GENERATOR_VERSION = 4
MIN_ROUTE_CLICKS = {"easy": 0, "normal": 4, "expert": 5}


def _directed(nodes, edges):
    graph = nx.DiGraph()
    graph.add_nodes_from((n["id"], n) for n in nodes)
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], **edge)
        if not edge["one_way"]:
            graph.add_edge(edge["target"], edge["source"], **edge)
    return graph


def _has_short_optimal_route(graph, start, goal, minimum_clicks):
    """Can a fastest route be entered in fewer than the required clicks?

    Mirror the UI's straight-road and forced-corridor shortcuts, including
    one-way streets. Search click endpoints, not individual shortest paths:
    ties can contain exponentially many paths on a grid. Integer milliseconds
    also include routes accepted as optimal by scoring (less than 0.01 s off).
    """
    if minimum_clicks <= 1:
        return False
    cost = lambda a, b, edge: round(edge["travel_time"] * 1000)
    remaining = nx.single_source_dijkstra_path_length(graph.reverse(copy=False), goal, weight=cost)
    limit = dijkstra(graph, start, goal)["travel_time"] + .009
    frontier = {(None, start): 0.}
    for _ in range(minimum_clicks - 1):
        following = {}
        for (previous, node), spent in frontier.items():
            def record(before, target, total):
                if total + remaining[target] / 1000 > limit + 1e-9:
                    return False
                key = (before, target)
                following[key] = min(total, following.get(key, float("inf")))
                return True

            # Every endpoint along a straight street is a possible click,
            # even when side streets branch off (straightExtension in the UI).
            for neighbor in graph.successors(node):
                dx = graph.nodes[neighbor]["x"] - graph.nodes[node]["x"]
                dy = graph.nodes[neighbor]["y"] - graph.nodes[node]["y"]
                before, target, total = node, neighbor, spent
                while True:
                    total = edge_arrival(graph[before][target], total)
                    if not record(before, target, total) or target == goal:
                        break
                    choices = [n for n in graph.successors(target)
                               if graph.nodes[n]["x"] - graph.nodes[target]["x"] == dx
                               and graph.nodes[n]["y"] - graph.nodes[target]["y"] == dy]
                    if len(choices) != 1:
                        break
                    before, target = target, choices[0]

            # A forced corridor may turn: exclude only the node we came from,
            # and stop at the first actual choice, just like corridorExtension.
            before, current, total, seen = previous, node, spent, {node}
            while current != goal:
                choices = [n for n in graph.successors(current) if n != before]
                if len(choices) != 1 or choices[0] in seen:
                    break
                target = choices[0]
                total = edge_arrival(graph[current][target], total)
                if not record(current, target, total):
                    break
                seen.add(target)
                before, current = current, target
        if any(node == goal for _, node in following):
            return True
        frontier = following
        if not frontier:
            break
    return False


def generate_map(difficulty, size, seed, depth=3):
    if difficulty not in DIFFICULTIES:
        raise ValueError("Difficulté ou taille inconnue.")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
        raise ValueError("La graine doit être un entier entre 0 et 2³²-1.")
    if not isinstance(depth, int) or not 1 <= depth <= 8:
        raise ValueError("Profondeur de recherche invalide.")
    settings = board_settings(size)
    width, height = settings["width"], settings["height"]
    rng = random.Random(seed)
    # Small boards have fewer winding routes; allow more bounded retries now
    # that trivial optimal routes are rejected as well as weak traffic traps.
    max_attempts = 512 if difficulty == "expert" and width * height <= 12 else 128
    for attempt in range(max_attempts):
        streets = nx.grid_2d_graph(width, height)
        river = rng.random() < .4
        river_y = rng.randrange(height - 1) + .5 if river else None
        if river:
            crossings = [(a,b) for a,b in streets.edges if a[1] != b[1] and min(a[1],b[1]) < river_y < max(a[1],b[1])]
            rng.shuffle(crossings)
            for a,b in crossings[2:]:
                streets.remove_edge(a,b)
                if not nx.is_biconnected(streets):
                    streets.add_edge(a,b)
        removable = list(streets.edges)
        rng.shuffle(removable)
        remove_count = max(1, int(len(removable) * rng.uniform(.1, .25)))
        removed = 0
        for a,b in removable:
            if removed >= remove_count:
                break
            streets.remove_edge(a,b)
            if nx.is_biconnected(streets):
                removed += 1
            else:
                streets.add_edge(a,b)
        corners = [(0,0),(width-1,0),(0,height-1),(width-1,height-1)]
        start_xy = rng.choice(corners)
        goal_xy = (width-1-start_xy[0], height-1-start_xy[1])
        node_id = lambda xy: f"n{xy[0]}_{xy[1]}"
        start, goal = node_id(start_xy), node_id(goal_xy)
        nodes = [{"id":node_id((x,y)), "x":x, "y":y,
                  "type":"start" if (x,y)==start_xy else "goal" if (x,y)==goal_xy else "intersection"}
                 for x,y in sorted(streets.nodes)]
        edges = []
        for index, (a,b) in enumerate(sorted(tuple(sorted(e)) for e in streets.edges)):
            bridge = river and a[1] != b[1] and min(a[1],b[1]) < river_y < max(a[1],b[1])
            edges.append({"id":f"e{index}", "source":node_id(a), "target":node_id(b),
                          "travel_time":1.6, "road_type":"bridge" if bridge else "normal",
                          "speed_type":"normal", "one_way":False})
        graph = _directed(nodes, edges)
        # Ralentir deux rues du choix géométrique donne un vrai piège, sans
        # inventer le trajet du robot. Les autres routes restent disponibles.
        naive = compute(graph, "myopic", start, goal)["path"]
        route_edges = [graph[a][b]["id"] for a,b in zip(naive,naive[1:])]
        traps = set(rng.sample(route_edges, min(2,len(route_edges))))
        for edge in edges:
            if edge["id"] in traps or rng.random() < .1:
                edge["travel_time"] *= 2.4
                edge["speed_type"] = "traffic"
                if edge["road_type"] != "bridge":
                    edge["road_type"] = "traffic"
        graph = _directed(nodes, edges)
        alternate = nx.dijkstra_path(graph,start,goal,weight="travel_time")
        fast_ids = [graph[a][b]["id"] for a,b in zip(alternate,alternate[1:])]
        offset = rng.randrange(max(1,len(fast_ids)-2))
        fast_ids = set(fast_ids[offset:offset+3])
        for edge in edges:
            if edge["id"] in fast_ids and edge["speed_type"] != "traffic":
                edge["travel_time"] *= .65
                edge["speed_type"] = "fast"
                if edge["road_type"] != "bridge":
                    edge["road_type"] = "fast"
        if not any(edge["speed_type"] == "fast" for edge in edges):
            continue
        if difficulty == "expert":
            candidates = list(edges)
            rng.shuffle(candidates)
            for edge in candidates[:max(3,len(edges)//4)]:
                edge["one_way"] = True
                if rng.random() < .5:
                    edge["source"],edge["target"] = edge["target"],edge["source"]
                if not nx.is_strongly_connected(_directed(nodes,edges)):
                    edge["one_way"] = False
            if not any(edge["one_way"] for edge in edges):
                continue
        graph = _directed(nodes,edges)
        optimal = nx.dijkstra_path_length(graph,start,goal,weight="travel_time")
        target_time = min(14.5, 8 + (width+height-7)*.6)
        scale = target_time / optimal
        for edge in edges:
            edge["travel_time"] = round(edge["travel_time"] * scale, 3)
        add_traffic_events({"difficulty": difficulty, "edges": edges, "nodes": nodes}, rng)
        graph = _directed(nodes,edges)
        optimal = dijkstra(graph,start,goal)["travel_time"]
        if not 6 <= optimal <= 15:
            continue
        if _has_short_optimal_route(graph, start, goal, MIN_ROUTE_CLICKS[difficulty]):
            continue
        myopic = compute(graph,"myopic",start,goal)
        if myopic["travel_time"] < optimal + 1:
            continue
        robot_times = [compute(graph,DIFFICULTIES[difficulty],start,goal,d)["travel_time"]
                       for d in (range(1,9) if difficulty == "normal" else [depth])]
        max_time = max(22,ceil(optimal*2.5),ceil(max(robot_times))+2)
        if max_time > 60:
            continue
        mission = rng.choice([("pizza","Livre la pizza !"),("school","Rejoins l’école !"),
                              ("home","Rentre à la maison !"),("hospital","Rejoins l’hôpital !")])
        data = {"id":f"generated_v{GENERATOR_VERSION}_{difficulty}_{size}_{seed}",
                "name":rng.choice(["Les jardins", "La traversée", "Les quatre vents", "Les avenues"]) + f" · {width} × {height}",
                "difficulty":difficulty, "destination":mission[0], "mission":mission[1],
                "background":"suburb_day", "river":river, "river_y":river_y,
                "nodes":nodes, "edges":edges, "width":width, "height":height,
                "max_travel_time":max_time, "selection_seconds":settings["selection_seconds"],
                "decoration_seed":seed, "trap":True, "procedural":True,
                "generation":{"version":GENERATOR_VERSION,"seed":seed,"size":size,"attempt":attempt},
                "science_hint":"Les rues rapides peuvent faire gagner du temps, même avec un détour."}
        try:
            validate_map(data)
        except ValueError:
            continue
        return data
    raise ValueError("La ville n’a pas pu être créée. Relance une nouvelle course.")
