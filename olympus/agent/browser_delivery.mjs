import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const config=JSON.parse(fs.readFileSync(0,'utf8'));
const {chromium}=await import(pathToFileURL(path.join(config.modules,'playwright/index.mjs')));
const root=fs.realpathSync(config.root),origin='http://olympus-delivery.invalid';
const types={'.html':'text/html; charset=utf-8','.htm':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.ico':'image/x-icon','.webp':'image/webp','.svg':'image/svg+xml','.woff':'font/woff','.woff2':'font/woff2','.ttf':'font/ttf','.mp4':'video/mp4','.webm':'video/webm'};
const errors=new Set(),viewports=[],interactions=[];
const browser=await chromium.launch({headless:true,chromiumSandbox:config.chromium_sandbox,
  ...(config.executable?{executablePath:config.executable}:{}),args:config.args});
try{
 const context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false});
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin||request.method()!=='GET'){
   errors.add('external request refused; use local credited assets and client-side behavior');return route.abort();
  }
  try{
   const relative=decodeURIComponent(url.pathname).replace(/^\/+/,''),parts=relative.split('/');
   if(parts.some(x=>x.startsWith('.')||['node_modules','venv','__pycache__','attachments','imports'].includes(x)))throw Error();
   const resolved=path.resolve(root,relative);
   if(!resolved.startsWith(root+path.sep))throw Error();
   let current=root;for(const part of parts){current=path.join(current,part);if(fs.lstatSync(current).isSymbolicLink())throw Error();}
   if(!types[path.extname(resolved)]||fs.statSync(resolved).size>8*1024*1024)throw Error();
   return route.fulfill({status:200,contentType:types[path.extname(resolved)],body:fs.readFileSync(resolved),headers:{
    'Content-Security-Policy':"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'self'",
    'X-Content-Type-Options':'nosniff'}});
  }catch{errors.add('missing or refused local resource: '+url.pathname.slice(0,180));return route.fulfill({status:404,body:''});}
 });
 const page=await context.newPage();page.setDefaultTimeout(5000);
 page.on('pageerror',error=>errors.add('JavaScript: '+error.message));
 page.on('console',message=>{if(message.type()==='error')errors.add('browser console: '+message.text().slice(0,300));});
 page.on('dialog',async dialog=>{interactions.push({dialog:dialog.type(),message:dialog.message().slice(0,180)});await dialog.dismiss();});
 const observableState=()=>JSON.stringify({
  text:document.body.innerText,
  state:[...document.querySelectorAll('details,input,select,textarea,[aria-expanded],[aria-pressed]')].map(el=>[
   el.tagName,el.open,el.checked,el.value,el.getAttribute('aria-expanded'),el.getAttribute('aria-pressed')]),
  background:getComputedStyle(document.body).backgroundColor
 });
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:900});
  await page.goto(origin+'/'+config.entrypoint,{waitUntil:'networkidle',timeout:10000});
  await page.evaluate(()=>document.fonts.ready);
  const checks=await page.evaluate(()=>{
   const visible=el=>!!el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden';
   const controls=[...document.querySelectorAll('input:not([type=hidden]),select,textarea,button')].filter(visible);
   const unnamed=controls.filter(el=>!el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby')&&!el.labels?.length&&!(el.tagName==='BUTTON'&&el.textContent.trim())).map(el=>el.tagName);
   const broken=[...document.images].filter(el=>visible(el)&&(!el.complete||!el.naturalWidth)).map(el=>el.getAttribute('src'));
   const anchors=[...document.querySelectorAll('a[href^="#"]')].filter(visible).filter(el=>el.hash.length<2||!document.getElementById(decodeURIComponent(el.hash.slice(1)))).map(el=>el.getAttribute('href'));
   return {overflow:document.documentElement.scrollWidth>innerWidth+1,unnamed,broken,anchors,
           visible_words:document.body.innerText.trim().split(/\s+/).length};
  });
  if(checks.overflow)errors.add('horizontal page overflow at '+width+'px');
  if(checks.unnamed.length)errors.add('unnamed controls at '+width+'px');
  if(checks.broken.length)errors.add('broken images at '+width+'px: '+checks.broken.join(', ').slice(0,180));
  if(checks.anchors.length)errors.add('fragment navigation has no destination at '+width+'px');
  if(checks.visible_words<4)errors.add('rendered page is empty or incomplete at '+width+'px');
  await page.screenshot({path:path.join(config.evidence,'viewport-'+width+'.png'),fullPage:true,timeout:10000});
  viewports.push({width,height:900,checks});
  if(width===1440){
   const buttons=page.locator('button:visible:not([disabled])');const count=Math.min(await buttons.count(),8);
   for(let index=0;index<count;index++){
    await page.goto(origin+'/'+config.entrypoint,{waitUntil:'networkidle'});
    const button=page.locator('button:visible:not([disabled])').nth(index);
    const formHandle=await button.evaluateHandle(el=>el.form),form=formHandle.asElement();
    if(form){
     for(const field of await form.$$('input[required],select[required],textarea[required]')){
      if(!await field.isVisible()||!await field.isEnabled()||await field.getAttribute('readonly')!==null)continue;
      const type=(await field.getAttribute('type')||'text').toLowerCase();
      if(['checkbox','radio'].includes(type)){await field.check();continue;}
      const tag=await field.evaluate(el=>el.tagName);
      if(tag==='SELECT'){
       const value=await field.evaluate(el=>[...el.options].find(option=>option.value&&!option.disabled)?.value);
       if(value)await field.selectOption(value);
      }else if(!['file','hidden','submit','button'].includes(type)){
       const value=type==='email'?'qa@example.invalid':type==='url'?'https://example.invalid':type==='number'?(await field.getAttribute('min')||'1'):type==='tel'?'0000000000':type==='date'?'2026-01-01':'Olympus QA';
       await field.fill(value);
      }
     }
    }
    const label=(await button.innerText()).trim().slice(0,120),before=await page.evaluate(observableState),dialogs=interactions.length;
    await button.click();
    // Poll through DevTools evaluation: Playwright's waitForFunction uses eval,
    // which the preview CSP correctly refuses. Never loosen that CSP for QA.
    const deadline=Date.now()+1500;
    while(Date.now()<deadline&&interactions.length===dialogs&&page.url()===origin+'/'+config.entrypoint){
     if(await page.evaluate(observableState)!==before)break;
     await new Promise(resolve=>setTimeout(resolve,50));
    }
    const after=await page.evaluate(observableState);
    const changed=before!==after||interactions.length!==dialogs||page.url()!==origin+'/'+config.entrypoint;
    interactions.push({label,observable_change:changed,synthetic_form_inputs:!!form});
    await formHandle.dispose();
    if(!changed)errors.add('button has no observable behavior: '+label);
   }
  }
 }
 console.log(JSON.stringify({browser_version:browser.version(),errors:[...errors],viewports,interactions}));
}finally{await browser.close();}
