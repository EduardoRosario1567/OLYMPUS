#!/usr/bin/env python3
"""REA Evidence: auditar completude sem confundir strings com capacidades."""
import argparse
import json
import pathlib
from html.parser import HTMLParser

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script','noscript'):
            self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('style','script','noscript') and self.skip:
            self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())

def glimpse(value,limit=350):
    if isinstance(value,(list,dict)):
        return str({k:type(v).__name__ for k,v in value.items()})[:limit] if isinstance(value,dict) else "lista (%d)"%len(value)
    return str(value)[:limit]

def audit(data):
    n=data.get('normalized_result',{})
    if not isinstance(n,dict): n={}
    out=[
        'REA / OLYMPUS — Auditoria da captura',
        'id: '+str(data.get('evidence_id')),
        'operacao: '+str(data.get('operation')),
        'autoridade: '+str(data.get('authority')),
        'confianca: '+str(data.get('confidence')),
        'Limites gerais: '+str(len(data.get('limitations') or [])),
        'Secoes: '+', '.join(n.keys())
    ]
    b=n.get('browser',{})
    if isinstance(b,dict):
        out.append('Browser: '+glimpse(b))
    out.append('Completude: '+glimpse(n.get('completeness')))
    steps=n.get('steps',[])
    if not isinstance(steps,list): steps=[]
    out.append('Passos registrados: %d'%len(steps))
    for i,step in enumerate(steps):
        if not isinstance(step,dict): continue
        out.append('PASSO %d: %s'%(i+1,glimpse(step,200)))
        for field in ('step_id','status','action','url','final_url','completeness','error'):
            if field in step:
                out.append('  %s: %s'%(field,glimpse(step[field])))
        for field in ('artifacts','captures','capture','result','snapshot'):
            value=step.get(field)
            if isinstance(value,dict):
                out.append('  %s: %s'%(field,glimpse(value)))
    out.append('ATENCAO: termos isolados em JSON nao provam filtros reais, vendas ou algoritmos.')
    out.append('Uma avaliacao funcional exige o DOM real, estado final da pagina e evidencias de interacoes.')
    return '\n'.join(out)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('evidencia',type=pathlib.Path)
    parser.add_argument('--saida',type=pathlib.Path)
    args=parser.parse_args()
    data=json.loads(args.evidencia.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('operation')!='capture_browser_scenario':
        raise SystemExit('Nao parece ser uma captura REA de navegador')
    report=audit(data)
    if args.saida:
        args.saida.write_text(report+'\n',encoding='utf-8')
    print(report)

if __name__=='__main__':
    main()
