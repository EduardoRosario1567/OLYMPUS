#!/usr/bin/env python3
"""OLYMPUS Xray BR: comparacao local por categoria. Sem estimar vendas. Python 3.9+."""
import argparse,collections,datetime as dt,html,json,pathlib,sqlite3,statistics
from decimal import Decimal,InvalidOperation
BASE=pathlib.Path(__file__).resolve().parent
DB=BASE/'radar.sqlite3'
def number(v):
    if v is None or str(v).strip()=='':return None
    try:d=Decimal(str(v).strip().replace(',','.'))
    except (ValueError,InvalidOperation):return None
    return d if d.is_finite() and d>=0 else None
def load(db):
    if not pathlib.Path(db).exists():return []
    with sqlite3.connect(str(db)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='blackbox_amazon_br'").fetchone():return []
        c.row_factory=sqlite3.Row
        rows=[dict(x) for x in c.execute("""SELECT asin,titulo,marca,categoria,preco,moeda,avaliacoes,nota,bsr,vendedores,vendas_mensais_estimadas,receita_mensal_estimada,data_observacao,url,fonte FROM blackbox_amazon_br WHERE marketplace='amazon.com.br' ORDER BY data_observacao DESC,asin""")]
    unique={}
    for r in rows:unique.setdefault(r['asin'],r)
    return list(unique.values())
def analyse(rows,today=None):
    today=today or dt.date.today()
    groups=collections.defaultdict(list);stale=0;bad_dates=0
    for r in rows:
        try:
            age=(today-dt.date.fromisoformat(r.get('data_observacao') or '')).days
            if age<0:bad_dates+=1
            elif age>7:stale+=1
        except ValueError:bad_dates+=1
        groups[r.get('categoria') or 'Nao informada'].append(r)
    out=[]
    for cat,items in sorted(groups.items()):
        prices=[number(r.get('preco')) if r.get('moeda')=='BRL' else None for r in items]
        prices=[p for p in prices if p is not None]
        reviews=[number(r.get('avaliacoes')) for r in items]
        reviews=[v for v in reviews if v is not None]
        brands={str(r.get('marca') or '').strip().casefold() for r in items if str(r.get('marca') or '').strip()}
        total=sum(reviews,Decimal(0))
        top=max(reviews)/total*100 if reviews and total else None
        out.append(dict(categoria=cat,amostra_produtos=len(items),
           preco_mediano=str(statistics.median(prices)) if prices else None,
           preco_min=str(min(prices)) if prices else None,
           preco_max=str(max(prices)) if prices else None,
           precos_disponiveis=len(prices),
           avaliacoes_medianas=str(statistics.median(reviews)) if reviews else None,
           avaliacoes_disponiveis=len(reviews),marcas_identificadas=len(brands),
           maior_frac_avaliacoes_amostra_pct=str(top.quantize(Decimal('0.01'))) if top is not None else None,
           estimativa_vendas=None,faturamento_mercado=None,representatividade_amostra='NAO DETERMINADA',
           produtos=[{k:r.get(k) for k in ('asin','titulo','preco','avaliacoes','data_observacao','url','fonte')} for r in items]))
    return dict(observados=len(rows),categorias=len(out),observacoes_mais_de_7_dias=stale,
                datas_invalidas_ou_futuras=bad_dates,analises=out,
                aviso='Amostra intencional, nao aleatoria. Indicadores descrevem somente itens observados; nao medem vendas, participacao de mercado ou lucratividade.')
def render(report):
    e=lambda v:html.escape(str(v) if v not in (None,'') else 'N/D',quote=True)
    cards=[]
    for r in report['analises']:
        metrics=[('Produtos na amostra',r['amostra_produtos']),('Preco mediano (BRL)',r['preco_mediano']),
                 ('Faixa de preco (BRL)',(r['preco_min']+' a '+r['preco_max']) if r['preco_min'] is not None else None),
                 ('Avaliacoes medianas',r['avaliacoes_medianas']),('Marcas observadas',r['marcas_identificadas']),
                 ('Maior parcela das avaliacoes da amostra',(r['maior_frac_avaliacoes_amostra_pct']+'%') if r['maior_frac_avaliacoes_amostra_pct'] is not None else None)]
        tiles=''.join('<div><small>'+e(k)+'</small><strong>'+e(v)+'</strong></div>' for k,v in metrics)
        links=[]
        for p in r['produtos']:
            url=str(p.get('url') or '')
            link='<a href="'+e(url)+'" rel="noopener noreferrer" target="_blank">Amazon</a>' if url.startswith('https://www.amazon.com.br/') else 'URL N/D'
            links.append('<li>'+e(p['titulo'])+' · '+e(p['asin'])+' · '+e(p['data_observacao'])+' · '+link+'</li>')
        cards.append('<article><h2>'+e(r['categoria'])+'</h2><div class="metrics">'+tiles+'</div><details><summary>Produtos e fontes ('+str(len(links))+')</summary><ul>'+''.join(links)+'</ul></details></article>')
    return '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OLYMPUS Xray Brasil</title><style>*{box-sizing:border-box}body{font:15px system-ui,Arial;background:#0b1729;color:#eaf2ff;margin:0}main{max-width:1140px;margin:auto;padding:26px 20px}h1{margin:0 0 8px}p{line-height:1.5;color:#b5c8df}.notice{border-left:3px solid #66b6fa;background:#182b43;padding:14px;border-radius:6px;margin:20px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}article{border:1px solid #344b68;background:#172741;border-radius:12px;padding:20px;min-width:0}h2{margin:0 0 18px;font-size:21px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:16px}small{display:block;color:#b6c7de;font-size:12px;line-height:1.4}strong{display:block;margin-top:4px}details{margin-top:20px;color:#bcd2ea;overflow-wrap:anywhere}summary{cursor:pointer}li{padding:6px 0}a{color:#87c9fa}</style></head><body><main><h1>OLYMPUS — Xray Brasil</h1><p>Analise descritiva de produtos observados por categoria.</p><div class="notice">'''+e(report['aviso'])+'</div><p>'+str(report['observados'])+' produtos · '+str(report['categorias'])+' categorias · '+str(report['observacoes_mais_de_7_dias'])+' observacoes historicas (&gt;7 dias)</p><section class="cards">'+''.join(cards)+'</section><p>Vendas, faturamento e participacao de mercado: nao determinados.</p></main></body></html>'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=pathlib.Path,default=DB)
    p.add_argument('--saida',type=pathlib.Path,default=BASE/'xray_br.html')
    a=p.parse_args()
    result=analyse(load(a.db))
    a.saida.parent.mkdir(parents=True,exist_ok=True)
    a.saida.write_text(render(result),encoding='utf8')
    a.saida.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('Xray BR:',result['observados'],'produtos |',result['categorias'],'categorias | historicos:',result['observacoes_mais_de_7_dias'])
    print('Relatorio:',a.saida)
if __name__=='__main__':main()
