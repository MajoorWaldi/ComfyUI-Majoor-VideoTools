/* MIT — SECATOR. Deterministic compositor driven by HyperFrames hf-seek. */
window.__majoorLayers = {
  attach(config) {
    const layers=config.layers||[], assets=config.layer_assets||{};
    if(!layers.length)return;
    const canvas=document.querySelector('#layerCanvas'), W=canvas.width,H=canvas.height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    const scratch=document.createElement('canvas');scratch.width=W;scratch.height=H;
    const sc=scratch.getContext('2d',{willReadFrequently:true});
    const maskCanvas=document.createElement('canvas');maskCanvas.width=W;maskCanvas.height=H;
    const mc=maskCanvas.getContext('2d',{willReadFrequently:true});
    const cache=new Map();
    async function image(path){
      if(!path)return null;
      if(cache.has(path))return cache.get(path);
      const promise=new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Missing layer asset '+path));img.src=path;});
      cache.set(path,promise);while(cache.size>12)cache.delete(cache.keys().next().value);
      return promise;
    }
    const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
    const timing=config.text_timing||{word_stagger:.09,exit_ratio:.5,minimum_exit:.1};
    const fontsReady=document.fonts?Promise.all([...new Set(layers.filter(l=>l.type==='text'||l.type==='track').map(l=>l.font==='serif'?'400 32px "Playfair Display"':l.font==='mono'?'900 32px monospace':l.font==='clean'?'900 32px Inter':'900 32px Oswald'))].map(font=>document.fonts.load(font))).then(()=>document.fonts.ready):Promise.resolve();
    const eased=(p,mode)=>mode==='linear'?p:mode==='smooth'?p*p*(3-2*p):mode==='back'?1+2.70158*Math.pow(p-1,3)+1.70158*Math.pow(p-1,2):1-Math.pow(1-p,4);
    function rng(seed){return()=>{seed=(Math.imul(seed,1664525)+1013904223)|0;return(seed>>>0)/4294967296;};}
    function state(l,t,index,n){
      const end=l.end==null?config.duration:l.end;if(t<l.start||t>=end)return null;
      const p=clamp((t-l.start)/l.in_time),ease=eased(p,l.ease);
      const s={a:l.opacity,dx:0,dy:0,scale:1,reveal:1,t:t-l.start};
      if(l.animation==='fade')s.a*=ease;
      if(l.animation==='pop'){const q=p-1;s.scale=.6+.4*(1+2.70158*q*q*q+1.70158*q*q);s.a*=Math.min(p*3,1);}
      if(l.animation==='slide_up'||l.animation==='slide_down'){s.dy=(1-ease)*.08*(l.animation==='slide_up'?1:-1);s.a*=ease;}
      if(l.animation==='slide_left'||l.animation==='slide_right'){s.dx=(1-ease)*.1*(l.animation==='slide_left'?1:-1);s.a*=ease;}
      if(['typewriter','draw'].includes(l.animation))s.reveal=p;
      if(l.animation==='glitch'&&p<1){const r=rng(index*31+n);s.dx=(r()-.5)*.06;s.dy=(r()-.5)*.02;}
      if(l.animation==='shake'){s.dx=.004*Math.sin(t*90);s.dy=.004*Math.cos(t*70);}
      if(l.animation==='float'){s.dy=.012*Math.sin((t-l.start)*4);s.a*=Math.min(p*2,1);}
      if(l.out==='fade'){const leave=Math.max(timing.minimum_exit,l.in_time*timing.exit_ratio);s.a*=clamp((end-t)/leave);}
      if(l.motion_from&&l.motion_to){
        const q=ease;
        const mix=k=>l.motion_from[k]+(l.motion_to[k]-l.motion_from[k])*q;
        s.dx+=mix('x');s.dy+=mix('y');s.scale*=mix('scale');s.rotate=mix('rotate');
      }
      return s;
    }
    const positions={center:[.5,.5],top:[.5,0],bottom:[.5,1],left:[0,.5],right:[1,.5],top_left:[0,0],top_right:[1,0],bottom_left:[0,1],bottom_right:[1,1]};
    function text(l,s,x=null,y=null){
      ctx.save();let px=Math.max(H*l.size*s.scale,6);const margin=Math.min(W,H)*.05;
      const family=l.type==='emoji'?'"Segoe UI Emoji",sans-serif':(l.font==='serif'?'"Playfair Display"':l.font==='mono'?'monospace':l.font==='clean'?'Inter,sans-serif':'Oswald,sans-serif');
      const font=()=>{ctx.font=`${l.font==='serif'?400:900} ${px}px ${family}`;};font();
      const box=(config.safe_boxes||{})[l.position]||(config.safe_boxes||{}).center||[0,0,W,H];
      const [left,top,right,bottom]=l.safe?box:[margin,margin,W-margin,H-margin];
      const boxWidth=right-left,boxHeight=bottom-top;
      let rows=String(l.content).split('\n');
      if(l.safe){
        const maxWidth=boxWidth*.96,longest=Math.max(1,...String(l.content).split(/\s+/).map(word=>ctx.measureText(word).width));
        if(longest>maxWidth){px=Math.max(1,px*maxWidth/longest);font();}
        const wrap=()=>String(l.content).split('\n').flatMap(line=>{const lines=[];let current='';for(const word of line.split(/\s+/)){const next=current?current+' '+word:word;if(current&&ctx.measureText(next).width>maxWidth){lines.push(current);current=word;}else current=next;}lines.push(current);return lines;});
        rows=wrap();const needed=px*1.15*rows.length*(l.repeat||1);
        if(needed>boxHeight*.96){px=Math.max(1,px*boxHeight*.96/needed);font();rows=wrap();}
      }
      const fullWidth=Math.max(...rows.map(v=>ctx.measureText(v).width));
      const totalHeight=px*1.15*rows.length*(l.repeat||1),pos=positions[l.position]||positions.center;
      if(x==null){x=l.x!=null?l.x*W:left+pos[0]*(right-left-fullWidth);y=l.x!=null?l.y*H:top+pos[1]*(bottom-top-totalHeight);}
      const angle=(l.rotate+(s.rotate||0))*Math.PI/180;
      let cx=x+s.dx*W+fullWidth/2,cy=y+s.dy*H+totalHeight/2,fit=1;
      if(l.safe){
        const pad=px*Math.max(.15,l.stroke||0),halfW=(Math.abs(Math.cos(angle))*fullWidth+Math.abs(Math.sin(angle))*totalHeight)/2+pad;
        const halfH=(Math.abs(Math.sin(angle))*fullWidth+Math.abs(Math.cos(angle))*totalHeight)/2+pad;
        fit=Math.min(1,boxWidth/(halfW*2),boxHeight/(halfH*2));
        cx=clamp(cx,left+halfW*fit,right-halfW*fit);
        cy=clamp(cy,top+halfH*fit,bottom-halfH*fit);
        ctx.beginPath();ctx.rect(left,top,boxWidth,boxHeight);ctx.clip();
      }
      ctx.translate(cx,cy);ctx.rotate(angle);ctx.scale(fit,fit);
      const rw=(Math.abs(Math.cos(angle))*fullWidth+Math.abs(Math.sin(angle))*totalHeight)*fit/2;
      const rh=(Math.abs(Math.sin(angle))*fullWidth+Math.abs(Math.cos(angle))*totalHeight)*fit/2;
      window.__majoorLayout.push({content:l.content,rect:[cx-rw,cy-rh,cx+rw,cy+rh],effective_font_px:px*fit,safe:!!l.safe,safe_box:[left,top,right,bottom],alpha:clamp(s.a)});
      ctx.globalAlpha=clamp(s.a);ctx.fillStyle=l.color;ctx.textBaseline='top';
      if(l.background){ctx.fillStyle=l.background;ctx.fillRect(-fullWidth/2-px*.15,-totalHeight/2-px*.15,fullWidth+px*.3,totalHeight+px*.3);ctx.fillStyle=l.color;}
      const outline=l.stroke!=null?l.stroke:.05;
      const count=rows.reduce((n,row)=>n+row.split(/\s+/).filter(Boolean).length,0)*(l.repeat||1);let wordIndex=0;
      for(let repeat=0;repeat<(l.repeat||1);repeat++)rows.forEach((row,i)=>{
        const yy=-totalHeight/2+(repeat*rows.length+i)*px*1.15;
        if(l.animation==='words'){
          const words=row.split(/\s+/).filter(Boolean),space=ctx.measureText(' ').width;let wx=-fullWidth/2;
          words.forEach((word,k)=>{
            const index=wordIndex++,q=clamp((s.t-index*timing.word_stagger)/l.in_time),e=eased(q,l.ease),last=index===count-1&&l.accent_last!==false&&config.accent;
            ctx.save();ctx.beginPath();ctx.rect(wx-px*.1,yy-px*.05,ctx.measureText(word).width+px*.2,px*1.2);ctx.clip();
            ctx.globalAlpha=clamp(s.a)*e;const lift=(1-e)*px*.6;ctx.fillStyle=last?config.accent:l.color;
            if(outline){ctx.strokeStyle='black';ctx.lineJoin='round';ctx.lineWidth=Math.max(1,px*outline);ctx.strokeText(word,wx,yy+lift);}
            ctx.fillText(word,wx,yy+lift);ctx.restore();wx+=ctx.measureText(word).width+space;
          });return;
        }
        const visible=l.animation==='typewriter'?row.slice(0,Math.max(1,Math.ceil(row.length*s.reveal))):row;
        if(outline){ctx.strokeStyle='black';ctx.lineJoin='round';ctx.lineWidth=Math.max(1,px*outline);ctx.strokeText(visible,-fullWidth/2,yy);}
        ctx.fillText(visible,-fullWidth/2,yy);
      });ctx.restore();
    }
    function shape(l,s){
      const [x,y,w,h]=l.rect.map((v,i)=>v*(i%2===0?W:H));
      const ww=w*s.scale,hh=h*s.scale,xx=x+(w-ww)/2+s.dx*W,yy=y+(h-hh)/2+s.dy*H;
      ctx.save();ctx.translate(xx+ww/2,yy+hh/2);ctx.rotate((s.rotate||0)*Math.PI/180);ctx.translate(-xx-ww/2,-yy-hh/2);ctx.globalAlpha=clamp(s.a);ctx.fillStyle=l.color;ctx.strokeStyle=l.color;
      if(l.type==='box')ctx.fillRect(xx,yy,ww,hh);
      else{const arm=Math.min(ww,hh)*l.arm*s.reveal;ctx.lineWidth=Math.max(1,Math.min(W,H)*l.thickness);ctx.beginPath();[[xx,yy,1,1],[xx+ww,yy,-1,1],[xx,yy+hh,1,-1],[xx+ww,yy+hh,-1,-1]].forEach(([a,b,sx,sy])=>{ctx.moveTo(a+sx*arm,b);ctx.lineTo(a,b);ctx.lineTo(a,b+sy*arm);});ctx.stroke();}ctx.restore();
    }
    function vector(l,s){
      const x=(l.at[0]+s.dx)*W,y=(l.at[1]+s.dy)*H;
      ctx.save();ctx.globalAlpha=clamp(s.a);ctx.strokeStyle=l.color;ctx.fillStyle=l.color;ctx.lineWidth=Math.max(1,Math.min(W,H)*l.thickness);ctx.lineCap='round';
      ctx.translate(x,y);ctx.rotate((s.rotate||0)*Math.PI/180);ctx.scale(s.scale,s.scale);ctx.beginPath();
      if(l.shape==='line'){ctx.moveTo(0,0);ctx.lineTo((l.to[0]-l.at[0])*W*s.reveal,(l.to[1]-l.at[1])*H*s.reveal);ctx.stroke();}
      else{ctx.arc(0,0,Math.min(W,H)*l.radius,0,Math.PI*2*(l.animation==='draw'?s.reveal:1));if(l.shape==='dot')ctx.fill();else ctx.stroke();}ctx.restore();
    }
    async function scalar(path,color,alpha){
      const img=await image(path);if(!img)return;
      mc.clearRect(0,0,W,H);mc.drawImage(img,0,0,W,H);
      const pixels=mc.getImageData(0,0,W,H);for(let p=0;p<pixels.data.length;p+=4)pixels.data[p+3]=pixels.data[p];mc.putImageData(pixels,0,0);
      mc.globalCompositeOperation='source-in';mc.fillStyle=color;mc.fillRect(0,0,W,H);mc.globalCompositeOperation='source-over';
      ctx.save();ctx.globalAlpha=clamp(alpha);ctx.drawImage(maskCanvas,0,0);ctx.restore();
    }
    async function effect(l,s,t,index){
      const amount=l.amount*s.a, kind=l.kind;
      sc.clearRect(0,0,W,H);sc.drawImage(canvas,0,0);
      if(['chromatic','glitch','grain'].includes(kind)){
        const src=ctx.getImageData(0,0,W,H),dst=sc.createImageData(W,H),r=rng(index*17+3);
        const shift=Math.max(1,Math.round(W*.018*amount));
        for(let y=0;y<H;y++){
          const strip=kind==='glitch'&&r()<.08?Math.round((r()-.5)*W*.12*amount):0;
          for(let x=0;x<W;x++){
            const p=(y*W+x)*4,noise=kind==='grain'?(r()-.5)*70*amount:0;
            for(let c=0;c<3;c++){let xx=clamp(x+strip+(kind==='chromatic'?(c-1)*shift:0),0,W-1);dst.data[p+c]=clamp(src.data[(y*W+xx)*4+c]+noise,0,255);}dst.data[p+3]=255;
          }
        }sc.putImageData(dst,0,0);
      } else if(['pan','roll','handheld'].includes(kind)){
        sc.clearRect(0,0,W,H);sc.save();sc.translate(W/2,H/2);
        sc.rotate((kind==='roll'?.035*amount*Math.sin(t*.7):kind==='handheld'?.008*amount*Math.sin(t*3.7):0));
        const scale=1+.08*amount;sc.scale(scale,scale);
        sc.translate(W*.025*amount*Math.sin(t*(kind==='handheld'?4.1:.65)),kind==='handheld'?H*.015*amount*Math.sin(t*5.3):0);sc.drawImage(canvas,-W/2,-H/2);sc.restore();
      } else {
        sc.save();sc.globalAlpha=clamp(amount*.6);sc.fillStyle=l.color;sc.strokeStyle=l.color;sc.lineWidth=Math.max(1,Math.min(W,H)*l.thickness);
        if(kind==='vignette'){const g=sc.createRadialGradient(W/2,H/2,Math.min(W,H)*.2,W/2,H/2,Math.max(W,H)*.68);g.addColorStop(0,'transparent');g.addColorStop(1,'black');sc.fillStyle=g;sc.fillRect(0,0,W,H);}
        else if(kind==='light_leak'){const g=sc.createLinearGradient(-W*.2+Math.sin(t*.8)*W*.4,0,W,0);g.addColorStop(0,l.color);g.addColorStop(.55,'transparent');sc.fillStyle=g;sc.globalCompositeOperation='screen';sc.fillRect(0,0,W,H);}
        else if(kind==='dots'){const step=Math.max(4,W*l.spacing);for(let y=0;y<H;y+=step)for(let x=0;x<W;x+=step){sc.beginPath();sc.arc(x,y,Math.min(W,H)*l.radius,0,Math.PI*2);sc.fill();}}
        else{if(l.flicker)sc.globalAlpha*=.35+.65*(Math.sin((t-l.start)*l.flicker*Math.PI*2)>=0?1:0);const step=Math.max(2,(kind==='scanlines'?H:W)*l.spacing),offset=((t-l.start)*l.speed*step)%step;sc.beginPath();for(let y=offset;y<H;y+=step){sc.moveTo(0,y);sc.lineTo(W,y);}if(kind==='grid')for(let x=offset;x<W;x+=step){sc.moveTo(x,0);sc.lineTo(x,H);}sc.stroke();}sc.restore();
      }
      if(l.target!=='frame'){
        const img=await image(assets.masks[index]);mc.clearRect(0,0,W,H);mc.drawImage(img,0,0,W,H);
        const mask=mc.getImageData(0,0,W,H),changed=sc.getImageData(0,0,W,H),base=ctx.getImageData(0,0,W,H);
        for(let p=0;p<changed.data.length;p+=4){const a=l.target==='subject'?mask.data[p]/255:1-mask.data[p]/255;for(let c=0;c<3;c++)changed.data[p+c]=base.data[p+c]*(1-a)+changed.data[p+c]*a;}sc.putImageData(changed,0,0);
      }ctx.clearRect(0,0,W,H);ctx.drawImage(scratch,0,0);
    }
    async function draw(t){
      await fontsReady;
      window.__majoorLayout=[];
      const index=clamp(Math.floor(t*config.fps+1e-5),0,(assets.count||Math.round(config.duration*config.fps))-1);
      ctx.clearRect(0,0,W,H);
      if(assets.footage){const path=assets.frame_paths?assets.frame_paths[index]:assets.frame_pattern+String(index).padStart(6,'0')+'.png';if(path){const frame=await image(path);ctx.drawImage(frame,0,0,W,H);}}
      for(let n=0;n<layers.length;n++){
        const l=layers[n],s=state(l,t,index,n);if(!s)continue;
        if(l.type==='effect'){await effect(l,s,t,index);continue;}
        if(l.type==='outline'){const paths=assets.outlines[String(n)];await scalar(paths.halo[index],l.color,s.a);await scalar(paths.ring[index],l.color,s.a);continue;}
        if(l.type==='track'){
          const point=assets.tracks[String(n)][index];if(!point)continue;
          const [x,y]=point,r=Math.min(W,H)*l.radius*s.scale,tx=x+l.offset[0]*W,ty=y+l.offset[1]*H;
          ctx.save();ctx.globalAlpha=clamp(s.a);ctx.strokeStyle=l.color;ctx.fillStyle=l.color;ctx.lineWidth=Math.max(1,Math.min(W,H)*.004);ctx.beginPath();
          if(l.shape==='ring'){ctx.arc(x,y,r,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.arc(x,y,r/4,0,Math.PI*2);ctx.fill();}
          if(l.shape==='dot'){ctx.arc(x,y,r/2,0,Math.PI*2);ctx.fill();}
          if(l.shape==='cross'){ctx.moveTo(x-r,y);ctx.lineTo(x+r,y);ctx.moveTo(x,y-r);ctx.lineTo(x,y+r);ctx.stroke();}
          if(l.line&&(l.label||l.emoji)){ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(tx,ty);ctx.stroke();}ctx.restore();
          if(l.label)text({...l,type:'text',content:l.label,rotate:0,stroke:.08},s,tx,ty-H*l.size/2);
          if(l.emoji)text({...l,type:'emoji',content:l.emoji,rotate:0,stroke:0,size:l.size*1.6},s,tx,ty-H*l.size*2);
          continue;
        }
        if(l.type==='vector')vector(l,s);else if(l.type==='text'||l.type==='emoji')text(l,s);else shape(l,s);
      }
    }
    window.addEventListener('hf-seek',e=>{e.detail.waitUntil(draw(e.detail.time));});
    window.__hf=window.__hf||{};window.__hf.buildReady=window.__hf.buildReady||{};window.__hf.buildReady.majoorLayers=draw(0);
  }
};
