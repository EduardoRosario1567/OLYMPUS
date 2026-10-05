# OLYMPUS Professional v2.0.8 — classificação e cobertura de rota

## Evidência do Mac

Backend `2.0.7` saudável e OmniRoute com 177 modelos. A missão profissional de
landing page foi bloqueada antes da chamada ao modelo porque a expressão
`trabalho manual` acionou por engano a palavra-chave `manual`, classificando a
tarefa como documentação.

## Correção

- Intenção explícita de construir site, landing page, interface, aplicativo,
  dashboard, tela ou componente tem prioridade sobre palavras incidentais de
  documentação e revisão.
- A detecção usa limites de palavras para evitar correspondências acidentais.
- A missão exata usada no Mac agora é classificada como `codigo` e seleciona a
  rota `openrouter/openrouter/free`.
- A rota gratuita também cobre texto, respostas, revisão e documentação
  legítima, evitando bloqueio por ausência de modelo nessas categorias.
- Geração nativa de imagem não foi declarada como suportada porque o agente
  atual ainda não possui esse executor.
