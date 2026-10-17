/** OLYMPUS P6: real-model bounded autonomous repair via original Open Lovable SSE.
 * Never manually fixes generated HTML; guards remain P5 local-only.
 * Every original response, failure and derived SHA-256 is saved.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
const OUT='/tmp/olympus-p6-results';
const BASE='http://127.0.0.1:3000';
const BRAND='Rosales Café, o melhor café brasileiro ao estilo Colombiano.';
const P5_SHA='838d3d741335a9ac49363237956be0c05beec60b7909b8b2407b22609bf57faf';
const sha=v=>crypto.createHash('sha256').update(v).digest('hex');
const banned=['O Melhor Café da América do Sul','Cartão de Crédito','Transferência bancária','Tarjeta de Débito','Faça seu Prato','Encontre-nos em qualquer lugar do Brasil','profissionais qualificados','entrega grátis','preço'];
function save(record) {
 fs.mkdirSync(OUT,{recursive:true});
 fs.writeFileSync(path.join(OUT,'p6-proof.json'),JSON.stringify(record,null,2));
}
export function extract(raw) {
 const items=[...raw.matchAll(/<file\s+path="([^"><]{1,150})"\s*>([\s\S]*?)<\/file>/gi)];
 return items.filter(m=>m[1]==='site/index.html' && m[2].length>=300 && m[2].length<50000)
   .map(m=>m[2].trim());
}
export function check(html) {
 let fail=[];
 if(!html.toLowerCase().includes(BRAND.toLowerCase()))fail.push('BRAND_POSITIONING_MISSING: '+BRAND);
 if(!/<html[^>]*lang=["']pt-BR["']/i.test(html))fail.push('LANG_NOT_PT_BR');
 for(const tag of ['header','nav','main','footer','h1'])if(!new RegExp('<'+tag+'(?:\\s|>)','i').test(html))fail.push('SEMANTIC_'+tag);
 if((html.match(/<section[\s>]/gi)||[]).length<2)fail.push('TOO_FEW_SECTIONS');
 if(!/<meta[^>]*name=["']viewport["']/i.test(html))fail.push('VIEWPORT_MISSING');
 if(!/<title>[^<]*Rosales Café/i.test(html))fail.push('TITLE_MISSING');
 const css=html.match(/<style[^>]*>([\s\S]*?)<\/style>/i)?.[1]||'';
 if(css.length<350)fail.push('INLINE_CSS_MISSING');
 if(!css.includes('@media'))fail.push('RESPONSIVE_CSS_MISSING');
 if(!/(background:|background-color:|linear-gradient\()/i.test(css))fail.push('VISUAL_STYLING_MISSING');
 if(/<form\b|<script\b|<iframe\b|<object\b/i.test(html))fail.push('UNVERIFIED_FORM_OR_EXECUTABLE');
 if(/<link[^>]+rel=["']stylesheet|<img[^>]+src=["']https?:|(?:href|src)=["']\/\//i.test(html))fail.push('EXTERNAL_DEPENDENCY');
 for(const item of banned)if(html.toLowerCase().includes(item.toLowerCase()))fail.push('UNVERIFIED_CLAIM: '+item);
 return fail;
}
export function prompt(issues,iteration) {
 return [
  iteration===1?'Repare a landing page Rosales Café previamente reprovada.':'SEGUNDA TENTATIVA: faça uma nova página inteira corrigindo todas as falhas.',
  'FALHAS VERIFICADAS: '+issues.slice(0,16).join('; '),
  'POSICIONAMENTO obrigatório e VISÍVEL: '+BRAND,
  'Produza exatamente UM arquivo <file path="site/index.html"> ... </file>.',
  'HTML completo com <!DOCTYPE html>, <html lang="pt-BR">, meta viewport, title Rosales Café, header, nav com âncoras, main, >=2 section, h1 e footer.',
  'Dentro do HTML use <style> com pelo menos 350 caracteres de CSS real, cores café e creme e um bloco @media para tela de 390px.',
  'Nenhum arquivo CSS/JS externo, script, iframe, links de imagem externa, preços, formas de pagamento, endereço, contato, certificações, datas, promoções ou dados comerciais não confirmados.',
  'Texto em português brasileiro sobre cultura, experiência, aromas e estilo colombiano. Não inventar origem geográfica.',
  'Feche todas as tags, retorne APENAS o <file ...> completo sem comentários fora dele.'
 ].join('\n');
}
async function streaming(res, progress) {
 if(!res.ok || !res.body)throw Error('OPEN_LOVABLE_STREAM_HTTP_'+res.status);
 const decoder=new TextDecoder();const reader=res.body.getReader();
 let buffer='',source='',events=0,errors=[];
 function frame(chunk) {
  for(const line of chunk.split('\n')) {
   if(!line.startsWith('data: '))continue;
   let item;try{item=JSON.parse(line.slice(6));}catch{continue;}
   events++;
   if(item.type==='stream' && typeof item.text==='string')source+=item.text;
   if(item.type==='error')errors.push(String(item.message||'UNKNOWN').slice(0,150));
   if(source.length>150000)throw Error('MODEL_OUTPUT_TOO_LARGE');
   if(events%25===0)progress({events,source_bytes:Buffer.byteLength(source),sha256:sha(source),errors:errors.slice(0,3)});
  }
 }
 while(true) {
  const {value,done}=await reader.read();
  if(done)break;
  buffer+=decoder.decode(value,{stream:true}).replaceAll('\r','');
  if(buffer.length>50000)throw Error('SSE_FRAME_TOO_LARGE');
  let i;while((i=buffer.indexOf('\n\n'))!==-1) {frame(buffer.slice(0,i));buffer=buffer.slice(i+2);}
 }
 if(buffer.trim())frame(buffer);
 return {source,events,errors};
}
async function main() {
 const original=fs.readFileSync('/app/p6_input/original.html','utf8');
 if(sha(original)!==P5_SHA)throw Error('P5_PROVENANCE_SHA_MISMATCH');
 const token=process.env.OLYMPUS_P5_GATE_TOKEN;
 if(!token || token.length<20)throw Error('NO_INTERNAL_GATE_TOKEN');
 const proof={schema:'olympus.p6.repair.v1',p5_sha256:P5_SHA,
  upstream:'firecrawl/open-lovable@806b8072f28afea11fa2b028cac1449eff74c511',
  model:'qwen2.5-coder:1.5b',provider:'local Ollama',paid_api_calls:0,
  attempts:[],status:'BLOCKED',quick_gate:false,final_browser_qa:false,
  production_integrated:false};
 save(proof);
 const health=await fetch(BASE+'/api/olympus-p3-proof',{signal:AbortSignal.timeout(6000)});
 if(!health.ok)throw Error('APP_NOT_READY');
 let problems=check(original);
 for(let attempt=1;attempt<=2;attempt++){
  const p=prompt(problems,attempt);
  const step={attempt,prompt_sha256:sha(p),status:'RUNNING'};
  proof.attempts.push(step);save(proof);
  try{
   const res=await fetch(BASE+'/api/generate-ai-code-stream',{
    method:'POST',headers:{'Content-Type':'application/json','x-olympus-p5-internal':token},
    body:JSON.stringify({prompt:p,model:'openai/qwen2.5-coder:1.5b',isEdit:false,context:{}}),
    signal:AbortSignal.timeout(180000)});
   step.http=res.status;save(proof);
   const result=await streaming(res,state=>{step.progress=state;save(proof)});
   fs.writeFileSync(path.join(OUT,'model-original-stream-'+attempt+'.txt'),result.source);
   step.events=result.events;step.stream_sha256=sha(result.source);step.errors=result.errors;
   const candidates=extract(result.source);
   if(!candidates.length) {
    step.status='BLOCKED_NO_COMPLETE_FILE';problems=['NO_COMPLETE_XML_FILE'];
    save(proof);continue;
   }
   const html=candidates.at(-1);step.generated_sha256=sha(html);step.bytes=Buffer.byteLength(html);
   fs.writeFileSync(path.join(OUT,'candidate-'+attempt+'.html'),html);
   problems=check(html);step.issues=problems;
   step.status=problems.length?'BLOCKED_QUICK_GATE':'QUICK_GATE_PASS';
   save(proof);
   if(!problems.length){
    fs.writeFileSync(path.join(OUT,'site-index.html'),html);
    proof.quick_gate=true;proof.status='QUICK_GATE_PASS_NEEDS_HTTP_BROWSER_QA';save(proof);
    return;
   }
  }catch(error){
   step.status='BLOCKED_ERROR';step.error=String(error?.message||error).slice(0,180);
   problems=[step.error];save(proof);
  }
 }
 proof.status='BLOCKED_REPAIR_EXHAUSTED';save(proof);process.exitCode=2;
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{await main();}catch(error){
  fs.mkdirSync(OUT,{recursive:true});
  fs.writeFileSync(path.join(OUT,'p6-error.txt'),String(error?.message||error));
  console.error('P6_BLOCKED',String(error?.message||error));process.exitCode=2;
 }
}