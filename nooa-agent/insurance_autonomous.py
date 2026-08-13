"""
Agente de seguros autónomo — hereda de AutonomousAgent.

Demuestra que crear un nuevo agente son ~80 líneas:
- tools_schema: 3 tools de seguros
- system_prompt: qué decide el LLM (aprobar/rechazar reclamos)
- _execute_tool: usar InSAR + Sentinel para validar reclamos
- _prepare_event: preparar datos del reclamo

El pipeline completo (detectar, proponer, aprobar, ejecutar, validar)
se hereda de base_agent.AutonomousAgent — cero código duplicado.
"""

from __future__ import annotations

import logging
from typing import Any

from base_agent import AutonomousAgent
from shared_tools import tool_search_sentinel, tool_generate_deformation_map

logger = logging.getLogger(__name__)


# ─── Tools de seguros ────────────────────────────────────────────────

TOOLS_INSURANCE = [
    {
        "type": "function",
        "function": {
            "name": "check_deformation",
            "description": "Verifica deformación InSAR en la ubicación del reclamo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud de la propiedad"},
                    "lng": {"type": "number", "description": "Longitud de la propiedad"},
                    "magnitude": {"type": "number", "description": "Magnitud del sismo reportado"},
                },
                "required": ["lat", "lng", "magnitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_sentinel_imagery",
            "description": "Busca imágenes Sentinel-2 pre y post evento para comparar daño visible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud"},
                    "lng": {"type": "number", "description": "Longitud"},
                },
                "required": ["lat", "lng"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_claim",
            "description": "Evalúa el reclamo basado en deformación e imágenes. Recomienda aprobar, rechazar o inspección manual.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ─── System prompt ───────────────────────────────────────────────────

PROMPT_INSURANCE = """Eres un agente de evaluación de reclamos de seguros que usa datos satelitales InSAR.

Tu trabajo:
1. Recibir reclamos de daños por sismo
2. Verificar la deformación real del suelo con InSAR (Sentinel-1)
3. Verificar imágenes pre/post evento (Sentinel-2)
4. Recomendar: aprobar, rechazar o inspección manual

Reglas:
- Si la deformación InSAR en la ubicación del reclamo es > 50mm → probable daño real → aprobar
- Si la deformación es < 10mm y el reclamo es por daño estructural → posible fraude → inspección manual
- Si no hay datos sufelites → inspección manual
- NUNCA aprobar sin aprobación humana — el humano decide final
- Sé conciso y directo
"""


# ─── Agente de seguros (hereda de AutonomousAgent) ──────────────────

class InsuranceAutonomousAgent(AutonomousAgent):
    """
    Agente de seguros autónomo con human-in-the-loop.

    Hereda todo el pipeline de AutonomousAgent.
    Solo define tools, prompt y ejecución específica de seguros.
    """

    tools_schema = TOOLS_INSURANCE
    system_prompt = PROMPT_INSURANCE
    agent_name = "InsuranceAgent"
    default_search_query = "sismo terremoto Colombia daños reclamos seguro"

    def __init__(self, memory_db_path: str | None = None):
        super().__init__(memory_db_path)
        self._claim_data: dict = {}
        self._deformation_mm: float = 0.0
        self._has_imagery: bool = False

    def _prepare_event(self, event_data: dict) -> None:
        """Prepara los datos del reclamo."""
        self._claim_data = event_data
        logger.info("Reclamo: %s", event_data.get('claim_id', 'N/A'))
        logger.info("Propiedad: %s", event_data.get('address', 'N/A'))
        logger.info("Magnitud reportada: %s", event_data.get('magnitude', 0))

    def _execute_tool(self, name: str, args: dict) -> Any:
        """Ejecuta tools específicos de seguros."""

        if name == "check_deformation":
            lat = args.get("lat", 0)
            lng = args.get("lng", 0)
            mag = args.get("magnitude", 6.0)

            result = tool_generate_deformation_map(
                lat=lat, lng=lng, magnitude=mag,
                zones=[{"name": "propiedad", "lat": lat, "lng": lng}],
            )

            self._deformation_mm = result["max_deformation_mm"]
            severity = result["zones"][0]["severity"] if result["zones"] else "unknown"

            return {
                "location": f"{lat}, {lng}",
                "deformation_mm": round(self._deformation_mm, 1),
                "severity": severity,
                "assessment": "daño probable" if self._deformation_mm > 50 else "daño improbable",
            }

        elif name == "check_sentinel_imagery":
            result = tool_search_sentinel(
                lat=args.get("lat", 0),
                lng=args.get("lng", 0),
                days_before=14,
            )

            self._has_imagery = result.get("count", 0) > 0
            return {"imagery": self._has_imagery, "products": result.get("products", []), "count": result.get("count", 0)}

        elif name == "evaluate_claim":
            if self._deformation_mm > 50:
                recommendation = "APROBAR — deformación significativa confirmada"
            elif self._deformation_mm < 10:
                recommendation = "INSPECCIÓN MANUAL — deformación baja, posible fraude"
            else:
                recommendation = "INSPECCIÓN MANUAL — deformación moderada, verificar in situ"

            return {
                "claim_id": self._claim_data.get("claim_id", "N/A"),
                "deformation_mm": round(self._deformation_mm, 1),
                "has_imagery": self._has_imagery,
                "recommendation": recommendation,
            }

        return {"error": f"Tool desconocido: {name}"}
