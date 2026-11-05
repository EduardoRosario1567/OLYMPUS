# OLYMPUS Commerce AI — Radar distribuído pelo GitHub

Versão simplificada de distribuição, independente do arquivo ZIP v3 anterior. Python 3.9+, sem pacotes externos, sem novos servidores e sem usar o Ollama Cloud.

## Instalar ou atualizar no Mac

```bash
BASE="$HOME/Projetos-IA/olympus-commerce-ai/radar-github"
mkdir -p "$BASE"
URL="https://raw.githubusercontent.com/EduardoRosario1567/OLYMPUS/commerce-radar-v3/commerce-ai/radar/radar.py"
curl -fLsS --retry 2 "$URL" -o "$BASE/radar.py.novo" && \
python3 -m py_compile "$BASE/radar.py.novo" && \
mv "$BASE/radar.py.novo" "$BASE/radar.py" && \
python3 "$BASE/radar.py" --limite 20 && \
open "$BASE/relatorio.html"
```

Dados persistentes: `radar.sqlite3` no diretório `radar-github`; a atualização apenas troca o script, não o banco. Não importa bancos das versões anteriores automaticamente.

O catálogo Open Food Facts comprova registro de produto associado ao Brasil, **não** vendas, demanda, fornecedor ou preço. Cotação CSV é informada pelo operador e suas URLs não são verificadas automaticamente. Se a API estiver indisponível, o relatório pode ficar vazio.

## Cotações CSV

Colunas obrigatórias: `codigo,preco,custo,frete,comissao,imposto,outros,url_preco,url_fornecedor,consultado_em`. Preços e custos devem ser preenchidos pelo operador, com URLs e data ISO `AAAA-MM-DD`. Para importar: `python3 radar.py --sem-rede --csv cotacoes.csv`. O produto precisa constar do catálogo local para aparecer no relatório.

**Ramo experimental**, sem alterações na branch `main` do OLYMPUS.
