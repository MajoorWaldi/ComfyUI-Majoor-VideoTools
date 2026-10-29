// Internal, offline layout probe. Uses the installed optional Tone browser runtime.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const runtime=process.env.MAJOOR_TONE_RUNTIME||path.join(root,'runtime/tonejs');
const require=createRequire(path.join(runtime,'package.json'));
const puppeteer=require('puppeteer-core');
const chrome=[process.env.MAJOOR_CHROME,process.env.PROGRAMFILES&&path.join(process.env.PROGRAMFILES,'Google/Chrome/Application/chrome.exe'),process.env['PROGRAMFILES(X86)']&&path.join(process.env['PROGRAMFILES(X86)'],'Microsoft/Edge/Application/msedge.exe'),'/usr/bin/google-chrome','/usr/bin/chromium'].find(p=>p&&fs.existsSync(p));
if(!chrome)throw Error('Optional browser unavailable');
const project=path.resolve(process.argv[2]),times=JSON.parse(process.argv[3]);
// Never write the probe inside the project: HyperFrames lint (--strict) rejects a second HTML file with data-composition-id.
fs.rmSync(path.join(project,'layout-probe.html'),{force:true});
const base=pathToFileURL(project+path.sep).href;
const html=fs.readFileSync(path.join(project,'compositions/motion.html'),'utf8').replace(/<head>/i,`<head><base href="${base}"><script src="assets/gsap.min.js"></script><script src="assets/hyperframes_layers.js"></script>`);
const probeDir=fs.mkdtempSync(path.join(os.tmpdir(),'majoor-layout-'));
const wrapper=path.join(probeDir,'layout-probe.html');
fs.writeFileSync(wrapper,html);
const browser=await puppeteer.launch({executablePath:chrome,headless:true,args:['--allow-file-access-from-files'],timeout:15000});
try{
 const page=await browser.newPage();
 await page.setRequestInterception(true);
 page.on('request',r=>/^https?:/.test(r.url())?r.abort():r.continue());
 await page.goto(pathToFileURL(wrapper).href,{waitUntil:'load',timeout:15000});
 const samples=[];
 for(const time of times){
  const data=await page.evaluate(async time=>{
   await Promise.all(Object.values(window.__hf?.buildReady||{}));
   Object.values(window.__timelines||{}).forEach(tl=>tl.seek(time,false));
   const pending=[];window.dispatchEvent(new CustomEvent('hf-seek',{detail:{time,waitUntil:p=>pending.push(p)}}));
   await Promise.all(pending);
   return {canvas:window.__majoorLayout||[],html:[...document.querySelectorAll('.words')].filter(e=>{const s=getComputedStyle(e.closest('.title')||e);return s.visibility!=='hidden'&&+s.opacity>0}).map(e=>{const r=e.getBoundingClientRect();return {content:e.textContent,rect:[r.left,r.top,r.right,r.bottom]}})};
  },time);
  samples.push({time,...data});
 }
 fs.writeFileSync(path.join(project,'previews/layout.json'),JSON.stringify({samples,scope:'Actual Canvas boxes and HTML bounds; no face recognition or contrast guarantee'},null,2));
}finally{await browser.close();fs.rmSync(probeDir,{recursive:true,force:true});}
