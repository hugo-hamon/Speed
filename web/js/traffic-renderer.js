import { trafficState } from './traffic.js';

function trafficClock(s,time) {
  return s.phase==='home'&&s.demo?(time-s.demo.started)%s.demo.duration:
    ['race','result'].includes(s.phase)?Math.max(0,time-s.raceStarted):0;
}

// Navigation overlays must not look like a second road across the open gap.
// The caller saves/restores the context so this clips only route/heat overlays.
export function clipRaisedBridges(r,time) {
  const clock=trafficClock(r.state,time),holes=new Path2D();let count=0;
  const bounds=r.visibleBounds;
  holes.rect(bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top);
  for(const edge of r.trafficEdges){
    if(edge.traffic_event.kind!=='bridge'||!trafficState(edge,clock).closed)continue;
    const a=r.nodesById[edge.source],b=r.nodesById[edge.target],length=Math.hypot(b.x-a.x,b.y-a.y);
    const dx=(b.x-a.x)/length,dy=(b.y-a.y)/length,x=(a.x+b.x)/2,y=(a.y+b.y)/2;
    [[-.30,-.20],[.30,-.20],[.30,.20],[-.30,.20]].forEach(([along,across],i)=>{
      const p=r.worldPoint(x+dx*along-dy*across,y+dy*along+dx*across,.032);
      i?holes.lineTo(p.sx,p.sy):holes.moveTo(p.sx,p.sy);
    });holes.closePath();count++;
  }
  if(count)r.ctx.clip(holes,'evenodd');
}

export function drawTraffic(r, time, pass='foreground') {
  const s=r.state,clock=trafficClock(s,time);
  for(const edge of r.trafficEdges){
    const isSignal=edge.traffic_event.kind==='signal';
    if((pass==='signals'&&!isSignal)||(pass==='foreground'&&isSignal))continue;
    const a=r.nodesById[edge.source],b=r.nodesById[edge.target];
    const x=(a.x+b.x)/2,y=(a.y+b.y)/2,dx=b.x-a.x,dy=b.y-a.y;
    const length=Math.hypot(dx,dy),ux=dx/length,uy=dy/length;
    const pos=(along=0,across=0,z=.04)=>r.worldPoint(x+ux*along-uy*across,y+uy*along+ux*across,z);
    const p=pos();if(!r.visible({left:p.sx-180,top:p.sy-130,width:360,height:230}))continue;
    const event=edge.traffic_event,status=trafficState(edge,clock);
    if(pass==='ground'){
      if(event.kind==='rail'){
        // Generation keeps the full rail bed and moving train on dry land.
        r.polygon([pos(-.16,-.80,.02),pos(.16,-.80,.02),pos(.16,.80,.02),pos(-.16,.80,.02)],'#aca997','#817e6e',1);
        for(let i=-5;i<=5;i++)r.line(pos(-.14,i*.14,.025),pos(.14,i*.14,.025),'#806b54',4);
        for(const side of [-1,1])r.line(pos(side*.08,-.80,.035),pos(side*.08,.80,.035),'#dce0dd',2.5);
      } else if(event.kind==='bridge'){
        const angle=status.closed?Math.PI*.4:0;
        const lift=.28*Math.sin(angle),shortening=.28*(1-Math.cos(angle));
        for(const side of [-1,1]){
          const tip=side*shortening;
          r.polygon([pos(side*.28,-.14,.04),pos(tip,-.14,.04+lift),pos(tip,.14,.04+lift),pos(side*.28,.14,.04)],'#a4b7b2','#526e70',2);
          for(const across of [-.15,.15])r.line(pos(side*.28,across,.10),pos(tip,across,.10+lift),'#e9ddba',2);
        }
      }
      continue;
    }
    // Reduced motion freezes decorative movement, but lights/barriers still
    // show their true state so the explanation stays correct.
    const progress=r.reducedMotion?.5:Math.min(1,status.phase/event.closed_for);
    if(event.kind==='signal'){
      for(const side of [-1,1]){
        const foot=pos(side*.12,side*.22),head=pos(side*.12,side*.22,.38);
        r.line(foot,head,'#47585c',3);
        r.ctx.fillStyle='#344449';r.ctx.beginPath();r.ctx.roundRect(head.sx-5,head.sy-15,10,27,4);r.ctx.fill();
        const amber=!status.closed && status.phase>event.period-.6;
        for(let i=0;i<3;i++)r.ellipse(head.sx,head.sy-10+i*8,3,3,
          [status.closed?'#ff6254':'#684a49',amber?'#ffc64d':'#6c6342',!status.closed&&!amber?'#8de392':'#446052'][i]);
      }
    } else if(event.kind==='rail') {
      if(status.closed){
        for(let i=0;i<2;i++){
          // Keep both carriages within the shortened track, away from nearby roads.
          const t=(progress-.5)+.14-i*.28,tx=x-uy*t,ty=y+ux*t;
          for(const side of [-1,1]){
            const wheel=r.worldPoint(tx+ux*.09+uy*side*.08,ty+uy*.09-ux*side*.08,.05);
            r.ellipse(wheel.sx,wheel.sy,3,3,'#364447');
          }
          r.box(tx,ty,uy?.26:.16,ux?.26:.16,.15,i?'#b89564':'#4c8b91',.045);
          r.box(tx,ty,uy?.18:.12,ux?.18:.12,.04,'#e7efe4',.195);
          r.box(tx,ty,uy?.15:.08,ux?.15:.08,.025,'#b5d9de',.235);
        }
      }
    } else {
      const boatX=Math.max(r.minX-.25,Math.min(r.maxX+.25,x+(status.closed?(progress-.5)*1.4:.8)));
      const boatY=s.map.river_y??y;
      r.worldPolygon([[boatX-.24,boatY-.09,.03],[boatX+.17,boatY-.09,.03],[boatX+.28,boatY,.03],[boatX+.17,boatY+.09,.03],[boatX-.24,boatY+.09,.03]],'#4a7d91');
      r.box(boatX-.03,boatY,.22,.12,.1,'#fff0cd',.045);
      r.box(boatX-.07,boatY,.08,.08,.06,'#d27b57',.145);
    }
    if(event.kind!=='signal'){
      for(const side of [-1,1]){
        r.line(pos(side*.25,-.20),pos(side*.25,-.20,.13),'#666750',3);
        const end=status.closed?pos(side*.25,.18,.13):pos(side*.25,-.18,.44);
        r.line(pos(side*.25,-.20,.13),end,'#fff4de',4);
        r.line(pos(side*.25,-.20,.13),end,'#d96951',3,[5,5]);
      }
    }
  }
}
