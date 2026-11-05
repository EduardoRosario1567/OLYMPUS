# OLYMPUS — Contrato de capacidades, inspirado nas funções públicas Helium 10

Revisão 2026-11-05. Complemento a `ENGENHARIA_REVERSA_HELIUM10_BR.md`.

## Descoberta documental decisiva

Helium 10 publica em https://github.com/helium10/Helium10-MCP uma descrição pública dos grupos de ferramentas:
- `search_products` (Black Box)
- `search_amazon_keywords`
- `get_keywords_by_asin` / `get_keywords_by_keyword` (Cerebro)
- `get_listing_details` / `get_listing_score` / `compare_listings`
- `get_competitor_overview`
- `get_keywords_rank_history`
- `get_product_profit_and_loss_summary`
- `get_sales_velocity` (dados de conta/estoque, não vendas de todo concorrente)

**NÃO É OPEN SOURCE.** Licença proprietária em https://github.com/helium10/Helium10-MCP/blob/main/LICENSE proíbe obras derivadas, alterações e redistribuição sem consentimento. Não copiar nenhum código, manifesto ou skill. A documentação funcional é referência de capacidades, não licença de uso de dados ou clonagem de código.

Helium10 Black Box/Cerebro suportam Amazon Brasil segundo https://kb.helium10.com/hc/en-us/articles/360036359334-Which-Tools-Are-Supported-in-Which-Markets. A documentação atual do MCP lista países sem Brasil: não presumir que MCP seja fonte de dados BR.

## Contrato proprietário OLYMPUS, desenvolvido independentemente

Função | Entrada | Saída mínima | Pré-condição
--- | --- | --- | ---
`discover_products` | marketplace BR, categoria, intervalo de preço, filtros observáveis | ASIN, título, preço, marca, categoria, data, URL | Fonte legítima de catálogo autorizado
`analyze_competition` | conjunto ASINs e período | número observado de ofertas, preços, avaliações, anúncios patrocinados se evidenciados | Amostra documentada
`reverse_keywords` | ASIN + conjunto de observações autorizadas | termo, fonte, posição, tipo orgânico/patrocinado, data | Não inferir rank se ausente
`product_history` | ASIN + snapshots com fonte | série temporal documentada, lacunas | Min 2 snapshots
`financial_scenarios` | preço, custo, taxas, frete, marketing, devoluções | contribuição cenário baixo/base/alto, não lucro líquido | Custos com premissas explícitas
`decision_dossier` | evidências de todas as fontes | condições para investigar, rejeitar ou aguardar dados | Sem campos inventados

Campos desconhecidos devem ser `null` e manter `evidence_status=unavailable`, nunca `0`.

## Fonte primária para desenvolver, sem Helium 10

Amazon Selling Partner API Catalog Items v2022-04-01:
https://developer-docs.amazon/sp-api/docs/search-catalog-items

Requer autorização Selling Partner + papel Product Listing; buscar por keyword/ASIN/identificador. Não equivale a acesso livre a BSR, vendas de concorrentes, demanda ou custo.

Fonte complementar potencial: https://github.com/dgtlmoon/changedetection.io (Apache-2.0). Para páginas cujos termos permitam monitoramento; não suporta contornar bloqueios e pode ser pesado no Mac 2012.

## Teste decisivo seguinte

1. Verificar se há acesso autorizado à SP-API e permissões necessárias, sem exigir compras de ferramentas terceirizadas.
2. Construir conector Amazon BR com ASIN, marca, categoria, fonte, URL e data; sem promover simulação.
3. Aplicar filtros Black Box aos registros Amazon reais.
4. Analisar concorrência apenas com métricas disponíveis (Xray).
5. Enriquecer palavras-chave apenas quando houver evidência de ranking real (Cerebro).
6. Só então pedir ao OLYMPUS AI para interpretar os dossiês.

Critério de êxito P0: >=10 ASINs brasileiros com URL e dados de catálogo rastreáveis + operação de filtro reproduzível, sem reivindicar vendas não observadas.

Manter em ramo experimental; não instalar assinaturas Helium10 e não reproduzir sua interface nem código.
