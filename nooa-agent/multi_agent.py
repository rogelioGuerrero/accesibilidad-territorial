"""
Agente multi-motor con filosofia NOOA.

Filosofia NOOA:
- El agente es una clase
- Los metodos son capabilities (tools que el LLM puede llamar)
- Los campos son estado (persisten entre turnos)
- Los docstrings son prompts (la documentacion es la instruccion para el LLM)

Motores disponibles:
1. VRP - Rutas de entrega (usa el solver existente)
2. Bin Packing - Empaquetado de productos
3. Asignacion escolar - Min Cost Flow + VRP

El agente muestra un menu, el usuario elige, y el LLM extrae las cantidades
del texto del usuario para construir el payload del motor seleccionado.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from llm_utils import llm_call

from vrp_solver.models import Location, LocationType, OptimizeRequest, Vehicle
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request

from engines.bin_packing import (
    BinPackingItem, BinPackingBin, BinPackingRequest, BinPackingSolver, BinPackingResult,
)
from engines.min_cost_flow import (
    AssignmentNode, AssignmentArc, AssignmentRequest, MinCostFlowSolver,
    AssignmentResult, build_school_assignment,
)

from config import AVAILABLE_MATRICES

load_dotenv()

MENU = """¿Qué problema quieres resolver?

  1. Rutas de entrega (VRP) — optimizar rutas de vehículos
  2. Empaquetado de productos (Bin Packing) — empacar items en cajas
  3. Asignación escolar (Min Cost Flow) — asignar niños a escuelas por distancia

Selecciona una opción (1-3): """

# Templates de preguntas por motor
MOTOR_QUESTIONS = {
    1: {
        "title": "Rutas de entrega (VRP)",
        "questions": [
            "¿Cuántos vehículos tienes?",
            "¿Cuál es la capacidad de cada vehículo (kg)?",
            "¿Cuántas entregas necesitas hacer?",
            "¿Cuánto pesa cada entrega (kg)?",
        ],
        "prompt_template": """Eres un experto en logistica. Convierte la respuesta del usuario en JSON para el solver VRP.

Reglas:
- El punto 0 es el deposito (type="depot").
- Los puntos 1 a {max_points} son entregas (type="delivery").
- weight_demand es POSITIVO (ej: 10.0 = 10kg).
- service_time default: 300 segundos.
- Cada vehiculo inicia y termina en el deposito.

Coordenadas disponibles ([lat, lng]):
{coords_str}

Respuesta del usuario:
{user_text}

Genera SOLO JSON (sin markdown, sin texto):
{{
  "locations": [
    {{"id": "depot", "name": "Deposito", "coords": [lat, lng], "type": "depot"}},
    {{"id": "del_1", "name": "Entrega 1", "coords": [lat, lng], "type": "delivery", "weight_demand": 10.0, "service_time": 300}}
  ],
  "vehicles": [
    {{"id": "veh_1", "name": "Vehiculo 1", "start_location_id": "depot", "end_location_id": "depot", "weight_capacity": 100.0}}
  ]
}}""",
    },
    2: {
        "title": "Empaquetado de productos (Bin Packing)",
        "questions": [
            "¿Cuántos productos necesitas empacar?",
            "¿Cuánto pesa cada producto (kg)?",
            "¿Cuántos tipos de caja tienes?",
            "¿Cuál es la capacidad de cada tipo de caja (kg)?",
        ],
        "prompt_template": """Eres un experto en empaquetado. Convierte la respuesta del usuario en JSON para bin packing.

Reglas:
- Cada item tiene un id, name, y weight (kg).
- Cada caja (bin) tiene un id, name, y capacity_weight (kg).
- Si el usuario dice "3 cajas de 50kg", crea 3 bins con capacidad 50.
- Si el usuario no especifica volumen, omite el campo volume.

Respuesta del usuario:
{user_text}

Genera SOLO JSON (sin markdown, sin texto):
{{
  "items": [
    {{"id": "item_1", "name": "Producto 1", "weight": 10.0}},
    {{"id": "item_2", "name": "Producto 2", "weight": 5.0}}
  ],
  "bins": [
    {{"id": "bin_1", "name": "Caja 1", "capacity_weight": 50.0}},
    {{"id": "bin_2", "name": "Caja 2", "capacity_weight": 50.0}}
  ]
}}""",
    },
    3: {
        "title": "Asignación escolar (Min Cost Flow)",
        "questions": [
            "¿Cuántos barrios tienen niños que necesitan escuela?",
            "¿Cuántos niños hay en cada barrio?",
            "¿Cuántas escuelas hay disponibles?",
            "¿Cuál es la capacidad de cada escuela?",
        ],
        "prompt_template": """Eres un experto en asignacion escolar. Convierte la respuesta del usuario en JSON para asignacion con Min Cost Flow.

Reglas:
- Cada barrio tiene id, name, coords [lat, lng], y children (numero de niños).
- Cada escuela tiene id, name, coords [lat, lng], y capacity (numero de cupos).
- Si el usuario no da coordenadas, genera coordenadas realistas para una ciudad latinoamericana (lat ~4.5-4.8, lng ~-74.0 a -74.2 para Bogota).
- Los ids deben ser unicos.

Respuesta del usuario:
{user_text}

Genera SOLO JSON (sin markdown, sin texto):
{{
  "neighborhoods": [
    {{"id": "bar_1", "name": "Barrio Norte", "coords": [4.65, -74.1], "children": 50}},
    {{"id": "bar_2", "name": "Barrio Sur", "coords": [4.55, -74.15], "children": 30}}
  ],
  "schools": [
    {{"id": "esc_1", "name": "Escuela A", "coords": [4.6, -74.05], "capacity": 60}},
    {{"id": "esc_2", "name": "Escuela B", "coords": [4.7, -74.12], "capacity": 40}}
  ]
}}""",
    },
}


class MultiEngineAgent:
    """
    Agente multi-motor con filosofia NOOA.

    Estado (campos que persisten entre turnos):
        - motor_elegido: que motor selecciono el usuario
        - ciudad: que ciudad/matriz usar
        - messages: historial de conversacion

    Capabilities (metodos = tools):
        - solve_vrp: resuelve rutas de entrega
        - solve_bin_packing: resuelve empaquetado
        - solve_school_assignment: resuelve asignacion escolar
        - explain_result: explica cualquier resultado en espanol
    """

    def __init__(self, city: str = "bogota"):
        if city not in AVAILABLE_MATRICES:
            raise ValueError(f"Ciudad no disponible: {city}")
        self.city = city
        self._fixture = AVAILABLE_MATRICES[city]
        self._coords = self._load_coords()
        self.motor_elegido: Optional[int] = None
        self._messages: list[dict] = []

    def _load_coords(self) -> list[tuple[float, float]]:
        with open(self._fixture["coords"]) as f:
            return [tuple(c) for c in json.load(f)["coords"]]

    def show_menu(self) -> str:
        """Muestra el menu de motores disponibles."""
        return MENU

    def select_motor(self, choice: str) -> str:
        """Procesa la seleccion del motor y devuelve las preguntas."""
        try:
            n = int(choice.strip())
        except ValueError:
            return "Opción inválida. Elige 1, 2 o 3."

        if n not in MOTOR_QUESTIONS:
            return "Opción inválida. Elige 1, 2 o 3."

        self.motor_elegido = n
        motor = MOTOR_QUESTIONS[n]
        questions_text = "\n".join(f"  - {q}" for q in motor["questions"])
        return f"**{motor['title']}**\n\nNecesito esta información:\n{questions_text}\n\nCuéntame en una o varias frases:"

    def process_user_response(self, user_text: str) -> str:
        """
        Procesa la respuesta del usuario: extrae cantidades con LLM,
        construye el payload, valida, ejecuta el motor, y explica el resultado.
        """
        if self.motor_elegido is None:
            return "Primero selecciona un motor del menú."

        motor = MOTOR_QUESTIONS[self.motor_elegido]

        # LLM extrae cantidades del texto del usuario
        if self.motor_elegido == 1:
            prompt = motor["prompt_template"].format(
                max_points=len(self._coords) - 1,
                coords_str="\n".join(
                    f"  Punto {i}: [{lat}, {lng}]" for i, (lat, lng) in enumerate(self._coords)
                ),
                user_text=user_text,
            )
        else:
            prompt = motor["prompt_template"].format(user_text=user_text)

        response = llm_call(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        raw_json = response.choices[0].message.content.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            return f"Error: no pude entender los datos.\nJSON: {raw_json}\nError: {e}"

        # Ejecutar el motor correspondiente
        if self.motor_elegido == 1:
            return self._solve_vrp(data)
        elif self.motor_elegido == 2:
            return self._solve_bin_packing(data)
        elif self.motor_elegido == 3:
            return self._solve_school_assignment(data)

        return "Motor no implementado."

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITIES (tools que el agente puede ejecutar)
    # ═══════════════════════════════════════════════════════════════════

    def _solve_vrp(self, data: dict) -> str:
        """Capability: resolver VRP con el solver existente."""
        try:
            locations = [Location(**loc) for loc in data["locations"]]
            vehicles = [Vehicle(**veh) for veh in data["vehicles"]]
            request = OptimizeRequest(locations=locations, vehicles=vehicles)
        except Exception as e:
            return f"Error construyendo solicitud VRP: {e}"

        # Validar
        validation = validate_request(request)
        if not validation.is_valid:
            errors = "\n".join(f"- [{err.code.value}] {err.message}" for err in validation.errors)
            return f"Validación falló:\n{errors}\n\nAjusta los datos e inténtalo de nuevo."

        # Resolver
        solver = VRPSolver.from_request(
            request,
            matrix_provider="cached",
            matrix_path=self._fixture["matrix"],
        )
        result = solver.solve()

        if result.errors:
            errors = "\n".join(f"- {e.message}" for e in result.errors)
            return f"El solver encontró errores:\n{errors}"

        return self._explain_vrp_result(result)

    def _solve_bin_packing(self, data: dict) -> str:
        """Capability: resolver bin packing con OR-Tools."""
        try:
            items = [BinPackingItem(**item) for item in data["items"]]
            bins = [BinPackingBin(**b) for b in data["bins"]]
            request = BinPackingRequest(items=items, bins=bins)
        except Exception as e:
            return f"Error construyendo solicitud de empaquetado: {e}"

        # Validar
        total_weight = sum(i.weight for i in items)
        total_capacity = sum(b.capacity_weight for b in bins)
        if total_weight > total_capacity:
            return (f"Capacidad insuficiente: {total_weight}kg de productos "
                    f"vs {total_capacity}kg de capacidad total.\n"
                    f"Agrega más cajas o reduce los productos.")

        solver = BinPackingSolver(request)
        result = solver.solve()

        if result.errors:
            errors = "\n".join(f"- {e}" for e in result.errors)
            return f"Error en empaquetado:\n{errors}"

        return self._explain_bin_packing_result(result)

    def _solve_school_assignment(self, data: dict) -> str:
        """Capability: resolver asignacion escolar con Min Cost Flow."""
        try:
            neighborhoods = data["neighborhoods"]
            schools = data["schools"]
            request = build_school_assignment(schools, neighborhoods)
        except Exception as e:
            return f"Error construyendo solicitud de asignación: {e}"

        # Validar
        total_children = sum(nb["children"] for nb in neighborhoods)
        total_capacity = sum(sc["capacity"] for sc in schools)
        if total_children > total_capacity:
            return (f"Capacidad insuficiente: {total_children} niños "
                    f"vs {total_capacity} cupos en escuelas.\n"
                    f"Agrega más escuelas o reduce los niños.")

        solver = MinCostFlowSolver(request)
        result = solver.solve()

        if result.errors:
            errors = "\n".join(f"- {e}" for e in result.errors)
            return f"Error en asignación:\n{errors}"

        return self._explain_assignment_result(result, neighborhoods, schools)

    # ═══════════════════════════════════════════════════════════════════
    # EXPLAINERS (LLM explica resultados en espanol natural)
    # ═══════════════════════════════════════════════════════════════════

    def _explain_vrp_result(self, result) -> str:
        """Explica resultado VRP en espanol."""
        routes_info = []
        for r in result.routes:
            stops = " -> ".join(s.name or s.location_id for s in r.stops)
            dist_km = r.total_distance / 1000.0
            dur_min = r.total_duration / 60.0 if r.total_duration else 0
            routes_info.append(
                f"Vehiculo {r.vehicle_name or r.vehicle_id}: {stops}\n"
                f"  Distancia: {dist_km:.2f} km | Duracion: {dur_min:.1f} min | "
                f"Paradas: {r.total_stops} | Peso max: {r.max_weight or 0:.1f}kg"
            )

        unassigned = ""
        if result.unassigned:
            unassigned = "\n\nNo asignados:\n" + "\n".join(
                f"  - {u.name or u.id}: {u.reason}" for u in result.unassigned
            )

        stats = result.statistics
        stats_str = ""
        if stats:
            stats_str = (
                f"\n\nTotal: {stats.vehicles_used}/{stats.vehicles_available} vehiculos, "
                f"{stats.nodes_assigned} entregas, "
                f"{stats.total_distance / 1000:.2f} km totales"
            )

        data = f"{chr(10).join(routes_info)}{unassigned}{stats_str}\n\nTiempo: {result.solver_time:.2f}s"
        return self._llm_explain("Explica este resultado de optimizacion de rutas VRP en espanol:", data)

    def _explain_bin_packing_result(self, result: BinPackingResult) -> str:
        """Explica resultado bin packing en espanol."""
        bins_info = []
        for pb in result.packed_bins:
            items_str = ", ".join(f"{i.name} ({i.weight}kg)" for i in pb.items)
            bins_info.append(
                f"{pb.bin_name}: {len(pb.items)} items, {pb.total_weight:.1f}kg / "
                f"{pb.utilization_weight * 100:.0f}% usado\n  Items: {items_str}"
            )

        unassigned = ""
        if result.unassigned_items:
            unassigned = "\n\nNo empacados:\n" + "\n".join(
                f"  - {i.name} ({i.weight}kg)" for i in result.unassigned_items
            )

        data = (
            f"{chr(10).join(bins_info)}{unassigned}\n\n"
            f"Total: {result.total_bins_used}/{result.total_bins_available} cajas usadas, "
            f"{result.total_items_packed}/{result.total_items} items empacados, "
            f"{result.total_weight:.1f}kg total\n"
            f"Tiempo: {result.solver_time:.3f}s"
        )
        return self._llm_explain("Explica este resultado de empaquetado (bin packing) en espanol:", data)

    def _explain_assignment_result(self, result: AssignmentResult, neighborhoods: list, schools: list) -> str:
        """Explica resultado asignacion escolar en espanol."""
        # Agrupar asignaciones por escuela
        school_assignments: dict[str, list[dict]] = {}
        for a in result.assignments:
            school_assignments.setdefault(a["to_id"], []).append(a)

        school_names = {s["id"]: s["name"] for s in schools}
        nb_names = {n["id"]: n["name"] for n in neighborhoods}

        schools_info = []
        for sid, assigns in school_assignments.items():
            total_kids = sum(a["units"] for a in assigns)
            from_list = ", ".join(
                f"{nb_names.get(a['from_id'], a['from_id'])} ({a['units']} niños)"
                for a in assigns
            )
            schools_info.append(
                f"{school_names.get(sid, sid)}: {total_kids} niños asignados\n"
                f"  Desde: {from_list}"
            )

        unassigned = ""
        if result.unassigned_demand > 0:
            unassigned = f"\n\n{result.unassigned_demand} niños sin asignar (capacidad insuficiente)"

        data = (
            f"{chr(10).join(schools_info)}{unassigned}\n\n"
            f"Total: {result.total_units_assigned} niños asignados, "
            f"distancia total: {result.total_cost / 1000:.2f} km\n"
            f"Tiempo: {result.solver_time:.3f}s"
        )
        return self._llm_explain("Explica este resultado de asignacion escolar en espanol:", data)

    def _llm_explain(self, system_msg: str, data: str) -> str:
        """LLM explica el resultado en espanol natural."""
        response = llm_call(
            messages=[
                {"role": "system", "content": "Eres un asistente de logistica que explica resultados en espanol claro y conciso. No uses JSON ni markdown."},
                {"role": "user", "content": f"{system_msg}\n\n{data}"},
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
