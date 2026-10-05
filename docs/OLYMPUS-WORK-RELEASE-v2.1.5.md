# OLYMPUS Professional v2.1.5 — conclusão vinculada ao preview

## Falha observada

A missão podia terminar com status `completed` enquanto o relatório de arquivos modificados chegava vazio à etapa de publicação. O arquivo gerado permanecia no workspace da execução, mas não era promovido ao projeto; por isso a interface mostrava “Tudo pronto” e o preview não encontrava uma página.

## Correções

- A publicação reconcilia o relatório do agente com os arquivos realmente alterados no workspace.
- Arquivos recuperados do disco são promovidos e registrados no evento `result_published`.
- Uma missão web somente recebe status concluído quando há HTML seguro e visualizável.
- Uma conclusão sem página é rejeitada e nunca publica uma versão vazia.
- Checkpoints concluídos preservam modelos, arquivos e testes executados.
- Diretórios internos `.olympus` não podem vazar para o projeto publicado.
- Ao iniciar, a versão 2.1.5 localiza resultados concluídos que ficaram presos em workspaces de versões anteriores e os publica automaticamente.

## Homologação interna

- Cenário de relatório vazio com `app/index.html` existente: arquivo recuperado, publicado e aberto pelo preview.
- Cenário de falsa conclusão sem HTML: execução rejeitada e nenhum evento de publicação criado.
- Reinicialização sobre execução legada concluída: HTML recuperado e preview aberto sem repetir a missão.
- Regressão completa: 728 testes aprovados e 14 ignorados.
