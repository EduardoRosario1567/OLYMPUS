// OLYMPUS P5: inspect the REAL local Ollama result and original Open Lovable SSE.
 // No execution of generated code, no fabricated artifacts, no remote publishing.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const RESULTS='/tmp/olympus-p5-results';
fs.mkdirSync(RESULTS,{recursive:true});
const report={
  schema:'olympus.p5.proof.v1', source:'firecrawl/open-lovable',
  upstream_commit:'806b8072f28afea11fa2b028cac1449eff74c511',
  configured_model:'qwen2.5-coder:0.5b',
  claimed_free_api_calls:0,
  generated_by_agent:false,
  site_passed:false,
  status:'BLOCKED',
  direct_model:{ok:false},
  open_lovable_stream:{ok:false},
  files:[]
};
const save=()=>{
  fs.writeFileSync(path.join(RESULTS,'proof.json'),JSON.stringify(report,null,2));
};
const digest=s=>crypto.createHash('sha256').update(s).digest('hex');
const modelBase='http://ollama:11434';
async function run(){
  const health=await fetch('http://127.0.0.1:3000/api/olympus-p3-proof',
    {signal:AbortSignal.timeout(12000)});
  if(!health.ok)throw Error('ORIGINAL_APP_NOT_HEALTHY');
  const h=await health.json();
  if(h.instanceId!==process.env.OLYMPUS_INSTANCE_ID)throw Error('INSTANCE_MISMATCH');
  const direct=await fetch(modelBase+'/v1/chat/completions',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({model:'qwen2.5-coder:0.5b',
      messages:[{role:'system',content:'You are a coding assistant.'},
                {role:'user',content:'Reply with exactly this word: FUNCTIONAL'}],
      stream:false,max_tokens:80,temperature:0}),
    signal:AbortSignal.timeout(120000)
  });
  const d=await direct.json();
  const answer=d?.choices?.[0]?.message?.content;
  report.direct_model={http_status:direct.status,ok:direct.ok&&
    typeof answer==='string'&&answer.trim().length>0,
    response_characters:typeof answer==='string'?answer.length:0,
    response_sha256:typeof answer==='string'?digest(answer):null,
    returned_model:d?.model??null,
    prompt_tokens:d?.usage?.prompt_tokens??null,
    completion_tokens:d?.usage?.completion_tokens??null};
  save();
  if(!report.direct_model.ok)throw Error('REAL_LOCAL_MODEL_INFERENCE_FAILED');

  // Only original upstream generator, not another hand-written site generator.
  const prompt=fs.readFileSync('/app/p5_mission.md','utf-8');
  if(prompt.length>4000)throw Error('MISSION_EXCEEDS_PINNED_PROMPT_LIMIT');
  const response=await fetch('http://127.0.0.1:3000/api/generate-ai-code-stream',{
    method:'POST',
    headers:{
      'Content-Type':'application/json',
      'x-olympus-p5-internal':process.env.OLYMPUS_P5_GATE_TOKEN
    },
    body:JSON.stringify({prompt,model:'openai/qwen2.5-coder:0.5b',isEdit:false,context:{}}),
    signal:AbortSignal.timeout(180000),
  });
  report.open_lovable_stream.http_status=response.status;
  report.open_lovable_stream.state='REQUEST_STARTED';
  save();
  if(!response.ok)throw Error('ORIGINAL_STREAM_ENDPOINT_REJECTED_'+response.status);
  if(!response.body)throw Error('EMPTY_STREAM');
  const reader=response.body.getReader();
  let wire='',raw='',numEvents=0,errors=[];
  const maxRaw=1_500_000;
  const processEvent=block=>{
    const line=block.split('\n').find(x=>x.startsWith('data: '));
    if(!line)return;
    let item;
    try{item=JSON.parse(line.slice(6));}catch{return;}
    numEvents++;
    if(item.type==='stream' && typeof item.text==='string'){
      raw+=item.text;
      if(raw.length>maxRaw)throw Error('GENERATED_RESPONSE_TOO_LARGE');
    }
    if(item.type==='error')errors.push(String(item.message||'provider error').slice(0,300));
    if(numEvents%5===0){
      report.open_lovable_stream={http_status:response.status,state:'STREAM_IN_PROGRESS',
        event_count:numEvents,raw_characters:raw.length,raw_sha256:digest(raw),
        errors:errors.slice(0,5)};
      fs.writeFileSync(path.join(RESULTS,'original-stream.txt'),raw,'utf-8');
      save();
    }
  };
  for(;;){
    const {value,done}=await reader.read();
    if(done)break;
    wire+=new TextDecoder().decode(value,{stream:true});
    if(wire.length>100000)throw Error('SSE_FRAME_TOO_LARGE');
    let pos;
    while((pos=wire.indexOf('\n\n'))>=0){
      const chunk=wire.slice(0,pos).replaceAll('\r','');
      wire=wire.slice(pos+2);
      processEvent(chunk);
    }
  }
  if(wire.trim())processEvent(wire);
  report.open_lovable_stream={http_status:response.status,ok:raw.length>0,
    event_count:numEvents,raw_characters:raw.length,raw_sha256:digest(raw),
    errors:errors.slice(0,5)};
  fs.writeFileSync(path.join(RESULTS,'original-stream.txt'),raw,'utf-8');
  const re=/<file path="([^"<>]{1,240})">([\s\S]*?)<\/file>/g;
  let match;
  while((match=re.exec(raw))){
    const target=match[1].replaceAll('\\','/');
    if(target.startsWith('/')||target.split('/').some(p=>p==='..'||!p)||
       !/^(site|src|app|public)\//.test(target) ||
       !/\.(html|css|jsx|tsx|ts|js|json|svg)$/.test(target))continue;
    const source=match[2];
    if(Buffer.byteLength(source)>1024*1024 || source.length<20)continue;
    const dest=path.resolve(RESULTS,'generated',target);
    if(!dest.startsWith(path.resolve(RESULTS,'generated')+path.sep))continue;
    fs.mkdirSync(path.dirname(dest),{recursive:true});
    fs.writeFileSync(dest,source);
    report.files.push({path:target,sha256:digest(source),bytes:Buffer.byteLength(source)});
    if(report.files.length>=60)break;
  }
  report.generated_by_agent=report.files.length>0 && errors.length===0;
  report.status=report.generated_by_agent ? 'LOCAL_MODEL_FILES_GENERATED'
    : 'BLOCKED_ORIGINAL_GENERATION_NO_COMPLETE_FILES';
  save();
  if(!report.generated_by_agent)throw Error('OPEN_LOVABLE_GENERATION_NOT_VERIFIED');
}
try{
  await run();
  console.log(JSON.stringify({status:report.status,
    direct_model:report.direct_model,stream:report.open_lovable_stream,
    files:report.files},null,2));
}catch(err){
  report.failure_code=String(err?.message||err).slice(0,280);
  save();
  console.error('P5_BLOCKED:',report.failure_code);
  process.exitCode=2;
}
