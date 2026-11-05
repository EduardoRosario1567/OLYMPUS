#!/usr/bin/env python3
"""Adaptador autorizado Amazon SP-API Catalog Items 2022-04-01 => CSV Black Box BR.
Sem chamadas de rede, autenticacao, scraping ou dados inventados. Python 3.9+.
"""
import argparse,csv,datetime as dt,json,pathlib,re
FIELDS=('marketplace','asin','titulo','categoria','marca','vendedor','preco','moeda',
'avaliacoes','nota','bsr','vendedores','vendas_mensais_estimadas',
'receita_mensal_estimada','data_observacao','url','fonte','metodo_estimativa')
BR='A2Q3Y263D00KWC'
def select(items):
    if not isinstance(items,list):return None
    return next((x for x in items if isinstance(x,dict) and x.get('marketplaceId')==BR),None)
def normalize_item(item,date,source):
    if not isinstance(item,dict):return None
    asin=item.get('asin')
    if not isinstance(asin,str) or not re.fullmatch('[A-Z0-9]{10}',asin):return None
    summary=select(item.get('summaries'))
    if not summary or not summary.get('itemName'):return None
    rank=select(item.get('salesRanks'))
    bsr=''
    if rank:
        for r in (rank.get('classificationRanks') or [])+(rank.get('displayGroupRanks') or []):
            if isinstance(r,dict) and isinstance(r.get('rank'),int) and r['rank']>0:
                bsr=str(r['rank']);break
    typ=select(item.get('productTypes'))
    category=summary.get('productType') or summary.get('productGroup') or (typ or {}).get('productType') or 'NAO INFORMADA'
    return dict(marketplace='amazon.com.br',asin=asin,titulo=str(summary['itemName']).strip(),
       categoria=str(category),marca=str(summary.get('brand') or summary.get('brandName') or ''),
       vendedor='',preco='',moeda='',avaliacoes='',nota='',bsr=bsr,vendedores='',
       vendas_mensais_estimadas='',receita_mensal_estimada='',data_observacao=date,
       url='https://www.amazon.com.br/dp/'+asin,fonte=source,metodo_estimativa='')
def normalize(payload,date,source):
    if not isinstance(payload,dict) or not isinstance(payload.get('items'),list):
        raise ValueError('Resposta inesperada: items[] obrigatorio')
    result=[];seen=set()
    for item in payload['items']:
        row=normalize_item(item,date,source)
        if row and row['asin'] not in seen:
            seen.add(row['asin']);result.append(row)
    return result
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entrada',required=True,type=pathlib.Path,
        help='JSON de resposta SP-API Catalog Items obtido por usuario autorizado')
    p.add_argument('--saida',type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent/'amazon_br_importacao.csv')
    p.add_argument('--data',default=dt.date.today().isoformat())
    p.add_argument('--fonte',default='Amazon SP-API Catalog Items 2022-04-01 — acesso autorizado')
    a=p.parse_args(argv);dt.date.fromisoformat(a.data)
    if not a.fonte.strip():p.error('Fonte obrigatoria')
    payload=json.loads(a.entrada.read_text(encoding='utf-8'))
    rows=normalize(payload,a.data,a.fonte)
    a.saida.parent.mkdir(parents=True,exist_ok=True)
    with a.saida.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    print('Produtos Amazon BR normalizados:',len(rows),'| CSV:',a.saida)
    print('Precos, reviews e vendas permanecem N/D, pois nao foram fornecidos.')
if __name__=='__main__':main()
