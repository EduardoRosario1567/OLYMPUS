#!/usr/bin/env python3
"""Safely configure optional independent AI provider credentials."""
from getpass import getpass
from pathlib import Path
import os
import shutil
import tempfile


MANAGED_KEYS = (
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY",
    "ZAI_API_KEY", "CLOUDFLARE_API_KEY", "KIMI_API_KEY",
    "OPENCODE_API_KEY",
    "OLYMPUS_CLOUDFLARE_URL", "FCC_PROXY_TOKEN",
    "HIGGSFIELD_API_KEY_ID", "HIGGSFIELD_API_KEY_SECRET",
)


def update_env(path: Path, updates: dict[str, str]) -> None:
    """Atomically update only managed keys and lock the resulting file."""
    path = path.resolve()
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    remaining = dict(updates)
    output = []
    for line in original.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            output.append("%s=%s" % (key, remaining.pop(key)))
        else:
            output.append(line)
    if remaining:
        if output and output[-1]:
            output.append("")
        output.append("# Provedores gratuitos independentes configurados localmente")
        output.extend("%s=%s" % item for item in remaining.items())
    payload = ("\n".join(output).rstrip() + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".olympus-env-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
    finally:
        os.close(descriptor)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    env_path = root / "backend" / ".env"
    example = root / "backend" / ".env.example"
    if not env_path.exists():
        shutil.copyfile(example, env_path)
        os.chmod(env_path, 0o600)

    print("OLYMPUS — Central de IAs")
    print("A chave não aparece na tela e fica somente neste Mac.")
    print("ENTER mantém o valor atual. Digite REMOVER para apagar uma chave.\n")
    updates = {}
    for key, label in (
        ("GROQ_API_KEY", "Chave gratuita Groq"),
        ("CEREBRAS_API_KEY", "Chave Cerebras (pode exigir quota paga)"),
        ("OPENROUTER_API_KEY", "Chave OpenRouter direta"),
        ("OPENAI_API_KEY", "Chave OpenAI"),
        ("GEMINI_API_KEY", "Chave Google Gemini"),
        ("MISTRAL_API_KEY", "Chave Mistral AI"),
        ("ZAI_API_KEY", "Chave Z.AI"),
        ("CLOUDFLARE_API_KEY", "Token Cloudflare Workers AI"),
        ("KIMI_API_KEY", "Chave Kimi (paga)"),
        ("OPENCODE_API_KEY", "Chave OpenCode Zen (modelos gratuitos e pagos)"),
        ("FCC_PROXY_TOKEN", "Token local do Free Claude Code, se a proteção do proxy estiver ativa"),
        ("HIGGSFIELD_API_KEY_ID", "ID da chave Higgsfield API (opcional, mídia paga)"),
        ("HIGGSFIELD_API_KEY_SECRET", "Segredo da chave Higgsfield API (opcional, mídia paga)"),
    ):
        value = getpass("%s: " % label).strip()
        if not value:
            continue
        updates[key] = "" if value.upper() == "REMOVER" else value
    cloudflare_url = input("URL OpenAI compatível da conta Cloudflare (opcional): ").strip()
    if cloudflare_url:
        updates["OLYMPUS_CLOUDFLARE_URL"] = "" if cloudflare_url.upper() == "REMOVER" else cloudflare_url
    if not updates:
        print("Nenhuma alteração realizada.")
        return 0
    update_env(env_path, updates)
    print("Configuração salva com permissão restrita. Reinicie o Olympus para ativá-la.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
