import unittest
from olympus.routing.model_lab import BenchmarkCategory, ModelLab


class TestModelLab(unittest.TestCase):
    def test_records_core_metrics(self):
        lab = ModelLab()
        lab.record(BenchmarkCategory.ACTION_PROTOCOL, "groq", "qwen", success=True, latency_ms=100, action_compliant=True)
        lab.record(BenchmarkCategory.ACTION_PROTOCOL, "groq", "qwen", success=False, latency_ms=300, timeout=True, action_compliant=False)
        row = lab.metrics(BenchmarkCategory.ACTION_PROTOCOL, "groq", "qwen")
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.success_rate, 0.5)
        self.assertEqual(row.timeout_rate, 0.5)
        self.assertEqual(row.action_compliance, 0.5)
        self.assertEqual(row.avg_latency_ms, 200)
        self.assertEqual(row.p95_latency_ms, 300)

    def test_sparse_evidence_is_shrunk_toward_neutral(self):
        lab = ModelLab()
        lab.record(BenchmarkCategory.CODE_GENERATION, "a", "m", success=True, action_compliant=True)
        score = lab.observed_score(BenchmarkCategory.CODE_GENERATION, "a", "m")
        self.assertGreater(score, 0.5)
        self.assertLess(score, 0.8)

    def test_mature_evidence_can_outrank_one_lucky_sample(self):
        lab = ModelLab()
        lab.record(BenchmarkCategory.EXISTING_EDIT, "lucky", "m", success=True, action_compliant=True)
        for _ in range(25):
            lab.record(BenchmarkCategory.EXISTING_EDIT, "proven", "m", success=True, action_compliant=True, latency_ms=100)
        ranked = lab.rank(BenchmarkCategory.EXISTING_EDIT, [
            {"provider":"lucky","model":"m","capability_score":0.8,"health_score":1,"cost_score":1},
            {"provider":"proven","model":"m","capability_score":0.8,"health_score":1,"cost_score":1},
        ])
        self.assertEqual(ranked[0]["provider"], "proven")

    def test_same_model_is_scored_per_provider_route(self):
        lab = ModelLab()
        for _ in range(10):
            lab.record(BenchmarkCategory.ACTION_PROTOCOL, "good", "qwen", success=True, action_compliant=True)
            lab.record(BenchmarkCategory.ACTION_PROTOCOL, "bad", "qwen", success=False, timeout=True, action_compliant=False)
        good = lab.observed_score(BenchmarkCategory.ACTION_PROTOCOL, "good", "qwen")
        bad = lab.observed_score(BenchmarkCategory.ACTION_PROTOCOL, "bad", "qwen")
        self.assertGreater(good, bad)

    def test_repair_metric_is_independent(self):
        lab = ModelLab()
        lab.record(BenchmarkCategory.TEST_REPAIR, "p", "m", success=True, repair_success=True)
        lab.record(BenchmarkCategory.TEST_REPAIR, "p", "m", success=False, repair_success=False)
        self.assertEqual(lab.metrics(BenchmarkCategory.TEST_REPAIR, "p", "m").repair_success, 0.5)


if __name__ == "__main__":
    unittest.main()
