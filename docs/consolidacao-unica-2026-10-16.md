# OLYMPUS — qualificação da consolidação única (WIP)

Estado: **BLOCKED / NÃO HOMOLOGADO**. Este documento não afirma que a consolidação ou a missão Rosales Café foram concluídas.

## Procedência do código
- Base desta branch: `olympus-3.0.9-isolation-qualification` em `9e1762f4f1399c0fe835f5e2bc8bc41368fd7439`.
- Conjunto complementar: `olympus-static-delivery-safe-v1` em `18a89577ea7a2ef1a537a31b297324c1f364183e` (PR #4, ainda draft).
- `main` estável permanece intacta; nenhum merge automático.
- Os ramos complementares divergem; 14 caminhos foram alterados em ambos com relação à `main`. As revisões devem preservar as duas linhas de trabalho.

## Arquivos comuns que exigem revisão
- `.github/workflows/ci.yml`
- `backend/app/api/cloud_projects.py`
- `backend/app/api/cloud_runtime.py`
- `backend/app/api/missions.py`
- `frontend/app/globals.css`
- `frontend/package-lock.json`
- `frontend/package.json`
- `olympus/agent/autonomous_developer.py`
- `olympus/agent/executor.py`
- `olympus/agent/test_runner.py`
- `scripts/blind_mission_gate.py`
- `scripts/macos_command_gate.py`
- `tests/frontend_contract.mjs`
- `tests/test_frontend_dependency_security_v209.py`

## Inventário local — apenas metadados, não importar cegamente
Um inventário externo apontou 57 diretórios e múltiplos conjuntos de código. A comparação pontual de uma instalação RC2 com uma pasta UPDATE encontrou 491 arquivos selecionados iguais, 49 caminhos com hashes diferentes, 42 caminhos presentes apenas no UPDATE e 2 apenas no RC2. Essas contagens cobrem apenas os arquivos selecionados pelo inventário; não provam integridade de dados persistentes, mídias, credenciais ou instaladores.

**Não enviar inventários locais completos, dumps, bancos ou credenciais ao repositório público.** Arquivos locais selecionados só poderão ser considerados depois de inspeção de conteúdo e redaction / revisão de segurança.

## Aceitação obrigatória
1. Conciliação por função dos dois ramos, mantendo testes de isolamento, atualização, failover, backend, frontend e entrega estática.
2. Restaurar seletivamente funcionalidades locais que não existam no GitHub depois de revisão de fonte; não equiparar arquivo adicional a funcionalidade apta.
3. CI verde para backend, frontend, contratos de compatibilidade e isolamento; sem usar o Mac para regressão reproduzível.
4. Instalador incremental no mesmo destino, operação com backup/rollback validado, preservação de `.env`, bancos, projetos e histórico; uma única linha de atualização pelo usuário.
5. Solução de execução segura compatível com Mac Intel macOS 12 e pouco espaço, sem presumir Docker disponível. Serviços remotos externos exigem autorização e orçamento.
6. Missão real Rosales Café executada pelo agente com provedor real, artefato preservado, hashes, QA em navegador e evidência. Marcar DONE apenas com prova; caso contrário BLOCKED.
7. Não alterar `main` ou publicar entrega sem aprovação. A limpeza de diretórios locais exige comprovação de equivalência dos dados excluídos da varredura e backup verificável.

## Situação
- [x] Criada branch de qualificação separada da `main`.
- [x] Identificados arquivos de potencial conflito e lacunas locais por hashes.
- [ ] Conciliação de código e testes.
- [ ] Revisão seletiva de conteúdo local.
- [ ] Validação CI da versão integrada.
- [ ] Pacote único de atualização com rollback testado.
- [ ] Smoke final local e missão real Rosales Café.
