# OLYMPUS Work v2.0 — fundação SaaS profissional

## Resultado

A v2.0 transforma o isolamento técnico por tenant em uma camada de produto:
organizações, pessoas, papéis, convites, uso, planos e auditoria. A evolução é
compatível com a instalação v1.9: a identidade administrativa atual assume a
organização já existente e nenhum projeto é migrado ou apagado.

## Entregue

- organizações múltiplas por pessoa e troca segura do espaço ativo;
- papéis proprietário, administrador, construtor e leitor;
- autorização aplicada no backend a projetos, missões e publicação;
- convite temporário de uso único, armazenado somente como SHA-256;
- senha de membro com PBKDF2-SHA256, 600 mil iterações e salt individual;
- contadores mensais transacionais para missões e publicações;
- limites de membros e projetos por plano;
- reserva e devolução de cota quando uma operação não é aceita;
- eventos de cobrança verificados externamente e idempotentes;
- histórico administrativo append-only encadeado por hash;
- tela secundária de organização, equipe, plano, uso e atividade;
- histórico de missões conectado ao runtime multi-tenant atual;
- API legada sem tenant desligada por padrão;
- validações fail-closed para configuração de produção.

## Matriz de acesso

| Capacidade | Proprietário | Administrador | Construtor | Leitor |
|---|---:|---:|---:|---:|
| Ver organização, equipe e projetos | Sim | Sim | Sim | Sim |
| Criar e editar projetos | Sim | Sim | Sim | Não |
| Executar missões | Sim | Sim | Sim | Não |
| Gerenciar GitHub e publicação | Sim | Sim | Sim | Não |
| Convidar e alterar membros | Sim | Sim | Não | Não |
| Consultar auditoria | Sim | Sim | Não | Não |
| Administrar cobrança | Sim | Não | Não | Não |

O proprietário não pode ser removido nem rebaixado. Uma futura transferência
de propriedade deverá exigir reautenticação e confirmação separada.

## Limites conscientes desta etapa

- o armazenamento SaaS usa SQLite transacional e é adequado ao Runner local ou
  a uma única instância; operação horizontal exige um adaptador PostgreSQL;
- a cadeia de auditoria detecta alteração acidental ou parcial, mas uma
  implantação regulada deverá ancorar o hash final fora do banco;
- não há cobrança real, checkout, reembolso ou emissão fiscal sem escolha do
  provedor e credenciais oficiais;
- recuperação de senha, MFA, SSO/SAML e SCIM ainda não foram implementados;
- envio automático do convite depende de um provedor de e-mail; por enquanto o
  proprietário copia o link de uso único por um canal seguro;
- o build Next.js continua dependendo das dependências declaradas do frontend;
  o pacote não instala dependências silenciosamente no Work ou no Mac.

## Próxima etapa segura

Antes da venda pública, o Olympus precisa de uma camada de infraestrutura
gerenciada: PostgreSQL, armazenamento de objetos, fila de trabalhos isolada,
observabilidade, backup/restauração testados, provedor de identidade e provedor
de cobrança. Esses componentes exigem decisões comerciais e credenciais do
proprietário; não são simulados dentro do pacote.
