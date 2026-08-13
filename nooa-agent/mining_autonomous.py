"""
Agente minero autónomo — hereda de AutonomousAgent.

Solo define:
- tools_schema: 6 tools de minería
- system_prompt: qué decide el LLM
- _execute_tool: cómo ejecutar cada tool
- _prepare_event: cómo preparar el evento

El pipeline completo (detectar, proponer, aprobar, ejecutar, validar)
se hereda de base_agent.AutonomousAgent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from base_agent import AutonomousAgent
from shared_tools import tool_search_sentinel, tool_generate_deformation_map

from vrp_solver.models import Location, LocationType, OptimizeRequest, Vehicle
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request

from engines.bin_packing import (
    BinPackingItem, BinPackingBin, BinPackingRequest, BinPackingSolver,
)
from engines.min_cost_flow import (
    AssignmentRequest, MinCostFlowSolver,
    build_school_assignment,
)

logger = logging.getLogger(__name__)


# ─── Data structures for mining ──────────────────────────────────────

@dataclass
class MiningEvent:
    """Estado: evento minero detectado."""
    event_type: str  # "subsidence", "blast", "collapse", "spill"
    location: tuple[float, float]  # [lat, lng]
    severity: float = 0.0  # 0-10 scale
    affected_sites: list[dict] = field(default_factory=list)
    timestamp: str = ""
    source: str = "manual"


@dataclass
class MineSite:
    """Recurso: sitio minero."""
    id: str
    name: str
    coords: tuple[float, float]  # [lat, lng]
    ore_tonnage: float = 0.0  # tons available
    priority: int = 1  # 1=low, 2=medium, 3=high


@dataclass
class Truck:
    """Recurso: camión de transporte."""
    id: str
    name: str
    base_coords: tuple[float, float]  # [lat, lng]
    capacity: float = 20.0  # tons per trip


@dataclass
class EquipmentItem:
    """Recurso: item de equipo minero."""
    id: str
    name: str
    weight: float  # kg


@dataclass
class MiningResult:
    """Resultado completo de la operación minera."""
    transport_routes: list[dict] = field(default_factory=list)
    worker_assignment: list[dict] = field(default_factory=list)
    equipment_loading: list[dict] = field(default_factory=list)
    sentinel_products: list[dict] = field(default_factory=list)
    deformation_zones: list[dict] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Tools disponibles para el LLM ───────────────────────────────────

TOOLS_MINING = [
    {
        "type": "function",
        "function": {
            "name": "search_sentinel",
            "description": "Busca imágenes Sentinel-1 y Sentinel-2 del área minera en CDSE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud del sitio minero"},
                    "lng": {"type": "number", "description": "Longitud del sitio minero"},
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
            "description": "Genera mapa de deformación InSAR para monitorear subsidencia minera.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitud del epicentro"},
                    "lng": {"type": "number", "description": "Longitud del epicentro"},
                    "magnitude": {"type": "number", "description": "Severidad del evento (0-10)"},
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
                        "description": "Sitios afectados con coordenadas",
                    },
                },
                "required": ["lat", "lng", "magnitude", "zones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_transport",
            "description": "Optimiza rutas de camiones para transporte de mineral con VRP.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_worker_assignment",
            "description": "Asigna trabajadores a sitios mineros por capacidad usando Min Cost Flow.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_equipment_loading",
            "description": "Empaca equipo minero en camiones usando Bin Packing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_capacity": {"type": "number", "description": "Capacidad por camión en kg (default 5000)"},
                    "num_bins": {"type": "integer", "description": "Número de camiones (default 5)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mining_report",
            "description": "Genera un reporte minero completo en español natural.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ─── System prompt ───────────────────────────────────────────────────

PROMPT_MINING = """Eres un agente de operaciones mineras que monitorea eventos en sitios mineros en tiempo real.

Tu trabajo:
1. Buscar noticias web sobre subsidencia, derrumbes, explosiones o derrames en minas de Colombia y Latinoamérica
2. Analizar si el evento es relevante (severidad >= 3, zona activa, trabajadores en riesgo)
3. Decidir qué tools ejecutar para generar un plan de operación
4. NUNCA ejecutar sin aprobación humana — siempre propones, el humano decide

Reglas:
- Si detectas un evento relevante, propone ejecutar: search_sentinel, generate_deformation_map, optimize_transport, optimize_worker_assignment, optimize_equipment_loading, generate_mining_report
- Si la severidad es < 3 o no hay trabajadores en riesgo, reporta pero no propongas tools
- Siempre explica QUÉ vas a hacer y POR QUÉ antes de pedir aprobación
- Sé conciso y directo
"""


# ─── Agente minero (hereda de AutonomousAgent) ──────────────────────

class MiningAutonomousAgent(AutonomousAgent):
    """
    Agente minero autónomo con human-in-the-loop.

    Hereda de AutonomousAgent:
        - detect_event, propose_actions, approve_and_execute,
          validate_plan, run_full_pipeline

    Override:
        - tools_schema: 6 tools de minería
        - system_prompt: instrucciones de minería
        - agent_name: "MiningAgent"
        - _execute_tool: implementación de cada tool
        - _prepare_event: prepara MiningEvent + recursos
    """

    tools_schema = TOOLS_MINING
    system_prompt = PROMPT_MINING
    agent_name = "MiningAgent"
    default_search_query = "mina subsidencia derrumbe Colombia reciente"

    def __init__(self, city: str = "bogota", memory_db_path: str | None = None):
        super().__init__(memory_db_path)
        self.event: MiningEvent | None = None
        self.sites: list[MineSite] = []
        self.trucks: list[Truck] = []
        self.equipment: list[EquipmentItem] = []
        self._result = MiningResult()

    def _prepare_event(self, event_data: dict) -> None:
        """Prepara MiningEvent y carga recursos."""
        location = tuple(event_data.get("location", event_data.get("epicenter", [0, 0])))
        severity = event_data.get("severity", event_data.get("magnitude", 5.0))
        sites = event_data.get("sites", event_data.get("zones", []))

        mining_sites = [
            {
                "name": s["name"],
                "coords": [s["lat"], s["lng"]],
                "ore_tonnage": s.get("ore_tonnage", 100),
                "priority": s.get("priority", 2),
            }
            for s in sites
        ]

        self.event = MiningEvent(
            event_type=event_data.get("event_type", "subsidence"),
            location=location,
            severity=severity,
            timestamp=event_data.get("date", ""),
            source="autonomous_agent",
            affected_sites=mining_sites,
        )

        if "sites" in event_data:
            self.sites = [MineSite(**s) for s in event_data["sites"]]
        if "trucks" in event_data:
            self.trucks = [Truck(**t) for t in event_data["trucks"]]
        if "equipment" in event_data:
            self.equipment = [EquipmentItem(**e) for e in event_data["equipment"]]

        logger.info("Evento: %s (severidad %s)", self.event.event_type, self.event.severity)
        logger.info("Sitios: %d, Camiones: %d, Equipo: %d", len(self.sites), len(self.trucks), len(self.equipment))

    def _execute_tool(self, name: str, args: dict) -> Any:
        """Ejecuta un tool específico de minería."""

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
                magnitude=args.get("magnitude", 5.0),
                zones=args.get("zones", []),
            )
            self._tool_results["deformation"] = result["zones"]
            return {"zones": result["zones"], "max_deformation_mm": result["max_deformation_mm"]}

        elif name == "optimize_transport":
            if not self.sites or not self.trucks:
                return {"error": "Sin sitios o camiones para optimizar transporte"}

            locations = []
            vehicles = []

            base = self.trucks[0].base_coords
            locations.append(Location(
                id="base", name="Base Camiones",
                coords=list(base), type=LocationType.depot,
            ))

            for i, site in enumerate(self.sites, 1):
                locations.append(Location(
                    id=f"site_{i}", name=site.name,
                    coords=list(site.coords),
                    type=LocationType.delivery,
                    weight_demand=site.ore_tonnage,
                    service_time=600,
                ))

            for truck in self.trucks:
                vehicles.append(Vehicle(
                    id=truck.id, name=truck.name,
                    start_location_id="base", end_location_id="base",
                    weight_capacity=truck.capacity,
                ))

            request = OptimizeRequest(locations=locations, vehicles=vehicles)
            validation = validate_request(request)

            if not validation.is_valid:
                errors = "; ".join(e.message for e in validation.errors)
                return {"error": f"Validación falló: {errors}"}

            solver = VRPSolver.from_request(request, matrix_provider="synthetic")
            result = solver.solve()

            if result.errors:
                return {"error": f"Solver: {[e.message for e in result.errors]}"}

            routes = []
            for r in result.routes:
                stops = " -> ".join(s.name or s.location_id for s in r.stops)
                routes.append({
                    "vehicle": r.vehicle_name or r.vehicle_id,
                    "stops": stops,
                    "distance_km": r.total_distance / 1000,
                    "stops_count": r.total_stops,
                })

            self._tool_results["transport"] = routes
            return {"routes": routes, "count": len(routes)}

        elif name == "optimize_worker_assignment":
            if not self.sites:
                return {"error": "Sin sitios para asignar trabajadores"}

            neighborhoods = [
                {
                    "id": f"site_{i+1}",
                    "name": s.name,
                    "coords": list(s.coords),
                    "children": s.ore_tonnage / 10,
                }
                for i, s in enumerate(self.sites)
            ]

            schools = [
                {
                    "id": s.id,
                    "name": s.name,
                    "coords": list(s.coords),
                    "capacity": s.ore_tonnage,
                }
                for s in self.sites
            ]

            try:
                request = build_school_assignment(schools, neighborhoods)
            except Exception as e:
                return {"error": f"Error construyendo asignación: {e}"}

            solver = MinCostFlowSolver(request)
            result = solver.solve()

            if result.errors:
                return {"error": f"Solver: {result.errors}"}

            assignments = [
                {
                    "from": a["from_id"],
                    "to": a["to_id"],
                    "workers": a["units"],
                }
                for a in result.assignments
            ]

            self._tool_results["workers"] = assignments
            return {"assignments": assignments, "count": len(assignments)}

        elif name == "optimize_equipment_loading":
            if not self.equipment:
                return {"error": "Sin equipo para cargar"}

            capacity = args.get("bin_capacity", 5000.0)
            num_bins = args.get("num_bins", 5)

            items = [
                BinPackingItem(id=e.id, name=e.name, weight=e.weight)
                for e in self.equipment
            ]
            bins = [
                BinPackingBin(id=f"truck_{i+1}", name=f"Camión {i+1}", capacity_weight=capacity)
                for i in range(num_bins)
            ]

            request = BinPackingRequest(items=items, bins=bins)
            solver = BinPackingSolver(request)
            result = solver.solve()

            if result.errors:
                return {"error": f"Solver: {result.errors}"}

            packed = [
                {
                    "truck": pb.bin_name,
                    "items": [i.name for i in pb.items],
                    "total_weight": pb.total_weight,
                    "utilization": pb.utilization_weight,
                }
                for pb in result.packed_bins
            ]

            self._tool_results["equipment"] = packed
            return {
                "trucks_used": len(packed),
                "items_packed": result.total_items_packed,
                "unassigned": len(result.unassigned_items),
            }

        elif name == "generate_mining_report":
            report_parts = []

            if self._tool_results.get("sentinel"):
                report_parts.append(f"Imágenes Sentinel: {len(self._tool_results['sentinel'])}")

            if self._tool_results.get("deformation"):
                report_parts.append(f"Zonas de deformación: {len(self._tool_results['deformation'])}")

            if self._tool_results.get("transport"):
                report_parts.append(f"Rutas de transporte: {len(self._tool_results['transport'])}")

            if self._tool_results.get("workers"):
                report_parts.append(f"Asignaciones de trabajadores: {len(self._tool_results['workers'])}")

            if self._tool_results.get("equipment"):
                report_parts.append(f"Camiones cargados: {len(self._tool_results['equipment'])}")

            report = "\n".join(report_parts) if report_parts else "No hay resultados para reportar."
            self._tool_results["report"] = report
            return {"report": report}

        return {"error": f"Tool desconocido: {name}"}
