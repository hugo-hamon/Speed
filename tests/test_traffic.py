from copy import deepcopy
import random

import networkx as nx
import pytest

from speed.algorithms import dijkstra, path_time
from speed.generator import generate_map
from speed.maps import validate_map, MapRepository
from speed.service import GameService
from speed.traffic import edge_arrival, traffic_wait, add_traffic_events


def traffic_graph():
    graph=nx.DiGraph()
    graph.add_edge('s','a',travel_time=1.,traffic_event={'kind':'signal','period':6.,'closed_for':3.,'phase':0.})
    graph.add_edge('a','g',travel_time=1.)
    graph.add_edge('s','b',travel_time=1.2)
    graph.add_edge('b','c',travel_time=1.2)
    graph.add_edge('c','g',travel_time=1.2)
    return graph


def test_dijkstra_changes_route_with_arrival_time():
    graph=traffic_graph()
    assert dijkstra(graph,'s','g')['path']==['s','b','c','g']
    assert dijkstra(graph,'s','g',departure_time=3)['path']==['s','a','g']
    assert path_time(graph,['s','a','g'])==4.65
    assert path_time(graph,['s','a','g'],departure_time=3)==2
    for start_time in [0,.1,2.65,3,5.65,6,7.123,12]:
        expected=min(path_time(graph,path,start_time) for path in nx.all_simple_paths(graph,'s','g'))
        assert dijkstra(graph,'s','g',departure_time=start_time)['travel_time']==expected


def test_cycles_are_fifo_and_boundary_times_are_exact():
    edge=traffic_graph()['s']['a']
    assert traffic_wait(edge,0)==3
    assert traffic_wait(edge,3)==0
    assert traffic_wait(edge,6)==3
    arrivals=[edge_arrival(edge,t/100) for t in range(1500)]
    assert arrivals==sorted(arrivals)
    assert edge_arrival(edge,2.65)==3.65
    assert edge_arrival(edge,5.65)==9.65


@pytest.mark.parametrize('level',['easy','normal','expert'])
def test_generated_obstacles_are_seeded_and_consistent(level):
    kinds=set()
    for seed in range(8):
        data=generate_map(level,'medium',seed)
        graph=validate_map(data)
        events=[e['traffic_event'] for e in data['edges'] if e.get('traffic_event')]
        if level=='easy':
            assert not events
            continue
        assert {'signal','rail'}<={e['kind'] for e in events}
        if data['river']:assert any(e['kind']=='bridge' for e in events)
        kinds.update(e['kind'] for e in events)
        assert data==generate_map(level,'medium',seed)
        start=next(n['id'] for n in data['nodes'] if n['type']=='start')
        goal=next(n['id'] for n in data['nodes'] if n['type']=='goal')
        result=dijkstra(graph,start,goal)
        assert result['travel_time']==path_time(graph,result['path'])
    if level!='easy':assert kinds=={'signal','rail','bridge'}


def test_authored_rounds_have_independent_cycles_and_completion(tmp_path):
    service=GameService(tmp_path/'records.json')
    config=deepcopy(service.config.value);config['map_source']='authored';service.save_config(config)
    first=service.get_random_map('expert');snapshot=deepcopy(service._graph(first['id']))
    service.get_random_map('expert')
    assert list(snapshot.edges(data=True))==list(service._graph(first['id']).edges(data=True))
    start=next(n['id'] for n in first['nodes'] if n['type']=='start')
    goal=next(n['id'] for n in first['nodes'] if n['type']=='goal')
    route=service.get_optimal_path(first['id'],start,goal)['path']
    completed=service.complete_route(first['round_id'],route[:3])
    assert completed['travel_time']==path_time(snapshot,completed['path'])
    result=service.finalize_round(first['round_id'],completed['path'])
    assert result['player_time']==completed['travel_time']


@pytest.mark.parametrize('change',[{'period':0},{'closed_for':10},{'phase':float('nan')},{'kind':'unknown'}])
def test_invalid_traffic_schedule_rejected(change):
    data=deepcopy(next(m for m in MapRepository().maps.values() if m['difficulty']=='normal'))
    add_traffic_events(data,random.Random(42))
    edge=next(e for e in data['edges'] if e.get('traffic_event'))
    edge['traffic_event'].update(change)
    with pytest.raises(ValueError,match='obstacle'):validate_map(data)
