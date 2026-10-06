from copy import deepcopy
import json
from time import perf_counter
from unittest.mock import patch

import networkx as nx
import pytest

from speed.algorithms import compute
from speed.config import BOARD_SIZES, DEFAULT_CONFIG, ConfigStore
from speed.generator import generate_map
from speed.maps import validate_map
from speed.service import GameService


@pytest.mark.parametrize("difficulty",["easy","normal","expert"])
@pytest.mark.parametrize("size",list(BOARD_SIZES))
def test_generated_cities_have_no_dead_ends_and_real_choices(difficulty,size):
    settings=BOARD_SIZES[size]
    for seed in range(20):
        data=generate_map(difficulty,size,seed)
        graph=validate_map(data)
        assert len(data["nodes"])==settings["width"]*settings["height"]
        undirected=graph.to_undirected()
        assert nx.is_biconnected(undirected)
        assert min(dict(undirected.degree()).values())>=2
        assert nx.is_strongly_connected(graph)
        start=next(n["id"] for n in data["nodes"] if n["type"]=="start")
        goal=next(n["id"] for n in data["nodes"] if n["type"]=="goal")
        optimal=nx.dijkstra_path_length(graph,start,goal,weight="travel_time")
        assert 6<=optimal<=15
        assert compute(graph,"myopic",start,goal)["travel_time"]>=optimal+1
        assert any(e["speed_type"]=="fast" for e in data["edges"])
        assert any(e["speed_type"]=="traffic" for e in data["edges"])
        assert all(e["travel_time"]>0 for e in data["edges"])
        assert any(e["one_way"] for e in data["edges"]) == (difficulty=="expert")
        paths=nx.shortest_simple_paths(graph,start,goal,weight="travel_time")
        assert next(paths)!=next(paths)


def test_generation_reproducible_and_varied():
    first=generate_map("normal","large",123456)
    assert first==generate_map("normal","large",123456)
    other=generate_map("normal","large",123457)
    assert first["edges"]!=other["edges"]
    assert first["id"]!=other["id"]


def test_largest_generation_is_bounded():
    started=perf_counter()
    for seed in range(10):
        generate_map("normal","huge",1000+seed)
    elapsed=perf_counter()-started
    print(f"\n10 villes de 63 carrefours générées en {elapsed:.3f} s")
    assert elapsed<10  # Garde-fou contre une recherche exponentielle accidentelle.


@pytest.mark.parametrize("level,size,seed",[("unknown","small",1),("easy","invalid",1),("easy","small",-1),("easy","small",True)])
def test_generator_rejects_invalid_input(level,size,seed):
    with pytest.raises(ValueError):
        generate_map(level,size,seed)


def test_config_persistence_validation_and_failed_save(tmp_path):
    path=tmp_path/"config.json"
    store=ConfigStore(path)
    assert store.value==DEFAULT_CONFIG
    selected=deepcopy(DEFAULT_CONFIG)
    selected["sizes"]["normal"]=["small","huge"]
    store.save(selected)
    assert ConfigStore(path).value==selected
    bad=deepcopy(selected);bad["sizes"]["easy"]=[]
    with pytest.raises(ValueError):
        store.save(bad)
    assert store.value==selected
    with patch("speed.config.os.replace",side_effect=OSError("readonly")):
        with pytest.raises(ValueError,match="Impossible"):
            store.save(DEFAULT_CONFIG)
    assert ConfigStore(path).value==selected
    assert not list(tmp_path.glob("*.tmp"))
    path.write_text("{invalid")
    assert ConfigStore(path).value==DEFAULT_CONFIG
    assert ConfigStore(path).warning


def test_service_uses_allowed_sizes_and_limits_generated_cache(tmp_path):
    service=GameService(tmp_path/"records.json")
    config=deepcopy(DEFAULT_CONFIG)
    config["sizes"]["easy"]=["medium","large"]
    service.save_config(config)
    sizes=set()
    for _ in range(44):
        data=service.get_random_map("easy")
        sizes.add(data["generation"]["size"])
        assert data["selection_seconds"] in (20,30)
        assert data["procedural"]
    assert sizes=={"medium","large"}
    assert len(service.generated)==40 and len(service.rounds)==32
    # Les manches encore valides doivent conserver leur carte et leur graphe.
    for ident in service.rounds:
        assert service._round(ident)
    config["map_source"]="authored"
    service.save_config(config)
    assert not service.get_random_map("easy").get("procedural",False)


def test_generated_round_scoring_and_config_snapshot(tmp_path):
    clock=[0.]
    service=GameService(tmp_path/"records.json",clock=lambda:clock[0])
    config=deepcopy(DEFAULT_CONFIG);config["sizes"]["expert"]=["huge"]
    service.save_config(config)
    data=service.get_random_map("expert")
    start=next(n["id"] for n in data["nodes"] if n["type"]=="start")
    goal=next(n["id"] for n in data["nodes"] if n["type"]=="goal")
    path=service.get_optimal_path(data["id"],start,goal)["path"]
    service.begin_selection(data["round_id"])
    clock[0]=20
    locked=service.lock_route(data["round_id"],path)
    service.save_config(DEFAULT_CONFIG)
    result=service.finalize_round(data["round_id"],locked["path"])
    assert result["winner"]=="tie" and result["speed_bonus"]==75
    assert result["reflection_time"]==20


@pytest.mark.parametrize("difficulty", ["easy", "normal", "expert"])
@pytest.mark.parametrize("seed", [7,42,2026])
def test_custom_city_and_uniform_costs(difficulty, seed):
    data=generate_map(difficulty,"custom_30x25",seed)
    validate_map(data)
    assert len(data["nodes"])==750
    assert data["selection_seconds"]==120
    groups={}
    for edge in data["edges"]:
        groups.setdefault(edge["speed_type"],set()).add(edge["travel_time"])
    assert all(len(costs)==1 for costs in groups.values())


def test_custom_config_survives_restart(tmp_path):
    from speed.config import board_settings
    config=deepcopy(DEFAULT_CONFIG)
    config["sizes"]["normal"]=["custom_30x25","medium"]
    store=ConfigStore(tmp_path/"config.json");store.save(config)
    assert ConfigStore(store.path).value==config
    for size in ["custom_31x3","custom_30x30","custom_3x3","custom_0x12","custom_3.5x4"]:
        with pytest.raises(ValueError):board_settings(size)


def test_authored_visual_classes_have_uniform_costs():
    from speed.maps import MapRepository
    for data in MapRepository().maps.values():
        groups={}
        for edge in data["edges"]:
            groups.setdefault(edge["speed_type"],set()).add(edge["travel_time"])
        assert all(len(costs)==1 for costs in groups.values())


def test_ai_timing_validation_migration_and_persistence(tmp_path):
    from speed.config import validate_config, DEFAULT_AI_TIMING
    old={'map_source':'procedural','sizes':deepcopy(DEFAULT_CONFIG['sizes'])}
    assert validate_config(old)['ai_timing']==DEFAULT_AI_TIMING
    config=validate_config(old)
    config['ai_timing']={'easy':8,'normal':20,'expert':30,'message_seconds':4}
    store=ConfigStore(tmp_path/'config.json');store.save(config)
    assert ConfigStore(store.path).value==config
    for key,value in [('easy',0),('normal',float('nan')),('expert',True),('message_seconds',16)]:
        bad=deepcopy(config);bad['ai_timing'][key]=value
        with pytest.raises(ValueError):store.save(bad)
    service=GameService(tmp_path/'records.json')
    assert service.get_random_map('easy')['ai_timing']==config['ai_timing']
