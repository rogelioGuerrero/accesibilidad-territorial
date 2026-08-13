"""
Clase base para agentes autónomos con Groq + tool calling + human-in-the-loop.

Filosofía NOOA (6 capacidades del harness):
1. Typed input/output — métodos con type hints y dataclasses
2. Pass by reference — ToolResult con bounded previews, no serialización completa
3. Code as action — @strategy decorator para métodos completados por LLM
4. Programmable loop engineering — pipelines como Python ordinario
5. Explicit object state — campos tipados en el objeto agente
6. Model-callable harness APIs — tools para inspeccionar contexto, historial, memoria

Pipeline común (heredado):
1. Groq compound busca noticias → detecta eventos
2. LLM decide si activar (tool calling)
3. HUMANO aprueba antes de ejecutar
4. Agente ejecuta tools (resultados por referencia, no serializados)
5. HUMANO valida plan final

Para crear un nuevo agente, heredar de AutonomousAgent y override:
- tools_schema: lista de tools disponibles
- system_prompt: qué decide el LLM
- agent_name: nombre del agente
- default_search_query: qué buscar por defecto
- _execute_tool: cómo ejecutar cada tool
- _prepare_event: cómo preparar el evento antes de proponer
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from llm_utils import llm_call
from harness import ToolResult, ResultRegistry
from memory_store import MemoryStore
from harness_api import HarnessAPI, HARNESS_TOOLS

load_dotenv()

logger = logging.getLogger(__name__)


class AutonomousAgent(ABC):
    """
    Motor base: Groq compound + tool calling + human-in-the-loop.

    Subclases definen:
        - tools_schema: tools disponibles para el LLM
        - system_prompt: instrucciones del agente
        - agent_name: nombre para logs
        - default_search_query: búsqueda por defecto
        - _execute_tool: implementación de cada tool
        - _prepare_event: preparación del evento antes de proponer

    Métodos comunes (heredados, no se override):
        - detect_event: busca noticias con Groq
        - propose_actions: LLM propone tools
        - approve_and_execute: humano aprueba, agente ejecuta
        - validate_plan: humano valida plan final
        - run_full_pipeline: pipeline completo
    """

    # ─── Atributos de clase (override en subclase) ──────────────
    tools_schema: list[dict] = []
    system_prompt: str = ""
    agent_name: str = "AutonomousAgent"
    default_search_query: str = "evento reciente"

    # ─── Constructor ─────────────────────────────────────────────

    def __init__(self, memory_db_path: str | Path | None = None):
        self._tool_results: dict[str, Any] = {}
        self._pending_tool_calls: list = []

        # NOOA: Pass-by-reference — tool results stay as live Python objects
        self._result_registry = ResultRegistry()

        # NOOA: Long-term memory — SQLite knowledge graph
        self._memory = MemoryStore(memory_db_path)

        # NOOA: Model-callable harness APIs
        self._harness = HarnessAPI(self, self._memory, self._result_registry)

        # Merge harness tools into agent tools (subclass tools_schema + harness tools)
        self._full_tools_schema = self.tools_schema + HARNESS_TOOLS

    # ─── Métodos abstractos (override obligatorio) ──────────────

    @abstractmethod
    def _execute_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Ejecuta un tool específico. Override en cada subclase."""
        ...

    @abstractmethod
    def _prepare_event(self, event_data: dict[str, Any]) -> None:
        """Prepara el evento antes de proponer acciones. Override en cada subclase."""
        ...

    # ─── Métodos comunes (heredados) ────────────────────────────

    def detect_event(self, query: str | None = None) -> str:
        """
        Busca noticias web sobre eventos y detecta relevancia.

        Usa Groq compound con tool calling.
        Incluye harness tools para que el LLM pueda inspeccionar contexto y memoria.
        """
        search_query = query or self.default_search_query

        logger.info("[%s] Buscando: '%s'", self.agent_name, search_query)

        response = llm_call(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Busca en la web: {search_query}. ¿Hay algún evento relevante?"},
            ],
            tools=self._full_tools_schema,
            temperature=0.3,
            max_tokens=1000,
        )

        message = response.choices[0].message

        if hasattr(message, "tool_calls") and message.tool_calls:
            self._pending_tool_calls = message.tool_calls
            logger.info("[%s] Propone %d acciones:", self.agent_name, len(message.tool_calls))
            for i, tc in enumerate(message.tool_calls, 1):
                logger.info("   %d. %s(%s)", i, tc.function.name, tc.function.arguments)
        else:
            self._pending_tool_calls = []

        content = message.content or "Sin respuesta del agente."
        logger.info("[%s] %s", self.agent_name, content)
        return content

    def propose_actions(self, event_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        LLM analiza un evento y propone qué tools ejecutar.

        NOOA pass-by-reference: solo envía previews de resultados previos,
        no el JSON completo. El LLM puede usar get_tool_result(name) para
        acceder al valor completo si lo necesita.
        """
        event_json = json.dumps(event_data, ensure_ascii=False)

        # Build context with result previews (pass-by-reference)
        results_context = self._result_registry.build_context_block()

        user_msg = f"""
Evento detectado:
{event_json}

Analiza este evento y decide qué tools ejecutar.
Si es relevante, propone ejecutar los tools necesarios.
Si no es relevante, explica por qué no.
"""
        if results_context:
            user_msg += f"\n\n{results_context}"

        response = llm_call(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=self._full_tools_schema,
            temperature=0.3,
            max_tokens=1500,
        )

        message = response.choices[0].message
        content = message.content or ""

        logger.info("[%s] Análisis:\n%s", self.agent_name, content)

        if hasattr(message, "tool_calls") and message.tool_calls:
            proposed = []
            for tc in message.tool_calls:
                args_str = tc.function.arguments
                try:
                    args = json.loads(args_str) if args_str else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}
                proposed.append({
                    "name": tc.function.name,
                    "arguments": args,
                })

            logger.info("Tools propuestos (%d):", len(proposed))
            for i, t in enumerate(proposed, 1):
                logger.info("   %d. %s(%s)", i, t['name'], json.dumps(t['arguments'], ensure_ascii=False))

            return proposed

        logger.info("[%s] No propone tools (evento no relevante)", self.agent_name)
        return []

    def approve_and_execute(
        self,
        proposed_tools: list[dict[str, Any]],
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        """
        Human-in-the-loop: humano aprueba, agente ejecuta.
        """
        if not proposed_tools:
            logger.warning("No hay tools para ejecutar")
            return {}

        # ─── HUMAN IN THE LOOP ──────────────────────────────────
        if not auto_approve:
            print("\n" + "=" * 60)
            print(f"  ⚠ APROBACIÓN HUMANA — [{self.agent_name}]")
            print("=" * 60)
            print(f"\n  El agente propone ejecutar {len(proposed_tools)} acciones:")
            for i, t in enumerate(proposed_tools, 1):
                print(f"    {i}. {t['name']}")

            respuesta = input("\n  ¿Aprobar ejecución? (s/n/editar): ").strip().lower()

            if respuesta == "n":
                print("  ❌ Ejecución cancelada por el humano")
                return {"status": "cancelled", "reason": "humano rechazó"}
            elif respuesta == "editar":
                print("  ✏ Edición manual — implementar según necesidad")
                return {"status": "edited", "reason": "humano editó"}
            elif respuesta != "s":
                print("  ❌ Respuesta no válida, cancelando")
                return {"status": "cancelled", "reason": "respuesta inválida"}

            print("  ✅ Aprobado por humano — ejecutando...\n")
        else:
            logger.info("Auto-aprobado (modo demo) — ejecutando...")

        # ─── Ejecutar tools ──────────────────────────────────────
        results = {}

        for tool in proposed_tools:
            name = tool["name"]
            args = tool.get("arguments") or {}

            logger.info("Ejecutando: %s...", name)

            try:
                # Route harness tools to HarnessAPI, agent tools to _execute_tool
                if name in {t["function"]["name"] for t in HARNESS_TOOLS}:
                    raw_result = self._harness.execute(name, args)
                else:
                    raw_result = self._execute_tool(name, args)

                # NOOA pass-by-reference: store as ToolResult with bounded preview
                tr = ToolResult.from_value(name, raw_result)
                self._result_registry.store(tr)
                self._tool_results[name] = raw_result
                results[name] = raw_result
                logger.info("✅ %s completado — preview: %s", name, tr.preview[:120])

            except Exception as e:
                logger.error("❌ %s falló: %s", name, e)
                tr = ToolResult.from_error(name, str(e))
                self._result_registry.store(tr)
                results[name] = {"error": str(e)}

        return results

    def validate_plan(self, plan: str, auto_approve: bool = False) -> bool:
        """
        Human-in-the-loop: humano valida plan final.
        """
        logger.info("=" * 60)
        logger.info("  📋 PLAN GENERADO — [%s]", self.agent_name)
        logger.info("=" * 60)
        logger.info("\n%s", plan)

        if auto_approve:
            logger.info("Auto-aprobado (modo demo)")
            return True

        print("\n" + "=" * 60)
        print("  ⚠ VALIDACIÓN HUMANA — ¿Notificar?")
        print("=" * 60)

        respuesta = input("\n  ¿Aprobar y notificar? (s/n): ").strip().lower()

        if respuesta == "s":
            logger.info("✅ Plan aprobado — notificando...")
            return True
        else:
            logger.info("❌ Plan rechazado — el agente esperará ajustes")
            return False

    def run_full_pipeline(
        self,
        event_data: dict,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        """
        Pipeline completo: preparar → proponer → aprobar → ejecutar → validar.
        """
        logger.info("═" * 60)
        logger.info("  %s — Human in the Loop", self.agent_name.upper())
        logger.info("═" * 60)

        # 1. Preparar evento (override en subclase)
        logger.info("▶ Preparando evento...")
        self._prepare_event(event_data)
        logger.info("✅ Evento preparado")

        # 2. Proponer acciones (común)
        proposed = self.propose_actions(event_data)

        if not proposed:
            return {"status": "no_action", "reason": "evento no relevante"}

        # 3. Aprobar y ejecutar (común)
        results = self.approve_and_execute(proposed, auto_approve=auto_approve)

        if results.get("status") == "cancelled":
            return results

        # 4. Validar plan final (común)
        if "generate_response_plan" in results:
            plan = results["generate_response_plan"].get("plan", "")
            approved = self.validate_plan(plan, auto_approve=auto_approve)

            return {
                "status": "approved" if approved else "rejected",
                "results": results,
                "plan": plan,
            }

        return {"status": "completed", "results": results}
