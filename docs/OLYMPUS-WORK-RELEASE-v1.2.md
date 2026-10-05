# OLYMPUS Work Release v1.2

## Objetivo

Consolidar o fluxo web validado no Mac em uma entrega única, preservando a UX
aprovada e usando somente inferência gratuita.

## Correções consolidadas

- rota estável `openrouter/openrouter/free`, que delega a escolha ao roteador
  gratuito oficial do OpenRouter;
- classificação de pedidos de interface, frontend, página, site e aplicativo
  como tarefas de código;
- normalização de ações com `path` aninhado em `payload`;
- uma tentativa automática de reparo para ações incompletas do modelo;
- suporte seguro a projetos web em `app/`, `src/`, `public/`, `frontend/`,
  `assets/` e arquivos raiz controlados;
- indexação de Python, shell, JavaScript, TypeScript, TSX, HTML, CSS, JSON e
  Markdown para missões posteriores;
- verificação de existência, conteúdo, sintaxe Python, JSON e HTML;
- snapshot isolado do projeto por execução;
- publicação dos arquivos verificados no projeto após conclusão;
- exportação do projeto em ZIP e botão **Baixar resultado (.zip)**;
- inicialização única por `start_olympus.command` e encerramento por
  `stop_olympus.command`.

## Validação

- instalação e imports do núcleo: PASS;
- compilação de todos os módulos Python: PASS;
- sintaxe dos inicializadores shell: PASS;
- missão web simulada completa, incluindo roteador, ação, criação, verificação,
  publicação, persistência e exportação: PASS;
- regressão disponível sem dependências web externas: 512 testes, 0 falhas,
  8 skips previstos.

Os testes HTTP que importam FastAPI/PyJWT dependem do ambiente virtual do
backend. As dependências permanecem fixadas em `backend/requirements.txt` e o
inicializador instala o que estiver ausente antes de subir o aplicativo.
