"""Tests Eel + vrai Chromium. Activer avec SPEED_BROWSER_TESTS=1.

Les tests accélèrent les horodatages de manche, jamais les règles ni les RPC.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import json
from urllib.request import urlopen

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.skipif(os.environ.get("SPEED_BROWSER_TESTS") != "1", reason="Activer SPEED_BROWSER_TESTS=1 pour lancer Chromium")]
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    data_dir=tmp_path_factory.mktemp("scores")
    data_dir.joinpath("config.json").write_text(json.dumps({"map_source":"authored","sizes":{"easy":["small"],"normal":["medium"],"expert":["large"]}}))
    process = subprocess.Popen([sys.executable, "app.py", "--no-browser", "--port", str(port),
                                "--data-dir", str(data_dir)], cwd=ROOT)
    url = f"http://localhost:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Le serveur Eel n'a pas démarré")
            try:
                with urlopen(url, timeout=.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError("Délai de démarrage Eel dépassé")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("SPEED_TEST_BROWSER", "chromium")).launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def game(browser, server):
    page = browser.new_page(viewport={"width":1920,"height":1080})
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    def restrict(route):
        if not route.request.url.startswith(server):
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()
    page.route("**/*", restrict)
    page.goto(server)
    page.evaluate("async () => {window.game = await import('/js/app.js'); window.rules = await import('/js/state.js'); window.api = await import('/js/api.js');}")
    page.wait_for_function("game.state.demo !== null")
    page.evaluate("async () => {await api.call('save_config',{map_source:'authored',sizes:{easy:['small'],normal:['medium'],expert:['large']}});await game.home();}")
    yield page
    assert not errors, errors
    assert not external, external
    page.close()


def phase(page, name):
    page.wait_for_function("expected => game.state.phase === expected", arg=name)


def begin(page, replay=False, overview=True):
    page.locator("#replay-button" if replay else "#play-button").click()
    page.wait_for_function("game.state.phase === 'preparation' && game.state.ai !== null")
    page.evaluate("game.state.phaseStarted -= 2")
    phase(page, "countdown")
    page.evaluate("game.state.phaseStarted -= 4")
    phase(page, "selection")
    if overview:
        page.locator('#overview-button').click()
        page.wait_for_function("Math.abs(game.renderer.camera.zoom-game.renderer.camera.targetZoom)<.002")


def optimal_route(page):
    return page.evaluate("async () => (await api.call('get_optimal_path',game.state.map.id,game.state.start,game.state.goal)).path")


def click_node(page, node, button="left"):
    page.wait_for_function("Math.abs(game.renderer.camera.x-game.renderer.camera.targetX)<.5 && Math.abs(game.renderer.camera.y-game.renderer.camera.targetY)<.5 && Math.abs(game.renderer.camera.zoom-game.renderer.camera.targetZoom)<.002")
    point = page.evaluate("id => {const n=game.state.map.nodes.find(n=>n.id===id);return game.renderer.project(n.x,n.y)}", node)
    page.mouse.click(point["sx"], point["sy"], button=button)


def finish(page):
    page.wait_for_function("Number.isFinite(game.state.exploreStarted)")
    page.evaluate("game.state.exploreStarted -= game.state.exploreDuration + 3")
    phase(page, "race")
    page.evaluate("game.state.raceStarted -= Math.max(rules.pathTime(game.state.map,game.state.path),game.state.ai.travel_time)+1")
    phase(page, "result")


def screenshot(page, name):
    directory = ROOT / "artifacts"
    directory.mkdir(exist_ok=True)
    page.screenshot(path=str(directory / name))


def test_home_layout_help_sound_and_resizing(game):
    screenshot(game, "home-1920.png")
    game.locator("#help-button").click()
    assert game.locator("#help-dialog").is_visible()
    game.locator("#help-close").click()
    game.locator("#sound-button").click()
    assert game.locator("#sound-button").get_attribute("aria-pressed") == "true"
    game.locator("#sound-button").click()
    assert game.locator("#sound-button").get_attribute("aria-pressed") == "false"
    game.set_viewport_size({"width":1280,"height":720})
    game.wait_for_function("game.renderer.width === 1280")
    screenshot(game, "home-1280.png")
    begin(game)
    route = optimal_route(game)
    click_node(game, route[1])
    assert game.evaluate("game.state.path.length") == 2
    screenshot(game, "selection-1280.png")
    game.set_viewport_size({"width":1920,"height":1080})
    game.wait_for_function("game.renderer.width === 1920")
    click_node(game, route[2])
    assert game.evaluate("game.state.path.length") == 3


def test_selection_correction_segment_click_result_and_science(game):
    begin(game)
    assert game.locator("#validate-button").is_disabled()
    route = optimal_route(game)
    # Refus du saut directement à une destination non voisine.
    click_node(game, route[-1])
    assert game.evaluate("game.state.path.length") == 1
    click_node(game, route[1])
    game.keyboard.press("Backspace")
    assert game.evaluate("game.state.path.length") == 1
    click_node(game, route[1])
    click_node(game, route[1], "right")
    assert game.evaluate("game.state.path.length") == 1
    # Cliquer au milieu d'une route doit sélectionner son extrémité.
    point = game.evaluate("ids => {const [a,b]=ids.map(id=>game.state.map.nodes.find(n=>n.id===id)); return game.renderer.project((a.x+b.x)/2,(a.y+b.y)/2)}", route[:2])
    game.mouse.click(point["sx"],point["sy"])
    assert game.evaluate("game.state.path.length") == 2
    for node in route[2:]:
        click_node(game,node)
    assert game.locator("#validate-button").is_enabled()
    screenshot(game, "selection-1920.png")
    game.keyboard.press("Enter")
    game.wait_for_function("Number.isFinite(game.state.exploreStarted)")
    game.evaluate("game.state.exploreStarted -= game.state.exploreDuration + 3")
    phase(game,"race")
    screenshot(game,"race-1920.png")
    finish(game)
    assert game.evaluate("game.state.result.optimal")
    screenshot(game,"result-1920.png")
    game.locator("#science-button").click()
    phase(game,"science")
    assert "graphe" in game.locator("#science-panel").inner_text()
    screenshot(game,"science-1920.png")
    game.locator("#science-close").click()
    phase(game,"result")


def test_timeout_assisted_excluded_from_records(game):
    begin(game)
    route=optimal_route(game)
    click_node(game,route[1])
    game.evaluate("game.state.selectionStarted -= 16")
    game.wait_for_function("game.state.assisted === true")
    finish(game)
    assert game.evaluate("game.state.result.assisted && game.state.result.score === 0 && !game.state.result.new_record")
    assert game.locator("#result-subtitle").inner_text() == "Bien arrivé !"
    assert "GPS assisté" not in game.locator("body").inner_text()


def test_twenty_consecutive_rounds_without_reload(game):
    previous = None
    for i in range(20):
        begin(game,replay=i>0)
        ident=game.evaluate("game.state.map.id")
        assert ident != previous
        previous=ident
        for node in optimal_route(game)[1:]:
            click_node(game,node)
        game.locator("#validate-button").click()
        finish(game)
        assert game.evaluate("game.state.result.optimal && !game.state.result.assisted")
        assert game.locator("#replay-button").is_visible()


def test_expert_one_way_tie_and_escape(game):
    game.locator('[data-difficulty="expert"]').click()
    game.wait_for_function("game.state.demo && game.state.map.difficulty === 'expert'")
    begin(game)
    assert game.evaluate("game.state.map.edges.some(e=>e.one_way)")
    assert game.locator('#direction-hint').is_visible()
    screenshot(game,'expert-1920.png')
    for node in optimal_route(game)[1:]:
        click_node(game,node)
    game.locator("#validate-button").click()
    finish(game)
    assert game.evaluate("game.state.result.winner === 'tie'")
    game.keyboard.press("r")
    phase(game,"preparation")
    game.keyboard.press("Escape")
    phase(game,"home")


def test_late_response_ignored_on_reset(game):
    game.evaluate("""() => {
      window.originalCompute = eel.compute_ai_path;
      eel.compute_ai_path = (...args) => () => new Promise(resolve => {
        originalCompute(...args)().then(result => {window.releaseOldResult = () => resolve(result);});
      });
    }""")
    game.locator("#play-button").click()
    game.wait_for_function("typeof releaseOldResult === 'function'")
    game.evaluate("eel.compute_ai_path = originalCompute")
    game.locator("#home-button").click()
    game.wait_for_function("game.state.phase === 'home' && game.state.demo !== null")
    game.evaluate("releaseOldResult()")
    game.wait_for_timeout(100)
    assert game.evaluate("game.state.phase === 'home' && game.state.ai === null")


def test_connection_error_is_readable(game):
    game.evaluate("eel.get_random_map = () => async () => ({ok:false,error:'Le moteur est indisponible.'})")
    game.locator("#play-button").click()
    game.locator("#error-panel").wait_for(state="visible")
    assert "indisponible" in game.locator("#error-message").inner_text()


def test_real_time_assisted_round_and_animation_costs(game):
    game.evaluate("""() => {
      window.observedPhases = []; window.frameIntervals = [];
      let lastPhase = null, lastTime = null;
      function observe(t) {
        if (game.state.phase !== lastPhase) {
          observedPhases.push({phase: game.state.phase, time: t});
          lastPhase = game.state.phase;
        }
        if (lastTime !== null && frameIntervals.length < 180) frameIntervals.push(t-lastTime);
        lastTime = t;
        if (game.state.phase !== 'result') requestAnimationFrame(observe);
      }
      requestAnimationFrame(observe);
    }""")
    game.locator("#play-button").click()
    game.wait_for_function("game.state.phase === 'result'", timeout=90000)
    observed = game.evaluate("observedPhases")
    times = {entry["phase"]:entry["time"] for entry in observed}
    result = game.evaluate("game.state.result")
    assert result["assisted"]
    assert times["race"] - times["selection"] >= 14900
    assert game.evaluate("performance.now() - game.state.raceStarted*1000") >= max(result["player_time"],result["robot_time"])*1000
    # Le milieu est atteint après la moitié du roulage plus l'attente réelle
    # au feu/train/pont, située avant ce milieu.
    assert game.evaluate("""async () => {
      const {edgeJourney}=await import('/js/traffic.js');
      return game.state.map.edges.every(e => {
      const a = game.state.map.nodes.find(n=>n.id===e.source);
      const b = game.state.map.nodes.find(n=>n.id===e.target);
      const at = rules.vehiclePosition(game.state.map,[e.source,e.target],e.travel_time/2+edgeJourney(e,0).wait);
      return Math.abs(at.x-(a.x+b.x)/2)<1e-8 && Math.abs(at.y-(a.y+b.y)/2)<1e-8;
      });
    }""")
    intervals = sorted(game.evaluate("frameIntervals"))
    print(f"\nCadence observée en test headless : intervalle médian {intervals[len(intervals)//2]:.1f} ms")


def test_music_credits_and_clear_space_below_map(game):
    assert "Université de Rouen" in game.locator(".footer").inner_text()
    assert "Hugo Hamon" in game.locator(".footer").inner_text()
    assert game.locator("#current-date").get_attribute("datetime") == game.evaluate("new Date().toLocaleDateString('sv-SE')")
    assert game.locator(".difficulty legend").text_content() == "Niveau de difficulté"
    assert "PETITES ROUTES" not in game.locator("body").inner_text()
    for size in [{"width":1920,"height":1080},{"width":1280,"height":720}]:
        game.set_viewport_size(size)
        game.wait_for_function("width => game.renderer.width === width", arg=size["width"])
        assert game.evaluate("document.getElementById('demo-label').getBoundingClientRect().top > game.renderer.project(3.575,2.575,-.17).sy + 15")
        assert game.evaluate("document.getElementById('demo-label').getBoundingClientRect().bottom < document.querySelector('.footer').getBoundingClientRect().top")
    assert game.locator('#music-button').count()==0
    game.locator("#sound-button").click()
    game.wait_for_function("game.sound.musicTimer !== null && game.sound.musicNotes.size > 0")
    begin(game)
    assert game.evaluate("game.sound.musicTimer === null")
    assert game.evaluate("document.getElementById('stage-label').getBoundingClientRect().top > game.renderer.project(3.575,2.575,-.17).sy")
    assert game.evaluate("document.getElementById('stage-label').getBoundingClientRect().bottom < document.getElementById('route-controls').getBoundingClientRect().top")
    game.keyboard.press("Escape")
    game.wait_for_function("game.state.demo && game.sound.musicTimer !== null")
    game.locator("#sound-button").click()
    assert game.evaluate("game.sound.musicTimer === null")


def test_route_budget_prevents_long_detours(game):
    game.locator('[data-difficulty="easy"]').click()
    game.wait_for_function("game.state.demo && game.state.map.difficulty === 'easy'")
    begin(game)
    route = optimal_route(game)
    # Boucler entre deux carrefours finit par être refusé, tout en réservant
    # assez de temps pour rejoindre l’arrivée depuis le dernier clic accepté.
    for _ in range(12):
        click_node(game,route[1])
        click_node(game,route[0])
    assert game.evaluate("rules.pathTime(game.state.map,game.state.path)+game.state.map.remaining_times[game.state.path.at(-1)] <= game.state.map.max_travel_time+.0001")
    assert "dépasse" in game.locator("#stage-text").inner_text()
    game.evaluate("game.state.selectionStarted -= 16")
    game.wait_for_function("game.state.assisted")
    assert game.evaluate("rules.pathTime(game.state.map,game.state.path) <= game.state.map.max_travel_time+.0001")
    finish(game)


def test_science_shows_only_optimal_route(game):
    begin(game)
    for node in optimal_route(game)[1:]:
        click_node(game,node)
    game.locator("#validate-button").click()
    finish(game)
    assert "Bonus rapidité" in game.locator("#reflection-line").inner_text()
    assert game.evaluate("getComputedStyle(document.getElementById('science-button')).animationName") == "science-hop"
    game.locator("#science-button").click()
    assert game.evaluate("""() => {
      const r=game.renderer, original=r.drawPath, colors=[];
      r.drawPath=function(path,color,...rest){colors.push(color);return original.call(this,path,color,...rest)};
      r.render(performance.now()/1000);r.drawPath=original;
      return colors.length===1 && colors[0]===rules.COLORS.optimal && r.vehicles(performance.now()/1000).length===0;
    }""")
    game.locator("#science-close").click()
    assert game.evaluate("game.renderer.vehicles(performance.now()/1000).length") == 2
    game.emulate_media(reduced_motion="reduce")
    assert game.evaluate("getComputedStyle(document.getElementById('science-button')).animationName") == "none"


def test_vehicle_is_occluded_by_foreground_building(game):
    assert game.evaluate("""() => {
      const r=game.renderer;
      r.decorations=[{type:'building',x:1,y:1,w:.6,d:.6,h:.7,color:'#df9580',variant:1}];
      r.sceneKey=null;
      const pixel=p=>{const q=r.project(p.x,p.y,.18);return Array.from(r.ctx.getImageData(Math.round(q.sx*r.dpr),Math.round(q.sy*r.dpr),1,1).data).join(',')};
      const behind={x:1,y:.55,dx:1,dy:0},front={x:1,y:1.45,dx:1,dy:0};
      r.vehicles=()=>[];r.render(performance.now()/1000);
      const beforeBehind=pixel(behind),beforeFront=pixel(front);
      r.vehicles=()=>[{p:behind,color:rules.COLORS.player,robot:false,offset:0,elapsed:2,tag:false}];r.render(performance.now()/1000);
      const hidden=beforeBehind===pixel(behind);
      r.vehicles=()=>[{p:front,color:rules.COLORS.player,robot:false,offset:0,elapsed:2,tag:false}];r.render(performance.now()/1000);
      return hidden && beforeFront!==pixel(front);
    }""")


def configure_generated(page, size='huge'):
    page.locator('#config-button').click()
    page.wait_for_function("!document.getElementById('config-save').disabled")
    page.locator('#map-source').select_option('procedural')
    for level in ('easy','normal','expert'):
        for checkbox in page.locator(f'#size-options input[name="{level}"]').all():
            checkbox.set_checked(checkbox.get_attribute('value') == size)
    page.locator('#config-save').click()
    page.wait_for_function("!document.getElementById('config-dialog').open && game.state.demo && game.state.map.procedural")


def test_configuration_validation_and_persistence(game):
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    game.locator('#map-source').select_option('procedural')
    game.locator('#size-options input[name="easy"][value="small"]').uncheck()
    game.locator('#config-save').click()
    assert 'au moins une taille' in game.locator('#config-error').inner_text()
    assert game.locator('#config-dialog').is_visible()
    game.locator('#config-reset').click()
    game.locator('#size-options input[name="normal"][value="huge"]').check()
    screenshot(game, 'config-1920.png')
    game.set_viewport_size({'width':1280,'height':720})
    screenshot(game, 'config-1280.png')
    game.locator('#config-save').click()
    game.wait_for_function("!document.getElementById('config-dialog').open && game.state.demo && game.state.map.procedural")
    game.reload()
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    assert game.locator('#map-source').input_value()=='procedural'
    assert game.locator('#size-options input[name="normal"][value="medium"]').is_checked()
    assert game.locator('#size-options input[name="normal"][value="huge"]').is_checked()


@pytest.mark.parametrize('difficulty',['normal','expert'])
def test_large_city_intro_zoom_follow_and_cache(game,difficulty):
    configure_generated(game)
    game.locator(f'[data-difficulty="{difficulty}"]').click()
    game.wait_for_function("level=>game.state.demo && game.state.map.difficulty===level",arg=difficulty)
    game.set_viewport_size({'width':1280,'height':720})
    game.locator('#play-button').click()
    game.wait_for_function("game.state.phase==='preparation' && game.state.ai && game.renderer.mapId===game.state.map.id")
    assert game.evaluate('game.state.map.nodes.length')==63
    # Fixer trois instants de l’introduction vérifie ses véritables positions.
    assert game.evaluate("""() => {
      const r=game.renderer,c=r.camera,start=r.worldPoint(r.startNode.x,r.startNode.y),goal=r.worldPoint(r.goalNode.x,r.goalNode.y);
      c.intro(.2,start,goal,false);const a={x:c.x,y:c.y,z:c.zoom};
      c.intro(2.5,start,goal,false);const b={x:c.x,y:c.y,z:c.zoom};
      c.intro(4.1,start,goal,false);const d={x:c.x,y:c.y,z:c.zoom};
      return c.large && a.z>b.z*1.2 && d.z>b.z*1.2 && Math.hypot(a.x-d.x,a.y-d.y)>100;
    }""")
    phase(game,'countdown')
    game.evaluate('game.state.phaseStarted -= 4')
    phase(game,'selection')
    assert '40 s' in game.locator('#timer-label').inner_text()
    game.evaluate('window.cachedGround=game.renderer.layers.base; window.initialCamera={x:game.renderer.camera.x,y:game.renderer.camera.y}')
    assert game.evaluate("game.renderer.camera.viewport.y > document.querySelector('.game-hud').getBoundingClientRect().bottom")
    screenshot(game,'large-start-1280.png')
    # Parcourir des carrefours proches du bord, sans forcer la caméra.
    route=optimal_route(game)
    selected=1
    for node in route[1:]:
        click_node(game,node)
        assert game.evaluate('game.state.path.at(-1)')==node
        selected+=1
        if game.evaluate('Math.hypot(game.renderer.camera.targetX-initialCamera.x,game.renderer.camera.targetY-initialCamera.y)>20'):
            break
    assert game.evaluate('Math.hypot(game.renderer.camera.targetX-initialCamera.x,game.renderer.camera.targetY-initialCamera.y)>20')
    point=game.evaluate('({x:game.renderer.camera.viewport.x+game.renderer.camera.viewport.width/2,y:game.renderer.camera.viewport.y+game.renderer.camera.viewport.height/2})')
    game.mouse.move(point['x'],point['y'])
    game.mouse.wheel(0,1500)
    game.wait_for_function('Math.abs(game.renderer.camera.zoom-game.renderer.camera.fitZoom)<.002')
    assert game.evaluate('game.renderer.layers.base===window.cachedGround')
    assert game.evaluate('game.renderer.nodePoints.every(p=>game.renderer.camera.contains(p.sx,p.sy))')
    screenshot(game,'large-overview-1280.png')
    game.set_viewport_size({'width':1920,'height':1080})
    game.wait_for_function('game.renderer.width===1920')
    game.locator('#overview-button').click()
    game.wait_for_function('Math.abs(game.renderer.camera.zoom-game.renderer.camera.fitZoom)<.002')
    assert game.evaluate('game.renderer.layers.base===window.cachedGround')
    screenshot(game,'large-overview-1920.png')
    # Mesurer le coût JS du rendu avec les caches chauds, sans imposer une
    # fréquence écran au navigateur headless.
    timing=game.evaluate("""() => {
      const samples=[];for(let i=0;i<40;i++){const t=performance.now();game.renderer.render(t/1000);samples.push(performance.now()-t);}
      samples.sort((a,b)=>a-b);return {median:samples[20],p95:samples[38]};
    }""")
    print(f"\nRendu 63 carrefours ({difficulty}) : médiane {timing['median']:.2f} ms, p95 {timing['p95']:.2f} ms")
    for node in route[selected:]:
        click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("Number.isFinite(game.state.exploreStarted)")
    game.evaluate('game.state.exploreStarted -= game.state.exploreDuration + 3')
    phase(game,'race')
    assert game.evaluate('''() => {
      const r=game.renderer;r.render(performance.now()/1000);
      return [...game.state.path,...game.state.ai.path].every(id=>{
        const n=r.nodesById[id],p=r.project(n.x,n.y);return r.camera.contains(p.sx,p.sy);
      });
    }''')
    screenshot(game,'large-race-both-routes.png')
    finish(game)
    assert not game.evaluate('game.state.result.assisted')
    game.locator('#science-button').click()
    screenshot(game,'large-science-1920.png')


def test_fast_lane_animation_and_scrolling_credits(game):
    assert game.evaluate("""() => {
      const track=document.querySelector('.credits-track'),animation=track.getAnimations()[0];
      const duration=animation.effect.getTiming().duration;
      animation.pause();animation.currentTime=duration*.2;
      const x=track.getBoundingClientRect().left;
      animation.currentTime=duration*.4;
      const forward=track.getBoundingClientRect().left>x;
      const height=track.getBoundingClientRect().height;
      return forward && [...track.children].every(child=>child.getBoundingClientRect().height<=height);
    }""")
    configure_generated(game,'medium')
    assert game.evaluate("""() => {
      const r=game.renderer,old=r.ctx,bounds=r.visibleBounds;
      const canvas=document.createElement('canvas');canvas.width=r.worldWidth;canvas.height=r.worldHeight;
      r.ctx=canvas.getContext('2d');r.visibleBounds=null;
      try {
        r.fastRoads(1);const a=r.ctx.getImageData(0,0,canvas.width,canvas.height).data;
        r.ctx.clearRect(0,0,canvas.width,canvas.height);r.fastRoads(2);
        const b=r.ctx.getImageData(0,0,canvas.width,canvas.height).data;
        return a.some((value,i)=>value!==b[i]);
      }finally{r.ctx=old;r.visibleBounds=bounds;}
    }""")


def test_stress_test_measurement_and_exit(game):
    config=game.evaluate("async()=>await api.call('get_config')")
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    game.locator('#stress-start').click()
    phase(game,'stress')
    game.wait_for_function('game.stress.samples.length>3')
    assert game.evaluate('game.state.map.nodes.length')==192
    assert game.evaluate('game.renderer.vehicles(performance.now()/1000).length')==120
    screenshot(game,'stress-1920.png')
    game.wait_for_function('game.stress.finished',timeout=25000)
    assert 'FPS moyens' in game.locator('#stress-status').inner_text()
    assert game.evaluate('game.stress.samples.every(n=>Number.isFinite(n)&&n>0)')
    game.locator('#stress-exit').click()
    game.wait_for_function('game.state.demo && !game.stress.active')
    assert game.evaluate('game.renderer.vehicles(performance.now()/1000).length')==2
    assert game.evaluate("async()=>await api.call('get_config')")==config
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    game.locator('#stress-start').click()
    phase(game,'stress')
    game.locator('#stress-stop').click()
    assert game.evaluate('game.stress.finished')
    game.keyboard.press('Escape')
    game.wait_for_function('game.state.demo && !game.stress.active')


def test_comparative_benchmark_same_scene_and_report(game):
    game.locator('#config-button').click()
    game.goto(game.url.rsplit('/',1)[0]+'/benchmark.html')
    game.evaluate("async()=>{window.bench=await import('/js/benchmark.js');window.sceneTools=await import('/js/benchmark-scene.js');}")
    game.locator('#size').select_option('30,25')
    game.locator('#start').click()
    game.wait_for_function('bench.benchmark.scene!==null',timeout=30000)
    assert game.evaluate('bench.benchmark.settings.cars')==2
    game.wait_for_function('bench.benchmark.samples.length>3')
    screenshot(game,'benchmark-canvas-1920.png')
    game.wait_for_function('bench.benchmark.pass===1',timeout=20000)
    screenshot(game,'benchmark-webgl-1920.png')
    game.wait_for_function('bench.benchmark.report?.complete',timeout=45000)
    report=game.evaluate('bench.benchmark.report')
    assert [r['backend'] for r in report['runs']]==['canvas','webgl','webgl','canvas']
    assert all(r['seconds']>=7.8 and r['fps']>0 for r in report['runs'])
    assert report['settings']['width']==30 and report['settings']['height']==25
    assert report['summary']['webgl']['frames']>0
    assert game.locator('#report-text').input_value()
    assert not game.evaluate('bench.benchmark.running')
    # Même caméra, mêmes rectangles et même image, y compris les transparences.
    game.locator('#size').select_option('16,12')
    game.locator('#start').click()
    game.wait_for_function('bench.benchmark.scene!==null',timeout=30000)
    parity=game.evaluate("""() => {
      const b=bench.benchmark;cancelAnimationFrame(b.raf);
      const commands=sceneTools.sceneCommands(b.scene,3,b.settings,b.viewport);
      b.backends.canvas.draw(commands);b.backends.webgl.draw(commands);
      const w=b.viewport.width,h=b.viewport.height,gl=b.backends.webgl.gl;
      const a=b.backends.canvas.ctx.getImageData(0,0,w,h).data,c=new Uint8Array(w*h*4);
      gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,c);
      let error=0,count=0,changed=0;
      for(let y=0;y<h;y+=4)for(let x=0;x<w;x+=4){const i=(y*w+x)*4,j=((h-1-y)*w+x)*4;
        for(let k=0;k<3;k++){error+=Math.abs(a[i+k]-c[j+k]);count++;}
        if(Math.abs(a[i]-237)>15)changed++;
      }
      return {error:error/count,changed,glError:gl.getError()};
    }""")
    assert parity['glError']==0
    assert parity['changed']>1000
    assert parity['error']<5,parity
    game.locator('#stop').click()
    assert 'incomplet' in game.locator('#results').inner_text()
    assert not game.evaluate('bench.benchmark.report.complete')


def test_comparative_benchmark_unavailable_and_resize(game):
    game.goto(game.url.rsplit('/',1)[0]+'/benchmark.html')
    game.evaluate("async()=>{window.bench=await import('/js/benchmark.js');}")
    game.evaluate("""() => {const original=HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='webgl'?null:original.call(this,type,...args)};
    }""")
    game.locator('#start').click()
    game.wait_for_function('bench.benchmark.report!==null')
    assert 'WebGL indisponible' in game.locator('#status').inner_text()
    assert not game.evaluate('bench.benchmark.report.complete')
    game.reload()
    game.evaluate("async()=>{window.bench=await import('/js/benchmark.js');}")
    game.locator('#start').click()
    game.set_viewport_size({'width':1280,'height':720})
    game.wait_for_function('bench.benchmark.report!==null')
    assert not game.evaluate('bench.benchmark.running')
    assert not game.evaluate('bench.benchmark.report.complete')


def test_game_render_caches_and_750_node_stress(game):
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    game.locator('#stress-size').select_option('30,25')
    game.locator('#stress-cars').select_option('2')
    game.locator('#stress-motion').select_option('moving')
    game.locator('#stress-start').click()
    # Mesure passive : les captures et sondes ne perturbent pas les FPS.
    game.wait_for_function('game.stress.finished',timeout=35000)
    assert game.evaluate('game.state.map.nodes.length')==750
    assert game.evaluate('game.renderer.vehicles(performance.now()/1000).length')==2
    assert game.evaluate("""() => {
      const r=game.renderer;
      return r.layers.base.tiles.length>1 && r.layers.base.tiles.every(t=>t.canvas.width<=516&&t.canvas.height<=516)
        && r.spriteAtlas.entries.size<50 && r.scenery.length>1000;
    }""")
    # Une image en régime établi ne doit reconstruire ni rues ni voitures.
    assert game.evaluate("""() => {
      const r=game.renderer,keys=['ground','roads','paintCar','paintFastEdge','building','tree'],old=keys.map(k=>r[k]);
      for(const key of keys)r[key]=()=>{throw new Error('Dessin reconstruit : '+key)};
      try{r.render(performance.now()/1000);return true;}finally{keys.forEach((k,i)=>r[k]=old[i]);}
    }""")
    screenshot(game,'optimized-stress-750.png')
    game.wait_for_function('game.stress.finished',timeout=25000)
    intervals=game.evaluate('game.stress.samples')
    print(f'\nJeu optimisé, 750 carrefours et 2 voitures : {len(intervals)*1000/sum(intervals):.1f} FPS headless')
    costs=game.evaluate("""() => {
      const r=game.renderer,keys=['layout','fastRoads','markers','drawSceneryAndVehicles'],totals={},original={};
      for(const key of keys){totals[key]=0;original[key]=r[key];r[key]=function(...args){const t=performance.now();const result=original[key].apply(this,args);totals[key]+=performance.now()-t;return result;};}
      try{for(let i=0;i<10;i++)r.render(performance.now()/1000);}finally{for(const key of keys)r[key]=original[key];}
      return Object.fromEntries(keys.map(k=>[k,totals[k]/10]));
    }""")
    print(f'Coût JS moyen par étape (ms) : {costs}')
    game.keyboard.press('Escape')
    game.wait_for_function('game.state.demo && !game.stress.active')
    game.wait_for_function('game.renderer.mapId===game.state.map.id && game.renderer.scenery.length<100')


def test_hidden_robot_continuous_credits_and_race_framing(game):
    assert game.locator('.benchmark-link').count() == 0
    assert game.evaluate("""() => {
      const t=document.querySelector('.credits-track'),a=t.getAnimations()[0];
      a.pause();
      return [0,.5,.999].every(f=>{
        a.currentTime=a.effect.getTiming().duration*f;
        const r=t.getBoundingClientRect();return r.left<=0 && r.right>=innerWidth;
      }) && document.querySelectorAll('#current-date').length===1;
    }""")
    begin(game)
    assert game.evaluate('game.renderer.camera.viewport.height / innerHeight > .59')
    assert game.evaluate("""() => {
      const r=game.renderer,draw=r.drawPath;let calls=0;
      r.drawPath=()=>calls++;
      try {r.exploration(game.state.exploreStarted+game.state.exploreDuration+1);}
      finally {r.drawPath=draw;}
      return calls===0;
    }""")
    route=optimal_route(game)
    for node in route[1:]: click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("Number.isFinite(game.state.exploreStarted)")
    game.evaluate('game.state.exploreStarted -= game.state.exploreDuration + 3')
    phase(game,'race')
    assert game.evaluate("""() => {
      const r=game.renderer;r.render(performance.now()/1000);
      return [...game.state.path,...game.state.ai.path].every(id=>{
        const n=r.nodesById[id],p=r.project(n.x,n.y);return r.camera.contains(p.sx,p.sy);
      });
    }""")
    screenshot(game,'race-both-routes.png')


def test_city_extends_beyond_camera_safe_area(game):
    configure_generated(game)
    begin(game, overview=False)
    assert game.evaluate("""() => {
      const r=game.renderer,v=r.camera.viewport,d=r.renderViewport;
      const corner=r.camera.world(0,0);
      return d.x===0 && d.y===0 && d.width===innerWidth && d.height===innerHeight
        && r.visibleBounds.top===corner.sy && r.visibleBounds.left===corner.sx
        && v.y>0 && v.height<d.height;
    }""")
    # Un carrefour visible hors de la zone sûre reste une cible de clic.
    assert game.evaluate("""() => {
      const r=game.renderer,c=r.camera,n=r.startNode;
      const p=r.worldPoint(n.x,n.y),v=c.viewport;
      c.x=p.sx-(25-v.x-v.width/2)/c.zoom;
      c.y=p.sy-(innerHeight/2-v.y-v.height/2)/c.zoom;
      c.targetX=c.x;c.targetY=c.y;r.layout(performance.now()/1000);
      const screen=r.project(n.x,n.y);
      return !c.contains(screen.sx,screen.sy) && r.hitTest(screen.sx,screen.sy)===n.id;
    }""")
    game.locator('#overview-button').click()
    game.wait_for_function('Math.abs(game.renderer.camera.zoom-game.renderer.camera.targetZoom)<.002')
    screenshot(game,'city-without-inner-frame.png')


def test_corridor_shortcut_rules(game):
    assert game.evaluate("""() => {
      const make=(extra=[])=>{
        const nodes=Array.from({length:8},(_,i)=>({id:String(i),x:i,y:0}));
        const edges=Array.from({length:6},(_,i)=>({source:String(i),target:String(i+1),travel_time:1}));
        return {phase:'selection',locked:false,path:['0'],goal:'6',map:{nodes,edges:[...edges,...extra],remaining_times:Object.fromEntries(nodes.map(n=>[n.id,6-Number(n.id)])),max_travel_time:10}};
      };
      let s=make();if(!rules.addNode(s,'6')||s.path.join()!= '0,1,2,3,4,5,6')return false;
      rules.undoNode(s);if(s.path.at(-1)!=='5')return false;
      s=make([{source:'3',target:'7',travel_time:1}]);
      s.map.nodes[4].y=1; // Une bifurcation suivie d’un virage reste un choix manuel.
      if(rules.addNode(s,'6')||s.path.length!==1)return false;
      if(!rules.addNode(s,'3'))return false; // On peut rejoindre la bifurcation.
      s=make();s.map.edges[3]={source:'4',target:'3',one_way:true,travel_time:1};
      if(rules.addNode(s,'6'))return false;
      s=make();s.map.max_travel_time=5;if(rules.addNode(s,'6')||s.path.length!==1)return false;
      s=make();s.goal='3';if(rules.addNode(s,'6'))return false;
      s=make();s.locked=true;if(rules.addNode(s,'6'))return false;
      s=make();s.map.edges.push({source:'6',target:'0',one_way:true,travel_time:1});s.goal='7';
      return !rules.addNode(s,'7');
    }""")


def test_tile_seams_at_fractional_zoom(game):
    assert game.evaluate("""async () => {
      const {TileLayer}=await import('/js/render-cache.js');
      const canvas=document.createElement('canvas');canvas.width=canvas.height=900;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});
      const r={ctx,worldWidth:1536,worldHeight:1536,visible:()=>true};
      for(const scale of [1,.5]){
        const layer=new TileLayer(r,()=>{r.ctx.fillStyle='#39754b';r.ctx.fillRect(-20,-20,1600,1600);},scale);
        for(const zoom of [.083,.317,.73,1.15]){
          ctx.resetTransform();ctx.clearRect(0,0,900,900);ctx.setTransform(zoom,0,0,zoom,13.37,7.29);
          layer.draw(r);
          const data=ctx.getImageData(0,0,900,900).data;
          for(let y=12;y<Math.min(895,1536*zoom);y++)for(let x=18;x<Math.min(895,1536*zoom);x++){
            const i=(y*900+x)*4;if(data[i+3]!==255)return false;
          }
        }
      }
      return true;
    }""")


def test_straight_shortcut_with_side_roads(game):
    assert game.evaluate("""() => {
      const make=(vertical=false)=>({phase:'selection',locked:false,path:['0'],goal:'5',map:{
        nodes:[...Array.from({length:6},(_,i)=>({id:String(i),x:vertical?0:i,y:vertical?i:0})),{id:'side',x:2,y:2}],
        edges:[...Array.from({length:5},(_,i)=>({source:String(i),target:String(i+1),travel_time:1})),{source:'2',target:'side',travel_time:1}],
        remaining_times:{0:5,1:4,2:3,3:2,4:1,5:0},max_travel_time:10
      }});
      for(const vertical of [false,true]){
        const s=make(vertical);if(!rules.addNode(s,'5')||s.path.join()!=='0,1,2,3,4,5')return false;
        rules.undoNode(s);if(s.path.at(-1)!=='4')return false;
      }
      let s=make();s.map.edges[3]={source:'4',target:'3',travel_time:1,one_way:true};
      if(rules.addNode(s,'5')||s.path.length!==1)return false;
      s=make();s.map.edges.splice(3,1);if(rules.addNode(s,'5'))return false;
      s=make();s.map.max_travel_time=4;if(rules.addNode(s,'5')||s.path.length!==1)return false;
      s=make();s.goal='3';if(rules.addNode(s,'5'))return false;
      s=make();s.path=['5'];s.goal='0';s.map.remaining_times[0]=0;
      return rules.addNode(s,'0')&&s.path.join()==='5,4,3,2,1,0';
    }""")


def test_custom_size_configuration_and_play(game):
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    game.locator('#map-source').select_option('procedural')
    game.locator('#custom-width').fill('12')
    game.locator('#custom-height').fill('10')
    game.locator('#custom-add').click()
    assert game.locator('input[name="normal"][value="custom_12x10"]').is_checked()
    game.locator('input[name="normal"][value="medium"]').uncheck()
    game.locator('#config-save').click()
    game.wait_for_function("game.state.demo && game.state.map.nodes.length===120")
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    assert game.locator('input[name="normal"][value="custom_12x10"]').is_checked()
    game.locator('#config-close').click()
    begin(game)
    assert game.evaluate('game.state.map.nodes.length')==120
    screenshot(game,'custom-city-120.png')
    route=optimal_route(game)
    for node in route[1:]:click_node(game,node)
    game.locator('#validate-button').click()
    finish(game)
    assert not game.evaluate('game.state.result.assisted')


def test_scene_surfaces_released_between_twenty_maps(game):
    assert game.evaluate("""async () => {
      const {stressMap}=await import('/js/stress.js');
      const r=game.renderer,s=game.state,original=s.map,phase=s.phase;
      const resources=()=>[...Object.values(r.layers||{}).flatMap(l=>l.tiles.map(t=>t.canvas)),...(r.spriteAtlas?.pages||[]),...(r.fastAtlas?.pages||[])];
      const old=[];let expected=null;
      try {
        s.phase='stress';s.stressMotion='fixed';
        for(let i=0;i<20;i++){
          old.push(...resources());
          const map=stressMap(12,10);map.id+='-cleanup-'+i;s.map=map;
          r.prepareDecorations(map);r.prepareSceneLayers();
          if(!old.every(c=>c.width===0&&c.height===0))return false;
          const bytes=resources().reduce((sum,c)=>sum+c.width*c.height*4,0);
          if(expected!==null&&bytes!==expected)return false;
          expected=bytes;
        }
        return expected>0;
      } finally {
        s.map=original;s.phase=phase;r.prepareDecorations(original);r.prepareSceneLayers();
      }
    }""")
    assert game.evaluate('game.renderer.layers.base.tiles.length>0')


def test_named_leaderboard_and_tabs(game):
    begin(game)
    for node in optimal_route(game)[1:]:click_node(game,node)
    game.locator('#validate-button').click();finish(game)
    game.set_viewport_size({'width':1280,'height':720})
    screenshot(game,'leaderboard-name-1280.png')
    game.locator('#player-name').fill('Hugo <pilote>')
    game.locator('#player-name').press('Backspace')
    assert game.evaluate("game.state.phase==='result'")
    game.locator('#player-name').fill('Hugo <pilote>')
    game.locator('#player-name').press('Enter')
    game.wait_for_function("document.getElementById('ranking-form').hidden")
    screenshot(game,'leaderboard-result.png')
    game.locator('#home-button').click()
    game.wait_for_function("document.getElementById('rank-rows').textContent.includes('Hugo <pilote>')")
    game.locator('#leaderboard-button').click()
    assert game.locator('#rank-rows pilote').count()==0
    for size in [{'width':1920,'height':1080},{'width':1280,'height':720}]:
        game.set_viewport_size(size)
        game.wait_for_function('w=>game.renderer.width===w',arg=size['width'])
        assert game.locator('#leaderboard').is_visible()
        assert game.evaluate("document.getElementById('leaderboard').getBoundingClientRect().right < game.renderer.camera.viewport.x")
        screenshot(game,f"leaderboard-home-{size['width']}.png")
    game.locator('#rank-easy').click()
    assert game.locator('#rank-easy').get_attribute('aria-selected')=='true'
    game.locator('#rank-easy').press('ArrowRight')
    assert game.locator('#rank-normal').get_attribute('aria-selected')=='true'


def test_leaderboard_view_keeps_demo_running(game):
    game.evaluate('window.demoBefore=game.state.demo;window.mapBefore=game.state.map.id')
    game.locator('#leaderboard-button').click()
    assert game.locator('#home-panel').is_hidden()
    assert game.locator('#leaderboard').is_visible()
    assert game.locator('#rank-note').count()==0
    assert game.evaluate("game.state.phase==='home' && game.state.demo===demoBefore && game.state.map.id===mapBefore")
    assert game.evaluate("JSON.stringify(game.renderer.vehicles(performance.now()/1000))!==JSON.stringify(game.renderer.vehicles(performance.now()/1000+1))")
    game.keyboard.press('Escape')
    assert game.locator('#home-panel').is_visible()
    assert game.locator('#leaderboard').is_hidden()
    game.locator('#leaderboard-button').click()
    game.locator('#leaderboard-back').click()
    assert game.evaluate("document.activeElement.id==='leaderboard-button'")


@pytest.mark.parametrize('difficulty',['easy','normal','expert'])
def test_robot_search_after_player_with_pause(game,difficulty):
    game.locator(f'[data-difficulty="{difficulty}"]').click()
    game.wait_for_function('level=>game.state.demo && game.state.map.difficulty===level',arg=difficulty)
    begin(game)
    assert game.locator('#ai-explanation').is_hidden()
    assert game.evaluate('game.state.exploreStarted===Infinity')
    assert 'attend' in game.locator('#robot-status').inner_text()
    for node in optimal_route(game)[1:]:click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("game.state.phase==='waiting' && Number.isFinite(game.state.exploreStarted)")
    assert game.locator('#ai-explanation').is_visible()
    assert game.evaluate('performance.now()/1000-game.state.exploreStarted<2')
    game.evaluate('game.state.exploreStarted -= game.state.exploreDuration * .4')
    game.locator('#ai-pause').click()
    assert game.evaluate('game.state.aiPaused')
    screenshot(game,f'robot-search-{difficulty}.png')
    game.evaluate('game.state.exploreStarted -= game.state.exploreDuration + 4')
    game.wait_for_timeout(200)
    assert game.evaluate("game.state.phase==='waiting'")
    game.locator('#ai-skip' if difficulty=='expert' else '#ai-pause').click()
    phase(game,'race')
    assert game.locator('#ai-explanation').is_hidden()


def test_configurable_robot_timing_and_readable_messages(game):
    assert game.evaluate("""() => {
      const s={ai:{events:Array(100)},exploreStarted:10,exploreDuration:12,aiMessageSeconds:2};
      return rules.explorationProgress(s,13.5)<rules.explorationProgress(s,14)
        && rules.acceptExplanation(s,'explore',0)
        && !rules.acceptExplanation(s,'advance',1)
        && rules.acceptExplanation(s,'explore',1.5)
        && rules.acceptExplanation(s,'advance',2)
        && !rules.acceptExplanation(s,'done',3)
        && rules.acceptExplanation(s,'done',4);
    }""")
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    for level in ['easy','normal','expert']:
        game.locator(f'#ai-time-{level}').fill('6')
    game.locator('#ai-time-message_seconds').fill('2')
    game.locator('#config-save').click()
    game.wait_for_function("game.state.demo && game.state.map.ai_timing.normal===6")
    game.locator('#config-button').click()
    game.wait_for_function("!document.getElementById('config-save').disabled")
    assert game.locator('#ai-time-message_seconds').input_value()=='2'
    screenshot(game,'robot-timing-settings.png')
    game.locator('#config-close').click()
    begin(game)
    for node in optimal_route(game)[1:]:click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("game.state.phase==='waiting' && game.state.aiMessageKind!==null")
    kind=game.evaluate('game.state.aiMessageKind')
    initial=game.evaluate('game.state.aiStep')
    assert game.evaluate('game.state.exploreDuration===6')
    game.wait_for_timeout(1100)
    assert game.evaluate('game.state.aiMessageKind')==kind
    assert game.evaluate('game.state.aiStep')>initial
    game.wait_for_function('game.state.aiMessageChangedAt>=2')
    assert game.evaluate('performance.now()/1000-game.state.exploreStarted>=2')
    game.locator('#ai-skip').click()
    phase(game,'race')


def test_small_map_resolution_and_expert_explanation(game):
    assert game.evaluate('game.state.map.nodes.length<=20 && game.renderer.cacheScale>=2')
    assert game.evaluate('game.renderer.spriteAtlas.pages.every(c=>c.width>=2048)')
    game.evaluate('window.oldLayers=game.renderer.layers')
    game.set_viewport_size({'width':1280,'height':720})
    game.wait_for_function('game.renderer.width===1280')
    assert game.evaluate('game.renderer.layers===oldLayers')
    game.locator('[data-difficulty="expert"]').click()
    game.wait_for_function("game.state.demo && game.state.map.difficulty==='expert'")
    begin(game)
    for node in optimal_route(game)[1:]:click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("document.getElementById('ai-explanation-text').textContent.includes('Dijkstra')")
    text=game.locator('#ai-explanation-text').inner_text()
    game.evaluate('game.state.exploreStarted -= game.state.exploreDuration*.4')
    game.wait_for_timeout(100)
    assert game.locator('#ai-explanation-text').inner_text()==text
    screenshot(game,'small-map-sharp-expert.png')
    game.locator('#ai-skip').click()
    phase(game,'race')


def test_search_heat_history_and_backtracking(game):
    assert game.evaluate("""async () => {
      const {updateExploration}=await import('/js/exploration.js');
      const events=[{node:'a',kind:'explore'},
        {node:'b',source:'a',kind:'explore'},
        {node:'b',source:'a',kind:'advance'},
        {node:'a',source:'b',kind:'backtrack'},
        {node:'c',source:'a',kind:'advance'}];
      const s={ai:{events},start:'a',exploreStarted:0,exploreDuration:5};
      let h=updateExploration(null,s,0);
      if(h.visits.size || h.route.length!==1)return false;
      h=updateExploration(h,s,2);
      if(h.visits.size!==2 || h.visits.get('b').count!==1 || h.visits.has('c'))return false;
      h=updateExploration(h,s,4);
      if(h.route.join()!=='a,b,a' || h.visits.get('a').count!==2 || h.visits.get('b').count!==2)return false;
      s.aiPaused=true;s.aiPauseTime=4;
      h=updateExploration(h,s,100);
      if(h.count!==4 || h.visits.has('c'))return false;
      s.aiPaused=false;h=updateExploration(h,s,5);
      if(h.route.join()!=='a,b,a,c' || h.visits.size!==3)return false;
      h=updateExploration(h,s,1);
      if(h.count!==1 || h.visits.size!==1 || h.route.join()!=='a')return false;
      s.ai.events=[{node:'c',kind:'explore'}];
      return updateExploration(h,s,5).visits.size===1;
    }""")


@pytest.mark.parametrize('difficulty',['easy','normal','expert'])
def test_current_search_heat_and_progressive_route(game,difficulty):
    game.locator(f'[data-difficulty="{difficulty}"]').click()
    game.wait_for_function('level=>game.state.demo && game.state.map.difficulty===level',arg=difficulty)
    begin(game)
    for node in optimal_route(game)[1:]:click_node(game,node)
    game.locator('#validate-button').click()
    game.wait_for_function("game.state.phase==='waiting' && Number.isFinite(game.state.exploreStarted)")
    # Freeze the algorithm clock, not the render loop, to check persistence.
    game.evaluate("""() => {
      const s=game.state;s.aiPaused=true;s.aiPauseTime=s.exploreStarted+s.exploreDuration*.5;
      game.renderer.render(performance.now()/1000);
      window.heatBefore=[...game.renderer.explored.visits];
    }""")
    assert game.locator('.search-legend').is_visible()
    assert game.evaluate("""() => {
      const r=game.renderer,s=game.state,draw=r.drawGrowingRoute;let calls=0;
      r.drawGrowingRoute=(...args)=>{calls++;return draw.apply(r,args)};
      try {r.exploration(performance.now()/1000+100);} finally {r.drawGrowingRoute=draw;}
      return JSON.stringify([...r.explored.visits])===JSON.stringify(heatBefore)
        && (s.map.ai_type!=='dijkstra' || calls===0);
    }""")
    game.evaluate("""() => {
      const s=game.state;s.aiPauseTime=s.exploreStarted+s.exploreDuration*.8;
      game.renderer.render(performance.now()/1000);
    }""")
    assert game.evaluate('heatBefore.every(([id,v])=>game.renderer.explored.visits.get(id).count>=v.count)')
    game.wait_for_function("document.getElementById('ai-focus').textContent.includes('carrefour')")
    if difficulty=='expert':
        assert 'Il examine le carrefour' in game.locator('#ai-focus').inner_text()
        assert game.evaluate("""() => {
          const r=game.renderer,ellipse=r.ellipse,targets=[];
          r.ellipse=(x,y,rx,ry,fill,stroke,...args)=>{
            if(stroke==='#523078')targets.push({x,y});
            return ellipse.call(r,x,y,rx,ry,fill,stroke,...args);
          };
          try {r.render(performance.now()/1000);} finally {r.ellipse=ellipse;}
          const e=r.explored.events[r.explored.count-1],n=r.nodesById[e.node],p=r.worldPoint(n.x,n.y,.045);
          return targets.length===1 && targets[0].x===p.sx && targets[0].y===p.sy;
        }""")
    screenshot(game,f'heat-search-{difficulty}.png')
    assert game.evaluate("""() => {
      const s=game.state,r=game.renderer,draw=r.drawGrowingRoute;let route,amounts;
      r.drawGrowingRoute=(path,fractions)=>{route=path;amounts=fractions;return draw.call(r,path,fractions)};
      try {
        s.aiPauseTime=s.exploreStarted+s.exploreDuration+.73;r.render(performance.now()/1000);
        if(JSON.stringify(route)!==JSON.stringify(s.ai.path))return false;
        if(s.map.ai_type==='dijkstra' && (!amounts.some(f=>f>0&&f<1)||amounts.at(-1)!==0))return false;
        s.aiPauseTime=s.exploreStarted+s.exploreDuration+2;r.render(performance.now()/1000);
        return amounts.every(f=>f===1);
      } finally {r.drawGrowingRoute=draw;}
    }""")
    assert game.evaluate("""() => {
      const r=game.renderer,stamp=r.heatStamp;let calls=0;
      r.heatStamp=(...args)=>{calls++;return stamp.apply(r,args)};
      try {r.render(performance.now()/1000);} finally {r.heatStamp=stamp;}
      return calls===0;
    }""")
    screenshot(game,f'heat-route-{difficulty}.png')
    game.set_viewport_size({'width':390,'height':844})
    game.wait_for_function('game.renderer.width===390')
    game.wait_for_function('Math.abs(game.renderer.camera.zoom-game.renderer.camera.targetZoom)<.002')
    assert game.evaluate("""() => {
      const v=game.renderer.camera.viewport,p=document.getElementById('ai-explanation').getBoundingClientRect();
      return v.y+v.height<=p.top && p.left>=0 && p.right<=innerWidth
        && game.state.map.nodes.every(n=>{const point=game.renderer.project(n.x,n.y);return game.renderer.camera.contains(point.sx,point.sy)});
    }""")
    screenshot(game,f'heat-mobile-{difficulty}.png')
    game.locator('#ai-skip').click()
    phase(game,'race')


def test_search_colours_clear_between_steps(game):
    assert game.evaluate("""async () => {
      const {updateExploration,heatOpacity}=await import('/js/exploration.js');
      const events=[{node:'a',kind:'explore'},{node:'b',kind:'explore'},
        {node:'b',kind:'advance'},{node:'c',kind:'explore'},
        {node:'c',kind:'advance'}];
      const s={ai:{events},map:{ai_type:'bfs'},start:'a',exploreStarted:0,exploreDuration:5};
      let h=updateExploration(null,s,2.5);
      if(heatOpacity(h.heat.get('a'),s,2.5)!==1)return false;
      h=updateExploration(h,s,3.2);
      const fading=heatOpacity(h.heat.get('a'),s,3.2);
      if(fading<=0 || fading>=1 || heatOpacity(h.heat.get('a'),s,3.5)!==0)return false;
      s.aiPaused=true;s.aiPauseTime=3.2;
      if(heatOpacity(h.heat.get('a'),s,100)!==fading)return false;
      s.aiPaused=false;h=updateExploration(h,s,4.5);
      if(heatOpacity(h.heat.get('a'),s,4.5)!==0 || heatOpacity(h.heat.get('c'),s,4.5)!==1)return false;
      h=updateExploration(h,s,5.5);
      if([...h.heat.values()].some(c=>heatOpacity(c,s,5.5)>0))return false;
      s.map.ai_type='dijkstra';s.exploreDuration=10;
      s.ai.events=Array.from({length:20},(_,i)=>({node:String(i),kind:'settle'}));
      h=updateExploration(null,s,5.2);
      if(heatOpacity(h.heat.get('0'),s,5.2)!==0 || heatOpacity(h.heat.get('9'),s,5.2)!==1)return false;
      // Reduced motion removes old colours immediately at the step boundary.
      return heatOpacity({...h.heat.get('9'),retiredAt:5.1},s,5.2,true)===0;
    }""")


def test_generated_routes_need_multiple_real_clicks(game):
    import networkx as nx
    from speed.generator import generate_map
    from speed.maps import validate_map

    cases=[]
    for difficulty,size,minimum in [('normal','medium',4),('expert','small',5),('expert','large',5),('expert','custom_3x4',5)]:
        for seed in [3,42,2026]:
            data=generate_map(difficulty,size,seed)
            graph=validate_map(data)
            start=next(n['id'] for n in data['nodes'] if n['type']=='start')
            goal=next(n['id'] for n in data['nodes'] if n['type']=='goal')
            data['remaining_times']=nx.single_source_dijkstra_path_length(graph.reverse(copy=False),goal,weight='travel_time')
            from speed.algorithms import dijkstra
            cases.append({'map':data,'start':start,'goal':goal,'minimum':minimum,'optimal':dijkstra(graph,start,goal)['travel_time']})
    # Independent check using the actual UI click handler, trying every node
    # as a target. Covers straight shortcuts, automatic turns and one-way roads.
    assert game.evaluate("""cases => cases.every(({map,start,goal,minimum,optimal})=>{
      const limit=optimal+.009001;
      let frontier=[{path:[start],cost:0}];
      for(let clicks=1;clicks<minimum;clicks++){
        const next=new Map();
        for(const candidate of frontier)for(const target of map.nodes){
          const s={map,start,goal,phase:'selection',locked:false,path:[...candidate.path]};
          if(!rules.addNode(s,target.id))continue;
          const cost=rules.pathTime(map,s.path);
          if(cost+map.remaining_times[target.id]>limit)continue;
          if(target.id===goal)return false;
          const key=s.path.slice(-2).join('>');
          if(!next.has(key)||next.get(key).cost>cost)next.set(key,{path:s.path,cost});
        }
        frontier=[...next.values()];
      }
      return true;
    })""", cases)


def test_traffic_clock_matches_server_and_stops_cars(game):
    from speed.traffic import edge_arrival
    edge={'id':'event','source':'a','target':'b','travel_time':1.,
          'traffic_event':{'kind':'signal','period':6.,'closed_for':3.,'phase':0.}}
    cases=[{'departure':t,'arrival':edge_arrival(edge,t)} for t in [0,.1,2.6499,2.65,3,5.6499,5.65,6,7.123,12]]
    assert game.evaluate("""async ({edge,cases}) => {
      const {edgeJourney}=await import('/js/traffic.js');
      if(!cases.every(({departure,arrival})=>Math.abs(edgeJourney(edge,departure).arrival-arrival)<1e-8))return false;
      const map={nodes:[{id:'a',x:0,y:0},{id:'b',x:1,y:0}],edges:[edge]};
      const before=rules.vehiclePosition(map,['a','b'],.2),waiting=rules.vehiclePosition(map,['a','b'],1),
        still=rules.vehiclePosition(map,['a','b'],2),after=rules.vehiclePosition(map,['a','b'],3.2);
      return before.x<.35 && waiting.waiting && waiting.x===.35 && waiting.x===still.x
        && after.x>.35 && !after.waiting && rules.pathTime(map,['a','b'])===3.65
        && rules.vehiclePosition(map,['a','b'],3.65).finished;
    }""",{'edge':edge,'cases':cases})


def test_live_traffic_wait_and_final_score(game):
    import networkx as nx
    from speed.maps import validate_map
    from speed.algorithms import path_time
    from speed.traffic import traffic_wait, edge_arrival, STOP_FRACTION

    begin(game)
    data=game.evaluate('game.state.map')
    graph=validate_map(data)
    start=game.evaluate('game.state.start');goal=game.evaluate('game.state.goal')
    chosen=None
    for i,path in enumerate(nx.shortest_simple_paths(graph,start,goal,weight='travel_time')):
        departure=0
        for a,b in zip(path,path[1:]):
            edge=graph[a][b];at=departure+edge['travel_time']*STOP_FRACTION
            wait=traffic_wait(edge,at)
            if wait>.3 and path_time(graph,path)<=data['max_travel_time']:
                chosen=(path,at+wait/2,path_time(graph,path));break
            departure=edge_arrival(edge,departure)
        if chosen or i>200:break
    assert chosen is not None
    path,wait_at,total=chosen
    for node in path[1:]:click_node(game,node)
    assert game.evaluate('game.state.path')==path
    assert game.evaluate('rules.pathTime(game.state.map,game.state.path)')==pytest.approx(total)
    screenshot(game,'traffic-selection.png')
    game.locator('#validate-button').click()
    game.wait_for_function("game.state.phase==='waiting' && Number.isFinite(game.state.exploreStarted)")
    game.locator('#ai-skip').click();phase(game,'race')
    game.evaluate('t=>game.state.raceStarted=performance.now()/1000-t',wait_at)
    game.wait_for_function('rules.vehiclePosition(game.state.map,game.state.path,performance.now()/1000-game.state.raceStarted).waiting')
    screenshot(game,'traffic-waiting.png')
    finish(game)
    assert game.evaluate('game.state.result.player_time')==pytest.approx(total)


def test_traffic_decor_closed_open_and_reduced_motion(game):
    from speed.generator import generate_map
    begin(game)
    data=next(data for seed in range(20) if (data:=generate_map('normal','medium',seed))['river'])
    game.evaluate("""map => {
      const r=game.renderer;window.trafficOriginal={state:r.state,reducedMotion:r.reducedMotion};
      const start=map.nodes.find(n=>n.type==='start').id,goal=map.nodes.find(n=>n.type==='goal').id;
      map.ai_type='bfs';map.id+='-visual';
      r.state={map,start,goal,path:[start],phase:'selection',ai:null,phaseStarted:0};
      for(const e of map.edges)if(e.traffic_event)e.traffic_event.phase=.5;
      r.reducedMotion=true;r.render(performance.now()/1000);r.overview();
    }""",data)
    try:
        assert game.evaluate("new Set(game.renderer.trafficEdges.map(e=>e.traffic_event.kind)).size===3")
        screenshot(game,'traffic-all-closed.png')
        game.evaluate("""() => {
          for(const e of game.renderer.trafficEdges)e.traffic_event.phase=e.traffic_event.closed_for+.5;
          game.renderer.render(performance.now()/1000);
        }""")
        screenshot(game,'traffic-all-open.png')
        assert game.evaluate("""async () => {
          const {trafficState}=await import('/js/traffic.js');
          return game.renderer.trafficEdges.every(e=>!trafficState(e,0).closed);
        }""")
    finally:
        game.evaluate('game.renderer.state=trafficOriginal.state;game.renderer.reducedMotion=trafficOriginal.reducedMotion;game.renderer.render(performance.now()/1000)')
