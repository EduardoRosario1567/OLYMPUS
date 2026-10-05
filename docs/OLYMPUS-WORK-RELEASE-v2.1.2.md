# OLYMPUS Professional v2.1.2 — failover de protocolo e retorno do preview

## Correção principal

- Respostas Groq `400 tool_use_failed` agora são classificadas como incompatibilidade técnica recuperável (`malformed_response`).
- Uma resposta HTTP bem-sucedida, mas sem ação textual, também aciona o próximo modelo em vez de encerrar a missão.
- A sequência Groq prioriza `llama-3.3-70b-versatile` e `llama-3.1-8b-instant` antes dos modelos GPT-OSS.
- Erros de modelo inexistente ou não permitido seguem como indisponibilidade recuperável.

## Experiência do projeto

- O ambiente de preview agora mostra o botão explícito **Voltar à conversa**.
- A tecla `Esc` fecha o ambiente, preservando a confirmação de descarte quando há edição não salva.
- A marca usa a versão `2.1.2` do cache em todas as superfícies principais.

## Verificação

- Regressão automatizada completa: 720 testes aprovados, 14 ignorados.
- Teste integrado cobre a troca entre dois modelos do mesmo provedor após `tool_use_failed`.
- Teste integrado existente cobre missão autônoma até a criação e verificação do artefato após failover entre provedores.

## Limite do teste local

O pacote não contém credenciais. A confirmação final contra a conta Groq do operador deve ser executada no Mac depois de preservar `backend/.env` e `.olympus/cloud` durante a atualização.
