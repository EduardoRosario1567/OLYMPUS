# Contribua com o OLYMPUS

## Procuramos colaboradores / Contributors welcome

O OLYMPUS busca tornar possível pedir sites e aplicativos em linguagem natural e receber arquivos funcionais, testes e uma entrega utilizável, com liberdade de provedores e atenção ao custo de tokens. Procuramos pessoas que queiram contribuir com engenharia, testes, UX e documentação. Não há promessa de remuneração; qualquer proposta comercial precisa ser combinada separadamente com o mantenedor.

**Estado em 21/10/2026:** projeto experimental, com componentes implementados e validações parciais. Ainda não comprovamos o fluxo nativo completo de solicitação → geração → testes → publicação. O isolamento da execução é um bloqueio conhecido. Não apresentar o projeto como plataforma pronta para produção.

## Onde sua contribuição faz diferença

| Frente | Primeiro resultado útil | Critério de aceitação |
| --- | --- | --- |
| Execução isolada (A01) | Proposta pequena e reproduzível para executar código em sandbox | Limites de tempo/recursos, proteção de credenciais, isolamento de arquivos e testes negativos documentados |
| Open Lovable e motores existentes | Avaliar uma versão fixada do upstream, antes de ampliar a integração | Pedido e alteração reais, arquivos gerados, build e limitações registrados; não assumir equivalência com Lovable comercial |
| Missão ponta a ponta | Uma missão pequena desde projeto vazio | Registro das chamadas reais, artefatos, testes independentes, intervenção manual declarada e entrega verificável |
| Provedores e economia | Medir uma tarefa com provedores já suportados | Modelo, tentativas, tokens e custo efetivamente informado pelo provedor; sem fallback pago silencioso |
| QA e experiência | Reproduzir um defeito ou testar desktop/mobile | Passos, versão/branch, resultado esperado e observado; evidência sem dados sensíveis |
| Documentação | Corrigir um passo de instalação ou explicar arquitetura | Instruções reproduzíveis e distinção entre recurso planejado e validado |

Essas são frentes para discussão, não tarefas já atribuídas nem decisões de arquitetura aprovadas. Priorizar uma entrega pequena comprovada em vez de adicionar camadas ou modelos.

## Como começar

1. Consulte as [issues existentes](https://github.com/EduardoRosario1567/OLYMPUS/issues) para evitar duplicação.
2. [Abra uma issue](https://github.com/EduardoRosario1567/OLYMPUS/issues/new) com o título **[Colaboração] área de interesse**. Informe experiência relevante, contribuição proposta, disponibilidade aproximada e um primeiro resultado pequeno. Não publique telefone, e-mail privado ou credenciais.
3. Indique a branch e o commit avaliados. `main` mantém uma base anterior; trabalhos de nuvem e Open Lovable também estão em `feature/olympus-cloud-private-beta`. Confirme o alvo com o mantenedor antes de implementar.
4. Para código, use fork/branch própria e abra um pull request com problema, alteração, testes executados e limitações. Mudanças de dependências, infraestrutura, banco ou arquitetura precisam de alinhamento prévio.

Também são bem-vindas contribuições pequenas de documentação e relatos reproduzíveis, sem compromisso de longo prazo. Não é necessário acesso às contas ou chaves do mantenedor para iniciar.

## Regras de contribuição

- Leia [AGENTS.md](AGENTS.md), especialmente se utilizar agentes de IA.
- Preserve a separação entre núcleo de decisão, execução e avaliação; roteamento deve continuar substituível.
- Não inclua segredos, dumps de banco, dados pessoais, logs com tokens nem dados reais de clientes. Use dados claramente marcados como DEMO.
- Não desative controles de isolamento ou permissões para fazer uma demonstração passar.
- Registre testes realmente executados. Simulação, build aprovado e avaliação visual são evidências diferentes.
- Mantenha alterações focadas e evite refatorações sem relação com a contribuição.
- Antes de incorporar código externo, verifique sua licença e atribuição; não presuma autorização apenas porque um repositório é público.

## English

OLYMPUS welcomes contributors interested in a personal, provider-flexible AI app-building workflow with measurable costs. The project is experimental: native end-to-end generation, independent testing and publication have not yet been demonstrated together. Execution isolation is a known blocker. We especially welcome reproducible sandbox evaluations, Open Lovable integration assessments, small end-to-end missions, provider cost measurements, QA and documentation. Start with a GitHub issue titled **[Collaboration] your area**, propose one small verifiable outcome, and confirm the target branch before implementation. Do not share credentials or assume paid work is offered.
