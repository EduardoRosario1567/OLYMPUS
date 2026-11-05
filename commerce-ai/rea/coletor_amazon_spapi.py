#!/usr/bin/env python3
"""Consulta autorizada ao catalogo Amazon Brasil (SP-API 2022-04-01).

Credenciais opcionais em ~/.config/olympus-commerce/amazon_spapi.json, modo 0600:
{"client_id":"...","client_secret":"...","refresh_token":"...",
 "keywords":["pilha alcalina","lampada led"],"pages_per_keyword":1}
NUNCA versionar esse arquivo. Sem credenciais, nao consulta nem altera dados.
Sem dependencia de terceiros. Nao presume acesso a precos, reviews ou vendas.
"""
import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from amazon_catalogo_br import normalize,FIELDS,BR

BASE=pathlib.Path(__file__).resolve().parent
CONFIG=pathlib.Path.home()/'.config'/'olympus-commerce'/'amazon_spapi.json'
INBOX=BASE/'entrada_csv'
TOKEN_URL='https://api.amazon.com/auth/o2/token'
CATALOG_URL='https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items'
USER_AGENT='OLYMPUS-Commerce-AI/0.1 (Language=Python/3.9)'
MAX_KEYWORDS=5
MAX_PAGES=2
MAX_BYTES=2_000_000

def read_config(path=CONFIG):
    if not path.is_file():
        return None
    mode=stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError('Credenciais devem ter permissao 0600: chmod 600 '+str(path))
    obj=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj,dict):
        raise ValueError('Configuracao invalida')
    keys=('client_id','client_secret','refresh_token')
    if not all(isinstance(obj.get(k),str) and obj[k].strip() for k in keys):
        raise ValueError('client_id, client_secret e refresh_token sao obrigatorios')
    words=obj.get('keywords',[])
    if not isinstance(words,list) or not (1<=len(words)<=MAX_KEYWORDS):
        raise ValueError('Informe 1 a 5 keywords de produtos na configuracao')
    if any(not isinstance(w,str) or not w.strip() or len(w)>80 for w in words):
        raise ValueError('Keyword invalida')
    pages=obj.get('pages_per_keyword',1)
    if not isinstance(pages,int) or not (1<=pages<=MAX_PAGES):
        raise ValueError('pages_per_keyword deve ser 1 ou 2')
    return obj

def request_json(url,headers=None,body=None,timeout=25):
    req=urllib.request.Request(url,data=body,headers=headers or {},method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as res:
            payload=res.read(MAX_BYTES+1)
            if len(payload)>MAX_BYTES:
                raise ValueError('Resposta da API excedeu o limite de tamanho')
            return json.loads(payload.decode('utf8'))
    except urllib.error.HTTPError as exc:
        # Nao exibir resposta do servidor: pode conter detalhes sensiveis.
        raise RuntimeError('Falha HTTP '+str(exc.code)+' em consulta Amazon autorizada') from None

def token(config):
    body=urllib.parse.urlencode({
        'grant_type':'refresh_token',
        'refresh_token':config['refresh_token'],
        'client_id':config['client_id'],
        'client_secret':config['client_secret'],
    }).encode('ascii')
    obj=request_json(TOKEN_URL,{'Content-Type':'application/x-www-form-urlencoded','User-Agent':USER_AGENT},body)
    access=obj.get('access_token') if isinstance(obj,dict) else None
    if not access or not isinstance(access,str):
        raise RuntimeError('Autorizacao LWA nao retornou access_token')
    return access

def search(keyword,access,next_token=None):
    params={'marketplaceIds':BR,'includedData':'summaries,productTypes,salesRanks','pageSize':'20'}
    if next_token:
        params['pageToken']=next_token
    else:
        params['keywords']=keyword
    url=CATALOG_URL+'?'+urllib.parse.urlencode(params)
    return request_json(url,{
        'x-amz-access-token':access,
        'User-Agent':USER_AGENT,
        'Accept':'application/json',
    })

def collect(config,fetch=search,sleeper=time.sleep):
    access=token(config)
    rows={}
    events=[]
    for keyword in config['keywords']:
        next_token=None
        for page in range(config.get('pages_per_keyword',1)):
            answer=fetch(keyword,access,next_token)
            if not isinstance(answer,dict) or not isinstance(answer.get('items'),list):
                raise RuntimeError('Resposta de catalogo inesperada')
            date=dt.date.today().isoformat()
            source='Amazon SP-API Catalog Items BR (fonte primaria; acesso autorizado)'
            products=normalize(answer,date,source)
            for p in products:
                rows[p['asin']]=p
            events.append({'termo':keyword,'pagina':page+1,'itens_recebidos':len(products)})
            next_token=(answer.get('pagination') or {}).get('nextToken')
            if not next_token:break
            sleeper(0.6)
        sleeper(0.6)
    return list(rows.values()),events

def write_inbox(rows,folder=INBOX):
    if not rows:return None
    folder.mkdir(parents=True,exist_ok=True)
    name='amazon_spapi_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.csv'
    dest=folder/name
    with dest.open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return dest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=pathlib.Path,default=CONFIG)
    p.add_argument('--verificar',action='store_true',help='Somente verifica se configuracao autorizada existe')
    args=p.parse_args()
    cfg=read_config(args.config)
    if cfg is None:
        print('FONTE AMAZON NAO CONECTADA: arquivo de credenciais autorizado ausente.')
        print('Caminho esperado:',args.config)
        return 0
    if args.verificar:
        print('Configuracao encontrada: termos',len(cfg['keywords']),'| paginas por termo:',cfg.get('pages_per_keyword',1))
        return 0
    rows,events=collect(cfg)
    dst=write_inbox(rows)
    print('Consulta Amazon BR: termos',len(events),'| ASINs',len(rows),'| arquivo',str(dst) if dst else 'nenhum')
    print('Nota: catalogo nao retorna aqui precos, reviews ou vendas.')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('ERRO AMAZON:',str(exc),file=sys.stderr)
        sys.exit(1)
