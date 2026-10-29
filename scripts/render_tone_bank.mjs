// Local offline synthesis only. No samples, CDN, telemetry or generated code.
import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
import {fileURLToPath} from 'node:url'
import crypto from 'node:crypto'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const runtime=path.resolve(process.env.MAJOOR_TONE_RUNTIME || path.join(root,'runtime/tonejs'))
const require=createRequire(path.join(runtime,'package.json'))
const puppeteer=require('puppeteer-core')
const version=require('tone/package.json').version
if(version!=='15.1.22')throw Error('Tone.js 15.1.22 is required')
const chrome=[process.env.MAJOOR_CHROME,process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES,'Google/Chrome/Application/chrome.exe'),process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'],'Microsoft/Edge/Application/msedge.exe'),'/usr/bin/google-chrome','/usr/bin/chromium'].find(p=>p && fs.existsSync(p))
if(!chrome)throw Error('Install Chrome/Edge or set MAJOOR_CHROME')
const output=path.resolve(process.argv[2] || path.join(runtime,'bank'))
fs.mkdirSync(output,{recursive:true})
const browser=await puppeteer.launch({executablePath:chrome,headless:true,args:['--autoplay-policy=no-user-gesture-required'],timeout:60000})
const kinds=['impact','hit','whoosh','swell','shutter','glitch','sub_drop','riser','reverse','downlifter','click','pop','tick','sparkle','tape_stop','stutter','ui_click_soft','ui_click_crisp','notification_soft','notification_confirm','notification_alert','metal_tick','metal_chime','glass_ping','stereo_whoosh_lr','stereo_whoosh_rl','stereo_sweep','logo_soft','logo_bold','logo_sparkle']
const entries={}
try{
 const page=await browser.newPage()
 await page.setContent('<!doctype html><meta charset="utf-8"><title>Local Tone synthesis</title>')
 // Seed before Tone creates its noise buffers. Rendering order is fixed.
 await page.evaluate(()=>{let seed=1729;Math.random=()=>{seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296}})
 await page.addScriptTag({path:path.join(runtime,'node_modules/tone/build/Tone.js')})
 for(const kind of kinds){
  const result=await page.evaluate(async kind=>{
   const duration={impact:1.2,hit:.4,whoosh:.6,swell:1,shutter:.3,glitch:.3,sub_drop:1.5,riser:1.6,reverse:.8,downlifter:1,click:.15,pop:.25,tick:.12,sparkle:.9,tape_stop:.55,stutter:.4,ui_click_soft:.15,ui_click_crisp:.16,notification_soft:.65,notification_confirm:.8,notification_alert:.65,metal_tick:.25,metal_chime:1.2,glass_ping:.85,stereo_whoosh_lr:.7,stereo_whoosh_rl:.7,stereo_sweep:1,logo_soft:1.4,logo_bold:1.3,logo_sparkle:1.5}[kind]
   const channels=kind.startsWith('stereo_') ? 2 : 1
   const buffer=await Tone.Offline(()=>{
    const limiter=new Tone.Limiter(-2).toDestination()
    function route(start,length,pan){
      if(pan===null)return limiter
      const p=new Tone.Panner(Array.isArray(pan)?pan[0]:pan).connect(limiter)
      if(Array.isArray(pan)){
        p.pan.setValueAtTime(pan[0],start)
        p.pan.linearRampToValueAtTime(pan[1],start+length)
      }
      return p
    }
    function osc(freq,end,start,length,amp=.3,type='sine',pan=null){
      const gain=new Tone.Gain(0).connect(route(start,length,pan))
      const o=new Tone.Oscillator(freq,type).connect(gain)
      gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(amp,start+.003)
      gain.gain.exponentialRampToValueAtTime(.0001,start+length)
      o.frequency.setValueAtTime(freq,start);o.frequency.exponentialRampToValueAtTime(Math.max(20,end),start+length*.8)
      o.start(start).stop(start+length+.01)
    }
    function noise(start,length,from,to,amp=.2,shape='decay',pan=null){
      const gain=new Tone.Gain(0).connect(route(start,length,pan))
      const filter=new Tone.Filter(from,'lowpass').connect(gain)
      const n=new Tone.Noise('white').connect(filter)
      filter.frequency.setValueAtTime(from,start);filter.frequency.exponentialRampToValueAtTime(to,start+length)
      if(shape==='rise'){
       gain.gain.setValueAtTime(.0001,start);gain.gain.exponentialRampToValueAtTime(amp,start+length*.93);gain.gain.linearRampToValueAtTime(0,start+length)
      }else if(shape==='sweep'){
       gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(amp,start+length*.5);gain.gain.linearRampToValueAtTime(0,start+length)
      }else{
       gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(amp,start+.002);gain.gain.exponentialRampToValueAtTime(.0001,start+length)
      }
      n.start(start).stop(start+length+.01)
    }
    switch(kind){
     case 'impact':osc(210,48,.002,.85,.65);noise(.002,.18,1700,250,.5);osc(670,190,.003,.32,.08,'triangle');break
     case 'hit':osc(220,100,.002,.23,.55);noise(.002,.08,4500,900,.25);break
     case 'whoosh':noise(.002,.55,300,10000,.65,'sweep');break
     case 'swell':noise(.002,.85,180,5500,.55,'rise');break
     case 'shutter':noise(.002,.025,10000,2500,.6);noise(.052,.05,6000,1000,.4);break
     case 'glitch':for(let i=0;i<5;i++){noise(.002+i*.045,.025,8500,800,.28);osc(1800+i*270,600,.002+i*.045,.024,.12,'square')}break
     case 'sub_drop':osc(130,30,.002,1.25,.65);noise(.002,.06,1000,200,.15);break
     case 'riser':noise(.002,1.4,180,11000,.48,'rise');osc(110,880,.002,1.4,.055,'triangle');break
     case 'reverse':noise(.002,.65,400,8500,.55,'rise');break
     case 'downlifter':noise(.002,.85,10000,180,.45);break
     case 'click':noise(.002,.025,10000,3500,.45);osc(1600,900,.002,.04,.12);break
     case 'pop':osc(720,180,.002,.12,.5);noise(.002,.022,2200,500,.12);break
     case 'tick':noise(.002,.018,9000,5000,.4);break
     case 'sparkle':for(let i=0;i<4;i++)osc([1318,1975,2637,3951][i],[1318,1975,2637,3951][i],.002+i*.075,.45,.15);break
     case 'tape_stop':osc(700,28,.002,.4,.25,'sawtooth');noise(.002,.35,4500,120,.12);break
     case 'stutter':for(let i=0;i<4;i++)noise(.002+i*.075,.035,4500,1500,.35);break
     case 'ui_click_soft':osc(1100,540,.002,.045,.18);noise(.002,.018,2600,900,.07);break
     case 'ui_click_crisp':noise(.002,.014,11500,5000,.4);osc(2900,1350,.002,.025,.12);break
     case 'notification_soft':osc(659,659,.002,.3,.22);osc(988,988,.12,.35,.15);break
     case 'notification_confirm':osc(784,784,.002,.24,.20);osc(1175,1175,.14,.40,.19);break
     case 'notification_alert':osc(880,880,.002,.14,.15,'triangle');osc(698,698,.20,.20,.13,'triangle');break
     case 'metal_tick':{
       const m=new Tone.MetalSynth({harmonicity:3.1,modulationIndex:12,resonance:3300,octaves:1.4,envelope:{attack:.001,decay:.055,sustain:0,release:.035},volume:-14}).connect(limiter)
       m.triggerAttackRelease(210,.06,.002);break
     }
     case 'metal_chime':{
       const m=new Tone.MetalSynth({harmonicity:2.7,modulationIndex:7,resonance:2000,octaves:1.1,envelope:{attack:.002,decay:.55,sustain:0,release:.25},volume:-19}).connect(limiter)
       m.triggerAttackRelease(340,.55,.002);osc(1568,1568,.002,.72,.1);break
     }
     case 'glass_ping':osc(2349,2349,.002,.55,.2);osc(3761,3761,.003,.32,.07);osc(5527,5527,.004,.17,.025);break
     case 'stereo_whoosh_lr':noise(.002,.60,300,10000,.6,'sweep',[-1,1]);break
     case 'stereo_whoosh_rl':noise(.002,.60,420,9000,.6,'sweep',[1,-1]);break
     case 'stereo_sweep':noise(.002,.85,220,6500,.4,'sweep',[-.9,.9]);osc(240,760,.05,.7,.06,'triangle',[.9,-.9]);break
     case 'logo_soft':for(let i=0;i<3;i++)osc([392,587,784][i],[392,587,784][i],.002+i*.15,.7,.14);break
     case 'logo_bold':osc(160,65,.002,.5,.3);for(let i=0;i<3;i++)osc([196,294,392][i],[196,294,392][i],.04+i*.1,.75,.1,'triangle');break
     case 'logo_sparkle':for(let i=0;i<4;i++)osc([784,1175,1568,2349][i],[784,1175,1568,2349][i],.002+i*.12,.75,.12);break

    }
   },duration,channels,48000)
   const audio=Array.from({length:channels},(_,c)=>buffer.getChannelData(c))
   const frames=audio[0].length
   let peak=0;for(const x of audio)for(const v of x)peak=Math.max(peak,Math.abs(v))
   if(!Number.isFinite(peak)||peak<1e-6)throw Error('Silent/invalid cue '+kind)
   const pcm=new Int16Array(frames*channels)
   for(let i=0;i<frames;i++)for(let c=0;c<channels;c++)pcm[i*channels+c]=Math.round(Math.max(-1,Math.min(1,audio[c][i]/peak*.9))*32767)
   const bytes=new Uint8Array(pcm.buffer);let encoded=''
   for(let i=0;i<bytes.length;i+=16384)encoded+=String.fromCharCode(...bytes.subarray(i,i+16384))
   return {pcm:btoa(encoded),duration,frames,channels}
  },kind)
  const pcm=Buffer.from(result.pcm,'base64'),header=Buffer.alloc(44)
  header.write('RIFF');header.writeUInt32LE(36+pcm.length,4);header.write('WAVEfmt ',8);header.writeUInt32LE(16,16);header.writeUInt16LE(1,20);header.writeUInt16LE(result.channels,22);header.writeUInt32LE(48000,24);header.writeUInt32LE(96000*result.channels,28);header.writeUInt16LE(2*result.channels,32);header.writeUInt16LE(16,34);header.write('data',36);header.writeUInt32LE(pcm.length,40)
  const file=kind+'.wav';fs.writeFileSync(path.join(output,file),Buffer.concat([header,pcm]))
  const peakAnchors={whoosh:.277,swell:.7925,riser:1.304,reverse:.6065,stereo_whoosh_lr:.302,stereo_whoosh_rl:.302,stereo_sweep:.427}
  const anchor_sample=Math.min(result.frames-1,Math.round((peakAnchors[kind]??.004)*48000))
  entries[kind]={file,license:'Procedurally synthesized; no third-party samples',source:'VideoTools Tone.js offline synthesizer',frames:result.frames,channels:result.channels,anchor_sample,anchor_kind:kind in peakAnchors?'designed_peak':'attack',sha256:crypto.createHash('sha256').update(Buffer.concat([header,pcm])).digest('hex')}
 }
 const renderer=crypto.createHash('sha256').update(fs.readFileSync(fileURLToPath(import.meta.url))).digest('hex')
 fs.writeFileSync(path.join(output,'tone.json'),JSON.stringify({engine:'tone.js',version,palette:2,renderer,rate:48000,entries},null,2))
 console.log(JSON.stringify({engine:'Tone.js',version,cues:kinds.length,output}))
}finally{await browser.close()}
