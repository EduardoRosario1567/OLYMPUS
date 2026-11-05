#!/usr/bin/env python3
"""Fila comercial orientada a tendencias; sem inventar vendas nem lucros."""
import argparse
import csv
import datetime as dt
import html
import json
import pathlib
import re
import sqlite3
import unicodedata
from urllib.parse import quote
from radar import DB, BASE

CATEGORIAS = {
    "Eletronicos": {"fone","headset","notebook","mouse","teclado","celular","smartphone",
       "carregador","monitor","tablet","camera","roteador","impressora"},
    "Casa e cozinha": {"luminaria","cadeira","mesa","aspirador","cafeteira",
       "ventilador","liquidificador","geladeira","fogao","microondas",
       "airfryer","panela","organizador","colchao","sofa"},
    "Moda e esporte": {"tenis","mochila","sapato","perfume","bicicleta"},
    "Brinquedos": {"brinquedo","boneca","lego"}
}

def tokens(texto):
    texto = unicodedata.normalize("NFKD", str(texto).casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+",texto))

def classificar(termo, noticias):
    palavras = tokens(termo)
    produtos = [categoria for categoria, vocabulario in CATEGORIAS.items()
                if palavras & vocabulario]
    if not produtos:
        return "ASSUNTO GERAL", "", "Nao ha produto explicito no termo"
    # Uma manchete e um sinal de contexto, nao intencao de comprar.
    if noticias:
        return "ANALISAR CONTEXTO", produtos[0], "Termo de produto com noticias associadas"
    return "INVESTIGAR PRODUTO", produtos[0], "Produto mencionado; confirmar demanda e precos"

def carregar(con):
    existe=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tendencias'").fetchone()
    if not existe:
        return []
    linhas=con.execute("""SELECT termo,volume_aproximado,publicado_em,url,fonte
                     FROM tendencias ORDER BY coletado_em DESC LIMIT 300""").fetchall()
    noticias={}
    path=BASE/"contexto_noticias.json"
    if path.exists():
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data,dict):
                noticias={str(k).casefold():v for k,v in data.items() if isinstance(v,list)}
        except (OSError,ValueError):
            pass
    vistos=set()
    resultado=[]
    for termo,volume,data,url,fonte in linhas:
        key=str(termo).casefold()
        if key in vistos: continue
        vistos.add(key)
        referencias=noticias.get(key,[])
        estado,categoria,motivo=classificar(termo,referencias)
        resultado.append({
            "termo":termo,"volume_google":volume,"publicado_em":data,
            "fonte":fonte,"url":url,"categoria_hipotetica":categoria,
            "triagem":estado,"motivo":motivo,
            "noticias_relacionadas":len(referencias),
            "preco_venda":"NAO DETERMINADO",
            "custo_fornecedor":"NAO DETERMINADO",
            "volume_vendas":"NAO DETERMINADO",
            "lucro":"NAO DETERMINADO"})
    return resultado

def salvar(resultados):
    destino=BASE/"fila_comercial.html"
    (BASE/"fila_comercial.json").write_text(json.dumps({
      "gerado_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "criterio":"Filtro textual conservador. Nao infere demanda ou vendas.",
      "tendencias":resultados},indent=2,ensure_ascii=False),encoding="utf-8")
    with (BASE/"fila_comercial.csv").open("w",encoding="utf-8",newline="") as out:
        w=csv.writer(out)
        w.writerow(["termo","categoria","triagem","buscas_rotulo_google",
                     "noticias_relacionadas","motivo","fonte"])
        for x in resultados:
            w.writerow([x["termo"],x["categoria_hipotetica"],x["triagem"],
                  x["volume_google"],x["noticias_relacionadas"],x["motivo"],x["fonte"]])
    prioridade={"INVESTIGAR PRODUTO":0,"ANALISAR CONTEXTO":1,"ASSUNTO GERAL":2}
    ordenados=sorted(resultados,key=lambda x:(prioridade[x["triagem"]],x["termo"].casefold()))
    with destino.open("w",encoding="utf-8") as f:
        f.write('<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>OLYMPUS Fila Comercial</title>'
                '<style>body{background:#0b1730;color:#fff;font:15px Arial;padding:28px}'
                'table{border-collapse:collapse;width:100%;}th,td{padding:10px;'
                'border-bottom:1px solid #475569;text-align:left;}a{color:#93c5fd}'
                '</style><h1>OLYMPUS — Fila de Investigacao Comercial</h1>'
                '<p>Filtro preliminar de tendencias. Nenhuma linha representa venda comprovada, '
                'fornecedor validado ou oportunidade lucrativa.</p><table>'
                '<tr><th>Pesquisa</th><th>Triagem</th><th>Categoria possivel</th>'
                '<th>Buscas (rotulo Google)</th><th>Noticias</th><th>Motivo</th></tr>')
        for item in ordenados:
            col=[item["termo"],item["triagem"],item["categoria_hipotetica"] or "N/D",
                 item["volume_google"] or "N/D",str(item["noticias_relacionadas"]),item["motivo"]]
            f.write("<tr>"+"".join("<td>"+html.escape(str(v))+"</td>" for v in col)+"</tr>")
        f.write("</table></html>")
    return destino

def main():
    parser=argparse.ArgumentParser()
    parser.parse_args()
    if not DB.exists():
        raise SystemExit("Banco nao encontrado. Execute tendencias.py antes.")
    with sqlite3.connect(str(DB)) as con:
        resultado=carregar(con)
    destino=salvar(resultado)
    resumo={estado:sum(x["triagem"]==estado for x in resultado) for estado in
       ("INVESTIGAR PRODUTO","ANALISAR CONTEXTO","ASSUNTO GERAL")}
    print("Tendencias processadas:",len(resultado))
    print("Triagem:",resumo)
    print("Relatorio:",destino)
    print("Nenhuma oportunidade de lucro foi automaticamente validada.")

if __name__=="__main__":
    main()
