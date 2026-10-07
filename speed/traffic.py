"""Shared traffic schedules, measured from the simultaneous race departure."""
from math import hypot

STOP_FRACTION = .35


def rail_is_dry(data, edge, nodes=None):
    """Keep the whole track AND both moving carriages off the river band."""
    if not data.get("river"):
        return True
    nodes = nodes or {n["id"]: n for n in data["nodes"]}
    a,b = nodes[edge["source"]],nodes[edge["target"]]
    dx,dy = b["x"]-a["x"],b["y"]-a["y"]
    length = hypot(dx,dy)
    half_height = abs(dy/length)*.16 + abs(dx/length)*1.10
    river_y = data.get("river_y")
    return abs((a["y"]+b["y"])/2 - (.5 if river_y is None else river_y)) > half_height + .22


def traffic_wait(edge, arrival):
    event = edge.get("traffic_event")
    if not event:
        return 0.
    phase = round(arrival + event["phase"], 6) % event["period"]
    return max(0., event["closed_for"] - phase)


def edge_arrival(edge, departure):
    drive = edge["travel_time"]
    return round(departure + drive + traffic_wait(edge, departure + drive * STOP_FRACTION), 6)


def add_traffic_events(data, rng):
    """Randomize schedules once; both competitors then share the same clock."""
    if data["difficulty"] == "easy":
        return
    edges = data["edges"]
    for edge in edges:
        edge.pop("traffic_event", None)
    available = list(edges)
    rng.shuffle(available)
    bridges = [e for e in available if e["road_type"] == "bridge"]
    plans = []
    if bridges and data["difficulty"] == "expert":
        edge = bridges[0]
        plans.append((edge, "bridge"))
        available.remove(edge)
    roads = [e for e in available if e["road_type"] != "bridge"]
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    landmarks = [n for n in nodes.values() if n.get("type") in {"start", "goal"}]
    for kind in (["signal", "rail", "signal"] if data["difficulty"] == "expert" else ["signal"]):
        if not roads:
            break
        def clearance(edge):
            if not landmarks:
                return 0
            a,b = nodes[edge["source"]],nodes[edge["target"]]
            x,y = (a["x"]+b["x"])/2,(a["y"]+b["y"])/2
            return min((x-n["x"])**2+(y-n["y"])**2 for n in landmarks)
        # A railway needs room on both sides; keep it away from the garage
        # and destination, whose buildings cannot be removed for scenery.
        eligible = [e for e in roads if rail_is_dry(data,e,nodes)] if kind == "rail" else roads
        if not eligible:
            continue
        candidates = [e for e in eligible if clearance(e) >= 1.44] if kind == "rail" else eligible
        edge = candidates[-1] if candidates else max(eligible,key=clearance)
        roads.remove(edge)
        plans.append((edge, kind))
    for edge, kind in plans:
        period = rng.randint(6, 10)
        closed = rng.choice([1.5, 2., 2.5]) if kind == "signal" else rng.choice([2., 2.5, 3.])
        edge["traffic_event"] = {"kind": kind, "period": period,
                                 "closed_for": closed, "phase": round(rng.uniform(0, period), 3)}
