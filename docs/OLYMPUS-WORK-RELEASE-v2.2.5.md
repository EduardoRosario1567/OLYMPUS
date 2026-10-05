# OLYMPUS Work v2.2.5

## Correção de prioridade operacional

- A ordem definida em **IAs e plugins** agora controla a ordem real das tentativas da missão.
- Um número menor continua significando tentativa mais cedo, tanto na interface quanto no motor.
- Desativar **Usar no fallback automático** no OmniRoute agora o remove das rotas da missão.
- A preferência visual e a seleção do `DecisionEngine` possuem testes de regressão dedicados.

## Cenário validado

Com Groq em prioridade 5 e OmniRoute em prioridade 10, o primeiro candidato real é um modelo Groq disponível; o roteador OmniRoute passa a ser a alternativa seguinte.
