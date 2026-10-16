# Missão real de aceitação: Rosales Café

> Este arquivo contém a instrução e os critérios de aceite. **Não é o site** e não conta como execução de IA.

## Instrução a ser enviada ao OLYMPUS

Crie uma landing page completa e responsiva para **Rosales Café**.

Posicionamento da marca fornecido pelo cliente: **"Rosales Café, o melhor café brasileiro ao estilo Colombiano."**

Entregue um site estático autocontido em `site/index.html`, com recursos em `site/`. Use HTML semântico, CSS responsivo, imagens e ilustrações locais com procedência/documentação, caso disponíveis, e JavaScript apenas quando necessário. Não utilize scripts, imagens, fontes, links de mídia ou estilos carregados de terceiros. Não invente prêmios, avaliações, certificações, contatos, endereços, preços, disponibilidade nem alegações sobre origem dos grãos. Trate a frase de posicionamento como linguagem promocional da marca, não como comprovação objetiva.

Proponha direção visual de café premium com personalidade própria, hierarquia editorial, comunicação em português do Brasil, chamada para ação sem prometer venda ou contato inexistente, e seções de apresentação da marca, proposta de experiência, diferenciais editoriais e convite à descoberta. Inclua navegação mobile, estados de foco visíveis, contraste e respeito à preferência por movimento reduzido. O resultado deve abrir localmente sem internet.

## Requisitos de comprovação

1. OLYMPUS deve registrar qual provedor/modelo **real** foi chamado, horários, tentativas e status, sem expor credenciais.
2. A entrega deve originar-se da execução real da missão pelo próprio agente; é proibido usar um site pronto preparado manualmente como evidência.
3. O artefato deve passar `scripts/verificar_entrega_estatica.py` e `scripts/preserve_static_delivery.py`; guardar o manifesto de SHA-256.
4. Executar teste em navegador real (desktop e viewport móvel) e registrar captura e resultado de interações, sem falsificar imagens, cliques ou URL de preview.
5. Quando não houver isolamento de execução no sistema operacional ou provedor conectado, registrar **BLOCKED** e não executar código gerado com privilégios do host.
6. Custos: somente rotas gratuitas estritas previamente conectadas e autorizadas; não recorrer automaticamente a provedores pagos.
7. Nenhuma alteração à branch `main`, credenciais, arquivos do Mac ou implantação pública sem aprovação.
8. Resultado final: `DONE` somente com artefato, validações, navegação e chamada real comprovada; caso contrário, `BLOCKED` com diagnóstico detalhado.

## Situação inicial

- Missão especificada, não executada.
- O ambiente atual ainda não demonstrou isolamento de execução de modelos nem credenciais de provedor aptas a esta missão.
- Testes com provedores simulados não satisfazem o item 1.
