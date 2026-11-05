#!/usr/bin/env python3
"""Fusao de evidencias comerciais dos bancos existentes, sem IA remota."""
import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sqlite3
import unicodedata
from decimal import Decimal
from radar import BASE, DB, margem

STOP = {'de','da','do','das','dos','e','em','com','para','sem',
        'um','uma','o','a','os','as','tipo','produto','kit'}
def palavras(valor):
    valor = unicodedata.normalize('NFKD',str(valor).lower())
    valor = ''.join(x for x in valor if not unicodedata.combining(x))
    return {x for x in re.findall(r'[a-z0-9]+',valor)
            if len(x)>=4 and x not in STOP}

def relacionar(nome,termo):
    produto=palavras(nome)
    pesquisa=palavras(termo)
    # Um termo comum isolado nao comprova vinculacao comercial.
    return len(produto & pesquisa)>=2 or (len(pesquisa)>=2 and pesquisa <= produto)

def tabela_existe(con,nome):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None

def analisar(con, hoje=None):
    hoje=hoje or dt.date.today()
    produtos = con.execute("""SELECT p.codigo,p.nome,p.marca,p.url,
             c.preco,c.custo,c.frete,c.comissao,c.imposto,c.outros,
             c.url_preco,c.url_fornecedor,c.consultado_em
             FROM produtos p LEFT JOIN cotacoes c ON p.codigo=c.codigo
             ORDER BY p.nome""").fetchall() if tabela_existe(con,'produtos') else []
    tendencias = con.execute("""SELECT termo,volume_aproximado,publicado_em,url,fonte
            FROM tendencias ORDER BY coletado_em DESC LIMIT 300""").fetchall() if tabela_existe(con,'tendencias') else []
    noticias={}
    # Contexto nao inventado: somente referencias explicitamente coletadas.
    json_contexto = BASE/'contexto_noticias.json'
    if json_contexto.exists():
        try:
            bruto=json.loads(json_contexto.read_text(encoding='utf-8'))
            if isinstance(bruto,dict):
                noticias={str(k).casefold():v for k,v in bruto.items() if isinstance(v,list)}
        except (ValueError,OSError):
            noticias={}
    dossies=[]
    for p in produtos:
        codigo,nome,marca,origem,preco,custo,frete,comissao,imposto,outros,up,uf,data = p
        sinais=[]
        for termo,volume,publicado,url,fonte in tendencias:
            if relacionar(nome,termo):
                sinais.append({'termo':termo,'buscas_aproximadas':volume,
                    'publicado_em':publicado,'fonte':fonte,'url':url,
                    'noticias':noticias.get(termo.casefold(),[])[:3]})
        contribuicao=percentual=None
        alerta=[]
        dados_cotacao=preco is not None
        if dados_cotacao:
            try:
                lucro,pc=margem(preco,custo,frete,comissao,imposto,outros)
                contribuicao=str(lucro)
                percentual=str(pc)
                vencida=not data or abs((hoje-dt.date.fromisoformat(data[:10])).days)>30
                if vencida:
                    alerta.append('COTACAO FORA DO PRAZO')
                if not (str(up or '').startswith('https://') and str(uf or '').startswith('https://')):
                    alerta.append('FONTES DA COTACAO NAO DOCUMENTADAS')
            except (ValueError,TypeError):
                alerta.append('VALORES DA COTACAO INVALIDOS')
        else:
            alerta.append('SEM PRECO E CUSTO DE FORNECEDOR')
        if not sinais:
            alerta.append('SEM CORRELACAO COM TENDENCIAS OBSERVADAS')
        # Mesmo com margem e correlacao nao ha prova de vendas ou fornecedores verificados.
        if not sinais or contribuicao is None:
            decisao='DADOS INSUFICIENTES'
        elif Decimal(percentual)<Decimal('15'):
            decisao='MARGEM ABAIXO DA META'
        elif alerta:
            decisao='REVISAR EVIDENCIAS'
        else:
            decisao='CANDIDATO A INVESTIGACAO'
        dossies.append({'codigo':codigo,'produto':nome,'marca':marca,
            'fonte_catalogo':origem,'correlacoes_tendencias':sinais,
            'preco_informado':preco,'custo_informado':custo,
            'margem_contribuicao_estimada_pct':percentual,
            'contribuicao_estimada':contribuicao,
            'urls_cotacao':{'varejo':up,'fornecedor':uf},
            'data_cotacao':data,'decisao':decisao,'alertas':alerta,
            'volume_vendas':'NAO DETERMINADO',
            'verificacao_independente_cotacoes':False})
    return dossies

def salvar(dossies):
    saida=BASE/'decisoes_comerciais.json'
    payload={'gerado_em_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'metodo':'correlacao conservadora de termos; sem IA e sem previsao de vendas',
             'dossies':dossies}
    saida.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    # Formato de entrada para uso futuro no OLYMPUS/DecisionEngine; nao significa execucao.
    entrada=BASE/'entrada_olympus.json'
    entrada.write_text(json.dumps({
        'objetivo':'Avaliar evidencia comercial sem inferir vendas ou lucros nao observados',
        'modelo_executado':False,'motivo':'franquia Ollama Cloud esgotada',
        'instrucoes':'Nao inventar demanda, fornecedores, vendas ou lucro. Exigir fontes.',
        'dossies':dossies},ensure_ascii=False,indent=2),encoding='utf-8')
    pagina=BASE/'inteligencia_comercial.html'
    with pagina.open('w',encoding='utf-8') as f:
        f.write('<!doctype html><html lang="pt-br"><meta charset="utf-8">'
                '<title>OLYMPUS — Decisoes comerciais</title>'
                '<style>body{font:15px Arial;background:#0b1730;color:white;padding:30px}'
                'table{border-collapse:collapse;width:100%}'
                'td,th{border-bottom:1px solid #52617c;padding:10px;text-align:left}'
                'a{color:#93c5fd}</style>'
                '<h1>OLYMPUS — Inteligencia Comercial Integrada</h1>'
                '<p>Produto + tendencias + cotacoes. Sem inferencia de IA, sem estimativa de vendas.</p>'
                '<table><tr><th>Produto</th><th>Sinais relacionados</th>'
                '<th>Margem estimada</th><th>Decisao</th><th>Alertas</th></tr>')
        for d in dossies:
            sinais='; '.join(x['termo'] for x in d['correlacoes_tendencias']) or 'Nenhum'
            col=[d['produto'],sinais,
                 (d['margem_contribuicao_estimada_pct'] or 'N/D')+'%' if d['margem_contribuicao_estimada_pct'] else 'N/D',
                 d['decisao'],'; '.join(d['alertas'])]
            f.write('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in col)+'</tr>')
        f.write('</table></html>')
    return pagina

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sem-rede',action='store_true',help='compatibilidade: nao consulta fontes externas')
    p.parse_args()
    if not DB.exists():
        raise SystemExit('Banco nao encontrado: execute primeiro radar.py e tendencias.py')
    with sqlite3.connect(str(DB)) as con:
        dados=analisar(con)
    pagina=salvar(dados)
    resumo={}
    for d in dados:
        resumo[d['decisao']]=resumo.get(d['decisao'],0)+1
    print('Produtos analisados:',len(dados))
    print('Decisoes:',resumo)
    print('Relatorio:',pagina)
    print('Dossies:',BASE/'decisoes_comerciais.json')
    print('Entrada futura para OLYMPUS:',BASE/'entrada_olympus.json')
    print('IA executada: NAO')

if __name__=='__main__':
    main()
