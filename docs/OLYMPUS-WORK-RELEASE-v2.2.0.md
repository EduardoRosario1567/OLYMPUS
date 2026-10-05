# OLYMPUS Professional v2.2.0 — Central de IAs e Plugins

## Objetivo

Transformar o tecido mult provedores já existente em uma experiência de produto clara, controlável e independente de uma única IA.

## Entregas

- Nova área **IAs e plugins** na navegação principal.
- Catálogo unificado para OmniRoute, OpenRouter, Groq, Cerebras, Ollama, OpenAI, Gemini e Mistral.
- Diagnóstico paralelo de disponibilidade e quantidade de modelos.
- Teste individual de conexão com mensagem compreensível.
- Ativação, desativação e prioridade persistentes sem armazenar chaves no arquivo de preferências.
- Alterações administrativas protegidas pela permissão de gerenciamento da organização.
- Configurador local ampliado para seis credenciais de nuvem, sempre com entrada oculta.
- OmniRoute passa a ser opcional no iniciador; sua indisponibilidade não impede o Olympus de abrir com outras IAs.
- Prioridade da Central aplicada à ordem dos fallbacks gratuitos independentes.
- Plugins GitHub, Railway, arquivos, preview e testes apresentados em uma mesma central.

## Segurança

- A API informa apenas se uma credencial existe; nunca retorna seu valor.
- Preferências guardam somente estado e prioridade, com escrita atômica e permissão de arquivo restrita.
- Nenhuma chave, banco local, workspace ou resultado privado integra o pacote público.

## Critério de conclusão

A versão somente é homologada após testes do controle de preferências, fallback, isolamento de segredos, contratos da interface, sintaxe dos iniciadores e regressão completa.
