# REA — Evidência Black Box Helium 10 (05/11/2026)

**Origem:** captura REA do usuário, id `ev_813882c5a4489e4449234024a65787e4b2aff844bd2327ef797097169d17ef84`; navegador Chromium 156; operação `capture_browser_scenario`; URL `https://www.helium10.com/tools/product-research/black-box/`; domínio final idêntico ao inicial; dois passos completos; último DOM capturado. Original de 891 KB mantido fora deste repositório por prudência.

## Fatos observados no DOM público

- Título da página: **Amazon FBA Product Finder Tool | Black Box by Helium 10**.
- Widget visível no DOM, classe `WIDGET-ATP`, título **Discover Profitable Products**.
- Widget: campo **Marketplace** com domínios Amazon, campo **Category** com diversas categorias, botões com IDs `WIDGET-ATP__search` e `WIDGET-ATP__clear`.
- Widget: cabeçalhos de saída **Product**, **Estimate Monthly Sales** e **Estimated Montly Revenue** (grafia original), mas **nenhuma execução de pesquisa ou registro de produto observado**.
- O widget exibe mensagem sobre **5 pesquisas restantes**, que pode ser apenas uma mensagem do demonstrador: não garante franquia efetiva.
- Elementos de marketing/documentação: filtros de preço/margem/limites operacionais; promessa de **mais de 20 filtros**; comparação de categorias por número de avaliações e densidade em títulos; análise de catálogos de marcas/vendedores; histórico de BSR, vendas, preços e sazonalidade; favoritos e listas exportáveis.
- A página pública lista funções Xray, Cerebro, Keyword Tracker, Profits, entre outras, no menu. Não significa que foram investigadas.
- A página menciona coleta de registros da Amazon e afirma tamanho e precisão de base própria; essas declarações são **alegações comerciais, não medições independentes**.

## Conclusões de engenharia

- O primeiro fluxo observável é selecionar marketplace/categoria → pesquisar → examinar métricas → salvar/exportar shortlist.
- **Não foram observados** endpoints de dados da ferramenta autenticada, modelos de estimação de vendas, fórmulas de ranking, pesos dos filtros, dados reais de ASINs, execução de uma pesquisa ou resultados testados.
- Esta coleta mostra uma **página institucional com widget público**, não a aplicação interna Black Box.
- `confidence=observed` valida a captura dos artefatos requisitados, não as promessas de marketing e nem o algoritmo privado.
- Construir conector Amazon BR com ASIN + fonte permitida; importar dados reais; filtrar por preço, categoria, reviews e BSR apenas se presentes; exigir metodologia para valores estimados; organizar shortlist.
- Não copiar HTML, scripts, identidade visual ou bases proprietárias; não tentar contornar mecanismos de acesso.

## Implementação experimental independente

O módulo `blackbox_br.py` foi desenvolvido neste trabalho em Python 3.9+, sem bibliotecas externas. Ele aceita CSV **de fonte autorizada**, valida ASIN/marketplace/URLs/data/valores, armazena em tabela SQLite separada de `produtos` Open Food Facts, filtra e gera HTML/JSON com trilha de evidências.

**Validação fora do Mac:** 10 testes unitários passando, incluindo rejeição de estimativa sem método, de fonte não Amazon, de preços em moeda errada, exclusão de campos nulos, armazenamento SQLite e escape de HTML. **Não validado no Mac do usuário** e ainda sem fonte de ASINs real instalada. Banco vazio é relatado como zero produtos, sem inventar oportunidade.

## Próximos critérios de aceite

1. Disponibilizar no OLYMPUS o importador e filtro independente, isolado do núcleo.
2. Obter ao menos 10 ASINs reais via fonte Amazon BR permitida, ou registrar bloqueio de acesso e elegibilidade em vez de fabricar resultados.
3. Testar no Mac; só então afirmar Black Box BR funcional com dados.
4. Investigar fluxos Xray e Cerebro pelo REA com a mesma metodologia baseada em evidências.
