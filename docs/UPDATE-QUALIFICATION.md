# Atualizador de fonte para macOS — qualificação

A candidata inclui `ATUALIZAR-OLYMPUS.command` e um manifesto de hashes
criado a partir dos arquivos rastreados do commit. Exige uma instalação
identificada 3.0.8 ou 3.0.9; não cria outra pasta nem migra estado de outras
instalações. Usa a instalação que está atendendo nas portas conhecidas, ou
uma pasta única em Documents/Projects; ambiguidades exigem `--target`.

Antes de substituir código: valida todos os hashes e caminhos; confere
ferramentas, versão Node, Python existente, credenciais presentes, socket
Docker local e propriedade das portas. Provisona bases Docker por digest,
usa o lock npm revisado e exige as duas provas reais de isolamento locais.
Se a preparação de imagens falhar, restaura os tags anteriores quando existem.
Nenhuma imagem/volume do usuário é podada por uma limpeza ampla.

Encerra somente processos da instalação nas portas 8000, 3000 e 3001,
reconferindo PID/porta/CWD antes de TERM. Não encerra o OmniRoute. Mantém
backup privado de código substituído, dependências anteriores e arquivos
persistentes. Credenciais, bancos, histórico e projetos não são arquivos de
payload. Templates `.env.example` já existentes também são preservados, pois
podem conter valores locais. O pacote é extraído fora da instalação ativa.
Instala Python/frontend novamente e exige healthchecks de versão
**e build** exatos, com backend/frontend nas portas 8000/3000.

Erros de instalação/início/healthcheck revertem código e dependências, desde
que não haja alteração concorrente. O diário permite recuperar uma interrupção
abrupta na próxima execução quando código e dados ainda correspondem ao
registro. Quando detecta uma alteração concorrente ou não consegue encerrar
um serviço, preserva essa alteração e os backups e bloqueia uma reversão
que a sobrescreveria. Não tenta reparar bancos ou desfazer trabalho do usuário.
Os backups não são apagados ao concluir: limpeza remove somente os arquivos
substituídos da instalação ativa, mantendo cópias para recuperação.

A CI macOS executa transações em filesystem real com operações de
processos/dependências controladas; cria e verifica o ZIP do commit e faz
build frontend com instalação nova. Também atualiza uma instalação sintética
com o código anterior qualificado: Python/npm, processos, portas e healthchecks
são reais. Apenas o provisionamento Docker é separado nesse smoke nativo,
pois o runner macOS não tem Docker Desktop; o atualizador de produção não
tem opção para ignorar suas provas de isolamento. A CI Linux mantém regressão, E2E e
isolamento Docker real. Esses testes não equivalem a uma atualização completa
na instalação real do usuário: só esse smoke depende das credenciais,
serviços e dados locais, e não deve ser confundido com a missão Rosales
Café usando provedor real. A candidata não é a entrega final do produto.
