# Contrato seguro de exportação Open Lovable → OLYMPUS

Este diretório é uma **proposta de patch aplicável a um fork do Open Lovable**, não é um endpoint publicado nem está ativado no Railway. Copiar o arquivo \`app/api/olympus-export/route.ts\` para o upstream dedicado somente após auditar sua compatibilidade com o SDK do sandbox ativo.

O Open Lovable original cria \`global.activeSandboxProvider\` em \`create-ai-sandbox-v2\`, mas as rotas \`create-zip\` e \`get-sandbox-files\` dependem de \`global.activeSandbox\`. Por isso o adapter não deve considerá-las uma exportação íntegra.

## Contrato

- POST \`/api/olympus-export\` em rede privada, \`X-Olympus-Bridge-Token\` (segredo gerado aleatoriamente, >=32 bytes e injetado exclusivamente por cofre).
- Corpo: \`{"sandboxId":"sandbox-id-autêntico"}\`.
- Resposta: \`{"success":true,"sandboxId":"...","files":[{"path":"src/App.jsx","content":"...","sha256":"..."}],"sha256":"hash-do-manifesto"}\`.
- Falha fechada em sandbox trocado, caminhos suspeitos, symlinks ou arquivos binários; exportação limitada por tamanho.
- Hash do manifesto: concatenação na ordem lexicográfica de caminho UTF-8 + byte NUL + SHA256 binário de cada conteúdo.

**Limite de segurança:** o código upstream ainda mantém estado global por processo. A verificação de identidade da exportação não torna o sistema multiusuário, não cria sessões isoladas nem impede mudanças por outros endpoints. **Produção permanece bloqueada.** Requer um serviço dedicado por missão ou refatoração real do upstream com sessão por tenant, token, sandboxes, locks distribuídos e isolamento testado.

**Próximos gates:** implantar fork em staging, checar autenticação e consistência de snapshot, testes de concorrência, E2B real com geração de Rosales Café, Playwright independente no artefato exportado, revisão de fontes/licenças de imagens, limites de custos e replay/idempotência.
