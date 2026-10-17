import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p3.prepare_upstream import Blocked
from p5.prepare_local_inference import overlay

SOURCE = """export async function POST(request) {
const { prompt, model = 'openai/gpt-oss-20b', context, isEdit = false } = await request.json();
const streamOptions = {model: modelProvider(actualModel), maxTokens: 8192,};\nconst message = {content: systemPrompt + ` Original generation instructions`};
// Add reasoning effort for GPT-5 models\n        if (isOpenAI) { streamOptions.experimental_providerMetadata = {}; }
                console.log('[generate-ai-code-stream] Groq service unavailable, falling back to GPT-4');
                streamOptions.model = openai('gpt-4-turbo');
                actualModel = 'gpt-4-turbo';
}"""

def sample(root,source=SOURCE):
    for name, content in {
        "LICENSE":"MIT License",
        "package.json":"{}",
        "package-lock.json":"{}",
        "app/api/generate-ai-code-stream/route.ts":source,
    }.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content)

class P5LocalOnlyTests(unittest.TestCase):
    def test_expected_pin_and_local_only_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sample(root)
            result=overlay(root,git_check=False)
            self.assertEqual(result["status"],"GUARDED_LOCAL_INFERENCE_CANDIDATE")
            content=(root/"app/api/generate-ai-code-stream/route.ts").read_text()
            self.assertIn("openai.chat(actualModel)",content)
            self.assertIn("OPENAI_P5" if False else "OLYMPUS_P5_LOCAL_ONLY",content)
            self.assertIn("1024",content)
            self.assertNotIn("openai('gpt-4-turbo')",content)
            guard=(root/"middleware.ts").read_text()
            self.assertIn("OLYMPUS_P5_GATE_TOKEN",guard)
            self.assertIn("request.method === 'POST'",guard)
            self.assertIn("OLYMPUS_P5_UNAUTHORIZED_OR_UNSAFE_ROUTE",guard)

    def test_missing_or_duplicate_source_signatures_are_blocked(self):
        for text in (SOURCE.replace("maxTokens: 8192,","maxTokens: 1024,"),
            SOURCE.replace("if (isOpenAI) {","if (isGoogle) {"),
            SOURCE.replace("openai('gpt-4-turbo')","openai('gpt-5')"),
            SOURCE.replace("model: modelProvider(actualModel),","model: fake(),")):
            with self.subTest(text=text[:55]),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);sample(root,text)
                with self.assertRaises(Blocked):
                    overlay(root,git_check=False)

    def test_no_host_network_or_external_paid_credentials_in_pilot(self):
        workflow=(ROOT/".github/workflows/open-lovable-p5-real-model.yml").read_text()
        self.assertIn("docker network create --internal",workflow)
        self.assertIn("docker network disconnect bridge",workflow)
        self.assertIn("--network",workflow)
        self.assertIn("OLYMPUS_P5_LOCAL_ONLY=1",workflow)
        self.assertNotIn("ANTHROPIC_API_KEY=",workflow)
        self.assertNotIn("GROQ_API_KEY=",workflow)
        self.assertNotIn("AI_GATEWAY_API_KEY=",workflow)

    def test_node_probe_is_syntactically_valid(self):
        subprocess.run(["node","--check",str(ROOT/"p5/qualify_real_stream.mjs")],check=True)

if __name__=="__main__":
    unittest.main()
