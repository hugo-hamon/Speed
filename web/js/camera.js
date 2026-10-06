const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const smooth=t=>{t=clamp(t,0,1);return t*t*(3-2*t);};

export class Camera {
  constructor() {
    this.x=0;this.y=0;this.zoom=1;this.targetX=0;this.targetY=0;this.targetZoom=1;
    this.key=null;this.large=false;this.introDuration=1.4;this.manualUntil=0;
  }
  configure(key,bounds,viewport,mode,unit,reducedMotion=false) {
    const signature=`${key}:${mode}:${viewport.x}:${viewport.y}:${viewport.width}:${viewport.height}`;
    this.viewport=viewport;this.bounds=bounds;
    this.fitZoom=Math.min(viewport.width/(bounds.right-bounds.left),viewport.height/(bounds.bottom-bounds.top))*.97;
    this.playZoom=Math.max(this.fitZoom,(viewport.width>1300?135:100)/unit);
    this.large=this.playZoom>this.fitZoom*1.2;
    this.introDuration=this.large&&!reducedMotion?4.4:1.4;
    if(this.key===signature)return;
    const sameGame=this.mode==='game'&&mode==='game'&&this.mapKey===key;
    this.key=signature;this.mapKey=key;this.mode=mode;
    if(!sameGame){this.overview(true);this.manualUntil=0;}
    else {this.targetZoom=clamp(this.targetZoom,this.fitZoom,this.playZoom*1.8);this.clampTargets();}
  }
  screen(point) {
    const v=this.viewport;
    return {sx:v.x+v.width/2+(point.sx-this.x)*this.zoom,sy:v.y+v.height/2+(point.sy-this.y)*this.zoom};
  }
  world(sx,sy) {
    const v=this.viewport;
    return {sx:this.x+(sx-v.x-v.width/2)/this.zoom,sy:this.y+(sy-v.y-v.height/2)/this.zoom};
  }
  contains(sx,sy) {const v=this.viewport;return sx>=v.x&&sx<=v.x+v.width&&sy>=v.y&&sy<=v.y+v.height;}
  clampTargets() {
    const b=this.bounds,v=this.viewport,hx=v.width/(2*this.targetZoom),hy=v.height/(2*this.targetZoom);
    this.targetX=2*hx>=b.right-b.left?(b.left+b.right)/2:clamp(this.targetX,b.left+hx,b.right-hx);
    this.targetY=2*hy>=b.bottom-b.top?(b.top+b.bottom)/2:clamp(this.targetY,b.top+hy,b.bottom-hy);
  }
  overview(immediate=false) {
    const b=this.bounds;
    this.targetX=(b.left+b.right)/2;this.targetY=(b.top+b.bottom)/2;this.targetZoom=this.fitZoom;
    if(immediate){this.x=this.targetX;this.y=this.targetY;this.zoom=this.targetZoom;}
  }
  framePoints(points,immediate=false) {
    if(!points.length)return;
    const xs=points.map(p=>p.sx),ys=points.map(p=>p.sy),v=this.viewport;
    const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
    this.targetZoom=clamp(Math.min((v.width-100)/Math.max(1,right-left),(v.height-100)/Math.max(1,bottom-top)),this.fitZoom,this.playZoom);
    this.targetX=(left+right)/2;this.targetY=(top+bottom)/2;this.clampTargets();
    if(immediate){this.x=this.targetX;this.y=this.targetY;this.zoom=this.targetZoom;}
  }
  focus(point,immediate=false) {
    this.targetX=point.sx;this.targetY=point.sy;this.clampTargets();
    if(immediate){this.x=this.targetX;this.y=this.targetY;}
  }
  ensureVisible(point,time=0) {
    if(time<this.manualUntil||this.zoom<=this.fitZoom*1.05)return;
    const p=this.screen(point),v=this.viewport,margin=Math.min(170,v.height*.28);
    if(p.sx<v.x+margin||p.sx>v.x+v.width-margin||p.sy<v.y+margin||p.sy>v.y+v.height-margin)this.focus(point);
  }
  zoomAt(factor,sx,sy,time) {
    const point=this.world(sx,sy),v=this.viewport;
    this.targetZoom=clamp(this.targetZoom*factor,this.fitZoom,this.playZoom*1.8);
    this.targetX=point.sx-(sx-v.x-v.width/2)/this.targetZoom;
    this.targetY=point.sy-(sy-v.y-v.height/2)/this.targetZoom;
    this.clampTargets();this.manualUntil=time+2;
  }
  intro(elapsed,start,goal,reducedMotion) {
    if(!this.large||reducedMotion)return;
    const b=this.bounds,center={sx:(b.left+b.right)/2,sy:(b.top+b.bottom)/2};
    let from,to,t,zoomFrom,zoomTo;
    if(elapsed<1){from=to=goal;t=0;zoomFrom=zoomTo=this.playZoom;}
    else if(elapsed<2.5){from=goal;to=center;t=smooth((elapsed-1)/1.5);zoomFrom=this.playZoom;zoomTo=this.fitZoom;}
    else {from=center;to=start;t=smooth((elapsed-2.5)/1.6);zoomFrom=this.fitZoom;zoomTo=this.playZoom;}
    this.targetX=from.sx+(to.sx-from.sx)*t;this.targetY=from.sy+(to.sy-from.sy)*t;
    this.targetZoom=zoomFrom+(zoomTo-zoomFrom)*t;this.clampTargets();
    this.x=this.targetX;this.y=this.targetY;this.zoom=this.targetZoom;
  }
  update(dt,reducedMotion=false) {
    const factor=reducedMotion?1:1-Math.exp(-Math.min(dt,.1)*10);
    this.x+=(this.targetX-this.x)*factor;this.y+=(this.targetY-this.y)*factor;this.zoom+=(this.targetZoom-this.zoom)*factor;
  }
  apply(context,dpr) {
    const v=this.viewport,z=this.zoom;
    context.setTransform(dpr*z,0,0,dpr*z,dpr*(v.x+v.width/2-this.x*z),dpr*(v.y+v.height/2-this.y*z));
  }
}
