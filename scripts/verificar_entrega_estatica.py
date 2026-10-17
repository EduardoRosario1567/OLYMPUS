#!/usr/bin/env python3
"""OLYMPUS: deterministic static-delivery gate. Never executes generated code.

Usage: python3 scripts/verificar_entrega_estatica.py entregas/rosales-cafe
Only reads source files. Reports DONE/BLOCKED as JSON and exits 0/1.
"""
import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

ALLOWED = {".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
           ".webp", ".gif", ".ico", ".txt", ".woff", ".woff2"}
MAX_FILES = 120
MAX_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
DISALLOWED_HTML = re.compile(r"<\s*(?:iframe|object|embed|base)\b", re.I)
UNSAFE_JS = re.compile(r"\b(?:eval|new\s+Function)\s*\(", re.I)
REMOTE_REF = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", re.I)


REMOTE_CSS = re.compile(r"""(?:@import\s+|url\(\s*["']?)\s*(?:https?:)?//""", re.I)
REMOTE_SCRIPT = re.compile(r"""\b(?:fetch|importScripts)\s*\(\s*["']\s*(?:https?:)?//""", re.I)

def verify(directory, root):
    issues = []
    base = Path(root).expanduser().resolve()
    target = Path(directory).expanduser().absolute()
    try:
        relative = target.relative_to(base)
    except ValueError:
        return ["Entrega fora da pasta autorizada"], 0
    if not relative.parts or ".." in relative.parts:
        return ["Pasta de entrega invalida"], 0
    if target.is_symlink() or not target.is_dir():
        return ["Pasta ausente ou link simbolico"], 0
    count = total = 0
    index_found = False
    for current, dirs, files in os.walk(target, followlinks=False):
        dirs.sort()
        files.sort()
        for dirname in list(dirs):
            item = Path(current) / dirname
            if item.is_symlink():
                issues.append("Diretorio simbolico proibido: " + str(item.relative_to(target)))
                dirs.remove(dirname)
        for filename in files:
            path = Path(current) / filename
            rel = str(path.relative_to(target))
            try:
                info = path.lstat()
            except OSError:
                issues.append("Arquivo inacessivel: " + rel)
                continue
            if not stat.S_ISREG(info.st_mode):
                issues.append("Arquivo especial ou link proibido: " + rel)
                continue
            count += 1
            total += info.st_size
            if path.suffix.lower() not in ALLOWED:
                issues.append("Extensao nao permitida: " + rel)
            if info.st_size > MAX_FILE_BYTES:
                issues.append("Arquivo muito grande: " + rel)
            if rel == "index.html":
                index_found = True
            if path.suffix.lower() not in {".html", ".js", ".css"} or info.st_size > MAX_FILE_BYTES:
                continue
            try:
                data = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                issues.append("Texto invalido: " + rel)
                continue
            if path.suffix.lower() == ".html":
                if DISALLOWED_HTML.search(data):
                    issues.append("Elemento HTML bloqueado: " + rel)
                if REMOTE_REF.search(data):
                    issues.append("Recurso externo nao aprovado: " + rel)
            if path.suffix.lower() == ".css" and REMOTE_CSS.search(data):
                issues.append("Recurso CSS externo proibido: " + rel)
            if path.suffix.lower() == ".js" and REMOTE_SCRIPT.search(data):
                issues.append("Recurso JS externo proibido: " + rel)
            if path.suffix.lower() == ".js" and UNSAFE_JS.search(data):
                issues.append("Execucao dinamica insegura: " + rel)
    if not index_found:
        issues.append("index.html obrigatorio na raiz")
    if count > MAX_FILES:
        issues.append("Quantidade de arquivos excedida")
    if total > MAX_BYTES:
        issues.append("Tamanho total excedido")
    if count == 0:
        issues.append("Entrega vazia")
    return sorted(set(issues)), count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="Diretorio de entrega")
    parser.add_argument("--root", default="entregas", help="Raiz permitida")
    args = parser.parse_args()
    issues, count = verify(args.directory, args.root)
    result = {"status": "BLOCKED" if issues else "DONE",
              "files_checked": count, "issues": issues,
              "note": "Validacao estatica; nao comprova qualidade visual, seguranca de navegador ou execucao de IA"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
