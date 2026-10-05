import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading


def load_module(root):
    path = root / 'scripts/omniroute_pool_sync.py'
    spec = importlib.util.spec_from_file_location('pool_sync_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classification_and_probe(tmp_path):
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root)
    assert mod._is_openrouter_free({'id':'openrouter/foo/bar:free'})
    assert not mod._is_openrouter_free({'id':'openrouter/foo/bar'})
    assert mod._classify_ollama({'id':'ollama/qwen2.5-coder:7b'}) == 'local'
    assert mod._classify_ollama({'id':'ollamacloud/qwen3-coder'}) == 'cloud'

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def _send(self, code, obj):
            raw=json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path == '/v1/models':
                self._send(200, {'data':[
                    {'id':'openrouter/foo/code:free'},
                    {'id':'ollama/qwen2.5-coder:7b','providerId':'ollama-local'},
                    {'id':'ollamacloud/qwen3-coder','providerId':'ollama-cloud'},
                ]})
            else: self._send(404,{})
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(n) or b'{}')
            if self.path == '/v1/chat/completions':
                self._send(200, {'model':data.get('model'), 'choices':[{'message':{'content':'OLYMPUS_READY'}}]})
            else: self._send(404,{})
    server=ThreadingHTTPServer(('127.0.0.1',0),H); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        mod.BASE_URL=f'http://127.0.0.1:{server.server_address[1]}'
        mod.STATUS_PATH=tmp_path/'status.json'
        mod._api_key=lambda: 'secret'
        mod._combo_list=lambda: ([{'name':'Conding-free','models':[{'model':'openrouter/openrouter/free'}]}], 'json')
        result=mod.run(full=False)
        assert result['primary_combo']=='Conding-free'
        assert result['primary_combo_ready'] is True
        assert result['ollama_local_ready']==['ollama/qwen2.5-coder:7b']
        assert result['ollama_cloud_ready']==['ollamacloud/qwen3-coder']
        assert result['openrouter_free_discovered']==1
    finally:
        server.shutdown(); server.server_close()
