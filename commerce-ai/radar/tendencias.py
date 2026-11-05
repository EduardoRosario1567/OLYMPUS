#!/usr/bin/env python3
"""OLYMPUS: tendencias Google Trends RSS Brasil. Sem dependencias externas."""
import argparse, csv, datetime as dt, html, json, pathlib, sqlite3
import urllib.request, urllib.error, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from radar import BASE, DB

RSS_URL = 'https://trends.google.com/trending/rss?geo=BR'
NS = {'ht':'https://trends.google.com/trending/rss'}
HEADERS = {'User-Agent':'OLYMPUS-Commerce-AI/1.1 (personal market research)',
           'Accept':'application/rss+xml, application/xml, text/xml'}
MAX_BYTES = 2_000_000

def parse_rss(raw):
    raiz = ET.fromstring(raw)
    if raiz.tag != 'rss':
        raise ValueError('XML inesperado; nao e RSS')
    registros = []
    vistos = set()
    for item in raiz.findall('./channel/item'):
        termo = (item.findtext('title') or '').strip()
        if not termo or termo.casefold() in vistos:
            continue
        vistos.add(termo.casefold())
        volume = (item.findtext('ht:approx_traffic',namespaces=NS) or '').strip()
        publicado = (item.findtext('pubDate') or '').strip()
        if publicado:
            try:
                publicado = parsedate_to_datetime(publicado).astimezone(dt.timezone.utc).isoformat()
            except (TypeError,ValueError,OverflowError):
                publicado = ''
        link = (item.findtext('link') or '').strip()
        if not link.startswith('https://'):
            link = 'https://trends.google.com/trending?geo=BR'
        registros.append({
            'termo':termo[:250], 'volume_aproximado':volume[:80],
            'publicado_em':publicado, 'url':link,
            'fonte':RSS_URL
        })
    return registros

def coletar(limite):
    if limite<1 or limite>50:
        raise ValueError('Limite entre 1 e 50')
    req = urllib.request.Request(RSS_URL,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=25) as resposta:
        if resposta.status!=200:
            raise RuntimeError('HTTP '+str(resposta.status))
        raw = resposta.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError('RSS grande demais')
    return parse_rss(raw)[:limite]

def conectar():
    con = sqlite3.connect(str(DB))
    con.execute('''CREATE TABLE IF NOT EXISTS tendencias (
        termo TEXT NOT NULL,
        publicado_em TEXT NOT NULL,
        volume_aproximado TEXT,
        url TEXT,
        fonte TEXT NOT NULL,
        coletado_em TEXT NOT NULL,
        PRIMARY KEY (termo,publicado_em,fonte))''')
    con.commit()
    return con

def gravar(con,itens):
    agora=dt.datetime.now(dt.timezone.utc).isoformat()
    with con:
        for item in itens:
            con.execute('''INSERT OR IGNORE INTO tendencias
               (termo,publicado_em,volume_aproximado,url,fonte,coletado_em)
               VALUES (?,?,?,?,?,?)''',
               (item['termo'],item['publicado_em'],
                item['volume_aproximado'],item['url'],item['fonte'],agora))

def gerar_relatorio(con):
    dados = con.execute('''SELECT termo,volume_aproximado,publicado_em,url,fonte
                           FROM tendencias ORDER BY coletado_em DESC, termo LIMIT 200''').fetchall()
    arq = BASE/'tendencias.html'
    with arq.open('w',encoding='utf-8') as f:
        f.write('<!doctype html><html lang="pt-br"><meta charset="utf-8">'
                '<title>OLYMPUS Tendencias Brasil</title>'
                '<style>body{font:15px Arial;background:#0b1730;color:#f8fafc;padding:28px}'
                'table{border-collapse:collapse;width:100%}'
                'th,td{text-align:left;border-bottom:1px solid #475569;padding:12px}'
                'a{color:#93c5fd}</style><h1>OLYMPUS Commerce AI — Tendencias Brasil</h1>'
                '<p>Sinais gerais de interesse em pesquisas. Nao sao vendas, '
                'nichos validados, demanda comercial ou faturamento.</p>'
                '<table><tr><th>Termo</th><th>Buscas aproximadas (rotulo Google)</th>'
                '<th>Publicado</th><th>Fonte</th></tr>')
        for termo,volume,publicado,url,fonte in dados:
            f.write('<tr><td>'+html.escape(termo)+'</td><td>'+html.escape(volume or 'N/D')+
                    '</td><td>'+html.escape(publicado or 'N/D')+'</td><td>')
            f.write('<a href="'+html.escape(url or fonte,quote=True)+'" rel="noopener noreferrer">Consultar</a></td></tr>')
        f.write('</table></html>')
    csv_path=BASE/'tendencias.csv'
    with csv_path.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['termo','volume_aproximado','publicado_em','url','fonte'])
        w.writerows(dados)
    return arq,len(dados)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limite',type=int,default=25)
    p.add_argument('--sem-rede',action='store_true')
    args=p.parse_args()
    with conectar() as con:
        if not args.sem_rede:
            try:
                itens=coletar(args.limite)
                gravar(con,itens)
                print('Tendencias capturadas agora:',len(itens),'| Fonte:',RSS_URL)
            except (ValueError,urllib.error.URLError,RuntimeError,ET.ParseError) as err:
                print('Fonte indisponivel:',type(err).__name__,str(err))
        destino,n=gerar_relatorio(con)
    print('Historico exibido:',n,'| Relatorio:',destino)

if __name__=='__main__': main()
