# OLYMPUS Professional v2.2.3 — Catálogo vivo de modelos

## Origem

O diagnóstico real no Mac confirmou que a chave Groq estava válida e que o
fallback percorreu todas as rotas, mas duas identificações fixas já não existiam
na conta. Os modelos GPT-OSS restantes responderam por chamadas de ferramenta
em vez do campo textual esperado.

## Correções

- As missões consultam o catálogo real do provedor e usam somente modelos que
  estão disponíveis naquela conta no momento da execução.
- Modelos de áudio, voz e proteção são excluídos das missões de construção.
- Modelos de código e chat são classificados por adequação, sem depender de
  nomes antigos gravados no pacote.
- Chamadas de ferramenta devolvidas em respostas HTTP 200 são convertidas para
  o protocolo interno de ações.
- A ação segura presente em `failed_generation` da Groq é recuperada mesmo
  quando a API responde `tool_use_failed` em HTTP 400.
- Toda ação recuperada continua passando por normalização, política de
  autonomia, restrição de workspace e verificação antes de ser executada.

## Critério de conclusão

A versão é aprovada após testes do catálogo dinâmico, recuperação de protocolo,
fallback integral, landing page determinística e regressão completa no pacote
extraído.
