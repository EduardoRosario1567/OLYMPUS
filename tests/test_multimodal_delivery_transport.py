"""Catch silent image loss at real HTTP adapter boundaries; no paid traffic."""
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest
from olympus.routing.provider_fabric import OpenAICompatibleAdapter, ProviderConfig
from olympus.routing.interfaces import ModelCapability
from olympus.routing.omniroute_adapter import OmniRouteAdapter

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
IMAGE = 'data:image/png;base64,' + base64.b64encode(PNG).decode()


@contextmanager
def provider_server(output='{"verdict":"revise","findings":[]}', on_request=None, returned_model='vision-free'):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            body = {'data': [
                {'id':'vision-free','architecture':{'input_modalities':['text','image']}},
                {'id':'text-only','architecture':{'input_modalities':['text']}},
                {'id':'paid-vision','architecture':{'input_modalities':['text','image']}},
            ]}
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())
        def do_POST(self):
            requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            if on_request: on_request()
            body = ({'output':[{'type':'message','content':[{'type':'output_text','text':output}]}],'model':returned_model}
                    if self.path.endswith('/responses') else
                    {'choices':[{'message':{'content':output}}],'model':returned_model})
            if returned_model is Ellipsis: body.pop('model')
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield 'http://127.0.0.1:%s/v1' % server.server_port, requests
    finally: server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('wire', ['chat_completions','responses'])
def test_real_http_request_contains_screenshot_pixels(wire):
    with provider_server() as (url, requests):
        adapter = OpenAICompatibleAdapter(ProviderConfig('openrouter',url,wire_api=wire))
        result = adapter.execute('vision-free','Review this page',image_inputs=(IMAGE,))
        assert result.success
        payload = requests[0][1]
        if wire == 'responses':
            assert isinstance(payload['input'], list), 'Responses silently dropped the screenshots'
        content = payload['input'][0]['content'] if wire=='responses' else payload['messages'][0]['content']
        assert isinstance(content, list), 'the adapter silently dropped the screenshots'
        part = content[1]
        actual = part['image_url'] if wire=='responses' else part['image_url']['url']
        assert base64.b64decode(actual.split(',',1)[1]) == PNG
        assert part['type'] == ('input_image' if wire=='responses' else 'image_url')
        assert result.metadata['image_inputs_sent'] == 1


@pytest.mark.parametrize('images', [
    ('https://remote.example/private.png',),
    ('data:image/png;base64,broken',),
    ('data:image/png;base64,'+base64.b64encode(b'not an image').decode(),),
    (IMAGE,)*4,
    ('data:image/svg+xml;base64,'+base64.b64encode(b'<svg/>').decode(),),
])
def test_invalid_images_are_rejected_before_network(images):
    with provider_server() as (url, requests):
        result = OpenAICompatibleAdapter(ProviderConfig('openrouter',url)).execute('vision-free','Review',image_inputs=images)
        assert not result.success, 'invalid image inputs were silently ignored'
        assert result.status == 'invalid_image_input'
        assert requests == []


def test_model_catalog_requires_explicit_image_input_modality():
    with provider_server() as (url, _):
        models = OpenAICompatibleAdapter(ProviderConfig('openrouter',url)).list_models()
        assert ModelCapability.IMAGEM in models[0].capabilities
        assert ModelCapability.IMAGEM not in models[1].capabilities


def test_plain_text_wire_contract_is_preserved():
    with provider_server() as (url, requests):
        assert OpenAICompatibleAdapter(ProviderConfig('openrouter',url)).execute('text-only','hello').success
        assert requests[0][1]['messages'] == [{'role':'user','content':'hello'}]


def test_omniroute_also_transports_actual_screenshot_pixels():
    with provider_server() as (url, requests):
        result = OmniRouteAdapter(url.removesuffix('/v1')).execute('vision-free','Review',image_inputs=(IMAGE,))
        assert result.success
        content = requests[0][1]['messages'][0]['content']
        assert isinstance(content, list), 'OmniRoute discarded the image'
        assert base64.b64decode(content[1]['image_url']['url'].split(',',1)[1]) == PNG
        assert result.metadata['image_inputs_sent'] == 1


def test_omniroute_refuses_remote_image_input_without_request():
    with provider_server() as (url, requests):
        result = OmniRouteAdapter(url.removesuffix('/v1')).execute('vision-free','Review',image_inputs=('https://remote.example/x.png',))
        assert not result.success
        assert result.status == 'invalid_image_input'
        assert not requests
