# OLYMPUS Work v1.7 — GitHub e publicação

## Resultado

O ambiente profissional do projeto agora inclui conexão por sessão com o
GitHub, repositório novo ou existente, branches, commits atômicos, histórico
remoto, sincronização automática e publicação estática em um clique.

## Segurança da credencial

- Token recebido por campo de senha e mantido somente na memória do backend.
- Token não entra em banco, JSON, projeto, versão, ZIP, log ou resposta HTTP.
- Metadados públicos do vínculo ficam fora da pasta do projeto, com permissão
  local `0600` e gravação atômica.
- Cada identidade possui conta e vínculo isolados por tenant.
- Cliente HTTP usa origem fixa `https://api.github.com`, resposta limitada e
  versão explícita da API.

## Sincronização

- Limite de 5.000 arquivos, 20 MB por arquivo e 200 MB por projeto.
- Exclusão de `.env`, anexos, importações, caches, dependências, arquivos
  ocultos, diretórios operacionais e links simbólicos.
- Arquivos binários são suportados por blobs em Base64.
- Comparação pelo hash Git blob evita commits vazios.
- Todos os arquivos alterados entram numa única árvore e num único commit.
- Atualização da referência com `force=false`.
- Conflito remoto interrompe a operação antes de mover a branch.
- Arquivos exclusivos do remoto são preservados.

## Commits automáticos

- Missão local concluída aciona a sincronização se houver conta ativa e
  repositório conectado.
- Sucesso e falha externa entram no histórico de eventos da missão.
- Falha da integração nunca converte uma missão local validada em falha.
- Mensagens externas de erro não são copiadas para o evento, evitando exposição
  acidental de informação sensível.

## Publicação

- Compatibilidade inicial: HTML estático ou build existente em `dist`/`build`.
- Validação integral dos arquivos publicáveis antes de qualquer commit.
- Código-fonte sincronizado antes da publicação.
- Site publicado na branch isolada `olympus-pages`.
- Árvore da publicação contém somente ativos web permitidos.
- URLs absolutas de HTML e CSS são ajustadas para o caminho do repositório.
- GitHub Pages configurado em modo legado na raiz da branch.
- Status e endereço público exibidos na mesma tela.
- Repositório privado continua disponível para sincronização, mas não para o
  caminho gratuito de publicação da v1.7.

## Limites explícitos

- A credencial precisa ser reconectada após reiniciar o backend; persistência
  segura em cofre do sistema exige uma integração específica de plataforma.
- A publicação não executa builds nem instala dependências silenciosamente.
- Aplicações com backend, banco ou funções de servidor ainda exigem adaptador
  para um provedor de hospedagem executável.
- Oferta pública multiusuário continua condicionada a isolamento de execução
  por contêiner, conforme declarado na v1.6.

## Referências de contrato

- GitHub REST API `2026-03-10`.
- Git database: blobs, trees, commits e refs.
- GitHub Pages: site, builds e origem por branch.
- Token refinado: Contents leitura/escrita; Pages e Administration
  leitura/escrita para publicação.
