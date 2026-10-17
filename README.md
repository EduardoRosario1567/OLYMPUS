# Olympus 3.0.9 — qualidade de entrega

Build DELIVERY-QUALITY-RC1 (candidata consolidada; publicação em main depende do gate de CI com navegador real). Fonte consolidada com segurança P0, catálogo,
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
