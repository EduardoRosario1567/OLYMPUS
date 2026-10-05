# OLYMPUS Professional v2.2.2 — Resiliência com provedores reais

## Origem

O primeiro teste real da v2.2.1 confirmou a inicialização e o fallback, mas duas
rotas devolveram ações fora do contrato. A missão foi protegida corretamente,
porém não chegou à construção da página.

## Correções

- Cada modelo selecionado após um erro técnico recebe um orçamento de iterações
  novo, sem perder arquivos nem observações já produzidos.
- O planejador solicita até 8.192 tokens de saída para evitar que páginas HTML
  completas sejam truncadas pelo limite padrão do provedor.
- Planos enviados como arrays são consumidos com segurança, uma ação por ciclo.
- Nomes de ferramentas com namespace, como `repo_browser.search_code`, são
  normalizados para o protocolo interno.
- Em missões web, conteúdo válido sem destino explícito é direcionado para
  `app/index.html`; o verificador ainda precisa aprovar e pode exigir reparos.
- `llama-3.3-70b-versatile` passa a ser a primeira alternativa direta na Groq,
  seguido pelas demais rotas gratuitas configuradas.

## Segurança

O Olympus continua executando uma única ação por ciclo, mesmo quando um modelo
devolve uma lista inteira. Destinos continuam restritos ao workspace, ações
destrutivas continuam bloqueadas e nenhum resultado é publicado sem passar pelo
verificador.

## Critério de conclusão

A versão é aprovada após regressão integral, ensaio de landing page, validação do
pacote extraído e repetição do teste real no Mac.
