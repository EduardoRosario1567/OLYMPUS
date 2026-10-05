# OLYMPUS Work v1.5 — Preview e versões protegidas

## Resultado

O Olympus passa a oferecer visualização do projeto e histórico restaurável sem
transformar a conversa principal em um painel técnico. O acesso fica reunido em
`Abrir projeto`, com as áreas `Preview` e `Versões`.

## Preview seguro

- Sessões temporárias com token aleatório e expiração automática.
- Visualização de páginas HTML e seus ativos web locais.
- Alternância entre larguras desktop e mobile.
- Iframe isolado e política de conteúdo que bloqueia conexões externas,
  formulários, objetos e frames aninhados.
- Arquivos ocultos, `.env`, código de servidor, diretórios internos, links
  simbólicos e arquivos acima de 10 MB não são servidos.
- O preview atual é estático: projetos que dependem de servidor de
  desenvolvimento precisam primeiro gerar uma saída HTML estática.

## Versionamento e restauração

- Cada missão concluída cria uma versão anterior e outra da entrega publicada.
- Também é possível salvar uma versão manualmente.
- A comparação mostra arquivos que seriam adicionados, modificados ou removidos.
- Toda versão contém manifesto SHA-256 e é verificada antes da restauração.
- Antes de restaurar, o estado atual recebe automaticamente uma versão de
  segurança.
- A restauração é transacional: uma falha posterior recoloca os arquivos
  anteriores.
- Restauração é bloqueada durante missões ativas.
- Anexos, importações, diretórios de execução, repositório Git e arquivos de
  ambiente permanecem fora do snapshot e são preservados.
- Links simbólicos são recusados para impedir perda silenciosa ou leitura fora
  do projeto.
- Cada snapshot aceita no máximo 5.000 arquivos e 512 MB, evitando consumo
  descontrolado de armazenamento durante uma missão.

## Arquitetura

- Snapshot baseado em arquivos e JSON, sem alteração do banco e sem migração.
- Armazenamento de versões fora da raiz exportável do projeto.
- Operações de publicação e restauração serializadas pelo mesmo controle de
  concorrência.
- Nenhuma dependência adicional.

## Validação

- Testes específicos cobrem captura, comparação, publicação, integridade,
  rollback, preservação de segredos/anexos, concorrência, isolamento por usuário,
  expiração do preview e bloqueio de caminhos perigosos.
- 548 testes da suíte segura foram executados com sucesso; 8 integrações
  opcionais foram ignoradas pelas próprias condições de execução.
- Três módulos HTTP que exigem FastAPI/PyJWT não foram carregados no executor
  Work, que não contém essas dependências. Contratos de rotas e compilação
  Python foram validados sem instalar pacotes; o inicializador cria o ambiente
  completo automaticamente na plataforma de uso.
- O build Next.js não foi executado no Work porque `node_modules` não integra o
  pacote-fonte e a política do projeto proíbe instalar dependências sem uma
  autorização específica. Os contratos e a estrutura TypeScript/JSX tocados
  estão cobertos pela suíte estática.
- A validação central é executada no ambiente Work; o Mac permanece apenas como
  plataforma final de uso, não como condição para a evolução do código.
