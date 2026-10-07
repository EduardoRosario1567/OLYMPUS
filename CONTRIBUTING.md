# Contribua com o OLYMPUS

Aceitamos ajuda em Python, Next.js/React, provedores, testes, design e documentação.
Você pode começar relatando um problema reproduzível ou propondo uma melhoria.

## Antes de começar

1. Leia o [README](README.md), o [Código de conduta](CODE_OF_CONDUCT.md) e
   [AGENTS.md](AGENTS.md).
2. Consulte as [prioridades](docs/community/ROADMAP.md) e as issues existentes.
3. Abra **Quero contribuir**, **Propor melhoria** ou **Reportar problema** no
   [seletor de issues](https://github.com/EduardoRosario1567/OLYMPUS/issues/new/choose).
4. Para trabalho maior, combine escopo e branch de destino com o mantenedor.
   O padrão é `main`; candidatas de release têm escopo próprio.

O código próprio usa [AGPL-3.0-only](LICENSE). Ao submeter código próprio para
incorporação, indique que sua contribuição pode ser distribuída sob esses
termos. Não há cessão de titularidade ao mantenedor. Não envie código de
terceiros sem identificar sua origem, licença e compatibilidade.

## Fluxo

- Use seu fork e um clone separado da instalação pessoal.
- Crie uma branch por mudança, como `docs/guia-provedores` ou `fix/estado-conexao`.
- Mantenha o diff focado. Evite formatar arquivos não relacionados e alterar
  código de terceiros junto com uma mudança funcional.
- Descreva comportamento antes/depois, reprodução e critérios de aceite.
- Abra um PR com o modelo do repositório. Use rascunho para discutir trabalho
  incompleto. A integração é decidida pelo mantenedor após revisão.

## Critérios de revisão

- Contratos entre decisão, execução e avaliação continuam separados.
- API e interface representam sucesso, falha e bloqueio de forma coerente.
- Credenciais, dados pessoais, projetos, bancos e logs locais ficam fora do diff.
- Mudanças funcionais têm testes de regressão que representam um problema real.
- Mudanças visuais têm evidências em desktop e tela pequena quando aplicável.
- Dependências, migrações, persistência e chamadas externas novas são discutidas
  antes da implementação.
- Atualizações preservam dados e permitem recuperação de falhas.
- Simulações são identificadas; provas reais informam provedor, modelo, commit
  e resultado, sem revelar chaves ou conteúdo privado.

Não execute toda a suíte para corrigir uma frase. Verifique proporcionalmente
à mudança e siga os gates da CI para releases. Veja os comandos em
[Desenvolvimento](docs/community/DEVELOPMENT.md).

## Provedores e custos

Não fornecemos chaves compartilhadas. Use sua própria conta apenas quando o
teste depender do serviço real. Não remova autorização de gasto para passar um
teste. Disponibilidade gratuita depende do provedor; não prometa execução
gratuita sem evidência.

## Assistência de IA

Contribuições com IA são aceitas. O autor deve revisar o código, verificar
fontes/licenças de recursos e executar os testes pertinentes. Informe no PR o
uso de IA quando ajudar a revisão. Nunca envie segredos ou material privado de
terceiros sem autorização a uma ferramenta de IA.

## Reconhecimento

Registre decisões técnicas nas issues e PRs. Créditos permanecem no histórico
das contribuições. O convite é voluntário, não é oferta de emprego nem promessa
de remuneração. Para vulnerabilidades, siga [SECURITY.md](SECURITY.md).
