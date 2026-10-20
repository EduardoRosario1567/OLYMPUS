'use strict';
// Private, single-job verifier. Generated packages are never installed here.
const http = require('node:http');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const LIMIT = 6 * 1024 * 1024;
const VIEWPORTS = [{width:1440,height:900},{width:390,height:844}];
function unpack(input) {
  if (!input || !/^[a-f0-9]{64}$/.test(input.source_manifest_sha256 || '') || !/^[a-f0-9]{32}$/.test(input.nonce || '')) throw Error('invalid_identity');
  if (!Array.isArray(input.files) || !input.files.length || input.files.length > 80) throw Error('invalid_files');
  const files = new Map(); let total=0;
  for (const f of input.files) {
    if (!/^[A-Za-z0-9_./-]+$/.test(f.path) || f.path.split('/').some(x=>!x || x.startsWith('.')) || !/\.(html|js|css|svg|png|jpe?g|webp|gif|ico|woff2?)$/.test(f.path) || files.has(f.path)) throw Error('invalid_path');
    if (typeof f.content_base64 !== 'string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(f.content_base64)) throw Error('invalid_encoding');
    const bytes=Buffer.from(f.content_base64,'base64'); total+=bytes.length;
    if (bytes.length>512*1024 || total>4*1024*1024 || sha(bytes)!==f.sha256) throw Error('invalid_checksum_or_size');
    files.set(f.path,bytes);
  }
  if (!files.has('index.html')) throw Error('missing_index');
  const digest=crypto.createHash('sha256');
  for (const name of [...files.keys()].sort()) digest.update(name+'\0').update(Buffer.from(sha(files.get(name)),'hex'));
  if (digest.digest('hex')!==input.artifact_sha256) throw Error('invalid_manifest');
  return files;
}
const types={html:'text/html; charset=utf-8',js:'text/javascript',css:'text/css',svg:'image/svg+xml',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',gif:'image/gif',ico:'image/x-icon',woff:'font/woff',woff2:'font/woff2'};
async function inspect(page) {
  return page.evaluate(()=>{
    const errors=[], contrast=[];
    const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility==='visible'&&Number(s.opacity)>0;};
    if(document.querySelectorAll('h1').length!==1) errors.push('one_h1_required');
    if(document.querySelectorAll('main').length!==1) errors.push('one_main_required');
    if(!document.documentElement.lang || !document.title || !document.querySelector('meta[name="viewport"]')) errors.push('document_metadata');
    if(!document.querySelector('h1') || !visible(document.querySelector('h1'))) errors.push('invisible_h1');
    if(document.documentElement.scrollWidth>innerWidth+1) errors.push('horizontal_overflow');
    if(document.querySelector('form,button,input,textarea,select,iframe,video,audio,canvas,object,embed')) errors.push('unsupported_interactive_content');
    if([...document.images].some(x=>!x.complete||!x.naturalWidth)) errors.push('image_failed');
    const anchors=[...document.querySelectorAll('a')];
    for(const a of anchors){const h=a.getAttribute('href')||'';if(!/^#[A-Za-z][\w:-]*$/.test(h)||!document.getElementById(h.slice(1)))errors.push('unsupported_or_broken_link');}
    const rgb=x=>(x.match(/[\d.]+/g)||[]).map(Number);
    const lum=c=>c.slice(0,3).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
    for(const e of document.querySelectorAll('h1,h2,h3,p,a,li,small,span')){
      if(!visible(e)||!e.textContent.trim()||[...e.children].some(x=>x.textContent.trim())) continue;
      let bg=[255,255,255], unknown=false, layers=[];
      for(let p=e;p;p=p.parentElement){let s=getComputedStyle(p);if(s.backgroundImage!=='none'||Number(s.opacity)<1)unknown=true;layers.unshift(rgb(s.backgroundColor));}
      for(const c of layers){let a=c[3]??1;bg=bg.map((v,i)=>c[i]*a+v*(1-a));}
      const s=getComputedStyle(e),fg=rgb(s.color),alpha=fg[3]??1,col=bg.map((v,i)=>fg[i]*alpha+v*(1-alpha));
      let a=lum(col),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);
      if(unknown) errors.push('unsupported_text_background');
      else if(ratio<(large?3:4.5)){
        const black=(b+.05)/.05,white=1.05/(b+.05);
        contrast.push({id:e.getAttribute('data-olympus-qa'),color:black>=white?'#000000':'#ffffff',ratio});
      }
    }
    return {errors:[...new Set(errors)],contrast,anchors:anchors.map(a=>a.getAttribute('href'))};
  });
}
async function checkAnchors(page, anchors) {
  const errors=[];
  for(const hash of [...new Set(anchors)]){
    await page.locator(`a[href="${hash}"]`).last().click({timeout:3000});
    await page.waitForTimeout(350);
    const ok=await page.evaluate(h=>{
      const target=document.getElementById(h.slice(1));if(!target)return false;
      const e=target.matches('h1,h2,h3')?target:target.querySelector('h1,h2,h3')||target;
      const r=e.getBoundingClientRect();
      const bottom=Math.max(0,...[...document.querySelectorAll('header,nav')].filter(x=>['fixed','sticky'].includes(getComputedStyle(x).position)).map(x=>x.getBoundingClientRect().bottom));
      return r.top>=bottom-1&&r.top<innerHeight&&r.bottom>0;
    },hash);
    if(!ok)errors.push('anchor_obscured:'+hash);
  }
  return errors;
}
async function verify(input) {
  const files=unpack(input), repairs=[], checks=[]; let finalHtml='';
  const server=http.createServer((req,res)=>{
    const name=(req.url||'/').split('?')[0].slice(1)||'index.html';
    const body=name==='__verified.html'?Buffer.from(finalHtml):files.get(name);
    res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'");
    if(!body){res.writeHead(404);return res.end();}
    res.setHeader('Content-Type',types[name.split('.').pop()]||'application/octet-stream');res.end(body);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser=await chromium.launch({headless:true});
    const context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false});
    let denied=0;
    await context.route('**/*',route=>{const u=new URL(route.request().url());return u.origin===origin?route.continue():(denied++,route.abort());});
    const page=await context.newPage();page.setDefaultTimeout(8000);
    const runtimeErrors=[];page.on('pageerror',()=>runtimeErrors.push('javascript_error'));
    await page.goto(origin,{waitUntil:'networkidle',timeout:15000});
    // Reserve identifiers ourselves; generated attributes cannot select repairs.
    await page.evaluate(()=>{let i=0;for(const e of document.querySelectorAll('*'))e.setAttribute('data-olympus-qa',String(i++));});
    for(const viewport of VIEWPORTS){
      await page.setViewportSize(viewport);await page.waitForTimeout(100);
      const result=await inspect(page);checks.push({viewport,...result});
      if(result.errors.length) throw Error(result.errors.join(','));
      for(const fix of result.contrast){
        const rule=`[data-olympus-qa="${fix.id}"]{color:${fix.color}!important;-webkit-text-fill-color:${fix.color}!important}`;
        await page.addStyleTag({content:rule});repairs.push({kind:'contrast',rule});
      }
    }
    const top=await page.evaluate(()=>Math.ceil(Math.max(0,...[...document.querySelectorAll('header,nav')].filter(x=>['fixed','sticky'].includes(getComputedStyle(x).position)).map(x=>x.getBoundingClientRect().height)))+24);
    const scrollRule=`html{scroll-behavior:auto!important;scroll-padding-top:${top}px!important} [id]{scroll-margin-top:0!important}`;
    await page.addStyleTag({content:scrollRule});repairs.push({kind:'anchor_offset',rule:scrollRule});
    if(denied||runtimeErrors.length)throw Error('external_request_or_javascript_error');
    // Flatten only this supported static-page profile. Preserve the exact DOM,
    // embed compiled CSS and local images; scripts and event handlers are removed.
    const css=[...files].filter(([n])=>n.endsWith('.css')).map(([,b])=>b.toString('utf8')).join('\n');
    const data=Object.fromEntries([...files].map(([n,b])=>[n,`data:${types[n.split('.').pop()]||'application/octet-stream'};base64,${b.toString('base64')}`]));
    if(/url\s*\(|@import/i.test(css))throw Error('unsupported_css_asset_reference');
    finalHtml=await page.evaluate(({css,data,repairs})=>{
      const doc=document.documentElement.cloneNode(true);
      doc.querySelectorAll('script,link,base,meta[http-equiv]').forEach(x=>x.remove());
      doc.querySelectorAll('*').forEach(e=>{for(const a of [...e.attributes])if(/^on/i.test(a.name))e.removeAttribute(a.name);});
      for(const img of doc.querySelectorAll('img')){
        const path=new URL(img.getAttribute('src')||'',location.href).pathname.slice(1);
        if(!data[path])throw Error('unsupported_image');img.setAttribute('src',data[path]);img.removeAttribute('srcset');img.setAttribute('loading','eager');
      }
      const style=document.createElement('style');style.textContent=css+'\n'+repairs.map(x=>x.rule).join('\n');doc.querySelector('head').append(style);
      return '<!doctype html>\n'+doc.outerHTML;
    },{css,data,repairs});
    await context.close();
    const verified=[];
    for(const viewport of VIEWPORTS){
      const ctx=await browser.newContext({viewport,javaScriptEnabled:false,serviceWorkers:'block',acceptDownloads:false});
      let blocked=0;await ctx.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():(blocked++,r.abort()));
      const p=await ctx.newPage();await p.goto(origin+'/__verified.html',{waitUntil:'networkidle',timeout:15000});
      const result=await inspect(p);result.errors.push(...await checkAnchors(p,result.anchors));
      if(result.contrast.length)result.errors.push('contrast_failed');if(blocked)result.errors.push('external_request');
      verified.push({viewport,passed:result.errors.length===0,errors:result.errors});await ctx.close();
    }
    const passed=verified.every(x=>x.passed);
    return {schema:'olympus.browser.v1',passed,nonce:input.nonce,source_manifest_sha256:input.source_manifest_sha256,artifact_sha256:input.artifact_sha256,html:passed?finalHtml:null,html_sha256:passed?sha(Buffer.from(finalHtml)):null,viewports:verified,repairs,original_checks:checks};
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
function start(){
 let busy=false;
 const token=process.env.OLYMPUS_BROWSER_VERIFIER_TOKEN;
 if(!token||token.length<24)throw Error('verifier_token_required');
 return http.createServer(async(req,res)=>{
  res.setHeader('Content-Type','application/json');
  if(req.method==='GET'&&req.url==='/health')return res.end('{"ok":true}');
  const supplied=String(req.headers['x-olympus-browser-token']||'');
  if(req.method!=='POST'||req.url!=='/verify'||sha(supplied)!==sha(token)){res.writeHead(403);return res.end('{}');}
  if(busy){res.writeHead(429);return res.end('{"error":"busy"}');}
  busy=true;let bytes=0,chunks=[];
  req.setTimeout(10000,()=>req.destroy());
  try{
   for await(const chunk of req){bytes+=chunk.length;if(bytes>LIMIT)throw Error('request_too_large');chunks.push(chunk);}
   const result=await verify(JSON.parse(Buffer.concat(chunks)));res.end(JSON.stringify(result));
  }catch(e){res.writeHead(422);res.end(JSON.stringify({passed:false,error:String(e.message).slice(0,300)}));}
  finally{busy=false;}
 }).listen(Number(process.env.PORT||8080),'0.0.0.0');
}
module.exports={unpack,verify};if(require.main===module)start();
