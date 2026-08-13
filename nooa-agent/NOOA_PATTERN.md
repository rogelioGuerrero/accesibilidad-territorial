# NOOA Pattern — Agent Harness Engineering con POO

**Fuente:** https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/
**Código:** https://github.com/nvidia-nemo/labs-OO-Agents
**Paper:** https://arxiv.org/abs/2607.20709

## Las 6 capacidades del harness

1. **Typed input/output** — type hints + dataclasses como contratos
2. **Pass by reference** — ToolResult con bounded previews, no JSON completo al contexto
3. **Code as action** — @strategy decorator, métodos con `...` completados por LLM en runtime
4. **Programmable loop engineering** — pipelines como Python ordinario, no DAGs
5. **Explicit object state** — campos tipados en el objeto agente
6. **Model-callable harness APIs** — tools para que el LLM inspeccione contexto, historial, memoria

## La receta (3 reglas)

1. **El agente es una clase Python.** Docstring = system prompt. Campos = estado. Métodos = tools.
2. **Las tools son métodos.** Sin JSON schema suelto, sin router aparte.
3. **El harness es `__init__` + loop.** `chat()` orquesta: LLM → tools → validación → respuesta.

## Lo que NO necesitas

- LangChain / LangGraph
- DAG de nodos
- Prompts en YAML
- Orchestrator separado
- Serializar todo a JSON entre pasos

## Resultados reportados por NVIDIA

- SWE-bench Verified: 82.2% (GPT-5.5)
- CyberGym L1: 86.8%
- ARC-AGI-3: 85.1% RHAE (<$20/game)
- ~50% menos tokens vs harnesses tradicionales (pass-by-reference)

## Aplicación a cualquier proyecto

| Paso | Qué haces |
|---|---|
| 1 | Define la clase con su docstring (el prompt) |
| 2 | Campos = estado que el LLM puede ver/modificar |
| 3 | Métodos con cuerpo = código determinístico |
| 4 | Métodos con `...` = LLM completa en runtime |
| 5 | `chat()` = loop: LLM → tools → validate → respond |
| 6 | MemoryStore = SQLite + knowledge graph (opcional) |
