// Caches libérés au changement de carte. Aucun canvas aux dimensions de la ville.
export class TileLayer {
  constructor(renderer,paint,scale=1) {
    this.tiles=[];const main=renderer.ctx,size=512,pad=2;
    try {
      for(let y=0;y<renderer.worldHeight;y+=size)for(let x=0;x<renderer.worldWidth;x+=size){
        const width=Math.min(size,renderer.worldWidth-x),height=Math.min(size,renderer.worldHeight-y);
        const canvas=document.createElement('canvas');canvas.width=Math.ceil(width*scale)+pad*2;canvas.height=Math.ceil(height*scale)+pad*2;
        renderer.ctx=canvas.getContext('2d');renderer.ctx.setTransform(scale,0,0,scale,pad-x*scale,pad-y*scale);paint();
        this.tiles.push({canvas,left:x,top:y,width,height,pad,scale});
      }
    } finally {renderer.ctx=main;}
  }
  dispose() {
    for(const {canvas} of this.tiles){canvas.width=0;canvas.height=0;}
    this.tiles.length=0;
  }
  draw(renderer) {
    const c=renderer.ctx,m=c.getTransform();
    // Partager exactement les mêmes frontières en pixels physiques : des
    // rectangles fractionnaires laissent sinon voir le fond entre les tuiles.
    // La bordure peinte fournit les texels nécessaires au rééchantillonnage.
    for(const t of this.tiles)if(renderer.visible(t)){
      const left=(Math.round(t.left*m.a+m.e)-m.e)/m.a;
      const top=(Math.round(t.top*m.d+m.f)-m.f)/m.d;
      const right=(Math.round((t.left+t.width)*m.a+m.e)-m.e)/m.a;
      const bottom=(Math.round((t.top+t.height)*m.d+m.f)-m.f)/m.d;
      c.drawImage(t.canvas,t.pad,t.pad,t.width*t.scale,t.height*t.scale,
        left,top,right-left,bottom-top);
    }
  }
}

export class SpriteAtlas {
  constructor(renderer,scale=1,cell=256){this.renderer=renderer;this.scale=scale;this.entries=new Map();this.pages=[];this.cell=cell;this.pageSize=1024;this.columns=this.pageSize/cell;this.perPage=this.columns**2;}
  dispose(){
    for(const canvas of this.pages){canvas.width=0;canvas.height=0;}
    this.pages.length=0;this.entries.clear();
  }
  get(key,paint,anchor){
    if(this.entries.has(key))return this.entries.get(key);
    const r=this.renderer,main=r.ctx,index=this.entries.size,slot=index%this.perPage;
    if(!slot){const canvas=document.createElement('canvas');canvas.width=canvas.height=this.pageSize*this.scale;this.pages.push(canvas);}
    const canvas=this.pages.at(-1),x=slot%this.columns*this.cell,y=Math.floor(slot/this.columns)*this.cell,s=this.scale;
    r.ctx=canvas.getContext('2d');r.ctx.save();r.ctx.setTransform(s,0,0,s,0,0);r.ctx.beginPath();r.ctx.rect(x,y,this.cell,this.cell);r.ctx.clip();r.ctx.translate(x+this.cell/2-anchor.sx,y+this.cell*.75-anchor.sy);
    try{paint();}finally{r.ctx.restore();r.ctx=main;}
    const sprite={canvas,sx:x*s,sy:y*s,sw:this.cell*s,sh:this.cell*s,width:this.cell,height:this.cell};this.entries.set(key,sprite);return sprite;
  }
  draw(sprite,x,y){this.renderer.ctx.drawImage(sprite.canvas,sprite.sx,sprite.sy,sprite.sw,sprite.sh,x-this.cell/2,y-this.cell*.75,sprite.width,sprite.height);}
}
