# OLYMPUS Professional v2.0.4 — estabilização do teste no Mac

## Objetivo

Esta entrega corrige os defeitos observados durante o teste real da v2.0.3 e
fornece uma base limpa para o próximo teste ponta a ponta no macOS.

## Correções

- Timeout de modelos gratuitos elevado de 30 para 180 segundos.
- Contrato de ações aceita as variações estruturadas observadas nos modelos.
- Uma resposta HTML completa sem `target` é recuperada somente para tarefas web
  e publicada em `app/index.html`.
- O estado enviado ao planejador inclui arquivos alterados, testes e últimas
  ações, além de instrução explícita para finalizar quando a entrega estiver
  pronta.
- Duas inspeções repetidas de uma alteração já verificada encerram a missão sem
  desperdiçar todo o orçamento.
- Novas missões recebem até 24 iterações.
- Uma execução antiga bloqueada por `iteration budget exhausted` pode ser
  retomada com 24 iterações, preservando os arquivos já criados.
- Backend e frontend são validados separadamente por versão. Um processo Olympus
  antigo só é encerrado depois de ser identificado; processos desconhecidos
  continuam protegidos.
- A marca principal foi substituída por um Zeus humano em perfil, branco,
  transparente e com 1024 × 1024 px. O ativo anterior foi removido.

## Cenário ponta a ponta reproduzido

O teste automatizado reproduz resposta incompleta e esgotamento de orçamento,
retoma a mesma execução, confirma o arquivo preservado, conclui a missão,
publica no projeto, cria as versões anterior e posterior, abre o preview e
exporta o ZIP.

## Condições do teste real

1. Usar somente a pasta limpa desta versão, sem copiar `.venv`, `node_modules`,
   `.olympus` ou `backend/.env` de versões anteriores.
2. macOS com Python 3, Node/npm e OmniRoute instalados.
3. OmniRoute autenticado e respondendo em `127.0.0.1:20128`.
4. Internet disponível e ao menos um modelo atendendo a rota
   `openrouter/openrouter/free` no momento da missão.
5. Backend confirmado como v2.0.4 e frontend confirmado pelo manifesto v2.0.4.
6. Executar uma nova missão de landing page e aguardar a conclusão assíncrona.

O item 4 é uma condição externa: nenhuma versão local pode garantir a capacidade
instantânea de um provedor gratuito. O Olympus agora tolera respostas lentas e
variações de formato; indisponibilidade total do provedor continua sendo
apresentada sem modificar ou perder o projeto.
