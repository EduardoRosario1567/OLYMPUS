# OLYMPUS Commerce AI — Engenharia reversa funcional Helium 10
Data: 2026-11-05. Mercado-alvo inicial: Amazon Brasil (amazon.com.br).

## Decisão de arquitetura

Reproduzir **capacidades e fluxos de trabalho**, não código fechado, banco de dados exclusivo ou identidade visual. Foco: Black Box -> Xray -> Cerebro -> Decisão financeira. Congelar coletores de notícias como eixo principal. Google Trends RSS e Open Food Facts ficam opcionais e secundários.

## Evidências oficiais

- Black Box Products/Advanced Filters: https://kb.helium10.com/hc/en-us/articles/360034015153-Tutorial-Navigating-the-Black-Box-Dashboard
- Black Box Product Overview (2026): https://kb.helium10.com/hc/en-us/articles/6710274045339-Black-Box-Product-Tab-Overview
- Xray: https://www.helium10.com/tools/product-research/xray/
- Cerebro: https://www.helium10.com/tools/keyword-research/cerebro/
- Magnet incorporado ao Cerebro em janeiro de 2026: https://kb.helium10.com/hc/en-us/articles/44262552100891-Magnet-Has-Been-Merged-Into-Cerebro-Everything-You-Need-to-Know
- Suporte a Amazon Brasil: https://kb.helium10.com/hc/en-us/articles/360036359334-Which-Tools-Are-Supported-in-Which-Markets
- Ferramentas MCP documentadas: https://kb.helium10.com/hc/en-us/articles/51580564409883-Getting-Started-with-Helium-10-MCP

## Produto-alvo A: OLYMPUS Black Box BR

Entrada: marketplace=Amazon BR, categoria, faixa de preço, tamanho/peso, reviews, concorrência, demanda e faturamento MENSURADOS/ESTIMADOS.

Filtro de cada produto:
- id externo (ASIN), nome, categoria, marca, vendedor, preço/moeda, observação temporal
- origem/endereço de evidência, licença/termos e forma autorizada de obtenção
- reviews, nota, BSR, idade de listing, quantidade de vendedores, peso/dimensões: apenas se disponíveis
- unidades vendidas no mês e receita: estimativas com método, calibração e faixa de incerteza ou nulo
- estoque, taxas, comissões, frete, custo do fornecedor, ads: somente quando documentados
- código da fonte, instante da coleta, qualidade da evidência

Filtros só podem operar sobre campos efetivamente disponíveis. Falta de campo => NAO DISPONIVEL, nunca zero, e nunca substituição por dado fabricado.

Resultado: shortlist de produtos com trilha de auditoria, filtros reproduzíveis e indicação de lacunas.

## Produto-alvo B: OLYMPUS Xray BR

Entrada: termo/categoria ou lista de ASINs com dados autorizados.
Resultado: panorama dos produtos concorrentes com preço, avaliações, posicionamento e anúncios patrocinados quando observáveis; concentração e dispersão; comparação do período atual com histórico.

Métricas:
- mediana de preços e dispersão, n produtos da amostra, dados ausentes
- saturação aproximada por avaliações e frequência de marcas, SEM alegar participação de mercado
- qualquer previsão de vendas requer calibração por categoria e benchmark externo com metodologia pública
- margem de contribuição estimada: preço menos custo conhecido, comissão, imposto, frete, devoluções e ads, conforme disponíveis
- intervalo de confiança só quando método estatístico justificar.

## Produto-alvo C: OLYMPUS Cerebro BR

Entrada: ASIN/concorrentes.
Resultado: palavras-chave e posições orgânicas/patrocinadas observadas por fonte permitida; sobreposição de ASINs; gaps de título e anúncio; frequência e tendências de buscas (somente quando a fonte mede busca Amazon, não Google Trends).

Não confundir Google Trends com volume de buscas da Amazon.
Não apresentar rank de palavra-chave sem evidência de ranking real.

## Motor de decisões

Regra de bloqueio de promessas financeiras:
1. Sem preço comercial atual ou custo de aquisição => rentabilidade nao determinada.
2. Sem volume de vendas com método calibrado => faturamento nao determinado.
3. Sem concorrência observável => saturação nao determinada.
4. Se evidência falhar, informar o que falta e indicar próxima ação concreta.
5. OLYMPUS DecisionEngine / Ollama pode explicar e priorizar somente evidências estruturadas, sem preencher os campos ausentes.
6. Judge estrutural não equivale a validação factual.

Mecanismo de classificação por prontidão:
- DESCOBERTO: ASIN/termo + fonte
- PESQUISAVEL: preço + características + concorrentes verificáveis
- ANALISAVEL: custos documentados + histórico
- AVALIADO: cenário financeiro + risco + confiança dos dados
- PRONTO PARA TESTE: decisão humana sobre fornecedor, regras, margem e exposição.

## Reutilização e custos

- Manter OLYMPUS, DecisionEngine, Adapter, SQLite, motor de margem.
- Considerar changedetection.io Apache-2.0 para monitoramento de páginas em que coleta automatizada seja autorizada; não exigir Docker no Mac antigo.
- APIs oficiais de Amazon/marketplaces quando houver acesso legítimo e elegibilidade; OAuth não equivale automaticamente a acesso a vendas dos outros vendedores.
- Catálogo Open Food Facts é secundário, não motor de produtos Amazon.
- Não pagar assinaturas Helium 10, Keepa ou terceirizadas.
- Não fazer scraping contrário às restrições de fonte, nem contornar paywall/bloqueio.

## Critérios de aceitação e provas

P0: um único dataset de ASINs Amazon BR com pelo menos 10 itens, URLs e preços atuais originados de fonte permitida, com fonte/data verificáveis; sem falsos dados.
P1: réplica funcional dos filtros Black Box sobre esses dados reais e testes de ausência de campos.
P2: diagnóstico Xray das mesmas ofertas: competição, preços e dados que faltam, sem inventar vendas.
P3: lacunas de palavras-chave com ranking real somente onde disponível.
P4: fornecedores + cotação + cenários de contribuição (não lucro líquido) com auditoria.

A ordem **não** é criar outra tela ou servidor: identificar a fonte de ASINs e validar a permissão, criar adaptador de dados e então filtrar/ranquear.
