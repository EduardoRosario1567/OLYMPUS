#!/usr/bin/env python3
"""OLYMPUS Black Box BR: painel local de produtos observados. Python 3.9+, sem servidor."""
import argparse
import datetime as dt
import html
import json
import pathlib
import sqlite3
from decimal import Decimal, InvalidOperation

BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "radar.sqlite3"

def money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            return None
        return "R$ " + f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, TypeError):
        return None

def load(db):
    if not db.exists():
        return [], "Banco ainda nao encontrado"
    con = sqlite3.connect(str(db))
    try:
        table = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blackbox_amazon_br'").fetchone()
        if not table:
            return [], "Tabela Black Box ainda nao criada"
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute("""
            SELECT marketplace, asin, titulo, categoria, marca, preco, moeda,
                   avaliacoes, nota, bsr, vendas_mensais_estimadas,
                   receita_mensal_estimada, data_observacao, url, fonte
            FROM blackbox_amazon_br
            WHERE marketplace='amazon.com.br'
            ORDER BY data_observacao DESC, titulo
        """)]
        unique = {}
        for row in rows:
            unique.setdefault(row["asin"], row)
        return list(unique.values()), None
    finally:
        con.close()

def build(rows, message=None):
    categories = sorted({r.get("categoria") or "Nao informada" for r in rows})
    def e(v):
        return html.escape(str(v or ""), quote=True)
    def observed(r):
        date = r.get("data_observacao") or ""
        try:
            age = (dt.date.today() - dt.date.fromisoformat(date)).days
            if age < 0:
                return "Data futura: verificar"
            if age > 7:
                return "Historico: " + date
            return "Registrado: " + date
        except ValueError:
            return "Data nao validada"
    cards = []
    for r in rows:
        price = money(r.get("preco"))
        url = str(r.get("url") or "")
        valid = url.startswith("https://www.amazon.com.br/") or url.startswith("https://amazon.com.br/")
        link = ('<a href="' + e(url) + '" target="_blank" rel="noopener noreferrer">Ver produto na Amazon</a>') if valid else "URL nao validada"
        review = r.get("avaliacoes") or "N/D"
        rating = r.get("nota") or "N/D"
        source = str(r.get("fonte") or "Nao informada")
        attr = ' data-title="' + e((r.get("titulo") or "") + " " + (r.get("marca") or "") + " " + (r.get("asin") or "")) + '"'
        attr += ' data-category="' + e(r.get("categoria") or "Nao informada") + '"'
        attr += ' data-price="' + e(r.get("preco") or "") + '"'
        cards.append(
            '<article class="item"' + attr + '>'
            '<div class="top"><span class="category">' + e(r.get("categoria") or "Nao informada") +
            '</span><span class="age">' + e(observed(r)) + '</span></div>'
            '<h2>' + e(r.get("titulo") or "Titulo indisponivel") + '</h2>'
            '<div class="identity">' + e(r.get("marca") or "Marca N/D") + ' · ASIN ' + e(r.get("asin")) + '</div>'
            '<div class="metrics"><div><span>Preco reportado</span><strong>' + e(price or "N/D") +
            '</strong></div><div><span>Avaliacoes</span><strong>' + e(review) +
            '</strong></div><div><span>Nota</span><strong>' + e(rating) +
            '</strong></div></div>'
            '<div class="unknown">Vendas mensais: ' + e(r.get("vendas_mensais_estimadas") or "N/D") +
            ' · Receita mensal: ' + e(r.get("receita_mensal_estimada") or "N/D") + '</div>'
            '<div class="bottom">' + link + '<details><summary>Origem e cautelas</summary><p>' +
            e(source) + '</p><p>Preco historico da fonte; disponibilidade e preco atual nao confirmados.</p></details></div>'
            '</article>'
        )
    options = ''.join('<option value="' + e(category) + '">' + e(category) + '</option>' for category in categories)
    warning = e(message or "Precos de fontes historicas nao constituem ofertas atuais. Valores N/D nao equivalem a zero.")
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>OLYMPUS | Black Box Brasil</title><style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#0c172b;color:#edf4ff}
main{max-width:1220px;margin:auto;padding:28px 22px}
h1{font-size:clamp(24px,4vw,34px);margin:0 0 8px}p{line-height:1.5}
header p{color:#a9bdd5;margin:0 0 23px}
.notice{padding:13px 15px;background:#152a45;border-left:3px solid #66b1ff;border-radius:6px;color:#c9d9e9}
.controls{display:grid;grid-template-columns:minmax(180px,2fr) minmax(150px,1fr) minmax(130px,1fr);gap:12px;margin:22px 0}
label{display:flex;flex-direction:column;gap:6px;color:#b9cce3;font-size:13px}
input,select{font:inherit;color:#fff;background:#1a2a42;border:1px solid #476381;padding:12px;border-radius:8px;width:100%}
.status{color:#b7c9db;margin:14px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.item{background:#15233a;border:1px solid #2c4666;border-radius:12px;padding:19px;min-width:0}
.top{display:flex;gap:8px;align-items:flex-start;justify-content:space-between}
.category{font-size:12px;color:#94c9ff}.age{color:#b3bfd3;font-size:11px;text-align:right}
h2{font-size:17px;line-height:1.35;min-height:46px;margin:15px 0 7px}
.identity{color:#a8bed6;font-size:12px;margin-bottom:18px}
.metrics{display:grid;grid-template-columns:1.3fr 1fr .65fr;gap:8px}
.metrics span{display:block;font-size:11px;color:#a8bed6;margin-bottom:6px}
.metrics strong{font-size:16px}.unknown{color:#b5c3d5;font-size:12px;margin:15px 0;padding-top:12px;border-top:1px solid #314762}
.bottom{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px}
a{color:#83c5ff}details{font-size:12px;color:#a9bdd3;max-width:100%;overflow-wrap:anywhere}summary{cursor:pointer}
details p{font-size:12px}.empty{color:#b7c6d9}
@media(max-width:690px){.controls{grid-template-columns:1fr}main{padding:20px 14px}.cards{grid-template-columns:1fr}}
</style></head><body><main>
<header><h1>OLYMPUS — Black Box Brasil</h1>
<p>Pesquisa de produtos identificados com fontes, datas e criterios verificaveis.</p></header>
<div class="notice">""" + warning + """</div>
<section class="controls" aria-label="Filtros">
<label>Buscar produto, marca ou ASIN<input id="q" type="search" placeholder="Ex.: pilha, Ype, B0..."></label>
<label>Categoria<select id="category"><option value="">Todas as categorias</option>""" + options + """</select></label>
<label>Preco historico maximo (R$)<input id="max" type="number" min="0" step="0.01" placeholder="Sem limite"></label>
</section>
<p class="status"><span id="count">""" + str(len(rows)) + """</span> produto(s) exibido(s) de """ + str(len(rows)) + """ cadastrado(s)</p>
<section id="cards" class="cards">""" + ''.join(cards) + """</section>
<p id="empty" class="empty" hidden>Nenhum produto corresponde aos filtros. Campos ausentes nunca sao considerados zero.</p>
<script>
(function () {
const q=document.getElementById("q"), category=document.getElementById("category"), maximum=document.getElementById("max");
const items=Array.from(document.querySelectorAll(".item"));
function update(){
 const term=q.value.trim().toLocaleLowerCase("pt-BR"), cat=category.value;
 const max=maximum.value.trim()==="" ? null : Number(maximum.value);
 let visible=0;
 items.forEach(function(item){
 const price=item.dataset.price==="" ? null : Number(item.dataset.price);
 const ok=(!term||item.dataset.title.toLocaleLowerCase("pt-BR").includes(term)) &&
 (!cat||item.dataset.category===cat) &&
 (max===null||(price!==null&&Number.isFinite(price)&&price<=max));
 item.hidden=!ok; if(ok)visible++;
 });
 document.getElementById("count").textContent=visible;
 document.getElementById("empty").hidden=visible!==0;
}
[q,category,maximum].forEach(function(el){el.addEventListener("input",update)});
update();
})();
</script></main></body></html>"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=pathlib.Path, default=DB)
    parser.add_argument("--saida", type=pathlib.Path, default=BASE/"blackbox_painel.html")
    args = parser.parse_args()
    rows, message = load(args.db)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(build(rows, message), encoding="utf-8")
    print("Produtos unicos:", len(rows))
    print("Painel:", args.saida)
    if message:
        print("Aviso:", message)

if __name__ == "__main__":
    main()
