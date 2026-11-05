# OLYMPUS Commerce AI — Programa REA: Engenharia reversa funcional do Helium 10
Data: 2026-11-05
Referências oficiais: https://github.com/morluto/rea | https://rea.tools/
Licença do REA: MIT. Licenças e termos das ferramentas *analisadas* são independentes.

## Meta executável

Reconstruir de forma independente as funcionalidades comerciais do Helium 10 para Amazon Brasil, usando o REA como instrumento de investigação **apenas sobre interfaces, dados, arquivos e comportamentos que tenhamos direito de analisar**. Não copiar código-fonte proprietário, marcas, visual protegido, bancos de dados fechados, funcionalidades sujeitas a autenticação não autorizada ou recursos de assinatura sem acesso legítimo.

### O que REA faz e não faz

- Faz: CLI/MCP de análise de arquivos JS/Electron e binários autorizados, registros HAR obtidos legitimamente, traces funcionais e evidências.
- Não faz: disponibilizar a base do Helium 10, prever vendas sem amostra/calibração, remover paywall, conceder autorização de acesso, substituir provedores de IA ou garantir uma cópia integral de SaaS fechado.
- Limite operacional: sem artefato/autorização para examinar aplicações proprietárias do Helium 10, a investigação ficará nas demonstrações públicas, documentação funcional e comportamento acessível nos termos aplicáveis. A cobertura e as hipóteses serão declaradas.
- Objetivo de zero custo: usar somente componentes gratuitos e APIs com elegibilidade e permissões adequadas; não comprar assinaturas.
- No Mac 2012: Node 26.x conhecido, npm e Claude Code existentes; o Gemma Cloud está temporariamente bloqueado (HTTP 429, franquia mensal). O REA pode rodar via CLI sem inferência, mas sua integração com agente precisa de modelo acessível.

## Inventário de referência

| Função | Entrada real | Campos/algoritmos de interesse | Artefato de auditoria | Nosso módulo |
|---|---|---|---|---|
| Black Box | marketplace BR, preço, categoria, review, receita estimada | filtros, ordenação, persistência, tratamento de campos ausentes | capturas autorizadas, docs, casos de uso e comparação | `discover_products` |
| Xray | busca/lista ASINs | preço, número de vendedores, review, BSR, anúncios; estimativas explicitamente rotuladas | casos com entrada/saída e fonte | `analyze_competition` |
| Cerebro | ASINs e consultas de palavras-chave | rank orgânico/patrocinado, termos e volume observado | evidência de posição e data; não inferir volume Amazon com Google Trends | `reverse_keywords` |
| Keyword tracking | ASIN + palavra + data | evolução e lacunas | snapshots com data | `keyword_history` |
| Financial | ASIN + custos documentados | taxa, frete, impostos, ads e devoluções | cálculo reproduzível em testes | `financial_scenarios` |
| Supplier | item + fornecedor | cotação, volume mínimo, prazo e documentação | URLs e datas verificáveis | `supplier_quotes` |

## Etapas REA (uma funcionalidade por vez)

### R0 — Preparação e escopo de autorização
1. Verificar `node -v`, `npm -v`, `uname -m` e espaço de disco.
2. Verificar origem do REA: `morluto/rea`, `rea.tools`, pacote npm `rea-agents`.
3. Verificar licença MIT do REA, licença e termos dos artefatos analisados.
4. Configurar o REA somente com confirmação explícita do operador; `npx rea-agents setup` altera configuração de agentes após mostrar plano e solicitar aprovação.
5. NÃO instalar Hopper, Ghidra, IDA ou Docker automaticamente. Para a investigação inicial de interfaces públicas não são pré-requisitos.
6. Guardar evidências, logs e saídas em pasta local ignorada pelo Git; redigir cookies/tokens e dados pessoais.

### R1 — Black Box público
- Coletar/documentar parâmetros, defaults, intervalos, ordenações, colunas, sinais e estados de erro observáveis em demonstrações/guias públicos.
- Descrever a lógica possível e separar observação de hipótese.
- Construir casos de teste com dados fictícios claramente identificados para filtros; produção somente quando houver produtos Amazon BR com fonte legítima.
- Escrever relatório com links da documentação/capturas autorizadas e grau de certeza.

### R2 — Xray
- Listar comparação observável de itens no resultado de busca: preço, categoria, reviews, BSR etc.
- Distinguir métricas capturadas de estimativas internas não reproduzíveis.
- Desenvolver nosso agregador com preço/avaliação observável e `null` nos campos sem acesso.
- Testes contra amostra do próprio usuário ou API legítima.

### R3 — Cerebro
- Documentar entradas ASINs, relatórios e métricas disponíveis publicamente.
- Construir contrato próprio para ranking de keywords, mas só preencher dados com observações autorizadas.
- Testar ausência de ranking como `NAO DETERMINADO`.

### R4 — Preço e lucro
- Reusar a implementação financeira do Commerce AI.
- Documentar todos os pressupostos, não chamar margem de contribuição de lucro líquido.
- Realizar testes parametrizados com frete, comissão, impostos, marketing e devolução.

### R5 — Produto comercial
- Uma única interface e uma única rotina de atualização; reaproveitar `~/Projetos-IA/olympus-commerce-ai`.
- Integrar resultados com `OLYMPUS-TESTE` somente por adaptador; não alterar núcleo.
- Quando Ollama Cloud retornar, avaliar dossiês com IA, mas não criar números ausentes.
- Evidências reais e decisões devem ser diferenciadas dos dados de demonstração.

## Saídas exigidas da investigação

- `docs/rea/01_ESCOPO_AUTORIZADO.md`: fontes, licenças, permissões e exclusões.
- `docs/rea/02_BLACK_BOX.md`: funcionalidades observadas e protótipo independente.
- `docs/rea/03_XRAY.md`: saídas, evidências e regras.
- `docs/rea/04_CEREBRO.md`: keywords e medições autorizadas.
- `docs/rea/05_MOTOR_FINANCEIRO.md`: fórmulas, premissas e testes.
- `docs/rea/06_DADOS_EVIDENCIAS.md`: matriz de fontes Amazon BR e disponibilidade.
- `docs/rea/07_TESTES_ACEITACAO.md`: testes executados e lacunas não resolvidas.
- `docs/rea/08_ARQUITETURA.md`: decisões e integrações com OLYMPUS.

Cada achado: recurso, entrada, saída, fonte URL/arquivo, data, nível de certeza (OBSERVADO / DOCUMENTADO / INFERIDO / NAO VALIDADO), método e restrição.

## Critérios de aceite

1. Pelo menos 10 produtos Amazon Brasil coletados com ASIN/preço/URL/data por meio autorizado, quando houver acesso às fontes; caso não, resultado explícito de bloqueio e conector pronto.
2. Black Box funcional e testado contra os dados permitidos, com filtros e reprodução de queries.
3. Xray exibe concorrência e qualidade dos dados sem alegar vendas de terceiros não observadas.
4. Cerebro identifica gap por keywords com evidência real, ou retorna `NAO DETERMINADO`.
5. Financial recusa recomendação sem custos de fornecedor confiáveis.
6. Nenhuma alteração sem necessidade no núcleo `main`; nenhuma assinatura paga, Docker ou serviços residentes adicionais.
7. Todas as análises incluem fonte, data, versão e status.

## Próxima execução real no Mac

Usar o `rea_bootstrap.sh` desta pasta para checar pré-requisitos; se houver aprovação, executar a instalação oficial do REA. O REA será ferramenta de investigação, **não** nova fonte proprietária de dados.

Não declarar engenharia reversa completa enquanto os seis fluxos e suas verificações não estiverem efetivamente concluídos.
