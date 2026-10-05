# OLYMPUS — matriz integrada de fontes de inteligência

**Data:** 2026-09-17  
**Status:** PASS

## Cenário

Foi executada uma missão única com dez etapas e dez artefatos de um mesmo
projeto. Cada etapa foi encaminhada a uma fonte diferente através do adaptador
que o Olympus realmente registra no `ProviderRegistry`.

Fontes atravessadas:

`OmniRoute · Free Claude Code · OpenRouter · Groq · Cerebras · Ollama · Gemini · Mistral · Z.AI · Cloudflare Workers AI`

O cenário usou um servidor HTTP local compatível com os protocolos reais. Não
foram usadas respostas internas do agente, créditos ou credenciais externas.

## Falhas deliberadas e regressões

- OmniRoute respondeu HTTP 429; o controle de missão transferiu o checkpoint
  para o FCC e a etapa continuou.
- Groq rejeitou o teto de saída; o adaptador genérico reduziu `max_tokens` e
  repetiu a chamada antes de continuar.
- Z.AI respondeu `tool_use_failed` com uma ação recuperável; o adaptador
  recuperou a ação sem perder a etapa.
- As demais fontes entregaram através de seus endpoints `/chat/completions`;
  o FCC foi exercitado no endpoint `/responses`.

## Resultado

```text
status: PASS
mission_status: completed
fontes saudáveis e catalogadas: 10/10
etapas executadas: 10/10
artefatos presentes: 10/10
publicação, versionamento, preview e ZIP: PASS
```

O mesmo teste está registrado na suíte em
`tests/test_provider_matrix_e2e.py` e é executado pelo
`VALIDAR-NUCLEO.command`.

A regressão final, já com as dependências do backend instaladas, terminou com
808 testes aprovados e 4 integrações externas condicionais.

## Limite honesto da evidência

Esta matriz comprova que o núcleo consegue conversar com cada protocolo
configurado, interpretar a resposta, aplicar ações, continuar após falhas e
entregar o projeto. A disponibilidade comercial, cota, modelo e autenticação
de cada conta ainda precisam ser confirmadas no Mac com as chaves reais; uma
simulação local não deve ser apresentada como essa confirmação externa.
