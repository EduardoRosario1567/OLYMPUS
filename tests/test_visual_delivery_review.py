"""Real screenshots and HTTP transport; provider verdicts are controlled fixtures."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from olympus.agent.verifier import AgentVerifier
from olympus.agent.browser_delivery import WebDeliveryVerifier
from olympus.routing.provider_fabric import OpenAICompatibleAdapter, ProviderConfig
from tests.test_browser_delivery_gate import workspace
from tests.test_multimodal_delivery_transport import provider_server


ASSESSMENTS = {
    key:'Controlled contract fixture: this is not a real aesthetic opinion.'
    for key in ('hierarchy','typography','imagery','brand','content','mobile')
}
PASS = {'verdict':'pass','assessments':ASSESSMENTS,'findings':[]}
REVISE = {'verdict':'revise','assessments':ASSESSMENTS,'findings':[
    {'severity':'blocking','viewport':390,'problem':'Headline dominates the entire mobile viewport.',
     'repair':'Reduce the mobile headline and restore space before the primary action.'},
]}


def reviewer(url, eligible=('vision-free',)):
    assert importlib.util.find_spec('olympus.agent.visual_delivery') is not None, 'the visual review cycle is missing'
    from olympus.agent.visual_delivery import VisualDeliveryReviewer
    return VisualDeliveryReviewer(OpenAICompatibleAdapter(ProviderConfig('openrouter',url)),eligible)


def test_visual_gate_sends_the_three_real_browser_screenshots(tmp_path):
    task = workspace(tmp_path)
    with provider_server(json.dumps(PASS)) as (url, requests):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',)) == ()
        review = verifier.delivery_review
        assert review['visual'] == 'model_review_passed'
        assert review['visual_review']['authority'] == 'model_opinion'
        content = requests[0][1]['messages'][0]['content']
        received = [base64.b64decode(item['image_url']['url'].split(',',1)[1]) for item in content[1:]]
        assert len(received) == 3
        assert {hashlib.sha256(data).hexdigest() for data in received} == {item['sha256'] for item in review['artifacts']}
        assert all(len(data)>10000 for data in received), 'the review received dummy pixels'
        assert 'Rosales' in content[0]['text']
        assert 'warm editorial' in content[0]['text']
        assert 'evidence_root' not in json.dumps(review)
        assert str(tmp_path) not in json.dumps(review)


def test_visual_critique_blocks_finish_with_specific_repair_feedback(tmp_path):
    task = workspace(tmp_path)
    with provider_server(json.dumps(REVISE)) as (url, _):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        errors = verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert any('Reduce the mobile headline' in item for item in errors)
        assert verifier.delivery_review['browser'] == 'passed'
        assert verifier.delivery_review['visual'] == 'revision_required'


@pytest.mark.parametrize('response', ['everything looks great', '{}', json.dumps(dict(PASS,assessments={})),
    json.dumps(dict(REVISE,verdict='pass')), json.dumps(dict(PASS,verdict='revise'))])
def test_malformed_or_contradictory_opinion_cannot_become_a_visual_pass(tmp_path,response):
    task = workspace(tmp_path)
    with provider_server(response) as (url, _):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert verifier.delivery_review['visual'] == 'not_assessed'


@pytest.mark.parametrize('eligible', [(), ('text-only',), ('not-in-catalog',)])
def test_no_eligible_vision_route_blocks_without_inference(tmp_path,eligible):
    task = workspace(tmp_path)
    with provider_server(json.dumps(PASS)) as (url, requests):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url,eligible))
        errors = verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert any('visual_review_unavailable' in item for item in errors)
        assert verifier.delivery_review['visual'] == 'not_assessed'
        assert requests == []


def test_screenshot_tampering_is_rejected_before_vision_inference(tmp_path):
    task = workspace(tmp_path)
    with provider_server(json.dumps(PASS)) as (url, requests):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        evidence = tmp_path.parent/(tmp_path.name+'-evidence')
        verifier.browser_verifier = WebDeliveryVerifier(tmp_path,evidence_root=evidence)
        assert verifier.browser_verifier.verify('app/index.html')[0] == ()
        next(evidence.rglob('viewport-390.png')).write_bytes(b'forged screenshot')
        assert verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert verifier.delivery_review['visual'] == 'not_assessed'
        assert requests == []


def test_source_modified_during_visual_review_invalidates_opinion(tmp_path):
    task = workspace(tmp_path)
    path = tmp_path/'app/index.html'
    def change(): path.write_text(path.read_text().replace('Rosales Café','Changed after screenshot'))
    with provider_server(json.dumps(PASS),on_request=change) as (url, _):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        errors = verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert any('delivery_changed' in item for item in errors)
        assert verifier.delivery_review['visual'] == 'not_assessed'


def test_identical_review_reuses_evidence_but_new_brief_requires_new_opinion(tmp_path):
    task = workspace(tmp_path)
    with provider_server(json.dumps(PASS)) as (url, requests):
        verifier = AgentVerifier(str(tmp_path), visual_reviewer=reviewer(url))
        assert not verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert not verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert len(requests) == 1
        concept = tmp_path/'docs/delivery-concept.md'
        concept.write_text(concept.read_text()+'\nRefine the visual rhythm without inventing company facts.\n')
        assert not verifier.verify_task_deliverable(task, ('app/index.html',), ('frontend',))
        assert len(requests) == 2


def test_independent_publication_rejects_runner_forged_visual_success(tmp_path):
    from olympus.cloud.runtime import CloudRuntime
    with provider_server(json.dumps(REVISE)) as (url, _):
        visual = reviewer(url)
        class Runner:
            def __init__(self,root): self.root=Path(root)
            def run(self,task,**kwargs):
                workspace(self.root)
                return SimpleNamespace(status='completed',error=None,files_modified=('app/index.html','docs/delivery-concept.md'),
                                       delivery_review={'browser':'passed','visual':'model_review_passed'})
        runtime = CloudRuntime(str(tmp_path/'runtime'),lambda root,telemetry:Runner(root),max_workers=1,
            verifier_factory=lambda root:AgentVerifier(root,visual_reviewer=visual))
        try:
            rec = runtime.submit('rosales','Crie uma landing page HTML para Rosales Café.')
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                rec=runtime.get(rec.execution_id)
                if rec.status in {'completed','failed','blocked'}: break
                time.sleep(.02)
            assert rec.status == 'failed'
            event = next(item for item in runtime.events(rec.execution_id) if item['event']=='completion_rejected')
            assert event['delivery_review']['visual']=='revision_required'
            assert any('Reduce the mobile headline' in item for item in event['errors'])
        finally: runtime.close()


def test_visual_review_budget_stops_fourth_inference(tmp_path):
    task=workspace(tmp_path)
    gate=WebDeliveryVerifier(tmp_path)
    errors,rendered=gate.verify('app/index.html')
    assert not errors
    images=gate.evidence_images(rendered['content_sha256'])
    with provider_server(json.dumps(REVISE)) as (url,requests):
        critic=reviewer(url)
        for index in range(3):
            errors,opinion=critic.review(task,'Controlled concept revision '+str(index),rendered,images)
            assert errors and opinion['status']=='revision_required'
        errors,opinion=critic.review(task,'Fourth revision',rendered,images)
        assert errors and opinion['status']=='not_assessed'
        assert 'budget exhausted' in errors[0]
        assert len(requests)==3


def test_text_only_transport_cannot_turn_an_opinion_into_visual_approval(tmp_path):
    from olympus.agent.visual_delivery import VisualDeliveryReviewer
    task=workspace(tmp_path)
    class OldTextTransport(OpenAICompatibleAdapter):
        def execute(self,model_id,prompt,**kwargs):
            return super().execute(model_id,prompt)
    with provider_server(json.dumps(PASS)) as (url,requests):
        critic=VisualDeliveryReviewer(OldTextTransport(ProviderConfig('openrouter',url)),('vision-free',))
        verifier=AgentVerifier(str(tmp_path),visual_reviewer=critic)
        assert verifier.verify_task_deliverable(task,('app/index.html',),('frontend',))
        assert verifier.delivery_review['visual']=='not_assessed'
        assert isinstance(requests[0][1]['messages'][0]['content'],str)


@pytest.mark.parametrize('reported', ['text-only','paid-vision',None,'',Ellipsis])
def test_actual_model_without_catalogued_vision_capability_cannot_approve(tmp_path,reported):
    task=workspace(tmp_path)
    with provider_server(json.dumps(PASS),returned_model=reported) as (url,_):
        verifier=AgentVerifier(str(tmp_path),visual_reviewer=reviewer(url))
        assert verifier.verify_task_deliverable(task,('app/index.html',),('frontend',)), 'a text-only actual model approved the visual delivery'
        assert verifier.delivery_review['visual']=='not_assessed'
