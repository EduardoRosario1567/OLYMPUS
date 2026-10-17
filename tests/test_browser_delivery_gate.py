from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.verifier import AgentVerifier
from olympus.agent.browser_delivery import BrowserRuntime, WebDeliveryVerifier
import base64
import pytest


HTML = '''<!doctype html><html lang="pt-BR"><head><title>Rosales Café</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{box-sizing:border-box}body{margin:0;background:#faf4ea;color:#302519;font:18px Arial}
main{width:min(100% - 32px,900px);margin:auto;padding:40px 0}h1{font-size:clamp(32px,6vw,64px)}
a,button{color:#302519}section{padding:24px 0}button{padding:12px}</style></head><body>
<main><nav><a href="#menu">Ver cardápio</a></nav><h1>Rosales Café</h1>
<p>Encontre seu momento de pausa com café, conversa e uma composição clara para escolher sua próxima bebida.</p>
<section id="menu"><h2>Escolha seu café</h2><p>Explore as opções apresentadas nesta página e escolha como aproveitar seu momento.</p>
<button id="reveal" onclick="document.querySelector('#status').textContent='Cardápio aberto'">Abrir opções</button>
<p id="status" aria-live="polite">Opções disponíveis abaixo.</p></section></main>__SCRIPT__</body></html>'''


def workspace(tmp_path, script=''):
    (tmp_path/'app').mkdir()
    (tmp_path/'app/index.html').write_text(HTML.replace('__SCRIPT__', script))
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/delivery-concept.md').write_text(
        '# Visual thesis\nA warm editorial composition with generous breathing space and a readable type scale.\n'
        '# Content plan\nBrand, offer, choices and a primary navigation anchor.\n'
        '# Interaction plan\nThe control reveals menu status without network access.\n'
        '# Evidence\nSynthetic test content only; no addresses, prices or business history are asserted.\n')
    return MissionCompiler().compile('Crie uma landing page profissional responsiva para Rosales Café.').instruction()


def test_valid_html_with_runtime_javascript_error_is_rejected(tmp_path):
    task = workspace(tmp_path, '<script>missingMissionInitializer();</script>')
    errors = AgentVerifier(str(tmp_path)).verify_task_deliverable(task, ('app/index.html',), ('frontend',))
    assert any('browser' in error and 'missingMissionInitializer' in error for error in errors)


def test_rendered_delivery_records_actual_browser_evidence(tmp_path):
    task = workspace(tmp_path)
    verifier = AgentVerifier(str(tmp_path))
    assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()
    assert verifier.delivery_review['browser'] == 'passed'
    assert verifier.delivery_review['layout'] == 'passed'
    assert verifier.delivery_review['visual'] == 'not_assessed'
    assert {item['width'] for item in verifier.delivery_review['viewports']} == {390,768,1440}


@pytest.mark.parametrize('fragment,expected', [
    ('<img src="missing-coffee.png" alt="Café">', 'broken images'),
    ('<div style="width:2000px">Conteúdo</div>', 'horizontal page overflow'),
    ('<button>Reservar</button>', 'button has no observable behavior'),
    ('<input placeholder="Seu nome">', 'unnamed controls'),
    ('<a href="#missing">Ver detalhes</a>', 'fragment navigation has no destination'),
])
def test_rendered_defects_block_completion(tmp_path, fragment, expected):
    task = workspace(tmp_path, fragment)
    errors = AgentVerifier(str(tmp_path)).verify_task_deliverable(task, ('app/index.html',), ('frontend',))
    assert any(expected in item for item in errors)


def test_source_change_invalidates_previous_browser_evidence(tmp_path):
    task = workspace(tmp_path)
    verifier = AgentVerifier(str(tmp_path))
    assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()
    first_hash = verifier.delivery_review['content_sha256']
    path = tmp_path/'app/index.html'
    path.write_text(path.read_text().replace('</body>', '<script>changedBrokenInitializer()</script></body>'))
    errors = verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
    assert any('changedBrokenInitializer' in item for item in errors)
    assert verifier.delivery_review['content_sha256'] != first_hash
    assert verifier.delivery_review['browser'] == 'failed'


def test_missing_browser_runtime_fails_closed(tmp_path):
    workspace(tmp_path)
    gate = WebDeliveryVerifier(tmp_path, runtime=BrowserRuntime(str(tmp_path/'absent-runtime')))
    errors, review = gate.verify('app/index.html')
    assert 'browser_runtime_unavailable' in errors[0]
    assert review['browser'] == 'failed'


def test_static_failure_cannot_reuse_a_previous_rendered_success(tmp_path):
    task = workspace(tmp_path)
    verifier = AgentVerifier(str(tmp_path))
    assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()
    path = tmp_path/'app/index.html'
    path.write_text('<html><body><h1>Incompleto</h1></body></html>')
    assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
    assert verifier.delivery_review is None


def test_blocked_external_hero_background_is_not_silent_success(tmp_path):
    task = workspace(tmp_path, '<style>h1{background-image:url(https://unverified.example/coffee.jpg)}</style>')
    errors = AgentVerifier(str(tmp_path)).verify_task_deliverable(task, ('app/index.html',), ('frontend',))
    assert any('browser console' in item and 'Content Security Policy' in item for item in errors)


def test_required_form_is_exercised_with_synthetic_inputs(tmp_path):
    task = workspace(tmp_path, '''<form onsubmit="event.preventDefault();this.querySelector('output').textContent='Demonstração local recebida'">
        <label>Nome<input name="name" required></label><label>E-mail<input type="email" required></label>
        <button>Demonstrar envio</button><output>Dados de teste</output></form>''')
    verifier = AgentVerifier(str(tmp_path))
    assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()
    interaction = next(item for item in verifier.delivery_review['interactions'] if item.get('label')=='Demonstrar envio')
    assert interaction['synthetic_form_inputs'] is True
    assert interaction['observable_change'] is True


def test_button_with_delayed_visible_response_is_accepted(tmp_path):
    task = workspace(tmp_path)
    path = tmp_path/'app/index.html'
    path.write_text(path.read_text().replace(
        "document.querySelector('#status').textContent='Cardápio aberto'",
        "setTimeout(() => document.querySelector('#status').textContent='Cardápio aberto', 250)"))
    assert AgentVerifier(str(tmp_path)).verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()


def test_runner_cannot_publish_broken_page_or_fabricated_browser_proof(tmp_path):
    from olympus.cloud.runtime import CloudRuntime
    from types import SimpleNamespace
    from pathlib import Path
    import time
    class Runner:
        def __init__(self, root): self.root = Path(root)
        def run(self, task, **kwargs):
            workspace(self.root, '<script>fabricatedSuccessInitializer();</script>')
            return SimpleNamespace(status='completed', error=None,
                files_modified=('app/index.html','docs/delivery-concept.md'),
                delivery_review={'browser':'passed','visual':'passed'})
    runtime = CloudRuntime(str(tmp_path/'runtime'), lambda root, telemetry: Runner(root), max_workers=1)
    try:
        rec = runtime.submit('rosales', 'Crie uma landing page HTML para Rosales Café.')
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            rec = runtime.get(rec.execution_id)
            if rec.status in {'completed','failed','blocked'}: break
            time.sleep(.02)
        assert rec.status == 'failed'
        events = runtime.events(rec.execution_id)
        rejected = next(item for item in events if item['event']=='completion_rejected')
        assert rejected['delivery_review']['browser']=='failed'
        assert any('fabricatedSuccessInitializer' in item for item in rejected['errors'])
        assert not any(item['event']=='result_published' for item in events)
        assert not (runtime.projects.project_root('rosales')/'app/index.html').exists()
    finally: runtime.close()


def test_agent_repairs_runtime_error_before_completing(tmp_path):
    from olympus.agent.loop import AgentLoop
    from olympus.agent.actions import ActionType, AgentAction
    task = workspace(tmp_path, '<script>repairMeInitializer();</script>')
    class Planner:
        calls = 0
        feedback = ''
        def next_action(self, *args):
            self.calls += 1
            if self.calls == 2:
                self.feedback = str(args)
                path = tmp_path/'app/index.html'
                return AgentAction(ActionType.PATCH_FILE, 'app/index.html', {
                    'operation':'replace_lines','start_line':1,'end_line':len(path.read_text().splitlines()),
                    'new_content':HTML.replace('__SCRIPT__','')})
            return AgentAction(ActionType.FINISH, payload='ready')
    planner = Planner()
    result = AgentLoop(str(tmp_path), planner).run(task, max_iterations=4)
    assert result.state.status.value == 'completed'
    assert 'repairMeInitializer' in planner.feedback
    assert result.state.metadata['delivery_review']['browser'] == 'passed'
    assert planner.calls == 3


def test_built_static_output_is_inspected_and_source_changes_invalidate_it(tmp_path):
    workspace(tmp_path)
    (tmp_path/'app').rename(tmp_path/'dist')
    gate=WebDeliveryVerifier(tmp_path)
    errors,review=gate.verify('dist/index.html')
    assert not errors, errors
    path=tmp_path/'dist/index.html'
    path.write_text(path.read_text().replace('</body>','<script>brokenBuildInitializer()</script></body>'))
    errors,updated=gate.verify('dist/index.html')
    assert any('brokenBuildInitializer' in item for item in errors)
    assert updated['content_sha256'] != review['content_sha256']


def test_local_gif_supported_by_preview_is_decoded_in_review(tmp_path):
    workspace(tmp_path,'<img src="coffee.gif" alt="Synthetic transport fixture">')
    (tmp_path/'app/coffee.gif').write_bytes(base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'))
    errors,review=WebDeliveryVerifier(tmp_path).verify('app/index.html')
    assert not errors, errors
    assert review['browser']=='passed'
