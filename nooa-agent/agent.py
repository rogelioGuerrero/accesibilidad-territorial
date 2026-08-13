"""
Agente VRP con LiteLLM (estilo NOOA: una sola clase).
Envuelve el VRPSolver existente sin modificarlo.

El agente:
1. Recibe una descripcion en lenguaje natural del problema
2. Usa el LLM para construir un OptimizeRequest (modelos Pydantic existentes)
3. Llama a VRPSolver con la matriz cacheada de Bogota
4. Usa el LLM para explicar el resultado en espanol
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from llm_utils import llm_call

from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    OptimizationObjective,
    SolverConfig,
    Vehicle,
)
from vrp_solver.solver import VRPSolver, SolverResult

from config import AVAILABLE_MATRICES

load_dotenv()


class VRPAgent:
    """
    Agente que entiende problemas VRP en lenguaje natural,
    los resuelve con OR-Tools, y explica la solucion en espanol.
    """

    def __init__(self, city: str = "bogota"):
        if city not in AVAILABLE_MATRICES:
            raise ValueError(f"Ciudad no disponible. Usa: {list(AVAILABLE_MATRICES.keys())}")
        self.city = city
        self._fixture = AVAILABLE_MATRICES[city]
        self._coords = self._load_coords()
        self._last_result: Optional[SolverResult] = None

    def _load_coords(self) -> list[tuple[float, float]]:
        with open(self._fixture["coords"]) as f:
            return [tuple(c) for c in json.load(f)["coords"]]

    def _build_system_prompt(self) -> str:
        coords_str = "\n".join(
            f"  Punto {i}: lat={lat}, lng={lng}"
            for i, (lat, lng) in enumerate(self._coords)
        )
        return f"""Eres un experto en logistica y optimizacion de rutas (VRP).
Tu trabajo es convertir la descripcion del usuario en un JSON valido para el solver.

Reglas:
- El punto 0 SIEMPRE es el deposito.
- Los puntos 1 a {len(self._coords)-1} son entregas.
- weight_demand es POSITIVO para entregas (ej: 10.0 para una entrega de 10kg).
- service_time en segundos (default: 300 = 5 min).
- El usuario puede no dar todos los detalles; usa valores razonables.
- Si el usuario no especifica capacidad, usa 100.0.
- Si el usuario no especifica numero de vehiculos, usa 1.

Coordenadas disponibles (orden: [lat, lng]):
{coords_str}

Responde SOLO con JSON valido, sin markdown, sin explicacion.
El JSON debe tener esta estructura exacta:
{{
  "locations": [
    {{"id": "depot", "name": "Deposito", "coords": [lat, lng], "type": "depot"}},
    {{"id": "del_1", "name": "Entrega 1", "coords": [lat, lng], "type": "delivery", "weight_demand": 10.0, "service_time": 300}}
  ],
  "vehicles": [
    {{"id": "veh_1", "name": "Vehiculo 1", "start_location_id": "depot", "end_location_id": "depot", "weight_capacity": 100.0}}
  ]
}}"""

    def _build_explanation_prompt(self, result: SolverResult) -> str:
        routes_info = []
        for r in result.routes:
            stops_str = " -> ".join(s.name or s.location_id for s in r.stops)
            dist_km = r.total_distance / 1000.0
            dur_min = r.total_duration / 60.0 if r.total_duration else 0
            routes_info.append(
                f"Vehiculo {r.vehicle_name or r.vehicle_id}:\n"
                f"  Ruta: {stops_str}\n"
                f"  Distancia: {dist_km:.2f} km\n"
                f"  Duracion: {dur_min:.1f} min\n"
                f"  Paradas: {r.total_stops}\n"
                f"  Peso maximo: {r.max_weight or 0:.1f} kg"
            )

        unassigned_info = ""
        if result.unassigned:
            unassigned_info = "\n\nNodos no asignados:\n" + "\n".join(
                f"  - {u.name or u.id}: {u.reason}" for u in result.unassigned
            )

        stats = result.statistics
        stats_info = ""
        if stats:
            stats_info = (
                f"\n\nEstadisticas:\n"
                f"  Vehiculos usados: {stats.vehicles_used}/{stats.vehicles_available}\n"
                f"  Nodos asignados: {stats.nodes_assigned}\n"
                f"  Nodos no asignados: {stats.nodes_unassigned}\n"
                f"  Distancia total: {stats.total_distance / 1000.0:.2f} km\n"
                f"  Duracion total: {stats.total_duration / 60.0:.1f} min"
            )

        return f"""Eres un asistente de logistica. Explica el resultado del solver VRP
en espanol claro y natural para el usuario. No uses JSON, no uses markdown.
Sé conciso pero completo.

Resultado del solver:
{chr(10).join(routes_info)}{unassigned_info}{stats_info}

Tiempo de computo: {result.solver_time:.2f}s

Explica el resultado:"""

    def solve_from_text(self, user_input: str) -> str:
        """
        Recibe descripcion en lenguaje natural,
        resuelve con OR-Tools, devuelve explicacion en espanol.
        """
        # Paso 1: LLM parsea el texto -> JSON del OptimizeRequest
        response = llm_call(
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw_json = response.choices[0].message.content.strip()
        # Limpiar markdown si el LLM lo envuelve
        if raw_json.startswith("```"):
            raw_json = raw_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            return f"Error: el LLM no genero JSON valido.\nRespuesta cruda:\n{raw_json}\nError: {e}"

        # Paso 2: Construir OptimizeRequest con los modelos Pydantic existentes
        try:
            locations = [Location(**loc) for loc in data["locations"]]
            vehicles = [Vehicle(**veh) for veh in data["vehicles"]]
            request = OptimizeRequest(locations=locations, vehicles=vehicles)
        except Exception as e:
            return f"Error construyendo request: {e}\nJSON recibido:\n{raw_json}"

        # Paso 3: Resolver con VRPSolver (tu solver, sin tocar nada)
        solver = VRPSolver.from_request(
            request,
            matrix_provider="cached",
            matrix_path=self._fixture["matrix"],
        )
        result = solver.solve()
        self._last_result = result

        if result.errors:
            error_msgs = "\n".join(f"  - {e.message}" for e in result.errors)
            return f"El solver encontro errores:\n{error_msgs}"

        # Paso 4: LLM explica el resultado en espanol
        explain_response = llm_call(
            messages=[
                {"role": "system", "content": "Eres un asistente de logistica que explica resultados de optimizacion de rutas en espanol natural y claro."},
                {"role": "user", "content": self._build_explanation_prompt(result)},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        return explain_response.choices[0].message.content.strip()
