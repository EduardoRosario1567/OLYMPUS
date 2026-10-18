// Staging-only patch for upstream 806b8072f28afea11fa2b028cac1449eff74c511.
// Groq actually exposes IDs 'openai/gpt-oss-*', but vanilla Open Lovable
// mistakenly sends them to the OpenAI provider (which has no configured key).
const fs = require('node:fs');
const path = '/app/app/api/generate-ai-code-stream/route.ts';
let text = fs.readFileSync(path, 'utf8');
function replaceOnce(from, to) {
  const i = text.indexOf(from);
  if (i < 0 || text.indexOf(from, i + 1) !== -1)
    throw new Error('Open Lovable upstream changed; model routing patch refused');
  text = text.replace(from, to);
}
replaceOnce(
  "const isOpenAI = model.startsWith('openai/');",
  "const isGroqOss = model.startsWith('openai/gpt-oss-');\n        const isOpenAI = model.startsWith('openai/') && !isGroqOss;"
);
replaceOnce(
  "if (model.includes('gpt') || model.includes('openai')) {\n                  completionClient = openai;",
  "if (model.startsWith('openai/gpt-oss-')) {\n                  completionClient = groq;\n                } else if (model.includes('gpt') || model.includes('openai')) {\n                  completionClient = openai;"
);
replaceOnce(
  "} else if (model.includes('openai')) {\n                  completionModelName = model.replace('openai/', '');",
  "} else if (model.startsWith('openai/gpt-oss-')) {\n                  completionModelName = model;\n                } else if (model.includes('openai')) {\n                  completionModelName = model.replace('openai/', '');"
);
fs.writeFileSync(path, text, 'utf8');
console.log('OLYMPUS model routing patch: Groq gpt-oss IDs routed to Groq');
