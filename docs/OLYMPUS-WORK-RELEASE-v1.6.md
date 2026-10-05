# OLYMPUS Work v1.6 — Ambiente profissional de construção

## Resultado

O Olympus reúne conversa, preview, arquivos, console e versões no mesmo
ambiente. A tela principal continua simples; os recursos técnicos aparecem
somente depois de `Abrir projeto`.

## Preview executável

- Reconhecimento limitado a Next.js, Vite e React Scripts.
- Execução direta pelo Node.js, sem shell e sem comandos arbitrários do
  `package.json`.
- Nenhuma instalação automática de dependências.
- Porta vinculada exclusivamente a `127.0.0.1` e sessão com token temporário.
- Respostas acessadas por proxy de capacidade e caminhos locais reescritos.
- Máximo de dois runtimes simultâneos e encerramento junto ao backend.
- Missões e restaurações encerram o runtime antes de substituir arquivos.
- Console somente leitura, limitado a 1.000 linhas e com filtragem de valores
  associados a token, senha, segredo, autorização e chave de API.

## Editor protegido

- Lista e edição de arquivos textuais UTF-8 de até 1 MB.
- Bloqueio de `.env`, arquivos ocultos, anexos, importações, `node_modules`,
  caches, builds, links simbólicos e travessia de diretórios.
- Hash SHA-256 usado como trava otimista contra alterações concorrentes.
- Snapshot automático antes da edição.
- Escrita atômica com preservação das permissões do arquivo.
- Aviso antes de descartar rascunhos não salvos.

## Seleção visual

- Modo `Selecionar elemento` no preview estático e executável.
- Destaque do elemento sob o cursor.
- Captura limitada de seletor, tag e texto visível.
- Conversão do elemento selecionado em um pedido editável ao Olympus.
- Mensagens aceitas somente do iframe de preview ativo.

## Higiene do projeto

- `node_modules`, `.next`, cobertura, repositório Git e arquivos `.env` não são
  copiados para missões nem incluídos em ZIPs de exportação.
- Dependências e caches de runtime não entram em snapshots, evitando versões
  excessivas e vazamento acidental de arquivos operacionais.

## Limite explícito

O runtime local executa código do projeto com as permissões do usuário do
Olympus. Esta versão é destinada a projetos próprios ou confiáveis em uso
local. Contêineres efêmeros com isolamento de sistema operacional são
necessários antes de uma oferta pública multiusuário.

## Validação

- Runtime Node real iniciado, acessado pelo proxy, inspecionado e encerrado no
  ambiente Work.
- Testes de travessia, links simbólicos, isolamento entre usuários, redaction,
  limite de logs, conflito de edição, snapshot e exclusão de segredos.
- Regressão integral executada sem depender do Mac.
- 567 testes executados com sucesso, zero falhas e 11 integrações opcionais
  ignoradas porque FastAPI, PyJWT ou serviços externos não fazem parte do
  runtime de validação do Work.
