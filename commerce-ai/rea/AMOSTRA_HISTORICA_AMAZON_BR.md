# Primeiros ASINs reais — OLYMPUS Black Box Brasil

Fonte secundária: [Nolyn, Mais vendidos Amazon Brasil — outubro de 2026](https://www.nolyn.ai/pt/case-studies/mais-vendidos-amazon-brasil).
O levantamento descreve observação de 21/10/2026, 04:20–04:22 UTC, para dez categorias e contém links individuais de produtos Amazon.com.br. Verificados dez destinos de links associados ao relatório (algumas páginas Amazon indisponíveis para leitura direta; **o link aponta o ASIN, não uma validação independente do preço**).

Arquivo `amostra_publica_amazon_br_20261021.csv`:
- 10 produtos Amazon Brasil, ASIN/URL por destino do link citado na publicação e título, categoria, preço, quantidade de avaliações e nota **reportados pela fonte secundária**;
- preço de **21/10/2026**, não preço atual, e não oferta comercial validada em 05/11/2026;
- `bsr` vazio: posição na lista de mais vendidos não é automaticamente BSR de produto, e não há evidência uniforme;
- `vendas_mensais_estimadas`, `receita_mensal_estimada`, `vendedores`, `vendedor` e `metodo_estimativa` vazios;
- não transformar os selos de “compras no mês” relatados na fonte em números exatos nem em previsão de vendas;
- não calcular lucro sem preço/custo do fornecedor, taxas e logística;
- amostra **histórica e não necessariamente representativa**, obtida para validar a pesquisa interna sem login nem extração indevida de APIs.

## Como importar com arquivo já baixado

```bash
python3 blackbox_br.py --csv amostra_publica_amazon_br_20261021.csv
```

Executar novamente não duplica a mesma observação no SQLite. Para filtrar:

```bash
python3 blackbox_br.py --preco-min 20 --preco-max 60
```

A saída HTML/JSON apresenta preços reportados pela fonte e não deve ser tratada como dados atuais. Nenhum crawler automático ou conector SP-API autorizado está ligado.

## Eixo de engenharia futura

1. Criar conexão de catálogo legítima/autenticada com API oficial, quando elegível; não confundir com estimativa de vendas.
2. Armazenar snapshots com timestamps, reputação da fonte, origem primária/secundária e validade de observação; avisar preço desatualizado.
3. Ter campo explícito de `ranking_em_categoria` e `selo_compras_min` quando auditados, **separados** de `bsr` e unidades efetivas.
4. Adicionar filtros multicritério que de fato funcionem sobre campos observados.
5. Validar funcionamento no Mac e abrir relatórios. Não reproduzir código visual proprietário do Helium 10.

Não fazer download nem upload do arquivo bruto de 891 KB com scripts/cookies/analytics do Helium 10 para o repositório público.
