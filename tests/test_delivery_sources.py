import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.action_normalizer import normalize_action_data
from olympus.agent.executor import ActionExecutor
from olympus.agent.delivery_sources import DeliverySources
from olympus.skills.registry import SkillRegistry
from olympus.skills.resolver import SkillResolver
from olympus.agent.loop import AgentLoop
from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.state import AgentState
from olympus.agent.verifier import AgentVerifier
from olympus.agent.delivery_sources import _NoRedirect
from olympus.agent.planner import ModelPlanner


def commons(url='https://upload.wikimedia.org/wikipedia/commons/a/a1/Coffee.jpg', license='CC BY 4.0'):
    return {'query': {'pages': [{'title': 'File:Coffee.jpg', 'imageinfo': [{
        'url': url, 'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Coffee.jpg',
        'mime': 'image/jpeg', 'width': 1800, 'height': 1200,
        'extmetadata': {'LicenseShortName': {'value': license},
                        'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by/4.0/'},
                        'Artist': {'value': '<a href="x">Photographer</a>'},
                        'ImageDescription': {'value': 'Coffee cup'}}}] }]}}


class DeliverySourcesTests(unittest.TestCase):
    def test_action_can_be_normalized_and_executed(self):
        action = normalize_action_data({'type': 'research_sources', 'target': 'images', 'payload': {'query': 'coffee'}})
        with tempfile.TemporaryDirectory() as root, patch.object(DeliverySources, '_json', return_value=commons()):
            observation = ActionExecutor(root).execute(action)
        self.assertTrue(observation.success, observation.error)
        self.assertEqual(observation.output['results'][0]['author'], 'Photographer')
        self.assertEqual(observation.output['results'][0]['width'], 1800)
        self.assertFalse(observation.output['visual_reviewed'])

    def test_unknown_license_is_not_suggested(self):
        with patch.object(DeliverySources, '_json', return_value=commons(license='Unknown')):
            self.assertEqual(DeliverySources().search('images', {'query': 'coffee'})['results'], [])

    def test_untrusted_image_hosts_are_excluded(self):
        for url in ['http://upload.wikimedia.org/x.jpg', 'https://127.0.0.1/x.jpg',
                    'https://upload.wikimedia.org.evil.test/x.jpg',
                    'https://evil@upload.wikimedia.org/x.jpg', 'https://upload.wikimedia.org:8443/x.jpg']:
            with self.subTest(url=url), patch.object(DeliverySources, '_json', return_value=commons(url)):
                self.assertEqual(DeliverySources().search('images', {'query': 'coffee'})['results'], [])

    def test_queries_are_encoded_and_endpoint_is_fixed(self):
        with patch.object(DeliverySources, '_json', return_value=commons()) as fetch:
            DeliverySources().search('images', {'query': 'coffee & x=https://localhost'})
        url = fetch.call_args.args[0]
        self.assertTrue(url.startswith('https://commons.wikimedia.org/w/api.php?'))
        self.assertIn('%26', url)

    def test_context_separates_background_from_business_facts(self):
        data = {'query': {'pages': [{'pageid': 12, 'title': 'Café', 'extract': 'A coffeehouse serves coffee.'}]}}
        with patch.object(DeliverySources, '_json', return_value=data):
            output = DeliverySources().search('context', {'query': 'coffee', 'language': 'pt'})
        self.assertIn('business facts', output['usage'])
        self.assertEqual(output['results'][0]['source_url'], 'https://pt.wikipedia.org/?curid=12')

    def test_context_does_not_allow_arbitrary_domains(self):
        with self.assertRaises(ValueError):
            DeliverySources().search('context', {'query': 'coffee', 'language': 'localhost'})

    def test_network_failure_is_failed_observation(self):
        with tempfile.TemporaryDirectory() as root, patch.object(DeliverySources, '_json', side_effect=OSError('offline')):
            result = ActionExecutor(root).execute(AgentAction(ActionType.RESEARCH_SOURCES, 'images', {'query': 'coffee'}))
        self.assertFalse(result.success)
        self.assertNotIn('offline', result.error)

    def test_inspect_result_cannot_fabricate_browser_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            output = ActionExecutor(root).execute(AgentAction(ActionType.INSPECT_RESULT, payload={'browser_passed': True})).output
        self.assertEqual(output['verification'], 'model_statement_only')
        self.assertFalse(output['browser_verified'])

    def test_frontend_resolves_research_and_concept_contract(self):
        skills = SkillResolver(SkillRegistry()).resolve('site Rosales Café', required=('frontend',))
        self.assertIn('research', [s.id for s in skills])
        frontend = next(s for s in skills if s.id == 'frontend')
        self.assertIn('research_sources', frontend.allowed_actions)
        self.assertTrue(any('docs/delivery-concept.md' in line for line in frontend.guidance))

    def test_empty_queries_and_unknown_modes_fail_before_network(self):
        with patch.object(DeliverySources, '_json') as fetch:
            for mode, payload in [('images', {'query': ''}), ('url', {'query': 'coffee'}), ('images', {'query': 'x'*241})]:
                with self.assertRaises(ValueError):
                    DeliverySources().search(mode, payload)
        fetch.assert_not_called()

    def test_retrieved_sources_reach_next_planning_cycle(self):
        with tempfile.TemporaryDirectory() as root, patch.object(DeliverySources, '_json', return_value=commons()):
            observation = ActionExecutor(root).execute(AgentAction(ActionType.RESEARCH_SOURCES, 'images', {'query': 'coffee'}))
        state = AgentState(task='site', observations=(observation,))
        summary = json.loads(AgentLoop._state_summary(state))
        self.assertIn('Coffee.jpg', summary['recent_actions'][0]['output']['results'][0]['source_url'])

    def test_new_web_contract_requires_concept_before_finish(self):
        compiled = MissionCompiler().compile('Crie um site para Rosales Café')
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'app').mkdir()
            Path(root, 'app/index.html').write_text('<html><h1>Rosales</h1></html>')
            errors = AgentVerifier(root).verify_task_deliverable(compiled.instruction(), ('app/index.html',))
        self.assertTrue(any('delivery-concept.md' in error for error in errors))

    def test_transport_refuses_redirects(self):
        with self.assertRaises(ValueError):
            _NoRedirect().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/private')

    def test_transport_refuses_unlisted_endpoints(self):
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):
                DeliverySources()._json('https://example.test/api')
        opener.assert_not_called()

    def test_transport_limits_response_and_checks_content_type(self):
        for content_type, body in [('text/html', b'<html>'), ('application/json', b'x' * (DeliverySources.MAX_BYTES + 1))]:
            with self.subTest(content_type=content_type):
                headers = Message()
                headers['Content-Type'] = content_type
                response = unittest.mock.MagicMock()
                response.__enter__.return_value = response
                response.headers = headers
                response.read.return_value = body
                with patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value = response
                    with self.assertRaises(ValueError):
                        DeliverySources()._json('https://commons.wikimedia.org/w/api.php')

    def test_prompt_compaction_preserves_exact_source_urls(self):
        url = 'https://upload.wikimedia.org/wikipedia/commons/' + 'a' * 400 + '/Coffee.jpg'
        summary = {'recent_actions': [{'output': {'results': [{'image_url': url, 'description': 'x' * 2000}]}}],
                   'professional_skill_contract': {'guidance': ['y' * 280] * 12}}
        compact = json.loads(ModelPlanner._bounded_state_summary(json.dumps(summary), limit=1500))
        self.assertEqual(compact['recent_actions'][0]['output']['results'][0]['image_url'], url)


if __name__ == '__main__':
    unittest.main()
