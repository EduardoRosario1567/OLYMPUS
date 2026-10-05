# OLYMPUS Professional v2.1.4 — ação incompleta recuperável

## Diagnóstico

A rota respondeu, mas o planejador recebeu uma ação sem destino válido. Esse erro era classificado como lógico e encerrava toda a missão, embora fosse uma falha recuperável de formato do modelo.

## Correção

- Para tarefas web, uma resposta com documento HTML completo e `target: null` é recuperada com segurança para `app/index.html`.
- Respostas ainda malformadas, sem tipo de ação ou sem destino passam a ser falhas técnicas recuperáveis.
- O controle da missão preserva o checkpoint e tenta o próximo modelo automaticamente.
- As correções de quota, Qwen disponível e exclusão padrão da Cerebras da versão 2.1.3 permanecem ativas.

## Homologação interna

- Teste autônomo completo: primeiro modelo retorna duas instruções incompletas; segundo modelo cria o código, cria o teste, executa o teste e conclui a missão.
- Teste de página: documento HTML completo com `target: null` é salvo no destino correto.
- Regressão completa: 725 testes aprovados e 14 ignorados.
