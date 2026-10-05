# OLYMPUS Professional v2.1.3 — rotas reais e controle de quota

## Diagnóstico confirmado no Mac

- A conta Groq disponibiliza `qwen/qwen3-32b`, `openai/gpt-oss-20b` e `openai/gpt-oss-120b`.
- Os antigos modelos Llama configurados retornam `model_not_found` nessa conta.
- Os modelos GPT-OSS atingem o limite compartilhado de tokens por minuto quando as tentativas são feitas em sequência imediata.
- A chave Cerebras está saudável, mas a inferência exige pagamento.

## Correções

- `qwen/qwen3-32b` agora é a primeira rota Groq.
- Somente modelos confirmados pela conta são usados na configuração padrão.
- Limites Groq com janela curta aguardam o tempo informado pelo provedor e repetem o mesmo modelo até duas vezes.
- O contexto do planejador foi reduzido para até 6.000 caracteres de estado e 6.000 caracteres de arquivos relevantes.
- Cerebras tornou-se opt-in por `OLYMPUS_ENABLE_METERED_PROVIDERS=true`, inclusive para instalações antigas cuja lista ainda contém `groq,cerebras`.

## Verificação

- 723 testes aprovados; 14 ignorados.
- Testes cobrem espera e repetição do mesmo modelo, orçamento do prompt, seleção do Qwen e exclusão padrão da Cerebras.
