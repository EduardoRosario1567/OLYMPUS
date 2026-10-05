import unittest
from unittest.mock import patch
from olympus.routing.interfaces import RoutingHealth, RoutingModelInfo, ModelCapability
from olympus.routing.provider_fabric import ProviderRegistry, ProviderConfig, OpenAICompatibleAdapter

class FakeProvider:
    def __init__(self, provider, healthy=True, models=()): self.provider=provider; self.ok=healthy; self.models=models
    def health(self): return RoutingHealth(self.ok, self.provider, "healthy" if self.ok else "offline")
    def list_models(self): return [RoutingModelInfo(x,self.provider,[ModelCapability.CODIGO],True) for x in self.models]

class TestProviderFabric(unittest.TestCase):
    def test_health_aware_registry(self):
        reg=ProviderRegistry(); reg.register('a',FakeProvider('a',False),10); reg.register('b',FakeProvider('b',True),20)
        self.assertEqual(reg.healthy_ids(),('b',))
    def test_priority_is_stable(self):
        reg=ProviderRegistry(); reg.register('slow',FakeProvider('slow'),50); reg.register('fast',FakeProvider('fast'),10)
        self.assertEqual(reg.ids(),('fast','slow'))
    def test_model_route_keeps_model_and_provider_separate(self):
        reg=ProviderRegistry(); reg.register('p1',FakeProvider('p1',True,['qwen']),10); reg.register('p2',FakeProvider('p2',True,['glm']),20)
        self.assertEqual(reg.ranked_routes('qwen'),(('p1','qwen'),))
    def test_disabled_provider_is_not_healthy(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('x','http://127.0.0.1:1',enabled=False))
        self.assertFalse(adapter.health().healthy)

    def test_provider_requests_identify_olympus_for_edge_security(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('x','https://example.invalid'))
        headers=adapter._headers()
        self.assertEqual(headers['User-Agent'], 'OLYMPUS/2.6.2')
        self.assertEqual(headers['Accept'], 'application/json')

    def test_unexpected_tool_call_is_a_recoverable_model_failure(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        adapter._request=lambda *args, **kwargs: (400, {
            'error': '{"error":{"message":"Tool choice is none, but model called a tool",'
                     '"code":"tool_use_failed","failed_generation":"repo_browser.search_code"}}'
        })
        result=adapter.execute('openai/gpt-oss-120b','return JSON')
        self.assertFalse(result.success)
        self.assertEqual(result.status,'malformed_response')

    def test_failed_generation_tool_call_becomes_a_normal_action(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        adapter._request=lambda *args, **kwargs: (400, {
            'error': '{"error":{"message":"Tool choice is none, but model called a tool",'
                     '"code":"tool_use_failed","failed_generation":"{\\"name\\":'
                     ' \\"repo_browser.read_file\\", \\"arguments\\":'
                     ' {\\"path\\": \\"app/index.html\\"}}"}}'
        })
        result=adapter.execute('openai/gpt-oss-20b','return JSON')
        self.assertTrue(result.success)
        self.assertIn('repo_browser.read_file', result.output)
        self.assertEqual(result.metadata['protocol_recovered'],'failed_tool_generation')

    def test_empty_completion_is_a_recoverable_model_failure(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        adapter._request=lambda *args, **kwargs: (200, {
            'model':'model-a', 'choices':[{'message':{'content':'','tool_calls':[{}]}}]
        })
        result=adapter.execute('model-a','return JSON')
        self.assertFalse(result.success)
        self.assertEqual(result.status,'malformed_response')

    def test_successful_tool_call_without_content_becomes_textual_action(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        adapter._request=lambda *args, **kwargs: (200, {
            'model':'model-a',
            'choices':[{'message':{'content':'','tool_calls':[{
                'function':{'name':'repo_browser.search_code','arguments':'{"path":"app","query":"Olympus"}'},
            }]}}],
        })
        result=adapter.execute('model-a','return JSON')
        self.assertTrue(result.success)
        self.assertIn('repo_browser.search_code', result.output)

    @patch('olympus.routing.provider_fabric.time.sleep')
    def test_short_provider_rate_limit_waits_and_retries_same_model(self, sleep):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        responses=iter((
            (429, {'error':'Rate limit reached. Please try again in 1.5s.'}),
            (200, {'model':'qwen/qwen3-32b','choices':[{'message':{'content':'{"type":"finish"}'}}]}),
        ))
        adapter._request=lambda *args, **kwargs: next(responses)
        result=adapter.execute('qwen/qwen3-32b','return JSON')
        self.assertTrue(result.success)
        self.assertEqual(result.metadata['rate_limit_retries'],1)
        sleep.assert_called_once_with(1.75)

    @patch('olympus.routing.provider_fabric.time.sleep')
    def test_millisecond_provider_rate_limit_waits_and_retries(self, sleep):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        responses=iter((
            (429, {'error':'Rate limit reached. Please try again in 525ms.'}),
            (200, {'model':'compound-mini','choices':[{'message':{'content':'{"type":"finish"}'}}]}),
        ))
        adapter._request=lambda *args, **kwargs: next(responses)
        result=adapter.execute('compound-mini','return JSON')
        self.assertTrue(result.success)
        self.assertEqual(result.metadata['rate_limit_retries'],1)
        sleep.assert_called_once_with(0.775)

    def test_provider_repairs_max_tokens_limit_and_retries_same_model(self):
        adapter=OpenAICompatibleAdapter(ProviderConfig('groq','https://example.invalid'))
        payloads=[]
        responses=iter((
            (400, {'error':{'message':'`max_tokens` must be less than or equal to `4096`, the maximum value for `max_tokens` is less than the context window'}}),
            (200, {'model':'allam','choices':[{'message':{'content':'{"type":"finish"}'}}]}),
        ))
        def request(_method, _path, payload=None):
            payloads.append(dict(payload))
            return next(responses)
        adapter._request=request
        result=adapter.execute('allam','return JSON',max_tokens=8192)
        self.assertTrue(result.success)
        self.assertEqual(payloads[0]['max_tokens'],8192)
        self.assertEqual(payloads[1]['max_tokens'],4096)
        self.assertTrue(result.metadata['token_budget_repaired'])

if __name__ == '__main__': unittest.main()
