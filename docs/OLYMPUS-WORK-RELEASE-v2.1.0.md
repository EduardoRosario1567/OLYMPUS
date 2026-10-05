# OLYMPUS Professional v2.1.0 — failover real entre provedores

## Resultado

O runtime de missões usa a mesma malha de provedores exibida pelo Olympus.
`openrouter/free` continua sendo a rota gratuita primária pelo OmniRoute. Se
ela falhar tecnicamente ou esgotar a cota diária, a execução preserva o estado
e muda automaticamente para uma rota independente configurada.

Ordem padrão:

1. OpenRouter Free Router (via OmniRoute);
2. Groq: GPT OSS 120B e GPT OSS 20B;
3. Cerebras: Qwen 3.8 27B e GPT OSS 120B.

Uma cota diária, credencial inválida ou bloqueio de faturamento inutiliza as
demais tentativas do mesmo provedor naquela missão. Um timeout isolado ainda
permite testar o próximo modelo dele. A interface não chama repetições da
mesma conta de “outra IA”.

## Segurança e custo

- Nenhuma chave está incluída no código ou no pacote.
- Groq e Cerebras só entram na seleção quando sua chave existe localmente.
- `configure_ai.command` grava apenas `backend/.env`, de forma atômica e com
  permissão `0600`; os caracteres digitados não aparecem no Terminal.
- O Olympus não compra créditos nem ativa planos. O proprietário deve manter
  cada conta no plano gratuito e acompanhar os limites definidos pelo provedor.
- O arquivo `backend/.env` existente é preservado nas atualizações.

## Limite verificável

Sem ao menos uma credencial independente, não existe failover real fora do
OpenRouter. Nesse caso, uma cota diária esgotada encerra uma única tentativa
com diagnóstico correto, sem repetir falsamente a mesma rota três vezes.
