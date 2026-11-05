# OLYMPUS Commerce AI — Radar + Tendências BR

Ramo experimental `commerce-radar-v3`, isolado da `main`. Compatível com Python 3.9+. Sem novos servidores, sem modelo de IA, sem pacotes externos. Não contém todos os arquivos do antigo ZIP v3.

## Atualizar e testar com um único comando

```bash
bash <<'OLYMPUS_RADAR'
set -e
BASE="$HOME/Projetos-IA/olympus-commerce-ai/radar-github"
RAW="https://raw.githubusercontent.com/EduardoRosario1567/OLYMPUS/commerce-radar-v3/commerce-ai/radar"
mkdir -p "$BASE"
for F in radar.py tendencias.py test_radar.py test_tendencias.py; do
  curl -fLsS --retry 2 --max-time 40 "$RAW/$F" -o "$BASE/$F.novo"
  python3 -m py_compile "$BASE/$F.novo"
done
for F in radar.py tendencias.py test_radar.py test_tendencias.py; do
  if [ -f "$BASE/$F" ]; then cp "$BASE/$F" "$BASE/$F.bak"; fi
  mv "$BASE/$F.novo" "$BASE/$F"
done
(cd "$BASE" && python3 -m unittest -v test_radar test_tendencias)
python3 "$BASE/radar.py" --limite 20
python3 "$BASE/tendencias.py" --limite 25
open "$BASE/relatorio.html" "$BASE/tendencias.html"
OLYMPUS_RADAR
```

O processo encerra após gerar os relatórios; as portas já existentes não são afetadas. Bancos persistem em `radar.sqlite3`, sem apagar as versões anteriores.

## Fontes e limitações

- Catálogo: Open Food Facts, registros associados ao Brasil. Não comprova disponibilidade, venda ou demanda.
- Tendências: RSS público Google Trends (`https://trends.google.com/trending/rss?geo=BR`). Termos frequentemente incluem esportes, notícias e entretenimento. Os volumes são rótulos aproximados de buscas, não vendas. A fonte pode mudar, limitar ou bloquear solicitações.
- Mercado Livre: conexão oficial para tendências exige autorização OAuth; não está habilitada automaticamente.
- Cotação CSV: dados inseridos pelo operador. URLs não são verificadas e a margem de contribuição não equivale a lucro líquido.
- Ainda não existe classificação automática confiável de nichos, precificação de atacado ou previsão de vendas.

Os arquivos `tendencias.csv` e `tendencias.html` são gerados no Mac. Em falha de rede, o sistema utiliza somente dados previamente armazenados e informa o problema, sem gerar valores fictícios.
