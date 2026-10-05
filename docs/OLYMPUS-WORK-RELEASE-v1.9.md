# OLYMPUS Work v1.9 — persistência e cadeia segura do Runner

## Resultado

A v1.9 substitui estados críticos temporários da v1.8 por contratos
transacionais e estabelece a cadeia criptográfica de atualização do Runner.
Ela não transforma o pacote de desenvolvimento em distribuição pública: o
núcleo continua privado e o binário público continua sendo produzido somente
pela CI controlada pelo proprietário.

## Entregue

- persistência SQLite transacional para instalações, hashes de renovação e
  revogações do Runner;
- vínculo entre estado persistido e fingerprint da chave de assinatura;
- histórico persistente de deployments, domínio, DNS e rollback;
- roteamento Railway restaurado após reinício do backend;
- contrato `KeyManagementProvider` para KMS/Secret Manager;
- cofre SQLite que armazena somente ciphertext e contexto associado;
- rotação integral da chave KMS com rollback da transação em qualquer falha;
- modo local volátil quando nenhum KMS está configurado;
- manifesto canônico de release e assinatura assimétrica SHA-256;
- validação de plataforma, arquitetura, canal, versão mínima e timestamp;
- bloqueio de downgrade, pacote adulterado, assinatura incorreta e symlink;
- staging atômico do pacote validado;
- endpoint autenticado de descoberta de atualização;
- utilitários de assinatura e verificação para CI privada.

## Limites e dependências externas

- o adaptador concreto do KMS depende do provedor escolhido para a
  infraestrutura SaaS; o Olympus já possui o contrato e a composição segura;
- tokens de GitHub e Railway permanecem apenas na sessão, sem persistência;
- compilação, assinatura Apple/Windows e notarização exigem binários reais,
  contas dos fabricantes e segredos da CI;
- nenhuma dessas credenciais foi solicitada, criada ou simulada nesta versão.

## Regra de liberação pública

Um Runner só poderá sair da CI depois de compilado, assinado pela plataforma,
notarizado quando aplicável, empacotado pelo limite público deny-by-default,
assinado pela chave de release e validado novamente com a chave pública que já
está fixada no Runner anterior.
