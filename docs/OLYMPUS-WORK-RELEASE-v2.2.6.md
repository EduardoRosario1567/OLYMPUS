# OLYMPUS Work v2.2.6

## Continuidade real entre modelos

- A retomada continua pela primeira rota ainda não tentada, em vez de reiniciar toda a cadeia.
- O handoff entrega ao próximo modelo os arquivos lidos e modificados, testes executados, último erro e modelos anteriores.
- Os arquivos já alterados entram obrigatoriamente no contexto da próxima etapa.

## Compatibilidade com limites gratuitos

- Qwen usa um orçamento de saída compatível com o limite gratuito observado.
- Respostas de rate limit em milissegundos ou segundos aguardam o intervalo indicado e repetem o mesmo modelo.
- Limites de `max_tokens` informados pelo provedor são corrigidos automaticamente.
- A ação `open_file` é normalizada para leitura segura de arquivo.
- Modelos sem adequação ao trabalho de programação são removidos da rota dinâmica.
