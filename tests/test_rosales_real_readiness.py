import tempfile
import unittest
from pathlib import Path

from scripts.rosales_real_readiness import evaluate


class RosalesReadinessTests(unittest.TestCase):
    def test_real_mission_fails_closed_without_sandbox_attestation_and_provider_proof(self):
        result = evaluate()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("OS_SANDBOX_ATTESTATION_UNAVAILABLE", result["issues"])
        self.assertIn("LIVE_PROVIDER_INFERENCE_NOT_VERIFIED", result["issues"])
        self.assertEqual(result["real_model_calls"], 0)
        self.assertIs(result["generated_site"], False)

    def test_environment_variables_cannot_falsely_mark_the_mission_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "missions").mkdir()
            (root / "missions" / "rosales-cafe-acceptance.md").write_text("mission", encoding="utf-8")
            result = evaluate(root, {
                "DOCKER_HOST": "unix:///var/run/docker.sock",
                "OLYMPUS_OMNIROUTE_API_KEY": "synthetic-test-value",
                "OLYMPUS_SANDBOX_VERIFIED": "true",
            })
            self.assertEqual(result["status"], "BLOCKED")
            self.assertNotIn("MISSION_CONTRACT_MISSING", result["issues"])


if __name__ == "__main__":
    unittest.main()
