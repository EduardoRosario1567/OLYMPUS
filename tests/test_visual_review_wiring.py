"""The production mission and publication must both use trusted visual review."""
import json
from pathlib import Path
from unittest.mock import patch

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.mission import AutonomousPatchRunner, MissionSpec, MissionStep
from olympus.agent.verifier import AgentVerifier
from olympus.routing.provider_fabric import OpenAICompatibleAdapter, ProviderConfig, ProviderRegistry
from olympus.agent.multibrain_registry import AgentModelRoute
from tests.test_browser_delivery_gate import workspace, HTML
from tests.test_multimodal_delivery_transport import provider_server
from tests.test_visual_delivery_review import reviewer, PASS, REVISE


def test_agent_repairs_visual_critique_before_finishing(tmp_path):
    task=workspace(tmp_path)
    response=json.dumps(REVISE)
    # Keep actual network/renderer/reviewer. Only the planner and remote opinion
    # are deterministic so this tests the repair feedback contract, not aesthetics.
    class Planner:
        calls=0
        feedback=''
        def next_action(self,*args):
            self.calls+=1
            if self.calls in {1,3}:
                if self.calls==3: self.feedback=str(args)
                path=tmp_path/'app/index.html'
                return AgentAction(ActionType.PATCH_FILE,'app/index.html',{
                    'operation':'replace_lines','start_line':1,'end_line':len(path.read_text().splitlines()),
                    'new_content':HTML.replace('__SCRIPT__','').replace('6vw','4vw' if self.calls==3 else '6vw')})
            return AgentAction(ActionType.FINISH,payload='ready')
    with provider_server(response) as (url, requests):
        # Return the second controlled opinion only after the repair has changed
        # the rendered source; the HTTP boundary remains real.
        adapter=OpenAICompatibleAdapter(ProviderConfig('openrouter',url))
        original=adapter._request_url
        def boundary(*args,**kwargs):
            status,data=original(*args,**kwargs)
            if args[0]=='POST' and len(requests)>1:
                data['choices'][0]['message']['content']=json.dumps(PASS)
            return status,data
        with patch.object(adapter,'_request_url',boundary):
            from olympus.agent.visual_delivery import VisualDeliveryReviewer
            verifier=AgentVerifier(str(tmp_path),visual_reviewer=VisualDeliveryReviewer(adapter,('vision-free',)))
            planner=Planner()
            result=AgentLoop(str(tmp_path),planner,verifier=verifier).run(task,max_iterations=5)
        assert result.state.status.value=='completed', (result.state.errors,result.state.metadata)
        assert 'Reduce the mobile headline' in planner.feedback
        assert planner.calls==4
        assert len(requests)==2
        assert result.state.metadata['delivery_review']['visual']=='model_review_passed'


def test_backend_verifier_blocks_missing_vision_instead_of_publishing_unreviewed_page(tmp_path):
    from app.api import cloud_runtime
    task=workspace(tmp_path)
    quality_factory=getattr(cloud_runtime,'_quality_verifier',None)
    assert callable(quality_factory), 'production has no independent visual gate'
    with provider_server(json.dumps(PASS)) as (url, requests), patch.object(cloud_runtime,'build_visual_review_routing',
            return_value=(OpenAICompatibleAdapter(ProviderConfig('openrouter',url)),())):
        verifier=quality_factory(str(tmp_path))
        assert verifier.verify_task_deliverable(task,('app/index.html',),('frontend',))
        assert verifier.delivery_review['visual']=='not_assessed'
        assert requests==[]


def test_visual_router_intersects_free_policy_with_catalog_and_excludes_paid_route():
    from app.core import provider_runtime
    builder=getattr(provider_runtime,'build_visual_review_routing',None)
    assert callable(builder), 'there is no cost-safe visual routing builder'
    with provider_server(json.dumps(PASS)) as (url, requests):
        registry=ProviderRegistry()
        registry.register('openrouter',OpenAICompatibleAdapter(ProviderConfig('openrouter',url)))
        registry.register('omniroute',OpenAICompatibleAdapter(ProviderConfig('omniroute',url)))
        routes=(AgentModelRoute('openrouter::vision-free','Free','openrouter',100,tier='free'),
                AgentModelRoute('openrouter::paid-vision','Paid','openrouter',90,tier='paid'))
        with patch.object(provider_runtime,'build_provider_registry',return_value=registry), \
             patch.object(provider_runtime,'configured_free_routes',return_value=routes):
            adapter,eligible=builder()
        assert eligible==('openrouter::vision-free',)
        assert not requests


def test_patch_runner_uses_visual_verifier_factory_before_completion(tmp_path):
    workspace(tmp_path,'<style>@media(max-width:600px){main{padding:24px 0}section{padding:16px 0}}button{border:1px solid #302519;border-radius:6px;background:#eee1cf}a{text-underline-offset:4px}</style>')
    class Selector:
        def select_candidates(self,*args): return ('coding',)
    class Planner:
        calls=0
        def next_action(self,*args):
            self.calls+=1
            if self.calls==1:
                path=tmp_path/'app/index.html'
                return AgentAction(ActionType.PATCH_FILE,'app/index.html',{
                    'operation':'replace_lines','start_line':1,'end_line':len(path.read_text().splitlines()),
                    'new_content':path.read_text()})
            return AgentAction(ActionType.FINISH,payload='ready')
    with provider_server(json.dumps(REVISE)) as (url,_):
        visual=reviewer(url)
        import inspect
        assert 'verifier_factory' in inspect.signature(AutonomousPatchRunner).parameters, 'mission loop cannot receive the visual gate'
        runner=AutonomousPatchRunner(str(tmp_path),object(),selector=Selector(),
            planner_factory=lambda adapter,model:Planner(),
            verifier_factory=lambda root:AgentVerifier(root,visual_reviewer=visual))
        result=runner.run(MissionSpec('visual','Visual delivery',(MissionStep('page','Page',
            'Crie uma landing page HTML para Rosales Café.',max_iterations=2),)))
        assert not result.success
        state=result.steps[0].loop_result.state
        assert state.metadata['delivery_review']['visual']=='revision_required', (state.errors,state.metadata)
        assert any('Reduce the mobile headline' in error for error in state.errors)
