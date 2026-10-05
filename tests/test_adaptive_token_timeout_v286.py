
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from olympus.agent.planner import ModelPlanner

class FakeRouter:
    def execute(self,*a,**k):
        raise AssertionError('not needed')

class AdaptiveBudgetsTests(unittest.TestCase):
    def test_web_gets_large_output_budget(self):
        p=ModelPlanner(FakeRouter(),'openrouter/cohere/north-mini-code:free')
        self.assertEqual(p._output_token_budget('Crie uma landing page responsiva'),8192)
    def test_code_gets_medium_large_budget(self):
        p=ModelPlanner(FakeRouter(),'openrouter/model:free')
        self.assertEqual(p._output_token_budget('Corrija o código Python'),6144)
    def test_simple_file_gets_small_budget(self):
        p=ModelPlanner(FakeRouter(),'openrouter/model:free')
        self.assertEqual(p._output_token_budget('Crie um arquivo txt'),2048)
    def test_known_qwen_cap_wins(self):
        p=ModelPlanner(FakeRouter(),'openrouter/qwen/qwen3-coder:free')
        self.assertEqual(p._output_token_budget('Crie uma landing page'),768)

class AdaptiveTimeoutSourceTests(unittest.TestCase):
    def test_cloud_runtime_policy_has_adaptive_timeout(self):
        src=(Path(__file__).parents[1]/'backend/app/api/cloud_runtime.py').read_text()
        self.assertIn('execution_policy["model_timeout_seconds"] = _adaptive_model_timeout(task)',src)
        self.assertIn('return 90',src)
        self.assertIn('mission_timeout = max(20, min(180, mission_timeout))',src)
    def test_start_default_is_90(self):
        src=(Path(__file__).parents[1]/'start_olympus.command').read_text()
        self.assertIn('OLYMPUS_MODEL_TIMEOUT="${OLYMPUS_MODEL_TIMEOUT:-90}"',src)

if __name__=='__main__': unittest.main()
