import { COLORS, neighbors, vehiclePosition, explorationProgress } from './state.js';
import { Camera } from './camera.js';
import { TileLayer, SpriteAtlas } from './render-cache.js';
const WORLD_UNIT = 128;

const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
const tint = (hex, amount) => '#' + hex.slice(1).match(/../g).map(v => clamp(parseInt(v, 16) + amount, 0, 255).toString(16).padStart(2, '0')).join('');

export class CityRenderer {
  constructor(canvas, state) {
    this.canvas = canvas; this.ctx = canvas.getContext('2d', {alpha:false}); this.state = state;
    this.width = 0; this.height = 0; this.unit = WORLD_UNIT; this.cx = 0; this.cy = 0;
    this.hover = null; this.nodePoints = []; this.decorations = []; this.mapId = null;
    this.sceneKey = null; this.layers = null; this.camera = new Camera(); this.lastFrame = 0;
    this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }
  resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.width = rect.width; this.height = rect.height;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(this.width * this.dpr); this.canvas.height = Math.round(this.height * this.dpr);
  }
  layout(time) {
    const phase=this.state.phase,mobile=this.width<=760,home=phase==='home',result=['result','science'].includes(phase);
    const top=mobile?(home?355:result?100:250):home?(this.height>800?115:95):result?125:phase==='stress'?(this.height>800?240:205):145;
    const bottom=mobile?(home?175:result?485:220):home?180:result?90:phase==='waiting'?230:phase==='stress'?(this.height>800?225:195):145;
    const left=mobile?this.width*.04:this.width*(home?.44:result?.03:.035);
    const viewport={x:left,y:top,width:mobile?this.width*.92:this.width*(home?.54:result?.59:.93),height:Math.max(170,this.height-top-bottom)};
    this.camera.configure(this.mapId,this.worldBounds,viewport,home?'home':result?'result':'game',WORLD_UNIT,this.reducedMotion);
    if(phase==='preparation')this.camera.intro(time-this.state.phaseStarted,this.worldPoint(this.startNode.x,this.startNode.y),this.worldPoint(this.goalNode.x,this.goalNode.y),this.reducedMotion);
    if(phase==='race'){
      const key=this.camera.key+':'+this.state.raceStarted;
      if(this.raceFrameKey!==key){
        const points=[...new Set([...this.state.path,...this.state.ai.path])].map(id=>{const n=this.nodesById[id];return this.worldPoint(n.x,n.y);});
        this.camera.framePoints(points,true);this.raceFrameKey=key;
      }
    }
    if(phase==='stress'&&this.state.stressMotion!=='fixed') {
      const t=this.state.stressTime||0,b=this.worldBounds;
      this.camera.targetZoom=this.camera.fitZoom*(1.25+.25*Math.sin(t*.65));
      this.camera.targetX=(b.left+b.right)/2+Math.sin(t*.45)*(b.right-b.left)*.18;
      this.camera.targetY=(b.top+b.bottom)/2+Math.cos(t*.45)*(b.bottom-b.top)*.15;
      this.camera.clampTargets();
    }
    this.camera.update(this.lastFrame?time-this.lastFrame:1/60,this.reducedMotion);this.lastFrame=time;
    const viewKey=[this.mapId,this.camera.x,this.camera.y,this.camera.zoom,viewport.x,viewport.y,viewport.width,viewport.height].join(':');
    if(viewKey!==this.viewKey){
      this.nodePoints=this.state.map.nodes.map(n=>({...n,...this.project(n.x,n.y)}));
      this.screenNodes=new Map(this.nodePoints.map(n=>[n.id,n]));this.viewKey=viewKey;
    }
    // Le cadrage garde une zone sûre pour les trajets, mais la ville se
    // dessine jusqu'aux bords de l'écran derrière les commandes flottantes.
    this.renderViewport=['preparation','countdown','selection','waiting','race'].includes(phase)
      ?{x:0,y:0,width:this.width,height:this.height}:viewport;
    const draw=this.renderViewport;
    const tl=this.camera.world(draw.x,draw.y),br=this.camera.world(draw.x+draw.width,draw.y+draw.height);
    this.visibleBounds={left:tl.sx,top:tl.sy,right:br.sx,bottom:br.sy};
    if(home){
      const label=document.getElementById('demo-label');
      const bottomPoint=this.project(this.maxX+.575,this.maxY+.575,-.17);
      label.style.top=`${bottomPoint.sy+24}px`;label.style.left=`${viewport.x+viewport.width/2}px`;
    }
  }
  worldPoint(x,y,z=0) {
    return {sx:this.cx+(x-y-(this.centerX-this.centerY))*this.unit,sy:this.cy+((x+y-this.centerX-this.centerY)*.5-z)*this.unit};
  }
  project(x,y,z=0) {return this.camera.screen(this.worldPoint(x,y,z));}
  followNode(id,immediate=false) {
    const node=this.state.map?.nodes.find(n=>n.id===id);if(!node||!this.camera.viewport)return;
    const p=this.worldPoint(node.x,node.y);
    // Un clic explicite reprend le suivi immédiatement après un zoom manuel.
    this.camera.manualUntil=0;
    immediate?this.camera.focus(p,true):this.camera.ensureVisible(p,performance.now()/1000);
  }
  overview() {if(this.camera.viewport)this.camera.overview();}
  zoom(factor,x=this.width/2,y=this.height/2) {
    if(!this.camera.viewport||!['selection','waiting','race','science','result'].includes(this.state.phase))return;
    this.camera.zoomAt(factor,x,y,performance.now()/1000);
  }
  polygon(points, fill, stroke = null, width = 1) {
    const c = this.ctx; c.beginPath();
    points.forEach((p, i) => i ? c.lineTo(p.sx, p.sy) : c.moveTo(p.sx, p.sy));
    c.closePath(); c.fillStyle = fill; c.fill();
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = width; c.stroke(); }
  }
  worldPolygon(points, fill) { this.polygon(points.map(p => this.worldPoint(...p)), fill); }
  box(x, y, w, d, height, color, base = 0) {
    const corners = [[x-w/2,y-d/2],[x+w/2,y-d/2],[x+w/2,y+d/2],[x-w/2,y+d/2]];
    const top = corners.map(p => this.worldPoint(...p, height+base));
    const bottom = corners.map(p => this.worldPoint(...p, base));
    this.polygon([top[1],top[2],bottom[2],bottom[1]], tint(color,-28));
    this.polygon([top[2],top[3],bottom[3],bottom[2]], tint(color,-13));
    this.polygon(top,color);
  }
  line(a, b, color, width, dash = []) {
    const c = this.ctx; c.beginPath(); c.moveTo(a.sx,a.sy); c.lineTo(b.sx,b.sy);
    c.strokeStyle=color; c.lineWidth=width; c.setLineDash(dash); c.lineCap='round'; c.stroke(); c.setLineDash([]);
  }
  ellipse(x, y, rx, ry, fill, stroke = null, width = 1) {
    const c=this.ctx; c.beginPath(); c.ellipse(x,y,rx,ry,0,0,Math.PI*2); c.fillStyle=fill; c.fill();
    if (stroke) { c.strokeStyle=stroke; c.lineWidth=width; c.stroke(); }
  }
  label(text, x, y, color = '#4b6040', bg = '#fffff3', fontSize = 11) {
    const c = this.ctx; c.font = `bold ${fontSize}px "Trebuchet MS", sans-serif`;
    const width = c.measureText(text).width+17, height=fontSize+13;
    c.fillStyle='#253b3010'; c.beginPath(); c.roundRect(x-width/2,y-height/2+3,width,height,6); c.fill();
    c.fillStyle=bg; c.beginPath(); c.roundRect(x-width/2,y-height/2,width,height,6); c.fill();
    c.fillStyle=color; c.textAlign='center'; c.textBaseline='middle'; c.fillText(text,x,y+.5);
  }
  prepareDecorations(map) {
    this.mapId=map.id; this.decorations=[];
    this.nodesById=Object.fromEntries(map.nodes.map(n=>[n.id,n]));
    this.pathCache=new Map();this.explored=null;this.viewKey=null;
    this.nodeOrdinals=new Map(map.nodes.map((n,i)=>[n.id,i+1]));
    this.fastEdges=map.edges.filter(e=>(e.speed_type||e.road_type)==='fast');
    this.minX=Math.min(...map.nodes.map(n=>n.x));this.maxX=Math.max(...map.nodes.map(n=>n.x));
    this.minY=Math.min(...map.nodes.map(n=>n.y));this.maxY=Math.max(...map.nodes.map(n=>n.y));
    this.centerX=(this.minX+this.maxX)/2;this.centerY=(this.minY+this.maxY)/2;
    this.columns=this.maxX-this.minX+1;this.rows=this.maxY-this.minY+1;
    this.worldWidth=Math.ceil((this.columns+this.rows+1)*WORLD_UNIT);
    this.worldHeight=Math.ceil(((this.columns+this.rows)/2+2)*WORLD_UNIT);
    this.cx=this.worldWidth/2;this.cy=this.worldHeight/2+WORLD_UNIT*.15;
    this.riverY=map.river_y??.5;
    this.startNode=map.nodes.find(n=>n.type==='start');this.goalNode=map.nodes.find(n=>n.type==='goal');
    const left=this.worldPoint(this.minX-.575,this.maxY+.575).sx;
    const right=this.worldPoint(this.maxX+.575,this.minY-.575).sx;
    const top=this.worldPoint(this.minX-.3,this.minY-.3,.72).sy;
    const bottom=this.worldPoint(this.maxX+.575,this.maxY+.575,-.17).sy;
    this.worldBounds={left:left-12,right:right+12,top:top-12,bottom:bottom+10};
    const palette=['#e9ba7b','#df9580','#e9d7aa','#a9c7c0','#d3c28b','#b8c98b'];
    for(let x=this.minX;x<this.maxX;x++) for(let y=this.minY;y<this.maxY;y++) {
      if (map.river && Math.abs(y+.5-this.riverY)<.1) continue;
      const seed=(x*7+y*3+map.decoration_seed)%6;
      this.decorations.push({type:'building',x:x+.54,y:y+.54,w:.36,d:.34,h:.15+(seed%3)*.035,color:palette[seed],variant:seed});
      this.decorations.push({type:'tree',x:x+.79,y:y+.72,h:.24});
    }
    for (let i=0;i<this.columns+this.rows;i++) {
      const x=i<this.columns?this.minX+i-.18:this.maxX+.4, y=i<this.columns?this.maxY+.4:this.minY+(i-this.columns)-.3;
      this.decorations.push({type:'tree',x,y,h:.24+(i%3)*.045});
    }
    const start=map.nodes.find(n=>n.type==='start'), goal=map.nodes.find(n=>n.type==='goal');
    this.decorations.push({type:'garage',x:start.x-.32,y:start.y-.28,w:.35,d:.33,h:.25,color:'#8faabc'});
    const goalSide=goal.x<this.centerX?-1:1;
    this.decorations.push({type:'destination',x:goal.x+goalSide*.3,y:goal.y-goalSide*.3,w:.32,d:.32,h:.44,color:'#f4d890',mission:map.destination});
    this.decorations.sort((a,b)=>(a.x+a.y)-(b.x+b.y));
  }
  ground(time) {
    const c=this.ctx,u=this.unit;
    c.save();
    const p=this.worldPoint(this.centerX,this.centerY,0);
    c.filter='blur(17px)'; this.ellipse(p.sx+12,p.sy+u*.48,u*(this.columns+this.rows)*.38,u*(this.columns+this.rows)*.18,'#4c684126'); c.filter='none';
    this.box(this.centerX,this.centerY,this.columns+.15,this.rows+.15,.14,'#aaca7b',-.17);
    this.worldPolygon([[this.minX-.575,this.minY-.575,0],[this.maxX+.575,this.minY-.575,0],[this.maxX+.575,this.maxY+.575,0],[this.minX-.575,this.maxY+.575,0]],'#c5dd99');
    for(let x=this.minX;x<=this.maxX;x++) for(let y=this.minY;y<=this.maxY;y++) {
      if((x+y)%2===0) this.worldPolygon([[x-.49,y-.49,.001],[x+.49,y-.49,.001],[x+.49,y+.49,.001],[x-.49,y+.49,.001]],'#c2da94');
    }
    // Petites touches d'herbe déterministes, sans bruit animé.
    for(let i=0;i<Math.min(200,this.columns*this.rows*4);i++) {
      const x=((i*37)%97)/97*(this.columns-.1)+this.minX-.45,y=((i*23)%83)/83*(this.rows-.1)+this.minY-.45;
      if(Math.abs(x-Math.round(x))<.22 || Math.abs(y-Math.round(y))<.22) continue;
      const a=this.worldPoint(x,y); this.line(a,{sx:a.sx+2,sy:a.sy-3},'#98ba734d',1.5);
    }
    if(this.state.map.river) {
      this.worldPolygon([[this.minX-.575,this.riverY-.22,.006],[this.maxX+.575,this.riverY-.22,.006],[this.maxX+.575,this.riverY+.22,.006],[this.minX-.575,this.riverY+.22,.006]],'#79bcc2');
      this.worldPolygon([[this.minX-.575,this.riverY-.18,.007],[this.maxX+.575,this.riverY-.18,.007],[this.maxX+.575,this.riverY+.15,.007],[this.minX-.575,this.riverY+.15,.007]],'#91ced1');
      for(let i=0;i<this.columns*3;i++) {
        const x=this.minX-.4+i*.34+(this.reducedMotion?0:Math.sin(time*.5+i)*.025);
        this.line(this.worldPoint(x,this.riverY-.08+(i%2)*.12,.01),this.worldPoint(x+.13,this.riverY-.08+(i%2)*.12,.01),'#c3e9e3',1.6);
      }
    }
    c.restore();
  }
  roads() {
    const map=this.state.map, nodes=this.nodesById;
    const strip=(a,b,w,color)=>{
      const dx=b.x-a.x,dy=b.y-a.y,l=Math.hypot(dx,dy),ox=-dy/l*w,oy=dx/l*w;
      this.worldPolygon([[a.x+ox,a.y+oy,.018],[b.x+ox,b.y+oy,.018],[b.x-ox,b.y-oy,.018],[a.x-ox,a.y-oy,.018]],color);
    };
    // Deux passes : trottoirs continus, puis chaussée. Les carrefours sont
    // raccordés dans le même plan, sans bouts de segments superposés.
    for(const e of map.edges)strip(nodes[e.source],nodes[e.target],e.road_type==='bridge'?.16:.145,'#d9dfc0');
    for(const n of map.nodes)this.box(n.x,n.y,.29,.29,.012,'#d9dfc0');
    for(const edge of map.edges) {
      const color=(edge.speed_type||edge.road_type)==='fast'?'#63917d':(edge.speed_type||edge.road_type)==='traffic'?'#a48a70':'#77837c';
      strip(nodes[edge.source],nodes[edge.target],.115,color);
    }
    for(const n of map.nodes)this.box(n.x,n.y,.23,.23,.018,'#77837c');
    for(const edge of map.edges) {
      const a=nodes[edge.source],b=nodes[edge.target],p=this.worldPoint(a.x,a.y,.023),q=this.worldPoint(b.x,b.y,.023);
      if(!edge.one_way&&(edge.speed_type||edge.road_type)!=='fast')this.line({sx:p.sx+(q.sx-p.sx)*.22,sy:p.sy+(q.sy-p.sy)*.22},{sx:p.sx+(q.sx-p.sx)*.78,sy:p.sy+(q.sy-p.sy)*.78},'#dce0cc99',1.4,[5,7]);
      if((edge.speed_type||edge.road_type)==='traffic') {
        for(let i=0;i<3;i++) {
          const t=.28+i*.16;
          this.box(a.x+(b.x-a.x)*t+.047,a.y+(b.y-a.y)*t+.047,.075,.075,.047,['#e2a36f','#e6c674','#dba990'][i],.025);
        }
      }
      if(edge.road_type==='light') {
        const at=this.worldPoint((a.x+b.x)/2+.1,(a.y+b.y)/2+.1,.12);
        this.line({...at,sy:at.sy+12},at,'#566758',2); this.ellipse(at.sx,at.sy,4,5,'#f09664');
      }
    }
  }
  directionMarkers() {
    const nodes=(this.nodesById||Object.fromEntries(this.state.map.nodes.map(n=>[n.id,n])));
    for(const e of this.state.map.edges.filter(e=>e.one_way)) {
      const a=nodes[e.source],b=nodes[e.target],length=Math.hypot(b.x-a.x,b.y-a.y);
      const dx=(b.x-a.x)/length,dy=(b.y-a.y)/length;
      const at=(t,along,across)=>[a.x+(b.x-a.x)*t+dx*along-dy*across,a.y+(b.y-a.y)*t+dy*along+dx*across,.038];
      for(const t of [.32,.65]) {
        const arrow=[[-.095,-.025],[.015,-.025],[.015,-.067],[.11,0],[.015,.067],[.015,.025],[-.095,.025]];
        this.polygon(arrow.map(([along,across])=>this.worldPoint(...at(t,along,across))),'#fffde8','#596b62',1);
      }
      this.line(this.worldPoint(...at(.18,0,.105)),this.worldPoint(...at(.85,0,.105)),'#f4d779',Math.max(2,this.unit*.017));
    }
  }
  paintFastEdge(edge,a,b,time) {
    const dx=b.x-a.x,dy=b.y-a.y;
    for(const side of [-1,1]) {
      const p=this.worldPoint(a.x+dx*.2-dy*.04*side,a.y+dy*.2+dx*.04*side,.032);
      const q=this.worldPoint(a.x+dx*.8-dy*.04*side,a.y+dy*.8+dx*.04*side,.032);
      this.ctx.save();this.ctx.lineDashOffset=-time*65*(edge.one_way?1:side);
      this.line(p,q,'#faffde',3,[10,13]);this.ctx.restore();
    }
  }
  fastRoads(time) {
    if(this.state.phase==='science')return;
    const frame=this.reducedMotion?0:Math.floor((time*65%23)/23*16);
    for(const edge of this.fastEdges||this.state.map.edges) {
      if((edge.speed_type||edge.road_type)!=='fast')continue;
      const a=this.nodesById[edge.source],b=this.nodesById[edge.target],p=this.worldPoint((a.x+b.x)/2,(a.y+b.y)/2);
      const key=`${b.x-a.x}:${b.y-a.y}:${!!edge.one_way}`,frames=this.fastFrames?.get(key);
      if(frames){if(this.visible({left:p.sx-64,top:p.sy-96,width:128,height:128}))this.fastAtlas.draw(frames[frame],p.sx,p.sy);}
      else this.paintFastEdge(edge,a,b,this.reducedMotion?0:time);
    }
  }
  drawPath(path,color,offset=0,dash=[],width=null) {
    if(!path || path.length<2)return;
    const key=path.join('>');let shape=this.pathCache.get(key);
    if(!shape){shape=new Path2D();path.forEach((id,i)=>{const n=this.nodesById[id],p=this.worldPoint(n.x,n.y,.032);i?shape.lineTo(p.sx,p.sy):shape.moveTo(p.sx,p.sy);});
      if(this.pathCache.size>=64)this.pathCache.delete(this.pathCache.keys().next().value);this.pathCache.set(key,shape);}
    const c=this.ctx;c.save();c.translate(0,offset);c.lineJoin='round';c.lineCap='round';c.lineWidth=width??Math.max(3,this.unit*.035);c.strokeStyle=color;c.setLineDash(dash);c.stroke(shape);c.restore();
  }
  exploration(time) {
    const s=this.state;if(!s.ai||!['waiting','race','result'].includes(s.phase))return;
    if(s.phase!=='waiting'){this.drawPath(s.ai.path,COLORS.robot,-3);return;}
    if(!Number.isFinite(s.exploreStarted))return;
    if(s.aiPaused)time=s.aiPauseTime;
    const progress=explorationProgress(s,time),events=s.ai.events;
    const last=Math.min(events.length,Math.floor(progress*events.length));
    if(!this.explored||this.explored.events!==events||last<this.explored.last)this.explored={events,last:0,recent:new Map(),route:[s.start]};
    for(let i=this.explored.last;i<last;i++){
      const e=events[i];this.explored.recent.set(e.node,{event:e,i});
      if(['advance','backtrack'].includes(e.kind))this.explored.route.push(e.node);
    }
    this.explored.last=last;
    const current=events[Math.max(0,last-1)];
    let path=this.explored.route;
    if(s.map.ai_type==='dijkstra'){
      path=[current.node];const seen=new Set(path);
      while(this.explored.recent.get(path[0])?.event.source){
        const parent=this.explored.recent.get(path[0]).event.source;if(seen.has(parent))break;
        seen.add(parent);path.unshift(parent);
      }
    }
    if(progress>=1)path=s.ai.path;
    this.drawPath(path,'#fffef5',0,[],14);this.drawPath(path,COLORS.robot,0,[],8);
    if(progress<1){
      if(current.source)this.drawPath([current.source,current.node],'#e87551',0);
      const n=this.nodesById[current.node],p=this.worldPoint(n.x,n.y,.06);
      this.ellipse(p.sx,p.sy,22,13,'#fff4dd','#d34e25',4);
      this.label(`CARREFOUR ${this.nodeOrdinals.get(current.node)}`,p.sx,p.sy-35,'#8b341b','#fff5e5',13);
    }
  }
  building(d) {
    const {x,y,w,h,color}=d,depth=d.d;
    const shadow=this.worldPoint(x+.13,y+.13,.02);
    this.ellipse(shadow.sx,shadow.sy,this.unit*w*.8,this.unit*depth*.48,'#466e4220');
    this.box(x,y,w+.055,depth+.055,.045,'#e0dfbc');
    this.box(x,y,w,depth,h,color,.045);
    this.box(x,y,w+.045,depth+.045,.06,tint(color,17),h+.045);
    if(d.variant%2===0)this.box(x-.08,y-.03,.12,.15,.06,'#e9e9cd',h+.105);
    // Fenêtres sur les deux façades visibles.
    for(let i=-1;i<=1;i+=2) {
      const a=x+i*w*.22, z=h*.57;
      this.worldPolygon([[a-.043,y+depth/2+.002,z],[a+.043,y+depth/2+.002,z],[a+.043,y+depth/2+.002,z+.10],[a-.043,y+depth/2+.002,z+.10]],'#698889');
      const b=y+i*depth*.22;
      this.worldPolygon([[x+w/2+.002,b-.04,z],[x+w/2+.002,b+.04,z],[x+w/2+.002,b+.04,z+.10],[x+w/2+.002,b-.04,z+.10]],'#759997');
    }
    if(d.type==='garage') {
      this.worldPolygon([[x-.12,y+depth/2+.004,.04],[x+.12,y+depth/2+.004,.04],[x+.12,y+depth/2+.004,.23],[x-.12,y+depth/2+.004,.23]],'#536d73');
    }
    if(d.type==='destination') {
      const p=this.worldPoint(x,y,h+.19);
      const symbol={pizza:'PIZZA',hospital:'+',school:'ÉCOLE',home:'MAISON'}[d.mission];
      this.label(symbol,p.sx,p.sy,'#925739','#fff8da',Math.max(9,this.unit*.085));
    }
  }
  tree(d) {
    const p=this.worldPoint(d.x+.06,d.y+.06,.02);this.ellipse(p.sx,p.sy,this.unit*.14,this.unit*.07,'#476b3c20');
    this.box(d.x,d.y,.045,.045,d.h*.6,'#9a8561');
    this.box(d.x,d.y,.18,.18,d.h*.62,'#82ad63',d.h*.4);
    this.box(d.x-.01,d.y-.01,.13,.13,.07,'#95ba6e',d.h);
  }
  staticMarkers() {
    for(const n of this.state.map.nodes)if(!['start','goal'].includes(n.type)){
      const radius=.055;this.polygon([[-radius,-radius],[radius,-radius],[radius,radius],[-radius,radius]].map(([x,y])=>this.worldPoint(n.x+x,n.y+y,.04)),'#d2dac5','#a5b49a',1);
    }
  }
  markers(time) {
    const s=this.state,selection=s.phase==='selection'&&!s.locked;
    const accessible=selection&&s.path.at(-1)!==s.goal?neighbors(s.map,s.path.at(-1)):[];
    const chosenNodes=new Set(!['home','science'].includes(s.phase)?s.path:[]);
    const marked=this.spriteAtlas&&s.phase!=='science'?[...new Set([...chosenNodes,...accessible,this.startNode.id,this.goalNode.id])].map(id=>this.nodesById[id]):s.map.nodes;
    for(const n of marked) {
      const p=this.worldPoint(n.x,n.y,.055),isStart=n.type==='start',isGoal=n.type==='goal';
      if(this.visibleBounds&&!this.visible({left:p.sx-80,top:p.sy-90,width:160,height:180}))continue;
      const chosen=chosenNodes.has(n.id);
      const active=accessible.includes(n.id),r=clamp(this.unit*.079,7,14);
      if(active||isGoal&&['preparation','countdown','selection'].includes(s.phase)) {
        const pulse=this.reducedMotion?1:1+Math.sin(time*3)*.1;
        this.ellipse(p.sx,p.sy,r*1.7*pulse,r*.85*pulse,active?'#3379ec17':'#d5ee7a30',active?'#3379ec55':'#7f9c44aa',1.5);
      }
      const color=chosen?COLORS.player:isGoal?'#90aa4f':isStart?COLORS.player:active?'#fffef0':'#d2dac5';
      const radius=active||chosen||isGoal||isStart?.09:.055;
      this.polygon([[-radius,-radius],[radius,-radius],[radius,radius],[-radius,radius]].map(([x,y])=>this.worldPoint(n.x+x,n.y+y,.04)),color,chosen||active?COLORS.player:'#a5b49a',active?2:1);
      if(s.phase==='science') {
        const c=this.ctx;c.fillStyle='#475d3b';c.font=`bold ${clamp(this.unit*.075,10,14)}px sans-serif`;c.textAlign='center';c.textBaseline='middle';c.fillText(s.map.procedural?this.nodeOrdinals.get(n.id):n.id,p.sx,p.sy);
      } else if(active||chosen)this.ellipse(p.sx,p.sy,2.5,1.5,chosen?'#ffffff':COLORS.player);
      if(isGoal) {
        const flag=this.worldPoint(n.x+.13,n.y-.13,.025);this.line(flag,{sx:flag.sx,sy:flag.sy-35},'#617646',2.5);
        this.polygon([{sx:flag.sx,sy:flag.sy-36},{sx:flag.sx+21,sy:flag.sy-31},{sx:flag.sx,sy:flag.sy-23}],'#fffde7');
        this.polygon([{sx:flag.sx,sy:flag.sy-36},{sx:flag.sx+10,sy:flag.sy-34},{sx:flag.sx+10,sy:flag.sy-28},{sx:flag.sx,sy:flag.sy-30}],'#658354');
        if(s.phase!=='home')this.label('ARRIVÉE',p.sx,p.sy+(n.x+n.y>this.maxX+this.maxY-1?32:-48),'#688644','#faffeb',clamp(this.unit*.085,11,14));
      }
      if(isStart&&['preparation','countdown','selection'].includes(s.phase))this.label('DÉPART',p.sx,p.sy+28,COLORS.player,'#f5faff',10);
    }
  }
  car(position,color,robot=false,time=0,tag=true,offset=0) {
    if(!this.spriteAtlas)return this.paintCar(position,color,robot,time,tag,offset);
    // Le petit rebond ne dure que 0,55 s : conserver son dessin exact.
    if(!this.reducedMotion&&time>0&&time<.55)return this.paintCar(position,color,robot,time,tag,offset);
    const alongX=Math.abs(position.dx)>=Math.abs(position.dy),p=this.worldPoint(position.x+offset,position.y-offset);
    if(!this.visible({left:p.sx-128,top:p.sy-192,width:256,height:256}))return;
    const sprite=this.spriteAtlas.get(`car:${color}:${robot}:${alongX}:${tag}`,()=>this.paintCar({x:0,y:0,dx:alongX?1:0,dy:alongX?0:1},color,robot,2,tag,0),this.worldPoint(0,0));
    this.spriteAtlas.draw(sprite,p.sx,p.sy);
  }
  paintCar(position,color,robot=false,time=0,tag=true,offset=0) {
    const x=position.x+offset,y=position.y-offset,alongX=Math.abs(position.dx)>=Math.abs(position.dy);
    const w=alongX?.30:.16,d=alongX?.16:.30, p=this.worldPoint(x,y,.035);
    const bounce=!this.reducedMotion&&time>0&&time<.55?Math.abs(Math.sin(time*15))*.065:0;
    this.ellipse(p.sx,p.sy,this.unit*.20,this.unit*.087,'#253b3030');
    for(const side of [-1,1]) for(const end of [-1,1]) {
      this.box(x+(alongX?end*.095:side*.09),y+(alongX?side*.09:end*.095),.055,.055,.055,'#34483e',.026+bounce);
    }
    this.box(x,y,w,d,.085,color,.058+bounce);
    this.box(x,y,w*.51,d*.76,.078,tint(color,22),.142+bounce);
    const windshield='#d3efeb';
    this.box(x+(alongX?.025:0),y+(alongX?0:.025),w*.28,d*.59,.006,windshield,.222+bounce);
    if(robot) {
      const a=this.worldPoint(x,y,.223+bounce),b=this.worldPoint(x,y,.34+bounce);this.line(a,b,'#555f55',1.7);this.ellipse(b.sx,b.sy,3,3,'#ffd98d');
    } else this.box(x,y,.05,.05,.025,'#f5df90',.232+bounce);
    if(tag) {
      const t=this.worldPoint(x,y,.43+bounce);this.label(robot?'02 · ROBOT':'01 · TOI',t.sx,t.sy+(robot?-10:13),color,'#fffef5',clamp(this.unit*.075,9,12));
    }
  }
  vehicles(time) {
    const s=this.state;if(!s.map||s.phase==='science')return [];
    if(s.phase==='home'&&s.demo) {
      const elapsed=(time-s.demo.started)%s.demo.duration;
      const cars=[{p:vehiclePosition(s.map,s.demo.a.path,elapsed),color:COLORS.player,robot:false,offset:.09},{p:vehiclePosition(s.map,s.demo.b.path,elapsed),color:COLORS.robot,robot:true,offset:-.09}];
      return cars.map(car=>({...car,elapsed,tag:true}));
    }
    const racing=['race','result','science'].includes(s.phase), elapsed=racing?time-s.raceStarted:0;
    const player=vehiclePosition(s.map,s.path.length?s.path:[s.start],elapsed);
    const robot=vehiclePosition(s.map,s.ai?.path||[s.start],elapsed);
    const cars=[{p:player,color:COLORS.player,robot:false,offset:.09},{p:robot,color:COLORS.robot,robot:true,offset:-.09}];
    return cars.map(car=>({...car,elapsed:racing?elapsed:0,tag:racing}));
  }
  science() {
    const s=this.state;if(s.phase!=='science')return;
    const n=s.map.nodes.find(n=>n.id===s.result.optimal_path[1]);
    const p=this.worldPoint(n.x,n.y,.08);this.label('SOMMET = CARREFOUR',p.sx,p.sy-40,'#567432','#f4ffdb',11);
    const start=s.map.nodes.find(n=>n.id===s.start),mid=this.worldPoint((n.x+start.x)/2,(n.y+start.y)/2);
    this.label('ARÊTE = ROUTE',mid.sx-12,mid.sy+30,'#567432','#f4ffdb',10);
    
  }
  confetti(time) {
    const s=this.state;if(s.phase!=='result'||s.result?.winner!=='player'||this.reducedMotion)return;
    const elapsed=time-s.phaseStarted;if(elapsed>4)return;
    const c=this.ctx;
    for(let i=0;i<45;i++) {
      const x=this.width*.32+Math.sin(i*13)*this.width*.23*elapsed*.4;
      const y=this.height*.27-Math.abs(Math.cos(i*9))*100*elapsed+70*elapsed*elapsed+(i%7)*8;
      c.save();c.translate(x,y);c.rotate(elapsed+i);c.globalAlpha=Math.max(0,1-elapsed/4);c.fillStyle=[COLORS.player,COLORS.robot,'#a1c75e','#f2c567'][i%4];c.fillRect(-3,-3,6,9);c.restore();
    }
  }
  visible(sprite) {
    const b=this.visibleBounds;
    return !b||sprite.left+sprite.width>=b.left&&sprite.left<=b.right&&sprite.top+sprite.height>=b.top&&sprite.top<=b.bottom;
  }
  releaseScene() {
    // Libérer les surfaces natives avant d'allouer la ville suivante : le
    // ramasse-miettes JS ne mesure pas nécessairement leur poids côté GPU.
    for(const layer of Object.values(this.layers||{}))layer.dispose();
    this.spriteAtlas?.dispose();this.fastAtlas?.dispose();
    this.layers=null;this.spriteAtlas=null;this.fastAtlas=null;
    this.scenery=[];this.fastFrames?.clear();this.sceneKey=null;
  }
  prepareSceneLayers() {
    // Les petites villes sont beaucoup agrandies à l'écran : leurs sprites
    // doivent être préparés plus finement pour ne pas grossir des pixels flous.
    const count=this.state.map.nodes.length;
    const scale=count<=20?Math.min(3,2*this.dpr):count>80?.5:1;
    if(this.sceneKey===this.mapId&&this.cacheScale===scale)return;
    this.releaseScene();
    this.cacheScale=scale;
    this.layers={base:new TileLayer(this,()=>{this.ground(0);this.roads();},this.cacheScale),arrows:new TileLayer(this,()=>{this.directionMarkers();this.staticMarkers();},this.cacheScale)};
    this.spriteAtlas=new SpriteAtlas(this,this.cacheScale);
    this.scenery=this.decorations.map(d=>{
      const p=this.worldPoint(d.x,d.y),key=JSON.stringify([d.type,d.w,d.d,d.h,d.color,d.variant,d.mission]);
      const sprite=this.spriteAtlas.get(key,()=>d.type==='tree'?this.tree(d):this.building(d),p);
      return {depth:d.x+d.y,sprite,left:p.sx-128,top:p.sy-192,width:256,height:256};
    }).sort((a,b)=>a.depth-b.depth);
    // Préparer les variantes usuelles avant le chronométrage de la course.
    for(const robot of [false,true])for(const axis of [false,true])for(const tag of [false,true]){
      const color=robot?COLORS.robot:COLORS.player;
      this.spriteAtlas.get(`car:${color}:${robot}:${axis}:${tag}`,()=>this.paintCar({x:0,y:0,dx:axis?1:0,dy:axis?0:1},color,robot,2,tag),this.worldPoint(0,0));
    }
    this.fastAtlas=new SpriteAtlas(this,this.cacheScale,128);this.fastFrames=new Map();
    for(const edge of this.fastEdges){
      const a=this.nodesById[edge.source],b=this.nodesById[edge.target],dx=b.x-a.x,dy=b.y-a.y,key=`${dx}:${dy}:${!!edge.one_way}`;
      if(this.fastFrames.has(key)||Math.abs(dx)+Math.abs(dy)!==1)continue;
      const frames=[];
      for(let frame=0;frame<16;frame++)frames.push(this.fastAtlas.get(`${key}:${frame}`,()=>this.paintFastEdge(edge,{x:0,y:0},{x:dx,y:dy},frame*23/16/65),this.worldPoint(dx/2,dy/2)));
      this.fastFrames.set(key,frames);
    }
    this.sceneKey=this.mapId;
  }
  drawSceneryAndVehicles(time) {
    const cars=this.vehicles(time).sort((a,b)=>(a.p.x+a.p.y)-(b.p.x+b.p.y));let i=0;
    const drawCar=car=>this.car(car.p,car.color,car.robot,car.elapsed,car.tag,car.offset);
    // Fusion de deux listes déjà triées : ni tri de tous les bâtiments,
    // ni recomposition des bandes de décor à chaque mouvement de voiture.
    for(const entity of this.scenery){
      while(i<cars.length&&cars[i].p.x+cars[i].p.y<entity.depth)drawCar(cars[i++]);
      if(this.visible(entity))this.spriteAtlas.draw(entity.sprite,entity.left+128,entity.top+192);
    }
    while(i<cars.length)drawCar(cars[i++]);
  }
  render(time) {
    const c=this.ctx;c.setTransform(this.dpr,0,0,this.dpr,0,0);c.fillStyle='#edf2e7';c.fillRect(0,0,this.width,this.height);
    if(!this.state.map)return;
    if(this.mapId!==this.state.map.id)this.prepareDecorations(this.state.map);
    this.layout(time);this.prepareSceneLayers();
    const v=this.renderViewport;c.save();c.beginPath();c.rect(v.x,v.y,v.width,v.height);c.clip();this.camera.apply(c,this.dpr);
    this.layers.base.draw(this);
    if(this.state.phase==='science')this.drawPath(this.state.result.optimal_path,COLORS.optimal,0);
    else if(this.state.phase!=='home'){if(this.state.phase!=='waiting'){this.exploration(time);this.drawPath(this.state.path,COLORS.player,3);}}
    else if(this.state.demo){this.drawPath(this.state.demo.a.path,COLORS.player,3);this.drawPath(this.state.demo.b.path,COLORS.robot,-3);}
    this.fastRoads(time);this.layers.arrows.draw(this);
    this.markers(time);
    this.drawSceneryAndVehicles(time);
    if(this.state.phase==='waiting')this.exploration(time);
    this.science();c.restore();this.confetti(time);
  }
  hitTest(clientX,clientY) {
    if(!this.state.map)return null;
    const rect=this.canvas.getBoundingClientRect(),x=clientX-rect.left,y=clientY-rect.top;
    const v=this.renderViewport||this.camera.viewport;
    if(x<v.x||x>v.x+v.width||y<v.y||y>v.y+v.height)return null;
    let nearest=null;for(const n of this.nodePoints){const d=Math.hypot(x-n.sx,y-n.sy);if(!nearest||d<nearest.d)nearest={id:n.id,d};}
    if(nearest&&nearest.d<=Math.max(18,this.unit*this.camera.zoom*.13))return nearest.id;
    const current=this.state.path.at(-1),candidates=neighbors(this.state.map,current);
    let best=null,bestDistance=15;
    for(const id of candidates) {
      const a=this.screenNodes.get(current),b=this.screenNodes.get(id);
      const dx=b.sx-a.sx,dy=b.sy-a.sy,t=clamp(((x-a.sx)*dx+(y-a.sy)*dy)/(dx*dx+dy*dy),0,1);
      const distance=Math.hypot(x-a.sx-t*dx,y-a.sy-t*dy);
      if(distance<bestDistance){bestDistance=distance;best=id;}
    }
    return best;
  }
}
