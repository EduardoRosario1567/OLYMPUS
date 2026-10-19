import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
import {join} from 'node:path';
const base='http://127.0.0.1:4176/';
const allowed=new Set([
 'Rosales Café','Conceito','Experiência','Nossa proposta','Brasil na origem. Colômbia na inspiração.',
 'Café para quem aprecia o momento.','Conheça o conceito','O ritual faz parte da história.',
 'Uma identidade entre duas culturas do café.',
 'Esta é uma apresentação conceitual da marca, sem ofertas comerciais ou afirmações sobre produtos ainda não confirmadas.',
 'Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração colombiana. Um convite a descobrir o café com atenção aos detalhes.',
 'Voltar ao início','© Rosales Café'
]);
const browser=await chromium.launch({headless:true});const evidence=process.env.EVIDENCE_DIR||'./evidence';
await mkdir(evidence,{recursive:true});
try{
 for(const [name,width,height] of [['iphone',390,844],['desktop',1440,900]]){
  const ctx=await browser.newContext({viewport:{width,height},locale:'pt-BR',reducedMotion:'reduce'});
  const page=await ctx.newPage(),external=[],errors=[];
  page.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('data:')&&!r.url().startsWith('about:'))external.push(r.url())});
  page.on('pageerror',e=>errors.push(e.message));
  const resp=await page.goto(base,{waitUntil:'networkidle'});
  if(resp?.status()!==200)throw Error('HTTP '+resp?.status());
  await page.getByRole('heading',{name:'Rosales Café',level:1}).waitFor();
  const audit=await page.evaluate(()=>{
   const norm=s=>s.replace(/\s+/g,' ').trim();
   const text=Array.from(document.querySelectorAll('h1,h2,h3,p,a,span')).filter(el=>!el.querySelector('h1,h2,h3,p,a,span')).map(el=>norm(el.textContent||'')).filter(Boolean);
   const anchors=Array.from(document.querySelectorAll('a[href]')).map(a=>a.getAttribute('href'));
   const broken=anchors.filter(h=>!h.startsWith('#')||!document.getElementById(h.slice(1)));
   const cta=document.querySelector('.cta-button');
   const rect=cta?.getBoundingClientRect();
   return {text,broken,overflow:document.documentElement.scrollWidth>innerWidth+1,
     bodyBg:getComputedStyle(document.body).backgroundColor, h1:document.querySelectorAll('h1').length,
     main:document.querySelectorAll('main').length,
     ctaHeight:rect?.height||0,ctaTag:cta?.tagName||'',mobileHeaderHeight:document.querySelector('header')?.getBoundingClientRect().height||0};
  });
  const unknown=audit.text.filter(t=>!allowed.has(t));
  if(unknown.length||audit.broken.length||errors.length||external.length||audit.overflow||
    audit.bodyBg!=='rgb(253, 248, 242)'||audit.h1!==1||audit.main!==0||
    audit.ctaTag!=='A'||audit.ctaHeight<44)
   throw Error('BASIC_QA '+JSON.stringify({name,unknown,broken:audit.broken,errors,external,overflow:audit.overflow,bg:audit.bodyBg,h1:audit.h1,main:audit.main,cta:audit.ctaTag,ctaHeight:audit.ctaHeight}));
  await page.screenshot({path:join(evidence,'rosales-v3-'+name+'.png'),fullPage:true});
  await page.getByRole('navigation').getByRole('link',{name:'Conceito'}).click();
  const anchor=await page.evaluate(()=>{
   const sec=document.getElementById('conceito')?.getBoundingClientRect();
   const header=document.querySelector('header')?.getBoundingClientRect();
   return {hash:location.hash,sectionTop:sec?.top,headerBottom:header?.bottom,headerHeight:header?.height};
  });
  if(anchor.hash!=='#conceito'||anchor.sectionTop < anchor.headerBottom-3)
   throw Error('STICKY_NAV_OCCLUSION '+JSON.stringify({name,anchor}));
  console.log('ROSALES_LOVABLE_V3_QA_PASS '+JSON.stringify({name,width,files:'React+CSS',links:audit.broken.length,approvedText:true,external:0,errors:0,ctaWorking:true,sectionVisible:true}));
  await ctx.close();
 }
}finally{await browser.close()}
