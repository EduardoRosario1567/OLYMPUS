import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
const require=createRequire(import.meta.url);
const { chromium }=require('../frontend/node_modules/playwright');
const fixture=resolve('frontend/fixtures/rosales-open-lovable');
const app=readFileSync(fixture+'/src/App.jsx');
const css=readFileSync(fixture+'/src/index.css');
const hashes={
  'src/App.jsx':'852f0ad8bf4343565792b9fa9c8369ce6737485188d23520a40905890e6bda9d',
  'src/index.css':'8935a8170e098985dfa4e4faf741d307bdf00397706ca263e00e46b3007c09bd'
};
for(const [name,bytes] of Object.entries({'src/App.jsx':app,'src/index.css':css})){
  const hash=createHash('sha256').update(bytes).digest('hex');
  if(hash!==hashes[name])throw Error('Export artifact hash mismatch: '+name+' '+hash);
}
const jsx=app.toString('utf8'),styles=css.toString('utf8');
if(/https?:\/\/|<script|fetch\s*\(|dangerouslySetInnerHTML|<button\b|@import\b|url\s*\(|@font-face\b/i.test(jsx+'\n'+styles))throw Error('Unexpected active or external resource');
for(const x of ['produtores sustentáveis','wi-fi','baristas','cardápio','chocolate e frutas vermelhas'])if(jsx.toLowerCase().includes(x))throw Error('Unapproved commercial claim '+x);
if(/from ['"]\.\/components\//.test(jsx))throw Error('Old missing component import');
const cmd=resolve('frontend/node_modules/.bin/vite');
const child=spawn(cmd,['--host','127.0.0.1','--port','4183','--strictPort','fixtures/rosales-open-lovable'],{
 cwd:resolve('frontend'),stdio:['ignore','pipe','pipe']
});
let log='';for(const stream of [child.stdout,child.stderr])stream.on('data',d=>{log+=d.toString();});
let browser;
try{
 let ready=false;
 for(let i=0;i<100;i++){
   if(child.exitCode!==null)throw Error('Vite exited: '+log.slice(-800));
   try{const r=await fetch('http://127.0.0.1:4183/');if(r.ok){ready=true;break;}}catch{}
   await sleep(200);
 }
 if(!ready)throw Error('Vite timeout: '+log.slice(-600));
 browser=await chromium.launch({headless:true});
 for(const {width,height} of [{width:390,height:844},{width:768,height:1024},{width:1440,height:900}]){
   const context=await browser.newContext({viewport:{width,height},locale:'pt-BR'});
   const page=await context.newPage();
   const jsErrors=[],outside=[];
   page.on('pageerror',err=>jsErrors.push(err.message));
   page.on('request',req=>{if(!req.url().startsWith('http://127.0.0.1:4183/'))outside.push(req.url());});
   const r=await page.goto('http://127.0.0.1:4183/',{waitUntil:'networkidle'});
   if(r.status!==200)throw Error('HTTP failure '+r.status);
   await page.getByRole('heading',{level:1,name:'Rosales Café'}).waitFor();
   for(const section of ['conceito','experiencia','proposta']){
     const target=page.locator('#'+section);
     if(await target.count()!==1)throw Error('Missing or duplicated section '+section);
   }
   const links=await page.locator('a[href^="#"]').evaluateAll(els=>els.map(x=>x.getAttribute('href')));
   const bad=await page.evaluate(links=>links.filter(x=>!document.getElementById(x.slice(1))),links);
   if(bad.length)throw Error('Broken anchors '+bad.join(','));
   await page.getByRole('link',{name:'Conheça o conceito'}).click();
   if((await page.evaluate(()=>location.hash))!=='#conceito')throw Error('CTA navigation broken');
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
   if(overflow)throw Error('Horizontal overflow at width '+width);
   const stylesOk=await page.locator('body').evaluate(x=>getComputedStyle(x).backgroundColor!=='rgba(0, 0, 0, 0)');
   if(!stylesOk)throw Error('CSS was not applied');
   if(jsErrors.length||outside.length)throw Error('Errors or remote requests: '+JSON.stringify({jsErrors,outside}));
   await page.screenshot({path:'/tmp/rosales-open-lovable-'+width+'.png',fullPage:true});
   console.log('ROSALES_LOVABLE_CHROMIUM_OK '+JSON.stringify({width,height,links:links.length,jsErrors:0,externalRequests:0}));
   await context.close();
 }
}finally{if(browser)await browser.close();child.kill('SIGTERM');}
