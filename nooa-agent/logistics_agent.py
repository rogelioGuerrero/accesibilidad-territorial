"""
Agente orquestador de logística con tool calling nativo.

Filosofía NOOA:
- Clase = agente
- Métodos = capabilities (tools que el LLM invoca vía tool calling)
- Campos = estado (historial de chat, último resultado)
- Docstrings = prompts

Un solo punto de entrada: el usuario chatea en lenguaje natural,
el LLM decide qué motor OR-Tools ejecutar, devuelve el resultado
explicado en español.

Reemplaza a VRPAgent, ChatVRPAgent y MultiEngineAgent.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from llm_utils import llm_call
from config import AVAILABLE_MATRICES
from harness import ToolResult, ResultRegistry
from memory_store import MemoryStore
from harness_api import HarnessAPI, HARNESS_TOOLS

from vrp_solver.models import Location, LocationType, OptimizeRequest, Vehicle
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request

from engines.bin_packing import (
    BinPackingItem, BinPackingBin, BinPackingRequest, BinPackingSolver,
)
from engines.min_cost_flow import (
    MinCostFlowSolver, build_school_assignment,
)

logger = logging.getLogger(__name__)


# ─── Tools schema (JSON para tool calling del LLM) ───────────────────

TOOLS_LOGISTICS = [
    {
        "type": "function",
        "function": {
            "name": "optimize_vrp",
            "description": (
                "Optimiza rutas de vehículos (VRP). Usa OR-Tools para encontrar "
                "las rutas óptimas que visiten todos los puntos de entrega "
                "minimizando distancia. Requiere coordenadas reales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "description": "Lista de puntos. El primero es el depósito.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "coords": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "description": "[lat, lng]",
                                },
                                "type": {"type": "string", "enum": ["depot", "delivery"]},
                                "weight_demand": {"type": "number", "description": "kg (solo entregas)"},
                                "service_time": {"type": "integer", "description": "segundos (default 300)"},
                            },
                            "required": ["id", "name", "coords", "type"],
                        },
                    },
                    "vehicles": {
                        "type": "array",
                        "description": "Lista de vehículos.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "start_location_id": {"type": "string"},
                                "end_location_id": {"type": "string"},
                                "weight_capacity": {"type": "number", "description": "kg"},
                            },
                            "required": ["id", "name", "start_location_id", "end_location_id", "weight_capacity"],
                        },
                    },
                },
                "required": ["locations", "vehicles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_bin_packing",
            "description": (
                "Empaqueta items en cajas minimizando el número de cajas usadas. "
                "Usa OR-Tools Knapsack. Cada item tiene peso, cada caja tiene capacidad."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "weight": {"type": "number", "description": "kg"},
                            },
                            "required": ["id", "name", "weight"],
                        },
                    },
                    "bins": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "capacity_weight": {"type": "number", "description": "kg"},
                            },
                            "required": ["id", "name", "capacity_weight"],
                        },
                    },
                },
                "required": ["items", "bins"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_min_cost_flow",
            "description": (
                "Asigna niños de barrios a escuelas minimizando la distancia total. "
                "Usa OR-Tools Min Cost Flow. Cada barrio tiene N niños, cada escuela "
                "tiene capacidad de cupos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "schools": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "coords": {"type": "array", "items": {"type": "number"}},
                                "capacity": {"type": "integer", "description": "cupos"},
                            },
                            "required": ["id", "name", "coords", "capacity"],
                        },
                    },
                    "neighborhoods": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "coords": {"type": "array", "items": {"type": "number"}},
                                "children": {"type": "integer", "description": "número de niños"},
                            },
                            "required": ["id", "name", "coords", "children"],
                        },
                    },
                },
                "required": ["schools", "neighborhoods"],
            },
        },
    },
]


# ─── System prompt ───────────────────────────────────────────────────

def _build_system_prompt(city: str, coords: list[tuple[float, float]]) -> str:
    coords_str = "\n".join(
        f"  Punto {i}: lat={lat}, lng={lng}"
        for i, (lat, lng) in enumerate(coords)
    )
    return f"""Eres un agente de logística que conversa con el usuario y resuelve
problemas de optimización usando tool calling.

## Capacidades disponibles:
1. **optimize_vrp** — Rutas de vehículos (VRP). Optimiza qué vehículo visita qué puntos.
2. **optimize_bin_packing** — Empaquetado. Distribuye items en cajas minimizando cajas usadas.
3. **optimize_min_cost_flow** — Asignación escolar. Asigna niños a escuelas por distancia.

## Coordenadas disponibles para VRP en {city} (máximo {len(coords)} puntos, [lat, lng]):
{coords_str}

## Reglas:
- Para VRP, el punto 0 SIEMPRE es el depósito (type="depot").
- Los puntos 1 a {len(coords)-1} son entregas (type="delivery").
- weight_demand es POSITIVO (ej: 10.0 = 10kg).
- service_time en segundos (default: 300 = 5 min).
- Cada vehículo inicia y termina en el depósito.
- La capacidad total de vehículos debe ser >= demanda total.
- Para bin_packing y min_cost_flow, el usuario puede dar sus propios datos.

## Flujo:
1. Saluda brevemente y pregunta qué necesita el usuario.
2. Si falta información, pregunta naturalmente.
3. Cuando tengas TODA la info necesaria, llama al tool correspondiente.
   NO pidas confirmación. NO digas "Entendido". Simplemente ejecuta.
4. Cuando recibas el resultado del tool, explícalo en español claro y natural.
   No uses JSON ni markdown en la explicación final."""


# ─── Agente ──────────────────────────────────────────────────────────


class LogisticsAgent:
    """
    Agente orquestador de logística con tool calling nativo.

    Estado:
        - city: ciudad activa (bogota/madrid)
        - _coords: coordenadas disponibles para VRP
        - _messages: historial de chat
        - _last_result: último resultado del solver

    Capabilities (tools que el LLM invoca):
        - optimize_vrp: rutas de vehículos con OR-Tools VRP
        - optimize_bin_packing: empaquetado con OR-Tools Knapsack
        - optimize_min_cost_flow: asignación escolar con Min Cost Flow

    Punto de entrada:
        - chat(user_input): un turno de conversación
    """

    def __init__(self, city: str = "bogota", memory_db_path: str | None = None):
        if city not in AVAILABLE_MATRICES:
            raise ValueError(f"Ciudad no disponible. Usa: {list(AVAILABLE_MATRICES.keys())}")
        self.city = city
        self._fixture = AVAILABLE_MATRICES[city]
        self._coords = self._load_coords()
        self._messages: list[dict] = []
        self._last_result: Any = None

        # NOOA: Pass-by-reference — tool results stay as live Python objects
        self._result_registry = ResultRegistry()

        # NOOA: Long-term memory — SQLite knowledge graph
        self._memory = MemoryStore(memory_db_path)

        # NOOA: Model-callable harness APIs
        self._harness = HarnessAPI(self, self._memory, self._result_registry)

        self._init_system_prompt()

    def _load_coords(self) -> list[tuple[float, float]]:
        with open(self._fixture["coords"]) as f:
            return [tuple(c) for c in json.load(f)["coords"]]

    def _init_system_prompt(self):
        system = _build_system_prompt(self.city, self._coords)
        self._messages = [{"role": "system", "content": system}]

    # ─── Tools (métodos = capabilities) ──────────────────────────

    def optimize_vrp(self, locations: list[dict], vehicles: list[dict]) -> dict:
        """
        Resuelve VRP con OR-Tools usando la matriz cacheada de la ciudad.
        Devuelve un dict con rutas, distancias y estadísticas.
        """
        try:
            locs = [Location(**loc) for loc in locations]
            vehs = [Vehicle(**veh) for veh in vehicles]
            request = OptimizeRequest(locations=locs, vehicles=vehs)
        except Exception as e:
            return {"error": f"Error construyendo request: {e}"}

        validation = validate_request(request)
        if not validation.is_valid:
            return {
                "error": "Validación falló",
                "errors": [e.message for e in validation.errors],
            }

        solver = VRPSolver.from_request(
            request,
            matrix_provider="cached",
            matrix_path=self._fixture["matrix"],
        )
        result = solver.solve()
        self._last_result = result

        if result.errors:
            return {"error": "Solver encontró errores", "errors": [e.message for e in result.errors]}

        routes = []
        for r in result.routes:
            routes.append({
                "vehicle": r.vehicle_name or r.vehicle_id,
                "stops": [s.name or s.location_id for s in r.stops],
                "distance_km": round(r.total_distance / 1000.0, 2),
                "duration_min": round(r.total_duration / 60.0, 1) if r.total_duration else 0,
                "stops_count": r.total_stops,
                "max_weight_kg": round(r.max_weight or 0, 1),
            })

        stats = result.statistics
        return {
            "routes": routes,
            "vehicles_used": stats.vehicles_used if stats else 0,
            "vehicles_available": stats.vehicles_available if stats else 0,
            "nodes_assigned": stats.nodes_assigned if stats else 0,
            "nodes_unassigned": stats.nodes_unassigned if stats else 0,
            "total_distance_km": round(stats.total_distance / 1000.0, 2) if stats else 0,
            "solver_time_s": round(result.solver_time, 2),
            "unassigned": [
                {"name": u.name or u.id, "reason": u.reason}
                for u in result.unassigned
            ] if result.unassigned else [],
        }

    def optimize_bin_packing(self, items: list[dict], bins: list[dict]) -> dict:
        """
        Resuelve bin packing con OR-Tools Knapsack.
        Devuelve un dict con cajas usadas, items empacados y utilization.
        """
        try:
            bp_items = [BinPackingItem(**item) for item in items]
            bp_bins = [BinPackingBin(**b) for b in bins]
            request = BinPackingRequest(items=bp_items, bins=bp_bins)
        except Exception as e:
            return {"error": f"Error construyendo request: {e}"}

        solver = BinPackingSolver(request)
        result = solver.solve()
        self._last_result = result

        if result.errors:
            return {"error": "Solver encontró errores", "errors": result.errors}

        packed_bins = []
        for pb in result.packed_bins:
            packed_bins.append({
                "bin_id": pb.bin_id,
                "bin_name": pb.bin_name,
                "items": [{"id": i.id, "name": i.name, "weight": i.weight} for i in pb.items],
                "total_weight": round(pb.total_weight, 1),
                "utilization_pct": round(pb.utilization_weight * 100, 0),
            })

        return {
            "packed_bins": packed_bins,
            "bins_used": result.total_bins_used,
            "bins_available": result.total_bins_available,
            "items_packed": result.total_items_packed,
            "items_total": result.total_items,
            "total_weight": round(result.total_weight, 1),
            "unassigned_items": [
                {"id": i.id, "name": i.name, "weight": i.weight}
                for i in result.unassigned_items
            ],
            "warnings": result.warnings,
            "solver_time_s": round(result.solver_time, 3),
        }

    def optimize_min_cost_flow(self, schools: list[dict], neighborhoods: list[dict]) -> dict:
        """
        Resuelve asignación escolar con OR-Tools Min Cost Flow.
        Devuelve un dict con asignaciones, niños asignados y distancia total.
        """
        try:
            request = build_school_assignment(schools, neighborhoods)
        except Exception as e:
            return {"error": f"Error construyendo request: {e}"}

        solver = MinCostFlowSolver(request)
        result = solver.solve()
        self._last_result = result

        if result.errors:
            return {"error": "Solver encontró errores", "errors": result.errors}

        return {
            "assignments": result.assignments,
            "total_children_assigned": result.total_units_assigned,
            "total_distance_km": round(result.total_cost / 1000.0, 2),
            "solver_time_s": round(result.solver_time, 3),
        }

    # ─── Ejecución de tools por nombre ───────────────────────────

    def _execute_tool(self, name: str, args: dict) -> Any:
        """Ejecuta un tool por nombre. Harness tools → HarnessAPI, resto → métodos."""
        # Route harness tools
        if name in {t["function"]["name"] for t in HARNESS_TOOLS}:
            return self._harness.execute(name, args)

        if name == "optimize_vrp":
            return self.optimize_vrp(**args)
        elif name == "optimize_bin_packing":
            return self.optimize_bin_packing(**args)
        elif name == "optimize_min_cost_flow":
            return self.optimize_min_cost_flow(**args)
        return {"error": f"Tool desconocido: {name}"}

    def _validate_output(self, tool_name: str, result: dict) -> bool:
        """
        Valida que el output del tool sea coherente.
        Devuelve True si el resultado es válido, False si hay error.
        """
        if not isinstance(result, dict):
            return False
        if "error" in result:
            logger.warning("Tool %s returned error: %s", tool_name, result["error"])
            return False

        # Validaciones específicas por tool
        if tool_name == "optimize_vrp":
            if not result.get("routes"):
                logger.warning("VRP returned no routes")
                return False
        elif tool_name == "optimize_bin_packing":
            if result.get("items_total", 0) > 0 and result.get("items_packed", 0) == 0:
                logger.warning("Bin packing packed 0 items out of %d", result.get("items_total", 0))
                return False
        elif tool_name == "optimize_min_cost_flow":
            if result.get("total_children_assigned", 0) == 0:
                logger.warning("Min cost flow assigned 0 children")
                return False

        return True

    # ─── Punto de entrada: chat ──────────────────────────────────

    def chat(self, user_input: str, max_tool_rounds: int = 3) -> str:
        """
        Un turno de conversación. El LLM decide si necesita más info,
        si llama un tool, o si explica un resultado.

        Si el LLM llama tools con parámetros inválidos, el error se
        alimenta de vuelta al LLM para que corrija (hasta max_tool_rounds).
        """
        self._messages.append({"role": "user", "content": user_input})

        for round_num in range(1, max_tool_rounds + 1):
            response = llm_call(
                messages=self._messages,
                tools=TOOLS_LOGISTICS + HARNESS_TOOLS,
                temperature=0.1,
                max_tokens=2500,
            )

            message = response.choices[0].message

            # Sin tool calls — respuesta conversacional normal
            if not (hasattr(message, "tool_calls") and message.tool_calls):
                content = message.content or ""
                self._messages.append({"role": "assistant", "content": content})
                return content

            # Guardar el mensaje del assistant con tool_calls en el historial
            self._messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # Ejecutar cada tool y añadir el resultado al historial
            all_valid = True
            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}

                logger.info("[round %d] Tool call: %s(%s)", round_num, tool_name, json.dumps(args, ensure_ascii=False))
                raw_result = self._execute_tool(tool_name, args)

                # NOOA pass-by-reference: store full result, send only bounded preview
                tr = ToolResult.from_value(tool_name, raw_result, tool_call_id=tc.id)
                self._result_registry.store(tr)
                logger.info("[round %d] Tool result preview: %s", round_num, tr.preview[:150])

                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": tr.preview,
                })

                if not self._validate_output(tool_name, raw_result):
                    all_valid = False

            # Si todos los tools dieron resultados válidos, pedir explicación
            if all_valid:
                explain_response = llm_call(
                    messages=self._messages,
                    temperature=0.3,
                    max_tokens=1500,
                )
                explanation = explain_response.choices[0].message.content.strip()
                self._messages.append({"role": "assistant", "content": explanation})
                return explanation

            # Si hubo errores, el loop continúa — el LLM verá los errores
            # en el historial y podrá corregir sus parámetros en el siguiente round
            logger.info("[round %d] Some tools failed — letting LLM retry with corrected params", round_num)

        # Si agotó los rounds, pedir explicación de lo que hay
        explain_response = llm_call(
            messages=self._messages,
            temperature=0.3,
            max_tokens=1500,
        )
        explanation = explain_response.choices[0].message.content.strip()
        self._messages.append({"role": "assistant", "content": explanation})
        return explanation

    def reset(self):
        """Reinicia la conversación manteniendo la ciudad."""
        self._last_result = None
        self._init_system_prompt()
