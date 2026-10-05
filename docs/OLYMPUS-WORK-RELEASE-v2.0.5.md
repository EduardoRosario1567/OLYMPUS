# OLYMPUS Professional v2.0.5 — failover gratuito automático

## Evidência do teste real

No Mac, a primeira chamada de uma missão expirou após 180 segundos. Uma chamada
direta imediatamente posterior para a mesma rota respondeu `OK`. Isso confirmou
que o backend, o OmniRoute e a autenticação estavam corretos, mas o controle de
execução encerrou cedo demais diante de uma indisponibilidade transitória.

## Correção

- A rota `openrouter/openrouter/free` continua sendo o único identificador
  estável usado pelo Olympus.
- Como essa rota escolhe dinamicamente uma IA gratuita em cada requisição, uma
  falha técnica agora dispara automaticamente outra chamada à rota.
- São permitidas até três tentativas totais por etapa, sempre limitadas.
- Timeout, limite de uso, conexão e indisponibilidade acionam o failover.
- Falhas lógicas, de validação ou de segurança não são repetidas silenciosamente.
- Arquivos alterados, testes e iteração atual são preservados entre tentativas.
- O usuário só recebe interrupção depois que as três alternativas técnicas se
  esgotarem.
- O reconhecimento seguro de processos Olympus antigos nas portas 8000 e 3000
  foi ajustado para permitir atualização automática entre versões.

## Cenário reproduzido

O teste automatizado faz a primeira IA expirar, faz a chamada seguinte responder,
cria `app/index.html`, verifica o resultado, conclui a missão e publica o arquivo
no projeto sem intervenção do usuário.
