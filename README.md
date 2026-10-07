# OLYMPUS — construa conosco uma ferramenta multi-IA

**Aceitamos desenvolvedores interessados em contribuir com a evolução do OLYMPUS.**
Buscamos pessoas que queiram transformar missões em entregas verificáveis: do
planejamento à execução, com acompanhamento, recuperação de falhas e evidências.
Contribuições em código, testes, design, acessibilidade e documentação são bem-vindas.

[Quero contribuir](CONTRIBUTING.md) · [Desenvolvimento local](docs/community/DEVELOPMENT.md) · [Prioridades](docs/community/ROADMAP.md) · [Reportar problema](https://github.com/EduardoRosario1567/OLYMPUS/issues/new/choose)

## O que estamos construindo

O OLYMPUS reúne uma interface Next.js/React, uma API Python/FastAPI e um núcleo
de decisão para coordenar tarefas com diferentes provedores de IA. O objetivo é
criar projetos, acompanhar missões e conferir os resultados produzidos.

O código contém adaptadores, integração com OmniRoute e Ollama, histórico,
retomada e verificadores de entrega. A presença de um adaptador não significa
que todo modelo esteja disponível, gratuito ou homologado: isso depende da
versão, da configuração e do provedor.

## Estágio do projeto

**Em desenvolvimento ativo e aberto à colaboração.** A base de `main` consultada
para esta documentação é a **3.0.8**, build `STABILITY-REGRESSION-P1`.
Candidatas **3.0.9** estão em branches próprias e devem ser avaliadas pelo commit
e pelas evidências antes da promoção. Confira a versão em `backend/app/main.py`
e o workflow de CI do commit escolhido.

Testes controlados, build e missão com provedor real são verificações diferentes.
Respostas simuladas não representam homologação de uma IA real. Instalação,
isolamento, roteamento e qualidade das entregas continuam evoluindo; o projeto
não é anunciado como serviço pronto para uso crítico ou produção multiusuário
sem avaliação específica.

## Onde você pode ajudar

| Área | Contribuições desejadas |
| --- | --- |
| Interface | Acessibilidade, navegação, clareza dos estados e experiência em telas menores |
| API e núcleo | Contratos, tratamento de erros, separação das camadas e observabilidade |
| Provedores | Adaptadores documentados, limites, autenticação e failover verificável |
| Qualidade | Regressões, evidências de navegador e contratos de aceite |
| Instalação | Atualização reversível, preservação de dados e compatibilidade |
| Documentação | Guias reproduzíveis, exemplos sem segredos e traduções |

Abra uma issue **Quero contribuir** com sua área de interesse ou escolha uma
proposta em [Prioridades](docs/community/ROADMAP.md). Não é necessário compartilhar
e-mail, telefone, chaves de API ou dados pessoais. Também aceitamos contribuições
em inglês.

## Estrutura

| Diretório | Responsabilidade |
| --- | --- |
| `olympus/` | Núcleo de decisão, execução e avaliação; integrações em módulos próprios |
| `backend/` | API, autenticação e serviços |
| `frontend/` | Interface Next.js/React |
| `tests/` | Regressões e contratos |
| `scripts/` | Instalação, configuração e verificação |
| `docs/` | Arquitetura, registros técnicos e guias |
| `vendor/superpowers/` | Dependência versionada com licença própria preservada |

Leia [Arquitetura](docs/community/ARCHITECTURE.md) e [AGENTS.md](AGENTS.md) antes
de modificar o núcleo. Use um clone separado da instalação pessoal, seguindo
[DEVELOPMENT.md](docs/community/DEVELOPMENT.md). É possível começar pela
documentação e pelos testes controlados sem credenciais de provedores.
Missões reais exigem seus próprios serviços, credenciais e respeito aos custos.

## Revisão das contribuições

Cada pull request deve explicar o problema, o comportamento resultante e a
validação realizada. Mudanças funcionais precisam de testes pertinentes;
mudanças visuais precisam de evidências. O mantenedor decide a integração.
Não há prazo de revisão garantido nem concessão automática de acesso de escrita.

Veja [CONTRIBUTING.md](CONTRIBUTING.md), [Código de conduta](CODE_OF_CONDUCT.md)
e [Segurança](SECURITY.md).

## Licença

O código próprio do OLYMPUS é disponibilizado sob **AGPL-3.0-only**; veja
[LICENSE](LICENSE). A política escolhida é manter acessível o código das versões
modificadas distribuídas ou oferecidas aos usuários como serviço pela rede,
conforme os termos da licença. Uso comercial continua permitido.

Componentes de terceiros conservam suas licenças e avisos próprios. A licença
MIT de `vendor/superpowers/` permanece preservada. Ao incluir dependências ou
recursos novos, verifique a compatibilidade e mantenha os créditos necessários.
