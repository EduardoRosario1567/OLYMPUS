# OLYMPUS Work v1.4 — Conversa, anexos e identidade

## Resultado

A experiência principal foi reduzida ao fluxo essencial: o usuário escreve um
pedido, pode anexar material, acompanha a execução como uma conversa e baixa a
entrega no mesmo lugar. A interface não mostra provedor, modelo ou detalhes da
orquestração na jornada principal.

## Mudanças

- Campo de pedido central inspirado no padrão conversacional contemporâneo.
- Upload por botão `+`, seletor de arquivos e arrastar e soltar.
- Até 10 anexos por missão, 25 por projeto e 20 MB por arquivo.
- Suporte a texto/código, PDF, DOCX, XLSX, PNG, JPEG, WebP, GIF e ZIP.
- Extração local de texto de DOCX, XLSX e PDFs digitais simples, sem dependência
  adicional; imagens permanecem disponíveis como ativos visuais.
- ZIPs são expandidos em área isolada, com bloqueio de travessia de diretório,
  links simbólicos e expansão excessiva.
- O agente passa a mapear `attachments/` e `imports/` como contexto do projeto.
- A entrega final inclui os anexos e arquivos importados, mas não o manifesto
  interno.
- Nova marca vetorial monocromática de Zeus, sem artefatos de baixa resolução ou
  marca-d'água, aplicada a login, navegação e conversa.

## Limites honestos

- Imagens e PDFs digitalizados ainda não recebem OCR/visão automaticamente.
- Esta versão não adiciona editor visual, preview ao vivo, publicação em um
  clique, sincronização GitHub ou histórico visual de versões.
- A seleção de modelo continua sendo responsabilidade interna do Olympus e do
  OmniRoute; ela não é exposta ao usuário.

## Verificação

- 530 testes da suíte segura executados com sucesso; 8 testes opcionais foram
  ignorados pelas próprias condições de integração.
- Três módulos de teste HTTP não puderam ser carregados neste executor porque
  FastAPI/PyJWT não estão instalados aqui; o inicializador do pacote instala
  essas dependências no ambiente virtual do macOS.
- O build Next.js não foi repetido neste executor porque `node_modules` não faz
  parte do pacote e nenhuma instalação de dependências foi autorizada durante
  a validação. As verificações estruturais do frontend passaram.
- Compilação Python concluída sem erros.
- Nenhuma dependência ou migração adicionada.
