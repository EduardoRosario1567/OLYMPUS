#!/usr/bin/env python3
"""Create one Mac-local Olympus identity without shipping default secrets."""

import argparse
import getpass
import os
import re
import secrets
import tempfile
from pathlib import Path


def validate_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Informe um e-mail válido.")
    return email


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 12:
        raise ValueError("A senha precisa ter pelo menos 12 caracteres.")
    if password.lower() in {"troque-isto", "admin12345678", "123456789012"}:
        raise ValueError("Escolha uma senha diferente do exemplo ou de sequências simples.")
    return password


def render_environment(template: str, email: str, password: str, jwt_secret: str) -> str:
    replacements = {
        "OLYMPUS_ADMIN_EMAIL": email,
        "OLYMPUS_ADMIN_SENHA": password,
        "OLYMPUS_JWT_SECRET": jwt_secret,
    }
    rendered = []
    found = set()
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in replacements:
            rendered.append("%s=%s" % (key, replacements[key]))
            found.add(key)
        else:
            rendered.append(line)
    missing = tuple(key for key in replacements if key not in found)
    if missing:
        raise ValueError("Modelo de configuração incompleto: %s" % ", ".join(missing))
    return "\n".join(rendered).rstrip() + "\n"


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".olympus-env-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    template_path = Path(args.template).resolve()
    output_path = Path(args.output).resolve()
    if output_path.exists():
        print("Configuração local já existe; nenhuma credencial foi alterada.")
        return 0

    print("\n=== PRIMEIRO ACESSO AO OLYMPUS ===")
    print("Crie as credenciais que serão usadas somente neste Mac.\n")
    try:
        email = validate_email(input("E-mail de acesso: "))
        password = validate_password(getpass.getpass("Senha (mínimo 12 caracteres): "))
        confirmation = getpass.getpass("Confirme a senha: ")
        if password != confirmation:
            raise ValueError("As senhas informadas são diferentes.")
        template = template_path.read_text(encoding="utf-8")
        content = render_environment(template, email, password, secrets.token_urlsafe(48))
        write_private(output_path, content)
    except (EOFError, KeyboardInterrupt):
        print("\nCadastro cancelado.")
        return 1
    except (OSError, ValueError) as exc:
        print("ERRO:", exc)
        return 1

    print("\nCADASTRO LOCAL: PASS")
    print("E-mail:", email)
    print("A senha e a chave de sessão não serão exibidas nem compartilhadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
