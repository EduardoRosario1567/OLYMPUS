import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';

const URL='http://127.0.0.1:4173/';
const server=spawn('npm',['run','preview'],{cwd:process.cwd(),stdio:'pipe'});
let stderr='';
server.stderr.on('data',chunk=>{stderr+=String(chunk).slice(0,400)});
async function waitServer(){
 for(let i=0;i<80;i++){
  try{const r=await fetch(URL,{signal:AbortSignal.timeout(900)});if(r.ok)return}catch{}
  await new Promise(resolve=>setTimeout(resolve,450));
 }
 throw Error('Vite preview unavailable: '+stderr.slice(-300));
}
let browser;
try{
 await waitServer();
 browser=await chromium.launch({headless:true});
 mkdirSync('evidence',{recursive:true});
 for(const v of [{width:390,height:844,name:'iphone'},{width:1440,height:900,name:'desktop'}]){
  const context=await browser.newContext({viewport:{width:v.width,height:v.height},locale:'pt-BR',reducedMotion:'reduce'});
  const page=await context.newPage();
  const errors=[],offsite=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!r.url().startsWith(URL))offsite.push(r.url())});
  const response=await page.goto(URL,{waitUntil:'networkidle',timeout:25000});
  if(response?.status()!==200)throw Error('HTTP '+response?.status());
  await page.getByRole('heading',{name:'Rosales Café',level:1}).waitFor();
  const text=(await page.locator('body').innerText()).toLowerCase();
  for(const claim of ['sustentável','produtores','baristas','wi-fi','cardápio','fazenda','certificado']){
   if(text.includes(claim))throw Error('Unverified claim: '+claim);
  }
  const links=await page.locator('a[href^="#"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
  if(links.length<3)throw Error('Too few internal links');
  for(const href of links){if(!await page.locator('[id="'+href.slice(1)+'"]').count())throw Error('Broken anchor '+href)}
  await page.getByRole('link',{name:'Conheça o conceito'}).first().click();
  if(await page.evaluate(()=>location.hash)!=='#concept')throw Error('Anchor navigation failed');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  if(overflow)throw Error('Horizontal overflow at '+v.width);
  const color=await page.locator('#root > div').evaluate(el=>getComputedStyle(el).backgroundColor);
  if(color==='rgba(0, 0, 0, 0)')throw Error('CSS not applied');
  if(errors.length||offsite.length)throw Error('Browser failure '+JSON.stringify({errors,offsite}));
  await page.screenshot({path:'evidence/rosales-open-lovable-'+v.name+'.png',fullPage:true});
  console.log('ROSALES_OPEN_LOVABLE_BROWSER_OK '+JSON.stringify({viewport:v.width,links:links.length,overflow:false,externalRequests:0,pageErrors:0}));
  await context.close();
 }
}finally{if(browser)await browser.close();server.kill('SIGTERM')}
