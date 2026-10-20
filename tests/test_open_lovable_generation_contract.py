import subprocess
import unittest
from pathlib import Path


class StagingGenerationContractTests(unittest.TestCase):
    def test_patched_generation_state_budget_and_completion(self):
        root = Path(__file__).resolve().parents[1]
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { patchGeneration } = require('./integrations/open_lovable_upstream/apply-generation-contract.cjs');
const original = fs.readFileSync('tests/fixtures/open_lovable_generation_contract.ts', 'utf8');
const patched = patchGeneration(original);
const stateBlock = patched.slice(0, patched.indexOf('const options'));
const state = { conversationState: { context: { messages: ['old mission'] } } };
new Function('global', 'isEdit', stateBlock)(state, false);
assert.deepEqual(state.conversationState.context.messages, []);
state.conversationState.context.messages.push('current mission');
new Function('global', 'isEdit', stateBlock)(state, true);
assert.deepEqual(state.conversationState.context.messages, ['current mission']);
assert.ok(!patched.includes('maxTokens:'));
const budget = patched.match(/maxOutputTokens: (.*), \/\/ Bounded/)[1];
assert.equal(new Function('model', 'return ' + budget)('openai/gpt-oss-120b'), 16384);
assert.equal(new Function('model', 'return ' + budget)('other-model'), 8192);
const profile = patched.slice(patched.indexOf('        // Honor an explicit'), patched.indexOf('        // Make streaming API'));
const runProfile = new Function('prompt','isEdit',"let systemPrompt='stock', fullPrompt='context';" + profile + ';return {systemPrompt,fullPrompt}');
for (const prompt of ['Use plain CSS, no Tailwind','Sem Tailwind','without tailwind']) {
  const result = runProfile(prompt,false);
  assert.match(result.systemPrompt,/semantic class names and plain CSS/);
  assert.equal(result.fullPrompt,prompt);
}
assert.equal(runProfile('Use Tailwind',false).systemPrompt,'stock');
assert.equal(runProfile('sem Tailwind',true).fullPrompt,'context');
const finish = patched.slice(patched.indexOf('        const generationFinishReason'), patched.indexOf('        // Function to extract packages'));
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const runFinish = new AsyncFunction('result', 'model', 'console', finish);
const messages = [];
const quiet = {log(...args){messages.push(args)}};
(async () => {
  await runFinish({finishReason: Promise.resolve('stop'),usage:Promise.resolve({inputTokens:200,outputTokens:500})}, 'test', quiet);
  assert.equal(JSON.parse(messages[0][1]).inputTokens,200);
  assert.equal(JSON.parse(messages[0][1]).outputTokens,500);
  await assert.rejects(runFinish({finishReason:Promise.resolve('length')}, 'test', quiet), /without a complete response: length/);
  await assert.rejects(runFinish({finishReason:Promise.resolve('content-filter')}, 'test', quiet), /content-filter/);
  const gate = patched.slice(patched.indexOf('        // Recovery must'), patched.indexOf('        // Send completion'));
  const check = new Function('generatedCode',gate);
  check('<file path="src/App.jsx">export default App;</file>');
  assert.throws(()=>check('<file path="src/App.jsx">unfinished'), /incomplete file blocks/);
  assert.throws(()=>check('no source'), /incomplete file blocks/);
  assert.throws(()=>patchGeneration(patched), /refusing patch/);
  assert.throws(()=>patchGeneration(original.replace('maxTokens: 8192','maxTokens: 8000')), /refusing patch/);
  assert.throws(()=>patchGeneration(original + '\nif (!global.conversationState) {'), /refusing patch/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', script], cwd=root, text=True,
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
