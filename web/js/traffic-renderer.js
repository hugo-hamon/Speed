import { trafficState, TRAFFIC_NAMES } from './traffic.js';

export function drawTraffic(r, time, groundOnly=false) {
  const s=r.state;
  const clock=s.phase==='home'&&s.demo?(time-s.demo.started)%s.demo.duration:
    ['race','result'].includes(s.phase)?Math.max(0,time-s.raceStarted):0;
  for(const edge of r.trafficEdges){
    const a=r.nodesById[edge.source],b=r.nodesById[edge.target];
    const x=(a.x+b.x)/2,y=(a.y+b.y)/2,dx=b.x-a.x,dy=b.y-a.y;
    const length=Math.hypot(dx,dy),ux=dx/length,uy=dy/length;
    const pos=(along=0,across=0,z=.04)=>r.worldPoint(x+ux*along-uy*across,y+uy*along+ux*across,z);
    const p=pos();if(!r.visible({left:p.sx-180,top:p.sy-130,width:360,height:230}))continue;
    const event=edge.traffic_event,status=trafficState(edge,clock);
    if(groundOnly){
      if(event.kind==='rail'){
        // A continuous bed also supports a local crossing over water.
        r.polygon([pos(-.16,-.93,.02),pos(.16,-.93,.02),pos(.16,.93,.02),pos(-.16,.93,.02)],'#aca997','#817e6e',1);
        for(let t=-.85;t<=.85;t+=.13)r.line(pos(-.14,t,.025),pos(.14,t,.025),'#806b54',4);
        for(const side of [-1,1])r.line(pos(side*.08,-.93,.035),pos(side*.08,.93,.035),'#dce0dd',2.5);
      } else if(event.kind==='bridge'){
        const lift=status.closed?.30:0;
        for(const side of [-1,1]){
          r.polygon([pos(side*.28,-.14,.04),pos(0,-.14,.04+lift),pos(0,.14,.04+lift),pos(side*.28,.14,.04)],'#a4b7b2','#526e70',2);
          for(const across of [-.15,.15])r.line(pos(side*.28,across,.10),pos(0,across,.10+lift),'#e9ddba',2);
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
          const t=(progress-.5)*1.35-i*.28,tx=x-uy*t,ty=y+ux*t;
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
    if(s.phase!=='home'){
      const label=pos(0,.28,.32);
      const text=status.closed?`${TRAFFIC_NAMES[event.kind]} · ${status.remaining.toFixed(1)} s`:
        event.kind==='signal'?(status.phase>event.period-.6?'Feu orange':'Feu vert'):event.kind==='rail'?'Voie libre':'Pont abaissé';
      r.label(['race','result'].includes(s.phase)?text:`Départ · ${text}`,label.sx,label.sy,status.closed?'#93412e':'#436851','#fff9e9',10);
    }
  }
}
