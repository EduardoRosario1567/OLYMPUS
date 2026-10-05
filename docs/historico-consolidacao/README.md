# OLYMPUS

## v2.6.2 — Piloto compartilhável para macOS

O pacote piloto pode ser instalado em outro Mac sem transportar projetos,
bancos, logs ou credenciais. A primeira abertura solicita o e-mail e uma senha
local, gera uma chave de sessão exclusiva e cria o ambiente privado daquele Mac.

## v2.6.1 — Hotfix de homologação macOS

O inicializador identifica dinamicamente a versão do pacote, valida Python e
Node antes de instalar dependências e apresenta erros compreensíveis. Consulte
`LEIA-ME-PRIMEIRO.txt` antes do teste em um Mac.

## v2.6.0 — Ecossistema de agentes com fronteiras reais

Esta versão incorpora oito capacidades nativas: Systematic Delivery, Product Sprint, Spec-Driven Development, Context Efficiency, Checkpoint Continuity, Social Media Strategy, Exposure Audit e Answer First. Metodologias públicas foram reescritas como contratos compactos do OLYMPUS; continuidade, economia de contexto, exposição de segredos e comunicação direta permanecem capacidades proprietárias.

A tela de Skills agora diferencia explicitamente contratos de instrução, conectores MCP e aplicativos/bibliotecas. Um nome presente no catálogo nunca é anunciado como integração funcional sem servidor detectado, permissão e teste real.

## v2.5.1 — Offer Engineering e design skills

Esta versão adiciona sete contratos proprietários de execução: Offer Engineering, Emil Design Engineering, UI/UX Pro Max, Web Design Guidelines, Brand Kit, Extract Design System e Image to Code. As seis skills inspiradas em projetos públicos mantêm origem e licença visíveis, mas foram reescritas no formato nativo do OLYMPUS, sem instalar ou executar código externo.

Cada contrato possui gatilhos discriminantes, ações permitidas, restrições, orientação operacional e verificações de conclusão. Dependências internas compõem automaticamente qualidade, acessibilidade, produto, frontend e testes quando necessário.

> **Distribuição:** este repositório e seus ZIPs integrais são artefatos internos
> de desenvolvimento. O produto comercial será Olympus Cloud + Runner público
> verificado + exportação dos projetos do cliente. Consulte
> `docs/OLYMPUS-DISTRIBUTION-POLICY-v1.8.md`.

## Inicialização no macOS

Abra `start_olympus.command` com duplo clique. O inicializador tenta subir o
OmniRoute quando disponível, inicia backend e frontend e então abre
`http://localhost:3000` no navegador. O OmniRoute é opcional: uma falha nele
não impede a abertura do Olympus quando outra IA estiver configurada.
Para encerrar os processos iniciados pelo pacote, abra `stop_olympus.command`.

## Continuidade, Skills e custo controlado

Cada pedido humano é compilado localmente em um contrato curto com objetivo,
restrições e critérios de conclusão. Essa etapa não chama uma IA. Por padrão, o
Olympus usa no máximo três tentativas gratuitas, priorizando provedores
independentes antes de modelos irmãos. Arquivos, testes, erros e requisitos são
transferidos como checkpoint; a IA seguinte continua o trabalho existente.

Abra `configure_ai.command` para configurar OmniRoute/OpenRouter, Groq,
Cerebras, Gemini, Mistral, Z.AI, Cloudflare Workers AI, OpenAI ou Kimi. Depois,
use `IAs e plugins` para ativar somente as rotas desejadas. O catálogo vivo de
modelos substitui os nomes padrão sempre que o provedor o disponibiliza.

As chaves não acompanham o pacote, não aparecem enquanto são digitadas e ficam
somente em `backend/.env`, com permissão local restrita. O Olympus não compra
créditos nem ativa planos.

Na área `IAs e plugins`, o botão `Testar` realiza uma geração mínima real e
distingue uma conta apenas conectada de uma rota pronta para executar. Rotas
pagas só entram quando estiverem configuradas, habilitadas para continuidade e
forem autorizadas na missão. A autorização exige teto estimado positivo; uma
guarda conservadora bloqueia a chamada antes do envio quando a requisição não
cabe no saldo autorizado. A cobrança final continua sendo feita diretamente
pelo provedor conforme a conta do usuário.

A área `Skills` contém os contratos operacionais proprietários do Olympus.
Repositórios públicos do GitHub com `SKILL.md` podem ser importados, mas entram
em quarentena: limite de tamanho, proteção contra travessia de caminho e link
simbólico, análise de instruções críticas e revisão administrativa precedem a
ativação. Código da skill nunca é executado durante a importação.

### Ponte opcional Free Claude Code

O Olympus pode detectar o gateway local do [Free Claude Code](https://github.com/Alishahryar1/free-claude-code) em `127.0.0.1:8082/v1` e incorporar seu catálogo sem abandonar o controle de missão do Olympus. Apenas identificadores explicitamente gratuitos ou locais entram na cadeia gratuita; modelos pagos e de assinatura não são inferidos como gratuitos. O FCC é um projeto independente, distribuído sob licença MIT, e não é instalado silenciosamente pelo Olympus.

O iniciador tenta abrir uma instalação FCC já existente. Use `OLYMPUS_START_FCC=0` para desativar esse comportamento, `FCC_PROXY_TOKEN` quando a autenticação local estiver habilitada e `OLYMPUS_FCC_FREE_MODELS` para definir uma lista exata de modelos gratuitos aprovados.

Saídas extensas de testes são compactadas deterministicamente antes de retornarem ao agente, preservando erros, resumos e início/fim. Essa etapa não chama outra IA e reduz repetição de tokens.

## Reliability Gate v2.5

Cada criação ou alteração de arquivo recebe uma identidade canônica independente
do provedor. Se outro modelo repetir a mesma mutação após um failover, o Olympus
reconhece que ela já foi aplicada e não a executa novamente. O estado compacto da
etapa — arquivos, testes, erros recentes e identidades concluídas — é salvo
atomicamente após cada fronteira de ação e atravessa reinícios e trocas de modelo.

Esse mecanismo não transforma um teste interno em promessa sobre cotas externas.
Ele garante que uma falha externa preserve o progresso e não recomece a missão do
zero.

## Homologação para demonstração

O ensaio determinístico de apresentação percorre o fluxo completo: compilação
local, rascunho na primeira rota, falha técnica, checkpoint entregue a outra IA,
autorreparo,
publicação, versionamento, preview HTTP, interação do formulário e ZIP final.
Ele não consome créditos nem depende de serviços externos:

```bash
PYTHONPATH=.:backend python3 scripts/investor_landing_smoke.py
```

O resultado somente é aprovado quando todas as verificações retornam `true`.

## Gate do núcleo: missão completa

O teste `scripts/core_runtime_e2e.py` atravessa o coração do Olympus com um
servidor OpenAI-compatible local: transporte HTTP do `OmniRouteAdapter`,
falha técnica na primeira rota, failover entre provedores, handoff de
checkpoint, execução limitada, verificação, persistência, publicação,
versionamento, preview e exportação. Ele não usa créditos nem credenciais
externas:

```bash
PYTHONPATH=. python3 scripts/core_runtime_e2e.py
```

O mesmo gate está incluído na regressão completa por meio de
`tests/test_core_runtime_e2e.py`. O relatório da validação atual está em
`docs/CORE-RUNTIME-E2E-REPORT-2026-09-17.md`.

Para validar a malha de fontes, execute também:

```bash
PYTHONPATH=. python3 scripts/provider_matrix_e2e.py
```

Esse ensaio atravessa dez fontes configuradas — OmniRoute, Free Claude Code,
OpenRouter, Groq, Cerebras, Ollama, Gemini, Mistral, Z.AI e Cloudflare Workers
AI — dentro de uma missão única com múltiplos artefatos. O relatório está em
`docs/PROVIDER-MATRIX-E2E-REPORT-2026-09-17.md`.

## Experiência principal

A tela `Nova missão` usa um fluxo conversacional: escolha um projeto, descreva o
resultado e acompanhe a execução no mesmo diálogo. O botão `+` e o gesto de
arrastar e soltar aceitam até 10 anexos por missão e 20 MB por arquivo. São
aceitos arquivos de texto e código, PDF, DOCX, XLSX, imagens e ZIP. Arquivos ZIP
são importados com validação de caminhos; conteúdo textual de documentos é
adicionado ao contexto da missão quando extraível sem OCR.

O botão `Abrir projeto` apresenta um preview isolado nas larguras desktop e
mobile. Cada missão concluída cria versões imutáveis antes e depois da
publicação. No histórico, é possível comparar uma versão com o estado atual e
restaurá-la; o Olympus cria outro backup antes de qualquer restauração.

## Ambiente profissional de construção

O ambiente do projeto reúne conversa, preview, arquivos e versões. Projetos
HTML continuam usando o preview estático protegido. Projetos Next.js, Vite e
React Scripts podem usar preview executável quando as dependências do próprio
projeto já estiverem presentes; o Olympus nunca executa instalação silenciosa.

O preview executável chama diretamente o runtime reconhecido, sem shell e sem
executar scripts arbitrários do `package.json`. Ele usa porta local aleatória,
sessão temporária, limite de dois previews simultâneos e encerramento automático
com o backend. O console é somente leitura, limitado e filtra valores com nomes
sensíveis.

O editor abre somente arquivos textuais UTF-8 de até 1 MB. Segredos, anexos,
dependências, caches, arquivos ocultos e links simbólicos ficam bloqueados.
Cada alteração usa verificação de conflito, gravação atômica e cria um snapshot
antes de substituir o arquivo. O seletor visual permite clicar em um elemento
do preview e levar seu seletor e texto diretamente para uma nova solicitação.

## GitHub e publicação

A aba `Publicar` conecta o projeto a um repositório novo ou existente. A
credencial do GitHub permanece somente na memória da sessão do backend; o
Olympus persiste apenas o proprietário, o repositório, a branch e o estado da
publicação. `.env`, anexos, importações, caches, dependências, diretórios
ocultos e links simbólicos nunca entram na sincronização.

Cada sincronização cria blobs, uma árvore e um único commit atômico. A branch
só avança como fast-forward, sem `force`; se outra pessoa tiver alterado a
referência, a operação para sem sobrescrever o trabalho remoto. Arquivos que
existem apenas no repositório não são apagados automaticamente.

Com a conta conectada, cada missão concluída tenta criar um commit automático.
Falhas do GitHub são registradas como integração pendente, mas não invalidam a
entrega local já verificada. Também é possível criar uma branch ou sincronizar
manualmente pela interface.

`Publicar em um clique` valida primeiro uma raiz HTML estática, sincroniza o
código-fonte e publica os ativos em uma branch isolada `olympus-pages`. O
histórico da branch principal não é substituído. Nesta versão, a publicação
gratuita requer repositório público e atende HTML estático ou builds já
presentes em `dist`/`build`.

Aplicações com backend podem ser publicadas no Railway pela mesma aba. O fluxo
exige que o serviço Railway esteja conectado ao mesmo repositório GitHub. Antes
de cada publicação, o Olympus sincroniza o projeto, gera e valida um artefato
sem segredos, atualiza as variáveis do ambiente sem substituir variáveis
externas e solicita o deploy. O commit informado pelo Railway precisa coincidir
com o commit aprovado; qualquer divergência ou ausência dessa confirmação
interrompe o fluxo sem declarar sucesso.

Tokens do GitHub e Railway e valores de variáveis permanecem apenas na memória
da sessão local. Em produção, esses três tipos de credencial precisam usar um
cofre KMS/Secret Manager. Domínio próprio e rollback ficam limitados ao tenant,
projeto, ambiente e serviço que originaram a publicação.

## Persistência e distribuição segura

Quando `OLYMPUS_RUNNER_SIGNING_KEY` é fornecida pelo cofre do ambiente, o
registro do Runner mantém instalações, hashes de renovação e revogações em
SQLite transacional. A chave não entra no banco e uma troca não coordenada da
chave faz o serviço falhar fechado, evitando aceitar estado com identidade
criptográfica divergente.

O histórico de publicações e o roteamento necessário para domínio e rollback
também persistem transacionalmente. Valores secretos continuam voláteis por
padrão. Para persistência, configure um adaptador KMS por
`OLYMPUS_KMS_PROVIDER=modulo:factory`; o banco recebe somente ciphertext e o
contexto associado. Não existe fallback para chave local ou criptografia
própria.

Releases públicas do Runner usam manifesto canônico, SHA-256 do pacote e
assinatura assimétrica via OpenSSL. O atualizador bloqueia alteração, chave
incorreta, plataforma/arquitetura divergente, downgrade e versão incompatível.
As ferramentas `scripts/sign_runner_release.py` e
`scripts/verify_runner_release.py` foram desenhadas para a CI privada. A chave
privada e as credenciais de assinatura/notarização nunca acompanham o produto.

Código de projeto em preview executável roda localmente com as permissões do
usuário que iniciou o Olympus. Use somente projetos próprios ou de origem
confiável. Isolamento de sistema operacional por contêiner permanece uma etapa
posterior para implantação multiusuário pública.

## Organizações e equipes

O Olympus 2.0 adiciona organizações reais ao isolamento existente. O primeiro
administrador local torna-se proprietário do espaço atual sem mover ou
renomear projetos. Uma pessoa pode participar de mais de uma organização e
trocar o espaço ativo; o token de sessão passa a carregar exatamente a
organização autorizada.

Os papéis são proprietário, administrador, construtor e leitor. As APIs de
projetos, missões, GitHub e Railway aplicam a permissão no servidor — esconder
um botão na interface nunca é considerado autorização. Convites expiram, são
de uso único e somente seu hash é persistido. Senhas de membros usam PBKDF2
com salt individual e não entram em logs ou respostas.

Planos e limites são aplicados antes de missões e publicações. A fundação de
cobrança é neutra em relação ao provedor: somente um adaptador que já tenha
validado a autenticidade do webhook pode alterar assinatura e plano, e o ID do
evento impede processamento duplicado. Esta versão não realiza cobranças nem
inclui preços comerciais; isso exige a escolha formal do provedor e as
credenciais do proprietário.

Alterações administrativas, solicitações de missão e publicação geram uma
trilha encadeada por hash. A API de desenvolvimento anterior usa um banco
global e, por segurança, não é publicada por padrão. Para diagnóstico local
de versões anteriores, ela pode ser ativada conscientemente com
`OLYMPUS_ENABLE_LEGACY_API=1`.

Em `OLYMPUS_ENV=production`, a inicialização falha se o JWT usar a chave de
desenvolvimento, se uma senha administrativa configurada tiver menos de 12
caracteres ou se CORS aceitar qualquer origem.

OLYMPUS is a model-agnostic agent runtime for bounded autonomous software work.

## Canonical runtime

The canonical autonomous path is:

`Human request -> MissionCompiler -> Skill contracts -> AutonomousPatchRunner -> bounded provider chain -> AgentLoop -> ContextEngine -> ModelPlanner -> ActionExecutor -> AgentVerifier -> checkpoint/publish`

Model selection is delegated to `DecisionEngine` through `OlympusModelSelector`. Technical model failures are classified by the runtime and may fail over to the next eligible model. The `AgentLoop` never performs model failover itself; it owns one bounded model attempt.

## Repository layout

- `olympus/agent/` — canonical agent runtime plus V1 compatibility modules
- `olympus/routing/` — replaceable routing contracts/adapters
- `olympus/judge/` — quality evaluation and final confidence
- `olympus/db/` — persistence contracts and implementations
- `backend/` / `frontend/` — product/UI layer
- `contexts/` — bounded context manifests
- `scripts/` — operational entrypoints
- `tests/` — regression and integration suite
- `docs/` — architecture, patch history, and reports

## Local baseline

The project targets Python 3.9+ on macOS. Core optional dependencies are declared in `requirements-core.txt`; backend dependencies remain in `backend/requirements.txt`.

Run local regression:

```bash
PYTHONPATH=. python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Run real OmniRoute integration on the Mac where OmniRoute is listening on `127.0.0.1:20128`:

```bash
RUN_REAL_OMNIROUTE=1 RUN_REAL_AGENT_LOOP=1 PYTHONPATH=. \
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Run an autonomous mission:

```bash
PYTHONPATH=. python3 scripts/olympus_mission.py docs/PATCH.md --root "$PWD" --timeout 30
```

See `docs/OLYMPUS-SOURCE-OF-TRUTH.md` before changing runtime responsibilities.


## Skill x Model x Provider Routing

OLYMPUS now ranks model/provider routes in the context of resolved Skills. Routing is advisory and remains subject to SkillPolicy, ActionNormalizer, Control Plane, sandbox and verification.
