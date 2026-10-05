# OLYMPUS Work v1.8 — distribuição protegida e publicação profissional

## Resultado

A v1.8 separa o produto distribuível do núcleo privado e acrescenta a primeira
publicação de aplicação completa. O pacote de desenvolvimento continua sendo
usado apenas internamente; a distribuição comercial prevista é Olympus Cloud
privado, Runner público compilado e assinado, e código do projeto exportável
pelo cliente.

## Capacidades entregues

- verificador deny-by-default para o pacote público do Runner;
- manifesto e hashes de integridade sem código-fonte do Olympus;
- registro de instalação, ativação de uso único, tokens curtos, rotação e
  revogação do Runner;
- contrato independente de provedor para artefatos, variáveis, deploy,
  domínio e rollback;
- isolamento de variáveis por organização, projeto e ambiente;
- adaptador Railway usando a API GraphQL oficial;
- sincronização automática do GitHub antes do deploy;
- confirmação obrigatória de que o Railway executa o commit aprovado;
- domínio próprio e rollback limitados ao escopo original;
- controles do Railway integrados à aba Publicar, sem poluir a conversa.

## Limites honestos

- tokens de integrações e valores secretos usam cofre volátil nesta edição;
  produção exige KMS/Secret Manager persistente;
- o Runner ainda precisa ser compilado, assinado, notarizado e receber canal
  seguro de atualização antes da distribuição pública;
- a validação real contra uma conta Railway requer credencial e infraestrutura
  do proprietário; a suíte local usa um simulador fiel do contrato oficial;
- cobrança, equipes, colaboração simultânea e observabilidade SaaS continuam
  nas fases seguintes.

## Aceitação

Uma publicação só é aceita quando projeto e integração pertencem ao tenant,
GitHub e Railway apontam para o mesmo repositório, existe versão local, o
artefato passa na verificação de integridade e o commit relatado pelo Railway
coincide com o commit sincronizado. Nenhuma credencial entra no repositório,
artefato, resposta da API ou arquivo de vínculo.
