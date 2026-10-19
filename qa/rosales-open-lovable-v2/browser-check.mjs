import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
const root = 'http://127.0.0.1:4175/';
const expected = new Set([
 'Rosales Café','Conceito','Experiência','Nossa proposta',
 'Brasil na origem. Colômbia na inspiração.','Café para quem aprecia o momento.',
 'Conheça o conceito','Voltar ao início','O ritual faz parte da história.',
 'Uma identidade entre duas culturas do café.',
 'Esta é uma apresentação conceitual da marca, sem ofertas comerciais ou afirmações sobre produtos ainda não confirmadas.',
 'Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração colombiana. Um convite a descobrir o café com atenção aos detalhes.',
 '© Rosales Café',
]);
const browser = await chromium.launch({headless:true});
const evidence=process.env.EVIDENCE_DIR||'./evidence';
await mkdir(evidence,{recursive:true});
try{
  for(const [name,width,height] of [['iphone',390,844],['desktop',1440,900]]){
    const context=await browser.newContext({viewport:{width,height},locale:'pt-BR',reducedMotion:'reduce'});
    const page=await context.newPage();
    const network=[],runtime=[];
    page.on('request',req=>{if(!req.url().startsWith(root)&&!req.url().startsWith('data:')&&!req.url().startsWith('about:'))network.push(req.url())});
    page.on('pageerror',e=>runtime.push(e.message));
    const resp=await page.goto(root,{waitUntil:'networkidle',timeout:22000});
    if(resp?.status()!==200)throw Error('page http '+resp?.status());
    await page.getByRole('heading',{level:1,name:'Rosales Café'}).waitFor();
    const assessment=await page.evaluate(()=>{
      const norm=s=>s.replace(/\s+/g,' ').trim();
      const visible=Array.from(document.querySelectorAll('h1,h2,p,a')).map(el=>norm(el.textContent||'')).filter(Boolean);
      const anchors=Array.from(document.querySelectorAll('a[href]')).map(x=>x.getAttribute('href'));
      const broken=anchors.filter(h=>!h.startsWith('#')||!document.getElementById(h.slice(1)));
      const style=getComputedStyle(document.querySelector('#root > div'));
      return {visible,broken,overflow:document.documentElement.scrollWidth>innerWidth+1,
        bg:style.backgroundColor,main:document.querySelectorAll('main').length,
        h1:document.querySelectorAll('h1').length,tailwindApplied:style.backgroundColor==='rgb(255, 251, 235)'};
    });
    const unexpected=assessment.visible.filter(v=>!expected.has(v));
    if(assessment.broken.length||unexpected.length||network.length||runtime.length||
       assessment.overflow||!assessment.tailwindApplied||assessment.h1!==1||assessment.main!==1)
      throw Error(JSON.stringify({name,unexpected,broken:assessment.broken,network,runtime,overflow:assessment.overflow,tailwindApplied:assessment.tailwindApplied,h1:assessment.h1,main:assessment.main}));
    await page.getByRole('navigation').getByRole('link',{name:'Conceito'}).click();
    const hash=await page.evaluate(()=>location.hash);
    if(hash!=='#conceito')throw Error('navigation failed '+hash);
    await page.screenshot({path:join(evidence,'rosales-open-lovable-'+name+'.png'),fullPage:true});
    console.log('ROSALES_OPEN_LOVABLE_BROWSER_PASS '+JSON.stringify({name,width,height,copyNodes:assessment.visible.length,links:assessment.broken.length,css:true,external:0,overflow:false}));
    await context.close();
  }
}finally{await browser.close()}
