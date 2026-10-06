import { edgeJourney, STOP_FRACTION } from './traffic.js';
export const SELECTION_SECONDS = 15;
export const selectionLimit = state => state.map?.selection_seconds || SELECTION_SECONDS;
export const COLORS = { player: '#3379ec', robot: '#e87551', optimal: '#7caa42' };
const mapIndexes=new WeakMap();
function indexFor(map) {
  let index=mapIndexes.get(map);if(index)return index;
  index={nodes:Object.fromEntries(map.nodes.map(n=>[n.id,n])),edges:new Map(),neighbors:new Map(map.nodes.map(n=>[n.id,[]])),hasTraffic:map.edges.some(e=>e.traffic_event)};
  for(const e of map.edges){
    index.edges.set(`${e.source}\0${e.target}`,e);index.neighbors.get(e.source).push(e.target);
    if(!e.one_way){index.edges.set(`${e.target}\0${e.source}`,e);index.neighbors.get(e.target).push(e.source);}
  }
  mapIndexes.set(map,index);return index;
}
export function edgeBetween(map, a, b) {return indexFor(map).edges.get(`${a}\0${b}`);}
export function pathTime(map, path) {
  let time=0;for(let i=1;i<path.length;i++)time=edgeJourney(edgeBetween(map,path[i-1],path[i]),time).arrival;
  return Math.round(time*1e6)/1e6;
}
// Earliest-arrival Dijkstra for validating a player's unfinished route. The
// server repeats this check and remains authoritative for scores/completion.
export function remainingTime(map, start, goal, departure) {
  const index=indexFor(map);
  if(!index.hasTraffic)return map.remaining_times[start];
  const distances=new Map([[start,departure]]),queue=[[start,departure]],settled=new Set();
  while(queue.length){
    queue.sort((a,b)=>b[1]-a[1]);const [node,time]=queue.pop();
    if(settled.has(node))continue;
    if(node===goal)return time-departure;
    settled.add(node);
    for(const next of index.neighbors.get(node)){
      const arrival=edgeJourney(edgeBetween(map,node,next),time).arrival;
      if(arrival<(distances.get(next)??Infinity)){distances.set(next,arrival);queue.push([next,arrival]);}
    }
  }
  return Infinity;
}
export function neighbors(map, node) {return indexFor(map).neighbors.get(node)||[];}
// Suivre les routes alignées vers la cible, sans choisir de détour latéral.
export function straightExtension(state, target) {
  const nodes=indexFor(state.map).nodes,start=nodes[state.path.at(-1)],end=nodes[target];
  if(!start||!end)return null;
  const dx=end.x-start.x,dy=end.y-start.y,length2=dx*dx+dy*dy;
  if(!length2)return null;
  let current=start.id,progress=0;const extension=[];
  while(extension.length+state.path.length<512){
    const choices=neighbors(state.map,current).filter(id=>{
      const n=nodes[id],x=n.x-start.x,y=n.y-start.y,t=(x*dx+y*dy)/length2;
      return Math.abs(x*dy-y*dx)<=1e-7*Math.sqrt(length2) && t>progress+1e-9 && t<=1+1e-9;
    });
    if(choices.length!==1)return null;
    const next=choices[0];extension.push(next);
    if(next===target)return extension;
    if(next===state.goal)return null;
    const n=nodes[next];progress=((n.x-start.x)*dx+(n.y-start.y)*dy)/length2;current=next;
  }
  return null;
}
// Un clic lointain ne choisit jamais une bifurcation à la place du joueur.
// Le retour immédiat reste possible par clic adjacent ou par Annuler.
export function corridorExtension(state, target) {
  let current=state.path.at(-1),previous=state.path.at(-2);
  if(!target||target===current)return null;
  if(neighbors(state.map,current).includes(target))return [target];
  const extension=[],seen=new Set([current]);
  while(extension.length+state.path.length<512){
    const choices=neighbors(state.map,current).filter(id=>id!==previous);
    if(choices.length!==1)return null;
    const next=choices[0];if(seen.has(next))return null;
    extension.push(next);if(next===target)return extension;
    if(next===state.goal)return null;
    seen.add(next);previous=current;current=next;
  }
  return null;
}
export function addNode(state, node) {
  if (state.phase !== 'selection' || state.locked || state.path.length >= 512) return false;
  if (state.path.at(-1) === state.goal) return false;
  const extension = straightExtension(state, node) || corridorExtension(state, node);
  if (!extension || state.path.length + extension.length > 512) return false;
  const candidate = [...state.path, ...extension];
  const cost=pathTime(state.map,candidate);
  const remaining = remainingTime(state.map,node,state.goal,cost);
  if (cost + remaining > state.map.max_travel_time + .0001) {
    state.routeNotice = `Ce détour dépasse ${state.map.max_travel_time} s. Annule une étape pour changer de route.`;
    return false;
  }
  state.routeNotice = '';
  state.path.push(...extension);
  return true;
}
export function undoNode(state) {
  if (state.phase !== 'selection' || state.locked || state.path.length < 2) return false;
  state.path.pop();
  state.routeNotice = '';
  return true;
}
export function vehiclePosition(map, path, elapsed) {
  const nodes = indexFor(map).nodes;
  elapsed=Math.max(0,elapsed);let departure=0;
  for (let i = 1; i < path.length; i++) {
    const edge = edgeBetween(map, path[i - 1], path[i]);
    const a = nodes[path[i - 1]], b = nodes[path[i]];
    const journey=edgeJourney(edge,departure);
    if (elapsed < journey.arrival) {
      const waiting=elapsed>=journey.stopAt && elapsed<journey.releaseAt;
      const t=waiting?STOP_FRACTION:(elapsed-departure-(elapsed>=journey.releaseAt?journey.wait:0))/journey.drive;
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, dx: b.x - a.x, dy: b.y - a.y, finished: false,
        waiting,waitRemaining:waiting?journey.releaseAt-elapsed:0,edgeId:edge.id,eventKind:edge.traffic_event?.kind };
    }
    departure=journey.arrival;
  }
  const end = nodes[path.at(-1)], prev = nodes[path.at(-2)] || end;
  return { ...end, dx: end.x - prev.x || 1, dy: end.y - prev.y, finished: true };
}
export function createState() {
  return { phase: 'home', map: null, path: [], goal: null, start: null, ai: null,
    locked: false, assisted: false, token: 0, exploreStarted: 0, exploreDuration: 1.2,
    selectionStarted: 0, selectionReady: null, reflectionTime: null, routeNotice: '',
    phaseStarted: 0, raceStarted: 0, result: null, demo: null };
}

// Le rendu suit son horloge indépendamment du délai de lecture.
export function explorationProgress(state, time) {
  if(!Number.isFinite(state.exploreStarted))return 0;
  const clock=state.aiPaused?state.aiPauseTime:time;
  return Math.max(0,Math.min(1,(clock-state.exploreStarted)/state.exploreDuration));
}

export function acceptExplanation(state, kind, elapsed) {
  if(kind===state.aiMessageKind)return true;
  if(state.aiMessageKind && elapsed-state.aiMessageChangedAt<(state.aiMessageSeconds||3))return false;
  state.aiMessageKind=kind;state.aiMessageChangedAt=elapsed;
  return true;
}
