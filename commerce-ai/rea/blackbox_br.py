#!/usr/bin/env python3
"""OLYMPUS Black Box BR: filtros locais em ASINs documentados. Python 3.9+, stdlib."""
import argparse,csv,datetime as dt,html,json,pathlib,re,sqlite3
from decimal import Decimal,InvalidOperation
from urllib.parse import urlparse
BASE=pathlib.Path(__file__).resolve().parent
DB=BASE/'radar.sqlite3'
FIELDS=('marketplace','asin','titulo','categoria','marca','vendedor','preco','moeda','avaliacoes','nota','bsr','vendedores','vendas_mensais_estimadas','receita_mensal_estimada','data_observacao','url','fonte','metodo_estimativa')
NUM={'preco','avaliacoes','nota','bsr','vendedores','vendas_mensais_estimadas','receita_mensal_estimada'}
def num(v,n):
    if v is None or str(v).strip()=='':return None
    try:d=Decimal(str(v).replace(',','.'))
    except (InvalidOperation,ValueError):raise ValueError('Numero invalido: '+n)
    if not d.is_finite() or d<0:raise ValueError('Numero invalido: '+n)
    if n in ('avaliacoes','bsr','vendedores','vendas_mensais_estimadas') and d!=d.to_integral_value():raise ValueError('Inteiro exigido: '+n)
    if n=='nota' and d>5:raise ValueError('Nota fora da escala')
    return d
def validate(row):
    r={k:str(row.get(k) or '').strip() for k in FIELDS}
    if r['marketplace']!='amazon.com.br':raise ValueError('Marketplace diferente de Amazon BR')
    if not re.fullmatch('[A-Za-z0-9]{10}',r['asin']):raise ValueError('ASIN invalido')
    if not r['titulo'] or not r['categoria']:raise ValueError('Titulo/categoria ausentes')
    u=urlparse(r['url'])
    if u.scheme!='https' or not u.netloc or not r['fonte']:raise ValueError('URL HTTPS e fonte obrigatorias')
    dt.date.fromisoformat(r['data_observacao'])
    if r['preco'] and r['moeda']!='BRL':raise ValueError('Preco exige BRL')
    for k in NUM:num(r[k],k)
    if (r['vendas_mensais_estimadas'] or r['receita_mensal_estimada']) and not r['metodo_estimativa']:raise ValueError('Estimativa sem metodologia')
    return r
def connect(path):
    c=sqlite3.connect(str(path))
    c.execute('CREATE TABLE IF NOT EXISTS blackbox_amazon_br ('+','.join(k+' TEXT' for k in FIELDS)+',PRIMARY KEY(marketplace,asin,data_observacao,fonte))')
    c.commit()
    return c
def import_csv(c,path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        required={'marketplace','asin','titulo','categoria','data_observacao','url','fonte'}
        if not required.issubset(reader.fieldnames or []):raise ValueError('Campos faltando: '+', '.join(sorted(required-set(reader.fieldnames or []))))
        rows=[validate(row) for row in reader]
    with c:
        c.executemany('INSERT OR REPLACE INTO blackbox_amazon_br ('+','.join(FIELDS)+') VALUES ('+','.join('?' for _ in FIELDS)+')',[[row[k] for k in FIELDS] for row in rows])
    return len(rows)
def filter_rows(rows,args):
    out=[]
    filters=(('preco',args.preco_min,'min'),('preco',args.preco_max,'max'),('avaliacoes',args.avaliacoes_max,'max'),('bsr',args.bsr_max,'max'),('vendas_mensais_estimadas',args.vendas_min,'min'))
    for r in rows:
        if args.termo and args.termo.casefold() not in (r['titulo']+' '+r['marca']+' '+r['asin']).casefold():continue
        if args.categoria and args.categoria.casefold() not in r['categoria'].casefold():continue
        valid=True
        for k,lim,op in filters:
            if lim is None:continue
            value=num(r[k],k)
            if value is None or (op=='min' and value<lim) or (op=='max' and value>lim):valid=False;break
        if valid:out.append(r)
    return sorted(out,key=lambda r:(r['categoria'],r['titulo'],r['asin']))
def output(rows,htmlpath,args):
    fields=('asin','titulo','categoria','preco','avaliacoes','bsr','vendas_mensais_estimadas','receita_mensal_estimada','fonte','data_observacao')
    missing=lambda r:[k for k in NUM if not r[k]]
    data={'marketplace':'amazon.com.br','total':len(rows),'observacoes':[{**r,'campos_ausentes':missing(r)} for r in rows],'aviso':'Dados ausentes nao significam zero; vendas so com metodo documentado.'}
    htmlpath.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    esc=lambda v:html.escape(str(v) if v not in ('',None) else 'N/D')
    tr=[]
    for r in rows:
        tds=''.join('<td>'+esc(r[k])+'</td>' for k in fields)
        tr.append('<tr>'+tds+'<td><a rel="noopener noreferrer" href="'+html.escape(r['url'],quote=True)+'">Fonte</a></td></tr>')
    doc='<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>OLYMPUS Black Box BR</title><style>body{font:15px Arial;background:#101d34;color:#fff;padding:24px}a{color:#8cf}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #789;text-align:left}</style><h1>OLYMPUS — Black Box Brasil</h1><p>Itens filtrados: '+str(len(rows))+'. Fonte de dados autorizada; N/D nao e zero. Sem calculo de vendas nao documentado.</p><table><tr>'+''.join('<th>'+esc(k)+'</th>' for k in fields)+'<th>URL</th></tr>'+''.join(tr)+'</table></html>'
    htmlpath.write_text(doc,encoding='utf8')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv',type=pathlib.Path);p.add_argument('--db',type=pathlib.Path,default=DB)
    p.add_argument('--saida',type=pathlib.Path,default=BASE/'blackbox_br.html')
    p.add_argument('--termo',default='');p.add_argument('--categoria',default='')
    for field in ('preco-min','preco-max','avaliacoes-max','bsr-max','vendas-min'):
        p.add_argument('--'+field,type=lambda v:num(v,field))
    args=p.parse_args();args.db.parent.mkdir(parents=True,exist_ok=True)
    with connect(args.db) as c:
        if args.csv:print('Importados:',import_csv(c,args.csv))
        c.row_factory=sqlite3.Row
        rows=[dict(x) for x in c.execute('SELECT '+','.join(FIELDS)+' FROM blackbox_amazon_br')]
    filtered=filter_rows(rows,args);output(filtered,args.saida,args)
    print('Amazon BR no banco:',len(rows),'| Apos filtros:',len(filtered),'| Relatorio:',args.saida)
    if not rows:print('SEM DADOS: importe CSV autorizado para consultar produtos.')
if __name__=='__main__':main()
