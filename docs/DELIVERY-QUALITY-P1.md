# Olympus: conceito de entrega e fontes

Build **DELIVERY-SOURCES-P1**, sobre Olympus 3.0.8. Implementação preparada no código; instalação no Mac ainda não confirmada.

O problema identificado não era apenas a quantidade de skills. A pesquisa não tinha ferramenta externa, a inspeção devolvia a declaração do próprio modelo e o limite de contexto escondia orientações de algumas dependências.

## O que foi implementado

| Parte | Comportamento desta etapa |
| --- | --- |
| Conceito de entrega | Novas missões web recebem um contrato que exige `docs/delivery-concept.md` com direção visual, conteúdo, interações e evidências antes de concluir. A presença e a estrutura básica são verificadas; isso não mede beleza. |
| Frontend, design e pesquisa | Orientações próprias revisadas, com referências oficiais. Identidade específica, conteúdo confirmado, escolha de imagens, créditos e limites de revisão fazem parte das instruções. |
| Dependências das skills | Orientações distribuídas entre as skills para que as primeiras não consumam todo o contexto. |
| Pesquisa de imagens | Ação `research_sources`, destino `images`: consulta Commons e retorna candidatos com URL, origem, autoria, licença e dimensões. Descarta formatos e licenças fora da seleção suportada, metadados de restrição e hosts inesperados. |
| Pesquisa de contexto | Destino `context`: busca introduções na Wikipédia em seis idiomas. É contexto geral, não confirmação de informações de uma empresa. |
| Planejamento | Resultados da pesquisa entram no próximo ciclo; a compactação preserva os endereços exatos das fontes. |
| Honestidade da revisão | `inspect_result` identifica seu conteúdo como declaração do modelo. O relatório e o evento de publicação levam revisão de navegador e revisão visual como pendentes. |
| Continuidade | Correções anteriores de segurança e catálogo incluídas. Superpowers 6.4.2 preservado, sem scripts externos novos executados. |

Exemplos de ações disponíveis ao modelo:

```json
{"type":"research_sources","target":"images","payload":{"query":"coffee shop interior","language":"pt"}}
```

```json
{"type":"research_sources","target":"context","payload":{"query":"café especial","language":"pt"}}
```

A pesquisa utiliza endpoints HTTPS fixos, recusa redirecionamentos, limita tamanho e tempo das respostas e não herda configuração de proxy. Resultados externos são dados, não instruções. Consultas devem conter termos públicos curtos, sem texto privado ou credenciais.

## Critério de entrega

1. Entender o público, a marca e a ação principal; separar fatos confirmados de informações desconhecidas.
2. Registrar direção visual, organização do conteúdo e comportamento dos controles.
3. Priorizar os arquivos do usuário; pesquisar referências quando necessário e registrar a origem e os créditos das escolhas.
4. Implementar uma composição própria e responsiva, com conteúdo específico e controles reais.
5. Validar a entrega principal e declarar exatamente quais verificações ocorreram.
6. Refinar o resultado renderizado antes de apresentá-lo como aprovado visualmente.

As etapas 1–5 têm instruções e ferramentas parciais neste patch. A etapa 6 continua pendente de integração de navegador e revisão das imagens renderizadas. O controle determinístico impede concluir sem o documento de conceito; a adequação do conceito e a veracidade de todos os textos ainda precisam de avaliação independente.

## Fontes pesquisadas e decisão

| Referência oficial | Aplicação no Olympus |
| --- | --- |
| [OpenAI: Designing delightful frontends](https://developers.openai.com/blog/designing-delightful-frontends-with-gpt-5-4) | Direção visual, conteúdo e imagens pensados em conjunto; inspeção do resultado renderizado. Conceitos adaptados em texto próprio. |
| [Anthropic: frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | Escolhas específicas para o assunto e o público, tipografia intencional e crítica do resultado. Não importamos a skill nem seu código. |
| [MediaWiki: Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo) | Consulta técnica de metadados de imagens. |
| [Commons: reutilização](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) | Verificação por imagem de origem, licença, créditos e demais direitos. A filtragem de metadados não garante todos os direitos de uso. |
| [Unsplash: API](https://unsplash.com/documentation) | Avaliado como opção futura; não conectado. Exige credencial e cumprimento de suas regras de atribuição, hotlinking e registro de download. |
| [Playwright: comparações visuais](https://playwright.dev/docs/test-snapshots) | Referência para a próxima integração. A dependência já consta no frontend, mas este patch não cria uma ferramenta de navegador nem ativa comparação visual. |

Consulta em 3 de outubro de 2026. A seleção considera adequação ao problema e fontes oficiais; não representa um ranking comprovado de todas as skills disponíveis.

## Validação e limites

- **103 testes direcionados aprovados**, com 7 subtestes e dois avisos preexistentes do FastAPI.
- **28 testes do atualizador aprovados**: bases conhecidas, repetição, código personalizado, portas, backups, falhas, interrupção e rollback, inclusive remoção de módulo novo ao restaurar.
- **Regressão geral: 968 aprovados, 20 falhas, 4 ignorados, 64 subtestes.** As 20 falhas correspondem às já registradas na auditoria anterior, incluindo contratos antigos de versão/UI e um teste que requer rede externa bloqueada no ambiente de validação. Permanecem abertas; não foram ocultadas ou marcadas como aprovadas.
- Análise sintática para Python 3.9; execução interna em Python 3.12. Aplicação completa testada em Mac simulado, com serviços HTTP locais e dados sintéticos.
- Pesquisa validada com respostas controladas. Disponibilidade das APIs públicas no Mac e comportamento de modelos reais ainda precisam de homologação. Nenhuma chamada real a modelos foi usada nestes testes.
- As imagens retornadas são candidatos. Não há download incorporado, verificação dos bytes, inspeção do enquadramento ou aprovação visual neste patch.
- Wikipédia não substitui a fonte oficial de uma empresa. Para Rosales Café, endereço, horários, preços, contatos, história e fotos do estabelecimento precisam ser confirmados.
- O isolamento completo da execução de código continua pendente na auditoria A01. As melhorias de segurança anteriores continuam parciais nesse ponto.

## Atualização e organização

`ATUALIZAR-ENTREGA-OLYMPUS.txt` contém um único comando Python legível para copiar inteiro no Terminal. Ele aceita as bases 3.0.8 conhecidas, guarda backup, aplica somente código/configuração das skills e identificação do build, reinicia os serviços da instalação e verifica o build em ambos. Falhas de aplicação restauram os arquivos anteriores, preservando alterações concorrentes identificadas. Bancos, projetos e credenciais não fazem parte do payload.

O pacote unificado contém `aplicativo/`, esta documentação, referências, testes do atualizador, evidências e manifesto SHA-256. Dependências instaladas, caches, bancos, credenciais e checkpoints de testes foram excluídos. Não há alteração da instalação ativa do Mac por esta sessão.

## Próxima condição para qualidade profissional

A primeira prioridade é ligar o navegador ao executor e ao verificador: abrir a página principal, conferir carregamento das imagens e recursos, testar controles em desktop/mobile e guardar capturas reais. Depois, uma revisão visual com acesso às capturas — por modelo capaz ou por pessoa — deve orientar correções e avaliar o Rosales Café com uma referência aprovada. Somente adicionar instruções não comprova esse padrão.

## Registro do patch

PATCH DELIVERY-SOURCES-P1: PASS no escopo implementado; homologação geral pendente.

CHANGED: executor, ações, normalizador, política de autonomia, planejador, compilador, ciclo, runner, relatório, publicação, três skills e fixtures relacionadas. Manifesto completo no pacote.

ACCEPTANCE: pesquisa acessível ao agente; fontes chegam ao planejamento; conceito exigido em novas missões web; declaração do modelo não é prova de navegador; limites de revisão registrados.

CONTEXT: base de catálogo e segurança preservada; sem dependências novas, migrações, commits, novos segredos ou instalação remota no Mac.

VIOLATIONS: NONE.

BLOCKED: NO para esta integração. Navegador, revisão visual, API real no Mac e as 20 falhas gerais não estão homologados.
