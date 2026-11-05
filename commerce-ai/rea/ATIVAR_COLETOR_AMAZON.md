# Amazon BR — ativação autorizada do coletor OLYMPUS

Situação: implementado, não autenticado; não possui credenciais cadastradas pelo assistente.

## Referências oficiais

- SP-API Catalog Items: https://developer-docs.amazon/sp-api/lang-pt_BR/docs/catalog-items-api
- searchCatalogItems: https://developer-docs.amazon/sp-api/lang-pt_BR/reference/searchcatalogitems
- Autorização: https://developer-docs.amazon/sp-api/docs/connecting-to-the-selling-partner-api
- Requer papel Product Listing e autorização adequada da conta de vendedor.
- LWA access token de curta duração obtido por refresh token; nunca colocar tokens no GitHub, ChatGPT ou logs.

## Arquivos

- `coletor_amazon_spapi.py` pesquisa o catálogo oficial BR apenas com credenciais válidas.
- `amazon_catalogo_br.py` normaliza itens para CSV importável.
- `atualizador_commerce.py` chama o coletor no início de cada execução agendada; falta de credenciais é registrada como `nao conectado`, e os painéis continuam.
- `test_coletor_amazon_spapi.py` contém testes offline com dados inventados e não valida conexão real.

## Ativação (uma vez, no Mac)

Após registrar um aplicativo SP-API próprio, obter client_id, client_secret, refresh_token autorizados da Amazon:

```bash
mkdir -p "$HOME/.config/olympus-commerce"
chmod 700 "$HOME/.config/olympus-commerce"
umask 077
nano "$HOME/.config/olympus-commerce/amazon_spapi.json"
```

Conteúdo JSON (substituir marcadores por valores próprios; nunca compartilhar):

```json
{
  "client_id": "SUBSTITUIR",
  "client_secret": "SUBSTITUIR",
  "refresh_token": "SUBSTITUIR",
  "keywords": ["pilha alcalina", "lampada led", "detergente"],
  "pages_per_keyword": 1
}
```

Após salvar:

```bash
chmod 600 "$HOME/.config/olympus-commerce/amazon_spapi.json"
cd "$HOME/Projetos-IA/olympus-commerce-ai/radar-github"
python3 coletor_amazon_spapi.py --verificar
python3 atualizador_commerce.py --executar
python3 atualizador_commerce.py --status
```

O coletor só consulta APIs com token válido, retorna dados na pasta `entrada_csv`, e o atualizador importa os arquivos. O launchd existente continua executando a rotina no login e a cada seis horas.

## Limitações

- API de catálogo não entrega preços atuais, número de avaliações ou vendas de concorrentes nesse conector; os campos permanecem vazios.
- Na ausência de elegibilidade/credenciais: sistema permanece com a base histórica e informa status `nao conectado`.
- Para preços/concorrência exigir outra fonte licenciada/autorizada e contratos específicos.
- Não mudar títulos/preços históricos pela data de execução; cada registro guarda data de origem.
- Fonte Amazon BR com identificador `A2Q3Y263D00KWC`.
- Sem Docker, scraping, navegador permanente ou assinatura Helium 10.
