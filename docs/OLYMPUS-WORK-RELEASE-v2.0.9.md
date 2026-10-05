# OLYMPUS Professional v2.0.9 — atualização segura do frontend

## Evidência do Mac

A instalação da v2.0.8 concluiu Python e npm, mas parou ao substituir o
frontend anterior. O processo deixou de servir ou permaneceu como processo
residual, enquanto o inicializador verificava apenas a existência do PID.
O npm também relatou vulnerabilidades na linha antiga do Next.js.

## Correção

- A atualização verifica a liberação real das portas 3000 e 8000, não a mera
  existência de um PID que pode estar finalizado ou residual.
- Antes de encerrar qualquer processo, continuam obrigatórias as verificações
  de comando e diretório Olympus.
- Um frontend Next.js resistente ao encerramento normal recebe uma única
  finalização forçada e limitada, somente após uma segunda validação de PID,
  comando e diretório.
- Mudança de proprietário da porta cancela a operação sem encerrar o novo
  processo.
- Next.js foi fixado em 15.5.24, versão Maintenance LTS indicada pela correção
  oficial de segurança de agosto de 2026.
- React e React DOM foram fixados em 18.3.1 para evitar resolução variável entre
  instalações.
