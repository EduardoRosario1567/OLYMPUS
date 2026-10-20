# Rosales Café — qualificação real do Groq (2026-10-19)

## Escopo
Prova isolada do modelo de geração HTML/CSS para a missão piloto Rosales Café, usando Railway Function de execução única, sem publicar domínio, sem acessar organização administrativa e sem executar código produzido pelo modelo.

## Evidência observada
- Chave Groq existente referenciada em serviço privado do Railway, sem copiar valor para o repositório ou logs.
- Consulta autenticada `GET /openai/v1/models`: HTTP 200. Entre os modelos disponíveis constam `openai/gpt-oss-20b` e `openai/gpt-oss-120b`.
- A primeira tentativa com `llama-3.3-70b-versatile` retornou HTTP 404; esse modelo não apareceu no catálogo da chave.
- Geração real `POST /openai/v1/chat/completions` com `openai/gpt-oss-20b`, JSON mode e limite de saída: **HTTP 200**.
- Saída em duas strings `html` e `css`, respectivamente **1.522 bytes** e **954 bytes**.
- Verificações iniciais na função: **4 seções**, **4 links internos**, links apontando para IDs existentes, sem os recursos remotos/executáveis proibidos por seu validador local.
- Consumo retornado pelo provedor: **322 tokens de entrada** e **829 de saída**.
- Política de reinício da função: `NEVER`. A variável `OLYMPUS_QA_RUN_ONCE` foi desligada após cada prova.
- O OLYMPUS Cloud backend recebeu referência Railway à chave Groq e modelo `openai/gpt-oss-20b`, mas `OLYMPUS_ROSALES_AI_PILOT=0` e a execução geral de missões continuam **bloqueadas**.

## Limites da prova
A saída validada pela função foi efêmera e **não foi** salva como projeto na organização do usuário. O teste foi do provedor isolado, não do fluxo autenticado de missões do OLYMPUS. A verificação inicial em TypeScript não substitui o validador Python rigoroso, Playwright real, inspeção de fontes nem verificação de qualidade visual. Não declarar missão concluída.

## Gates seguintes
1. Executar fluxo autenticado completo no backend com organização efêmera e provedor Groq real, sem usar credenciais do usuário.
2. Guardar os bytes exatos do HTML/CSS produzido e executar o validador estrito, preview e Playwright independente em desktop e iPhone.
3. Revisar falhas, custos e uso dos modelos. Manter isolamento por organização e limites de tentativas.
4. Somente depois liberar uma missão-piloto administrativa, permanecendo o motor genérico bloqueado enquanto o upstream Open Lovable não tiver isolamento.


## Prova com arquivo real e Chromium independente
- Nova geração `openai/gpt-oss-120b` no Railway isolado: HTTP 200, **2.784 bytes HTML**, **2.330 bytes CSS**, nove links internos. Uso: **384 tokens de entrada / 1.706 de saída**.
- SHA256 exato: `index.html = 6d18a1a53551b3975aa6ab0b6e53d03eb8169983d18e01da730f3bcbc2240e1a`; `style.css = fc8bbd369e87f31891f963d5a87c8511c5332754347ee9290d032122ea0dae80`.
- Os arquivos foram recuperados da saída GZIP/Base64 do serviço Railway e submetidos ao Chromium com o conteúdo carregado em contexto local isolado, sem rede externa. O navegador deste ambiente bloqueou os esquemas `file://` e `127.0.0.1`; por isso a avaliação usou `set_content` com **os mesmos bytes de HTML/CSS**, injetando o CSS no documento de teste. Isso **não prova** hospedagem/HTTP dos arquivos originais.
- Resultado do navegador para **390 × 844 (iPhone)** e **1440 × 900 (desktop)**: navegação para `#conceito` OK, CSS renderizado, sem transbordamento horizontal, sem erros de página, sem recursos remotos.
- **REPROVADO em conteúdo comercial:** saída inventou produtores sustentáveis, notas de degustação de chocolate/frutas vermelhas, cardápio, baristas treinados, Wi-Fi e um estabelecimento físico não confirmados. Não publicar nem promover este HTML como site final.
- Implementado gate conservador no validador Python: todo fragmento visível da página gerada deve pertencer à cópia previamente aprovada em `olympus/cloud/project_templates.py`. Bloqueia texto novo não fundamentado, além de conteúdo textual injetado via CSS, mantendo liberdade de layout HTML/CSS. A integração continua **desativada** em Railway.
- A versão original aprovada do site estático do usuário foi preservada. Nenhum arquivo de projeto pessoal foi sobrescrito.
