"""Fail-closed extraction of the untouched model-generated P5 HTML from the original CI artifact."""
import hashlib,json,re,sys
from pathlib import Path
EXPECTED='838d3d741335a9ac49363237956be0c05beec60b7909b8b2407b22609bf57faf'
UPSTREAM='806b8072f28afea11fa2b028cac1449eff74c511'
def extract(evidence:Path,destination:Path):
 proof=json.loads((evidence/'proof.json').read_text(encoding='utf8'))
 assert proof['upstream_commit']==UPSTREAM and proof['configured_model']=='qwen2.5-coder:1.5b','WRONG_MODEL_OR_UPSTREAM'
 assert proof['status']=='LOCAL_MODEL_FILES_GENERATED','P5_NOT_REAL_GENERATION'
 assert proof['direct_model']['ok'] is True and proof['open_lovable_stream']['ok'] is True,'NO_INFERENCE_PROOF'
 assert proof['files'][0]['sha256']==EXPECTED,'P5_MANIFEST_CHANGED'
 raw=(evidence/'original-stream.txt').read_text(encoding='utf8')
 m=re.search(r'<file path="site/index.html">([\s\S]*?)</file>',raw)
 assert m,'ORIGINAL_STREAM_LACKS_HTML'
 html=m.group(1)
 assert hashlib.sha256(html.encode('utf8')).hexdigest()==EXPECTED,'P5_SOURCE_TAMPERED'
 destination.parent.mkdir(parents=True,exist_ok=True)
 destination.write_text(html,encoding='utf8')
 return {'path':str(destination),'bytes':len(html.encode('utf8')),'sha256':EXPECTED}
if __name__=='__main__':
 try:print(json.dumps(extract(Path(sys.argv[1]),Path(sys.argv[2]))))
 except Exception as err:print('P6_BLOCKED:',str(err),file=sys.stderr);raise SystemExit(2)