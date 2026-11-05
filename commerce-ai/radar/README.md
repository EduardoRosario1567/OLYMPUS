# OLYMPUS Commerce AI — Radar no GitHub

Versão experimental simplificada, sem arquivo ZIP. Compatível com Python 3.9+, sem pacotes adicionais e sem novos servidores. **Não é o ZIP v3 completo**; o conector Open Prices do pacote anterior não está incluído.

## Instalar ou atualizar e executar testes no Mac

Execute o bloco abaixo em um Terminal comum. Ele não abre processos residentes e **não apaga** o banco `radar.sqlite3`.

```bash
bash <<'RADAR'
set -e
BASE="$HOME/Projetos-IA/olympus-commerce-ai/radar-github"
URL="https://raw.githubusercontent.com/EduardoRosario1567/OLYMPUS/commerce-radar-v3/commerce-ai/radar"
mkdir -p "$BASE"
curl -fLsS --retry 2 "$URL/radar.py" -o "$BASE/radar.py.novo"
curl -fLsS --retry 2 "$URL/test_radar.py" -o "$BASE/test_radar.py.novo"
python3 -m py_compile "$BASE/radar.py.novo" "$BASE/test_radar.py.novo"
if [ -f "$BASE/radar.py" ]; then cp "$BASE/radar.py" "$BASE/radar.py.bak"; fi
mv "$BASE/radar.py.novo" "$BASE/radar.py"
mv "$BASE/test_radar.py.novo" "$BASE/test_radar.py"
(cd "$BASE" && python3 -m unittest -v test_radar)
python3 "$BASE/radar.py" --limite 20
open "$BASE/relatorio.html"
RADAR
```

A chamada externa à API depende do acesso de rede do Mac. Se indisponível, o programa mantém registros existentes e abre o relatório (que pode estar vazio). O resultado no GitHub não comprova ainda a consulta ao vivo.

## Dados e limitações

- Catálogo: Open Food Facts, produtos associados ao Brasil. Registro no catálogo **não** prova vendas, nível de demanda, preço ou estoque.
- Cotações: importadas pelo operador em CSV. Não são verificadas automaticamente.
- Cálculo: **margem de contribuição estimada**, não lucro líquido.
- Dados persistentes ficam em `radar.sqlite3` na pasta `radar-github`; atualização de código não remove nem migra bancos de outras versões.
- Sem credenciais, sem compras e sem anúncios automáticos.

## Importar cotações

Colunas obrigatórias: `codigo,preco,custo,frete,comissao,imposto,outros,url_preco,url_fornecedor,consultado_em`. Data ISO `AAAA-MM-DD`. Exemplo de execução: `python3 radar.py --sem-rede --csv cotacoes.csv`. O código deve constar no catálogo armazenado.

O ramo `commerce-radar-v3` é experimental. Nenhuma alteração na `main` do OLYMPUS.
