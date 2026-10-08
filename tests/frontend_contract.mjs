import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [modules,base]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(modules+'/playwright/index.mjs'));
const {expect}=await import(pathToFileURL(modules+'/playwright/test.mjs'));
const browser=await chromium.launch({headless:true,...(process.env.OLYMPUS_QA_CHROMIUM ? {executablePath:process.env.OLYMPUS_QA_CHROMIUM,args:JSON.parse(process.env.OLYMPUS_QA_CHROMIUM_ARGS||'[]')} : {})});
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
const page=await context.newPage();
page.setDefaultTimeout(8000);
const errors=[],checks={},requests=[],consoleErrors=[];
page.on('console',msg=>{if(msg.type()==='error')consoleErrors.push(msg.text());});
page.on('pageerror',e=>errors.push(e.message));
const project={project_id:'qa-cafe',name:'Rosales Café',created_at:1,updated_at:2,tenant_id:'qa'};
const execution={execution_id:'qa-execution',project_id:'qa-cafe',task:'Construir Rosales Café',status:'completed',created_at:1,updated_at:2,error:null};
const events=[{seq:1,event:'model_failover',at:1,payload:{from_provider:'qa-a',to_provider:'qa-b'}},{seq:2,event:'result_published',at:2,payload:{files_modified:['app/index.html'],verification:{success:true},api_key:'SYNTHETIC_SECRET_ONLY'}}];
let createFails=true;
await context.route('**/*',async route=>{
 const url=new URL(route.request().url());
 if(url.port===new URL(base).port)return route.continue();
 if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort();
 const path=url.pathname,method=route.request().method();requests.push({path,method});
 let data={};let status=200;
 if(path==='/auth/login')data={access_token:'synthetic-browser-token',token_type:'bearer'};
 else if(path==='/cloud/projects'&&method==='POST'){status=createFails?503:200;data=createFails?{detail:'Não foi possível criar o projeto.'}:{...project,project_id:'qa-created',name:'Novo café'};}
 else if(path==='/cloud/projects')data={projects:[project]};
 else if(path==='/cloud/executions')data={executions:[execution]};
 else if(path.endsWith('/events'))data={events};
 else if(path==='/preview/qa')return route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:'<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Rosales Café — preview</h1></body></html>'});
 else if(path.endsWith('/preview-session'))data={preview_url:'http://127.0.0.1:8000/preview/qa',entrypoint:'app/index.html',kind:'static',status:'ready',expires_at:9999999999};
 else if(path.endsWith('/versions'))data={versions:[]};
 else if(path.endsWith('/files'))data={files:[{path:'app/index.html',size:128,editable:true}]};
 else if(path.endsWith('/runtime/logs'))data={logs:[]};
 else if(path==='/cloud/saas/organization')data={role:'owner',organization:{name:'QA'}};
 else if(path==='/providers/catalog')data={providers:[{id:'fcc',name:'Free Claude Code',kind:'local',enabled:true,automatic:true,configured:true,status:'healthy',healthy:true,models:[],safe_free_model_count:2,priority:10,inference_ready:true}],plugins:[],routing_policy:{mode:'free_first',free_attempt_limit:4,paid_fallback_authorized:false,paid_spend_cap_usd:0},fallback_routes:[]};
 else if(path==='/providers/fcc/test')data={success:true,inference_ready:true,message:'Protocolo Olympus confirmado',provider:'fcc'};
 else if(path.startsWith('/providers/fcc'))data={success:true};
 else if(path.endsWith('/download'))return route.fulfill({status:200,contentType:'application/zip',body:'synthetic zip fixture'});
 return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
});
async function check(name,fn){try{await fn();checks[name]=true;}catch(e){checks[name]=String(e.stack||e);if(name==='preview'){checks[name]+='\nFRAMES='+JSON.stringify(await Promise.all(page.frames().map(async f=>({url:f.url(),body:await f.locator('body').innerText({timeout:500}).catch(()=>null)}))));if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/preview-failure.png',fullPage:true,animations:'disabled'});}}}
try {
await check('hydration',async()=>{
 await page.goto(base+'/missao');await page.waitForURL('**/login');
 await page.getByLabel('Email',{exact:true}).fill('qa@olympus.test');await page.getByLabel('Senha',{exact:true}).fill('SyntheticOnly308');
 await page.getByRole('button',{name:'Entrar',exact:true}).click();await page.waitForURL('**/missao');
 await expect(page.getByRole('button',{name:'Enviar pedido'})).toBeVisible();assert.deepEqual(errors,[]);
});
await check('navigation',async()=>{
 for(const name of ['Nova missão','Histórico','Skills Fabric','Inteligência'])await expect(page.getByRole('link',{name,exact:true}).first()).toBeVisible();
 await expect(page.getByRole('button',{name:/^Projetos/})).toBeVisible();
 await expect(page.getByRole('link',{name:'Rosales Café',exact:true})).toHaveAttribute('href','/missao?project_id=qa-cafe');
});
await check('brand',async()=>{
 for(const path of ['/login','/missao']){await page.goto(base+path);const img=page.locator('img[src*="olympus-mark.png"]').first();await expect(img).toBeVisible();await expect(img).toHaveJSProperty('naturalWidth',1024);}
 const mark=page.locator('aside img[src*="olympus-mark.png"]');await expect(mark).toBeVisible();const box=await mark.boundingBox();assert.ok(box.width>=40&&box.height>=40);
});
await check('project_creation_failure',async()=>{
 await page.getByRole('button',{name:'+ Novo projeto',exact:true}).click();await page.getByPlaceholder('Nome do projeto').fill('Novo café');await page.getByRole('button',{name:'Criar',exact:true}).click();
 await expect(page.getByText('Não foi possível criar o projeto.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Criar',exact:true})).toBeEnabled();
 createFails=false;await page.getByRole('button',{name:'Criar',exact:true}).click();await page.waitForURL('**/missao?project_id=qa-created');
 assert.ok(requests.filter(r=>r.path==='/cloud/projects'&&r.method==='POST').length===2);
});
await page.goto(base+'/missao?project_id=qa-cafe');
await check('diagnostic',async()=>{
 const toolbar=page.getByRole('toolbar',{name:'Diagnóstico técnico'});await expect(toolbar).toBeVisible();
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.qaCopied=text;}}}));
 await toolbar.getByRole('button',{name:'Copiar diagnóstico',exact:true}).click();const text=await page.evaluate(()=>window.qaCopied);assert.ok(text.includes('qa-execution'));assert.ok(text.includes('model_failover'));assert.ok(!text.includes('SYNTHETIC_SECRET_ONLY'));
 const download=page.waitForEvent('download');await toolbar.getByRole('button',{name:'Baixar diagnóstico',exact:true}).click();await download;
 await expect(toolbar.getByRole('button',{name:'Compartilhar detalhes',exact:true})).toBeVisible();
 await page.goto(base+'/logs');await expect(page.getByRole('toolbar',{name:'Diagnóstico técnico'})).toBeVisible();
});
await check('mission_flow',async()=>{
 await page.goto(base+'/missao?project_id=qa-cafe');await expect(page.getByRole('button',{name:'Anexar arquivos'})).toBeVisible();
 for(const name of ['Visualizar','Arquivos','Versões','Publicar'])await expect(page.getByRole('button',{name,exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Arquivos',exact:true}).first().click();await expect(page.getByRole('dialog',{name:'Ambiente do projeto'})).toBeVisible();
 await expect(page.getByText('app/index.html',{exact:true}).first()).toBeVisible();await page.getByRole('button',{name:'Fechar ambiente do projeto'}).click();
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/mission-desktop.png',fullPage:true,animations:'disabled'});
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Baixar resultado',exact:true}).click();await download;
});
await check('preview',async()=>{
await page.goto(base+'/missao?project_id=qa-cafe');await page.getByRole('button',{name:'Visualizar',exact:true}).first().click();
await expect(page.frameLocator('iframe').getByRole('heading',{name:'Rosales Café — preview'})).toBeVisible();
await page.getByRole('button',{name:'Fechar ambiente do projeto'}).click();
});
await check('connections',async()=>{
 await page.goto(base+'/conexoes');await expect(page.getByRole('heading',{name:'Inteligência',exact:true})).toBeVisible();
 await page.getByText('Free Claude Code',{exact:true}).click();await page.getByRole('button',{name:'Testar',exact:true}).click();
 await expect(page.getByText('Protocolo Olympus confirmado',{exact:false})).toBeVisible();assert.ok(requests.some(r=>r.path==='/providers/fcc/test'&&r.method==='POST'));
});
await check('contrast',async()=>{
 await page.goto(base+'/missao');for(const theme of ['light','dark']){
 await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 const link=page.getByRole('link',{name:'Nova missão',exact:true}).first();await expect(link).toBeVisible();
 assert.ok(await link.evaluate(el=>{const luminance=s=>{const rgb=s.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];};let parent=el,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement;}const a=luminance(getComputedStyle(el).color),b=luminance(bg);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;}));
 }
});
await check('style_layout',async()=>{
 await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/missao');
 const sidebar=page.locator('aside').filter({has:page.getByRole('link',{name:'Nova missão',exact:true})}).first();
 await expect(sidebar).toBeVisible();
 assert.equal(await sidebar.evaluate(el=>getComputedStyle(el).width),'250px');
 assert.equal(await sidebar.evaluate(el=>getComputedStyle(el).paddingLeft),'12px');
 const logo=sidebar.locator('.olympus-logo');await expect(logo).toBeVisible();
 assert.equal(await logo.evaluate(el=>getComputedStyle(el).width),'44px');
 for(const theme of ['light','dark']){
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  await page.evaluate(()=>Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))));
  if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/mission-desktop-'+theme+'.png',fullPage:true,animations:'disabled'});
 }
 await page.setViewportSize({width:390,height:844});await expect(sidebar).toBeHidden();
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
});
await check('version',async()=>{
 const version=JSON.parse(fs.readFileSync(new URL('../frontend/public/olympus-version.json',import.meta.url)));
 await page.setViewportSize({width:1440,height:1000});await expect(page.getByText('OLYMPUS '+version.version,{exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await expect(page.getByText(version.version,{exact:true})).toBeVisible();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/mission-mobile.png',fullPage:true,animations:'disabled'});
});
await check('failure_diagnostic',async()=>{
await page.setViewportSize({width:1440,height:1000});execution.status='failed';execution.error='synthetic failure';
events.push({seq:3,event:'failed',at:3,failure_stage:'execution',error_type:'ValueError',traceback:[{file:'qa_runner.py',line:12,function:'run'}]});
await page.goto(base+'/missao?project_id=qa-cafe');await page.getByText('Ver diagnóstico técnico',{exact:true}).click();
await expect(page.locator('.mission-diagnostic')).toContainText('qa_runner.py');
await expect(page.locator('.mission-diagnostic')).toContainText('failure_stage');
});
console.log(JSON.stringify({browser:browser.version(),checks,page_errors:errors,console_errors:consoleErrors,requests}));
} finally {await browser.close();}
