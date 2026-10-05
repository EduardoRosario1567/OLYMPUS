# PATCH-006 — OLYMPUS AGENT RUNTIME

## MISSÃO

Evoluir o OLYMPUS Dev Agent de gerador linear para um
Agent Runtime autônomo, model-agnostic e orientado a microações.

O runtime deve controlar:
- estado
- contexto
- ações
- permissões
- execução
- verificação
- retry
- parada

O modelo apenas raciocina e propõe ações.

## PRINCÍPIOS

- não enviar o repositório inteiro ao modelo
- não regenerar arquivos inteiros para pequenas alterações
- uma inferência = uma ação pequena
- runtime controla limites e parada
- modelo nunca executa filesystem ou shell diretamente
- operações perigosas devem bloquear
- modelos continuam intercambiáveis
- reutilizar componentes existentes
- Python 3.9
- stdlib quando possível
- manter compatibilidade com V1

## COMPONENTES

### olympus/agent/state.py

Criar AgentState frozen.

Campos:
task
task_type
status
iteration
max_iterations
selected_model
current_action
files_read
files_modified
tests_run
observations
errors
quality_score
final_confidence
metadata

Estados:
CREATED
PLANNING
ACTING
OBSERVING
VERIFYING
RETRYING
COMPLETED
BLOCKED
FAILED

### olympus/agent/actions.py

Ações estruturadas:

READ_FILE
SEARCH_CODE
CREATE_FILE
PATCH_FILE
RUN_TEST
INSPECT_RESULT
FINISH

Cada ação:
type
target
payload
reason
metadata

### olympus/agent/repo_map.py

Mapa leve do repositório.

Para Python usar AST.

Indexar:
- arquivos Python
- módulos
- classes
- funções
- imports
- testes

Expor:
build_repo_map()
find_symbol()
find_related_files()
find_test_for_file()
rank_relevant_files()

Não usar embeddings na V1.

### olympus/agent/context_engine.py

Selecionar contexto limitado.

Prioridade:
1. caminhos explícitos
2. símbolos citados
3. arquivos relacionados
4. testes relacionados
5. imports/dependências
6. manifests

Limites:
max_files
max_chars
max_lines

Registrar motivo da seleção.

### olympus/agent/planner.py

Receber:
task
state summary
context
available actions

Retornar UMA próxima ação estruturada.

Não implementar a tarefa inteira em uma chamada.

### olympus/agent/executor.py

Executar ações deterministicamente.

READ_FILE → leitura segura
SEARCH_CODE → busca local
CREATE_FILE → SafeApply
PATCH_FILE → PatchEngine
RUN_TEST → TargetedTestRunner
INSPECT_RESULT → observação
FINISH → encerramento

Proibir:
rm
git reset
git clean
git push
instalação automática
shell arbitrário

### olympus/agent/patch_engine.py

Implementar edições estruturadas:

replace_lines
insert_after_symbol
insert_before_symbol
replace_function
append_block

Usar AST/símbolos quando possível.

Nunca exigir que o modelo reproduza o arquivo inteiro.

Validar:
- path
- símbolo
- operação
- tamanho da alteração
- sintaxe Python

### olympus/agent/verifier.py

Validar na ordem:

1. sintaxe
2. teste direcionado
3. testes relacionados
4. diff
5. RuleBasedJudge quando aplicável
6. FinalConfidence quando aplicável

SafeApply não equivale a sucesso da tarefa.

### olympus/agent/autonomy.py

Sem confirmação para:

read
search
create allowed file
patch allowed file
run targeted test
retry
repair

Exigir usuário para:

objetivo ambíguo
operação destrutiva
fora do workspace
rede não autorizada
instalação de dependência
migration
budget excedido
violação de segurança

Não usar:
"Posso continuar?"
"Devo prosseguir?"

### olympus/agent/loop.py

Loop central:

PLAN
ACT
OBSERVE
VERIFY
DECIDE_NEXT
STOP

Limite default:
12 iterações.

Nunca permitir loop infinito.

Modelo não controla o limite.

### ROUTING

Reutilizar DecisionEngine.

Não hardcodar modelo no loop.

Falha técnica:
timeout
provider_error
rate_limited
unavailable

→ próximo candidato elegível.

## OBSERVABILIDADE

Registrar por iteração:
- iteration
- action
- target
- model
- latency
- observation
- verification
- next decision

## COMPATIBILIDADE

Não quebrar:
DecisionEngine
TaskClassifier
ModelRegistry
RoutingAdapter
OmniRouteAdapter
ExecutionResult
ExecutionStatus
Judge
QualityEvaluation
FinalConfidence
SafeApply
TargetedTestRunner
RepairLoop
OLYMPUS.app

## TESTES

Criar testes unitários para:
- estado
- transições
- limites
- ações
- segurança
- repo map
- AST
- contexto
- orçamento
- planner
- executor
- patch
- sintaxe
- testes
- fallback
- retry
- stop
- blocked
- autonomy

Adicionar integração opcional:

RUN_REAL_AGENT_LOOP=1

A integração real deve usar diretório temporário.

## ESTRATÉGIA DE IMPLEMENTAÇÃO

NÃO implementar tudo em uma geração.

Decompor internamente:

1 state/actions
2 repo_map
3 context_engine
4 planner
5 patch_engine
6 executor
7 verifier
8 autonomy
9 loop
10 integração
11 regressão

Cada subetapa deve:
- ter escopo pequeno
- validar sintaxe
- executar testes relevantes
- continuar somente se passar

## ACCEPTANCE

O PATCH só passa se:

- AgentLoop end-to-end funcionar
- edição existente funcionar
- contexto for limitado
- modelo propuser ações
- runtime executar ações
- operações seguras não pedirem confirmação
- perigosas bloquearem
- fallback funcionar
- limite impedir loops
- testes determinarem sucesso
- V1 continuar funcionando
- regressão completa passar
- integração real temporária passar

## RESULTADO

Gerar PATCH-006 REPORT.

Não iniciar PATCH-007.
Parar somente após o relatório.
