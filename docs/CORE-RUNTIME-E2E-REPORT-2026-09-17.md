# OLYMPUS — validação do núcleo do runtime

**Data:** 2026-09-17  
**Status:** PASS

## Escopo

Esta validação cobre o caminho operacional completo do Olympus, e não a tela
HTML isolada:

`missão humana → compilação → rota HTTP → execução → falha técnica → failover → checkpoint → verificação → persistência → publicação → preview → ZIP`

O cenário usa um servidor OpenAI-compatible local controlado pelo teste. Assim,
o transporte é real e determinístico, mas a validação não depende de cotas,
credenciais ou disponibilidade de um provedor externo.

## Evidências executadas

```text
808 testes descobertos; OK (skipped=4)
compileall: PASS
frontend `npm run build`: PASS
scripts/core_runtime_e2e.py: PASS
```

O teste ponta a ponta confirmou:

- a rota primária foi chamada e falhou com HTTP 429;
- o controle de missão transferiu o checkpoint para outra rota/provedor;
- a segunda rota corrigiu o arquivo e concluiu a missão;
- o verificador aceitou o resultado final;
- o checkpoint terminou como `completed` e preservou as rotas utilizadas;
- o resultado foi persistido, versionado, aberto em preview e exportado em ZIP.

## Correção aplicada no coração

O `OmniRouteAdapter` agora identifica uma rejeição de formato causada por
`max_tokens` acima do limite informado pelo provedor. Ele reduz o teto para o
valor explicitamente reportado e repete **uma única vez no mesmo modelo**.

Isso impede que uma limitação de saída seja confundida com indisponibilidade de
modelo, evitando failover prematuro e preservando a continuidade da missão.
O comportamento possui teste de regressão dedicado.

## Repetição

No Mac, com o pacote aberto na raiz:

```bash
./VALIDAR-NUCLEO.command
```

Para a homologação externa, ainda é necessário executar a suíte real com o
OmniRoute local e as contas escolhidas:

```bash
RUN_REAL_OMNIROUTE=1 RUN_REAL_AGENT_LOOP=1 PYTHONPATH=. \
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Essa última etapa mede dependências que não podem ser reproduzidas com
segurança no ambiente local: processo OmniRoute, catálogo real, quotas,
autenticação e disponibilidade dos provedores.
