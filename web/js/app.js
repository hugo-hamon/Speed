import { installLeaderboard } from './leaderboard.js';
import { call } from './api.js';
import { createState, addNode, undoNode, pathTime, selectionLimit, explorationProgress, acceptExplanation, vehiclePosition } from './state.js';
import { ROUTE_REVEAL_SECONDS, routeRevealProgress } from './exploration.js';
import { CityRenderer } from './renderer.js';
import { Sound } from './audio.js';
import { installConfig } from './config.js';
import { StressTest, stressMap } from './stress.js';

const $ = id => document.getElementById(id);
const now = () => performance.now() / 1000;
const seconds = value => `${Number(value).toLocaleString('fr-FR', {minimumFractionDigits: 1, maximumFractionDigits: 2})} s`;
export const state = createState();
export const renderer = new CityRenderer($('city'), state);
export const sound = new Sound();
export const stress = new StressTest(renderer,state);
let difficulty = 'normal', busy = false, lastCountdown = null, lastUi = 0;
const ROBOTS = { myopic: 'ROBOT FACILE · VISION 2', bfs: 'ROBOT NORMAL · VISION', dijkstra: 'ROBOT EXPERT · GPS' };

function show(id, visible) { $(id).hidden = !visible; }
function announce(text) { $('announcer').textContent = text; }
const ranking=installLeaderboard(()=>state);
function setPhase(phase) {
  show('stress-panel', phase === 'stress');
  show('ai-explanation',phase==='waiting');
  ranking.close();
  if(phase==='home')ranking.refresh();
  document.body.classList.toggle('playing',['preparation','countdown','selection','waiting','race'].includes(phase));
  state.phase = phase; state.phaseStarted = now(); document.body.dataset.screen = phase;
  show('home-panel', phase === 'home'); show('demo-label', phase === 'home' && !!state.demo);
  show('game-hud', ['preparation','countdown','selection','waiting','race'].includes(phase));
  show('countdown', phase === 'countdown'); show('route-controls', phase === 'selection');
  show('stage-label', ['preparation','selection','waiting','race'].includes(phase));
  show('race-progress', phase === 'race'); show('result-panel', phase === 'result');
  show('science-panel', phase === 'science');
  show('camera-controls', ['selection','waiting','race','science','result'].includes(phase));
  if(phase==='home')updateDate();
  sound.setScene(phase);
  if (phase !== 'race') sound.stopMotor();
}

function error(error, token = state.token) {
  if (token !== state.token) return;
  sound.stopMotor(); sound.setScene('error'); busy = false; state.token++;
  state.locked = true; state.phase = 'error';
  for (const id of ['countdown','route-controls','stage-label','race-progress','camera-controls']) show(id, false);
  $('error-message').textContent = error.message || String(error); show('error-panel', true);
  $('retry-button').focus();
}

function setMap(map) {
  state.map = map; state.start = map.nodes.find(n => n.type === 'start').id;
  state.goal = map.nodes.find(n => n.type === 'goal').id; state.path = [state.start];
  state.ai = null; state.result = null; state.assisted = false; state.locked = false; state.demo = null;
  state.routeNotice = ''; state.selectionReady = null; state.reflectionTime = null;
  $('map-name').textContent = map.name.toUpperCase(); $('mission-title').textContent = map.mission;
  $('robot-label').textContent = ROBOTS[map.ai_type] + (map.ai_type === 'bfs' ? ` ${map.ai_depth}` : '');
  const fast=map.edges.some(edge=>(edge.speed_type||edge.road_type)==='fast');
  const directed=map.edges.some(edge=>edge.one_way);
  const traffic=map.edges.some(edge=>edge.traffic_event);
  $('direction-hint').textContent=[fast?'Traits blancs : rues rapides':'',directed?'Flèches : sens uniques':'',traffic?(map.difficulty==='expert'?'Feux, trains, ponts : attente selon ton arrivée':'Feux : attente selon ton arrivée'):''].filter(Boolean).join(' · ');
  show('direction-hint',fast||directed||traffic);
}

export async function home() {
  stress.dispose();
  const token = ++state.token; busy = false; show('error-panel', false); setPhase('home');
  $('play-button').disabled = false;
  try {
    const map = await call('get_random_map', difficulty);
    if (token !== state.token) return;
    setMap(map);
    const [a, b] = await Promise.all([call('get_optimal_path', map.id, state.start, state.goal), call('compute_ai_path', map.id, 'myopic', state.start, state.goal)]);
    if (token !== state.token) return;
    state.demo = { a, b, started: now(), duration: Math.max(a.travel_time, b.travel_time) + 2.4 };
    show('demo-label', true);
  } catch (e) { error(e, token); }
}

export async function startRound() {
  if (busy) return;
  const token = ++state.token; busy = true; show('error-panel', false);
  $('play-button').disabled = true;
  try {
    const map = await call('get_random_map', difficulty);
    if (token !== state.token) return;
    setMap(map); setPhase('preparation');
    $('player-status').textContent = 'Repère ta destination'; $('robot-status').textContent = 'Il attend ton trajet';
    $('stage-text').textContent = 'Du garage au drapeau : choisis les bonnes rues.';
    announce(map.mission); lastCountdown = null;
    // Calcul immédiat ; seule sa restitution visuelle commence à GO.
    const ai = await call('compute_ai_path', map.id, map.ai_type, state.start, state.goal);
    if (token !== state.token) return;
    state.ai = ai;
    const timing=map.ai_timing||{easy:12,normal:18,expert:24,message_seconds:3};
    state.aiMessageSeconds=timing.message_seconds;
    state.exploreDuration=timing[map.difficulty];
    state.aiSteps=Math.max(1,Math.min(ai.events.length,Math.ceil(state.exploreDuration*60)));
    busy = false;
  } catch (e) { error(e, token); }
}

function updateSelection() {
  const ready = state.path.at(-1) === state.goal;
  $('validate-button').disabled = !ready || state.locked;
  $('undo-button').disabled = state.path.length <= 1 || state.locked;
  $('route-time').textContent = `${seconds(pathTime(state.map, state.path))} / ${state.map.max_travel_time} s max`;
  $('selection-hint').textContent = ready ? 'Destination atteinte. Prêt à partir ?' : 'Clique à côté, en ligne droite ou sans bifurcation';
  $('player-status').textContent = ready ? 'Trajet prêt !' : `${state.path.length - 1} rue${state.path.length > 2 ? 's' : ''} choisie${state.path.length > 2 ? 's' : ''}`;
}

function select(node) {
  if (addNode(state, node)) {
    sound.beep(620, .06); updateSelection();
    renderer.followNode(node);
    $('stage-text').textContent = 'Trace ta route jusqu’au drapeau. Chaque seconde compte.';
  } else if(state.routeNotice) {
    $('stage-text').textContent = state.routeNotice;
    announce(state.routeNotice);
  } else if (state.map.edges.some(e => e.one_way && e.target === state.path.at(-1) && e.source === node)) {
    $('stage-text').textContent = 'Sens unique : suis les flèches pour trouver une autre route.';
  }
}
function undo() {
  if (undoNode(state)) { sound.beep(400, .06); updateSelection(); renderer.followNode(state.path.at(-1)); $('stage-text').textContent = 'Trace ta route jusqu’au drapeau. Chaque seconde compte.'; }
}

export async function lockRoute(automatic = false) {
  if (state.phase !== 'selection' || state.locked || busy) return;
  if (!automatic && state.path.at(-1) !== state.goal) return;
  state.locked = true; busy = true; updateSelection();
  const token = state.token;
  state.exploreStarted=Infinity;state.aiPaused=false;$('ai-pause').textContent='Pause';$('ai-step').textContent='AU TOUR DU ROBOT';$('ai-batch').hidden=state.ai.events.length<=state.aiSteps;
  $('ai-explanation-text').textContent='Ton trajet est verrouillé. Préparation de la recherche du robot…';
  $('ai-focus').textContent='';
  setPhase('waiting'); $('stage-text').textContent = automatic ? 'On termine ton trajet…' : 'Ton trajet est prêt. À présent, observe le robot.';
  try {
    await state.selectionReady;
    if (token !== state.token) return;
    const locked = await call('lock_route', state.map.round_id, [...state.path], automatic);
    if (token !== state.token) return;
    state.path = locked.path; state.assisted = locked.assisted; state.reflectionTime = locked.reflection_time;
    busy = false;state.exploreStarted=now();state.aiStep=-1;state.aiMessageKind=null;state.aiMessageChangedAt=0;state.aiMessageEventCount=-1;renderer.overview();
    $('player-status').textContent = 'Trajet verrouillé';
    maybeRace(now());
  } catch (e) { error(e, token); }
}

function maybeRace(time) {
  if (state.phase !== 'waiting' || busy || !state.ai || state.aiPaused || time - state.exploreStarted < state.exploreDuration+Math.max(state.aiMessageSeconds||3,ROUTE_REVEAL_SECONDS+.5)) return;
  if(state.aiMessageKind!=='done' || time-state.exploreStarted-state.aiMessageChangedAt<(state.aiMessageSeconds||3))return;
  state.raceStarted = time; setPhase('race'); sound.startMotor(); sound.beep(840, .15);
  $('stage-text').textContent = state.assisted ? 'C’est parti ! Cette course ne compte pas pour les records.' : 'C’est parti ! Que le meilleur chemin gagne.';
  $('robot-status').textContent = 'En route !'; $('player-status').textContent = 'En route !';
  announce('Les deux voitures démarrent !');
}

async function finishRound() {
  if (busy || state.phase !== 'race') return;
  busy = true; const token = state.token;
  try {
    const result = await call('finalize_round', state.map.round_id, [...state.path]);
    if (token !== state.token) return;
    state.result = result; busy = false; setPhase('result');ranking.reset(result);
    $('result-title').textContent = { player: 'VICTOIRE !', robot: 'LE ROBOT GAGNE !', tie: 'ÉGALITÉ !' }[result.winner];
    $('result-subtitle').textContent = result.assisted ? 'Bien arrivé !' : result.optimal ? 'Bien joué, tu as trouvé un chemin optimal !' : result.winner === 'player' ? 'Ton sens de l’orientation a fait la différence.' : 'Un autre chemin te fera peut-être gagner…';
    $('result-badge').textContent = result.new_record ? '★ NOUVEAU RECORD DU JOUR' : 'LIGNE D’ARRIVÉE';
    $('result-player').textContent = seconds(result.player_time); $('result-robot').textContent = seconds(result.robot_time);
    $('result-difference').textContent = result.winner === 'tie' ? 'Au même instant' : `${seconds(Math.abs(result.difference))} ${result.winner === 'player' ? 'd’avance' : 'de retard'}`;
    $('result-record').textContent = result.record == null ? 'À établir' : seconds(result.record);
    $('reflection-line').textContent = result.assisted ? '' : `Chemin trouvé en ${seconds(result.reflection_time)} · Bonus rapidité : +${result.speed_bonus} points`;
    show('reflection-line', !result.assisted);
    $('score-line').textContent = result.assisted ? `Meilleur score de session : ${result.best_score}` : `${result.score} points · Meilleur score de session : ${result.best_score}`;
    $('record-warning').textContent = result.warning || ''; show('record-warning', !!result.warning);
    sound.finish(result.winner === 'player'); announce($('result-title').textContent); $('replay-button').focus({preventScroll:true});
  } catch (e) { error(e, token); }
}

function science() {
  if (!state.result) return;
  setPhase('science');
  const metadata = state.result.metadata;
  $('science-description').textContent = metadata.depth ? `Le robot ne regarde que ${metadata.depth} rues à l’avance. Il choisit ce qui semble le rapprocher du drapeau, sans regarder les ralentissements plus loin. Comme quelqu’un qui tourne trop tôt, il peut perdre du temps !` : 'Ce robot additionne le temps des rues pour comparer les chemins. Il trouve celui qui permet d’arriver le plus vite, même s’il fait un détour, en calculant aussi l’attente aux feux, aux trains et aux ponts selon son heure d’arrivée. Cette méthode s’appelle Dijkstra.';
  const saved = state.result.player_time - state.result.optimal_time;
  $('science-comparison').textContent = saved < .01 ? `Le chemin vert est le plus rapide : ${seconds(state.result.optimal_time)}. Tu as trouvé un chemin aussi rapide. Bien joué !` : `Le chemin vert prend ${seconds(state.result.optimal_time)}, soit ${seconds(saved)} de moins que ton trajet. Regarde où il évite les ralentissements ou les détours.`;
}

function frame() {
  const time = now();
  if(stress.active){stress.frame(time);requestAnimationFrame(frame);return;}
  if (state.phase === 'preparation' && renderer.mapId === state.map.id) {
    if(time-state.phaseStarted>=renderer.camera.introDuration && state.ai)setPhase('countdown');
    else if(renderer.camera.large) $('stage-text').textContent=time-state.phaseStarted<1?'Voici ton arrivée !':time-state.phaseStarted<2.5?'Repère les routes de la ville…':'Retour au départ. À toi de jouer !';
  }
  if (state.phase === 'countdown') {
    const elapsed = time - state.phaseStarted;
    const text = elapsed < 3 ? String(3 - Math.floor(elapsed)) : 'GO !';
    if (text !== lastCountdown) { $('countdown-number').textContent = text; sound.beep(text === 'GO !' ? 900 : 500, .12); lastCountdown = text; }
    if (elapsed >= 3.5) {
      setPhase('selection'); state.selectionStarted = time; state.exploreStarted = Infinity;
      const token = state.token;
      state.selectionReady = call('begin_selection', state.map.round_id).catch(e => { error(e, token); });
      $('stage-text').textContent = 'Trace ta route jusqu’au drapeau. Chaque seconde compte.';
      updateSelection(); announce(`À toi de tracer ton trajet. Tu as ${selectionLimit(state)} secondes.`);
    }
  }
  if (state.phase === 'selection') {
    const remaining = Math.max(0, selectionLimit(state) - (time - state.selectionStarted));
    $('timer-fill').style.width = `${remaining / selectionLimit(state) * 100}%`;
    $('timer-label').textContent = `${Math.ceil(remaining)} s pour choisir`;
    if (remaining <= 0) lockRoute(true);
  }
  if(state.phase==='selection')$('robot-status').textContent='Il attend ton trajet';
  if(state.phase==='waiting'&&!busy){
    const progress=explorationProgress(state,time);
    const count=Math.floor(progress*state.ai.events.length),e=state.ai.events[Math.max(0,count-1)];
    $('robot-status').textContent=progress>=1?(routeRevealProgress(state,time)<1&&state.map.ai_type==='dijkstra'?'Il trace son trajet…':'Son trajet est prêt !'):`Il cherche · ${Math.round(progress*100)} %`;
    state.aiStep=count;
    const currentNumber=count?state.map.nodes.findIndex(n=>n.id===e.node)+1:null;
    $('ai-focus').textContent=progress>=1?'Recherche terminée':!count?'La recherche commence…':
      ['explore','settle'].includes(e.kind)?`◎ Il examine le carrefour ${currentNumber}`:
      `Il ${e.kind==='backtrack'?'revient':'avance'} vers le carrefour ${currentNumber}`;
    const kind=progress>=1?'done':e.kind;
    const elapsed=(state.aiPaused?state.aiPauseTime:time)-state.exploreStarted;
    if((count!==state.aiMessageEventCount || kind!==state.aiMessageKind) && acceptExplanation(state,kind,elapsed)){
      state.aiMessageEventCount=count;
      const number=state.map.nodes.findIndex(n=>n.id===e.node)+1;
      const text=progress>=1?'Le trajet retenu se dessine en orange. Les cases violettes s’effacent pour laisser le trajet bien visible. Les deux voitures vont partir ensemble !':
        e.kind==='settle'?'Ce robot utilise Dijkstra : il additionne le temps des rues et explore d’abord les carrefours accessibles le plus vite. Il trouve ainsi le trajet le plus rapide jusqu’à l’arrivée, en tenant compte des ralentissements, des rues rapides, des sens uniques et de l’heure d’arrivée aux feux, trains et ponts levants.':
        e.kind==='advance'?`Il choisit d’avancer vers le carrefour ${number}, qui semble le rapprocher de l’arrivée. Les ralentissements ne sont pas pris en compte par ce robot.`:
        e.kind==='backtrack'?`Cette piste ne permet plus d’avancer : le robot revient au carrefour ${number} pour essayer ailleurs. Ce détour comptera dans sa course.`:
        `Il regarde jusqu’à ${state.ai.metadata.depth} rues devant lui. Les cases violettes montrent les possibilités de cette étape. Elles s’effacent quand il avance. Le chemin orange grandit quand il décide d’avancer.`;
      $('ai-explanation-text').textContent=text;
      $('ai-step').textContent=progress>=1?'TRAJET TROUVÉ':state.map.ai_type==='dijkstra'?'DIJKSTRA · LE TRAJET LE PLUS RAPIDE':'IL EXPLORE LES POSSIBILITÉS';
    }
    maybeRace(time);
  }
  if (state.phase === 'race' && time - lastUi > .05) {
    const elapsed = time - state.raceStarted, total = pathTime(state.map, state.path);
    $('player-progress').style.width = `${Math.min(1,elapsed / total) * 100}%`;
    $('robot-progress').style.width = `${Math.min(1,elapsed / state.ai.travel_time) * 100}%`;
    const raceStatus=(path,total)=>{
      const car=vehiclePosition(state.map,path,elapsed);
      return elapsed>=total?'Arrivé !':car.waiting?'En attente…':seconds(elapsed);
    };
    $('player-status').textContent = raceStatus(state.path,total);
    $('robot-status').textContent = raceStatus(state.ai.path,state.ai.travel_time);
    if (elapsed >= Math.max(total,state.ai.travel_time) + .65) finishRound();
    lastUi = time;
  }
  renderer.render(time); requestAnimationFrame(frame);
}

$('ai-pause').addEventListener('click',()=>{
  if(state.phase!=='waiting'||busy)return;
  if(state.aiPaused){state.exploreStarted+=now()-state.aiPauseTime;state.aiPaused=false;}
  else{state.aiPaused=true;state.aiPauseTime=now();}
  $('ai-pause').textContent=state.aiPaused?'Reprendre':'Pause';
});
$('ai-skip').addEventListener('click',()=>{
  if(state.phase!=='waiting'||busy)return;
  state.aiPaused=false;state.aiMessageKind='done';state.aiMessageChangedAt=-Infinity;state.exploreStarted=now()-state.exploreDuration-Math.max(state.aiMessageSeconds||3,ROUTE_REVEAL_SECONDS+.5)-1;maybeRace(now());
});
$('play-button').addEventListener('click', startRound);
$('replay-button').addEventListener('click', startRound);
$('home-button').addEventListener('click',()=>{if(state.phase==='home'&&!$('leaderboard').hidden)ranking.close(true);else home();});
$('retry-button').addEventListener('click', home);
$('undo-button').addEventListener('click', undo);
$('validate-button').addEventListener('click', () => lockRoute(false));
$('science-button').addEventListener('click', science);
$('science-close').addEventListener('click', () => setPhase('result'));
function toggleSound() {
  const enabled = sound.toggle();
  $('sound-button').setAttribute('aria-pressed', String(enabled));
  $('sound-button').setAttribute('aria-label', enabled ? 'Couper le son' : 'Activer le son');
  $('sound-button').title = enabled ? 'Couper le son' : 'Activer le son';
  $('sound-button').querySelector('path').setAttribute('d', enabled ? 'M4 9h4l5-4v14l-5-4H4zM17 8q5 4 0 8M19 5q8 7 0 14' : 'M4 9h4l5-4v14l-5-4H4zM17 9l5 6m0-6-5 6');
  if (enabled) { sound.beep(); if (state.phase === 'race') sound.startMotor(); }
}
$('sound-button').addEventListener('click', toggleSound);
installConfig(home);
$('stress-start').addEventListener('click',()=>{
  if($('config-save').disabled)return;
  $('config-dialog').close();state.token++;busy=false;
  const [width,height]=$('stress-size').value.split(',').map(Number);
  setMap(stressMap(width,height));setPhase('stress');stress.start({cars:Number($('stress-cars').value),motion:$('stress-motion').value});
});
$('stress-exit').addEventListener('click',home);
$('stress-stop').addEventListener('click',()=>stress.finish('Test arrêté'));
document.addEventListener('visibilitychange',()=>{if(document.hidden&&stress.active&&!stress.finished)stress.finish('Test interrompu : onglet masqué');});
$('overview-button').addEventListener('click',()=>renderer.overview());
$('zoom-in').addEventListener('click',()=>renderer.zoom(1.25));
$('zoom-out').addEventListener('click',()=>renderer.zoom(.8));
$('city').addEventListener('wheel',event=>{
  if(!['selection','waiting','race','science','result'].includes(state.phase))return;
  event.preventDefault();renderer.zoom(Math.exp(-event.deltaY*.0012),event.clientX,event.clientY);
},{passive:false});
document.querySelectorAll('[data-difficulty]').forEach(button => button.addEventListener('click', () => {
  difficulty = button.dataset.difficulty;
  document.querySelectorAll('[data-difficulty]').forEach(b => { b.classList.toggle('selected', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  home();
}));
$('help-button').addEventListener('click', () => $('help-dialog').showModal());
$('help-close').addEventListener('click', () => $('help-dialog').close());
$('help-ready').addEventListener('click', () => { $('help-dialog').close(); startRound(); });
$('city').addEventListener('click', event => { if (state.phase === 'selection') select(renderer.hitTest(event.clientX,event.clientY)); });
$('city').addEventListener('contextmenu', event => { event.preventDefault(); undo(); });
$('city').addEventListener('pointermove', event => {
  const node = state.phase === 'selection' ? renderer.hitTest(event.clientX,event.clientY) : null;
  $('city').style.cursor = node ? 'pointer' : 'default';
});
document.addEventListener('keydown', event => {
  if(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)return;
  if ($('help-dialog').open || $('config-dialog').open) return;
  if(event.key==='Escape'&&state.phase==='home'&&!$('leaderboard').hidden){event.preventDefault();ranking.close(true);return;}
  if (event.key === 'Escape') { event.preventDefault(); home(); }
  if (event.key === 'Backspace') { event.preventDefault(); undo(); }
  if (event.key === 'Enter' && state.phase === 'selection') { event.preventDefault(); lockRoute(false); }
  if (event.key.toLowerCase() === 'r' && ['result','science'].includes(state.phase)) startRound();
});

function updateDate() {
  const date = new Date();
  $('current-date').textContent = date.toLocaleDateString('fr-FR', {day:'numeric',month:'long',year:'numeric'});
  $('current-date').dateTime = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const track=document.querySelector('.credits-track'),group=track.firstElementChild;
  const width=group.getBoundingClientRect().width;
  const signature=`${width}:${window.innerWidth}:${$('current-date').dateTime}`;
  if(track.dataset.signature===signature||!width)return;
  track.dataset.signature=signature;
  while(track.children.length>1)track.lastElementChild.remove();
  for(let i=0;i<Math.ceil(window.innerWidth/width)+1;i++){
    const copy=group.cloneNode(true);copy.setAttribute('aria-hidden','true');
    copy.querySelector('[id]')?.removeAttribute('id');track.append(copy);
  }
  track.style.setProperty('--credits-distance',`${width}px`);
  track.style.setProperty('--credits-duration',`${width/55}s`);
}
window.addEventListener('resize',updateDate);
updateDate(); setInterval(updateDate, 30000);
home(); requestAnimationFrame(frame);
