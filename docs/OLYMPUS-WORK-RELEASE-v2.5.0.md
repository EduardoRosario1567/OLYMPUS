# OLYMPUS Work v2.5.0 — Reliability Gate

## Objetivo

Impedir que o failover entre modelos repita trabalho concluído ou perca o estado
da etapa ativa.

## Contrato implementado

- toda ação de criação ou alteração de arquivo possui identidade SHA-256 canônica;
- a identidade depende de tipo, destino e conteúdo, não do provedor;
- mutações concluídas são registradas no estado portátil da missão;
- uma mutação idêntica proposta por outro modelo é reconhecida e ignorada;
- arquivos lidos e modificados, testes, modelo, erros recentes e identidades de
  ação são persistidos atomicamente após cada fronteira de ação;
- checkpoints intermediários sobrevivem a uma exceção do runtime;
- o próximo modelo recebe o progresso compacto e não a obrigação de reiniciar.

## Aceite executado

- regressão completa do repositório;
- testes específicos de identidade, repetição e checkpoint intermediário;
- smoke determinístico de landing page com failover entre provedores;
- publicação, versionamento, preview HTTP, interação, responsividade,
  acessibilidade e ZIP final.

## Limite honesto

Esta versão protege continuidade e evita repetição de mutações. Disponibilidade,
cotas, qualidade e compatibilidade de modelos externos continuam dependendo de
cada provedor e precisam ser verificadas no Mac antes de uma demonstração ao vivo.
