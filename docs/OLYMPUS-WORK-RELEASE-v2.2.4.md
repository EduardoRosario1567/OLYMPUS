# OLYMPUS Professional v2.2.4 — Redundância operacional

## Objetivo

Permitir que o usuário componha uma sequência de provedores independentes e
saiba quais conexões realmente conseguem gerar uma resposta antes de iniciar
uma missão importante.

## Entregas

- O botão `Testar` executa uma geração mínima real, em vez de validar somente o
  acesso ao catálogo de modelos.
- A Central distingue conta conectada de provedor pronto para executar.
- Cada provedor ativo pode ser incluído ou removido do fallback automático.
- Groq, OpenRouter, Cerebras, Gemini, Mistral, OpenAI e Ollama são elegíveis
  quando configurados e autorizados pelo usuário.
- Provedores potencialmente pagos exigem confirmação visual antes de entrar na
  sequência automática.
- O catálogo vivo filtra modelos de áudio e segurança, ordena modelos adequados
  para código e continua tentando as demais rotas após uma falha técnica.

## Segurança financeira e operacional

O Olympus não compra créditos, não altera planos e não inclui silenciosamente
fontes potencialmente pagas. A preferência explícita fica no armazenamento
local sem registrar credenciais. Toda ação de modelo continua sujeita às
políticas de segurança e à verificação da entrega.

## Critério de conclusão

A versão é aprovada após testes de preferências, catálogo vivo, inferência real,
fallback, fluxo completo da landing page e regressão no pacote extraído.
