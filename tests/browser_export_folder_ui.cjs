const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const element = () => ({hidden:false,disabled:false,textContent:'',value:'',open:false,
  showModal(){this.open=true;},focus(){this.focused=true;},removeAttribute(){}});
const ids = ['renderDialog','chooseRenderDirectory','openRenderDirectory','openDefaultRenderDirectory',
  'renderDirectoryInput','downloadRender','renderDirectory','renderMessage','renderPercent',
  'renderProgress','renderResult','renderError','cancelRender','confirmRender','renderClose'];
const els = Object.fromEntries(ids.map(id=>[id,element()]));
els.renderProgress.style={};
const manual=element();
let status={available:true,directory:null}, chosen='/chosen folder', chooserCalls=0, renders=[], warnings=[], pending;
const ctx={els,document:{getElementById:()=>manual},IS_DESKTOP_HOST:false,
  window:{location:{origin:'http://127.0.0.1:5500'}},project:{exportRange:null,title:'test'},
  currentRenderJob:null,renderPollTimer:null,formatTime:String,t:x=>x,clone:structuredClone,
  toast:(...args)=>warnings.push(args),setTimeout:()=>0,clearTimeout(){},
  api:async(path,options)=>{
    if(path==='/api/export-folder') return status;
    if(path==='/api/export-folder/choose'){chooserCalls++; if(pending) return await pending; return {directory:chosen};}
    if(path==='/api/render'){renders.push(JSON.parse(options.body));return {id:'job'};}
    return {id:'job',state:'complete',progress:1,result:{path:'/chosen folder/test.mp4',width:320,height:320,fps:12,duration:1,elapsed:1}};
  }};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/app-render.js','utf8'),ctx);
async function main(){
  await ctx.openRenderDialog();
  assert.equal(els.chooseRenderDirectory.hidden,false);
  assert.equal(els.renderDirectoryInput.hidden,true);
  await ctx.startRender();assert.equal(renders.length,0); // no folder chosen
  await ctx.chooseRenderDirectory();assert.equal(els.renderDirectoryInput.value,'/chosen folder');
  chosen=null;await ctx.chooseRenderDirectory();assert.equal(els.renderDirectoryInput.value,'/chosen folder');
  await ctx.startRender();assert.equal(renders[0].outputDirectory,'/chosen folder');
  ctx.currentRenderJob=null;
  status={available:false,directory:null};await ctx.openRenderDialog();
  assert.equal(els.chooseRenderDirectory.hidden,true);assert.equal(els.renderDirectoryInput.hidden,false);
  els.renderDirectoryInput.value='/manual path';await ctx.startRender();
  assert.equal(renders.at(-1).outputDirectory,'/manual path');ctx.currentRenderJob=null;
  status={available:true,directory:'/previous'};els.renderDirectoryInput.value='';await ctx.openRenderDialog();
  assert.equal(els.renderDirectoryInput.value,'/previous');
  let complete;pending=new Promise(resolve=>complete=resolve);
  const before=chooserCalls, first=ctx.chooseRenderDirectory();
  await ctx.chooseRenderDirectory();await ctx.startRender();
  assert.equal(chooserCalls,before+1);assert.equal(els.confirmRender.disabled,true);
  complete({directory:'/new'});await first;pending=null;
  assert.equal(els.confirmRender.disabled,false);
  ctx.IS_DESKTOP_HOST=true;
  let desktopCalls=0;ctx.window.pywebview={api:{get_selected_render_directory:async()=>'/desktop',
    choose_render_directory:async()=>{desktopCalls++;return '/desktop chosen';}}};
  await ctx.openRenderDialog();await ctx.chooseRenderDirectory();
  assert.equal(desktopCalls,1);assert.equal(els.renderDirectoryInput.hidden,true);assert.equal(manual.hidden,true);
  await ctx.startRender();assert.equal(renders.at(-1).outputDirectory,'/desktop chosen');
  console.log('Browser + desktop folder UI: selection, cancel, manual fallback, no-folder guard, concurrency and desktop bridge passed');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
