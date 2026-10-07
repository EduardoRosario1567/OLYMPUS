# Preparação para divulgar a comunidade

## Convite pronto para uso

> Estamos abrindo espaço para desenvolvedores interessados em evoluir o OLYMPUS,
> uma ferramenta multi-IA para planejar, executar e verificar entregas. Buscamos
> contribuições em Python, Next.js/React, provedores, testes, acessibilidade,
> design e documentação. O projeto está em desenvolvimento ativo: queremos
> construir qualidade com casos reproduzíveis, revisão e evidências. Consulte
> o guia de contribuição e abra uma issue “Quero contribuir” para combinar uma
> primeira tarefa.

Repositório: https://github.com/EduardoRosario1567/OLYMPUS

Descrição sugerida:
“Ferramenta multi-IA para planejar, executar e verificar entregas. Em desenvolvimento ativo — colaboradores são bem-vindos.”

Topics sugeridos: `python`, `fastapi`, `nextjs`, `react`, `ai-agents`, `llm`,
`ollama`, `developer-tools`.

## Antes da divulgação ampla

1. Conferir a licença AGPL-3.0-only preparada e a compatibilidade dos componentes de terceiros.
2. Definir canal privado para segurança e conduta; habilitar relato privado de
   vulnerabilidades no GitHub, se disponível.
3. Revisar histórico e arquivos das branches a divulgar para segredos e dados
   privados. O `.gitignore` não saneia histórico existente.
4. Integrar os materiais na branch padrão para os formulários aparecerem.
5. Criar labels e primeiras tarefas pequenas com escopo e aceite acordados.
6. Configurar revisão e checks na proteção de `main`, conforme recursos da conta.

Consulta em 2026-10-07: o GitHub informa repositório **público**, issues
habilitadas e ainda sem licença publicada. AGPL-3.0-only foi escolhida pelo
mantenedor e preparada neste pacote. Esta preparação não alterou visibilidade,
permissões, branches remotas, configuração ou versão do aplicativo.

## Aplicar o pacote de documentação

O patch foi preparado sobre `main` no commit
`e06fc1c39f067d30eb0d575f568a8be9b857547f`. Em clone limpo:

```bash
git switch -c docs/community-onboarding
git apply --check /caminho/OLYMPUS-COMUNIDADE.patch
git apply /caminho/OLYMPUS-COMUNIDADE.patch
git diff --check
```

Se o check falhar, reconcilie os arquivos atuais; não force a aplicação. Depois
de revisar, o mantenedor pode publicar a branch e abrir PR. O pacote não instala
nem reinicia serviços.
