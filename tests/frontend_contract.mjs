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
const events=[{seq:1,event:'mission_compiled',at:1,payload:{original_sha256:'initial-contract'}},
 {seq:2,event:'model_failover',at:1,payload:{from_provider:'qa-a',to_provider:'qa-b'}},
 ...Array.from({length:100},(_,i)=>({seq:i+3,event:'skill_applied',at:i+2,payload:{mode:'advisory_context',success:true}})),
 {seq:103,event:'result_published',at:103,payload:{files_modified:['app/index.html'],delivery_review:{scope:'static_checks_only',browser:'pending',visual:'pending'},verification:{success:true},api_key:'SYNTHETIC_SECRET_ONLY'}}];
let createFails=true;
let projectItems=[project],catalogFailure=false,credentialFailure=false,organizationRole='owner';
const fixtureProvider=(id,name,healthy=true)=>({id,name,description:'Conexão de teste controlada',kind:'api',tier:'free',cost:'Gratuito',enabled:true,configured:true,status:healthy?'healthy':'unreachable',healthy,model_count:3,automatic_active:healthy,priority:10,capacity_counts:{ready:healthy?2:0,cooldown:0},credential_fields:[{id:'api_key',label:'Chave da API',secret:true,required:true,configured:true},{id:'base_url',label:'Endereço da API',secret:false,required:false,configured:true}]});
let providerItems=[fixtureProvider('fcc','Free Claude Code')];
const credentialRequests=[];
const catalog=()=>({providers:providerItems,plugins:[],routing_policy:{mode:'free_first',free_attempt_limit:4,paid_fallback_authorized:false,paid_spend_cap_usd:0},fallback_routes:[]});
await context.route('**/*',async route=>{
 const url=new URL(route.request().url());
 if(url.port===new URL(base).port)return route.continue();
 if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort();
 const path=url.pathname,method=route.request().method();requests.push({path,method});
 let data={};let status=200;
 if(path==='/auth/login')data={access_token:'synthetic-browser-token',token_type:'bearer'};
 else if(path==='/cloud/projects'&&method==='POST'){status=createFails?503:200;data=createFails?{detail:'Não foi possível criar o projeto.'}:{...project,project_id:'qa-created',name:'Novo café'};}
 else if(path==='/cloud/projects')data={projects:projectItems};
 else if(path==='/cloud/executions')data={executions:[execution]};
 else if(path.endsWith('/events'))data={events};
 else if(path==='/preview/qa')return route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:'<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Rosales Café — preview</h1></body></html>'});
 else if(path.endsWith('/preview-session'))data={preview_url:'http://127.0.0.1:8000/preview/qa',entrypoint:'app/index.html',kind:'static',status:'ready',expires_at:9999999999};
 else if(path.endsWith('/versions'))data={versions:[]};
 else if(path.endsWith('/files'))data={files:[{path:'app/index.html',size:128,editable:true}]};
 else if(path.endsWith('/runtime/logs'))data={logs:[]};
 else if(path==='/cloud/saas/organization')data={organization_id:'qa-org',role:organizationRole,name:'Organização de teste'};
 else if(path==='/cloud/saas/organizations')data={organizations:[{organization_id:'qa-org',role:organizationRole,name:'Organização de teste'}]};
 else if(path==='/cloud/saas/members')data={members:[{user_id:'qa-owner',role:'owner',email:'pessoa.com.email.extenso@organizacao.example'},{user_id:'qa-builder',role:'builder',email:'outro.email.extenso@organizacao.example'}]};
 else if(path==='/cloud/saas/usage')data={plan_id:'founder',subscription_status:'active',usage:{missions_month:2,deployments_month:0},limits:{missions_month:100,deployments_month:100,members:10}};
 else if(path==='/cloud/saas/audit')data={events:[],chain_valid:true};
 else if(path==='/skills')data={skills:[],categories:[],external_repositories:[]};
 else if(path==='/providers/catalog'){status=catalogFailure?503:200;data=catalogFailure?{detail:'Conexões temporariamente indisponíveis'}:catalog();}
 else if(path.endsWith('/credentials')){credentialRequests.push(route.request().postDataJSON());status=credentialFailure?503:200;data=credentialFailure?{detail:'Não foi possível salvar as credenciais'}:catalog();}
 else if(path==='/providers/fcc/test')data={success:true,inference_ready:true,message:'Protocolo Olympus confirmado',provider:'fcc'};
 else if(path.startsWith('/providers/fcc'))data={success:true};
 else if(path.endsWith('/download'))return route.fulfill({status:200,contentType:'application/zip',body:'synthetic zip fixture'});
 return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
});
async function check(name,fn){try{await fn();checks[name]=true;}catch(e){checks[name]=String(e.stack||e);if(name==='preview'){checks[name]+='\nFRAMES='+JSON.stringify(await Promise.all(page.frames().map(async f=>({url:f.url(),body:await f.locator('body').innerText({timeout:500}).catch(()=>null)}))));if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/preview-failure.png',fullPage:true});}}finally{catalogFailure=false;credentialFailure=false;organizationRole='owner';providerItems=[fixtureProvider('fcc','Free Claude Code')];projectItems=[project];}}
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
 assert.ok(text.includes('initial-contract'));
 const download=page.waitForEvent('download');await toolbar.getByRole('button',{name:'Baixar diagnóstico',exact:true}).click();await download;
 await expect(toolbar.getByRole('button',{name:'Compartilhar detalhes',exact:true})).toBeVisible();
 const history=await page.goto(base+'/execucoes');assert.equal(history.status(),200);
 await page.getByRole('link',{name:/Construir Rosales Café/}).click();
 await page.waitForURL('**/missao?project_id=qa-cafe');
 await expect(page.getByRole('toolbar',{name:'Diagnóstico técnico'})).toBeVisible();
});
await check('mission_flow',async()=>{
 await page.goto(base+'/missao?project_id=qa-cafe');await expect(page.getByRole('button',{name:'Anexar arquivos'})).toBeVisible();
 for(const name of ['Visualizar','Arquivos','Versões','Publicar'])await expect(page.getByRole('button',{name,exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Arquivos',exact:true}).first().click();await expect(page.getByRole('dialog',{name:'Ambiente do projeto'})).toBeVisible();
 await expect(page.getByText('OmniRoute automático',{exact:true})).toHaveCount(0);
 await expect(page.getByText('app/index.html',{exact:true}).first()).toBeVisible();await page.getByRole('button',{name:'Fechar ambiente do projeto'}).click();
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/mission-desktop.png',fullPage:true});
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Baixar resultado',exact:true}).click();await download;
});
await check('preview',async()=>{
await page.goto(base+'/missao?project_id=qa-cafe');await page.getByRole('button',{name:'Visualizar',exact:true}).first().click();
await expect(page.frameLocator('iframe').getByRole('heading',{name:'Rosales Café — preview'})).toBeVisible();
await page.getByRole('button',{name:'Fechar ambiente do projeto'}).click();
});
await check('connections',async()=>{
 await page.goto(base+'/conexoes');await expect(page.getByRole('heading',{name:'APIs e provedores',exact:true})).toBeVisible();
 await page.getByText('Free Claude Code',{exact:true}).click();await page.getByRole('button',{name:'Testar',exact:true}).click();
 await expect(page.getByText('Protocolo Olympus confirmado',{exact:false})).toBeVisible();assert.ok(requests.some(r=>r.path==='/providers/fcc/test'&&r.method==='POST'));
});
await check('independent_scroll',async()=>{
 await page.setViewportSize({width:1440,height:800});
 projectItems=Array.from({length:55},(_,i)=>({...project,project_id:'project-'+i,name:'Projeto '+i}));
 providerItems=Array.from({length:30},(_,i)=>fixtureProvider('provider-'+i,'Provedor '+i,i%2===0));
 await page.goto(base+'/conexoes');await expect(page.getByRole('heading',{name:'Provedor 29',exact:true})).toBeAttached();
 const nav=page.locator('.app-sidebar .sidebar-navigation'),content=page.locator('#app-content');
 await page.getByRole('button',{name:/^Projetos/}).click();
 const brand=page.locator('.app-sidebar .olympus-brand');const before=await brand.boundingBox();
 await content.hover({position:{x:500,y:400}});await page.mouse.wheel(0,600);await expect.poll(()=>content.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
 const contentTop=await content.evaluate(el=>el.scrollTop);assert.equal(await nav.evaluate(el=>el.scrollTop),0);assert.equal((await brand.boundingBox()).y,before.y);
 await nav.hover({position:{x:90,y:200}});await page.mouse.wheel(0,500);await expect.poll(()=>nav.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);assert.equal(await content.evaluate(el=>el.scrollTop),contentTop);
 assert.equal(await page.evaluate(()=>scrollY),0);
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/independent-scroll.png'});
 projectItems=[project];providerItems=[fixtureProvider('fcc','Free Claude Code')];
});
await check('provider_filters_refresh',async()=>{
 providerItems=[fixtureProvider('fcc','Free Claude Code'),fixtureProvider('offline','Provedor indisponível',false)];
 await page.goto(base+'/conexoes');await expect(page.getByRole('heading',{name:'Provedor indisponível',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Disponíveis',exact:true}).click();await expect(page.getByRole('heading',{name:'Provedor indisponível',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Precisam de atenção',exact:true}).click();await expect(page.getByRole('heading',{name:'Free Claude Code',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Todos',exact:true}).click();await page.getByRole('searchbox',{name:'Buscar provedor'}).fill('nenhum-resultado');await expect(page.getByRole('heading',{name:'Nenhum provedor encontrado'})).toBeVisible();
 await page.getByRole('button',{name:'Limpar filtros'}).click();
 catalogFailure=true;await page.getByRole('button',{name:'Atualizar conexões'}).click();await expect(page.locator('main').getByRole('alert')).toContainText('Conexões temporariamente indisponíveis');await expect(page.getByRole('heading',{name:'Free Claude Code',exact:true})).toBeVisible();
 catalogFailure=false;await page.getByRole('button',{name:'Atualizar conexões'}).click();await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
 await expect(page.getByText('Fallback automático',{exact:true})).toHaveCount(0);
 const version=JSON.parse(fs.readFileSync(new URL('../frontend/public/olympus-version.json',import.meta.url)));await expect(page.locator('main').getByText('OLYMPUS '+version.version,{exact:true})).toBeVisible();
 for(const theme of ['light','dark']){
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  assert.ok(await page.locator('.provider-card h3').first().evaluate(el=>{
   const lum=s=>{const c=document.createElement('canvas');c.width=c.height=1;const ctx=c.getContext('2d');ctx.fillStyle=s;ctx.fillRect(0,0,1,1);const rgb=Array.from(ctx.getImageData(0,0,1,1).data).slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];};const a=lum(getComputedStyle(el).color),b=lum(getComputedStyle(el.closest('article')).backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;
  }),`Provider title contrast in ${theme}`);
  if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+`/providers-desktop-${theme}.png`,animations:'disabled'});
 }
 providerItems=[fixtureProvider('fcc','Free Claude Code')];
});
await check('provider_credentials_permissions',async()=>{
 await page.goto(base+'/conexoes');await page.getByRole('heading',{name:'Free Claude Code',exact:true}).click();
 const key=page.getByLabel('Chave da API',{exact:false});await expect(key).toHaveAttribute('type','password');await key.fill('SYNTHETIC_NEW_KEY');credentialFailure=true;
 await page.getByRole('button',{name:'Salvar credenciais'}).click();await expect(page.locator('main').getByRole('alert')).toContainText('Não foi possível salvar');await expect(key).toHaveValue('SYNTHETIC_NEW_KEY');
 credentialFailure=false;await page.getByRole('button',{name:'Salvar credenciais'}).click();await expect(key).toHaveValue('');await expect(page.getByRole('status').filter({hasText:'Credenciais salvas.'})).toBeVisible();
 assert.ok(credentialRequests.length>=2);for(const request of credentialRequests)assert.deepEqual(Object.keys(request.values).sort(),['api_key']);
 organizationRole='viewer';await page.goto(base+'/conexoes');await page.getByRole('heading',{name:'Free Claude Code',exact:true}).click();await expect(page.getByLabel('Chave da API',{exact:false})).toBeDisabled();await expect(page.getByRole('button',{name:'Salvar credenciais'})).toBeDisabled();organizationRole='owner';
});
await check('mobile_navigation_scroll',async()=>{
 await page.setViewportSize({width:390,height:844});await page.goto(base+'/conexoes');await expect(page.getByRole('heading',{name:'APIs e provedores'})).toBeVisible();
 const opener=page.getByRole('button',{name:'Abrir navegação'});await opener.click();await expect(page.getByRole('dialog',{name:'Navegação OLYMPUS'})).toBeVisible();await page.keyboard.press('Escape');await expect(opener).toBeFocused();await expect(page.getByRole('dialog')).toHaveCount(0);
 const before=await page.locator('.app-mobile-nav').boundingBox();await page.locator('#app-content').evaluate(el=>el.scrollTop=450);assert.equal((await page.locator('.app-mobile-nav').boundingBox()).y,before.y);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/providers-mobile.png'});
 await page.setViewportSize({width:1440,height:1000});
});
await check('contrast',async()=>{
 await page.goto(base+'/missao');for(const theme of ['light','dark']){
 await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 const link=page.getByRole('link',{name:'Nova missão',exact:true}).first();await expect(link).toBeVisible();
 assert.ok(await link.evaluate(el=>{const luminance=s=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d');ctx.fillStyle=s;ctx.fillRect(0,0,1,1);const rgb=Array.from(ctx.getImageData(0,0,1,1).data).slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];};let parent=el,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement;}const a=luminance(getComputedStyle(el).color),b=luminance(bg);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;}));
 }
});
await check('version',async()=>{
 const version=JSON.parse(fs.readFileSync(new URL('../frontend/public/olympus-version.json',import.meta.url)));
 await page.setViewportSize({width:1440,height:1000});await expect(page.getByText('OLYMPUS '+version.version,{exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await expect(page.getByText(version.version,{exact:true})).toBeVisible();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 if(process.env.OLYMPUS_QA_BROWSER_EVIDENCE)await page.screenshot({path:process.env.OLYMPUS_QA_BROWSER_EVIDENCE+'/mission-mobile.png',fullPage:true});
});
await check('failure_diagnostic',async()=>{
await page.setViewportSize({width:1440,height:1000});execution.status='failed';execution.error='synthetic failure';
events.push({seq:3,event:'failed',at:3,failure_stage:'execution',error_type:'ValueError',traceback:[{file:'qa_runner.py',line:12,function:'run'}]});
await page.goto(base+'/missao?project_id=qa-cafe');await page.getByText('Ver diagnóstico técnico',{exact:true}).click();
await expect(page.locator('.mission-diagnostic')).toContainText('qa_runner.py');
await expect(page.locator('.mission-diagnostic')).toContainText('failure_stage');
});
await check('accessible_layout',async()=>{
 for(const width of [390,768,1440]){
  await page.setViewportSize({width,height:1000});
  for(const path of ['/missao','/projetos','/execucoes','/skills','/configuracoes']){
   await page.goto(base+path);await page.locator('#app-content main').first().waitFor({state:'visible'});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),path+' overflows at '+width);
   const missing=await page.locator('input,textarea,select').evaluateAll(els=>els.filter(el=>getComputedStyle(el).display!=='none'&&el.type!=='hidden'&&!el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby')&&!el.labels?.length).map(el=>el.outerHTML));
   assert.deepEqual(missing,[],path+' unnamed controls at '+width);
  }
 }
});
console.log(JSON.stringify({browser:browser.version(),checks,page_errors:errors,console_errors:consoleErrors,requests}));
} finally {await browser.close();}
