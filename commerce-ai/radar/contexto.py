#!/usr/bin/env python3
"""Contexto jornalistico de tendencias: leitura publica RSS Brasil."""
import csv
import html
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

URL = "https://trends.google.com/trending/rss?geo=BR"
NS = {"ht": "https://trends.google.com/trending/rss"}
BASE = pathlib.Path(__file__).resolve().parent

def parsear(dados):
    raiz = ET.fromstring(dados)
    if raiz.tag != "rss":
        raise ValueError("Resposta nao RSS")
    registros = []
    for item in raiz.findall("./channel/item"):
        termo = (item.findtext("title") or "").strip()
        if not termo:
            continue
        noticias = []
        vistos = set()
        for ni in item.findall("ht:news_item", NS):
            titulo = (ni.findtext("ht:news_item_title", namespaces=NS) or "").strip()
            link = (ni.findtext("ht:news_item_url", namespaces=NS) or "").strip()
            fonte = (ni.findtext("ht:news_item_source", namespaces=NS) or "").strip()
            if titulo and link.startswith("https://") and link not in vistos:
                vistos.add(link)
                noticias.append((titulo[:300], fonte[:100], link[:1500]))
        registros.append((termo[:250], noticias))
    return registros

def salvar(registros):
    pagina = BASE / "contexto_tendencias.html"
    arquivo = BASE / "contexto_tendencias.csv"
    with arquivo.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["termo", "noticias", "observacao"])
        for termo, noticias in registros:
            escritor.writerow([termo, len(noticias), "Cobertura jornalistica, nao vendas"])
    with pagina.open("w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="pt-br"><meta charset="utf-8">')
        f.write('<title>OLYMPUS Contexto</title><style>')
        f.write('body{background:#0b1730;color:#fff;font:15px Arial;padding:30px}')
        f.write('article{background:#172849;padding:16px;margin:14px 0;border-radius:12px}')
        f.write('a{color:#93c5fd}</style><h1>OLYMPUS — Contexto das Tendencias</h1>')
        f.write('<p>Noticias do RSS. Interesse jornalistico nao comprova intencao de compra.</p>')
        for termo, noticias in registros:
            f.write('<article><h2>' + html.escape(termo) + '</h2>')
            if not noticias:
                f.write('<p>Sem noticias associadas no RSS.</p>')
            for titulo, fonte, link in noticias[:4]:
                f.write('<p><a rel="noopener noreferrer" href="' +
                        html.escape(link, quote=True) + '">' +
                        html.escape(titulo) + '</a> — ' +
                        html.escape(fonte) + '</p>')
            f.write('</article>')
        f.write('</html>')
    return pagina

def main():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "OLYMPUS-Commerce-AI/1.2 (research)",
        "Accept": "application/rss+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=25) as resposta:
        dados = resposta.read(2000001)
    if len(dados) > 2000000:
        raise ValueError("RSS excede limite")
    registros = parsear(dados)
    destino = salvar(registros)
    print("Termos analisados:", len(registros))
    print("Com noticias:", sum(bool(n) for _,n in registros))
    print("Relatorio:", destino)

if __name__ == "__main__":
    main()
