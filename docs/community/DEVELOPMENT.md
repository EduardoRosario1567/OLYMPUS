# Ambiente de desenvolvimento

Guia para **clone novo de desenvolvimento**, não para atualizar uma instalação
pessoal. Não reutilize bancos, `.env` ou projetos de produção. Os comandos usam
um shell compatível com Bash em macOS/Linux.

## Requisitos e clone

- Git, Python 3.11, npm e Node.js compatível com `frontend/package.json`.
  A candidata 3.0.9 usa Node 24 na CI; a CI antiga de `main` referencia Node 20.
- Provedores e OmniRoute são opcionais para documentação e testes controlados.
- Docker e isolamento dependem da branch/gate. Consulte os workflows antes de
  executar código gerado; não desative isolamento para contornar falhas.

```bash
git clone https://github.com/EduardoRosario1567/OLYMPUS.git OLYMPUS-dev
cd OLYMPUS-dev
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-core.txt -r backend/requirements.txt pytest
```

Para enviar código, clone seu fork e configure o original como `upstream`.
Leia a licença AGPL-3.0-only e preserve os avisos de terceiros.

## Configuração privada

O comando existente solicita credenciais locais e cria segredo de sessão
aleatório; não substitui configuração existente:

```bash
python scripts/first_run_setup.py --template backend/.env.example --output backend/.env
```

Use credenciais de desenvolvimento. O backend carrega `backend/.env`.
Na interface, crie a configuração apenas se ausente:

```bash
cd frontend
npm ci
test -f .env.local || printf '%s\n' 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000' > .env.local
```

## Iniciar serviços

Na raiz, com o ambiente virtual ativado:

```bash
PYTHONPATH=.:backend python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Em outro terminal, em `frontend/`:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Abra `http://localhost:3000`; saúde da API em `http://localhost:8000/health`.
Se as portas estiverem ocupadas, não encerre processos de outra instalação.
Use ambiente separado e ajuste URL da API e origens CORS coerentemente.

## Verificações

Exemplo de teste controlado do classificador, na raiz:

```bash
PYTHONPATH=.:backend python -m pytest tests/test_classifier_agent_intent.py -q
```

Para outra mudança, escolha o teste correspondente. A suíte completa usa:

```bash
PYTHONPATH=.:backend python -m pytest tests/ -q
```

Na pasta `frontend/`:

```bash
npm run lint
npm run build
```

`lint` é o TypeScript (`tsc --noEmit`) nesta base. Gates de navegador e
isolamento exigem preparação específica descrita nos workflows. Os exemplos
não prometem que toda a suíte rode sem Docker, navegador ou fixtures adicionais.

Registre commit, comandos, resultado e limitações no PR. Identifique provedor e
modelo em testes reais, sem revelar segredos. Missão concluída exige conferir
arquivos e critérios de aceite, além do término do processo.
