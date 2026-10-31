const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const driver=fs.readFileSync(process.argv[2],'utf8');
async function trace(content,time,extra={}){
  const calls=[],rects=[],centers=[],listeners={},stack=[];
  const ctx={globalAlpha:1,fillStyle:'white',font:'900 80px Inter',measureText(s){return {width:String(s).length*parseFloat(this.font.split(' ')[1])*.5}},save(){stack.push({globalAlpha:this.globalAlpha,fillStyle:this.fillStyle})},restore(){Object.assign(this,stack.pop())},fillText(word){calls.push({word,alpha:this.globalAlpha,color:this.fillStyle})},strokeText(){},clearRect(){},translate(x,y){centers.push([x,y])},rotate(){},scale(){},beginPath(){},rect(...r){rects.push(r)},clip(){},fillRect(){}};
  const canvas={width:1000,height:1000,getContext:()=>ctx};
  const document={querySelector:()=>canvas,createElement:()=>({getContext:()=>ctx})};
  const window={addEventListener:(event,fn)=>listeners[event]=fn};
  vm.runInNewContext(driver,{window,document,console,Image:class{}});
  const layer={type:'text',content,start:0,end:3,in_time:.25,size:.08,opacity:1,color:'white',font:'clean',rotate:0,stroke:.05,safe:true,position:'center',animation:'words',out:'none',repeat:1,...extra};
  window.__majoorLayers.attach({duration:3,fps:24,accent:'#ff0000',safe_boxes:{center:[60,60,940,860]},text_timing:{word_stagger:.09,exit_ratio:.5,minimum_exit:.1},layers:[layer]});
  await window.__hf.buildReady.majoorLayers;calls.length=rects.length=centers.length=0;
  let done;listeners['hf-seek']({detail:{time,waitUntil:p=>done=p}});await done;
  return {calls,rects,centers,layout:window.__majoorLayout};
}
(async()=>{
  let r=await trace('ONE TWO THREE FOUR\nFIVE SIX',.12);
  assert.deepEqual(r.calls.filter(x=>x.alpha>0).map(x=>x.word),['ONE','TWO']);
  r=await trace('ONE TWO THREE FOUR\nFIVE SIX',1);
  assert.deepEqual(r.calls.filter(x=>x.color==='#ff0000').map(x=>x.word),['SIX']);
  r=await trace('ONE TWO',.12,{repeat:2});assert.equal(r.calls[2].alpha,0);
  r=await trace('ONE TWO',1,{accent_last:false});assert.equal(r.calls.filter(x=>x.color==='#ff0000').length,0);
  r=await trace('ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN',.12,{size:.25});
  assert.deepEqual(r.calls.filter(x=>x.alpha>0).map(x=>x.word),['ONE','TWO']);
  r=await trace('HELLO',.125,{animation:'fade'});assert.equal(r.calls[0].alpha,.9375);
  r=await trace('HELLO',.125,{animation:'fade',ease:'linear'});assert.equal(r.calls[0].alpha,.5);
  r=await trace('HELLO',2.95,{animation:'fade',out:'fade',end:null});assert.ok(Math.abs(r.calls[0].alpha-.4)<1e-8);
  r=await trace('HELLO WORLD',1,{x:.99,y:.99,rotate:25});
  assert.deepEqual(r.rects[0],[60,60,880,800]);assert.ok(r.centers[0][0]<940&&r.centers[0][1]<860);
  assert.equal(r.layout.length,1);assert.ok(r.layout[0].effective_font_px>0);
  assert.ok(r.layout[0].rect[0]>=60&&r.layout[0].rect[2]<=940.001);
  r=await trace('ONE TWO',.5,{word_times:[0,1]});
  assert.deepEqual(r.calls.map(x=>[x.word,x.alpha>0]),[['ONE',true],['TWO',false]]);
  r=await trace('AB',.01,{animation:'split_letters'});
  assert.deepEqual(r.calls.map(x=>[x.word,x.alpha>0]),[['A',true],['B',false]]);
  r=await trace('HELLOWORLD',.1,{animation:'scramble'});
  assert.equal(r.calls[0].word.length,10);assert.equal(r.calls[0].word.slice(0,4),'HELL');assert.notEqual(r.calls[0].word.slice(4),'OWORLD');
  r=await trace('ONE TWO',.5,{animation:'karaoke_fill',word_times:[0,1]});
  assert.ok(r.calls.some(x=>x.word==='ONE'&&x.color==='#ff0000')&&r.rects.some(x=>x[2]>0));
  for(const animation of ['scale_pop','blur_in','wiggle','mask_reveal']){
    r=await trace('HELLO',.125,{animation});assert.ok(r.calls.length>0&&r.calls[0].word==='HELLO'&&r.calls[0].alpha>0,animation);
  }
  console.log('word renderer: order, wrapping, repeats, accent, fade, exit, word times and the new animations passed');
})().catch(e=>{console.error(e);process.exitCode=1});
