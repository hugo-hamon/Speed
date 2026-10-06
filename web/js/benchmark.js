import { CanvasBackend, WebGLBackend } from './benchmark-renderers.js';
import { buildScene, sceneCommands } from './benchmark-scene.js';
const $=id=>document.getElementById(id);
const WARMUP=2,MEASURE=8,ORDER=['canvas','webgl','webgl','canvas'];
const names={canvas:'Canvas 2D optimisé',webgl:'WebGL sprites'};
export function summarize(samples) {
  const sorted=[...samples].sort((a,b)=>a-b),sum=samples.reduce((a,b)=>a+b,0);
  return {frames:samples.length,seconds:sum/1000,fps:sum?1000*samples.length/sum:0,p50_ms:sorted[Math.floor(sorted.length*.5)]||0,p95_ms:sorted[Math.max(0,Math.ceil(sorted.length*.95)-1)]||0,over33ms:samples.filter(t=>t>33.34).length};
}
export const benchmark={running:false,token:0,runs:[],backends:null,scene:null,raf:0};
function controls(running){for(const el of $('options').elements)el.disabled=running;$('stop').disabled=!running;}
function release(){cancelAnimationFrame(benchmark.raf);if(benchmark.backends)for(const b of Object.values(benchmark.backends))b.dispose();benchmark.backends=null;benchmark.scene=null;$('stage').replaceChildren();}
function report(reason){
  const complete=reason==='Terminé',groups={};
  for(const name of ['canvas','webgl'])groups[name]=summarize(benchmark.runs.filter(r=>r.backend===name).flatMap(r=>r.intervals));
  const payload={benchmark:'speed-render-comparison-v1',complete,reason,date:new Date().toISOString(),settings:benchmark.settings,viewport:benchmark.viewport,devicePixelRatio:window.devicePixelRatio,userAgent:navigator.userAgent,webgl:benchmark.glInfo,protocol:{order:ORDER,warmup_seconds:WARMUP,measure_seconds:MEASURE,shared_sprites:true,world_unit:64,tile_pixels:512,roads_animated:false,ai:false,current_game_renderer:false},runs:benchmark.runs.map(r=>({backend:r.backend,...summarize(r.intervals)})),summary:groups};
  if(complete)payload.webgl_to_canvas_fps_ratio=groups.canvas.fps?groups.webgl.fps/groups.canvas.fps:null;
  benchmark.report=payload;$('report-text').value=JSON.stringify(payload,null,2);$('report').hidden=false;
  $('results').textContent=complete?`Canvas 2D : ${groups.canvas.fps.toFixed(1)} FPS · p95 ${groups.canvas.p95_ms.toFixed(1)} ms\nWebGL : ${groups.webgl.fps.toFixed(1)} FPS · p95 ${groups.webgl.p95_ms.toFixed(1)} ms\nRapport WebGL / Canvas : ×${payload.webgl_to_canvas_fps_ratio?.toFixed(2)}. Un résultat proche ne garantit pas de gain avec une migration.`:'Test incomplet : ne pas utiliser ce résultat pour comparer les moteurs.';
}
function finish(reason){
  if(!benchmark.running)return;benchmark.running=false;benchmark.token++;cancelAnimationFrame(benchmark.raf);controls(false);$('status').textContent=reason;
  report(reason);release();
}
function frame(ms){
  if(!benchmark.running)return;
  if(document.hidden){finish('Interrompu : onglet masqué');return;}
  try {
    const t=ms/1000;
    if(benchmark.passStart===null)benchmark.passStart=t;
    const elapsed=t-benchmark.passStart,name=ORDER[benchmark.pass],backend=benchmark.backends[name];
    if(benchmark.previous!==null&&elapsed>=WARMUP&&benchmark.previous-benchmark.passStart>=WARMUP)benchmark.samples.push((t-benchmark.previous)*1000);
    benchmark.previous=t;
    const commands=sceneCommands(benchmark.scene,Math.max(0,elapsed-WARMUP),benchmark.settings,benchmark.viewport);
    backend.draw(commands);
    if(t-benchmark.lastUi>.25){$('status').textContent=`Passage ${benchmark.pass+1}/4 · ${names[name]} · ${elapsed<WARMUP?'chauffe':`${Math.ceil(WARMUP+MEASURE-elapsed)} s restantes`}`;benchmark.lastUi=t;}
    if(elapsed>=WARMUP+MEASURE){
      benchmark.runs.push({backend:name,intervals:benchmark.samples});benchmark.pass++;
      if(benchmark.pass===ORDER.length){finish('Terminé');return;}
      benchmark.samples=[];benchmark.previous=null;benchmark.passStart=null;selectBackend();
    }
    benchmark.raf=requestAnimationFrame(frame);
  }catch(e){finish(`Erreur de rendu : ${e.message}`);}
}
function selectBackend(){for(const [name,b] of Object.entries(benchmark.backends))b.canvas.hidden=name!==ORDER[benchmark.pass];}
export async function start(){
  if(benchmark.running)return;release();benchmark.running=true;const token=++benchmark.token;
  benchmark.runs=[];benchmark.report=null;benchmark.glInfo=null;$('report').hidden=true;$('results').textContent='';$('copy-status').textContent='';controls(true);$('status').textContent='Préparation locale du décor et des textures…';
  const [width,height]=$('size').value.split(',').map(Number);benchmark.settings={width,height,cars:Number($('cars').value),motion:$('motion').value};
  const rect=$('stage').getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2);
  benchmark.viewport={width:Math.round(rect.width*dpr),height:Math.round(rect.height*dpr),cssWidth:rect.width,cssHeight:rect.height,dpr};
  try{
    const make=()=>{const c=document.createElement('canvas');c.width=benchmark.viewport.width;c.height=benchmark.viewport.height;$('stage').append(c);return c;};
    benchmark.backends={canvas:new CanvasBackend(make())};
    const gpu=new WebGLBackend(make());benchmark.backends.webgl=gpu;benchmark.glInfo=gpu.info;
    gpu.canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(benchmark.running&&token===benchmark.token)finish('Interrompu : contexte WebGL perdu');});
    const check=()=>{if(token!==benchmark.token)throw new Error('Test annulé');};
    const scene=await buildScene(width,height,check);check();benchmark.scene=scene;
    for(const image of scene.images){if(image.width>gpu.info.maxTextureSize||image.height>gpu.info.maxTextureSize)throw new Error('Texture trop grande pour ce GPU.');gpu.upload(image);}
    if(gpu.gl.getError()!==gpu.gl.NO_ERROR)throw new Error('Échec du chargement des textures WebGL.');
    benchmark.pass=0;benchmark.passStart=null;benchmark.previous=null;benchmark.samples=[];benchmark.lastUi=0;selectBackend();benchmark.raf=requestAnimationFrame(frame);
  }catch(e){if(token===benchmark.token)finish(e.message);}
}
$('options').addEventListener('submit',event=>{event.preventDefault();start();});$('stop').addEventListener('click',()=>finish('Arrêt demandé'));
window.addEventListener('resize',()=>{if(benchmark.running)finish('Interrompu : fenêtre redimensionnée');});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&benchmark.running)finish('Interrompu : onglet masqué');});
document.addEventListener('keydown',event=>{if(event.key==='Escape')finish('Arrêt demandé');});
window.addEventListener('pagehide',()=>{benchmark.running=false;benchmark.token++;release();});
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('report-text').value);$('copy-status').textContent='Résultats copiés.';}catch{ $('report-text').focus();$('report-text').select();$('copy-status').textContent='Utilise Ctrl+C pour copier le rapport sélectionné.';}});
