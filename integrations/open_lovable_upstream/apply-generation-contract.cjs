// Pinned staging snapshot only. This does not provide tenant isolation.
const fs = require('node:fs');
const target = '/app/app/api/generate-ai-code-stream/route.ts';

function patchGeneration(source) {
  let text = source;
  function once(from, to) {
    const at = text.indexOf(from);
    if (at < 0 || text.indexOf(from, at + 1) !== -1)
      throw new Error('Pinned upstream generation contract changed; refusing patch');
    text = text.replace(from, to);
  }
  // A complete new generation must not inherit previous mission requests.
  // Edits retain the existing conversation behavior.
  once('if (!global.conversationState) {',
       'if (!isEdit || !global.conversationState) {');
  once('maxTokens: 8192, // Reduce to ensure completion',
       "maxOutputTokens: model.startsWith('openai/gpt-oss-') ? 16384 : 8192, // Bounded staging budget (AI SDK 5)");
  once('        // Make streaming API call with appropriate provider',
       `        // Honor an explicit plain-CSS request instead of the stock Tailwind-only system prompt.
        if (!isEdit && /(?:sem|no|without)\\s+tailwind/i.test(prompt)) {
          systemPrompt = 'Generate complete React/Vite source in closed <file path="...">...</file> blocks. '
            + 'Follow the user file list and content exactly. Use semantic class names and plain CSS in src/index.css; '
            + 'do not use Tailwind, new packages, invented business facts or unrequested configuration files. '
            + 'Use one main and one h1, working anchor links, responsive layouts, accessible contrast and focus styles. '
            + 'Preserve the requested entrypoints, CSS imports and metadata. Output complete concise source only.';
          fullPrompt = prompt;
        }

        // Make streaming API call with appropriate provider`);
  once('        // Function to extract packages from import statements',
       `        const generationFinishReason = await result?.finishReason;
        const generationUsage = await result?.usage;
        console.log('OLYMPUS_GENERATION_FINISH', JSON.stringify({
          model, finishReason: generationFinishReason,
          inputTokens: generationUsage?.inputTokens,
          outputTokens: generationUsage?.outputTokens
        }));
        if (generationFinishReason === 'length' || generationFinishReason === 'content-filter') {
          throw new Error('Generation ended without a complete response: ' + generationFinishReason);
        }

        // Function to extract packages from import statements`);
  once('        // Send completion with packages info',
       `        // Recovery must not claim completion with missing file boundaries.
        const finalOpenFiles = (generatedCode.match(/<file\\s+path="/g) || []).length;
        const finalCloseFiles = (generatedCode.match(/<\\/file>/g) || []).length;
        if (!finalOpenFiles || finalOpenFiles !== finalCloseFiles) {
          throw new Error('Generation contains incomplete file blocks');
        }

        // Send completion with packages info`);
  once("          generatedCode,\n          explanation,",
       "          generatedCode,\n          finishReason: generationFinishReason,\n          usage: generationUsage,\n          explanation,");
  return text;
}

if (require.main === module) {
  const text = patchGeneration(fs.readFileSync(target, 'utf8'));
  fs.writeFileSync(target, text, 'utf8');
  console.log('OLYMPUS staging generation contract installed');
}
module.exports = { patchGeneration };
