# Olympus 3.0.8 — etapa de segurança

Build: `AUDIT-SECURITY-P0`.

A atualização aplica cinco arquivos de runtime, a identificação de build e as regressões desta etapa. Nenhuma dependência ou migração nova. O ajuste visual permanece separado.

| Auditoria | Resultado desta etapa | Limite |
| --- | --- | --- |
| A01 | Variáveis com credenciais, proxies e hooks Python deixam de ser herdadas. Testes usam o Python ativo e HOME temporário. | Não é isolamento de sistema operacional; código de projeto ainda tem as permissões do usuário. A01 permanece parcial até definir e homologar essa execução isolada. |
| A02 | Propriedade verificada antes de parar runtime ou arquivar pasta; busca restrita ao projeto registrado da organização. | Consistência do catálogo em memória é A05, próxima etapa. |
| A03 | Links diretos e em diretórios rejeitados antes da resolução; seleção de entrada também verifica o caminho. | Política CSP preservada; importação de imagens e revisão de concorrência para ambiente público ficam nas etapas seguintes. |
| A04 | Leitor consulta artefatos e não pode criar/excluir. Escrita exige projects.write; isolamento entre organizações preservado. | Limites de conteúdo e validação completa dos identificadores/associação a projetos precisam de revisão própria. |

Verificação interna: 132 testes direcionados, 7 subtestes e 24 testes do atualizador aprovados, incluindo 18 casos próprios de segurança e identificação de build. Dois avisos preexistentes do FastAPI sobre on_event. Não foi repetida a suíte geral nesta correção; a auditoria anterior registrou 20 falhas a revisar. Não há homologação geral, aprovação estética ou prova de execução em Python 3.9 real.

O instalador verifica a base conhecida, a propriedade das portas 8000/3000, integridade do conteúdo, credenciais preservadas e build confirmado nos dois serviços. Guarda backup dos arquivos substituídos, preserva modos e reverte em caso de falha do reinício ou da conferência. Não apaga bancos, projetos, histórico, checkpoints ou configurações de provedores. Usa as dependências já instaladas.

Não confundir rollback do código com recuperação de perda de energia ou isolamento completo de código gerado. A etapa seguinte trata catálogo de projetos e validação contínua; depois, critérios reais de entrega e apresentação.
