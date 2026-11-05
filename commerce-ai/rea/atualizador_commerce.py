#!/usr/bin/env python3
"""OLYMPUS Commerce AI - atualizacao automatica sem servidores.

Modo execucao:
- Processa somente arquivos CSV inseridos pelo operador em entrada_csv/
- Regenera Black Box, Xray e o painel unificado, usando o SQLite existente
- Registra status e datas efetivas dos registros sem fingir nova coleta
- Compativel com Python 3.9 e macOS, sem pacotes adicionais

Modo --instalar:
- Registra LaunchAgent do usuario para executar a cada 6 horas e no login
- Nao faz consultas autenticadas nem coleta automatica de produtos
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import traceback

BASE=pathlib.Path(__file__).resolve().parent
INBOX=BASE/"entrada_csv"
PROCESSED=INBOX/"processados"
DB=BASE/"radar.sqlite3"
STATUS=BASE/"status_atualizacao.json"
LABEL="com.olympus.commerce.refresh"
PLIST=pathlib.Path.home()/"Library"/"LaunchAgents"/(LABEL+".plist")
LOG=pathlib.Path.home()/"Library"/"Logs"/"OLYMPUS-Commerce"/"atualizacao.log"
INTERVAL=6*60*60

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def dates():
    if not DB.exists():return {"produtos_no_banco":0,"data_mais_recente_observacao":None}
    with sqlite3.connect(str(DB)) as con:
        table=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='blackbox_amazon_br'").fetchone()
        if not table:return {"produtos_no_banco":0,"data_mais_recente_observacao":None}
        total,latest=con.execute(
            "SELECT COUNT(DISTINCT asin),MAX(data_observacao) FROM blackbox_amazon_br WHERE marketplace='amazon.com.br'"
        ).fetchone()
        return {"produtos_no_banco":total,"data_mais_recente_observacao":latest}

def write_status(obj):
    temp=STATUS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(str(temp),str(STATUS))

def update():
    import blackbox_br
    import xray_br
    import commerce_integrado

    INBOX.mkdir(parents=True,exist_ok=True)
    PROCESSED.mkdir(parents=True,exist_ok=True)
    initial=dates()
    errors=[]
    imported=0
    files=[]
    collector=BASE/"coletor_amazon_spapi.py"
    amazon="coletor ausente"
    if collector.exists():
        try:
            proc=subprocess.run([sys.executable,str(collector)],cwd=str(BASE),capture_output=True,text=True,timeout=150)
            if proc.returncode:
                raise RuntimeError((proc.stderr or proc.stdout).strip()[:300])
            amazon="consulta concluida" if "Consulta Amazon BR:" in proc.stdout else "nao conectado"
            print("Fonte Amazon:",amazon)
        except Exception as exc:
            amazon="erro de consulta"
            errors.append({"coletor":"Amazon SP-API","erro":str(exc)})
            print("AVISO: Consulta Amazon indisponivel:",str(exc),file=sys.stderr)
    for csvfile in sorted(INBOX.glob("*.csv")):
        try:
            with blackbox_br.connect(DB) as con:
                n=blackbox_br.import_csv(con,csvfile)
            destination=PROCESSED/(dt.datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+csvfile.name)
            if destination.exists():
                raise RuntimeError("Arquivo processado com nome repetido")
            shutil.move(str(csvfile),str(destination))
            imported+=n
            files.append({"arquivo":csvfile.name,"registros":n})
        except Exception as exc:
            errors.append({"arquivo":csvfile.name,"erro":str(exc)})
            print("CSV NAO IMPORTADO:",csvfile.name,str(exc),file=sys.stderr)
    panels={}
    for name,fn in (("blackbox_br","blackbox_br.py"),("xray_br","xray_br.py"),("commerce_integrado","commerce_integrado.py")):
        if not (BASE/fn).exists():
            errors.append({"painel":name,"erro":"Modulo ausente: "+fn})
            continue
        try:
            result=subprocess.run([sys.executable,str(BASE/fn)],cwd=str(BASE),capture_output=True,text=True,timeout=90)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip()[:500])
            panels[name]="gerado"
        except Exception as exc:
            panels[name]="falhou"
            errors.append({"painel":name,"erro":str(exc)})
    after=dates()
    stamp=now()
    result={
        "executado_em_utc":stamp,
        "status":"ERRO" if errors else "OK",
        "fonte_amazon":amazon,
        "csv_importados":files,
        "registros_csv_importados":imported,
        "paineis":panels,
        "antes":initial,
        "depois":after,
        "novos_dados_nesta_execucao":bool(imported),
        "observacao":"Regeneracao de painel NAO equivale a nova coleta na Amazon. Dados mais recentes sao datados pela fonte original.",
        "erros":errors,
    }
    write_status(result)
    print("OLYMPUS |",result["status"],"| CSV:",len(files),"| registros:",imported,
          "| produtos:",after["produtos_no_banco"],
          "| observacao mais recente:",after["data_mais_recente_observacao"])
    print("Status:",STATUS)
    return 1 if errors else 0

def install():
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    LOG.parent.mkdir(parents=True,exist_ok=True)
    payload={
        "Label":LABEL,
        "ProgramArguments":[str(pathlib.Path(sys.executable).resolve()),str(pathlib.Path(__file__).resolve()),"--executar"],
        "WorkingDirectory":str(BASE),
        "RunAtLoad":True,
        "StartInterval":INTERVAL,
        "StandardOutPath":str(LOG),
        "StandardErrorPath":str(LOG),
    }
    PLIST.write_bytes(plistlib.dumps(payload))
    uid=os.getuid()
    domain="gui/"+str(uid)
    subprocess.run(["launchctl","bootout",domain,str(PLIST)],capture_output=True,text=True)
    boot=subprocess.run(["launchctl","bootstrap",domain,str(PLIST)],capture_output=True,text=True)
    if boot.returncode:
        raise RuntimeError("launchctl bootstrap: "+(boot.stderr or boot.stdout).strip())
    print("Agendamento local instalado: inicializacao e a cada 6 horas.")
    print("Plist:",PLIST)
    print("Log:",LOG)
    print("Sem servidor residente. Nao coleta automaticamente novos dados da Amazon.")
    return 0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument("--instalar",action="store_true",help="Cria LaunchAgent com atualizacao a cada 6 horas")
    group.add_argument("--status",action="store_true",help="Exibe ultimo status")
    group.add_argument("--executar",action="store_true",help="Importa CSVs pendentes e regenera paineis")
    args=p.parse_args()
    if args.instalar:
        return install()
    if args.status:
        print(STATUS.read_text(encoding="utf-8") if STATUS.exists() else "Sem execucao registrada")
        return 0
    return update()

if __name__=="__main__":
    try:sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
