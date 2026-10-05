# Olympus 3.0.8 — catálogo corrigido

Build `AUDIT-CATALOG-P1`. Base unificada com as correções de segurança e de
consistência do catálogo. O ajuste visual continua reservado à etapa posterior.

A atualização única está em `../ATUALIZAR-CATALOGO-OLYMPUS.txt`: aceita a base
3.0.8 auditada e a base com segurança corrigida. Usa as dependências existentes,
cria backup, reinicia pelo inicializador instalado e confirma o build nos dois
serviços. Preserve bancos, projetos, credenciais e histórico da instalação.

O pacote de fonte inclui as regressões. A atualização no Terminal aplica apenas
sete arquivos Python e a identificação de build do frontend. Nenhuma dependência,
migração ou alteração de dados é acrescentada à instalação.

Validação desta etapa: 103 testes direcionados e 25 testes do atualizador; análise
sintática para Python 3.9, execução interna em Python 3.12 e Mac simulado. Não há
confirmação de instalação real no Mac. Dois avisos anteriores de depreciação do
FastAPI permanecem. A suíte geral anterior registrou 20 falhas, ainda em revisão.
A01 continua parcial: execução de código ainda requer isolamento de arquivos/rede.

O catálogo é sincronizado pelo gestor de projetos no processo do servidor.
Concorrência entre múltiplos processos e perda de energia não são homologadas.
Histórico de execução e arquivos de projetos excluídos ficam preservados em arquivo
recuperável. Cada alteração do catálogo guarda um backup distinto.

Componentes: olympus/ (núcleo), backend/ (APIs), frontend/ (interface), tests/
(regressões), docs/ (referências) e vendor/superpowers/6.4.2/ (inalterado).
Caches, dependências instaladas, bancos, logs e credenciais não integram esta fonte.
Os modelos de configuração não contêm segredos. Consulte AGENTS.md e
`../auditoria/RELATORIO-CATALOGO-OLYMPUS.html` para o escopo e os limites.

Os instaladores herdados permanecem como referência histórica. Para esta etapa,
use somente a atualização fornecida acima sobre a instalação 3.0.8 existente.
