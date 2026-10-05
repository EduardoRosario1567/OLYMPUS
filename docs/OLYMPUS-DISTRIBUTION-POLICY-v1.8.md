# OLYMPUS v1.8 — Política de distribuição

## Fronteiras do produto

| Artefato | Distribuição | Conteúdo permitido |
|---|---|---|
| Olympus Cloud | Privada | Núcleo, orquestração, prompts, políticas, backend e testes |
| Olympus Runner | Pública e assinada | Executável compilado, recursos visuais e manifesto de integridade |
| Projeto do cliente | Exportável | Código e ativos criados no workspace do próprio cliente |

O pacote monolítico usado durante o desenvolvimento não é um produto de
distribuição. O usuário final acessa o Olympus Cloud pelo navegador e recebe
somente o Runner quando uma tarefa precisar executar localmente.

## Regra automática

Todo pacote público do Runner precisa passar por
`scripts/verify_public_bundle.py`. A verificação é deny-by-default e bloqueia:

- código-fonte Python, TypeScript, JSX e mapas de código;
- `backend/`, `frontend/`, `olympus/`, `contexts/`, `tests/`, `scripts/` e documentação interna;
- `.env`, dependências, configurações privadas e arquivos ocultos;
- links simbólicos, caminhos relativos perigosos e entradas duplicadas;
- arquivo não declarado, hash divergente ou manifesto forjado;
- quantidade e tamanho superiores aos limites do pacote.

A verificação de integridade não substitui a assinatura/notarização da
plataforma. O Runner só poderá ser publicado depois de compilado, assinado e
submetido ao processo oficial de distribuição do sistema operacional.

## Propriedade

O projeto exportado pertence ao cliente conforme o plano e os termos
contratados. O motor Olympus, seus agentes, políticas, prompts, mecanismos de
seleção, segurança e correção permanecem ativos privados da plataforma.

## Próximas barreiras

1. ~~contrato de registro, tokens e persistência transacional do Runner~~ — implementado;
2. ~~endpoints do registro, ativação, rotação e revogação~~ — implementados;
3. ~~persistência transacional e manifesto com assinatura assimétrica~~ — implementado;
4. ~~contrato de cofre e variáveis por ambiente~~ — implementado;
5. ~~artefato executável independente de provedor~~ — implementado;
6. ~~verificação e atualização segura do Runner~~ — implementado;
7. compilação, assinatura de plataforma e notarização do binário público — depende da CI e das credenciais do proprietário.

## Primeiro provedor de publicação

O Railway é o primeiro adaptador real da camada neutra de publicação. A
integração usa somente o endpoint GraphQL oficial, com origem fixa, resposta
limitada e autenticação Bearer mantida em memória. Nenhuma mensagem remota que
possa repetir variáveis ou credenciais é apresentada diretamente ao usuário.

O serviço Railway precisa estar previamente conectado ao mesmo repositório do
projeto no GitHub. Uma publicação executa, na ordem: sincronização atômica do
GitHub, geração e conferência do artefato Olympus, envio de variáveis com
`replace: false` e `skipDeploys: true`, disparo único do serviço e conferência
do hash Git relatado no metadata do deployment. Falta ou divergência de hash é
falha segura.

Domínio próprio usa verificação de disponibilidade antes de criar o vínculo.
Rollback exige que deployment atual e alvo pertençam ao mesmo tenant, projeto,
ambiente e serviço. O Olympus nunca apaga projeto, repositório ou deployment ao
desconectar uma integração.

## Publicação e variáveis protegidas

O contrato de publicação reconhece projetos estáticos, Node, Python e
containers sem executar builds dentro do Olympus. Antes do envio, gera um ZIP
com inventário e hashes, excluindo `.env`, anexos, importações, dependências,
caches, arquivos ocultos e links simbólicos. O pacote adulterado é recusado.

Variáveis ficam isoladas por tenant, projeto e ambiente (`preview` ou
`production`). O artefato contém somente os nomes necessários. O valor é
materializado em memória durante a chamada do provedor e zerado logo depois.
O cofre em memória atende desenvolvimento e testes; produção deverá usar um
adaptador KMS/Secret Manager sem alterar o contrato da plataforma.

O coordenador valida novamente o hash do pacote, tenant, projeto, ambiente,
versão das referências e identidade do provedor antes de publicar. URLs de
resultado precisam usar HTTPS. Domínios são normalizados por IDNA e recusados
se trouxerem protocolo, porta, caminho, credencial ou rótulo inválido. Rollback
e domínio só podem operar sobre deployments pertencentes ao mesmo escopo.

## Contrato de acesso do Runner

- ativação por código aleatório de uso único, válido por no máximo 10 minutos;
- identificação vinculada ao tenant, licença, instalação, plataforma e versão;
- access token autenticado com HMAC-SHA256 e duração máxima de 15 minutos;
- refresh token rotacionado: o valor anterior deixa de funcionar imediatamente;
- revogação invalida access e refresh sem aguardar o vencimento;
- licença vencida bloqueia ativação, renovação e uso;
- apenas hashes autenticados de códigos e refresh tokens ficam em memória;
- segredos nunca aparecem na representação dos objetos ou no manifesto público.

O Runner fará apenas conexões HTTPS de saída. Nenhuma porta de execução local
será exposta. O registro em memória é o contrato de referência; a oferta SaaS
dependerá de adaptador persistente e de chave de assinatura mantida em KMS/cofre.

Os endpoints ficam sob `/cloud/runner`: emissão autenticada do código de uso
único, ativação, rotação, validação da sessão, listagem por tenant e revogação.
Na execução local sem chave configurada, o backend usa uma chave aleatória de
sessão; reiniciá-lo invalida todas as credenciais. Produção deverá fornecer
`OLYMPUS_RUNNER_SIGNING_KEY` pelo cofre, nunca por arquivo distribuído.
