# OLYMPUS Professional v2.2.1 — Homologação para apresentação

## Objetivo

Homologar o fluxo crítico de uma missão web antes da apresentação a investidores,
com evidência reproduzível desde a seleção de IA até a entrega visualizável e
exportável.

## Entregas

- Ensaio determinístico `scripts/investor_landing_smoke.py`, sem consumo de
  chaves ou créditos externos.
- Simulação de indisponibilidade da primeira rota e fallback automático para um
  segundo provedor, preservando a mesma missão.
- Construção de uma landing page completa do Olympus em português, responsiva,
  acessível e sem dependências externas.
- Rejeição intencional do primeiro rascunho incompleto, seguida de autorreparo e
  nova verificação antes da conclusão.
- Publicação local, duas versões imutáveis, resolução do preview, resposta HTTP
  200, execução da interação do formulário e exportação ZIP.
- Relatório JSON opcional com todos os critérios de aceite por meio de
  `--output DIRETORIO`.

## Correções encontradas pelo ensaio

- O bloqueio de comandos destrutivos não confunde mais o seletor CSS `.form`
  com o comando de terminal `rm`.
- O verificador de placeholders não confunde mais a palavra portuguesa `todo`
  com a marca técnica `TODO`; a marca em maiúsculas continua bloqueada.

## Execução

```bash
PYTHONPATH=.:backend python3 scripts/investor_landing_smoke.py
```

Para preservar a landing page, o ZIP e o relatório do ensaio:

```bash
PYTHONPATH=.:backend python3 scripts/investor_landing_smoke.py \
  --output OLYMPUS-INVESTOR-DEMO
```

## Limites da homologação

O ensaio confirma de forma determinística o núcleo da missão, fallback,
verificação, reparo, publicação, preview, interação, versionamento e download.
Ele não faz chamadas pagas nem depende da disponibilidade momentânea de um
provedor externo. A inicialização completa de Next.js e FastAPI deve ser
confirmada no Mac com as dependências já declaradas no pacote; esta homologação
não instala dependências silenciosamente.

## Critério de conclusão

A versão somente é aprovada quando todas as verificações do ensaio retornam
`true`, a regressão integral passa e o mesmo resultado é reproduzido a partir do
ZIP final extraído em diretório limpo.
