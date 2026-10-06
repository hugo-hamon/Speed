"""Villes orthogonales reproductibles, sans impasse et avec des choix de trajet.

La grille est élaguée en conservant sa biconnexité. Les sens uniques sont
acceptés seulement si la connexité forte subsiste. Les tentatives sont bornées.
"""
from math import ceil
import random

import networkx as nx

from .algorithms import compute
from .config import board_settings
from .maps import DIFFICULTIES, validate_map

GENERATOR_VERSION = 2


def _directed(nodes, edges):
    graph = nx.DiGraph()
    graph.add_nodes_from((n["id"], n) for n in nodes)
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], **edge)
        if not edge["one_way"]:
            graph.add_edge(edge["target"], edge["source"], **edge)
    return graph


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
    for attempt in range(32):
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
        graph = _directed(nodes,edges)
        optimal = nx.dijkstra_path_length(graph,start,goal,weight="travel_time")
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
