from unittest.mock import patch
import pytest
from speed.leaderboard import LeaderboardStore
from speed.service import GameService


def test_persistence_order_limit_and_failures(tmp_path):
    store=LeaderboardStore(tmp_path/'leaderboard.json')
    for i in range(12):store.add('normal',f'Pilote {i}',{'player_time':20-i/2,'score':i})
    store.add('easy','Hugo',{'player_time':8,'score':99})
    assert len(store.entries['normal'])==10
    assert store.entries['normal'][0]['score']==11
    assert LeaderboardStore(store.path).entries==store.entries
    before=store.get()
    with patch('speed.leaderboard.os.replace',side_effect=OSError()):
        with pytest.raises(ValueError):store.add('easy','Test',{'player_time':5,'score':200})
    assert store.get()==before
    for name in ['', ' '*4, 'x'*25, None]:
        with pytest.raises(ValueError):store.add('easy',name,{'player_time':5,'score':2})
    store.path.write_text('{bad')
    assert LeaderboardStore(store.path).warning


def test_service_uses_finalized_values_and_rejects_assistance(tmp_path):
    service=GameService(tmp_path/'records.json')
    data=service.get_random_map('normal');rid=data['round_id']
    with pytest.raises(ValueError):service.submit_leaderboard(rid,'Hugo')
    start=next(n['id'] for n in data['nodes'] if n['type']=='start')
    goal=next(n['id'] for n in data['nodes'] if n['type']=='goal')
    route=service.get_optimal_path(data['id'],start,goal)['path']
    result=service.finalize_round(rid,route)
    service.submit_leaderboard(rid,'Hugo')
    service.submit_leaderboard(rid,'Autre nom')
    rows=service.get_leaderboard()['entries']['normal']
    assert rows==[{'name':'Hugo','time':result['player_time'],'score':result['score']}]
    service.rounds[rid]['result']['assisted']=True
    with pytest.raises(ValueError):service.submit_leaderboard(rid,'Test')


def test_ties_use_time_and_scores_remain_separate(tmp_path):
    store=LeaderboardStore(tmp_path/'leaderboard.json')
    for level in ('easy','normal','expert'):
        store.add(level,'Lent',{'player_time':12,'score':100})
        store.add(level,'Rapide',{'player_time':8,'score':100})
        store.add(level,'Plus de points',{'player_time':14,'score':101})
        assert [e['name'] for e in store.entries[level]]==['Plus de points','Rapide','Lent']
    assert LeaderboardStore(store.path).entries==store.entries
