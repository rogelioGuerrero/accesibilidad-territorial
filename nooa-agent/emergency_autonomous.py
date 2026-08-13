"""
Agente de emergencias autónomo — hereda de AutonomousAgent.

Solo define:
- tools_schema: 6 tools de emergencia
- system_prompt: qué decide el LLM
- _execute_tool: cómo ejecutar cada tool
- _prepare_event: cómo preparar el evento

El pipeline completo (detectar, proponer, aprobar, ejecutar, validar)
se hereda de base_agent.AutonomousAgent.
"""

from __future__ import annotations

import logging
from typing import Any

from base_agent import AutonomousAgent
from code_action import strategy, PredictStrategy
from emergency_agent import (
    AidItem, Ambulance, EmergencyAgent, EmergencyEvent, Hospital,
)
from shared_tools import tool_search_sentinel, tool_generate_deformation_map

logger = logging.getLogger(__name__)


# ─── Tools disponibles para el LLM ───────────────────────────────────

TOOLS_EMERGENCY = [
    {
        "type": "function",
        "function": {
            "name": "search_sentinel",
            "description": "Busca imágenes Sentinel-1 y Sentinel-2 del área afectada en CDSE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud del epicentro"},
                    "lng": {"type": "number", "description": "Longitud del epicentro"},
                    "days_before": {"type": "integer", "description": "Días antes del evento (default 7)"},
                },
                "required": ["lat", "lng"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_deformation_map",
            "description": "Genera mapa de deformación InSAR basado en magnitud y ubicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud del epicentro"},
                    "lng": {"type": "number", "description": "Longitud del epicentro"},
                    "magnitude": {"type": "number", "description": "Magnitud del sismo"},
                    "zones": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "lat": {"type": "number"},
                                "lng": {"type": "number"},
                            },
                        },
                        "description": "Zonas afectadas con coordenadas",
                    },
                },
                "required": ["lat", "lng", "magnitude", "zones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_evacuation",
            "description": "Optimiza rutas de ambulancias con VRP.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_hospital_assignment",
            "description": "Asigna heridos a hospitales por capacidad usando Min Cost Flow.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_aid_distribution",
            "description": "Empaca ayuda humanitaria usando Bin Packing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_capacity": {"type": "number", "description": "Capacidad por caja en kg (default 50)"},
                    "num_bins": {"type": "integer", "description": "Número de cajas (default 5)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_response_plan",
            "description": "Genera un plan de respuesta completo en español natural.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ─── System prompt ───────────────────────────────────────────────────

PROMPT_EMERGENCY = """Eres un agente de respuesta a emergencias que monitorea eventos naturales en tiempo real.

Tu trabajo:
1. Buscar noticias web sobre sismos, inundaciones o desastres en Colombia y Latinoamérica
2. Analizar si el evento es relevante (magnitud >= 5.0, zona poblada, daños reportados)
3. Decidir qué tools ejecutar para generar un plan de respuesta
4. NUNCA ejecutar sin aprobación humana — siempre propones, el humano decide

Reglas:
- Si detectas un sismo relevante, propone ejecutar: search_sentinel, generate_deformation_map, optimize_evacuation, optimize_hospital_assignment, optimize_aid_distribution, generate_response_plan
- Si la magnitud es < 5.0 o no hay población cerca, reporta pero no propongas tools
- Siempre explica QUÉ vas a hacer y POR QUÉ antes de pedir aprobación
- Sé conciso y directo
"""


# ─── Agente de emergencias (hereda de AutonomousAgent) ──────────────

class EmergencyAutonomousAgent(AutonomousAgent):
    """
    Agente de emergencias autónomo con human-in-the-loop.

    Hereda de AutonomousAgent:
        - detect_event, propose_actions, approve_and_execute,
          validate_plan, run_full_pipeline

    Override:
        - tools_schema: 6 tools de emergencia
        - system_prompt: instrucciones de emergencias
        - agent_name: "EmergencyAgent"
        - _execute_tool: implementación de cada tool
        - _prepare_event: prepara EmergencyEvent + recursos
    """

    tools_schema = TOOLS_EMERGENCY
    system_prompt = PROMPT_EMERGENCY
    agent_name = "EmergencyAgent"
    default_search_query = "sismo terremoto Colombia reciente magnitud"

    def __init__(self, city: str = "bogota", memory_db_path: str | None = None):
        super().__init__(memory_db_path)
        self.engine = EmergencyAgent(city=city)
        self.event: EmergencyEvent | None = None

    def _prepare_event(self, event_data: dict) -> None:
        """Prepara EmergencyEvent y carga recursos en el motor."""
        epicenter = tuple(event_data.get("epicenter", [0, 0]))
        magnitude = event_data.get("magnitude", 0)
        zones = event_data.get("zones", [])

        emergency_zones = [
            {
                "name": z["name"],
                "coords": [z["lat"], z["lng"]],
                "severity": "alta",
                "casualties": z.get("casualties", 10),
            }
            for z in zones
        ]

        self.event = EmergencyEvent(
            event_type="sismo",
            epicenter=epicenter,
            magnitude=magnitude,
            timestamp=event_data.get("date", ""),
            source="autonomous_agent",
            affected_zones=emergency_zones,
        )

        if "hospitals" in event_data:
            self.engine.hospitals = [Hospital(**h) for h in event_data["hospitals"]]
        if "ambulances" in event_data:
            self.engine.ambulances = [Ambulance(**a) for a in event_data["ambulances"]]
        if "aid_items" in event_data:
            self.engine.aid_items = [AidItem(**a) for a in event_data["aid_items"]]

        init_result = self.engine.on_event(self.event)
        logger.info("Plan inicial: %s...", init_result[:150])

    def _execute_tool(self, name: str, args: dict) -> Any:
        """Ejecuta un tool específico de emergencias."""

        if name == "search_sentinel":
            result = tool_search_sentinel(
                lat=args.get("lat", 0),
                lng=args.get("lng", 0),
                days_before=args.get("days_before", 7),
            )
            self._tool_results["sentinel"] = result.get("products", [])
            return result

        elif name == "generate_deformation_map":
            result = tool_generate_deformation_map(
                lat=args.get("lat", 0),
                lng=args.get("lng", 0),
                magnitude=args.get("magnitude", 6.0),
                zones=args.get("zones", []),
            )
            self._tool_results["deformation"] = result["zones"]
            self.engine.deformation_map = result["_deformation_map"]
            return {"zones": result["zones"], "max_deformation_mm": result["max_deformation_mm"]}

        elif name == "optimize_evacuation":
            result = self.engine.optimize_evacuation()
            routes = len(self.engine._result.evacuation_routes)
            self._tool_results["evacuation"] = result
            return {"routes": routes, "summary": result[:300]}

        elif name == "optimize_hospital_assignment":
            result = self.engine.optimize_hospital_assignment()
            assignments = len(self.engine._result.hospital_assignment)
            self._tool_results["hospitals"] = result
            return {"assignments": assignments, "summary": result[:300]}

        elif name == "optimize_aid_distribution":
            capacity = args.get("bin_capacity", 50.0)
            num_bins = args.get("num_bins", 5)
            result = self.engine.optimize_aid_distribution(
                bin_capacity=capacity, num_bins=num_bins
            )
            bins = len(self.engine._result.aid_distribution)
            self._tool_results["aid"] = result
            return {"bins_used": bins, "summary": result[:300]}

        elif name == "generate_response_plan":
            result = self.engine.explain_full_response()
            self._tool_results["plan"] = result
            return {"plan": result}

        return {"error": f"Tool desconocido: {name}"}

    # ─── Code-as-action: método completado por LLM en runtime ────

    @strategy(PredictStrategy(temperature=0.2, max_tokens=2000))
    def cross_analysis(self, event: EmergencyEvent) -> str:
        """
        Analiza el evento de emergencia usando TODOS los resultados
        disponibles (deformación, Sentinel, evacuación, hospitales, ayuda)
        y genera un informe ejecutivo integrado en español.

        Debes:
        1. Obtener los resultados de tools previos con self._result_registry.get_value(nombre)
        2. Cruzar datos: deformación vs zonas afectadas, ambulancias vs hospitales
        3. Identificar el punto más crítico (mayor deformación, más heridos)
        4. Generar un resumen de 3 párrafos: situación, acciones tomadas, recomendaciones
        5. Devolver el informe como string
        """
        ...
