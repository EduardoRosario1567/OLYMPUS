# OLYMPUS — IA com múltiplos provedores

> ## Procuramos colaboradores — Contributors welcome
>
> Quer ajudar a evoluir o OLYMPUS? Buscamos contribuições em execução isolada, integração com Open Lovable e motores existentes, testes ponta a ponta, provedores econômicos e UX.
>
> **Projeto experimental:** a entrega nativa completa de aplicativos ainda não está comprovada. Queremos resolver esse ponto com contribuições pequenas, reproduzíveis e verificáveis.
>
> **[Veja as prioridades e como participar](CONTRIBUTING.md)** · **[Proponha uma colaboração](https://github.com/EduardoRosario1567/OLYMPUS/issues/new)**
>
> Atualização de colaboração: 21/10/2026. A documentação da base 3.0.8 abaixo foi preservada; ela não representa sozinha os trabalhos posteriores de nuvem e Open Lovable.

# Olympus 3.0.8 — estabilidade e regressão

Build STABILITY-REGRESSION-P1. Fonte consolidada com segurança P0, catálogo,
Superpowers 6.4.2 e conceito de entrega/fontes preservados. Este ajuste corrige
inicialização da interface, preview local, marca, erro de criação de projeto,
registro e exibição de exceções, e proteção contra troca de processo no reinício.

Leia ../RELATORIO-ESTABILIDADE-OLYMPUS.md. Para atualizar a instalação existente:
../ATUALIZAR-ESTABILIDADE-OLYMPUS.txt. Copie todo o conteúdo no Terminal.
A atualização usa as dependências já instaladas, cria backup, verifica o novo
build e restaura o código anterior se falhar. Não substitui credenciais, bancos,
projetos, histórico, checkpoints ou preferências.

Os resultados e o destino das 20 falhas anteriores estão no relatório e em
../evidencias/. Os testes do navegador usam respostas HTTP sintéticas; não são
homologação de APIs reais nem de um site criado por IA. Instalação no Mac e
qualidade visual das entregas ainda exigem validação no ambiente real.
A01 (isolamento completo do código executado) permanece pendente.

Organização: olympus/ núcleo, backend/ APIs, frontend/ interface, tests/
regressões, scripts/ demonstrações, docs/ registros e vendor/superpowers/
biblioteca original versionada. O pacote exclui dependências instaladas, caches,
bancos, credenciais e checkpoints gerados pelos testes.
