from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from speed.algorithms import compute, dijkstra, limited_search, path_time
from speed.maps import MapRepository, validate_map
from speed.scores import ScoreStore
from speed.service import GameService


@pytest.fixture(autouse=True)
def authored_defaults(monkeypatch):
    from speed.config import DEFAULT_CONFIG
    value=deepcopy(DEFAULT_CONFIG)
    value["map_source"]="authored"
    monkeypatch.setattr("speed.config.DEFAULT_CONFIG",value)


@pytest.fixture(scope="module")
def repository():
    return MapRepository()


def endpoints(data):
    return tuple(next(n["id"] for n in data["nodes"] if n["type"] == role) for role in ("start", "goal"))


def test_twelve_authored_maps_and_no_repeat(repository):
    assert len(repository.maps) == 12
    for level in ("easy", "normal", "expert"):
        assert sum(m["difficulty"] == level for m in repository.maps.values()) == 4
        previous = None
        for _ in range(20):
            selected = repository.random(level)
            assert selected["id"] != previous
            previous = selected["id"]


@pytest.mark.parametrize("ai", ["myopic", "bfs", "dijkstra"])
def test_all_algorithms_legal_terminating_and_instrumented(repository, ai):
    for ident, data in repository.maps.items():
        graph = repository.graphs[ident]
        start, goal = endpoints(data)
        result = compute(graph, ai, start, goal)
        assert result["path"][0] == start and result["path"][-1] == goal
        assert len(result["path"]) < 100
        assert result["travel_time"] == path_time(graph, result["path"])
        assert result["visited_order"] == [e["node"] for e in result["events"]]
        assert all(e["source"] is None or graph.has_edge(e["source"], e["node"]) for e in result["events"])
        optimal = nx.dijkstra_path_length(graph, start, goal, weight="travel_time")
        assert result["travel_time"] + .0001 >= optimal
        if ai == "dijkstra":
            assert result["travel_time"] == pytest.approx(optimal)
        if ai == "myopic" and data["trap"]:
            assert result["travel_time"] >= optimal + 1 - .0001


def test_bfs_is_battable_on_normal_maps(repository):
    beatable = 0
    for ident, data in repository.maps.items():
        if data["difficulty"] != "normal":
            continue
        start, goal = endpoints(data)
        graph = repository.graphs[ident]
        beatable += compute(graph, "bfs", start, goal)["travel_time"] > dijkstra(graph, start, goal)["travel_time"] + .5
    assert beatable >= 2


def test_one_way_and_invalid_paths(repository):
    data = next(d for d in repository.maps.values() if d["difficulty"] == "expert")
    graph = repository.graphs[data["id"]]
    edge = next(e for e in data["edges"] if e["one_way"])
    assert graph.has_edge(edge["source"], edge["target"])
    assert not graph.has_edge(edge["target"], edge["source"])
    with pytest.raises(ValueError, match="contresens"):
        path_time(graph, [edge["target"], edge["source"]])
    with pytest.raises(ValueError):
        path_time(graph, ["UNKNOWN"])


def test_dead_end_backtracking_is_in_race_cost():
    graph = nx.DiGraph()
    for name, x, y in [("S",0,0),("A",1,0),("B",2,0),("C",0,4),("G",3,0)]:
        graph.add_node(name, x=x, y=y)
    for a,b in [("S","A"),("A","B"),("S","C"),("C","G")]:
        graph.add_edge(a,b,travel_time=2)
        graph.add_edge(b,a,travel_time=2)
    result = limited_search(graph, "S", "G", 1)
    assert result["path"] == ["S","A","B","A","S","C","G"]
    assert result["travel_time"] == 12
    assert any(e["kind"] == "backtrack" for e in result["events"])


@pytest.mark.parametrize("cost", [0, -1, float("nan"), float("inf"), True, "2"])
def test_rejects_invalid_cost(repository, cost):
    data = deepcopy(next(iter(repository.maps.values())))
    data["edges"][0]["travel_time"] = cost
    with pytest.raises(ValueError, match="coût"):
        validate_map(data)


def test_rejects_duplicate_and_unreachable_nodes(repository):
    data = deepcopy(next(iter(repository.maps.values())))
    data["nodes"][1]["id"] = data["nodes"][0]["id"]
    with pytest.raises(ValueError, match="dupliqués"):
        validate_map(data)
    data = deepcopy(next(iter(repository.maps.values())))
    data["nodes"].append({"id":"M", "x":5, "y":5, "type":"intersection"})
    with pytest.raises(ValueError, match="inaccessible"):
        validate_map(data)


def test_records_persist_roll_over_and_session_resets(tmp_path):
    day = [date(2026, 9, 14)]
    path = tmp_path / "data" / "records.json"
    store = ScoreStore(path, today=lambda: day[0])
    assert store.get_record("a", "easy") is None
    assert store.record("a", "easy", 10)
    assert not store.record("a", "easy", 12)
    assert store.record("a", "easy", 8)
    store.save_session_score(170)
    restarted = ScoreStore(path, today=lambda: day[0])
    assert restarted.get_record("a", "easy") == 8
    assert restarted.get_record("a", "normal") is None
    assert restarted.best_score == 0
    day[0] += timedelta(days=1)
    assert store.get_record("a", "easy") is None
    assert store.best_score == 170
    assert store.record("a", "easy", 15)
    assert json.loads(path.read_text())["date"] == day[0].isoformat()
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("content", ["{broken", "[]", '{"records": []}', '{"date":"2026-09-14","records":{"a":-2}}'])
def test_corrupt_records_do_not_crash(tmp_path, content):
    path = tmp_path / "records.json"
    path.write_text(content)
    store = ScoreStore(path, today=lambda: date(2026,9,14))
    assert store.warning
    assert store.record("a", "easy", 9)
    assert json.loads(path.read_text())["records"]["easy:a"] == 9


def test_failed_write_keeps_game_running(tmp_path):
    store = ScoreStore(tmp_path / "records.json")
    with patch("speed.scores.os.replace", side_effect=OSError("Read-only")):
        assert store.record("a", "easy", 8)
    assert store.get_record("a", "easy") == 8
    assert "Sauvegarde impossible" in store.warning
    assert not list(tmp_path.glob("*.tmp"))


def test_round_completion_assistance_and_idempotence(tmp_path, repository):
    service = GameService(tmp_path / "records.json", repository=repository)
    data = service.get_random_map("normal")
    start, goal = endpoints(data)
    with pytest.raises(ValueError, match="destination"):
        service.finalize_round(data["round_id"], [start])
    completed = service.complete_route(data["round_id"], [start])
    assert completed["assisted"] and completed["path"][-1] == goal
    result = service.finalize_round(data["round_id"], completed["path"])
    assert result["assisted"] and result["score"] == 0 and result["record"] is None
    assert not (tmp_path / "records.json").exists()
    assert service.finalize_round(data["round_id"], completed["path"]) == result
    with pytest.raises(ValueError, match="terminée"):
        service.complete_route(data["round_id"], [start])


def test_20_rounds_scores_optimality_and_tie(tmp_path, repository):
    service = GameService(tmp_path / "records.json", repository=repository)
    for i in range(20):
        data = service.get_random_map(["easy","normal","expert"][i % 3])
        start, goal = endpoints(data)
        optimal = service.get_optimal_path(data["id"], start, goal)
        result = service.finalize_round(data["round_id"], optimal["path"])
        assert result["optimal"] and not result["assisted"]
        assert result["winner"] in ("player", "tie")
        assert result["record"] == result["player_time"]
        if data["difficulty"] == "expert":
            assert result["winner"] == "tie" and result["score"] == 50
        assert result["best_score"] >= result["score"]


def test_timeout_with_complete_path_is_unassisted(tmp_path, repository):
    service = GameService(tmp_path / "records.json", repository=repository)
    data = service.get_random_map("easy")
    start, goal = endpoints(data)
    path = service.get_optimal_path(data["id"],start,goal)["path"]
    assert not service.complete_route(data["round_id"],path)["assisted"]


def test_stale_round_and_bounded_history(tmp_path, repository):
    service = GameService(tmp_path / "records.json", repository=repository)
    first = service.get_random_map("easy")
    for _ in range(40):
        service.get_random_map("easy")
    assert len(service.rounds) == 32
    with pytest.raises(ValueError, match="expiré"):
        service.complete_route(first["round_id"], ["A"])


def test_speed_bonus_freezes_when_route_is_locked(tmp_path, repository):
    clock = [100.]
    service = GameService(tmp_path / "records.json", repository=repository, clock=lambda: clock[0])
    results = []
    for reflection in [3., 8.]:
        data = service.get_random_map("expert")
        start, goal = endpoints(data)
        path = service.get_optimal_path(data["id"],start,goal)["path"]
        service.begin_selection(data["round_id"])
        clock[0] += reflection
        service.begin_selection(data["round_id"])  # Ne redémarre pas le chrono.
        locked = service.lock_route(data["round_id"],path)
        assert locked["reflection_time"] == reflection
        clock[0] += 30  # Attente du robot + course : aucune incidence.
        assert service.lock_route(data["round_id"],path) == {"path":path,"assisted":False,"reflection_time":reflection}
        result = service.finalize_round(data["round_id"],path)
        assert result["reflection_time"] == reflection
        assert result["speed_bonus"] == (15-reflection)*10
        assert result["winner"] == "tie"
        results.append(result)
    assert results[0]["score"] > results[1]["score"]


def test_route_cap_rejects_long_path_and_preserves_assistance(tmp_path, repository):
    service = GameService(tmp_path / "records.json", repository=repository)
    data = service.get_random_map("easy")
    start, goal = endpoints(data)
    graph = repository.graphs[data["id"]]
    neighbor = next(iter(graph.successors(start)))
    path = [start] + [neighbor,start]*20
    with pytest.raises(ValueError,match="limite"):
        service.complete_route(data["round_id"],path)
    path += service.get_optimal_path(data["id"],start,goal)["path"][1:]
    with pytest.raises(ValueError,match="limite"):
        service.finalize_round(data["round_id"],path)
    assert not service.rounds[data["round_id"]]["assisted"]
    for node,cost in data["remaining_times"].items():
        assert cost == pytest.approx(nx.dijkstra_path_length(graph,node,goal,weight="travel_time"))


def test_automatic_completion_no_speed_bonus_or_route_changes(tmp_path, repository):
    clock = [0.]
    service = GameService(tmp_path / "records.json", repository=repository, clock=lambda: clock[0])
    data = service.get_random_map("normal")
    start, goal = endpoints(data)
    service.begin_selection(data["round_id"])
    clock[0] = 18.
    locked = service.lock_route(data["round_id"],[start],automatic=True)
    assert locked["reflection_time"] == 15
    with pytest.raises(ValueError,match="modifié"):
        service.finalize_round(data["round_id"],[start])
    result = service.finalize_round(data["round_id"],locked["path"])
    assert result["speed_bonus"] == result["score"] == 0


@pytest.mark.parametrize("limit", [0, 1, 100, float("nan"), True])
def test_map_rejects_unusable_time_limit(repository, limit):
    data = deepcopy(next(iter(repository.maps.values())))
    data["max_travel_time"] = limit
    with pytest.raises(ValueError,match="limite"):
        validate_map(data)
