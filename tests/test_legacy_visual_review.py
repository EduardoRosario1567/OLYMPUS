"""The older web tester must not bypass the same visual quality boundary."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from olympus.agent.mission import AutonomousPatchRunner
from olympus.routing.interfaces import RoutingExecutionResult
from olympus.routing.provider_fabric import OpenAICompatibleAdapter, ProviderConfig
from tests.test_browser_delivery_gate import workspace
from tests.test_multimodal_delivery_transport import provider_server
from tests.test_visual_delivery_review import REVISE


def test_legacy_mission_cannot_finish_without_visual_review(tmp_path):
    from app.api import missions
    from app.core import provider_runtime
    workspace(tmp_path,'<style>button{background:#eee1cf;border:1px solid #302519;border-radius:6px}a{text-underline-offset:4px}</style>')
    html=(tmp_path/'app/index.html').read_text()
    concept=(tmp_path/'docs/delivery-concept.md').read_text()
    actions=iter([
        {'action':'create_file','target':'app/index.html','payload':html},
        {'action':'create_file','target':'docs/delivery-concept.md','payload':concept},
    ])
    class CodingProviderFixture:
        def execute(self,model_id,prompt,**kwargs):
            output=json.dumps(next(actions,{'action':'finish','payload':'ready'}))
            return RoutingExecutionResult(model_id,model_id,'coding-fixture',output,1,0.0,True)
    observed=[]
    class ObservedRunner(AutonomousPatchRunner):
        def run(self,*args,**kwargs):
            result=super().run(*args,**kwargs)
            observed.append(result)
            return result
    record={'task':'Crie uma landing page HTML para Rosales Café.','_max_iterations':5,'models':[],'events':[]}
    with provider_server(json.dumps(REVISE)) as (url,requests), \
         patch.dict(missions._MISSIONS,{'visual-legacy':record}), \
         patch.object(missions,'OmniRouteAdapter',return_value=CodingProviderFixture()), \
         patch.object(missions,'AutonomousPatchRunner',ObservedRunner), \
         patch.object(provider_runtime,'build_visual_review_routing',return_value=(
             OpenAICompatibleAdapter(ProviderConfig('openrouter',url)),('vision-free',))):
        missions._run_mission('visual-legacy')
        assert record['status'] != 'completed', 'the old mission path bypassed the visual critic'
        state=observed[0].steps[0].loop_result.state
        assert state.metadata['delivery_review']['visual']=='revision_required'
        assert any('Reduce the mobile headline' in item for item in state.errors)
        assert len(requests)==1
