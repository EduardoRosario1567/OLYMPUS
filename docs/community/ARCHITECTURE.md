# Arquitetura para colaboradores

O OLYMPUS distingue decisão, execução e avaliação. Uma resposta do provedor ou
um processo sem erro não são, por si só, evidência de que a entrega atende ao objetivo.

| Camada | Local | Regra |
| --- | --- | --- |
| Decisão | `olympus/classifier.py`, `olympus/registry.py`, `olympus/decision_engine.py` | Preservar contratos sem acoplar o núcleo a um fornecedor |
| Pipeline e avaliação | `olympus/pipeline.py`, `olympus/intelligence_loop.py`, `olympus/judge/` | Separar decisão, execução e julgamento |
| Integrações | Módulos próprios em `olympus/` e serviços em `backend/` | Tratar autenticação, limites, falhas e custos |
| Produto | `backend/`, `frontend/` | Estados claros e contratos autenticados |
| Qualificação | `tests/`, `.github/workflows/`, `scripts/` | Evidência verificável; distinguir simulação e prova real |

Leia [AGENTS.md](../../AGENTS.md), fonte das regras para agentes. Discuta mudanças
de arquitetura, persistência ou dependências. Não atualize `vendor/` por
conveniência de outra mudança. Documentos antigos em `docs/` são registros
históricos; não substituem o código e a CI do commit analisado.
