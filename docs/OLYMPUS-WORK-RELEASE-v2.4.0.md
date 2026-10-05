# OLYMPUS Work v2.4.0

## Objetivo

Ampliar a disponibilidade de modelos sem quebrar o controle proprietário de missão, checkpoint, Skills e autorização de gasto do Olympus.

## Ponte Free Claude Code

- provedor local opcional `fcc` em `http://127.0.0.1:8082/v1`;
- descoberta do catálogo vivo via API compatível;
- inicialização automática apenas quando o FCC já estiver instalado;
- suporte opcional a proxy protegido por `FCC_PROXY_TOKEN`;
- nenhuma instalação externa silenciosa;
- nenhuma chave incluída no pacote;
- somente modelos com identidade gratuita/local entram no fallback gratuito;
- lista exata opcional por `OLYMPUS_FCC_FREE_MODELS`;
- modelos pagos ou de assinatura do FCC não são tratados como gratuitos.

O Free Claude Code permanece um projeto independente e não substitui o agente Olympus. A integração utiliza apenas seu gateway público local; o compilador de missão, a seleção, os checkpoints, a verificação e a política financeira continuam sob controle do Olympus.

## Economia de contexto

Saídas longas de testes são compactadas localmente e sem IA. O algoritmo preserva início, fim e linhas diagnósticas, remove repetição e aplica limites de caracteres e linhas antes de devolver o resultado ao próximo ciclo do agente.

## Limites honestos

- disponibilidade e franquias são definidas por cada provedor e podem mudar;
- “gratuito” não significa capacidade garantida;
- o FCC precisa ser instalado separadamente pelo responsável pelo Mac;
- o Olympus não habilita automaticamente um modelo FCC cuja gratuidade não possa ser identificada;
- a homologação local não substitui uma execução real no Mac com as contas escolhidas.

## Referência

Projeto independente: https://github.com/Alishahryar1/free-claude-code — licença MIT conforme o repositório consultado em 12/09/2026.
