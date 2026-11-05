#!/usr/bin/env python3
"""OLYMPUS Radar: catalogo brasileiro e cotacoes. Python 3.9+, sem dependencias."""
import argparse, csv, datetime as dt, html, json, pathlib, sqlite3, urllib.parse, urllib.request
from decimal import Decimal, InvalidOperation
BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / 'radar.sqlite3'
API = 'https://world.openfoodfacts.org/api/v2/search'
AGENT = 'OLYMPUS-Commerce-AI/1.0 (personal catalogue research)'

def decimal(valor):
    try: n = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, TypeError): raise ValueError('valor numerico invalido')
    if not n.is_finite() or n < 0: raise ValueError('valor numerico negativo ou invalido')
    return n

def margem(preco, custo, frete, comissao, imposto, outros):
    p,c,f,co,i,o = map(decimal, (preco,custo,frete,comissao,imposto,outros))
    if p <= 0 or co+i >= 100: raise ValueError('preco ou taxas invalidas')
    contribuicao = p*(1-(co+i)/100)-c-f-o
    return round(contribuicao,2),round(100*contribuicao/p,2)

def banco():
    con=sqlite3.connect(str(DB))
    con.execute('''CREATE TABLE IF NOT EXISTS produtos (
        codigo TEXT PRIMARY KEY, nome TEXT NOT NULL, marca TEXT,
        url TEXT NOT NULL, coletado_em TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS cotacoes (
        codigo TEXT PRIMARY KEY, preco TEXT NOT NULL, custo TEXT NOT NULL,
        frete TEXT NOT NULL, comissao TEXT NOT NULL, imposto TEXT NOT NULL,
        outros TEXT NOT NULL, url_preco TEXT, url_fornecedor TEXT,
        consultado_em TEXT NOT NULL)''')
    con.commit()
    return con

def normalizar(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('products'),list):
        raise ValueError('resposta inesperada da API')
    vistos=set(); itens=[]
    for p in payload['products']:
        if not isinstance(p,dict): continue
        codigo=str(p.get('code') or '').strip()
        nome=str(p.get('product_name') or '').strip()
        paises=p.get('countries_tags') or []
        if not isinstance(paises,list): continue
        if not (codigo.isdigit() and 8 <= len(codigo) <= 14 and nome): continue
        if 'en:brazil' not in [str(t).lower() for t in paises] or codigo in vistos: continue
        vistos.add(codigo)
        itens.append((codigo,nome[:200],str(p.get('brands') or '')[:150],
            'https://world.openfoodfacts.org/product/'+codigo,
            dt.datetime.now(dt.timezone.utc).isoformat()))
    return itens

def coletar(con,limite):
    if not (1<=limite<=50): raise ValueError('limite deve estar entre 1 e 50')
    parametros=urllib.parse.urlencode({'countries_tags':'en:brazil','page_size':limite,
        'page':1,'fields':'code,product_name,brands,countries_tags'})
    url=API+'?'+parametros
    req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as resp:
        if resp.status!=200: raise ValueError('HTTP '+str(resp.status))
        pacote=resp.read(3000001)
        if len(pacote)>3000000: raise ValueError('resposta muito grande')
    linhas=normalizar(json.loads(pacote.decode('utf-8')))
    with con:
        con.executemany('''INSERT INTO produtos VALUES (?,?,?,?,?)
            ON CONFLICT(codigo) DO UPDATE SET nome=excluded.nome,
            marca=excluded.marca,url=excluded.url,coletado_em=excluded.coletado_em''',linhas)
    print('Produtos recebidos:',len(linhas),'| Fonte:',url)

def importar(con,caminho):
    with open(caminho,encoding='utf-8-sig',newline='') as arq:
        leitor=csv.DictReader(arq)
        campos={'codigo','preco','custo','frete','comissao','imposto',
                'outros','url_preco','url_fornecedor','consultado_em'}
        if not campos.issubset(set(leitor.fieldnames or [])):
            raise ValueError('CSV exige: '+', '.join(sorted(campos)))
        total=0
        with con:
            for linha in leitor:
                margem(*(linha[c] for c in ('preco','custo','frete','comissao','imposto','outros')))
                if not str(linha['codigo']).isdigit(): raise ValueError('codigo invalido')
                dt.date.fromisoformat(str(linha['consultado_em'])[:10])
                dados=tuple(str(linha[c]).strip() for c in ('codigo','preco','custo',
                    'frete','comissao','imposto','outros','url_preco',
                    'url_fornecedor','consultado_em'))
                con.execute('''INSERT INTO cotacoes VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(codigo) DO UPDATE SET preco=excluded.preco,
                    custo=excluded.custo,frete=excluded.frete,
                    comissao=excluded.comissao,imposto=excluded.imposto,
                    outros=excluded.outros,url_preco=excluded.url_preco,
                    url_fornecedor=excluded.url_fornecedor,
                    consultado_em=excluded.consultado_em''',dados)
                total+=1
    print('Cotacoes importadas:',total)

def relatorio(con):
    linhas=con.execute('''SELECT p.codigo,p.nome,p.marca,p.url,
        c.preco,c.custo,c.frete,c.comissao,c.imposto,c.outros,
        c.url_preco,c.url_fornecedor,c.consultado_em
        FROM produtos p LEFT JOIN cotacoes c ON c.codigo=p.codigo
        ORDER BY p.nome''').fetchall()
    registros=[]
    for x in linhas:
        codigo,nome,marca,url,preco,custo,frete,comissao,imposto,outros,up,uf,data=x
        contribuicao=porcentagem=None
        situacao='SEM COTACAO'
        if preco is not None:
            try:
                contribuicao,porcentagem=margem(preco,custo,frete,comissao,imposto,outros)
                idade=(dt.date.today()-dt.date.fromisoformat(data[:10])).days
                if idade<0 or idade>30: situacao='COTACAO DESATUALIZADA'
                elif not (str(up).startswith('https://') and str(uf).startswith('https://')):
                    situacao='FONTES A CONFERIR'
                elif porcentagem>=15: situacao='CANDIDATO A CONFERENCIA'
                else: situacao='MARGEM ABAIXO DA META'
            except (ValueError,TypeError): situacao='DADOS INSUFICIENTES'
        registros.append((codigo,nome,marca,preco,contribuicao,porcentagem,situacao,url))
    destino=BASE/'relatorio.html'
    headers=['Codigo','Produto','Marca','Preco informado','Contribuicao',
        'Margem %','Situacao','Fonte catalogo']
    with destino.open('w',encoding='utf-8') as f:
        f.write('<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>OLYMPUS Radar</title>')
        f.write('<style>body{font:15px Arial;background:#0b1730;color:white;padding:30px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #667;padding:9px;text-align:left}a{color:#93c5fd}</style>')
        f.write('<h1>OLYMPUS Commerce AI - Radar</h1><p>Catalogo nao comprova demanda nem vendas. Cotacoes nao sao automaticamente verificadas.</p><table><tr>')
        for titulo in headers: f.write('<th>'+html.escape(titulo)+'</th>')
        f.write('</tr>')
        for r in registros:
            f.write('<tr>')
            for i,valor in enumerate(r):
                if i==7:
                    f.write('<td><a rel="noopener" href="'+html.escape(str(valor),quote=True)+'">Ver fonte</a></td>')
                else:
                    f.write('<td>'+html.escape('N/D' if valor is None else str(valor))+'</td>')
            f.write('</tr>')
        f.write('</table></html>')
    print('Relatorio:',destino,'| Registros:',len(registros))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limite',type=int,default=20)
    parser.add_argument('--sem-rede',action='store_true')
    parser.add_argument('--csv')
    args=parser.parse_args()
    with banco() as con:
        if not args.sem_rede:
            try: coletar(con,args.limite)
            except Exception as exc: print('Fonte indisponivel:',type(exc).__name__,str(exc))
        if args.csv: importar(con,args.csv)
        relatorio(con)

if __name__=='__main__': main()
