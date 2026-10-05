# OLYMPUS Live Execution Monitor

The terminal entrypoint now displays an operational progress indicator while a local step is running.

The monitor is intentionally runtime-driven: it does not expose hidden model reasoning. It reports the current bounded operation and elapsed time so the user can see that the process is alive.

Displayed activity labels include:

- preparando contexto
- analisando repositório
- selecionando contexto
- planejando próxima ação
- aguardando modelo
- executando ação
- validando resultado

These labels are a visible activity indicator for the current bounded operation, not a claim about hidden chain-of-thought or exact internal sub-step timing.
