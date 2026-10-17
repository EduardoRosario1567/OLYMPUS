# OLYMPUS — qualificação integral do Open Lovable (primeira execução)

Data: 2026-10-16. Estado: **baseline de compilação em avaliação**, NÃO é integração nem missão real homologada.

## Objeto
Validar o produto **original e integral** `firecrawl/open-lovable` em execução segregada, sem copiar código de terceiros para o repositório OLYMPUS, modificar `main`, invocar serviços pagos ou exigir comandos no Mac.

- Origem: https://github.com/firecrawl/open-lovable
- Fonte fixa: `806b8072f28afea11fa2b028cac1449eff74c511` (2026-10-09).
- Licença principal: MIT (avisos devem ser preservados em qualquer futura distribuição).
- Alvo: Node.js 22, `npm ci --ignore-scripts`, `npm run build`, ambiente descartável Ubuntu no GitHub Actions.
- Isolamento: somente checkout do Open Lovable dentro do job; permissões GitHub `contents: read`; sem segredos e sem `.env.local`.
- Nenhum provedor de IA, Firecrawl, sandbox remota ou publicação será acionado nessa etapa; não se alegará teste ponta a ponta.

## Motivo da linha-base
Antes de implantar ou integrar, precisamos descobrir se o projeto upstream puro instala e compila de forma reproduzível. Qualquer falha deverá ser atribuída ao passo e log exatos, sem introduzir patches silenciosos ou alterar o projeto original.

## Fragilidade já identificada na fonte original
O arquivo `package.json` define `test:all` como `npm run test:integration && npm run test:api && npm run test:code`, mas **não define `test:integration`**. Isso impede aceitar `npm run test:all` como evidência de qualidade completa.

## Próximos gates, ainda NÃO executados
1. Executar o Open Lovable original com credenciais isoladas, limites explícitos de custo e acesso privado.
2. Fazer missão real de aplicativo com API e banco de dados; obter arquivos originais, verificar build, operações CRUD e persistência.
3. Aplicar testes independentes de segurança, autorização por usuário, isolamento por missão, Playwright, falhas e custos.
4. Somente então decidir adoção integral, integração por API ou substituição do motor do OLYMPUS.

## Restrições de governança
Repositório OLYMPUS atualmente público: nenhuma chave, projeto privado, dump do Mac ou credencial pode ser enviada. Não existe aprovação para instalação no Mac, consumo pago ou promoção para `main`. O fluxo `/cloud/missions` da versão atual permanece intacto.
