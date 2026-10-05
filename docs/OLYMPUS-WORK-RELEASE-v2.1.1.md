# OLYMPUS Professional v2.1.1 — compatibilidade de borda dos provedores

O teste real no macOS confirmou uma chave Cerebras válida (`HTTP 200`) quando
a requisição se identifica, enquanto o cliente genérico do Olympus recebia
`HTTP 403` antes da autenticação. Todas as requisições OpenAI-compatible agora
enviam `Accept: application/json` e um `User-Agent` explícito do Olympus.

A chave Groq testada respondeu `HTTP 401 Invalid API Key`. Isso não impede a
missão: o controle de execução bloqueia o restante das rotas Groq daquela
tentativa e segue para a Cerebras, preservando o projeto e o checkpoint.

Nenhuma credencial integra esta distribuição. Em uma atualização local, o
arquivo `backend/.env` deve ser copiado da instalação anterior pelo próprio
proprietário e mantido com permissão `0600`.
