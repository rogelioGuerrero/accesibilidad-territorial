"""
Agente VRP conversacional con LiteLLM.
Chat multi-turno que recolecta pedidos, construye el payload,
valida con el validator del solver, y si todo esta bien resuelve.

El agente respeta todas las validaciones del solver:
1. Al menos un deposito
2. Vehiculos referencian depositos validos
3. Capacidad total >= demanda total
4. Demanda individual <= capacidad del vehiculo mas grande
5. Skills compatibles
6. Horarios de vehiculos coherentes
7. Time windows coherentes
8. Pickup-delivery: IDs existen
"""

from __future__ import annotations

import json
import os
import re
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
    PickupDeliveryPair,
    SolverConfig,
    TimeWindow,
    Vehicle,
)
from vrp_solver.solver import VRPSolver, SolverResult
from vrp_solver.validator import validate_request

from config import AVAILABLE_MATRICES

load_dotenv()


class ChatVRPAgent:
    """
    Agente conversacional que toma pedidos en chat,
    construye el payload del solver, valida, y resuelve.
    """

    def __init__(self, city: str = "bogota"):
        if city not in AVAILABLE_MATRICES:
            raise ValueError(f"Ciudad no disponible. Usa: {list(AVAILABLE_MATRICES.keys())}")
        self.city = city
        self._fixture = AVAILABLE_MATRICES[city]
        self._coords = self._load_coords()
        self._max_points = self._fixture["max_points"]
        self._messages: list[dict] = []
        self._last_result: Optional[SolverResult] = None
        self._init_system_prompt()

    def _load_coords(self) -> list[tuple[float, float]]:
        with open(self._fixture["coords"]) as f:
            return [tuple(c) for c in json.load(f)["coords"]]

    def _init_system_prompt(self):
        coords_str = "\n".join(
            f"  Punto {i}: lat={lat}, lng={lng}"
            for i, (lat, lng) in enumerate(self._coords)
        )
        system = f"""Eres un asistente de logistica que conversa con el usuario para recolectar
los datos de un problema de optimizacion de rutas (VRP).

Tu trabajo es conversar naturalmente, hacer preguntas cuando falte informacion,
y cuando tengas todo, generar un JSON con la estructura del solver.

## Puntos disponibles en {self.city} (maximo {self._max_points} puntos, orden [lat, lng]):
{coords_str}

## Reglas del solver (DEBES cumplirlas o el solver rechazara el request):
1. El punto 0 SIEMPRE es el deposito (type="depot").
2. Los puntos 1 a {len(self._coords)-1} son entregas (type="delivery").
3. weight_demand es POSITIVO para entregas (ej: 10.0 = 10kg).
4. service_time en segundos (default: 300 = 5 min).
5. Cada vehiculo debe iniciar y terminar en un deposito (start_location_id y end_location_id).
6. La capacidad total de los vehiculos debe ser >= demanda total de entregas.
7. Ninguna entrega individual puede pesar mas que el vehiculo mas grande.
8. Si el usuario menciona ventanas de tiempo, van en segundos desde medianoche (ej: 28800 = 08:00).
9. Si el usuario menciona pickup-delivery, incluye el array "pickups_deliveries".
10. Maximo {self._max_points} puntos totales (incluyendo deposito).

## Flujo de conversacion:
1. Saluda brevemente y pregunta que necesita el usuario.
2. Si falta info (cuantos vehiculos, capacidad, cuantas entregas, peso), pregunta.
3. Cuando tengas TODA la info necesaria (vehiculos + capacidad + numero de entregas + peso),
   GENERA EL JSON INMEDIATAMENTE. NO pidas confirmacion. NO preguntes si quiere ventanas de tiempo.
   NO digas "Excelente" ni "Entendido". SOLO responde con el JSON.
   Si el usuario no menciono ventanas de tiempo, no las incluyas. Si no menciono pickups, incluye array vacio.
4. El JSON debe tener esta estructura:
{{
  "locations": [
    {{"id": "depot", "name": "Deposito", "coords": [lat, lng], "type": "depot"}},
    {{"id": "del_1", "name": "Entrega 1", "coords": [lat, lng], "type": "delivery", "weight_demand": 10.0, "service_time": 300}}
  ],
  "vehicles": [
    {{"id": "veh_1", "name": "Vehiculo 1", "start_location_id": "depot", "end_location_id": "depot", "weight_capacity": 100.0}}
  ],
  "pickups_deliveries": []
}}

## IMPORTANTE:
- Cuando generes el JSON, responde SOLO con el JSON, sin markdown, sin texto adicional.
- Mientras conversas (antes de tener toda la info), responde en espanol natural, sin JSON.
- Si el usuario da coordenadas propias, usalas. Si no, usa los puntos disponibles.
- Si el usuario pide mas entregas que puntos disponibles, dile el limite y ajusta."""

        self._messages = [{"role": "system", "content": system}]

    def chat(self, user_input: str) -> str:
        """Un turno de conversacion. Devuelve la respuesta del agente."""
        self._messages.append({"role": "user", "content": user_input})

        response = llm_call(
            messages=self._messages,
            temperature=0.1,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content.strip()
        self._messages.append({"role": "assistant", "content": raw})

        # Detectar si el LLM genero un JSON (intento de crear payload)
        json_data = self._try_extract_json(raw)
        if json_data is not None:
            return self._process_payload(json_data)

        return raw

    def _try_extract_json(self, text: str) -> Optional[dict]:
        """Intenta extraer JSON del texto del LLM."""
        # Limpiar markdown
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        # Intentar parsear directo
        try:
            data = json.loads(clean)
            if isinstance(data, dict) and "locations" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Buscar JSON embebido
        match = re.search(r'\{[^{}]*"locations"[^{}]*\}', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Intentar con regex mas amplia
        brace_start = clean.find("{")
        brace_end = clean.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                candidate = clean[brace_start:brace_end + 1]
                data = json.loads(candidate)
                if isinstance(data, dict) and "locations" in data:
                    return data
            except json.JSONDecodeError:
                pass

        return None

    def _process_payload(self, data: dict) -> str:
        """Construye OptimizeRequest, valida, y si todo ok resuelve."""
        try:
            locations = [Location(**loc) for loc in data["locations"]]
            vehicles = [Vehicle(**veh) for veh in data["vehicles"]]
            pairs_data = data.get("pickups_deliveries", [])
            pairs = [PickupDeliveryPair(**p) for p in pairs_data] if pairs_data else []
            request = OptimizeRequest(
                locations=locations,
                vehicles=vehicles,
                pickups_deliveries=pairs if pairs else None,
            )
        except Exception as e:
            error_msg = f"Error construyendo la solicitud: {e}\n\nPor favor corrige los datos."
            self._messages.append({"role": "system", "content": f"Error de construccion: {e}"})
            return error_msg

        # Validar con el validator del solver
        validation = validate_request(request)
        if not validation.is_valid:
            error_lines = []
            for err in validation.errors:
                error_lines.append(f"- [{err.code.value}] {err.message}")
            error_text = "\n".join(error_lines)
            self._messages.append({
                "role": "system",
                "content": f"La solicitud fue rechazada por el validador. Errores:\n{error_text}. "
                           f"Pide al usuario que corrija estos problemas."
            })
            return f"La solicitud no paso la validacion. Hay que corregir:\n\n{error_text}\n\n¿Puedes ajustar los datos?"

        # Todo valido -> resolver
        solver = VRPSolver.from_request(
            request,
            matrix_provider="cached",
            matrix_path=self._fixture["matrix"],
        )
        result = solver.solve()
        self._last_result = result

        if result.errors:
            error_msgs = "\n".join(f"- {e.message}" for e in result.errors)
            return f"El solver encontro errores:\n{error_msgs}"

        # Explicar resultado
        return self._explain_result(result)

    def _explain_result(self, result: SolverResult) -> str:
        """Usa el LLM para explicar el resultado en espanol natural."""
        routes_info = []
        for r in result.routes:
            stops_str = " -> ".join(s.name or s.location_id for s in r.stops)
            dist_km = r.total_distance / 1000.0
            dur_min = r.total_duration / 60.0 if r.total_duration else 0
            weight_info = f"\n  Peso maximo: {r.max_weight:.1f} kg" if r.max_weight else ""
            routes_info.append(
                f"Vehiculo {r.vehicle_name or r.vehicle_id}:\n"
                f"  Ruta: {stops_str}\n"
                f"  Distancia: {dist_km:.2f} km\n"
                f"  Duracion: {dur_min:.1f} min\n"
                f"  Paradas: {r.total_stops}{weight_info}"
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

        explain_prompt = f"""Eres un asistente de logistica. Explica el resultado del solver VRP
en espanol claro y natural para el usuario. No uses JSON, no uses markdown.
Sé conciso pero completo. Incluye la ruta de cada vehiculo, distancias, y si hubo nodos no asignados.

Resultado del solver:
{chr(10).join(routes_info)}{unassigned_info}{stats_info}

Tiempo de computo: {result.solver_time:.2f}s

Explica el resultado:"""

        explain_response = llm_call(
            messages=[
                {"role": "system", "content": "Eres un asistente de logistica que explica resultados de optimizacion de rutas en espanol natural y claro."},
                {"role": "user", "content": explain_prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        return explain_response.choices[0].message.content.strip()

    def reset(self):
        """Reinicia la conversacion manteniendo la ciudad."""
        self._last_result = None
        self._init_system_prompt()
