import { CityRenderer } from './renderer.js';
import { stressMap } from './stress.js';
import { COLORS } from './state.js';
const canvas=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;};
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));

export async function buildScene(width,height,check=()=>{}) {
  const map=stressMap(width,height),source=Object.create(CityRenderer.prototype);
  source.state={map,phase:'benchmark',path:[],start:map.nodes[0].id};source.reducedMotion=false;source.unit=64;
  source.prepareDecorations(map);source.unit=64;source.cx=0;source.cy=0;
  const a=source.worldPoint(-.8,height-.2),b=source.worldPoint(width-.2,-.8),top=source.worldPoint(-.8,-.8,1),bottom=source.worldPoint(width-.2,height-.2,-.3);
  const bounds={left:Math.floor(a.sx-20),right:Math.ceil(b.sx+20),top:Math.floor(top.sy-20),bottom:Math.ceil(bottom.sy+20)};
  const tiles=[];
  // Petites textures, sans bitmap géant de toute la ville. Bord d'un pixel
  // partagé pour le filtrage linéaire, exclu du rectangle effectivement dessiné.
  for(let y=bounds.top;y<bounds.bottom;y+=512)for(let x=bounds.left;x<bounds.right;x+=512){
    check();const image=canvas(514,514);source.ctx=image.getContext('2d');source.ctx.setTransform(1,0,0,1,1-x,1-y);
    source.ground(0);source.roads();source.fastRoads(0);source.markers(0);
    tiles.push({image,sx:1,sy:1,sw:512,sh:512,x,y,w:512,h:512});await nextFrame();
  }
  check();const atlas=canvas(1024,1024),context=atlas.getContext('2d'),cache=new Map();
  const makeSprite=(key,paint,anchor)=>{
    if(cache.has(key))return cache.get(key);
    const i=cache.size,sx=i%8*128,sy=Math.floor(i/8)*128;
    if(i>=64)throw new Error('Atlas trop petit.');
    source.ctx=context;context.save();context.beginPath();context.rect(sx,sy,128,128);context.clip();context.setTransform(1,0,0,1,sx+64-anchor.sx,sy+96-anchor.sy);paint();context.restore();
    const sprite={image:atlas,sx,sy,sw:128,sh:128,w:128,h:128};cache.set(key,sprite);return sprite;
  };
  const props=source.decorations.map(d=>{
    const anchor=source.worldPoint(d.x,d.y),key=JSON.stringify([d.type,d.w,d.d,d.h,d.color,d.variant,d.mission]);
    const sprite=makeSprite(key,()=>d.type==='tree'?source.tree(d):source.building(d),anchor);
    return {...sprite,x:anchor.sx-64,y:anchor.sy-96,depth:d.x+d.y};
  });
  const carSprites=[false,true].map(robot=>makeSprite(`car-${robot}`,()=>source.car({x:0,y:0,dx:1,dy:0},robot?COLORS.robot:COLORS.player,robot,2,false),source.worldPoint(0,0)));
  return {bounds,tiles,props,carSprites,width,height,point:(x,y)=>source.worldPoint(x,y),images:[...tiles.map(t=>t.image),atlas]};
}

export function sceneCommands(scene,time,settings,viewport) {
  const b=scene.bounds,fit=Math.min(viewport.width/(b.right-b.left),viewport.height/(b.bottom-b.top))*.94;
  const moving=settings.motion==='moving',zoom=fit*(moving?1.25+.25*Math.sin(time*.65):1);
  const cx=(b.left+b.right)/2+(moving?Math.sin(time*.45)*(b.right-b.left)*.18:0),cy=(b.top+b.bottom)/2+(moving?Math.cos(time*.45)*(b.bottom-b.top)*.15:0);
  const cars=Array.from({length:settings.cars},(_,i)=>{
    const span=scene.width-1,distance=(time*(1+i%3*.25)+i*.73)%(span*2),x=distance<span?distance:span*2-distance,y=settings.cars===2?Math.floor(scene.height/2)+i:i%scene.height,p=scene.point(x,y);
    return {...scene.carSprites[i%2],x:p.sx-64,y:p.sy-96,depth:x+y};
  });
  const ordered=[...scene.tiles,...[...scene.props,...cars].sort((a,b)=>a.depth-b.depth)],commands=[];
  for(const q of ordered){const x=viewport.width/2+(q.x-cx)*zoom,y=viewport.height/2+(q.y-cy)*zoom,w=q.w*zoom,h=q.h*zoom;if(x+w<0||y+h<0||x>viewport.width||y>viewport.height)continue;commands.push({...q,x,y,w,h});}
  return commands;
}
