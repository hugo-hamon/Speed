"""Recherches instrumentées : le calcul ne contient aucune temporisation."""
from collections import deque
from heapq import heappop, heappush
from itertools import count
from math import hypot

import networkx as nx


def path_time(graph, path):
    if not path or any(node not in graph for node in path):
        raise ValueError("Le trajet contient un carrefour inconnu.")
    if any(not graph.has_edge(a, b) for a, b in zip(path, path[1:])):
        raise ValueError("Le trajet emprunte une route absente ou à contresens.")
    return round(sum(graph[a][b]["travel_time"] for a, b in zip(path, path[1:])), 4)


def _result(graph, path, events, name, depth=None):
    return {
        "path": path,
        "visited_order": [event["node"] for event in events],
        "travel_time": path_time(graph, path),
        "events": events,
        "metadata": {"algorithm": name, "depth": depth,
                     "nodes_explored": len(events),
                     "unique_nodes_explored": len({e["node"] for e in events})},
    }


def dijkstra(graph, start, goal):
    if start not in graph or goal not in graph:
        raise ValueError("Départ ou destination inconnu.")
    serial = count()
    queue = [(0.0, next(serial), start)]
    distances, parents, settled, events = {start: 0.0}, {}, set(), []
    while queue:
        cost, _, node = heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        events.append({"node": node, "source": parents.get(node), "depth": 0,
                       "cost": round(cost, 4), "kind": "settle"})
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(parents[path[-1]])
            return _result(graph, list(reversed(path)), events, "Dijkstra")
        for neighbor in sorted(graph.successors(node)):
            candidate = cost + graph[node][neighbor]["travel_time"]
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                parents[neighbor] = node
                heappush(queue, (candidate, next(serial), neighbor))
    raise ValueError("La destination est inaccessible.")


def limited_search(graph, start, goal, depth=2, name="Robot myope"):
    """Décisions locales, mémoire des carrefours et retours réellement parcourus.

    Une vague BFS locale classe les prochains choix par distance à destination.
    Les poids sont ignorés volontairement. Une pile DFS assure la terminaison.
    Sur route à sens unique, un retour BFS légal remplace le demi-tour.
    """
    if start not in graph or goal not in graph:
        raise ValueError("Départ ou destination inconnu.")
    if not isinstance(depth, int) or not 1 <= depth <= 8:
        raise ValueError("La profondeur doit être comprise entre 1 et 8.")
    gx, gy = graph.nodes[goal]["x"], graph.nodes[goal]["y"]

    def distance(node):
        data = graph.nodes[node]
        return hypot(data["x"] - gx, data["y"] - gy)

    route, stack, discovered = [start], [start], {start}
    events = [{"node": start, "source": None, "depth": 0, "kind": "explore"}]
    while stack:
        current = stack[-1]
        if current == goal:
            return _result(graph, route, events, name, depth)
        candidates = [n for n in sorted(graph.successors(current)) if n not in discovered]
        # Chaque branche conserve son propre ensemble visité : on compare les
        # horizons des choix disponibles sans favoriser la première branche.
        frontier = deque((n, current, 1, n) for n in candidates)
        seen = {n: {current, n} for n in candidates}
        ranks = {n: (distance(n), 1, n) for n in candidates}
        while frontier:
            node, parent, level, first = frontier.popleft()
            events.append({"node": node, "source": parent, "depth": level,
                           "kind": "explore"})
            ranks[first] = min(ranks[first], (distance(node), level, node))
            if level < depth and node != goal:
                for neighbor in sorted(graph.successors(node)):
                    if neighbor not in discovered and neighbor not in seen[first]:
                        seen[first].add(neighbor)
                        frontier.append((neighbor, node, level + 1, first))
        if candidates:
            chosen = min(candidates, key=lambda n: (ranks[n], n))
            discovered.add(chosen)
            stack.append(chosen)
            events.append({"node": chosen, "source": current, "depth": 0, "kind": "advance"})
            route.append(chosen)
        else:
            stack.pop()
            if stack:
                try:
                    back = nx.shortest_path(graph, current, stack[-1])
                except nx.NetworkXNoPath as exc:
                    raise ValueError("Le robot ne peut pas sortir de cette impasse.") from exc
                for node in back[1:]:
                    events.append({"node": node, "source": route[-1], "depth": 0,
                                   "kind": "backtrack"})
                    route.append(node)
                    if node == goal:
                        return _result(graph, route, events, name, depth)
    raise ValueError("La destination est inaccessible.")


def compute(graph, ai_type, start, goal, depth=3):
    if ai_type == "myopic":
        return limited_search(graph, start, goal, 2, "Robot myope")
    if ai_type == "bfs":
        return limited_search(graph, start, goal, depth, "BFS limité")
    if ai_type == "dijkstra":
        return dijkstra(graph, start, goal)
    raise ValueError("Type de robot inconnu.")
