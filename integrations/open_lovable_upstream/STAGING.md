# Open Lovable — build de staging sem fork adicional

O Dockerfile cria um artefato imutável do Open Lovable oficial no commit \`806b8072f28afea11fa2b028cac1449eff74c511\`, aplicando **somente** \`app/api/olympus-export/route.ts\` do OLYMPUS. Não altera o repositório original e não atualiza automaticamente para um commit novo.

Workflow \`.github/workflows/open-lovable-staging.yml\`: build em GitHub Actions, execução temporária sem chaves de provedores e verificação HTTP de que \`/api/olympus-export\` responde 401 sem token e 409 quando não há sandbox ativo. A imagem **não é publicada em registry** nem implantada automaticamente.

Segurança: **não usar no ambiente multiusuário**. O Open Lovable continua com \`global.activeSandboxProvider\` e \`global.conversationState\`; criação de um sandbox pode terminar o sandbox anterior. Segurança da exportação não equivale a isolamento por missão. Validar licença e realizar \`npm audit\` de runtime antes de qualquer disponibilização de staging. O Dockerfile contém código original somente no contêiner temporário e não hospeda segredos.

O serviço Railway atual \`open-lovable-upstream\` segue conectado a \`firecrawl/open-lovable\` e **não usa este Dockerfile**. A implantação nova requer serviço dedicado e configuração em ambiente privado, preservando o piloto existente. Bloqueios restantes: isolamento por sessão, exportação real com E2B, build independente do snapshot, Playwright, Rosales Café de ponta a ponta e limites de custo.
