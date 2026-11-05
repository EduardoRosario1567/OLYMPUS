#!/usr/bin/env python3
"""OLYMPUS Commerce AI: Black Box + Xray integrados, sem servidor (Python 3.9+)."""
import argparse
import datetime as dt
import html
import json
import pathlib
from decimal import Decimal, InvalidOperation
import xray_br

BASE=pathlib.Path(__file__).resolve().parent
DB=BASE/'radar.sqlite3'

def decimal(value):
    if value is None or str(value).strip()=='':
        return None
    try:
        n=Decimal(str(value).replace(',','.'))
    except (InvalidOperation,ValueError):
        return None
    return n if n.is_finite() and n>=0 else None

def age_label(raw, today=None):
    today=today or dt.date.today()
    try:
        date=dt.date.fromisoformat(str(raw))
    except (ValueError,TypeError):
        return 'Data nao validada', True
    days=(today-date).days
    if days<0:
        return 'Data futura: verificar',True
    if days>7:
        return 'Historico: '+date.isoformat(),True
    return 'Observado: '+date.isoformat(),False

def payload(rows, today=None):
    today=today or dt.date.today()
    groups=xray_br.analyse(rows,today)
    products=[]
    for r in rows:
        label,stale=age_label(r.get('data_observacao'),today)
        p=decimal(r.get('preco')) if r.get('moeda')=='BRL' else None
        reviews=decimal(r.get('avaliacoes'))
        products.append({
            'asin':str(r.get('asin') or ''),
            'title':str(r.get('titulo') or ''),
            'brand':str(r.get('marca') or ''),
            'category':str(r.get('categoria') or 'Nao informada'),
            'price':float(p) if p is not None else None,
            'reviews':int(reviews) if reviews is not None and reviews==int(reviews) else None,
            'rating':float(decimal(r.get('nota'))) if decimal(r.get('nota')) is not None else None,
            'date':str(r.get('data_observacao') or ''),
            'age':label,'stale':stale,
            'url':str(r.get('url') or ''),
            'source':str(r.get('fonte') or ''),
            'sales_known':bool(r.get('vendas_mensais_estimadas')) and bool(r.get('metodo_estimativa')),
        })
    return {
        'marketplace':'amazon.com.br','products':products,
        'categories':groups['analises'],'total':len(products),
        'historical':sum(1 for p in products if p['stale']),
        'warning':'Fonte secundaria/historica. Comparacoes descrevem apenas a amostra; nao demonstram demanda, receita ou participacao de mercado.'
    }

def page(data):
    # JSON in script tag must not allow source-driven HTML/script breakouts.
    embedded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OLYMPUS Commerce AI | Pesquisa Integrada</title>
<style>
:root{color-scheme:dark;font:15px -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#0b172a;color:#f1f6ff}main{max-width:1200px;margin:auto;padding:26px 20px}
header{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap}
h1{margin:0;font-size:clamp(24px,4vw,32px)}.subtitle,.muted{color:#b2c3d9}h2{font-size:19px}
.notice{background:#172e49;border-left:3px solid #72b9ff;border-radius:8px;padding:14px;margin:20px 0;color:#cad9eb}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:15px 0}
.stat,.panel,.item{border:1px solid #304c6b;background:#16263e;border-radius:12px;padding:16px}
.stat strong{font-size:25px;display:block}.stat span,small{color:#b5c7da}
.controls{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px;margin:25px 0}
label{font-size:12px;color:#c1d1e3;display:flex;flex-direction:column;gap:7px}
input,select{background:#1c304c;color:white;border:1px solid #567393;border-radius:8px;padding:11px;width:100%;font:inherit}
section{margin:24px 0}.comparison{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.panel h3{margin:0 0 12px}.panel p{margin:6px 0;font-size:13px;color:#c9d7e6}
.items{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:14px}
.item h3{font-size:16px;line-height:1.35;min-height:43px;margin:13px 0 9px}
.badge{font-size:11px;color:#a7cfff}.age{font-size:11px;color:#d1c29b}
.bar{display:flex;gap:8px;justify-content:space-between}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:15px 0}
.metrics small{font-size:11px;display:block}.metrics strong{display:block;font-size:16px;margin-top:5px}
.explain{color:#abbfd3;font-size:12px;line-height:1.45}
a{color:#93caff}details{margin-top:12px;font-size:12px;color:#bbcade;overflow-wrap:anywhere}
summary{cursor:pointer}p{line-height:1.45}
@media(max-width:760px){.controls{grid-template-columns:1fr 1fr}.stats{grid-template-columns:1fr 1fr}}
@media(max-width:490px){.controls,.stats{grid-template-columns:1fr}}
</style></head><body><main>
<header><div><h1>OLYMPUS Commerce AI</h1><p class="subtitle">Black Box + Xray Brasil — pesquisa e comparacao integradas</p></div><span class="muted">Amazon Brasil · amostra local</span></header>
<div class="notice">Fonte secundaria/historica. Valores ausentes nao significam zero. Nao ha vendas, receita ou lucro apurados.</div>
<div class="stats"><div class="stat"><strong id="total">0</strong><span>Produtos visiveis</span></div>
<div class="stat"><strong id="cats">0</strong><span>Categorias na selecao</span></div>
<div class="stat"><strong id="historical">0</strong><span>Registros historicos na selecao</span></div></div>
<div class="controls">
<label>Pesquisar nome, marca ou ASIN<input id="q" type="search" placeholder="Ex.: pilha, Elseve, ASIN"></label>
<label>Categoria<select id="cat"><option value="">Todas</option></select></label>
<label>Preco historico ate R$<input id="max" type="number" min="0" step="0.01" placeholder="Sem limite"></label>
<label>Ordenacao<select id="sort"><option value="name">Nome</option><option value="price">Menor preco</option><option value="reviews">Mais avaliacoes</option></select></label>
</div>
<section><h2>Xray — Comparacao da selecao</h2><p class="explain">Estatisticas recalculadas ao filtrar produtos. As avaliacoes nao representam participacao de mercado.</p>
<div id="compare" class="comparison"></div></section>
<section><h2>Black Box — Produtos</h2><p id="counter" class="muted"></p><div id="items" class="items"></div></section>
<script type="application/json" id="data">""" + embedded + """</script>
<script>
(function(){
"use strict";
const data=JSON.parse(document.getElementById("data").textContent);
const q=document.getElementById("q"),cat=document.getElementById("cat"),max=document.getElementById("max"),sort=document.getElementById("sort");
const items=document.getElementById("items"),compare=document.getElementById("compare");
function el(tag,text,cls){
 const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;
}
function brl(v){return v===null?"N/D":new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v);}
function median(a){if(!a.length)return null;const b=a.slice().sort((x,y)=>x-y),i=Math.floor(b.length/2);return b.length%2?b[i]:(b[i-1]+b[i])/2;}
function number(v){return v===null?"N/D":new Intl.NumberFormat("pt-BR",{maximumFractionDigits:1}).format(v);}
for(const c of [...new Set(data.products.map(p=>p.category))].sort()){const o=el("option",c);o.value=c;cat.appendChild(o);}
function render(){
 const term=q.value.trim().toLocaleLowerCase("pt-BR"),limit=max.value===""?null:Number(max.value);
 const found=data.products.filter(p=>(!term||[p.title,p.brand,p.asin].join(" ").toLocaleLowerCase("pt-BR").includes(term)) &&
 (!cat.value||p.category===cat.value) && (limit===null||(p.price!==null&&p.price<=limit)));
 if(sort.value==="price")found.sort((a,b)=>(a.price===null?Infinity:a.price)-(b.price===null?Infinity:b.price));
 else if(sort.value==="reviews")found.sort((a,b)=>(b.reviews===null?-1:b.reviews)-(a.reviews===null?-1:a.reviews));
 else found.sort((a,b)=>a.title.localeCompare(b.title,"pt-BR"));
 document.getElementById("total").textContent=found.length;
 document.getElementById("cats").textContent=new Set(found.map(p=>p.category)).size;
 document.getElementById("historical").textContent=found.filter(p=>p.stale).length;
 document.getElementById("counter").textContent=found.length+" de "+data.total+" produtos cadastrados";
 items.replaceChildren();compare.replaceChildren();
 const groups=new Map();
 for(const p of found){if(!groups.has(p.category))groups.set(p.category,[]);groups.get(p.category).push(p);}
 for(const [category,list] of [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],"pt-BR"))){
   const card=el("article",undefined,"panel");
   card.append(el("h3",category));
   const prices=list.map(p=>p.price).filter(v=>v!==null), reviews=list.map(p=>p.reviews).filter(v=>v!==null);
   for(const line of [list.length+" produto(s) observado(s)",
      "Preco mediano: "+brl(median(prices)),
      "Faixa: "+(prices.length?brl(Math.min(...prices))+" a "+brl(Math.max(...prices)):"N/D"),
      "Avaliacoes medianas: "+number(median(reviews)),
      "Marcas identificadas: "+new Set(list.map(p=>p.brand).filter(Boolean)).size]){
       card.append(el("p",line));
   }
   compare.append(card);
 }
 if(!found.length){compare.append(el("p","Sem dados para calcular indicadores."));items.append(el("p","Nenhum produto corresponde aos filtros."));}
 for(const p of found){
   const card=el("article",undefined,"item"),top=el("div",undefined,"bar");
   top.append(el("span",p.category,"badge"),el("span",p.age,"age"));card.append(top);
   card.append(el("h3",p.title),el("p",(p.brand||"Marca N/D")+" · ASIN "+p.asin,"explain"));
   const metrics=el("div",undefined,"metrics");
   for(const [label,value] of [["Preco reportado",brl(p.price)],["Avaliacoes",number(p.reviews)],["Nota",number(p.rating)]]){
      const box=el("div");box.append(el("small",label),el("strong",value));metrics.append(box);
   }
   card.append(metrics,el("p","Vendas mensais e receita: N/D. Sem inferencia de demanda.","explain"));
   if(/^https:\/\/www\.amazon\.com\.br\/dp\/[A-Z0-9]{10}$/.test(p.url)){
      const link=el("a","Consultar na Amazon");link.href=p.url;link.target="_blank";link.rel="noopener noreferrer";card.append(link);
   }
   const details=el("details"),summary=el("summary","Fonte e observacao");
   details.append(summary,el("p",p.source||"Nao informada"),el("p","Observado em "+p.date+"; preco atual nao confirmado."));
   card.append(details);items.append(card);
 }
}
[q,cat,max,sort].forEach(n=>n.addEventListener("input",render));render();
})();
</script></main></body></html>"""

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=pathlib.Path,default=DB)
    p.add_argument('--saida',type=pathlib.Path,default=BASE/'commerce_integrado.html')
    a=p.parse_args()
    rows=xray_br.load(a.db)
    report=payload(rows)
    a.saida.parent.mkdir(parents=True,exist_ok=True)
    a.saida.write_text(page(report),encoding='utf8')
    a.saida.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('OLYMPUS integrado |',report['total'],'produtos |',len(report['categories']),'categorias |',report['historical'],'historicos')
    print('HTML:',a.saida)
    if not rows:print('SEM PRODUTOS: conecte fonte autorizada ou importe observacoes.')
if __name__=='__main__':main()
