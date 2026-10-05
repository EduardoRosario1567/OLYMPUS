# OLYMPUS Work v2.3.0

## Objetivo desta versão

Esta versão troca a repetição de tentativas por continuidade verificável. Ela
não afirma que uma conta gratuita externa ficará sempre disponível; garante que
o Olympus limita tentativas, preserva o trabalho, diversifica provedores e não
entra em uma rota paga sem autorização explícita.

## Compilador de Missões

- Traduz o pedido humano localmente, sem chamada de modelo.
- Mantém objetivo, requisitos, restrições negativas e critérios de aceitação.
- Preserva o pedido original e seu SHA-256 no checkpoint.
- Envia um contrato estável e compacto para cada IA.

## Continuidade entre modelos

- O orçamento de iterações pertence à missão inteira; ele não recomeça em cada modelo.
- O handoff inclui arquivos lidos e modificados, testes, último erro e saldo de iterações.
- Antes de gastar outro token, a próxima IA verifica se o resultado existente já atende à missão.
- Cotas organizacionais/TPM bloqueiam os modelos irmãos do mesmo provedor e avançam para uma fonte independente.
- A cadeia gratuita é limitada e diversificada por provedor.

## Gratuito e pago

- Modos: somente gratuito, gratuito seguido de continuação paga, ou premium direto.
- Continuação paga requer chave própria, ativação do provedor, consentimento na missão e teto estimado positivo.
- A guarda de custo reserva uma estimativa conservadora antes da chamada e acumula o uso informado pela API. Ausência de telemetria conta como uso máximo reservado.
- O valor é uma proteção estimada do Olympus; a fatura oficial permanece sendo a do provedor.

## Provedores

Além de OmniRoute/OpenRouter, Groq, Cerebras, Ollama, OpenAI, Gemini e Mistral,
o catálogo inclui Z.AI, Cloudflare Workers AI e Kimi. O runtime consulta o
catálogo vivo antes de recorrer a nomes padrão, evitando manter uma lista longa
de modelos descontinuados.

## Skills

- Tela e API próprias, separadas de integrações de infraestrutura.
- Skills nativas continuam ativas e definem orientação e verificação.
- Skills externas seguem `SKILL.md`, entram como `review_required` e não executam código na importação.
- Importação GitHub aceita somente HTTPS público, impõe limites de arquivo e conteúdo, rejeita caminhos inseguros e impede substituir uma skill nativa.
- Conteúdo externo permanece subordinado ao pedido, às políticas do Olympus e às restrições das skills nativas.

## Evidência interna

O teste de apresentação não usa provedores externos. Ele constrói e publica uma
landing page, força a primeira rota a falhar após criar um arquivo, confirma o
handoff desse arquivo para outra rota, repara o conteúdo, valida responsividade,
acessibilidade e interação, abre preview HTTP, cria versão e prepara ZIP.

Execute:

```bash
PYTHONPATH=.:backend python3 scripts/investor_landing_smoke.py
```

## Limites honestos

- O ensaio interno prova o comportamento do Olympus com respostas controladas; não prova cota, latência ou compatibilidade futura de APIs de terceiros.
- Cada conexão real deve ser confirmada pelo botão `Testar`, que faz uma geração mínima e pode consumir cota.
- Para uma apresentação externa, mantenha pelo menos duas fontes independentes confirmadas e preserve uma versão local já homologada do projeto demonstrado.
