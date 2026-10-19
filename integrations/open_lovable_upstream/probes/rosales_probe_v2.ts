/**
 * Open Lovable Rosales Café — isolated one-shot delivery qualification.
 * Runs only against the Railway-private staging service. No user credentials.
 * Never promotes to a customer project. MUST inspect embedded E2B return code.
 */
import { createHash } from "node:crypto";

const BASE = "http://olympus-lovable-staging.railway.internal:8080";
const MODEL = Bun.env.OLYMPUS_STAGING_GROQ_MODEL || "openai/gpt-oss-120b";
const TASK = [
  "Crie uma landing page visualmente excelente, responsiva em 390px e 1440px, para ROSALES CAFÉ.",
  "Marca conceitual: café brasileiro com inspiração no estilo colombiano; apenas esse fato é confirmado.",
  "Crie EXATAMENTE 2 arquivos de código: src/App.jsx e src/index.css, no formato <file path=\"...\">.",
  "src/App.jsx deve conter TODOS os componentes React no mesmo arquivo, com export default App;",
  "NÃO importe ./components, não adicione bibliotecas nem arquivos novos, não use imagens ou URLs remotas.",
  "A estilização CSS deve estar em src/index.css, que já é importado pelo Vite.",
  "Inclua cabeçalho com links âncora, hero, conceito, experiência e rodapé.",
  "Use tipografia do sistema, layout editorial moderno, tons de café e creme e ilustração 100% CSS.",
  "Textos permitidos: 'Rosales Café', 'Café brasileiro com inspiração no estilo colombiano',",
  "'Uma pausa para apreciar o café', 'Conheça o conceito', 'Nossa proposta',",
  "'Um convite a descobrir o café com atenção aos detalhes'.",
  "Não invente loja, endereço, preços, equipe, fornecedores, certificações, sustentabilidade,",
  "ingredientes, notas de degustação, horários, contatos, depoimentos, baristas, Wi-Fi ou entregas.",
  "Sem código executável além do React necessário. Sem chamadas de rede, iframe, eval ou dangerouslySetInnerHTML.",
  "O resultado deve compilar com npm run build em Vite e ter âncoras locais funcionais."
].join(" ");
function sha(x){return createHash("sha256").update(x).digest("hex")}
async function post(path, body, extra={}, timeout=140000){
  const response=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json",...extra},
    body:JSON.stringify(body),signal:AbortSignal.timeout(timeout)});
  if(!response.ok) throw Error("http_"+response.status+"_"+path.split("/").at(-1));
  const raw=await response.text();
  if(raw.length>6000000) throw Error("response_too_large");
  if((response.headers.get("content-type")||"").includes("text/event-stream")){
    let completed=null, count=0;
    for(const line of raw.split(/\r?\n/)){
      if(!line.startsWith("data: "))continue;
      if(++count>30000)throw Error("sse_limit");
      let event;
      try{event=JSON.parse(line.slice(6))}catch{throw Error("invalid_sse")}
      if(event.type==="error")throw Error("upstream_generation_error");
      if(event.type==="complete"){
        if(completed)throw Error("duplicate_complete");
        completed=event;
      }
    }
    if(!completed)throw Error("no_sse_completion");
    return completed;
  }
  let out;
  try{out=JSON.parse(raw)}catch{throw Error("invalid_json")}
  if(!out||out.error||out.success===false)throw Error("provider_negative_response");
  return out;
}
async function run(){
 if(Bun.env.OLYMPUS_ROSALES_PROBE_ONCE!=="1"){
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase:"disabled"}));return;
 }
 let phase="sandbox";
 try{
  const sandbox=await post("/api/create-ai-sandbox-v2",{}, {},90000);
  const sid=sandbox.sandboxId;
  if(typeof sid!=="string"||sid.length<4)throw Error("missing_sandbox");
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:true}));
  phase="generation";
  const gen=await post("/api/generate-ai-code-stream",
    {prompt:TASK,model:MODEL,context:{sandboxId:sid},isEdit:false},{},180000);
  const source=gen.generatedCode;
  if(typeof source!=="string"||source.length>250000||!source.includes("<file path="))
    throw Error("generated_text_missing");
  const paths=[...source.matchAll(/<file path="([^"]+)">/g)].map(x=>x[1]);
  if(paths.length!==2||!paths.includes("src/App.jsx")||!paths.includes("src/index.css"))
    throw Error("model_violated_two_file_contract:"+paths.join(",").slice(0,95));
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:true,model:MODEL,files:paths.length}));
  phase="apply";
  const apply=await post("/api/apply-ai-code-stream",
    {response:source,isEdit:false,packages:[],sandboxId:sid},{},150000);
  const result=apply.results;
  if(!result||(result.errors||[]).length)throw Error("apply_failed");
  const written=[...(result.filesCreated||[]),...(result.filesUpdated||[])];
  if(!paths.every(x=>written.includes(x)))throw Error("incomplete_file_apply");
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:true,written:written.length}));
  phase="build";
  // Upstream E2B wrapper may report success:true/exitCode:0 even when nested build failed.
  const build=await post("/api/run-command-v2",{command:"npm run build"},{},120000);
  const transcript=String(build.output||"");
  const codes=[...transcript.matchAll(/Return code:\s*(\d+)/g)].map(x=>Number(x[1]));
  const realCode=codes.length?codes.at(-1):null;
  if(realCode!==0){
    const errors=transcript.split("\n").filter(x=>/Could not resolve|ERROR|error:|Failed|RollupError/.test(x)).slice(0,3);
    console.log("OLYMPUS_OPEN_LOVABLE_BUILD_ERROR "+JSON.stringify({realExit:realCode,errors:errors.map(x=>x.slice(0,175))}));
    throw Error("react_build_failed_"+String(realCode));
  }
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:true,realExit:realCode}));
  phase="export";
  const token=Bun.env.OLYMPUS_BRIDGE_EXPORT_TOKEN||"";
  if(token.length<32)throw Error("bridge_token_missing");
  const snap=await post("/api/olympus-export",{sandboxId:sid},{"x-olympus-bridge-token":token},120000);
  if(snap.sandboxId!==sid||!Array.isArray(snap.files)||!snap.files.length)throw Error("export_identity_or_empty");
  const files=[...snap.files].sort((a,b)=>Buffer.compare(Buffer.from(String(a.path)),Buffer.from(String(b.path))));
  const digest=createHash("sha256"),seen=new Set();
  for(const f of files){
    if(typeof f.path!=="string"||typeof f.content!=="string"||seen.has(f.path))throw Error("bad_snapshot");
    seen.add(f.path);
    const actual=sha(Buffer.from(f.content));
    if(actual!==f.sha256)throw Error("file_digest_mismatch");
    digest.update(Buffer.from(f.path));digest.update(Buffer.from([0]));digest.update(Buffer.from(actual,"hex"));
  }
  if(digest.digest("hex")!==snap.sha256||!paths.every(x=>seen.has(x)))throw Error("manifest_mismatch");
  const combined=files.map(x=>x.content).join("\n");
  const bad=/(?:https?:\/\/|dangerouslySetInnerHTML|fetch\(|\b(?:sustent[aá]vel|baristas?|wi-?fi|card[aá]pio|produtores?|fazendas?|gr[aã]os certificados|hor[aá]rios de funcionamento)\b)/i;
  const contentApproved=!bad.test(combined);
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:true,model:MODEL,exported:files.length,
    sha256:snap.sha256,contentApproved,result:contentApproved?"BUILT_EXPORT_REVIEW_PENDING":"BUILT_EXPORT_CONTENT_REJECTED"}));
 }catch(error){
  console.log("OLYMPUS_OPEN_LOVABLE_V2 "+JSON.stringify({phase,ok:false,model:MODEL,
    reason:error instanceof Error?error.message.slice(0,150):"unknown"}));
 }
}
await run();
