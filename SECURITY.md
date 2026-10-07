# Política de segurança

## Relatos

Não publique credenciais, dados pessoais, exploração ou detalhes de uma
vulnerabilidade em uma issue pública.

Se o repositório oferecer **Security → Report a vulnerability**, use esse canal
reservado. Este arquivo não habilita o recurso automaticamente. Se a opção
estiver ausente, abra uma issue apenas solicitando um canal privado ao mantenedor,
sem descrever a falha nem anexar evidências sensíveis. Aguarde o canal antes de
transmitir os detalhes.

No relato privado, informe commit, componente, impacto, reprodução mínima e
possível mitigação. Use apenas ambientes e dados de teste autorizados; não
execute exploração contra contas ou serviços de terceiros.

## Versões e limites

O projeto não possui SLA de segurança ou suporte de longo prazo. Relatos devem
identificar o commit afetado; o mantenedor avalia correções em `main` e candidatas
ativas. Não se assume que instalações antigas tenham recebido correções atuais.

## Dados privados

Não versione chaves de provedores, tokens, senhas, `.env` reais, chaves privadas,
bancos, históricos, checkpoints, projetos pessoais ou prints com dados sensíveis.
Use exemplos sem valores reais e revise anexos. O `.gitignore` não remove
arquivos já versionados e não substitui a revisão do histórico antes da divulgação.
