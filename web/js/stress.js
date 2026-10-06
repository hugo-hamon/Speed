// Charge visuelle fixe : aucun calcul de trajet, score ou appel Python.
import { COLORS } from './state.js';
export function stressMap(width=16,height=12) {
  const nodes=[],edges=[];
  for(let x=0;x<width;x++)for(let y=0;y<height;y++) {
    const id=`${x}:${y}`;
    nodes.push({id,x,y,type:x===0&&y===0?'start':x===width-1&&y===height-1?'goal':'intersection'});
    for(const [dx,dy] of [[1,0],[0,1]])if(x+dx<width&&y+dy<height)
      edges.push({id:`${id}:${dx}`,source:id,target:`${x+dx}:${y+dy}`,travel_time:1,road_type:(x+y)%4===0?'fast':'normal',one_way:false});
  }
  return {id:`stress-${width}x${height}`,nodes,edges,width,height,decoration_seed:42,river:false,destination:'home',name:'Test de charge',mission:'',ai_type:'myopic',max_travel_time:60};
}
export class StressTest {
  constructor(renderer,state) {this.renderer=renderer;this.state=state;this.active=false;}
  start({cars=120,motion='moving'}={}) {
    this.active=true;this.started=null;this.previous=null;this.samples=[];this.finished=false;this.lastUi=0;
    this.state.stressMotion=motion;
    this.originalVehicles=this.renderer.vehicles;
    const width=this.state.map.width||16,height=this.state.map.height||12;
    const vehicles=Array.from({length:cars},(_,i)=>({index:i,p:{x:0,y:0,dx:1,dy:0},color:i%2?COLORS.robot:COLORS.player,robot:!!(i%2),elapsed:2,tag:false,offset:i%2?.07:-.07}));
    this.renderer.vehicles=time=>{
      for(const car of vehicles){const i=car.index,span=width-1,distance=((time-(this.started??time))*(1+i%3*.25)+i*.73)%(span*2),forward=distance<span;
        Object.assign(car.p,{x:forward?distance:span*2-distance,y:cars===2?Math.floor(height/2)+i:i%height,dx:forward?1:-1});}
      return vehicles;
    };
    document.getElementById('stress-description').textContent=`${width*height} carrefours · ${cars} voitures · caméra ${motion==='fixed'?'fixe':'animée'}`;
    document.getElementById('stress-status').textContent='Préparation du décor…';
  }
  dispose() {
    if(this.active)this.renderer.vehicles=this.originalVehicles;
    this.active=false;this.state.stressTime=0;
  }
  finish(message='Test terminé') {
    this.finished=true;
    const sorted=[...this.samples].sort((a,b)=>a-b);
    const duration=this.samples.reduce((a,b)=>a+b,0);
    const fps=duration?1000*this.samples.length/duration:0;
    const p95=sorted.length?sorted[Math.ceil(sorted.length*.95)-1]:0;
    document.getElementById('stress-status').textContent=sorted.length?`${message} · ${fps.toFixed(1)} FPS moyens · 95 % des images en moins de ${p95.toFixed(1)} ms`:`${message} · Pas encore de mesure`;
  }
  frame(time) {
    if(this.finished)return;
    if(document.hidden){this.finish('Test interrompu : onglet masqué');return;}
    if(this.started===null){
      // La construction du décor ne consomme pas les deux secondes de chauffe.
      this.state.stressTime=0;this.renderer.render(time);
      this.started=performance.now()/1000;this.previous=null;return;
    }
    const elapsed=time-this.started;
    // Écarter la création des caches et deux secondes de chauffe.
    if(this.previous!==null&&elapsed>=2&&this.previous-this.started>=2)this.samples.push((time-this.previous)*1000);
    this.previous=time;this.state.stressTime=elapsed;
    this.renderer.render(time);
    if(elapsed>=17){this.finish();return;}
    if(time-this.lastUi>.25){
      const recent=this.samples.slice(-60),sum=recent.reduce((a,b)=>a+b,0);
      document.getElementById('stress-status').textContent=elapsed<2?'Mise en route…':`${Math.ceil(17-elapsed)} s restantes · ${sum?(1000*recent.length/sum).toFixed(1):'…'} FPS`;
      document.getElementById('stress-resolution').textContent=`${this.renderer.width} × ${this.renderer.height} · densité Canvas ${this.renderer.dpr}× · textures ${this.renderer.cacheScale}×`;
      this.lastUi=time;
    }
  }
}
